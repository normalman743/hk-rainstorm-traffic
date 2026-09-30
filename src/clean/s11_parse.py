"""S11 L1: every segment speed of the distinct S11 files, as written, one Parquet file per bundle.

    python -m src.clean.s11_parse [--workers 8]

Needs data/interim/manifest/irnAvgSpeed-all.xml.csv (python -m src.clean.manifest ...).

Output:
- data/interim/l1/s11/<bundle YYYYMM>.parquet, one row per <segment>:
    bundle, index                  the zip member the row comes from (see the manifest)
    date, time, irn_version        of the file
    segment_id, speed, valid       of the <segment>
  Every value is the element's text, unchanged, as a string; an element that is absent is
  null, an empty element is "". Types are checked later, not here.
- data/interim/checks/s11_files.csv, one row per distinct file: bundle, index, member,
  fetch_time, n_copies, complete (ends with </segment_speed_list>), date, time, irn_version,
  n_segments (rows written; empty for a skipped file).

Which files are read:
- one file per group of byte-identical files (the manifest keeps every fetch time);
- members that are not `*-irnAvgSpeed-all.xml` (the bundle's data-dictionary.pdf pointer)
  are skipped and listed;
- a truncated file (not complete) is skipped only if a complete file has the same date and
  time; otherwise this raises and no output is renamed into place. A truncated file cannot be
  parsed, so its date and time are read with a regular expression (each must occur once).

Any element not in the structure below, or a child that occurs twice, raises:
    segment_speed_list > date, time, irn_version, segments > segment > segment_id, speed, valid
"""

from __future__ import annotations

import argparse
import csv
import re
import zipfile
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from os import cpu_count
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
from lxml import etree
from tqdm import tqdm

from src.clean.manifest import OUT_DIR as MANIFEST_DIR
from src.clean.s1_parse import L1_DIR, _children, _text
from src.clean.s1_periods import OUT_DIR as CHECKS_DIR, TD_DIR

RESOURCE = "irnAvgSpeed-all.xml"
BUNDLES = TD_DIR / RESOURCE / "bundle"
OUT_DIR = L1_DIR / "s11"
FILES = CHECKS_DIR / "s11_files.csv"
END = b"</segment_speed_list>"
HEAD = ["date", "time", "irn_version"]
SEGMENT = ["segment_id", "speed", "valid"]
COLUMNS = ["bundle", "index", *HEAD, *SEGMENT]
SCHEMA = pa.schema([(c, pa.int32() if c == "index" else pa.string()) for c in COLUMNS])
FILE_COLUMNS = ["bundle", "index", "member", "fetch_time", "n_copies", "complete", *HEAD, "n_segments"]

_zips: dict[Path, zipfile.ZipFile] = {}


def parse(data: bytes, where: str) -> tuple[tuple, list[tuple]]:
    """(date, time, irn_version) of one S11 file, and (segment_id, speed, valid) of every segment."""
    root = etree.fromstring(data)
    if root.tag != "segment_speed_list":
        raise ValueError(f"{where}: root <{root.tag}>")
    top = _children(root, {*HEAD, "segments"}, where)
    rows = []
    for seg in top["segments"] if "segments" in top else []:
        if seg.tag != "segment":
            raise ValueError(f"{where}: unexpected <{seg.tag}> in <segments>")
        s = _children(seg, set(SEGMENT), where)
        rows.append(tuple(_text(s, t) for t in SEGMENT))
    return tuple(_text(top, t) for t in HEAD), rows


def _head_of_truncated(data: bytes, where: str) -> tuple:
    out = []
    for t in HEAD:
        found = re.findall(rb"<%s>(.*?)</%s>" % (t.encode(), t.encode()), data)
        if len(found) != 1:
            raise ValueError(f"{where}: truncated file with {len(found)} <{t}>")
        out.append(found[0].decode())
    return tuple(out)


def _parse_chunk(bundle: Path, indexes: list[int]) -> tuple[pa.Table, list[tuple], int]:
    if bundle not in _zips:
        _zips[bundle] = zipfile.ZipFile(bundle)
    z = _zips[bundle]
    infos = z.infolist()
    cols = defaultdict(list)
    files = []
    nbytes = 0
    for i in indexes:
        data = z.read(infos[i])
        nbytes += len(data)
        where = f"{bundle.name}:{i} {infos[i].filename}"
        if not data.rstrip().endswith(END):
            files.append((i, False, *_head_of_truncated(data, where), None))
            continue
        head, rows = parse(data, where)
        files.append((i, True, *head, len(rows)))
        for row in rows:
            cols["bundle"].append(bundle.name)
            cols["index"].append(i)
            for c, v in zip(COLUMNS[2:], (*head, *row)):
                cols[c].append(v)
    return pa.table({c: cols[c] for c in COLUMNS}, schema=SCHEMA), files, nbytes


def build(workers: int) -> None:
    with (MANIFEST_DIR / f"{RESOURCE}.csv").open() as f:
        firsts = [r for r in csv.DictReader(f) if r["group"] == f"{r['bundle']}:{r['index']}"]
    todo = defaultdict(list)
    for r in firsts:
        if r["member"].endswith(f"-{RESOURCE}"):
            todo[r["bundle"]].append(r)
        else:
            print(f"skipped {r['bundle']}:{r['index']} {r['member']}: not {RESOURCE}")
    manifest = {(r["bundle"], int(r["index"])): r for r in firsts}

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    files = []
    parts = []
    total = sum(int(r["size"]) for rs in todo.values() for r in rs)
    with ProcessPoolExecutor(max_workers=workers) as pool, \
            tqdm(total=total, unit="B", unit_scale=True, desc="parsing") as bar:
        for bundle in sorted(todo):
            ix = [int(r["index"]) for r in todo[bundle]]
            tmp = OUT_DIR / f"{bundle[:6]}.parquet.part"
            n_rows = 0
            with pq.ParquetWriter(tmp, SCHEMA, compression="zstd") as w:
                futures = [pool.submit(_parse_chunk, BUNDLES / bundle, ix[s:s + 50])
                           for s in range(0, len(ix), 50)]
                for fut in as_completed(futures):
                    table, chunk_files, nbytes = fut.result()
                    w.write_table(table)
                    files += [(bundle, *f) for f in chunk_files]
                    n_rows += table.num_rows
                    bar.update(nbytes)
            parts.append(tmp)
            tqdm.write(f"{bundle}: {len(ix):,} files, {n_rows:,} rows, {tmp.stat().st_size / 1e9:.2f} GB")

    complete_times = {(f[3], f[4]) for f in files if f[2]}
    truncated = [f for f in files if not f[2]]
    uncovered = [f for f in truncated if (f[3], f[4]) not in complete_times]
    if uncovered:
        raise ValueError(f"truncated files whose date and time are in no complete file "
                         f"(outputs left as .part): {uncovered}")
    for f in truncated:
        print(f"skipped {f[0]}:{f[1]} {manifest[(f[0], f[1])]['member']}: truncated, "
              f"{f[3]} {f[4]} is in a complete file")

    FILES.parent.mkdir(parents=True, exist_ok=True)
    with FILES.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(FILE_COLUMNS)
        for bundle, i, complete, date, time, irn, n in sorted(files):
            m = manifest[(bundle, i)]
            w.writerow([bundle, i, m["member"], m["fetch_time"], m["n_copies"], complete, date, time, irn, n])
    for tmp in parts:
        tmp.replace(tmp.with_suffix(""))
    print(f"written: {OUT_DIR}/*.parquet, {FILES}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--workers", type=int, default=cpu_count())
    build(p.parse_args().workers)


if __name__ == "__main__":
    main()
