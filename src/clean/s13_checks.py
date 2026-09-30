"""Checks on S13 L1: nulls, formats, repeated and conflicting messages, value lists, fetch timing.

    python -m src.clean.s13_checks

Reads data/interim/l1/s13/*.parquet (python -m src.clean.s13_parse) and the manifest (every
fetch time, identical copies included). Changes nothing.

- Versions: the same `ID` in several distinct files (expected: status NEW / UPDATED / CLOSED, or
  a re-fetch). A conflict is the same (ID, ANNOUNCEMENT_DATE) with different other fields.
- Formats: ANNOUNCEMENT_DATE YYYY-MM-DDTHH:MM:SS, ID an integer, LATITUDE / LONGITUDE numbers.
- EN / CN pairs: one of the two empty or absent while the other is not.
- Timing: announcement -> first fetch of the file (minutes); fetches per day and the longest
  time between two fetches (the archive holds one message per fetch, so a message replaced
  within a gap is not in the archive).
- IDs: how many integers between the smallest and largest ID of a month are never seen
  (a fact about the numbers only; whether TD numbers messages consecutively is not known).

Output, in data/interim/checks/:
- s13_summary.csv   month, check, n
- s13_problems.csv  bundle, index, check, detail
- s13_values.csv    column, value, n  (heading, detail, status, district, direction; EN)
"""

from __future__ import annotations

import csv
import re
from collections import Counter, defaultdict
from datetime import datetime

import pyarrow.parquet as pq

from src.clean.manifest import OUT_DIR as MANIFEST_DIR
from src.clean.s1_periods import OUT_DIR as CHECKS_DIR
from src.clean.s13_parse import FIELDS, OUT_DIR as L1_DIR, RESOURCE

DATE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")
NUMBER = re.compile(r"-?\d+(\.\d+)?")
PAIRS = sorted({f[:-3] for f in FIELDS if f.endswith(("_EN", "_CN"))})
LISTED = ["INCIDENT_HEADING_EN", "INCIDENT_DETAIL_EN", "INCIDENT_STATUS_EN", "DISTRICT_EN", "DIRECTION_EN"]


def main() -> None:
    rows = []
    for p in sorted(L1_DIR.glob("*.parquet")):
        rows += pq.read_table(p).to_pylist()
    with (MANIFEST_DIR / f"{RESOURCE}.csv").open() as f:
        members = [r for r in csv.DictReader(f) if r["member"].endswith(f"-{RESOURCE}")]
    first_fetch = {}
    for r in members:
        g = tuple(r["group"].split(":"))
        t = datetime.strptime(r["fetch_time"], "%Y%m%d-%H%M")
        first_fetch[g] = min(first_fetch.get(g, t), t)

    summary: Counter = Counter()
    problems: list[tuple] = []

    def flag(r: dict, check: str, detail: str = "") -> None:
        summary[(r["bundle"][:6], check)] += 1
        problems.append((r["bundle"], r["index"], check, detail))

    per_file = Counter((r["bundle"], r["index"]) for r in rows)
    for (bundle, _), n in per_file.items():
        summary[(bundle[:6], f"files with {n} message(s)")] += 1
    by_id = defaultdict(list)
    values = Counter()
    lags = defaultdict(list)
    for r in rows:
        month = r["bundle"][:6]
        summary[(month, "message rows")] += 1
        for c in FIELDS:
            if r[c] is None:
                summary[(month, f"{c}: absent")] += 1
            elif r[c] == "":
                summary[(month, f"{c}: empty")] += 1
        for pair in PAIRS:
            en, cn = r[f"{pair}_EN"], r[f"{pair}_CN"]
            if bool(en) != bool(cn):
                flag(r, f"{pair}: only one of EN / CN", f"EN={en!r} CN={cn!r}")
        if r["ANNOUNCEMENT_DATE"] is not None and not DATE.fullmatch(r["ANNOUNCEMENT_DATE"]):
            flag(r, "ANNOUNCEMENT_DATE not YYYY-MM-DDTHH:MM:SS", repr(r["ANNOUNCEMENT_DATE"]))
        if r["ID"] is None or not r["ID"].isdigit():
            flag(r, "ID not an integer", repr(r["ID"]))
        for c in ("LATITUDE", "LONGITUDE"):
            if r[c] and not NUMBER.fullmatch(r[c]):
                flag(r, f"{c} not a number", repr(r[c]))
        if bool(r["LATITUDE"]) != bool(r["LONGITUDE"]):
            flag(r, "only one of LATITUDE / LONGITUDE", f"{r['LATITUDE']!r} {r['LONGITUDE']!r}")
        for c in LISTED:
            values[(c, r[c])] += 1
        by_id[r["ID"]].append(r)
        if r["ANNOUNCEMENT_DATE"] and DATE.fullmatch(r["ANNOUNCEMENT_DATE"]):
            a = datetime.strptime(r["ANNOUNCEMENT_DATE"], "%Y-%m-%dT%H:%M:%S")
            lag = (first_fetch[(r["bundle"], str(r["index"]))] - a).total_seconds() / 60
            lags[month].append(lag)
            if lag < 0:
                flag(r, "fetched before the announcement", f"{lag:.0f} min")

    for id_, rs in by_id.items():
        month = min(r["bundle"] for r in rs)[:6]
        summary[(month, "distinct IDs")] += 1
        summary[(month, f"IDs in {min(len(rs), 5)}{'+' if len(rs) >= 5 else ''} distinct files")] += 1
        if len({r["INCIDENT_NUMBER"] for r in rs}) > 1:
            for r in rs:
                flag(r, "ID with >1 INCIDENT_NUMBER", f"ID {id_}")
        if len({(r["bundle"], r["index"]) for r in rs}) < len(rs):
            for r in rs:
                flag(r, "ID twice in one file", f"ID {id_}")
        by_date = defaultdict(set)
        for r in rs:
            by_date[r["ANNOUNCEMENT_DATE"]].add(tuple(r[c] for c in FIELDS))
        for date, versions in by_date.items():
            if len(versions) > 1:
                differ = sorted({c for c in FIELDS for v in versions for w in versions
                                 if v[FIELDS.index(c)] != w[FIELDS.index(c)]})
                for r in rs:
                    if r["ANNOUNCEMENT_DATE"] == date:
                        flag(r, "same ID and ANNOUNCEMENT_DATE, other fields differ",
                             f"ID {id_} {date}: {', '.join(differ)}")
        order = sorted(rs, key=lambda r: (r["ANNOUNCEMENT_DATE"] or "", first_fetch[(r["bundle"], str(r["index"]))]))
        statuses = [r["INCIDENT_STATUS_EN"] for r in order]
        summary[(month, "status sequence " + " > ".join(dict.fromkeys(statuses)))] += 1
    incidents = defaultdict(set)
    for r in rows:
        incidents[r["INCIDENT_NUMBER"]].add(r["ID"])
    for inc, ids in incidents.items():
        summary[("all", f"incidents with {min(len(ids), 5)}{'+' if len(ids) >= 5 else ''} IDs")] += 1

    for month in sorted({r["bundle"][:6] for r in rows}):
        ids = sorted({int(r["ID"]) for r in rows if r["bundle"][:6] == month and r["ID"].isdigit()})
        summary[(month, "ID range: smallest")] = ids[0]
        summary[(month, "ID range: largest")] = ids[-1]
        summary[(month, "ID range: integers not seen")] = ids[-1] - ids[0] + 1 - len(ids)
        xs = sorted(lags[month])
        summary[(month, "announcement -> first fetch, median (min)")] = round(xs[len(xs) // 2])
        summary[(month, "announcement -> first fetch, max (min)")] = round(xs[-1])
        summary[(month, "announcement -> first fetch > 60 min")] = sum(1 for x in xs if x > 60)
    fetches = defaultdict(list)
    for r in members:
        fetches[r["fetch_time"][:8]].append(datetime.strptime(r["fetch_time"], "%Y%m%d-%H%M"))
    for day, ts in sorted(fetches.items()):
        ts.sort()
        month = day[:6]
        summary[(month, "days with fetches")] += 1
        summary[(month, "fetches")] += len(ts)
        gap = max((b - a).total_seconds() / 60 for a, b in zip(ts, ts[1:])) if len(ts) > 1 else 24 * 60
        summary[(month, "longest time between fetches in a day (min)")] = max(
            summary[(month, "longest time between fetches in a day (min)")], round(gap))

    CHECKS_DIR.mkdir(parents=True, exist_ok=True)
    with (CHECKS_DIR / "s13_summary.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["month", "check", "n"])
        w.writerows((m, c, n) for (m, c), n in sorted(summary.items()))
    with (CHECKS_DIR / "s13_problems.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["bundle", "index", "check", "detail"])
        w.writerows(problems)
    with (CHECKS_DIR / "s13_values.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["column", "value", "n"])
        w.writerows((c, v, n) for (c, v), n in sorted(values.items(), key=lambda x: (x[0][0], -x[1])))
    print(f"written to {CHECKS_DIR}: s13_summary.csv, s13_problems.csv, s13_values.csv\n")
    months = sorted({m for m, _ in summary})
    print(f"{'check':60}" + "".join(f"{m:>9}" for m in months))
    for c in sorted({c for _, c in summary}):
        print(f"{c[:60]:60}" + "".join(f"{summary.get((m, c), 0):>9,}" for m in months))
    print("\nproblems by check:", dict(Counter(p[2] for p in problems)))


if __name__ == "__main__":
    main()
