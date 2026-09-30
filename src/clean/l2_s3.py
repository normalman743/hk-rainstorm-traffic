"""S3 L2: past-hour rainfall per district, one row per hour and district, without gaps.

    python -m src.clean.l2_s3

Input: data/interim/l1/s3_bulletins/*.parquet and data/interim/l1/s3_rain/*.parquet
(src.clean.s3_parse), every month on disk.
Output: data/interim/l2/s3/rain.parquet, one row per (rain period, district):
    period_start, period_end   the hour HH:45 -> HH:45 the rainfall is for (TIMESTAMP, HKT)
    district                   one of DISTRICTS (the HKO names)
    low, high                  mm (DOUBLE); a single value in the bulletin gives low = high
    l2_rule                    D8 (interpolated), D9 (not listed: 0 mm) or null (as listed)
and data/interim/checks/l2_s3_counts.csv (rule, what, n).

The period of a bulletin: from its rainfall sentence ("Between 6:45 and 7:45 a.m."), dated by
the bulletin's own time (`title`); a bulletin without the sentence (no district had rain) is
for the last HH:45 at least 10 min before the bulletin (checked on the bulletins with the
sentence: see PERIOD_LAG below). Rules (docs/cleaning.md): D9 a district not listed has 0 mm;
D10 one row per (period, district), the bulletins for one period must agree; D8 a single
missing period is the mean of the period before and after, per district.

Raises on: a title or period in another form, a start hour that is not one hour before the
end, a bulletin more than PERIOD_MAX after its period's end, a district not in DISTRICTS,
bulletins for one period that disagree, two or more missing periods in a row (within
MAX_GAP; longer gaps separate the months), and a period without all 18 districts.
"""

from __future__ import annotations

import csv
import re
from datetime import datetime, timedelta

import duckdb
import pandas as pd

from src.clean.l2_s1 import CHECKS_DIR, L2_DIR
from src.clean.s1_parse import L1_DIR

DISTRICTS = ["Central & Western District", "Eastern District", "Islands District", "Kowloon City",
             "Kwai Tsing", "Kwun Tong", "North District", "Sai Kung", "Sha Tin", "Sham Shui Po",
             "Southern District", "Tai Po", "Tsuen Wan", "Tuen Mun", "Wan Chai", "Wong Tai Sin",
             "Yau Tsim Mong", "Yuen Long"]
TITLE = re.compile(r"Bulletin updated at (\d\d:\d\d) HKT (\d\d/\d\d/\d{4})")
PERIOD = re.compile(r"(\d{1,2}):45(?: ([ap])\.m\.)? and (\d{1,2}):45 ([ap])\.m\.")
PERIOD_LAG = timedelta(minutes=10)   # a period ends at least this long before its bulletin
PERIOD_MAX = timedelta(minutes=90)   # ... and at most this long (the 17:00 repeat is 75 min)
MAX_GAP = timedelta(days=7)          # a longer gap between periods separates two months
HOUR = timedelta(hours=1)


def _hour24(h: int, ap: str) -> int:
    return h % 12 + (12 if ap == "p" else 0)


def period_end(period: str, bulletin: datetime, where: str) -> datetime:
    """End of the period named in the rainfall sentence, the last such time before the bulletin."""
    m = PERIOD.fullmatch(period)
    if m is None:
        raise ValueError(f"{where}: period {period!r} in another form")
    end_h = _hour24(int(m[3]), m[4])
    end = bulletin.replace(hour=end_h, minute=45, second=0)
    if end > bulletin:
        end -= timedelta(days=1)
    start_h = (end - HOUR).hour
    if start_h % 12 != int(m[1]) % 12 or (m[2] and _hour24(int(m[1]), m[2]) != start_h):
        raise ValueError(f"{where}: period {period!r} is not one hour")
    return end


def build_rain(bulletins: pd.DataFrame, rain: pd.DataFrame) -> tuple[pd.DataFrame, list[tuple]]:
    """(rain table, counts) from the L1 bulletins and rain rows of every month."""
    counts = [("L1", "bulletins", len(bulletins)), ("L1", "rain rows", len(rain))]
    times = {}
    for b in bulletins.itertuples():
        m = TITLE.fullmatch(b.title)
        if m is None:
            raise ValueError(f"{b.bundle}:{b.index}: title {b.title!r}")
        times[(b.bundle, b.index)] = datetime.strptime(f"{m[2]} {m[1]}", "%d/%m/%Y %H:%M")

    bad = sorted(set(rain.district) - set(DISTRICTS))
    if bad:
        raise ValueError(f"districts not in DISTRICTS: {bad}")
    rain = rain.assign(low=rain.low.astype(float), high=rain.high.fillna(rain.low).astype(float))

    # Period of each bulletin: from its sentence, or by PERIOD_LAG if it has none.
    ends, lags = {}, []
    for (bundle, index), g in rain.groupby(["bundle", "index"]):
        periods = g.period.unique()
        if len(periods) != 1:
            raise ValueError(f"{bundle}:{index}: {len(periods)} periods")
        t = times[(bundle, index)]
        ends[(bundle, index)] = period_end(periods[0], t, f"{bundle}:{index}")
        lags.append(t - ends[(bundle, index)])
    by_lag = lambda t: (t - PERIOD_LAG).replace(minute=45, second=0) - (  # noqa: E731
        HOUR if (t - PERIOD_LAG).minute < 45 else timedelta(0))
    rule_differs = [k for k, e in ends.items() if by_lag(times[k]) != e]
    counts.append(("period", "bulletins with rain whose period differs from the lag rule", len(rule_differs)))
    for k in rule_differs:
        print(f"period differs from the lag rule: {k} bulletin {times[k]} period end {ends[k]}")
    too_late = [(k, e) for k, e in ends.items() if not timedelta(0) < times[k] - e <= PERIOD_MAX]
    if too_late:
        raise ValueError(f"bulletin not 0-{PERIOD_MAX} after its period: {too_late[:10]}")
    for k, t in times.items():
        ends.setdefault(k, by_lag(t))
    counts.append(("period", "bulletins without rain (period by the lag rule)", len(times) - rain.groupby(["bundle", "index"]).ngroups))

    # One set of (district, low, high) per bulletin, then per period (D10).
    listed = {k: frozenset() for k in times}
    for k, g in rain.groupby(["bundle", "index"]):
        listed[k] = frozenset(zip(g.district, g.low, g.high))
    per_period: dict[datetime, set] = {}
    for k, e in ends.items():
        per_period.setdefault(e, set()).add(listed[k])
    conflicts = {e: v for e, v in per_period.items() if len(v) > 1}
    if conflicts:
        raise ValueError(f"D10: bulletins for one period disagree: {list(conflicts.items())[:3]}")
    counts.append(("D10", "periods given by more than one bulletin",
                   sum(1 for e in per_period if list(ends.values()).count(e) > 1)))

    # Periods in time order; one missing period between two is interpolated (D8).
    known = sorted(per_period)
    rows = []
    for e in known:
        values = {d: (lo, hi) for d, lo, hi in next(iter(per_period[e]))}
        for d in DISTRICTS:
            lo, hi = values.get(d, (0.0, 0.0))
            rows.append((e - HOUR, e, d, lo, hi, None if d in values else "D9"))
    table = pd.DataFrame(rows, columns=["period_start", "period_end", "district", "low", "high", "l2_rule"])
    counts.append(("D9", "rows not listed (0 mm)", int((table.l2_rule == "D9").sum())))
    added = []
    for a, b in zip(known, known[1:]):
        gap = b - a
        if gap == HOUR or gap > MAX_GAP:
            continue
        if gap != 2 * HOUR:
            raise ValueError(f"{gap / HOUR - 1:.0f} periods missing in a row after {a}")
        mid = a + HOUR
        pa = table[table.period_end == a].set_index("district")
        pb = table[table.period_end == b].set_index("district")
        for d in DISTRICTS:
            added.append((mid - HOUR, mid, d, (pa.low[d] + pb.low[d]) / 2, (pa.high[d] + pb.high[d]) / 2, "D8"))
        print(f"D8: period ending {mid} interpolated")
    counts.append(("D8", "periods interpolated", len(added) // len(DISTRICTS)))
    table = pd.concat([table, pd.DataFrame(added, columns=table.columns)]).sort_values(["period_end", "district"])
    n = table.groupby("period_end").district.nunique()
    if (n != len(DISTRICTS)).any():
        raise ValueError(f"periods without 18 districts: {n[n != len(DISTRICTS)].head()}")
    counts.append(("L2", "rows out", len(table)))
    return table.reset_index(drop=True), counts


def build() -> None:
    bulletins = duckdb.sql(f"select * from read_parquet('{L1_DIR / 's3_bulletins'}/*.parquet')").df()
    rain = duckdb.sql(f"select * from read_parquet('{L1_DIR / 's3_rain'}/*.parquet')").df()
    table, counts = build_rain(bulletins, rain)
    out = L2_DIR / "s3" / "rain.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    table.to_parquet(out, index=False)
    with (CHECKS_DIR / "l2_s3_counts.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["rule", "what", "n"])
        w.writerows(counts)
    for c in counts:
        print(f"{c[0]:>6} {c[1]}: {c[2]:,}")
    print(f"s3: {out}: {len(table):,} rows, {table.period_end.min()} .. {table.period_end.max()}")


if __name__ == "__main__":
    build()
