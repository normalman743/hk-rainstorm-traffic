"""Choose which days to download: rainstorm event days plus dry control days.

Downloading every day is ~1 GB/month for traffic alone, so we pick:
- event days: every calendar day touched by a rainstorm episode, padded by
  `pad_hours` on both sides (to capture pre-storm baseline and recovery);
- control days: the same weekday 1..n_controls weeks before each event day,
  if that day has no rainstorm warning and no tropical cyclone signal. These feed the
  "normal traffic" baseline (proposal step P10).

Only days on or after the start of the traffic archive (June 2021) are kept.
"""

from __future__ import annotations

import csv
from datetime import date, datetime, timedelta
from pathlib import Path

from src.config import INTERIM_DIR, RAW_DIR
from src.download.warnings import LEVEL_NAMES, read_episodes

ARCHIVE_START = date(2021, 6, 1)
MANIFEST = INTERIM_DIR / "day_manifest.csv"


def _days_between(start: datetime, end: datetime) -> list[date]:
    days, d = [], start.date()
    while d <= end.date():
        days.append(d)
        d += timedelta(days=1)
    return days


def _tc_days() -> set[date]:
    path = RAW_DIR / "hko" / "tc_signals.csv"
    if not path.exists():
        return set()
    with path.open() as f:
        return {d for r in csv.DictReader(f)
                for d in _days_between(datetime.fromisoformat(r["start"]), datetime.fromisoformat(r["end"]))}


def select_days(first_year: int, last_year: int, min_level: int = 1, pad_hours: int = 3,
                n_controls: int = 2, months: tuple[int, ...] = tuple(range(1, 13))) -> list[dict]:
    episodes = read_episodes()
    pad = timedelta(hours=pad_hours)

    # Any day with any rainstorm signal cannot serve as a control, even below min_level.
    warned_days = {d for e in episodes for d in _days_between(e.start, e.end)}
    excluded = warned_days | _tc_days()

    events: dict[date, dict] = {}
    for e in episodes:
        if e.max_level < min_level or not (first_year <= e.start.year <= last_year) or e.start.month not in months:
            continue
        for d in _days_between(e.start - pad, e.end + pad):
            row = events.setdefault(d, {"date": d, "role": "event", "episode_ids": [], "max_level": 0})
            row["episode_ids"].append(e.episode_id)
            row["max_level"] = max(row["max_level"], e.max_level)

    controls: dict[date, dict] = {}
    for d in events:
        for k in range(1, n_controls + 1):
            c = d - timedelta(weeks=k)
            if c not in events and c not in excluded:
                controls.setdefault(c, {"date": c, "role": "control", "episode_ids": [], "max_level": 0})

    rows = [r for r in sorted({**controls, **events}.values(), key=lambda r: r["date"])
            if r["date"] >= ARCHIVE_START]
    for r in rows:
        r["max_level_name"] = LEVEL_NAMES.get(r["max_level"], "")
        r["episode_ids"] = " ".join(map(str, r["episode_ids"]))
    return rows


def write_manifest(rows: list[dict], path: Path = MANIFEST) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["date", "role", "episode_ids", "max_level", "max_level_name"])
        writer.writeheader()
        writer.writerows(rows)


def read_manifest(path: Path = MANIFEST) -> list[date]:
    with path.open() as f:
        return [date.fromisoformat(r["date"]) for r in csv.DictReader(f)]
