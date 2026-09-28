"""Download -> parse -> Parquet, one day at a time: python -m src.pipeline ...

For each source and day:
  1. download the day's snapshots into data/raw/<source>/<YYYY>/<YYYYMMDD>.zip
  2. parse them into data/processed/<table>/<YYYY>/<YYYYMMDD>.parquet
  3. delete the ZIP (unless --keep-raw), so disk use stays at the Parquet size
  4. record coverage in data/processed/coverage.csv

Days whose Parquet file already exists are skipped, so the command can be
re-run after an interruption. A day that fails is logged in coverage.csv and
the run continues.

Each day's file holds everything archived on that day, which includes a few
minutes of the previous day (files lag measurement time). Use
src.data.load_* to read days; it deduplicates across neighbouring files.
"""

from __future__ import annotations

import argparse
import csv
from datetime import date, timedelta
from pathlib import Path

from src.config import PROCESSED_DIR
from src.download.archive import download_day
from src.download.select_days import read_manifest
from src.parse import traffic, weather

TABLES = {
    "traffic": ("traffic_lane", traffic.parse_day_zip),
    "weather": ("rainfall_district", weather.parse_day_zip),
}
COVERAGE = PROCESSED_DIR / "coverage.csv"
COVERAGE_FIELDS = ["source", "date", "status", "n_snapshots", "n_rows_raw", "n_rows", "n_periods",
                   "n_detectors", "has_sd", "n_periods_redated", "n_bulletins", "n_with_rain_section", "max_rain_mm", "error"]


def table_path(source: str, day: date) -> Path:
    return PROCESSED_DIR / TABLES[source][0] / f"{day:%Y}" / f"{day:%Y%m%d}.parquet"


def _read_coverage() -> dict[tuple[str, str], dict]:
    if not COVERAGE.exists():
        return {}
    with COVERAGE.open() as f:
        return {(r["source"], r["date"]): r for r in csv.DictReader(f)}


def _write_coverage(rows: dict[tuple[str, str], dict]) -> None:
    COVERAGE.parent.mkdir(parents=True, exist_ok=True)
    tmp = COVERAGE.with_suffix(".csv.part")
    with tmp.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COVERAGE_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows[k] for k in sorted(rows))
    tmp.replace(COVERAGE)


def process_day(source: str, day: date, keep_raw: bool = False, workers: int = 8) -> dict:
    out = table_path(source, day)
    if out.exists():
        print(f"[skip] {out.relative_to(PROCESSED_DIR)} exists")
        return {}
    raw = download_day(source, day, workers=workers)
    if raw is None:
        return {"source": source, "date": day.isoformat(), "status": "no_data"}
    df, stats = TABLES[source][1](raw)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".parquet.part")
    df.to_parquet(tmp, compression="zstd", index=False)
    tmp.replace(out)
    if not keep_raw:
        raw.unlink()
    print(f"[ok]   {out.relative_to(PROCESSED_DIR)}: {len(df):,} rows, {out.stat().st_size / 1e6:.1f} MB")
    return {"source": source, "date": day.isoformat(), "status": "ok", **stats}


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m src.pipeline", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    when = parser.add_mutually_exclusive_group(required=True)
    when.add_argument("--manifest", action="store_true", help="days in data/interim/day_manifest.csv")
    when.add_argument("--days", nargs="+", type=date.fromisoformat, help="YYYY-MM-DD ...")
    when.add_argument("--range", nargs=2, type=date.fromisoformat, metavar=("START", "END"))
    parser.add_argument("--sources", nargs="+", choices=list(TABLES), default=["weather", "traffic"])
    parser.add_argument("--keep-raw", action="store_true", help="keep the downloaded ZIPs")
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()

    if args.manifest:
        days = read_manifest()
    elif args.range:
        start, end = args.range
        days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    else:
        days = args.days

    coverage = _read_coverage()
    failures = 0
    for source in args.sources:
        for day in days:
            try:
                row = process_day(source, day, keep_raw=args.keep_raw, workers=args.workers)
            except Exception as exc:  # keep going; the failure is recorded and printed
                failures += 1
                print(f"[fail] {source} {day}: {type(exc).__name__}: {exc}")
                row = {"source": source, "date": day.isoformat(), "status": "failed",
                       "error": f"{type(exc).__name__}: {exc}"}
            if row:
                coverage[(row["source"], row["date"])] = row
                _write_coverage(coverage)
    print(f"done: {len(days)} days x {len(args.sources)} sources, {failures} failed -> {COVERAGE}")


if __name__ == "__main__":
    main()
