"""List every snapshot file in the selected monthly bundles and group byte-identical ones.

    python -m src.clean.manifest 202405 202507 202508 [--workers 8] [--source CurrentWeather.xml ...]

Nothing is extracted to disk and data/raw is not changed. For each source (a folder with
a `bundle/` subfolder under data/raw) and each bundle whose name starts with one of the
months, every zip member becomes one row of

    data/interim/manifest/<resource file name>.csv
        bundle, index, member, fetch_time, size, crc32, group, n_copies

- `index` is the member's position in the zip (a name can occur twice, e.g. 20250805-2056).
- `fetch_time` is YYYYMMDD-HHMM from the member name: when the archive fetched the file.
- `group` = `bundle:index` of the first member with the same bytes (not the name, which
  can repeat); `n_copies` = group size.
  One file per group is enough to parse; the other rows keep every fetch time (lossless).

Identity is decided in two steps, both exact:
1. Members whose (size, CRC-32) from the zip directory occur once are unique: different
   size or CRC means different bytes. This needs no decompression.
2. Members sharing (size, CRC-32) are decompressed and compared by SHA-256.

Also written: data/interim/manifest/summary.csv, one row per source and bundle.
Sources without a bundle in the months are listed and skipped.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import zipfile
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from os import cpu_count
from pathlib import Path

from tqdm import tqdm

from src.config import INTERIM_DIR, RAW_DIR

OUT_DIR = INTERIM_DIR / "manifest"
CHUNK_BYTES = 256 * 1024 * 1024  # members per worker task, by uncompressed size

_zips: dict[Path, zipfile.ZipFile] = {}  # one open ZipFile per bundle per worker process


def _sha256(bundle: Path, indexes: list[int]) -> list[tuple[int, str, int]]:
    """SHA-256 of the given members of one bundle, streamed; returns (index, digest, bytes)."""
    if bundle not in _zips:
        _zips[bundle] = zipfile.ZipFile(bundle)
    z = _zips[bundle]
    infos = z.infolist()
    out = []
    for i in indexes:
        h = hashlib.sha256()
        with z.open(infos[i]) as f:  # zipfile checks the CRC-32 at the end of the read
            for block in iter(lambda: f.read(1 << 20), b""):
                h.update(block)
        out.append((i, h.hexdigest(), infos[i].file_size))
    return out


def _sources(months: list[str], only: list[str] | None) -> tuple[dict[str, list[Path]], list[str]]:
    found, skipped = {}, []
    for folder in sorted(RAW_DIR.rglob("bundle")):
        name = folder.parent.name
        if only is not None and name not in only:
            continue
        bundles = sorted(b for b in folder.glob("*.zip") if b.name[:6] in months)
        if name in found:
            raise ValueError(f"two sources named {name}: {folder.parent}")
        if bundles:
            found[name] = bundles
        else:
            skipped.append(str(folder.parent.relative_to(RAW_DIR)))
    if only is not None and set(only) - set(found) - {Path(s).name for s in skipped}:
        raise ValueError(f"unknown source(s): {sorted(set(only) - set(found) - {Path(s).name for s in skipped})}")
    return found, skipped


def build(months: list[str], workers: int, only: list[str] | None = None) -> None:
    sources, skipped = _sources(months, only)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for s in skipped:
        print(f"skipped (no bundle in {', '.join(months)}): {s}")

    # Step 1: read every zip directory (fast, no decompression).
    rows: dict[str, list[dict]] = {}
    for name, bundles in sources.items():
        rows[name] = []
        for b in bundles:
            with zipfile.ZipFile(b) as z:
                for i, info in enumerate(z.infolist()):
                    if info.is_dir():
                        raise ValueError(f"{b}: unexpected directory member {info.filename}")
                    member = info.filename.rsplit("/", 1)[-1]
                    rows[name].append({"bundle": b.name, "index": i, "member": member,
                                       "fetch_time": member[:13], "size": info.file_size,
                                       "crc32": f"{info.CRC:08x}", "_path": b})

    # Step 2: hash only members whose (size, crc32) is shared within the source.
    tasks: list[tuple[Path, list[int]]] = []
    for name, rs in rows.items():
        by_key = defaultdict(list)
        for r in rs:
            by_key[(r["size"], r["crc32"])].append(r)
        todo = defaultdict(list)
        for group in by_key.values():
            if len(group) > 1:
                for r in group:
                    todo[r["_path"]].append(r)
        for path, rs_ in todo.items():
            chunk, size = [], 0
            for r in rs_:
                chunk.append(r["index"])
                size += r["size"]
                if size >= CHUNK_BYTES:
                    tasks.append((path, chunk))
                    chunk, size = [], 0
            if chunk:
                tasks.append((path, chunk))

    digests: dict[tuple[Path, int], str] = {}
    to_hash = {(path, i) for path, ix in tasks for i in ix}
    total = sum(r["size"] for rs in rows.values() for r in rs if (r["_path"], r["index"]) in to_hash)
    n_all = sum(len(rs) for rs in rows.values())
    n_hash = sum(len(ix) for _, ix in tasks)
    print(f"{n_all:,} members in {sum(len(b) for b in sources.values())} bundles; "
          f"{n_hash:,} share size+CRC and are hashed ({total / 1e9:.1f} GB uncompressed)")
    with ProcessPoolExecutor(max_workers=workers) as pool, \
            tqdm(total=total, unit="B", unit_scale=True, desc="hashing") as bar:
        futures = [pool.submit(_sha256, path, ix) for path, ix in tasks]
        paths = {f: path for f, (path, _) in zip(futures, tasks)}
        for f in as_completed(futures):
            for i, digest, nbytes in f.result():
                digests[(paths[f], i)] = digest
                bar.update(nbytes)

    # Step 3: group, write one CSV per source and the summary.
    summary = []
    for name, rs in rows.items():
        first: dict[tuple, str] = {}
        for r in rs:  # rows are in bundle order, then zip order: the first copy names the group
            key = (r["size"], r["crc32"], digests.get((r["_path"], r["index"])))
            r["group"] = first.setdefault(key, f"{r['bundle']}:{r['index']}")
        n = defaultdict(int)
        for r in rs:
            n[r["group"]] += 1
        with (OUT_DIR / f"{name}.csv").open("w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["bundle", "index", "member", "fetch_time", "size", "crc32", "group", "n_copies"])
            for r in rs:
                w.writerow([r["bundle"], r["index"], r["member"], r["fetch_time"], r["size"],
                            r["crc32"], r["group"], n[r["group"]]])
        for b in sorted({r["bundle"] for r in rs}):
            br = [r for r in rs if r["bundle"] == b]
            names = defaultdict(int)
            for r in br:
                names[r["member"]] += 1
            summary.append({
                "source": name, "bundle": b, "members": len(br),
                "distinct_contents": len({r["group"] for r in br}),
                "extra_copies": len(br) - len({r["group"] for r in br}),
                "groups_with_copies": len({r["group"] for r in br if n[r["group"]] > 1}),
                "repeated_names": sum(c - 1 for c in names.values() if c > 1),
                "copies_of_other_bundle": sum(1 for r in br if not r["group"].startswith(b + ":")),
                "uncompressed_gb": round(sum(r["size"] for r in br) / 1e9, 3),
            })
    with (OUT_DIR / "summary.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(summary[0]))
        w.writeheader()
        w.writerows(summary)

    print(f"\nwritten to {OUT_DIR}")
    print(f"{'source':45} {'bundle':13} {'members':>8} {'distinct':>8} {'extra':>6} {'%':>5} {'rep.names':>9}")
    for s in summary:
        pct = 100 * s["extra_copies"] / s["members"]
        print(f"{s['source']:45} {s['bundle']:13} {s['members']:8,} {s['distinct_contents']:8,} "
              f"{s['extra_copies']:6,} {pct:5.1f} {s['repeated_names']:9}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("months", nargs="+", help="YYYYMM, matched against bundle names")
    p.add_argument("--workers", type=int, default=cpu_count())
    p.add_argument("--source", nargs="+", help="only these resource file names, e.g. CurrentWeather.xml")
    a = p.parse_args()
    build(a.months, a.workers, a.source)


if __name__ == "__main__":
    main()
