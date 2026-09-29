"""Static reference files (detector locations, daily rainfall)."""

from __future__ import annotations

import io
import zipfile
from datetime import date, timedelta
from pathlib import Path

import requests

from posixpath import basename

from src.config import RAW_DIR, STATIC_SOURCES
from src.download.archive import get_snapshot, list_versions, session

EARLIEST = date(2005, 3, 1)  # historical-archive API rejects start dates before this


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


def download_static_history() -> None:
    """Every archived version of each static file, not just the current one.

    `download_static()` only keeps "as of today"; these files (detector locations,
    road network segments) changed multiple times during 2024-2025, so an analysis
    of that period should be able to pick the version valid at a given date instead.
    (daily_HKO_RF_ALL.csv is cumulative and untracked by the archive, so this is a
    no-op for it -- download_static()'s latest copy already has full history.)
    """
    end = date.today() - timedelta(days=1)
    for rel_path, url in STATIC_SOURCES.items():
        out_dir = RAW_DIR / Path(rel_path).parent / Path(rel_path).stem
        out_dir.mkdir(parents=True, exist_ok=True)
        suffix = "-" + Path(rel_path).name  # e.g. -traffic_speed_volume_occ_info.csv
        bundles = list_versions(url, EARLIEST, end).get("data-files") or []
        for b in bundles:
            ts = b["timestamp"]
            out = out_dir / f"{ts}.csv"
            if out.exists():
                continue
            with zipfile.ZipFile(io.BytesIO(get_snapshot(url, ts))) as zf:
                member = next(i for i in zf.infolist() if basename(i.filename).endswith(suffix))
                data = zf.read(member)
            out.write_bytes(data)
            print(f"[ok]   {rel_path} {ts} ({len(data) / 1e3:.0f} kB)")
