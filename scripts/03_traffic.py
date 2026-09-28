"""Download TD traffic-detector snapshots from the DATA.GOV.HK archive, parse
them to lane level, and store one Parquet file per day. Raw XML is discarded.

Output: data/interim/traffic/lanes_<YYYYMMDD>.parquet   (git-ignored, ~5-15 MB/day)
        data/interim/traffic/_download_log.csv          (missing snapshots)

A full day has ~1,000 snapshots (~0.7 GB). By default we keep one snapshot
every 5 minutes (~200 MB of downloads per day). Each snapshot contains two
30-second periods; both are kept.

Usage:  python scripts/03_traffic.py 2025-07-27 2025-08-16 [--every 5] [--workers 6]
"""
import argparse
import xml.etree.ElementTree as ET
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from hkrt.archive import TRAFFIC_RAW_URL, buckets, daterange, fetch_version, list_versions  # noqa: E402
from hkrt.parse import parse_traffic_xml  # noqa: E402

OUT = ROOT / "data" / "interim" / "traffic"


def one_bucket(cands: list[str], max_tries: int = 4):
    """Try snapshots in the bucket in order until one exists in the archive."""
    for ts in cands[:max_tries]:
        body = fetch_version(TRAFFIC_RAW_URL, ts)
        if body is None:
            continue
        try:
            return cands[0], parse_traffic_xml(body, ts)
        except ET.ParseError:  # some archived files are truncated
            print("  truncated XML, trying next:", ts)
    return cands[0], None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("start"); ap.add_argument("end")
    ap.add_argument("--every", type=int, default=5, help="minutes between kept snapshots")
    ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    log = []
    for d in daterange(date.fromisoformat(a.start), date.fromisoformat(a.end)):
        path = OUT / f"lanes_{d:%Y%m%d}.parquet"
        if path.exists():
            print("skip", path.name); continue
        wanted = buckets(list_versions(TRAFFIC_RAW_URL, d, d), a.every)
        with ThreadPoolExecutor(a.workers) as ex:
            res = list(ex.map(one_bucket, wanted))
        frames = [df for _, df in res if df is not None]
        miss = [ts for ts, df in res if df is None]
        log += [{"date": d, "bucket_start": ts, "status": "no snapshot"} for ts in miss]
        day = pd.concat(frames, ignore_index=True)
        for c in ["detector_id", "direction", "lane", "valid", "snapshot"]:
            day[c] = day[c].astype("category")
        day.to_parquet(path, compression="zstd", index=False)
        print(f"{path.name}: {len(wanted)-len(miss)}/{len(wanted)} snapshots, {len(day):,} lane rows")
    if log:
        lp = OUT / "_download_log.csv"
        pd.DataFrame(log).to_csv(lp, mode="a", header=not lp.exists(), index=False)


if __name__ == "__main__":
    main()
