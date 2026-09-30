"""Checks on S7 L1: files not parsed, per-file shape, formats, grid, repeated cells, times, values.

    python -m src.clean.s7_checks

Reads data/interim/checks/s7_files.csv, data/interim/l1/s7/*.parquet (python -m src.clean.s7_parse)
and the manifest (every fetch). Changes nothing.

- Shape of a file: rows, distinct `updated`, distinct `ending`, rows per ending, and a cell
  (ending, latitude, longitude) twice in one file. The grid over all files is counted too.
- Cell set: per (file, ending), the XOR of the hashes of its (latitude, longitude) pairs; a file
  whose value differs from the most common one has a cell that the usual grid does not (a
  corrupted row can keep 5 fields and the format, so this is how it shows).
- Formats: updated / ending 12 digits (YYYYMMDDHHMM), latitude / longitude digits.3 digits,
  rainfall digits.2 digits.
- Times: `ending` - `updated` in minutes; fetch time minus `updated`; the same `updated` in two
  distinct files (then the values are compared); gaps between successive `updated` values.

Output, in data/interim/checks/:
- s7_summary.csv     month, check, n
- s7_file_stats.csv  bundle, index, fetch_time, n_rows, n_updated, updated, n_ending, endings
                     (minutes after updated, ";"-joined), rows_per_ending (";"-joined), cells_differ
- s7_days.csv        date (of fetch), fetches, parsed, distinct_updated, longest_gap_min
                     (between successive distinct `updated` of parsed files, within the day)
"""

from __future__ import annotations

import csv
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from statistics import median

import duckdb

from src.clean.manifest import OUT_DIR as MANIFEST_DIR
from src.clean.s1_periods import OUT_DIR as CHECKS_DIR
from src.clean.s7_parse import FILES, OUT_DIR as L1_DIR, RESOURCE

BUCKETS = 16
FORMATS = {"updated": "[0-9]{12}", "ending": "[0-9]{12}", "latitude": r"[0-9]+\.[0-9]{3}",
           "longitude": r"[0-9]+\.[0-9]{3}", "rainfall": r"[0-9]+\.[0-9]{2}"}


def _minutes(a: str, b: str) -> float:
    return (datetime.strptime(b, "%Y%m%d%H%M") - datetime.strptime(a, "%Y%m%d%H%M")) / timedelta(minutes=1)


def main() -> None:
    with FILES.open() as f:
        files = list(csv.DictReader(f))
    with (MANIFEST_DIR / f"{RESOURCE}.csv").open() as f:
        fetches = [r for r in csv.DictReader(f) if r["member"].endswith(f"-{RESOURCE}")]
    summary: Counter = Counter()
    for r in files:
        month = r["bundle"][:6]
        summary[(month, "distinct files")] += 1
        summary[(month, f"parsed = {r['parsed']}")] += 1
        if r["parsed"] != "True":
            kind = "no final newline" if r["problem"].startswith("no final newline") else "a line without 5 fields"
            summary[(month, f"not parsed: {kind}")] += 1

    con = duckdb.connect()
    con.execute(f"SET memory_limit = '6GB'; SET temp_directory = '{L1_DIR.parent / 'duckdb_tmp'}'")
    con.execute(f"CREATE VIEW l1 AS SELECT *, left(bundle, 6) AS mon FROM read_parquet('{L1_DIR}/*.parquet')")

    checks = {
        "rows": "count(*)",
        **{f"{c}: empty": f"count(*) FILTER ({c} = '')" for c in FORMATS},
        **{f"{c}: other format": f"count(*) FILTER (NOT regexp_full_match({c}, '{p}'))" for c, p in FORMATS.items()},
        "rainfall min": "min(TRY_CAST(rainfall AS DOUBLE))",
        "rainfall max": "max(TRY_CAST(rainfall AS DOUBLE))",
        "rainfall = 0.00": "count(*) FILTER (rainfall = '0.00')",
        "rainfall >= 0.50": "count(*) FILTER (TRY_CAST(rainfall AS DOUBLE) >= 0.5)",
        "rainfall >= 10": "count(*) FILTER (TRY_CAST(rainfall AS DOUBLE) >= 10)",
        "rainfall >= 100": "count(*) FILTER (TRY_CAST(rainfall AS DOUBLE) >= 100)",
        "rainfall >= 1000": "count(*) FILTER (TRY_CAST(rainfall AS DOUBLE) >= 1000)",
        "distinct latitude": "count(DISTINCT latitude)",
        "distinct longitude": "count(DISTINCT longitude)",
        "latitude min": "min(latitude)", "latitude max": "max(latitude)",
        "longitude min": "min(longitude)", "longitude max": "max(longitude)",
    }
    sql = ", ".join(f'{e} AS "{k}"' for k, e in checks.items())
    for mon, *vals in con.execute(f"SELECT mon, {sql} FROM l1 GROUP BY mon ORDER BY mon").fetchall():
        for k, v in zip(checks, vals):
            summary[(mon, k)] = v
    n_cells = con.execute("SELECT count(*) FROM (SELECT DISTINCT latitude, longitude FROM l1)").fetchone()[0]
    summary[("all", "distinct (latitude, longitude) over all files")] = n_cells

    for b in range(BUCKETS):
        for mon, n in con.execute(f"""
                SELECT mon, count(*) FROM (
                    SELECT mon, bundle, index, ending, latitude, longitude FROM l1
                    WHERE hash(latitude, longitude) % {BUCKETS} = {b}
                    GROUP BY ALL HAVING count(*) > 1)
                GROUP BY mon""").fetchall():
            summary[(mon, "cell (ending, latitude, longitude) twice in a file")] += n

    per_ending = con.execute("""
        SELECT bundle, index, updated, ending, count(*), bit_xor(hash(latitude, longitude))
        FROM l1 GROUP BY bundle, index, updated, ending ORDER BY ALL""").fetchall()
    by_file = defaultdict(list)
    cell_sets = Counter(h for *_, h in per_ending)
    common = cell_sets.most_common(1)[0][0]
    for bundle, index, upd, end, n, h in per_ending:
        by_file[(bundle, str(index))].append((upd, end, n, h != common))
    fetch = {(r["bundle"], r["index"]): r["fetch_time"] for r in files}
    stats, lags, by_updated = [], defaultdict(list), defaultdict(list)
    for (bundle, index), rows in sorted(by_file.items()):
        month = bundle[:6]
        updated = sorted({r[0] for r in rows})
        ends = sorted({r[1] for r in rows})
        n_rows = sum(r[2] for r in rows)
        cells_differ = any(r[3] for r in rows)
        summary[(month, f"file rows: {n_rows}")] += 1
        summary[(month, f"file distinct updated: {len(updated)}")] += 1
        summary[(month, f"file distinct ending: {len(ends)}")] += 1
        summary[(month, "file cells differ from the most common cell set")] += cells_differ
        per = ";".join(str(r[2]) for r in rows)
        summary[(month, f"rows per ending: {per if len(set(per.split(';'))) > 1 else per.split(';')[0] + ' each'}")] += 1
        after = ";".join(str(round(_minutes(updated[0], e))) for e in ends) if len(updated) == 1 else ""
        summary[(month, f"ending - updated (min): {after or 'several updated'}")] += 1
        stats.append((bundle, index, fetch[(bundle, index)], n_rows, len(updated), ";".join(updated),
                      len(ends), after, per, cells_differ))
        if len(updated) == 1:
            ft = datetime.strptime(fetch[(bundle, index)], "%Y%m%d-%H%M").strftime("%Y%m%d%H%M")
            lags[month].append(_minutes(updated[0], ft))
            by_updated[updated[0]].append((bundle, index))
            summary[(month, f"updated at minute :{updated[0][-2:]}")] += 1
    for month, xs in sorted(lags.items()):
        summary[(month, "fetch - updated, min (min)")] = round(min(xs))
        summary[(month, "fetch - updated, median (min)")] = round(median(xs))
        summary[(month, "fetch - updated, max (min)")] = round(max(xs))
        summary[(month, "fetch - updated < 0")] = sum(1 for x in xs if x < 0)
    for upd, fs in by_updated.items():
        if len(fs) > 1:
            month = fs[0][0][:6]
            summary[(month, "updated in 2+ distinct files")] += 1
            where = " OR ".join(f"(bundle = '{b}' AND index = {i})" for b, i in fs)
            n_diff = con.execute(f"""
                SELECT count(*) FROM (SELECT ending, latitude, longitude FROM l1 WHERE {where}
                GROUP BY ALL HAVING count(DISTINCT rainfall) > 1)""").fetchone()[0]
            summary[(month, "updated in 2+ distinct files: cells with different rainfall")] += n_diff

    days_fetch = Counter(r["fetch_time"][:8] for r in fetches)
    days_parsed = Counter(r["fetch_time"][:8] for r in files if r["parsed"] == "True")
    upd_by_day = defaultdict(set)
    for upd in by_updated:
        upd_by_day[upd[:8]].add(upd)
    days = []
    for day in sorted(set(days_fetch) | set(upd_by_day)):
        ts = sorted(upd_by_day[day])
        gap = max((_minutes(a, b) for a, b in zip(ts, ts[1:])), default=None)
        days.append((day, days_fetch[day], days_parsed[day], len(ts), None if gap is None else round(gap)))
        month = day[:6]
        summary[(month, "days")] += 1
        summary[(month, f"fetches per day: {'96' if days_fetch[day] == 96 else 'other'}")] += 1

    CHECKS_DIR.mkdir(parents=True, exist_ok=True)
    out = {
        "s7_summary.csv": (["month", "check", "n"], [(m, c, n) for (m, c), n in sorted(summary.items())]),
        "s7_file_stats.csv": (["bundle", "index", "fetch_time", "n_rows", "n_updated", "updated", "n_ending",
                               "endings_after_updated_min", "rows_per_ending", "cells_differ"], stats),
        "s7_days.csv": (["date", "fetches", "parsed", "distinct_updated", "longest_gap_min"], days),
    }
    for name, (header, rows) in out.items():
        with (CHECKS_DIR / name).open("w", newline="") as f:
            w = csv.writer(f)
            w.writerow(header)
            w.writerows(rows)
    print(f"written to {CHECKS_DIR}: {', '.join(out)}\n")
    months = sorted({m for m, _ in summary})
    print(f"{'check':58}" + "".join(f"{m:>14}" for m in months))
    for c in sorted({c for _, c in summary}):
        print(f"{c[:58]:58}" + "".join(f"{summary.get((m, c), 0):>14,}" if not isinstance(summary.get((m, c)), str)
                                       else f"{summary[(m, c)]:>14}" for m in months))


if __name__ == "__main__":
    main()
