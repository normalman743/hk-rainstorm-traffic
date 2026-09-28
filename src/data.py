"""Load processed tables for a set of days.

Each day file holds what was *archived* that day. Because files lag the
measurement time, readings from just before midnight sit in the next day's
file. So we read each requested day plus the following day, keep only rows
whose timestamp falls on a requested day, and deduplicate.
"""

from __future__ import annotations

from datetime import date
from typing import Iterable

import pandas as pd
from pandas.api.types import union_categoricals

from src.pipeline import table_path


def _concat(frames: list[pd.DataFrame]) -> pd.DataFrame:
    """Concatenate while keeping categorical columns categorical (pandas falls back to
    object dtype when category sets differ, which is slow on millions of rows)."""
    frames = [f for f in frames if len(f)]
    if len(frames) <= 1:
        return frames[0] if frames else pd.DataFrame()
    for col in frames[0].columns:
        if isinstance(frames[0][col].dtype, pd.CategoricalDtype):
            cats = union_categoricals([f[col] for f in frames]).categories
            for f in frames:
                f[col] = f[col].cat.set_categories(cats)
    return pd.concat(frames, ignore_index=True)


def _load(source: str, days: Iterable[date], time_col: str, key: list[str], columns=None) -> pd.DataFrame:
    wanted = pd.DatetimeIndex(sorted({pd.Timestamp(d) for d in days}))
    paths = sorted({p for d in wanted for p in (table_path(source, d.date()), table_path(source, (d + pd.Timedelta(days=1)).date()))
                    if p.exists()})
    frames = []
    for p in paths:
        f = pd.read_parquet(p, columns=columns)
        frames.append(f[f[time_col].dt.normalize().isin(wanted)])
    df = _concat(frames)
    if df.empty:
        return df
    return df.drop_duplicates(key).sort_values(key, ignore_index=True)


def load_traffic_lane(days: Iterable[date], columns: list[str] | None = None) -> pd.DataFrame:
    """Lane-level readings (see docs/database_description.md, `traffic_lane`)."""
    return _load("traffic", days, "time", ["detector_id", "lane", "time"], columns)


def load_rainfall_district(days: Iterable[date]) -> pd.DataFrame:
    """Hourly district rainfall (see docs/database_description.md, `rainfall_district`)."""
    return _load("weather", days, "period_end", ["district", "period_end"])

