"""Load processed tables for a set of days.

Each day file holds what was *archived* that day. Because files lag the
measurement time, readings from just before midnight sit in the next day's
file. So we read each requested day plus the following day, keep only rows
whose timestamp falls on a requested day, and deduplicate.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Iterable

import pandas as pd

from src.pipeline import table_path


def _load(source: str, days: Iterable[date], time_col: str, key: list[str], columns=None) -> pd.DataFrame:
    days = sorted(set(days))
    wanted = set(days)
    files = sorted({p for d in days for p in (table_path(source, d), table_path(source, d + timedelta(days=1)))
                    if p.exists()})
    if not files:
        return pd.DataFrame()
    df = pd.concat([pd.read_parquet(p, columns=columns) for p in files], ignore_index=True)
    df = df[df[time_col].dt.date.isin(wanted)]
    return df.drop_duplicates(key).sort_values(key, ignore_index=True)


def load_traffic_lane(days: Iterable[date], columns: list[str] | None = None) -> pd.DataFrame:
    """Lane-level readings (see docs/database_description.md, `traffic_lane`)."""
    return _load("traffic", days, "time", ["detector_id", "lane", "time"], columns)


def load_rainfall_district(days: Iterable[date]) -> pd.DataFrame:
    """Hourly district rainfall (see docs/database_description.md, `rainfall_district`)."""
    return _load("weather", days, "period_end", ["district", "period_end"])

