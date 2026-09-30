"""S8 L1: every day of the HKO daily total rainfall file, as written.

    python -m src.clean.s8_parse

File: data/raw/hko/daily_HKO_RF_ALL.csv, saved by `python -m src.download static` (bytes as
downloaded; the Historical Archive has no copy of this URL, see docs/raw_data.md, S8).
Output: data/interim/l1/s8/daily_HKO_RF_ALL.parquet, one row per data line:
    line        1-based line number in the file
    HEADER      the 5 columns, with the header's names as written; strings as written
Only the data lines become rows. The other lines are fixed text, checked instead of kept, so any
change raises: the 2 TITLE lines and HEADER before the data, one empty line and LEGEND after it.

Raises on: bytes that are not UTF-8 (a leading byte-order mark is allowed), a "\\r" or '"', no
final newline, other lines around the data, and a data line without exactly 5 comma-separated
fields.
"""

from __future__ import annotations

import pyarrow as pa
import pyarrow.parquet as pq

from src.clean.s1_parse import L1_DIR
from src.config import RAW_DIR

FILE = RAW_DIR / "hko" / "daily_HKO_RF_ALL.csv"
OUT = L1_DIR / "s8" / "daily_HKO_RF_ALL.parquet"
TITLE = ["日總雨量(毫米) - 天文台", "Daily Total Rainfall (mm) at the Hong Kong Observatory"]
HEADER = ["年/Year", "月/Month", "日/Day", "數值/Value", "數據完整性/data Completeness"]
LEGEND = ["*** 沒有數據/unavailable", "# 數據不完整/data incomplete",
          "微量表示少於 0.05 毫米/Trace means rainfall less than 0.05 mm", "C 數據完整/data Complete"]


def parse(data: bytes, where: str) -> list[tuple]:
    """(line, *HEADER fields) of every data line."""
    text = data.decode("utf-8-sig")
    for bad in ("\r", '"'):
        if bad in text:
            raise ValueError(f"{where}: contains {bad!r}")
    if not text.endswith("\n"):
        raise ValueError(f"{where}: no final newline")
    lines = text[:-1].split("\n")
    head, tail = [*TITLE, ",".join(HEADER)], ["", *LEGEND]
    if lines[:len(head)] != head:
        raise ValueError(f"{where}: first lines {lines[:len(head)]!r}, expected {head!r}")
    if lines[-len(tail):] != tail:
        raise ValueError(f"{where}: last lines {lines[-len(tail):]!r}, expected {tail!r}")
    rows = []
    for n, line in enumerate(lines[len(head):len(lines) - len(tail)], len(head) + 1):
        fields = line.split(",")
        if len(fields) != len(HEADER):
            raise ValueError(f"{where}: line {n} has {len(fields)} fields: {line!r}")
        rows.append((n, *fields))
    return rows


def build() -> None:
    rows = parse(FILE.read_bytes(), str(FILE))
    columns = ["line", *HEADER]
    schema = pa.schema([(c, pa.int32() if c == "line" else pa.string()) for c in columns])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    table = pa.table({c: [r[k] for r in rows] for k, c in enumerate(columns)}, schema=schema)
    pq.write_table(table, OUT.with_suffix(".parquet.part"), compression="zstd")
    OUT.with_suffix(".parquet.part").replace(OUT)
    print(f"s8: {FILE.name} -> {OUT}: {len(rows)} days, {'-'.join(rows[0][1:4])} .. {'-'.join(rows[-1][1:4])}")


if __name__ == "__main__":
    build()
