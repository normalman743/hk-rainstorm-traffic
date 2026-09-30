"""Checks on S11 L1: times (missing, repeated, fetch lag), nulls, formats, repeated segments, segment sets.

    python -m src.clean.s11_checks

Reads data/interim/checks/s11_files.csv and data/interim/l1/s11/*.parquet
(python -m src.clean.s11_parse). Changes nothing.

- Times: every observed `time` is HH:MM:00 at an odd minute, so a day is compared with the 720
  odd-minute times (00:01 .. 23:59). This grid is what the files show, not a documented rule.
  Only complete files count; `date` and `time` are taken as written.
- Lag: fetch time of the first copy (manifest) minus date + time of the file, in minutes.
- Repeated: the same segment_id twice in one file (identical or different speed / valid).
  A (date, time) in two complete files is counted too; then the same segment could have two values.
- Segments: for each segment_id, the files it is in and its first and last time, per month.

Output, in data/interim/checks/:
- s11_summary.csv    month, check, n
- s11_days.csv       date, n_files, n_times, missing (of 720), longest_gap_min, off_grid
- s11_segments.csv   month, segment_id, n_files, first, last  (first / last: date time)
- s11_repeated.csv   bundle, index, segment_id, n, n_distinct (segment_id twice in one file)
"""

from __future__ import annotations

import csv
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from statistics import median

import duckdb

from src.clean.s1_periods import OUT_DIR as CHECKS_DIR
from src.clean.s11_parse import FILES, OUT_DIR as L1_DIR

GRID = [f"{m // 60:02d}:{m % 60:02d}:00" for m in range(1, 24 * 60, 2)]
BUCKETS = 16


def _times(files: list[dict], summary: Counter) -> list[tuple]:
    by_day = defaultdict(list)
    for f in files:
        month = f["bundle"][:6]
        summary[(month, "distinct files")] += 1
        summary[(month, f"complete = {f['complete']}")] += 1
        summary[(month, f"irn_version {f['irn_version']}")] += 1
        if f["complete"] != "True":
            continue
        summary[(month, f"segments per file: {f['n_segments']}")] += 1
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", f["date"]) or not re.fullmatch(r"\d{2}:\d{2}:\d{2}", f["time"]):
            summary[(month, "date or time not YYYY-MM-DD / HH:MM:SS")] += 1
            continue
        by_day[f["date"]].append(f["time"])
        t = datetime.strptime(f"{f['date']} {f['time']}", "%Y-%m-%d %H:%M:%S")
        lag = (datetime.strptime(f["fetch_time"], "%Y%m%d-%H%M") - t) / timedelta(minutes=1)
        summary[(month, "lag < 0 (fetched before time)")] += lag < 0
        summary[(month, "lag > 10 min")] += lag > 10
        f["lag"] = lag
    for month in sorted({f["bundle"][:6] for f in files}):
        lags = [f["lag"] for f in files if f["bundle"][:6] == month and "lag" in f]
        summary[(month, "lag min (min)")] = round(min(lags))
        summary[(month, "lag median (min)")] = round(median(lags))
        summary[(month, "lag max (min)")] = round(max(lags))

    days = []
    for date, times in sorted(by_day.items()):
        month = date[:4] + date[5:7]
        count = Counter(times)
        summary[(month, "(date, time) in 2+ complete files")] += sum(1 for n in count.values() if n > 1)
        off = sorted(set(count) - set(GRID))
        run = longest = 0
        for g in GRID:
            run = 0 if g in count else run + 1
            longest = max(longest, run)
        missing = sum(1 for g in GRID if g not in count)
        summary[(month, "days")] += 1
        summary[(month, "grid times missing")] += missing
        summary[(month, "times off the grid")] += len(off)
        days.append((date, len(times), len(count), missing, longest * 2, ";".join(off)))
    return days


def main() -> None:
    with FILES.open() as f:
        files = list(csv.DictReader(f))
    summary: Counter = Counter()
    days = _times(files, summary)

    con = duckdb.connect()
    con.execute(f"SET memory_limit = '6GB'; SET temp_directory = '{L1_DIR.parent / 'duckdb_tmp'}'")
    con.execute(f"CREATE VIEW l1 AS SELECT *, left(bundle, 6) AS month FROM read_parquet('{L1_DIR}/*.parquet')")
    cols = ["date", "time", "irn_version", "segment_id", "speed", "valid"]
    checks = {
        "rows": "count(*)",
        **{f"{c}: absent": f"count(*) FILTER ({c} IS NULL)" for c in cols},
        **{f"{c}: empty": f"count(*) FILTER ({c} = '')" for c in cols},
        "segment_id not digits": r"count(*) FILTER (NOT regexp_full_match(segment_id, '[0-9]+'))",
        "speed not a decimal number": r"count(*) FILTER (NOT regexp_full_match(speed, '-?[0-9]+(\.[0-9]+)?'))",
        "speed with 1 decimal place": r"count(*) FILTER (regexp_full_match(speed, '[0-9]+\.[0-9]'))",
        "speed without decimal point": r"count(*) FILTER (regexp_full_match(speed, '[0-9]+'))",
        "valid = Y": "count(*) FILTER (valid = 'Y')",
        "valid = N": "count(*) FILTER (valid = 'N')",
        "valid other": "count(*) FILTER (valid NOT IN ('Y', 'N'))",
        "speed min": "min(TRY_CAST(speed AS DOUBLE))",
        "speed max": "max(TRY_CAST(speed AS DOUBLE))",
        "speed = 0": "count(*) FILTER (TRY_CAST(speed AS DOUBLE) = 0)",
        "speed > 120": "count(*) FILTER (TRY_CAST(speed AS DOUBLE) > 120)",
        "valid = N: speed min": "min(TRY_CAST(speed AS DOUBLE)) FILTER (valid = 'N')",
        "valid = N: speed max": "max(TRY_CAST(speed AS DOUBLE)) FILTER (valid = 'N')",
        "valid = N: speed = 0": "count(*) FILTER (valid = 'N' AND TRY_CAST(speed AS DOUBLE) = 0)",
        "distinct segment_id": "count(DISTINCT segment_id)",
    }
    sql = ", ".join(f'{e} AS "{k}"' for k, e in checks.items())
    for month, *vals in con.execute(f"SELECT month, {sql} FROM l1 GROUP BY month ORDER BY month").fetchall():
        for k, v in zip(checks, vals):
            summary[(month, k)] = v if not isinstance(v, float) else round(v, 1)

    repeated = []
    for b in range(BUCKETS):
        repeated += con.execute(f"""
            SELECT bundle, index, segment_id, count(*), count(DISTINCT (speed, valid))
            FROM l1 WHERE hash(segment_id) % {BUCKETS} = {b}
            GROUP BY bundle, index, segment_id HAVING count(*) > 1""").fetchall()
    for bundle, index, seg, n, nd in repeated:
        summary[(bundle[:6], "segment_id twice in a file: keys")] += 1
        summary[(bundle[:6], f"segment_id twice in a file: keys with {'same' if nd == 1 else 'different'} values")] += 1
    segments = con.execute("""
        SELECT month, segment_id, count(DISTINCT index), min(date || ' ' || time), max(date || ' ' || time)
        FROM l1 GROUP BY month, segment_id ORDER BY month, segment_id""").fetchall()
    n_files = Counter(f["bundle"][:6] for f in files if f["complete"] == "True")
    for month, seg, n, first, last in segments:
        summary[(month, "segments in every complete file" if n == n_files[month]
                 else "segments missing from some complete files")] += 1

    CHECKS_DIR.mkdir(parents=True, exist_ok=True)
    out = {
        "s11_summary.csv": (["month", "check", "n"], [(m, c, n) for (m, c), n in sorted(summary.items())]),
        "s11_days.csv": (["date", "n_files", "n_times", "missing", "longest_gap_min", "off_grid"], days),
        "s11_segments.csv": (["month", "segment_id", "n_files", "first", "last"], segments),
        "s11_repeated.csv": (["bundle", "index", "segment_id", "n", "n_distinct"], sorted(repeated)),
    }
    for name, (header, rows) in out.items():
        with (CHECKS_DIR / name).open("w", newline="") as f:
            w = csv.writer(f)
            w.writerow(header)
            w.writerows(rows)
    print(f"written to {CHECKS_DIR}: {', '.join(out)}\n")
    months = sorted({m for m, _ in summary})
    print(f"{'check':55}" + "".join(f"{m:>14}" for m in months))
    for c in sorted({c for _, c in summary}):
        print(f"{c[:55]:55}" + "".join(f"{summary.get((m, c), 0):>14,}" for m in months))


if __name__ == "__main__":
    main()
