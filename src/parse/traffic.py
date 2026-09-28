"""TD raw detector XML (rawSpeedVol-all.xml) -> lane-level table.

One output row = one lane of one detector in one 30-second period:

    time, detector_id, lane, speed, occupancy, volume, sd, valid

The XML is regular and machine-generated, so a single regex pass over each file
is much faster than a DOM parser and gives identical results (checked against
ElementTree on a full day: 3,611,987 identical rows).

Schema history: `<s.d.>` only exists from ~18 Nov 2021 (data dictionary
20211118); earlier files leave `sd` missing.

Midnight quirk: the period starting at 00:00 is published with the previous
day's `<date>` (e.g. 2025-08-05 00:00:00 appears as 2025-08-04 00:00:00). When
the archive time of the file is known, a period more than 12 h older than it
is moved forward one day.
"""

from __future__ import annotations

import re
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

COLUMNS = ["time", "detector_id", "lane", "speed", "occupancy", "volume", "sd", "valid"]
KEY = ["time", "detector_id", "lane"]

# One alternation, scanned once per file. Groups:
# 1 date | 2 period_from | 3 detector_id | 4-9 lane fields (sd optional)
_TOKEN = re.compile(
    r"<date>\s*([\d-]+)\s*</date>"
    r"|<period_from>\s*([\d:]+)\s*</period_from>"
    r"|<detector_id>\s*(\w+)\s*</detector_id>"
    r"|<lane_id>\s*([^<]*?)\s*</lane_id>"
    r"\s*<speed>\s*([^<]*?)\s*</speed>"
    r"\s*<occupancy>\s*([^<]*?)\s*</occupancy>"
    r"\s*<volume>\s*([^<]*?)\s*</volume>"
    r"(?:\s*<s\.d\.>\s*([^<]*?)\s*</s\.d\.>)?"
    r"\s*<valid>\s*([^<]*?)\s*</valid>"
)


def _scan(items: Iterable[tuple[datetime | None, bytes]]) -> tuple[dict[str, list], int]:
    """items: (archive time of the file or None, XML). Returns columns and the number of periods re-dated."""
    cols: dict[str, list] = {c: [] for c in COLUMNS}
    times, dets, lanes, speeds, occs, vols, sds, valids = cols.values()
    n_fixed = 0
    for archived_at, xml in items:
        day = stamp = det = None
        for m in _TOKEN.finditer(xml.decode("utf-8", "replace")):
            if m.group(4) is not None:
                if stamp is None or det is None:
                    raise ValueError("lane before period/detector")
                times.append(stamp)
                dets.append(det)
                lanes.append(m.group(4))
                speeds.append(m.group(5))
                occs.append(m.group(6))
                vols.append(m.group(7))
                sds.append(m.group(8))
                valids.append(m.group(9))
            elif m.group(3) is not None:
                det = m.group(3)
            elif m.group(2) is not None:
                if day is None:
                    raise ValueError("period before <date>")
                stamp = f"{day} {m.group(2)}"
                if archived_at is not None:
                    measured = datetime.strptime(stamp, "%Y-%m-%d %H:%M:%S")
                    if archived_at - measured > timedelta(hours=12):
                        stamp = f"{measured + timedelta(days=1):%Y-%m-%d %H:%M:%S}"
                        n_fixed += 1
            else:
                day = m.group(1)
    return cols, n_fixed


def _numeric(values: list, dtype: str) -> pd.array:
    """Convert strings to numbers via their distinct values (few per column), which is much faster."""
    cat = pd.Categorical(values)
    nums = pd.to_numeric(pd.Series(cat.categories, dtype=object), errors="coerce").to_numpy(dtype="float64")
    # Missing values have code -1, which indexes the NaN appended at the end.
    out = np.append(nums, np.nan)[cat.codes]
    return pd.array(out, dtype=dtype) if dtype != "float32" else out.astype("float32")


def to_frame(cols: dict[str, list]) -> pd.DataFrame:
    stamps = pd.Categorical(cols["time"])
    times = pd.to_datetime(pd.Series(stamps.categories, dtype=object), format="%Y-%m-%d %H:%M:%S").to_numpy()
    return pd.DataFrame({
        "time": times[stamps.codes] if len(stamps) else np.array([], dtype="datetime64[ns]"),
        "detector_id": pd.Categorical(cols["detector_id"]),
        "lane": pd.Categorical(cols["lane"]),
        "speed": _numeric(cols["speed"], "Int16"),
        "occupancy": _numeric(cols["occupancy"], "Int16"),
        "volume": _numeric(cols["volume"], "Int16"),
        "sd": _numeric(cols["sd"], "float32"),
        "valid": pd.Categorical(cols["valid"]),
    })


def parse_snapshots(xmls: Iterable[bytes], archived_at: Iterable[datetime | None] | None = None) -> pd.DataFrame:
    """Parse XML files; pass their archive times to correct the midnight date quirk."""
    xmls = list(xmls)
    times = list(archived_at) if archived_at is not None else [None] * len(xmls)
    return to_frame(_scan(zip(times, xmls))[0])


def archive_time(member_name: str) -> datetime:
    """'20250805-0801-rawSpeedVol-all.xml' -> 2025-08-05 08:01."""
    return datetime.strptime(Path(member_name).name[:13], "%Y%m%d-%H%M")


def parse_day_zip(path: Path) -> tuple[pd.DataFrame, dict]:
    """Parse all snapshots in one day ZIP and drop duplicate readings (adjacent files overlap).

    Returns the lane table and a coverage summary.
    """
    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()
        cols, n_fixed = _scan((archive_time(name), zf.read(name)) for name in names)
    df = to_frame(cols)
    n_raw = len(df)
    df = df.drop_duplicates(KEY).sort_values(["detector_id", "lane", "time"], ignore_index=True)
    stats = {
        "n_snapshots": len(names),
        "n_rows_raw": n_raw,
        "n_rows": len(df),
        "n_periods": int(df["time"].nunique()),
        "n_detectors": int(df["detector_id"].nunique()),
        "has_sd": bool(df["sd"].notna().any()),
        "n_periods_redated": n_fixed,
    }
    return df, stats
