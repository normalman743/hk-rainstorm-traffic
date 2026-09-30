"""Which 30-second periods do the S1 files hold? Missing periods and periods found in several files.

    python -m src.clean.s1_periods [--source s1] [--workers 8]

`--source s9` does the same for the smart-lamppost readings, which have the S1 format
(same XSD, SpeedVolOcc-BR.xsd). Below, <source> is s1 or s9 and <resource> its file name.

Needs data/interim/manifest/<resource>.csv (python -m src.clean.manifest ...).
One file per group of identical files is read (the others have the same bytes). Nothing is
changed or corrected: dates and times are taken as written in the file, so the 00:00 period
stays under the previous day's <date> (see docs/raw_data.md, S1 quirks).

Output, in data/interim/checks/:
- <source>_files.csv: one row per distinct file: bundle, index, member, fetch_time, n_copies,
  n_date (number of <date> elements), date, periods (period_from values, ";"-joined),
  period_to (";"-joined), complete (ends with </raw_speed_volume_list>).
- <source>_days.csv: one row per <date> in the files: n_files, n_periods (distinct period_from),
  missing (of 2,880), longest_gap_min (longest run of missing periods, in minutes),
  periods_in_several_files (period_from values that occur in more than one distinct file).
"""

from __future__ import annotations

import argparse
import csv
import re
import zipfile
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from os import cpu_count
from pathlib import Path

from tqdm import tqdm

from src.clean.manifest import OUT_DIR as MANIFEST_DIR
from src.config import INTERIM_DIR, RAW_DIR

# sources in the S1 format: name -> resource file name
SOURCES = {"s1": "rawSpeedVol-all.xml", "s9": "rawSpeedVol_SLP-all.xml"}
TD_DIR = RAW_DIR / "resource.data.one.gov.hk/td/traffic-detectors"
OUT_DIR = INTERIM_DIR / "checks"
END = b"</raw_speed_volume_list>"
PERIODS_PER_DAY = 2880

_zips: dict[Path, zipfile.ZipFile] = {}


def _read(bundle: Path, indexes: list[int]) -> list[tuple[int, list[bytes], list[bytes], list[bytes], bool, int]]:
    if bundle not in _zips:
        _zips[bundle] = zipfile.ZipFile(bundle)
    z = _zips[bundle]
    infos = z.infolist()
    out = []
    for i in indexes:
        b = z.read(infos[i])
        out.append((i, re.findall(rb"<date>(.*?)</date>", b),
                    re.findall(rb"<period_from>(.*?)</period_from>", b),
                    re.findall(rb"<period_to>(.*?)</period_to>", b),
                    b.rstrip().endswith(END), len(b)))
    return out


def bundles(source: str) -> Path:
    return TD_DIR / SOURCES[source] / "bundle"


def _seconds(hms: str) -> int:
    h, m, s = hms.split(":")
    return int(h) * 3600 + int(m) * 60 + int(s)


def build(source: str, workers: int) -> None:
    with (MANIFEST_DIR / f"{SOURCES[source]}.csv").open() as f:
        rows = [r for r in csv.DictReader(f) if r["group"] == f"{r['bundle']}:{r['index']}"]

    tasks: list[tuple[Path, list[int]]] = []
    for bundle in sorted({r["bundle"] for r in rows}):
        ix = [int(r["index"]) for r in rows if r["bundle"] == bundle]
        tasks += [(bundles(source) / bundle, ix[s:s + 300]) for s in range(0, len(ix), 300)]
    by_key = {(r["bundle"], int(r["index"])): r for r in rows}
    total = sum(int(r["size"]) for r in rows)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    days: dict[str, dict] = defaultdict(lambda: {"files": 0, "periods": defaultdict(int)})
    odd: dict[str, int] = defaultdict(int)  # counts of files that are incomplete or not 1 <date>
    with ProcessPoolExecutor(max_workers=workers) as pool, \
            tqdm(total=total, unit="B", unit_scale=True, desc="reading") as bar, \
            (OUT_DIR / f"{source}_files.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["bundle", "index", "member", "fetch_time", "n_copies",
                    "n_date", "date", "periods", "period_to", "complete"])
        futures = {pool.submit(_read, path, ix): path for path, ix in tasks}
        for fut in as_completed(futures):
            for i, dates, froms, tos, complete, nbytes in fut.result():
                r = by_key[(futures[fut].name, i)]
                date = dates[0].decode() if len(dates) == 1 else ""
                froms_s = [x.decode() for x in froms]
                w.writerow([r["bundle"], i, r["member"], r["fetch_time"], r["n_copies"],
                            len(dates), date, ";".join(froms_s),
                            ";".join(x.decode() for x in tos), complete])
                if not complete:
                    odd["incomplete"] += 1
                if len(dates) != 1:
                    odd[f"{len(dates)} <date>"] += 1
                if len(froms) != 2:
                    odd[f"{len(froms)} periods"] += 1
                if date:
                    days[date]["files"] += 1
                    for p in set(froms_s):
                        days[date]["periods"][p] += 1
                bar.update(nbytes)

    day_rows = []
    for date in sorted(days):
        present = sorted(_seconds(p) for p in days[date]["periods"])
        # gaps in 30-s steps, including before the first and after the last period of the day
        edges = [-30] + present + [PERIODS_PER_DAY * 30]
        longest = max((b - a) // 30 - 1 for a, b in zip(edges, edges[1:]))
        several = sum(1 for n in days[date]["periods"].values() if n > 1)
        day_rows.append([date, days[date]["files"], len(present), PERIODS_PER_DAY - len(present),
                         longest / 2, several])
    with (OUT_DIR / f"{source}_days.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "n_files", "n_periods", "missing", "longest_gap_min", "periods_in_several_files"])
        w.writerows(day_rows)
    print(f"written to {OUT_DIR}: {source}_files.csv, {source}_days.csv")

    print("files that are incomplete / not one <date> / not two periods:", dict(odd) or "none")
    print(f"{'month':8} {'days':>4} {'files':>7} {'missing %':>9} {'min/day':>8} {'max/day':>8} "
          f"{'longest gap (min)':>17} {'periods in >1 file':>18}")
    for month in sorted({d[:7] for d, *_ in day_rows}):
        ds = [r for r in day_rows if r[0][:7] == month]
        miss = [r[3] for r in ds]
        print(f"{month:8} {len(ds):4} {sum(r[1] for r in ds):7,} "
              f"{100 * sum(miss) / (PERIODS_PER_DAY * len(ds)):9.1f} {min(miss):8} {max(miss):8} "
              f"{max(r[4] for r in ds):17} {sum(r[5] for r in ds):18}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--source", choices=list(SOURCES), default="s1")
    p.add_argument("--workers", type=int, default=cpu_count())
    a = p.parse_args()
    build(a.source, a.workers)


if __name__ == "__main__":
    main()
