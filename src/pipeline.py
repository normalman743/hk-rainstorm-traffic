"""Download -> parse -> Parquet, day by day: python -m src.pipeline ...

For each source and day:
  1. download the day's snapshots into data/raw/<source>/<YYYY>/<YYYYMMDD>.zip
  2. parse them into data/processed/<table>/<YYYY>/<YYYYMMDD>.parquet
  3. delete the ZIP (unless --keep-raw), so disk use stays at the Parquet size
  4. record coverage in data/processed/coverage.csv

Downloads run in this process (many threads per day, network-bound); parsing
runs in a pool of --jobs worker processes (CPU-bound, ~20 s and ~1.6 GB RAM per
traffic day). Downloads stay at most --jobs days ahead of parsing, so only a
few ZIPs sit on disk at once.

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
import os
from concurrent.futures import FIRST_COMPLETED, Future, ProcessPoolExecutor, wait
from datetime import date, timedelta
from pathlib import Path

from tqdm import tqdm

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
                   "n_detectors", "has_sd", "n_periods_redated", "n_truncated_files", "n_bulletins", "n_with_rain_section",
                   "max_rain_mm", "error"]


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


def convert_day(source: str, day: date, raw: Path, keep_raw: bool = False) -> dict:
    """Parse one downloaded day into Parquet (runs in a worker process)."""
    df, stats = TABLES[source][1](raw)
    out = table_path(source, day)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".parquet.part")
    df.to_parquet(tmp, compression="zstd", index=False)
    tmp.replace(out)
    if not keep_raw:
        raw.unlink()
    return {"source": source, "date": day.isoformat(), "status": "ok", "n_rows": len(df),
            "size_mb": out.stat().st_size / 1e6, **stats}


def run(tasks: list[tuple[str, date]], jobs: int = 3, workers: int = 16, keep_raw: bool = False) -> int:
    """Process (source, day) tasks; returns the number of failures."""
    todo = [t for t in tasks if not table_path(*t).exists()]
    coverage = _read_coverage()
    failures = 0

    def record(row: dict, days_bar: tqdm) -> None:
        nonlocal failures
        coverage[(row["source"], row["date"])] = row
        _write_coverage(coverage)
        if row["status"] == "ok":
            tqdm.write(f"[ok]   {row['source']} {row['date']}: {row['n_rows']:,} rows, {row['size_mb']:.1f} MB")
        else:
            failures += row["status"] == "failed"
            tqdm.write(f"[{row['status']}] {row['source']} {row['date']}: {row.get('error', '')}")
        days_bar.update()
        days_bar.set_postfix(failed=failures)

    def collect(pending: dict[Future, tuple[str, date]], days_bar: tqdm, block_until: int) -> None:
        while len(pending) > block_until:
            done, _ = wait(pending, return_when=FIRST_COMPLETED)
            for fut in done:
                source, day = pending.pop(fut)
                try:
                    row = fut.result()
                except Exception as exc:  # recorded and reported; the run continues
                    row = {"source": source, "date": day.isoformat(), "status": "failed",
                           "error": f"parse: {type(exc).__name__}: {exc}"}
                record(row, days_bar)

    with tqdm(total=len(tasks), initial=len(tasks) - len(todo), desc="days", unit="day", position=0) as days_bar, \
            tqdm(desc="download", unit="file", position=1, leave=False) as dl_bar, \
            ProcessPoolExecutor(max_workers=jobs) as pool:
        if len(todo) < len(tasks):
            tqdm.write(f"[skip] {len(tasks) - len(todo)} day(s) already converted")
        pending: dict[Future, tuple[str, date]] = {}
        for source, day in todo:
            collect(pending, days_bar, block_until=jobs)  # keep at most `jobs` days waiting to parse
            dl_bar.set_description(f"download {source} {day}")
            try:
                raw = download_day(source, day, workers=workers, log=lambda msg: None, progress=dl_bar)
            except Exception as exc:
                record({"source": source, "date": day.isoformat(), "status": "failed",
                        "error": f"download: {type(exc).__name__}: {exc}"}, days_bar)
                continue
            if raw is None:
                record({"source": source, "date": day.isoformat(), "status": "no_data"}, days_bar)
                continue
            pending[pool.submit(convert_day, source, day, raw, keep_raw)] = (source, day)
        dl_bar.close()  # downloads finished; only parsing remains
        collect(pending, days_bar, block_until=0)
    return failures


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m src.pipeline", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    when = parser.add_mutually_exclusive_group(required=True)
    when.add_argument("--manifest", action="store_true", help="days in data/interim/day_manifest.csv")
    when.add_argument("--days", nargs="+", type=date.fromisoformat, help="YYYY-MM-DD ...")
    when.add_argument("--range", nargs=2, type=date.fromisoformat, metavar=("START", "END"))
    parser.add_argument("--sources", nargs="+", choices=list(TABLES), default=["weather", "traffic"])
    parser.add_argument("--jobs", type=int, default=min(3, os.cpu_count() or 1),
                        help="parallel parse processes (each needs ~1.6 GB RAM for a traffic day; default 3)")
    parser.add_argument("--workers", type=int, default=16, help="download threads per day (default 16)")
    parser.add_argument("--keep-raw", action="store_true", help="keep the downloaded ZIPs")
    args = parser.parse_args()

    if args.manifest:
        days = read_manifest()
    elif args.range:
        start, end = args.range
        days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    else:
        days = args.days

    tasks = [(source, day) for source in args.sources for day in days]
    failures = run(tasks, jobs=args.jobs, workers=args.workers, keep_raw=args.keep_raw)
    print(f"done: {len(tasks)} tasks, {failures} failed -> {COVERAGE}")


if __name__ == "__main__":
    main()
