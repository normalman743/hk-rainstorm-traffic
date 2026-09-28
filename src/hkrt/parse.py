"""Parsers: raw source files -> tidy pandas tables. No cleaning happens here;
every value is kept as published so that cleaning choices can be compared later."""
from __future__ import annotations

import html
import io
import re
import xml.etree.ElementTree as ET

import pandas as pd

# ----------------------------------------------------------------- traffic ---

def parse_traffic_xml(body: bytes, snapshot: str) -> pd.DataFrame:
    """One ``rawSpeedVol-all.xml`` snapshot -> one row per (period, detector, lane).

    ``obs_time`` is the start of the 30-second measurement period. It lags the
    snapshot (file) time by roughly 5-10 minutes, so always align on ``obs_time``.
    """
    root = ET.fromstring(body)
    day = root.findtext("date")
    rows = []
    for p in root.iter("period"):
        t0 = p.findtext("period_from")
        for d in p.iter("detector"):
            det, direction = d.findtext("detector_id"), d.findtext("direction")
            for ln in d.iter("lane"):
                rows.append(
                    (snapshot, f"{day} {t0}", det, direction, ln.findtext("lane_id"),
                     ln.findtext("speed"), ln.findtext("occupancy"), ln.findtext("volume"),
                     ln.findtext("s.d."), ln.findtext("valid"))
                )
    df = pd.DataFrame(rows, columns=["snapshot", "obs_time", "detector_id", "direction", "lane",
                                     "speed", "occupancy", "volume", "speed_sd", "valid"])
    df["obs_time"] = pd.to_datetime(df["obs_time"])
    for c in ["speed", "occupancy", "volume", "speed_sd"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def fix_midnight_date(df: pd.DataFrame) -> pd.DataFrame:
    """Data quirk: just after midnight the XML <date> can still show the previous
    day while <period_from> is already 00:0x, so obs_time lands ~24 h too early.
    Detect by comparing with the snapshot time and shift those rows by one day.
    Adds a boolean ``date_fixed`` column."""
    snap = pd.to_datetime(df["snapshot"].astype(str), format="%Y%m%d-%H%M")
    bad = (snap - df["obs_time"]) > pd.Timedelta(hours=12)
    df = df.copy()
    df.loc[bad, "obs_time"] = df.loc[bad, "obs_time"] + pd.Timedelta(days=1)
    df["date_fixed"] = bad
    return df


# ----------------------------------------------------------------- weather ---

_RAIN_BLOCK = re.compile(r"rainfall recorded in various regions were:(.*?)\.\s", re.S)
_RAIN_ITEM = re.compile(r"\s*(.+?)\s+(\d+)(?:\s+to\s+(\d+))?\s*mm")
_HOUR = re.compile(r"At\s+(\d{1,2})\s*(a\.m\.|p\.m\.|noon|midnight)", re.I)


def _text(body: bytes) -> str:
    t = html.unescape(body.decode("utf-8", errors="ignore"))
    t = re.sub(r"<[^>]+>", " ", t)
    return re.sub(r"\s+", " ", t)


_UPDATED = re.compile(r"Bulletin updated at (\d{2}):(\d{2}) HKT (\d{2})/(\d{2})/(\d{4})")


def _report_time(t: str):
    """Observation hour of the report ("At 8 a.m. ..."), as a HKT timestamp.

    The rainfall figures cover the hour ending at this time.
    """
    u, h = _UPDATED.search(t), _HOUR.search(t)
    if not u:
        return pd.NaT
    day = pd.Timestamp(int(u.group(5)), int(u.group(4)), int(u.group(3)))
    if not h:
        return day + pd.Timedelta(hours=int(u.group(1)))
    hr, ap = int(h.group(1)), h.group(2).lower()
    if ap == "noon":
        hr = 12
    elif ap == "midnight":
        hr = 0
    elif ap == "p.m." and hr != 12:
        hr += 12
    elif ap == "a.m." and hr == 12:
        hr = 0
    ts = day + pd.Timedelta(hours=hr)
    # a report issued just after midnight may still describe the previous day's hour
    if ts > day + pd.Timedelta(hours=int(u.group(1)), minutes=int(u.group(2))) + pd.Timedelta(minutes=5):
        ts -= pd.Timedelta(days=1)
    return ts


def parse_current_weather(body: bytes, snapshot: str) -> pd.DataFrame:
    """HKO ``CurrentWeather.xml`` -> one row per district with past-hour rainfall range.

    Districts that are not listed had no measurable rain; they are NOT added
    here (the integration step decides how to treat them). If no district
    received rain, a single row with ``district = None`` records that the
    report exists and was dry.
    """
    t = _text(body)
    m = _RAIN_BLOCK.search(t)
    base = {"snapshot": snapshot, "report_time": _report_time(t)}
    if not m:
        return pd.DataFrame([{**base, "district": None, "rain_lo_mm": 0, "rain_hi_mm": 0}])
    rows = []
    for part in m.group(1).split(";"):
        mm = _RAIN_ITEM.match(part)
        if mm:
            lo = int(mm.group(2))
            rows.append({**base, "district": mm.group(1).strip(), "rain_lo_mm": lo,
                         "rain_hi_mm": int(mm.group(3) or lo)})
    return pd.DataFrame(rows)


# --------------------------------------------------------------- warnings ---

def parse_rainstorm_db(body: bytes) -> pd.DataFrame:
    """HKO rainstorm warning database (``rstorm.dat``) -> one row per signal period."""
    rows = []
    for line in body.decode("utf-8", errors="ignore").splitlines():
        f = line.split()
        if len(f) < 11 or f[0] not in {"A", "R", "B"}:
            continue
        y1, mo1, d1, h1, mi1, y2, mo2, d2, h2, mi2 = map(int, f[1:11])
        rows.append({
            "signal": {"A": "Amber", "R": "Red", "B": "Black"}[f[0]],
            "start": pd.Timestamp(y1, mo1, d1) + pd.Timedelta(hours=h1, minutes=mi1),
            "end": pd.Timestamp(y2, mo2, d2) + pd.Timedelta(hours=h2, minutes=mi2),
        })
    df = pd.DataFrame(rows)
    df["duration_min"] = (df["end"] - df["start"]).dt.total_seconds() / 60
    return df


# --------------------------------------------------------------- holidays ---

def parse_holidays_json(body: bytes) -> pd.DataFrame:
    import json
    j = json.loads(body.decode("utf-8-sig"))
    ev = j["vcalendar"][0]["vevent"]
    return pd.DataFrame({
        "date": pd.to_datetime([e["dtstart"][0] for e in ev]).date,
        "name": [e["summary"] for e in ev],
    })
