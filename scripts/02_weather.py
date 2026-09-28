"""Download HKO Current Weather Reports (hourly) from the DATA.GOV.HK archive
and extract past-hour rainfall per district.

Output: data/weather/district_rain_<start>_<end>.csv  (small; committed)
        one row per (report, district that had rain); dry reports -> district empty

Usage:  python scripts/02_weather.py 2025-07-01 2025-08-31
"""
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from hkrt.archive import CURRENT_WEATHER_URL, daterange, fetch_version, list_versions  # noqa: E402
from hkrt.parse import parse_current_weather  # noqa: E402


def one(ts: str):
    body = fetch_version(CURRENT_WEATHER_URL, ts)
    return ts, (None if body is None else parse_current_weather(body, ts))


def main(start: str, end: str, workers: int = 12):
    s, e = date.fromisoformat(start), date.fromisoformat(end)
    with ThreadPoolExecutor(workers) as ex:
        days = list(ex.map(lambda d: list_versions(CURRENT_WEATHER_URL, d, d), daterange(s, e)))
        res = list(ex.map(one, [ts for day in days for ts in day]))
    df = pd.concat([r for _, r in res if r is not None], ignore_index=True)
    missing = [ts for ts, r in res if r is None]
    # several bulletins can describe the same hour (updates); keep the latest
    df = df.sort_values("snapshot").drop_duplicates(["report_time", "district"], keep="last")
    out = ROOT / "data" / "weather" / f"district_rain_{s:%Y%m%d}_{e:%Y%m%d}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)
    print(f"{out.name}: {df.report_time.nunique()} hourly reports, {len(df)} rows, {len(missing)} missing snapshots")


if __name__ == "__main__":
    main(*sys.argv[1:3])
