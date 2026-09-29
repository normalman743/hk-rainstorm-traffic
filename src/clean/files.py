"""Work on snapshot files: take them out of a monthly bundle, merge byte-identical copies.

A bundle (data/raw/<host>/<path>/bundle/<YYYYMMDD>.zip) holds one member per archived
snapshot, named `<url-encoded folder>/<YYYYMMDD-HHMM>-<resource file name>`, where
YYYYMMDD-HHMM is when the archive fetched the file, not when it was measured.

Observed on 5 Aug 2025 (S1, 947 files):
- 82 snapshots were fetched twice, 2–4 min apart, with byte-identical content
  (e.g. 0007 and 0010 both hold 00:00:00–00:01:00). No period had two different contents.
- One member name (20250805-2056) occurs twice in the bundle.
"""

from __future__ import annotations

import hashlib
import shutil
import zipfile
from pathlib import Path


def extract(bundle: Path, out_dir: Path, days: list[str] | None = None) -> list[Path]:
    """Write the bundle's snapshot files, unchanged, to out_dir; return the paths written.

    days: archive dates `YYYYMMDD` to take (matched on the file name, i.e. the fetch
    date, so the first minutes of a day can hold the previous day's data); None = all.
    Lossless: a member name that occurs twice with identical content is written once with
    its time repeated (`20250805-2056-2056-<resource>`), as in merge_identical; different
    content raises. An existing file in out_dir (from an earlier run) is kept if identical,
    else raises.
    """
    with zipfile.ZipFile(bundle) as z:
        members = [i for i in z.infolist() if not i.is_dir()]
        if days is not None:
            members = [i for i in members if i.filename.rsplit("/", 1)[-1][:8] in days]
            missing = set(days) - {i.filename.rsplit("/", 1)[-1][:8] for i in members}
            if missing:
                raise ValueError(f"{bundle}: no files for {sorted(missing)}")

        need = sum(i.file_size for i in members)
        out_dir.mkdir(parents=True, exist_ok=True)
        free = shutil.disk_usage(out_dir).free
        if need > free:
            raise OSError(f"{bundle}: {need / 1e9:.2f} GB to extract, {free / 1e9:.2f} GB free")

        written: list[Path] = []
        this_run: dict[str, int] = {}  # index in `written` of each member name seen in this call
        for info in members:
            name = info.filename.rsplit("/", 1)[-1]
            path = out_dir / name
            data = z.read(info)
            if name in this_run:
                earlier = written[this_run[name]]
                if earlier.read_bytes() != data:
                    raise ValueError(f"{bundle}: member {name} occurs twice with different content")
                stamp, resource = earlier.name[:13], name[14:]
                target = out_dir / f"{earlier.name[: -len(resource) - 1]}-{stamp[9:]}-{resource}"
                written[this_run[name]] = earlier.rename(target)
                continue
            if path.exists():
                if path.read_bytes() != data:
                    raise ValueError(f"{path}: differs from bundle member {info.filename}")
                continue
            path.write_bytes(data)
            this_run[name] = len(written)
            written.append(path)
    print(f"{bundle.name}: {len(members)} members, {len(written)} files written to {out_dir}")
    return written


def merge_identical(folder: Path, resource: str = "rawSpeedVol-all.xml") -> list[Path]:
    """Keep one file per identical content, named with every fetch time; return the renamed files.

    `20250805-0007-<resource>` and a byte-identical `20250805-0010-<resource>` become
    `20250805-0007-0010-<resource>` (the earliest file is kept and renamed, the later
    ones are deleted). Raises if identical files were fetched on different dates.
    """
    groups: dict[str, list[Path]] = {}
    for path in sorted(folder.glob(f"*-{resource}")):
        groups.setdefault(hashlib.sha256(path.read_bytes()).hexdigest(), []).append(path)

    renamed: list[Path] = []
    for paths in groups.values():
        if len(paths) == 1:
            continue
        stamps = [p.name[: -len(resource) - 1] for p in paths]  # "YYYYMMDD-HHMM[-HHMM...]"
        dates = {s[:8] for s in stamps}
        if len(dates) > 1:
            raise ValueError(f"identical files fetched on different dates: {[p.name for p in paths]}")
        times = [t for s in stamps for t in s[9:].split("-")]
        target = folder / f"{stamps[0][:8]}-{'-'.join(times)}-{resource}"
        paths[0].rename(target)
        for p in paths[1:]:
            p.unlink()
        renamed.append(target)
    n_files = sum(len(p) for p in groups.values())
    print(f"{folder}: {n_files} files, {len(renamed)} merged names, {n_files - len(groups)} identical copies deleted")
    return renamed
