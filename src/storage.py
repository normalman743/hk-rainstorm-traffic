"""Parquet files that remember which code version produced them.

Every processed file carries a small JSON record in its Parquet schema metadata
(key `hkrt`), e.g. {"table": "traffic_lane", "version": 3, "date": "2025-08-05"}.
The pipeline compares it with the current code version and rebuilds outdated
files instead of silently skipping them.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

META_KEY = b"hkrt"


def write_parquet(df: pd.DataFrame, path: Path, meta: dict) -> None:
    """Write atomically (via a .part file) with `meta` stored in the schema metadata."""
    table = pa.Table.from_pandas(df, preserve_index=False)
    table = table.replace_schema_metadata({**(table.schema.metadata or {}),
                                           META_KEY: json.dumps(meta, default=str).encode()})
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".parquet.part")
    pq.write_table(table, tmp, compression="zstd")
    tmp.replace(path)


def read_meta(path: Path) -> dict | None:
    """The `hkrt` record of a file, or None if the file is missing or predates versioning."""
    if not path.exists():
        return None
    raw = (pq.read_schema(path).metadata or {}).get(META_KEY)
    return json.loads(raw) if raw else None


def file_version(path: Path) -> int | None:
    meta = read_meta(path)
    return None if meta is None else meta.get("version")
