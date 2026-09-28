"""Static reference files (detector locations, daily rainfall)."""

from __future__ import annotations

from datetime import date, timedelta

import requests

from src.config import RAW_DIR, STATIC_SOURCES
from src.download.archive import get_snapshot, list_versions, session


def _latest_archived(url: str) -> bytes:
    """Most recent copy of `url` in the DATA.GOV.HK Historical Archive (up to yesterday)."""
    end = date.today() - timedelta(days=1)
    timestamps = list_versions(url, end - timedelta(days=30), end).get("timestamps") or []
    if not timestamps:
        raise RuntimeError(f"no archived copy of {url}")
    return get_snapshot(url, timestamps[-1])


def download_static() -> None:
    for rel_path, url in STATIC_SOURCES.items():
        out = RAW_DIR / rel_path
        out.parent.mkdir(parents=True, exist_ok=True)
        try:
            resp = session().get(url, timeout=60)
            resp.raise_for_status()
            content, via = resp.content, "direct"
        except requests.RequestException as exc:
            # www/data.weather.gov.hk sometimes resets connections from cloud hosts.
            print(f"[warn] {rel_path}: {type(exc).__name__}, falling back to historical archive")
            content, via = _latest_archived(url), "archive"
        out.write_bytes(content)
        print(f"[ok]   {rel_path} ({len(content) / 1e3:.0f} kB, {via})")
