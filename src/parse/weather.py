"""HKO Current Weather Report (CurrentWeather.xml) -> district rainfall table.

Each hourly bulletin may contain a sentence like

    Between 6:45 and 7:45 a.m., [lightning ...]. The rainfall recorded in various
    regions were: Southern District 27 to 60 mm; Wan Chai 24 mm; ... .

giving the min-max past-hour rainfall over the gauges of each district. The
format is unchanged across 2021-2025 (checked on samples from every year).

Output: one row per bulletin x 18 districts:

    bulletin_time, period_start, period_end, district, rain_min_mm, rain_max_mm,
    listed, section_present

- `listed`: the district appeared in the sentence. Districts not listed in a
  bulletin that has the sentence recorded no rain (0 mm).
- `section_present`: the bulletin had a rainfall sentence at all. HKO drops the
  sentence when no rain was recorded anywhere; such bulletins give 0 mm for all
  districts and an inferred period (see `_infer_period_end`).
"""

from __future__ import annotations

import html
import re
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

DISTRICTS = [
    "Central & Western", "Eastern", "Islands", "Kowloon City", "Kwai Tsing", "Kwun Tong",
    "North", "Sai Kung", "Sha Tin", "Sham Shui Po", "Southern", "Tai Po", "Tsuen Wan",
    "Tuen Mun", "Wan Chai", "Wong Tai Sin", "Yau Tsim Mong", "Yuen Long",
]

_BULLETIN = re.compile(r"Bulletin updated at (\d{1,2}:\d{2}) HKT (\d{2}/\d{2}/\d{4})")
_PERIOD = re.compile(
    r"Between (\d{1,2}):(\d{2})(?: ([ap])\.m\.)? and (\d{1,2}):(\d{2}) ([ap])\.m\.")
_SECTION = re.compile(r"rainfall recorded in various regions were:(.*?)(?:\.\s|\.$|\]\]>)", re.S)
_ENTRY = re.compile(r"([A-Za-z&' ]+?)\s+(\d+(?:\.\d+)?)(?:\s+to\s+(\d+(?:\.\d+)?))?\s*mm")


def normalise_district(name: str) -> str:
    """Map HKO / TD spellings to one name: 'Southern District' -> 'Southern', 'and' -> '&'."""
    name = re.sub(r"\s+", " ", name).strip()
    name = re.sub(r" District$", "", name)
    return name.replace(" and ", " & ")


def _clock(hour: int, minute: int, ampm: str) -> tuple[int, int]:
    """12-hour clock to 24-hour. HKO writes 0:45 a.m. as well as 12:45 a.m."""
    hour %= 12
    return (hour + 12 if ampm == "p" else hour), minute


def _latest_at_or_before(ref: datetime, hour: int, minute: int) -> datetime:
    candidate = ref.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return candidate if candidate <= ref else candidate - timedelta(days=1)


def _infer_period_end(bulletin: datetime) -> datetime:
    """Last HH:45 at least 15 min before the bulletin (bulletins at 13:02 and 01:46 report 12:45 and 00:45)."""
    ref = bulletin - timedelta(minutes=15)
    end = ref.replace(minute=45, second=0, microsecond=0)
    return end if end <= ref else end - timedelta(hours=1)


def parse_bulletin(xml: bytes) -> list[dict]:
    text = re.sub(r"<[^>]+>", " ", html.unescape(xml.decode("utf-8", "replace")))
    text = re.sub(r"\s+", " ", text)

    m = _BULLETIN.search(text)
    if m is None:
        raise ValueError("no 'Bulletin updated at' timestamp")
    bulletin = datetime.strptime(f"{m.group(2)} {m.group(1)}", "%d/%m/%Y %H:%M")

    values: dict[str, tuple[float, float]] = {}
    section = _SECTION.search(text)
    period = _PERIOD.search(text)
    if section and period:
        h, mi = _clock(int(period.group(4)), int(period.group(5)), period.group(6))
        period_end = _latest_at_or_before(bulletin, h, mi)
        for entry in filter(None, (x.strip() for x in section.group(1).split(";"))):
            e = _ENTRY.fullmatch(entry)
            if e is None:
                raise ValueError(f"cannot parse rainfall entry {entry!r} in bulletin {bulletin}")
            district = normalise_district(e.group(1))
            if district not in DISTRICTS:
                raise ValueError(f"unknown district {e.group(1)!r} in bulletin {bulletin}")
            lo = float(e.group(2))
            values[district] = (lo, float(e.group(3)) if e.group(3) else lo)
    else:
        section = None
        period_end = _infer_period_end(bulletin)

    return [{
        "bulletin_time": bulletin,
        "period_start": period_end - timedelta(hours=1),
        "period_end": period_end,
        "district": d,
        "rain_min_mm": values.get(d, (0.0, 0.0))[0],
        "rain_max_mm": values.get(d, (0.0, 0.0))[1],
        "listed": d in values,
        "section_present": section is not None,
    } for d in DISTRICTS]


def parse_day_zip(path: Path) -> tuple[pd.DataFrame, dict]:
    rows: list[dict] = []
    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()
        for name in names:
            rows.extend(parse_bulletin(zf.read(name)))
    df = pd.DataFrame(rows)
    # The same bulletin can be archived more than once.
    df = df.drop_duplicates(["bulletin_time", "district"]).sort_values(["period_end", "district"], ignore_index=True)
    df["district"] = df["district"].astype("category")
    df[["rain_min_mm", "rain_max_mm"]] = df[["rain_min_mm", "rain_max_mm"]].astype("float32")
    stats = {
        "n_snapshots": len(names),
        "n_bulletins": int(df["bulletin_time"].nunique()),
        "n_with_rain_section": int(df.loc[df["section_present"], "bulletin_time"].nunique()),
        "max_rain_mm": float(df["rain_max_mm"].max()),
    }
    return df, stats
