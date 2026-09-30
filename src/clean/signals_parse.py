"""S4, S5 L1: every line of the HKO warning-signal databases, as written, one Parquet file each.

    python -m src.clean.signals_parse

Files (saved by `python -m src.download warnings`, which decodes the download as UTF-8, dropping
a byte-order mark, and writes the text back; nothing else is changed):
- S4 data/raw/hko/rstorm.dat -> data/interim/l1/s4/rstorm.parquet
- S5 data/raw/hko/tc.dat     -> data/interim/l1/s5/tc.parquet

Both are tab-separated without a header, one signal per line; a line `UUUU` marks where
provisional records begin (docs/raw_data.md, S4 and S5). One row per line:
    line           1-based line number
    <fields>       S4: 13, S5: 16, named after the columns in docs/raw_data.md; strings as
                   written, nothing trimmed
    trailing_tabs  number of empty fields after the last one (some lines end with one or two tabs)
The `UUUU` line has its text in the first field and null in the others.

Raises on: bytes that are not UTF-8, a "\\r", no final newline, an empty line, and a line that
is neither `UUUU` nor the field count followed only by empty fields.
"""

from __future__ import annotations

import pyarrow as pa
import pyarrow.parquet as pq

from src.clean.s1_parse import L1_DIR
from src.config import RAW_DIR

MARKER = "UUUU"
SOURCES = {
    "s4": {"file": RAW_DIR / "hko" / "rstorm.dat",
           "fields": ["colour", "start_year", "start_month", "start_day", "start_hour", "start_minute",
                      "end_year", "end_month", "end_day", "end_hour", "end_minute",
                      "duration_hours", "duration_minutes"]},
    "s5": {"file": RAW_DIR / "hko" / "tc.dat",
           "fields": ["cyclone", "intensity", "name", "signal", "direction",
                      "start_time", "start_day", "start_month", "start_year", "start_flag",
                      "end_time", "end_day", "end_month", "end_year", "end_flag", "duration"]},
}


def parse(data: bytes, n_fields: int, where: str) -> list[tuple]:
    """(line, *fields, trailing_tabs) of every line."""
    text = data.decode("utf-8")
    if "\r" in text:
        raise ValueError(f"{where}: contains \\r")
    if not text.endswith("\n"):
        raise ValueError(f"{where}: no final newline")
    rows = []
    for n, line in enumerate(text[:-1].split("\n"), 1):
        if line == MARKER:
            rows.append((n, line, *[None] * (n_fields - 1), 0))
            continue
        fields = line.split("\t")
        if len(fields) < n_fields or any(fields[n_fields:]):
            raise ValueError(f"{where}: line {n} has {len(fields)} fields, "
                             f"not {n_fields} plus empty ones: {line!r}")
        rows.append((n, *fields[:n_fields], len(fields) - n_fields))
    return rows


def build() -> None:
    for source, s in SOURCES.items():
        columns = ["line", *s["fields"], "trailing_tabs"]
        schema = pa.schema([(c, pa.int32() if c in ("line", "trailing_tabs") else pa.string())
                            for c in columns])
        rows = parse(s["file"].read_bytes(), len(s["fields"]), str(s["file"]))
        out = L1_DIR / source / f"{s['file'].stem}.parquet"
        out.parent.mkdir(parents=True, exist_ok=True)
        table = pa.table({c: [r[k] for r in rows] for k, c in enumerate(columns)}, schema=schema)
        pq.write_table(table, out.with_suffix(".parquet.part"), compression="zstd")
        out.with_suffix(".parquet.part").replace(out)
        print(f"{source}: {s['file'].name} -> {out}: {len(rows)} lines "
              f"({sum(r[1] == MARKER for r in rows)} `{MARKER}`, "
              f"{sum(r[-1] > 0 for r in rows)} with trailing tabs)")


if __name__ == "__main__":
    build()
