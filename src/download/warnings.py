"""HKO warning databases -> tidy CSV tables.

The warning-database web pages load plain tab-separated files. We parse them
directly instead of scraping the rendered HTML. All times are Hong Kong
local time (HKT, UTC+8) and are written as naive ISO timestamps.

rstorm.dat (rainstorm warnings), one signal per line:
    colour  start_y start_m start_d start_H start_M  end_y end_m end_d end_H end_M  dur_hh dur_mm
    colour is A (Amber), R (Red) or B (Black).

tc.dat (tropical cyclone signals), one signal per line:
    tc_code intensity name signal direction start_HHMM d m y flag end_HHMM d m y flag duration
    Rows whose intensity is "MSN" are not tropical-cyclone signals and are skipped.

In both files a line "UUUU" marks the start of provisional records.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path

import requests

from src.config import INTERIM_DIR, RAINSTORM_DB_URL, RAW_DIR, TC_SIGNAL_DB_URL

LEVELS = {"A": 1, "R": 2, "B": 3}
LEVEL_NAMES = {1: "Amber", 2: "Red", 3: "Black"}


@dataclass
class Signal:
    level: int  # 1 Amber, 2 Red, 3 Black
    start: datetime
    end: datetime
    provisional: bool


@dataclass
class Episode:
    episode_id: int
    start: datetime
    end: datetime
    max_level: int
    n_signals: int
    provisional: bool


@dataclass
class TCSignal:
    tc_code: str
    name: str
    intensity: str
    signal: str  # "1", "3", "8", "9", "10"
    direction: str  # NE/NW/SE/SW for No. 8, else X or *
    start: datetime
    end: datetime
    provisional: bool


def _fetch(url: str) -> str:
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()
    return resp.content.decode("utf-8-sig")


def _hhmm(value: str) -> tuple[int, int]:
    value = value.strip().zfill(4)
    return int(value[:2]), int(value[2:])


def _dt(year: int, month: int, day: int, hour: int, minute: int) -> datetime:
    """Build a datetime, accepting HKO's "24:00" for midnight at the end of a day."""
    return datetime(year, month, day) + timedelta(hours=hour, minutes=minute)


def parse_rainstorm(text: str) -> list[Signal]:
    signals: list[Signal] = []
    provisional = False
    for line in text.splitlines():
        fields = [f.strip() for f in line.split("\t")]
        if not fields[0]:
            continue
        if fields[0].startswith("UUUU"):
            provisional = True
            continue
        if fields[0] not in LEVELS or len(fields) < 11:
            continue
        sy, smo, sd, sh, smi, ey, emo, ed, eh, emi = map(int, fields[1:11])
        signals.append(Signal(
            level=LEVELS[fields[0]],
            start=_dt(sy, smo, sd, sh, smi),
            end=_dt(ey, emo, ed, eh, emi),
            provisional=provisional,
        ))
    signals.sort(key=lambda s: s.start)
    return signals


def group_episodes(signals: list[Signal], max_gap: timedelta = timedelta(0)) -> list[Episode]:
    """Merge signals that follow each other (e.g. Amber -> Red -> Black -> Amber) into episodes.

    Two signals belong to the same episode when the next one starts no later
    than `max_gap` after the previous one ends. HKO upgrades/downgrades
    are recorded with identical end/start times, so the default gap is 0.
    """
    episodes: list[Episode] = []
    for sig in signals:
        last = episodes[-1] if episodes else None
        if last is not None and sig.start <= last.end + max_gap:
            last.end = max(last.end, sig.end)
            last.max_level = max(last.max_level, sig.level)
            last.n_signals += 1
            last.provisional = last.provisional or sig.provisional
        else:
            episodes.append(Episode(len(episodes) + 1, sig.start, sig.end, sig.level, 1, sig.provisional))
    return episodes


def parse_tc(text: str) -> list[TCSignal]:
    signals: list[TCSignal] = []
    provisional = False
    for line in text.splitlines():
        fields = [f.strip() for f in line.split("\t")]
        if not fields[0]:
            continue
        if fields[0].startswith("UUUU"):
            provisional = True
            continue
        if len(fields) < 15 or fields[1] == "MSN":
            continue
        sh, smi = _hhmm(fields[5])
        eh, emi = _hhmm(fields[10])
        signals.append(TCSignal(
            tc_code=fields[0],
            name="" if fields[2] in ("", "NIL") else fields[2],
            intensity=fields[1],
            signal=fields[3],
            direction=fields[4],
            start=_dt(int(fields[8]), int(fields[7]), int(fields[6]), sh, smi),
            end=_dt(int(fields[13]), int(fields[12]), int(fields[11]), eh, emi),
            provisional=provisional,
        ))
    signals.sort(key=lambda s: s.start)
    return signals


def _write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        for row in rows:
            writer.writerow({k: v.isoformat(timespec="minutes") if isinstance(v, datetime) else v
                             for k, v in row.items()})


def read_episodes(path: Path | None = None) -> list[Episode]:
    path = path or INTERIM_DIR / "rainstorm_episodes.csv"
    with path.open() as f:
        return [Episode(
            episode_id=int(r["episode_id"]),
            start=datetime.fromisoformat(r["start"]),
            end=datetime.fromisoformat(r["end"]),
            max_level=int(r["max_level"]),
            n_signals=int(r["n_signals"]),
            provisional=r["provisional"] == "True",
        ) for r in csv.DictReader(f)]


def download_warnings() -> None:
    rain_text = _fetch(RAINSTORM_DB_URL)
    tc_text = _fetch(TC_SIGNAL_DB_URL)
    (RAW_DIR / "hko").mkdir(parents=True, exist_ok=True)
    (RAW_DIR / "hko" / "rstorm.dat").write_text(rain_text)
    (RAW_DIR / "hko" / "tc.dat").write_text(tc_text)

    signals = parse_rainstorm(rain_text)
    _write_csv(RAW_DIR / "hko" / "rainstorm_warnings.csv", [
        {"level": s.level, "level_name": LEVEL_NAMES[s.level], "start": s.start, "end": s.end,
         "duration_min": int((s.end - s.start).total_seconds() // 60), "provisional": s.provisional}
        for s in signals
    ])
    episodes = group_episodes(signals)
    _write_csv(INTERIM_DIR / "rainstorm_episodes.csv", [
        {**asdict(e), "max_level_name": LEVEL_NAMES[e.max_level],
         "duration_min": int((e.end - e.start).total_seconds() // 60)}
        for e in episodes
    ])
    tc = parse_tc(tc_text)
    _write_csv(RAW_DIR / "hko" / "tc_signals.csv", [asdict(s) for s in tc])

    print(f"rainstorm signals: {len(signals)} ({signals[0].start:%Y-%m-%d} .. {signals[-1].end:%Y-%m-%d}), "
          f"episodes: {len(episodes)}, TC signals: {len(tc)}")
