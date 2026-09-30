"""S2, S10, S14 L1: every row of every version file, as written, one Parquet file per version.

    python -m src.clean.versions_parse

A version file is either the one CSV member of an archive bundle (data/raw/static.data.gov.hk/
.../bundle/<YYYYMMDD>.zip) or a CSV saved by src.download (data/raw/td/<name>/<YYYYMMDD>.csv).
The version is that YYYYMMDD. The S2 live copy (data/raw/td/traffic_speed_volume_occ_info.csv)
has no version date: it must be byte-identical to one version file, otherwise this raises.

Output:
- data/interim/l1/<source>/<version>.parquet, one row per CSV data row:
    file   the file (and zip member) the row comes from, relative to data/raw
    row    1-based number of the data row (the header is not counted)
    then the columns of the file's own header, in order, with the header's names as written
  Every value is a string as written (CSV quoting removed, nothing trimmed). The headers differ
  between versions (S14: `Road Name,Segment ID`, `route,irn_id`, `irn_id,ucase(route)`), so the
  versions are not stacked here.
- data/interim/checks/versions_files.csv, one row per file: source, version, file, bytes, md5,
  encoding, delimiter, line_end, final_newline, n_rows, header (";"-joined), note.

Reading: the encoding is taken from the byte-order mark (UTF-8 BOM, UTF-16 LE BOM), else UTF-8;
the delimiter is a tab if the header line has one, else a comma. Raises on bytes that do not
decode, a row with another number of fields than the header, a repeated header name, a bundle
without exactly one CSV member, and a version found twice.
"""

from __future__ import annotations

import codecs
import csv
import hashlib
import io
import zipfile
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from src.clean.s1_parse import L1_DIR
from src.clean.s1_periods import OUT_DIR as CHECKS_DIR
from src.config import RAW_DIR

INFO = RAW_DIR / "static.data.gov.hk/td"
SOURCES = {
    "s2": {"bundles": INFO / "traffic-data-strategic-major-roads/info/traffic_speed_volume_occ_info.csv/bundle",
           "local": RAW_DIR / "td/traffic_speed_volume_occ_info",
           "live": RAW_DIR / "td/traffic_speed_volume_occ_info.csv"},
    "s10": {"bundles": INFO / "traffic-data-slp/info/traffic_speed_volume_occ_info-slp.csv/bundle"},
    "s14": {"bundles": INFO / "traffic-data-strategic-major-roads/info/speed_segments_info.csv/bundle",
            "local": RAW_DIR / "td/speed_segments_info"},
}
FILES = CHECKS_DIR / "versions_files.csv"
FILE_COLUMNS = ["source", "version", "file", "bytes", "md5", "encoding", "delimiter", "line_end",
                "final_newline", "n_rows", "header", "note"]


def decode(data: bytes) -> tuple[str, str]:
    """Text and the encoding it was read with."""
    if data.startswith(codecs.BOM_UTF8):
        return data[len(codecs.BOM_UTF8):].decode("utf-8"), "UTF-8 BOM"
    if data.startswith(codecs.BOM_UTF16_LE):
        return data[len(codecs.BOM_UTF16_LE):].decode("utf-16-le"), "UTF-16 LE BOM"
    return data.decode("utf-8"), "UTF-8"


def parse(text: str, where: str) -> tuple[list[str], list[list[str]], str]:
    """Header, data rows and delimiter of one CSV text."""
    delimiter = "\t" if "\t" in text.split("\n", 1)[0] else ","
    rows = list(csv.reader(io.StringIO(text, newline=""), delimiter=delimiter, strict=True))
    header, body = rows[0], rows[1:]
    if len(set(header)) != len(header):
        raise ValueError(f"{where}: repeated name in header {header}")
    for k, r in enumerate(body, start=1):
        if len(r) != len(header):
            raise ValueError(f"{where}: data row {k} has {len(r)} fields, header {len(header)}: {r}")
    return header, body, delimiter


def _version_files(source: str) -> list[tuple[str, str, bytes]]:
    """(version, file relative to data/raw, bytes) of every version file of a source."""
    out = []
    for bundle in sorted(SOURCES[source]["bundles"].glob("*.zip")):
        z = zipfile.ZipFile(bundle)
        csvs = [i for i in z.infolist() if i.filename.endswith(".csv")]
        if len(csvs) != 1:
            raise ValueError(f"{bundle}: {len(csvs)} CSV members")
        out.append((bundle.stem, f"{bundle.relative_to(RAW_DIR)}:{csvs[0].filename}", z.read(csvs[0])))
    if "local" in SOURCES[source]:
        for p in sorted(SOURCES[source]["local"].glob("*.csv")):
            out.append((p.stem, str(p.relative_to(RAW_DIR)), p.read_bytes()))
    versions = [v for v, _, _ in out]
    if len(set(versions)) != len(versions):
        raise ValueError(f"{source}: a version found twice: {sorted(versions)}")
    return sorted(out)


def build() -> None:
    records = []
    for source in SOURCES:
        out_dir = L1_DIR / source
        out_dir.mkdir(parents=True, exist_ok=True)
        files = _version_files(source)
        for version, name, data in files:
            text, encoding = decode(data)
            header, body, delimiter = parse(text, name)
            schema = pa.schema([("file", pa.string()), ("row", pa.int32()), *((c, pa.string()) for c in header)])
            table = pa.table({"file": [name] * len(body), "row": list(range(1, len(body) + 1)),
                              **{c: [r[k] for r in body] for k, c in enumerate(header)}}, schema=schema)
            out = out_dir / f"{version}.parquet"
            pq.write_table(table, out.with_suffix(".parquet.part"), compression="zstd")
            out.with_suffix(".parquet.part").replace(out)
            crlf = text.count("\r\n")
            line_end = "CRLF" if crlf and crlf == text.count("\n") else "LF" if not crlf else "mixed"
            records.append((source, version, name, len(data), hashlib.md5(data).hexdigest(), encoding,
                            "tab" if delimiter == "\t" else "comma", line_end, text.endswith("\n"),
                            len(body), ";".join(header), ""))
            print(f"{source} {version}: {len(body)} rows, {encoding}, {records[-1][6]}, {line_end} -> {out}")
        live = SOURCES[source].get("live")
        if live:
            data = live.read_bytes()
            same = [v for v, _, d in files if d == data]
            if not same:
                raise ValueError(f"{live} is identical to no version file; its version date is not known")
            records.append((source, "", str(live.relative_to(RAW_DIR)), len(data), hashlib.md5(data).hexdigest(),
                            "", "", "", "", "", "", f"identical to version {same[0]}; not written again"))
            print(f"{source} live copy: identical to {same[0]}")
    FILES.parent.mkdir(parents=True, exist_ok=True)
    with FILES.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(FILE_COLUMNS)
        w.writerows(records)
    print(f"written: {FILES}")


if __name__ == "__main__":
    build()
