"""S1 L1: every lane reading of the distinct S1 files, as written, one Parquet file per bundle.

    python -m src.clean.s1_parse [--source s1] [--workers 8]

`--source s9`: the smart-lamppost readings, same format (see src.clean.s1_periods).
Needs data/interim/manifest/<resource>.csv and data/interim/checks/<source>_files.csv
(python -m src.clean.manifest ..., python -m src.clean.s1_periods --source <source>).

Output: data/interim/l1/<source>/<bundle YYYYMM>.parquet, one row per <lane>:
    bundle, index                  the zip member the row comes from (see the manifest)
    date                           <date> of the file
    period_from, period_to         of the <period>
    detector_id, direction         of the <detector>
    lane_position                  0, 1, … : the <lane>'s place in its <lanes> (integer)
    lane_id, speed, occupancy, volume, sd, valid   of the <lane> (`sd` is <s.d.>)

Every value except lane_position is the element's text, unchanged, as a string; an element
that is absent is null, an empty element is "". Types are checked later, not here.
lane_position keeps the order of the file: TDS90026 writes two lanes as `Middle Lane`
(docs/cleaning.md D4), and only their order tells them apart.

Which files are read:
- one file per group of byte-identical files (the manifest keeps every fetch time);
- members that are not `*-<resource>` (the bundle's data-dictionary.pdf pointer)
  are skipped and listed;
- truncated files (complete = False in <source>_files.csv) are skipped only if every period they
  hold is also in a complete file; otherwise this raises.

Any element not in the structure below, or a child that occurs twice, raises:
    raw_speed_volume_list > date, periods > period > period_from, period_to, detectors
    > detector > detector_id, direction, lanes > lane > lane_id, speed, occupancy, volume, s.d., valid
"""

from __future__ import annotations

import argparse
import csv
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
from src.clean.s1_periods import OUT_DIR as CHECKS_DIR, SOURCES, bundles
from src.config import INTERIM_DIR

L1_DIR = INTERIM_DIR / "l1"  # output: L1_DIR / <source>

LANE_FIELDS = {"lane_id": "lane_id", "speed": "speed", "occupancy": "occupancy",
               "volume": "volume", "s.d.": "sd", "valid": "valid"}
COLUMNS = ["bundle", "index", "date", "period_from", "period_to", "detector_id", "direction",
           "lane_position", *LANE_FIELDS.values()]
INTEGERS = {"index": pa.int32(), "lane_position": pa.int16()}
SCHEMA = pa.schema([(c, INTEGERS.get(c, pa.string())) for c in COLUMNS])

_zips: dict[Path, zipfile.ZipFile] = {}


def _children(el, allowed: set[str], where: str) -> dict:
    """Map tag -> child element; raise on an unknown or repeated tag."""
    out = {}
    for c in el:
        if c.tag not in allowed:
            raise ValueError(f"{where}: unexpected <{c.tag}> in <{el.tag}>")
        if c.tag in out:
            raise ValueError(f"{where}: <{c.tag}> twice in <{el.tag}>")
        out[c.tag] = c
    return out


def _text(children: dict, tag: str) -> str | None:
    """Element text as written; None if the element is absent, "" if it is empty."""
    if tag not in children:
        return None
    return children[tag].text or ""


def parse(data: bytes, where: str) -> list[tuple]:
    """Rows of one S1 file (without bundle and index)."""
    root = etree.fromstring(data)
    if root.tag != "raw_speed_volume_list":
        raise ValueError(f"{where}: root <{root.tag}>")
    top = _children(root, {"date", "periods"}, where)
    date = _text(top, "date")
    rows = []
    for period in top["periods"] if "periods" in top else []:
        if period.tag != "period":
            raise ValueError(f"{where}: unexpected <{period.tag}> in <periods>")
        p = _children(period, {"period_from", "period_to", "detectors"}, where)
        for det in p["detectors"] if "detectors" in p else []:
            if det.tag != "detector":
                raise ValueError(f"{where}: unexpected <{det.tag}> in <detectors>")
            d = _children(det, {"detector_id", "direction", "lanes"}, where)
            for position, lane in enumerate(d["lanes"] if "lanes" in d else []):
                if lane.tag != "lane":
                    raise ValueError(f"{where}: unexpected <{lane.tag}> in <lanes>")
                ln = _children(lane, set(LANE_FIELDS), where)
                rows.append((date, _text(p, "period_from"), _text(p, "period_to"),
                             _text(d, "detector_id"), _text(d, "direction"), position,
                             *(_text(ln, t) for t in LANE_FIELDS)))
    return rows


def _parse_chunk(bundle: Path, indexes: list[int]) -> tuple[pa.Table, int]:
    if bundle not in _zips:
        _zips[bundle] = zipfile.ZipFile(bundle)
    z = _zips[bundle]
    infos = z.infolist()
    cols = defaultdict(list)
    nbytes = 0
    for i in indexes:
        data = z.read(infos[i])
        nbytes += len(data)
        for row in parse(data, f"{bundle.name}:{i} {infos[i].filename}"):
            cols["bundle"].append(bundle.name)
            cols["index"].append(i)
            for c, v in zip(COLUMNS[2:], row):
                cols[c].append(v)
    return pa.table({c: cols[c] for c in COLUMNS}, schema=SCHEMA), nbytes


def _select(source: str) -> tuple[dict[str, list[dict]], list[str]]:
    """Members to parse per bundle, and a list of what is skipped and why."""
    resource = SOURCES[source]
    with (MANIFEST_DIR / f"{resource}.csv").open() as f:
        firsts = [r for r in csv.DictReader(f) if r["group"] == f"{r['bundle']}:{r['index']}"]
    with (CHECKS_DIR / f"{source}_files.csv").open() as f:
        checks = {(r["bundle"], r["index"]): r for r in csv.DictReader(f)}

    complete_periods = set()
    for r in checks.values():
        if r["complete"] == "True" and r["date"]:
            complete_periods.update((r["date"], p) for p in r["periods"].split(";"))

    todo, skipped = defaultdict(list), []
    for r in firsts:
        if not r["member"].endswith(f"-{resource}"):
            skipped.append(f"{r['bundle']}:{r['index']} {r['member']}: not {resource}")
            continue
        c = checks[(r["bundle"], r["index"])]
        if c["complete"] != "True":
            held = {(c["date"], p) for p in c["periods"].split(";")} if c["periods"] else set()
            if not held or not held <= complete_periods:
                raise ValueError(f"truncated {r['bundle']}:{r['index']} {r['member']} holds periods "
                                 f"not in any complete file: {sorted(held - complete_periods)}")
            skipped.append(f"{r['bundle']}:{r['index']} {r['member']}: truncated, periods "
                           f"{c['periods']} are in complete files")
            continue
        todo[r["bundle"]].append(r)
    return todo, skipped


def build(source: str, workers: int) -> None:
    todo, skipped = _select(source)
    for s in skipped:
        print("skipped", s)
    out_dir = L1_DIR / source
    out_dir.mkdir(parents=True, exist_ok=True)
    total = sum(int(r["size"]) for rs in todo.values() for r in rs)
    with ProcessPoolExecutor(max_workers=workers) as pool, \
            tqdm(total=total, unit="B", unit_scale=True, desc="parsing") as bar:
        for bundle in sorted(todo):
            ix = [int(r["index"]) for r in todo[bundle]]
            out = out_dir / f"{bundle[:6]}.parquet"
            tmp = out.with_suffix(".parquet.part")
            n_rows = 0
            with pq.ParquetWriter(tmp, SCHEMA, compression="zstd") as w:
                futures = [pool.submit(_parse_chunk, bundles(source) / bundle, ix[s:s + 50])
                           for s in range(0, len(ix), 50)]
                for fut in as_completed(futures):
                    table, nbytes = fut.result()
                    w.write_table(table)
                    n_rows += table.num_rows
                    bar.update(nbytes)
            tmp.replace(out)
            tqdm.write(f"{out}: {len(ix):,} files, {n_rows:,} rows, {out.stat().st_size / 1e9:.2f} GB")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--source", choices=list(SOURCES), default="s1")
    p.add_argument("--workers", type=int, default=cpu_count())
    a = p.parse_args()
    build(a.source, a.workers)


if __name__ == "__main__":
    main()
