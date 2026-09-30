"""S7 L1: every row of the well-formed gridded rainfall nowcast files, as written, one Parquet file per bundle.

    python -m src.clean.s7_parse [--workers 8]

Needs data/interim/manifest/Gridded_rainfall_nowcast.csv.csv (python -m src.clean.manifest ...).

Output:
- data/interim/l1/s7/<bundle YYYYMM>.parquet, one row per CSV data row:
    bundle, index      the zip member the row comes from (see the manifest)
    updated, ending, latitude, longitude, rainfall
                       the 5 columns of HEADER, in order, text as written (strings)
- data/interim/checks/s7_files.csv, one row per distinct file: bundle, index, member, fetch_time,
  n_copies, parsed, problem, n_rows (rows written; empty when not parsed).

Which files are read:
- one file per group of byte-identical files; members that are not `*-Gridded_rainfall_nowcast.csv`
  (the bundle's data-dictionary.pdf pointer) are skipped and listed;
- a file is parsed only when it is well-formed: it ends with "\\n" and every line after the
  header has exactly 5 comma-separated fields (an empty line has 1). Files that are not are
  listed with `parsed = False` and the first problem (line number and text), and have no rows.
  Seen in 2024-05 / 2025-07 / 2025-08: files cut at a multiple of 32 KiB, files with a piece of
  another version after the last row, files with merged lines (docs/raw_data.md, S7).
- anything else unexpected raises: a header other than HEADER, a '"' or '\\r' in the file
  (quoting and CRLF are not handled), bytes that are not ASCII.
"""

from __future__ import annotations

import argparse
import csv
import io
import zipfile
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from os import cpu_count
from pathlib import Path

import pyarrow as pa
import pyarrow.csv as pacsv
import pyarrow.parquet as pq
from tqdm import tqdm

from src.clean.manifest import OUT_DIR as MANIFEST_DIR
from src.clean.s1_parse import L1_DIR
from src.clean.s1_periods import OUT_DIR as CHECKS_DIR
from src.config import RAW_DIR

RESOURCE = "Gridded_rainfall_nowcast.csv"
BUNDLES = RAW_DIR / "data.weather.gov.hk/weatherAPI/hko_data/F3" / RESOURCE / "bundle"
OUT_DIR = L1_DIR / "s7"
FILES = CHECKS_DIR / "s7_files.csv"
HEADER = (b"Updated Date and Time (in Hong Kong Time),Ending Date and Time (in Hong Kong Time),"
          b"Latitude (degree),Longitude (degree),Half-hourly Nowcast Accumulated Rainfall (mm)")
FIELDS = ["updated", "ending", "latitude", "longitude", "rainfall"]
COLUMNS = ["bundle", "index", *FIELDS]
SCHEMA = pa.schema([(c, pa.int32() if c == "index" else pa.string()) for c in COLUMNS])
FILE_COLUMNS = ["bundle", "index", "member", "fetch_time", "n_copies", "parsed", "problem", "n_rows"]

_zips: dict[Path, zipfile.ZipFile] = {}


def _check_format(data: bytes, where: str) -> bytes:
    """The data rows of the file (bytes after the header line); raise on what is not handled."""
    head, sep, body = data.partition(b"\n")
    if head != HEADER or not sep:
        raise ValueError(f"{where}: header {head[:200]!r}")
    for bad in (b'"', b"\r"):
        if bad in data:
            raise ValueError(f"{where}: {bad!r} at byte {data.index(bad)}")
    if not data.isascii():
        raise ValueError(f"{where}: bytes that are not ASCII")
    return body


def malformed(data: bytes, where: str) -> str | None:
    """Why the file is not well-formed (first problem found), or None."""
    body = _check_format(data, where)
    if not body.endswith(b"\n"):
        return f"no final newline (size {len(data)}), last line {body.rsplit(b'\n', 1)[-1][-80:]!r}"
    for k, line in enumerate(body[:-1].split(b"\n"), start=2):
        if line.count(b",") != 4:
            return f"line {k}: {line.count(b',') + 1} fields: {line[:120]!r}"
    return None


def parse(data: bytes, where: str) -> pa.Table:
    """The 5 columns of a well-formed S7 file, as strings."""
    body = _check_format(data, where)
    return pacsv.read_csv(
        io.BytesIO(body),
        read_options=pacsv.ReadOptions(column_names=FIELDS),
        parse_options=pacsv.ParseOptions(quote_char=False, double_quote=False, escape_char=False,
                                         newlines_in_values=False, ignore_empty_lines=False),
        convert_options=pacsv.ConvertOptions(column_types={c: pa.string() for c in FIELDS},
                                             strings_can_be_null=False, quoted_strings_can_be_null=False))


def _parse_chunk(bundle: Path, indexes: list[int]) -> tuple[pa.Table, list[tuple], int]:
    if bundle not in _zips:
        _zips[bundle] = zipfile.ZipFile(bundle)
    z = _zips[bundle]
    infos = z.infolist()
    tables, files, nbytes = [], [], 0
    for i in indexes:
        data = z.read(infos[i])
        nbytes += len(data)
        where = f"{bundle.name}:{i} {infos[i].filename}"
        problem = malformed(data, where)
        if problem:
            files.append((i, False, problem, None))
            continue
        t = parse(data, where)
        files.append((i, True, "", t.num_rows))
        tables.append(pa.table({"bundle": pa.array([bundle.name] * t.num_rows, pa.string()),
                                "index": pa.array([i] * t.num_rows, pa.int32()),
                                **{c: t[c] for c in FIELDS}}, schema=SCHEMA))
    table = pa.concat_tables(tables) if tables else SCHEMA.empty_table()
    return table, files, nbytes


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
    files, parts = [], []
    total = sum(int(r["size"]) for rs in todo.values() for r in rs)
    with ProcessPoolExecutor(max_workers=workers) as pool, \
            tqdm(total=total, unit="B", unit_scale=True, desc="parsing") as bar:
        for bundle in sorted(todo):
            ix = [int(r["index"]) for r in todo[bundle]]
            tmp = OUT_DIR / f"{bundle[:6]}.parquet.part"
            n_rows = 0
            with pq.ParquetWriter(tmp, SCHEMA, compression="zstd") as w:
                futures = [pool.submit(_parse_chunk, BUNDLES / bundle, ix[s:s + 20])
                           for s in range(0, len(ix), 20)]
                for fut in as_completed(futures):
                    table, chunk_files, nbytes = fut.result()
                    w.write_table(table)
                    files += [(bundle, *f) for f in chunk_files]
                    n_rows += table.num_rows
                    bar.update(nbytes)
            parts.append(tmp)
            n_bad = sum(1 for f in files if f[0] == bundle and not f[2])
            tqdm.write(f"{bundle}: {len(ix):,} files ({n_bad} not well-formed, not parsed), "
                       f"{n_rows:,} rows, {tmp.stat().st_size / 1e9:.2f} GB")

    FILES.parent.mkdir(parents=True, exist_ok=True)
    with FILES.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(FILE_COLUMNS)
        for bundle, i, parsed, problem, n in sorted(files):
            m = manifest[(bundle, i)]
            w.writerow([bundle, i, m["member"], m["fetch_time"], m["n_copies"], parsed, problem, n])
    for tmp in parts:
        tmp.replace(tmp.with_suffix(""))
    print(f"written: {OUT_DIR}/*.parquet, {FILES}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--workers", type=int, default=cpu_count())
    build(p.parse_args().workers)


if __name__ == "__main__":
    main()
