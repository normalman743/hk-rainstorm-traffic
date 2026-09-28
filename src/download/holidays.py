"""Hong Kong general holidays from 1823 (https://data.gov.hk/en-data/dataset/hk-dpo-statistic-cal).

The live JSON only covers the current and next two years, so we merge every
archived version from the DATA.GOV.HK Historical Archive (2019 onwards) with
the live file. Later versions win when a date appears in several files.
"""

from __future__ import annotations

import csv
import json
from datetime import date, datetime, timedelta

from src.config import RAW_DIR
from src.download.archive import get_snapshot, list_versions, session

HOLIDAYS_URL = "https://www.1823.gov.hk/common/ical/en.json"
OUTPUT = RAW_DIR / "calendar" / "public_holidays.csv"


def parse_holidays(raw: bytes) -> dict[date, str]:
    doc = json.loads(raw.decode("utf-8-sig"))
    return {datetime.strptime(ev["dtstart"][0], "%Y%m%d").date(): ev["summary"].strip()
            for ev in doc["vcalendar"][0]["vevent"]}


def download_holidays() -> None:
    yesterday = date.today() - timedelta(days=1)
    versions = list_versions(HOLIDAYS_URL, date(2019, 1, 1), yesterday).get("timestamps") or []
    holidays: dict[date, str] = {}
    for ts in versions:
        holidays.update(parse_holidays(get_snapshot(HOLIDAYS_URL, ts)))
    live = session().get(HOLIDAYS_URL, timeout=60)
    live.raise_for_status()
    holidays.update(parse_holidays(live.content))

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["date", "name"])
        writer.writerows((d.isoformat(), name) for d, name in sorted(holidays.items()))
    days = sorted(holidays)
    print(f"[ok]   calendar/public_holidays.csv: {len(days)} holidays, {days[0]} .. {days[-1]} "
          f"({len(versions)} archived versions + live)")
