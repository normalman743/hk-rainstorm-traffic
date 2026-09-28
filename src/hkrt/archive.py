"""Client for the DATA.GOV.HK Historical Archive API.

Every DATA.GOV.HK resource (e.g. the traffic detector XML or the HKO
Current Weather RSS) is snapshotted each time it changes. This module lists
those snapshots and downloads individual versions.
"""
from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path

API = "https://api.data.gov.hk/v1/historical-archive/"

TRAFFIC_RAW_URL = "https://resource.data.one.gov.hk/td/traffic-detectors/rawSpeedVol-all.xml"
CURRENT_WEATHER_URL = "https://rss.weather.gov.hk/rss/CurrentWeather.xml"

_UA = {"User-Agent": "hk-rainstorm-traffic/0.1 (course project)"}


def _get(url: str, timeout: int = 120) -> bytes:
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def list_versions(resource_url: str, start: date, end: date) -> list[str]:
    """Return snapshot timestamps (``YYYYMMDD-HHMM``) between two dates, inclusive."""
    q = urllib.parse.urlencode(
        {"url": resource_url, "start": start.strftime("%Y%m%d"), "end": end.strftime("%Y%m%d")}
    )
    return json.loads(_get(API + "list-file-versions?" + q)).get("timestamps", [])


def fetch_version(resource_url: str, ts: str, retries: int = 4) -> bytes | None:
    """Download one snapshot. Returns None if the archive has no file (HTTP 404)."""
    q = urllib.parse.urlencode({"url": resource_url, "time": ts})
    err: Exception | None = None
    for k in range(retries):
        try:
            body = _get(API + "get-file?" + q)
            # The API usually answers with a redirect target in JSON.
            if body[:12].startswith(b'{"location"'):
                body = _get(json.loads(body)["location"])
            return body
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            err = e
        except Exception as e:  # network hiccups
            err = e
        time.sleep(2 + 3 * k)
    raise RuntimeError(f"failed {resource_url} @ {ts}: {err}")


def daterange(start: date, end: date):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def pick_every(timestamps: list[str], minutes: int) -> list[str]:
    """Keep the first snapshot in each ``minutes``-wide bucket of the day."""
    seen, out = set(), []
    for ts in sorted(timestamps):
        hh, mm = int(ts[9:11]), int(ts[11:13])
        key = (ts[:8], (hh * 60 + mm) // minutes)
        if key not in seen:
            seen.add(key)
            out.append(ts)
    return out


def buckets(timestamps: list[str], minutes: int) -> list[list[str]]:
    """Group snapshots into ``minutes``-wide buckets; each bucket keeps all
    candidates in time order so a 404 can fall back to the next one."""
    out: dict[tuple, list[str]] = {}
    for ts in sorted(timestamps):
        hh, mm = int(ts[9:11]), int(ts[11:13])
        out.setdefault((ts[:8], (hh * 60 + mm) // minutes), []).append(ts)
    return list(out.values())


def save(body: bytes, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
