"""Command-line entry point: python -m src.download <command> ...

    warnings      HKO rainstorm + tropical cyclone warning databases -> CSV
    static        detector locations, road segments, daily rainfall
    holidays      Hong Kong general holidays 2018-2027 (merged archived versions)
    select-days   build data/interim/day_manifest.csv (event + control days)
    fetch         download archived snapshots for given days
"""

from __future__ import annotations

import argparse
from datetime import date, timedelta

from tqdm import tqdm

from src.config import ARCHIVED_SOURCES
from src.download.archive import download_day
from src.download.holidays import download_holidays
from src.download.select_days import MANIFEST, read_manifest, select_days, write_manifest
from src.download.static import download_static
from src.download.warnings import LEVELS, download_warnings


def _date_range(start: date, end: date) -> list[date]:
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m src.download", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("warnings", help="download HKO warning databases")
    sub.add_parser("static", help="download static reference files")
    sub.add_parser("holidays", help="download Hong Kong public holidays")

    sel = sub.add_parser("select-days", help="choose event and control days")
    sel.add_argument("--years", default="2022-2025",
                     help="e.g. 2022-2025 or 2025 (2021 has only ~42 detectors until Nov)")
    sel.add_argument("--min-level", choices=list(LEVELS), default="A",
                     help="lowest warning level that makes an event (A/R/B)")
    sel.add_argument("--months", default="4-10", help="months to keep, e.g. 4-10 (rainy season)")
    sel.add_argument("--pad-hours", type=int, default=3)
    sel.add_argument("--controls", type=int, default=2, help="control weeks per event day")

    fetch = sub.add_parser("fetch", help="download archived snapshots")
    fetch.add_argument("sources", nargs="+", choices=list(ARCHIVED_SOURCES))
    when = fetch.add_mutually_exclusive_group(required=True)
    when.add_argument("--days", nargs="+", type=date.fromisoformat, help="YYYY-MM-DD ...")
    when.add_argument("--range", nargs=2, type=date.fromisoformat, metavar=("START", "END"))
    when.add_argument("--manifest", action="store_true", help=f"use {MANIFEST.name}")
    fetch.add_argument("--workers", type=int, default=16, help="download threads per day")
    fetch.add_argument("--overwrite", action="store_true")

    args = parser.parse_args()

    if args.command == "warnings":
        download_warnings()
    elif args.command == "static":
        download_static()
    elif args.command == "holidays":
        download_holidays()
    elif args.command == "select-days":
        first, _, last = args.years.partition("-")
        m1, _, m2 = args.months.partition("-")
        rows = select_days(int(first), int(last or first), LEVELS[args.min_level], args.pad_hours,
                           args.controls, tuple(range(int(m1), int(m2 or m1) + 1)))
        write_manifest(rows)
        n_event = sum(r["role"] == "event" for r in rows)
        print(f"{len(rows)} days ({n_event} event, {len(rows) - n_event} control) -> {MANIFEST}")
    elif args.command == "fetch":
        days = (args.days or (_date_range(*args.range) if args.range else read_manifest()))
        tasks = [(source, day) for source in args.sources for day in days]
        with tqdm(total=len(tasks), desc="days", unit="day", position=0) as days_bar, \
                tqdm(desc="download", unit="file", position=1, leave=False) as dl_bar:
            for source, day in tasks:
                dl_bar.set_description(f"download {source} {day}")
                download_day(source, day, workers=args.workers, overwrite=args.overwrite,
                             log=tqdm.write, progress=dl_bar)
                days_bar.update()


if __name__ == "__main__":
    main()
