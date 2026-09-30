"""Checks on S3 L1: nulls, times, missing hours, repeated bulletins, rainfall rows.

    python -m src.clean.s3_checks

Reads data/interim/l1/s3_bulletins/*.parquet, s3_rain/*.parquet (python -m src.clean.s3_parse)
and the manifest (fetch times). Changes nothing. Times are read from the text only here,
to compare them; L1 keeps the text.

- Bulletin time T: from `title` ("Bulletin updated at HH:MM HKT DD/MM/YYYY"). Compared with
  `pubDate` (GMT, + 8 h), with the time in `guid` (…/CurrentWeather/YYYYMMDDHHMMSS) and with
  the fetch time of the file (lag = fetch - T).
- Missing hours: per date of T, the hours 0..23 without a bulletin.
- Rainfall period "H:MM [a.m.|p.m.] and H:MM a.m.|p.m.": the end E is taken as the latest
  time at or before T with that clock time; report T - E and the period length.

Output, in data/interim/checks/:
- s3_summary.csv   month, check, n
- s3_problems.csv  bundle, index, check, detail: every bulletin or rain row a check flags
- s3_districts.csv district, n_rows, n_months (as written)
"""

from __future__ import annotations

import csv
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime

import pyarrow.parquet as pq

from src.clean.manifest import OUT_DIR as MANIFEST_DIR
from src.clean.s1_periods import OUT_DIR as CHECKS_DIR
from src.clean.s3_parse import BULLETIN_COLUMNS, OUT_BULLETINS, OUT_RAIN, RAIN_COLUMNS, RESOURCE

TITLE = re.compile(r"Bulletin updated at (\d{2}):(\d{2}) HKT (\d{2})/(\d{2})/(\d{4})")
GUID = re.compile(r"\s*http://rss\.weather\.gov\.hk/rss/CurrentWeather/(\d{14})\s*")
PERIOD = re.compile(r"(\d{1,2}):(\d{2})(?: ([ap])\.m\.)? and (\d{1,2}):(\d{2}) ([ap])\.m\.")


def _read(folder) -> list[dict]:
    rows = []
    for p in sorted(folder.glob("*.parquet")):
        rows += pq.read_table(p).to_pylist()
    return rows


def _clock(h: int, m: int, ampm: str) -> tuple[int, int] | None:
    """24-hour (h, m) of "h:mm a.m./p.m."; None for an hour that is not 0..12."""
    if not 0 <= h <= 12:
        return None
    if ampm == "a":
        return (0 if h == 12 else h, m)
    return (h if h == 12 else h + 12, m)


def main() -> None:
    bulletins = _read(OUT_BULLETINS)
    rain = _read(OUT_RAIN)
    with (MANIFEST_DIR / f"{RESOURCE}.csv").open() as f:
        fetch = {(r["bundle"], int(r["index"])): r["fetch_time"] for r in csv.DictReader(f)}

    summary: Counter = Counter()
    problems: list[tuple] = []

    def flag(b: dict, check: str, detail: str = "") -> None:
        summary[(b["bundle"][:6], check)] += 1
        problems.append((b["bundle"], b["index"], check, detail))

    # ---- bulletins
    t_of: dict[tuple, datetime] = {}
    by_guid, by_title, hours = defaultdict(set), defaultdict(set), defaultdict(Counter)
    lags = defaultdict(list)
    for b in bulletins:
        month = b["bundle"][:6]
        summary[(month, "bulletins")] += 1
        for c in BULLETIN_COLUMNS[2:]:
            if b[c] is None:
                flag(b, f"{c}: null")
            elif b[c] == "":
                flag(b, f"{c}: empty")
        m = TITLE.fullmatch(b["title"] or "")
        if not m:
            flag(b, "title not 'Bulletin updated at HH:MM HKT DD/MM/YYYY'", repr(b["title"]))
            continue
        hh, mm, dd, mo, yyyy = map(int, m.groups())
        t = datetime(yyyy, mo, dd, hh, mm)
        t_of[(b["bundle"], b["index"])] = t
        hours[t.date()][hh] += 1
        summary[(month, f"category {b['category']!r}")] += 1
        summary[(month, f"update minute :{mm:02d}")] += 1
        try:
            pub = parsedate_to_datetime(b["pubDate"])
        except (TypeError, ValueError) as e:
            flag(b, "pubDate not a date", f"{b['pubDate']!r} {e}")
        else:
            if pub.utcoffset() != timedelta(0) or pub.replace(tzinfo=None) + timedelta(hours=8) != t:
                flag(b, "pubDate + 8 h != title time", f"{b['pubDate']} vs {b['title']}")
        g = GUID.fullmatch(b["guid"] or "")
        if not g:
            flag(b, "guid not …/CurrentWeather/YYYYMMDDHHMMSS", repr(b["guid"]))
        else:
            by_guid[g.group(1)].add((b["bundle"], b["index"], b["description"]))
            if datetime.strptime(g.group(1), "%Y%m%d%H%M%S") != t:
                flag(b, "guid time != title time", f"{g.group(1)} vs {b['title']}")
        by_title[b["title"]].add((b["bundle"], b["index"], b["description"]))
        lag = (datetime.strptime(fetch[(b["bundle"], b["index"])], "%Y%m%d-%H%M") - t).total_seconds() / 60
        lags[month].append(lag)
        if not 0 <= lag <= 60:
            flag(b, "fetch - update time not in 0..60 min", f"{lag:.0f} min")

    for name, groups in (("guid", by_guid), ("title", by_title)):
        for key, members in groups.items():
            if len(members) > 1:
                first = min(members)
                month = first[0][:6]
                summary[(month, f"{name} in >1 file")] += 1
                if len({d for *_, d in members}) > 1:
                    summary[(month, f"{name} in >1 file, descriptions differ")] += 1
                for bundle, index, _ in sorted(members):
                    problems.append((bundle, index, f"{name} in >1 file", key))

    months = sorted({b["bundle"][:6] for b in bulletins})
    for day, c in sorted(hours.items()):
        month = f"{day:%Y%m}"
        if month not in months:  # e.g. the last bulletins of the previous month, fetched after midnight
            summary[(month, "bulletins dated outside the bundle month")] += sum(c.values())
            continue
        missing = [h for h in range(24) if h not in c]
        summary[(month, "days")] += 1
        summary[(month, "hours without bulletin")] += len(missing)
        summary[(month, "hours with >1 bulletin")] += sum(1 for n in c.values() if n > 1)
        if missing:
            problems.append(("", "", "hours without bulletin", f"{day} {missing}"))
    for month, xs in lags.items():
        xs.sort()
        summary[(month, "fetch lag min (minutes)")] = round(xs[0])
        summary[(month, "fetch lag median")] = round(xs[len(xs) // 2])
        summary[(month, "fetch lag max")] = round(xs[-1])

    # ---- rain rows
    districts = defaultdict(lambda: [0, set()])
    per_bulletin = defaultdict(Counter)
    periods = defaultdict(set)
    values = defaultdict(set)  # bulletin -> {(district, low, high)}
    for r in rain:
        month = r["bundle"][:6]
        summary[(month, "rain rows")] += 1
        for c in RAIN_COLUMNS[2:]:
            if r[c] is None:
                summary[(month, f"rain {c}: null")] += 1
            elif r[c] == "":
                flag(r, f"rain {c}: empty")
        districts[r["district"]][0] += 1
        districts[r["district"]][1].add(month)
        per_bulletin[(r["bundle"], r["index"])][r["district"]] += 1
        periods[(r["bundle"], r["index"])].add(r["period"])
        values[(r["bundle"], r["index"])].add((r["district"], r["low"], r["high"]))
        if r["high"] is not None and int(r["low"]) > int(r["high"]):
            flag(r, "rain low > high", f"{r['district']} {r['low']} to {r['high']}")
    by_end = defaultdict(list)  # period end (datetime) -> bulletins reporting that period
    for key, c in per_bulletin.items():
        month = key[0][:6]
        summary[(month, "bulletins with rain")] += 1
        summary[(month, f"districts per bulletin: {len(c):2d}")] += 1
        for d, n in c.items():
            if n > 1:
                flag({"bundle": key[0], "index": key[1]}, "district twice in one bulletin", d)
        (period,) = periods[key]  # one sentence per bulletin (s3_parse raises otherwise)
        b = {"bundle": key[0], "index": key[1]}
        m = PERIOD.fullmatch(period)
        if not m:
            flag(b, "rain period not 'H:MM [a.m.] and H:MM a.m.'", repr(period))
            continue
        h1, m1, ap1, h2, m2, ap2 = m.groups()
        end = _clock(int(h2), int(m2), ap2)
        start = _clock(int(h1), int(m1), ap1 or ap2)
        if end is None or start is None:
            flag(b, "rain period hour not 0..12", period)
            continue
        if (m1, m2) != ("45", "45"):
            flag(b, "rain period not HH:45 to HH:45", period)
        length = ((end[0] * 60 + end[1]) - (start[0] * 60 + start[1])) % (24 * 60)
        if length != 60:
            flag(b, "rain period not 60 min", period)
        t = t_of.get(key)
        if t is not None:
            e = t.replace(hour=end[0], minute=end[1])
            if e > t:
                e -= timedelta(days=1)
            gap = (t - e).total_seconds() / 60
            summary[(key[0][:6], f"update - period end: {int(gap // 10 * 10):3d}..{int(gap // 10 * 10 + 9):3d} min")] += 1
            by_end[e].append(key)
    for e, keys in by_end.items():
        if len(keys) > 1:
            month = min(keys)[0][:6]
            same = len({frozenset(values[k]) for k in keys}) == 1
            summary[(month, "rain period in >1 bulletin" + ("" if same else ", values differ"))] += 1
            for k in sorted(keys):
                problems.append((*k, "rain period in >1 bulletin" + ("" if same else ", values differ"),
                                 f"period ending {e:%Y-%m-%d %H:%M}"))

    CHECKS_DIR.mkdir(parents=True, exist_ok=True)
    with (CHECKS_DIR / "s3_summary.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["month", "check", "n"])
        w.writerows((m, c, n) for (m, c), n in sorted(summary.items()))
    with (CHECKS_DIR / "s3_problems.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["bundle", "index", "check", "detail"])
        w.writerows(problems)
    with (CHECKS_DIR / "s3_districts.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["district", "n_rows", "n_months"])
        w.writerows(sorted((d, n, len(ms)) for d, (n, ms) in districts.items()))
    print(f"written to {CHECKS_DIR}: s3_summary.csv, s3_problems.csv, s3_districts.csv\n")
    all_months = sorted({m for m, _ in summary})
    checks = sorted({c for _, c in summary})
    print(f"{'check':52}" + "".join(f"{m:>9}" for m in all_months))
    for c in checks:
        print(f"{c:52}" + "".join(f"{summary.get((m, c), 0):>9,}" for m in all_months))
    print(f"\n{len(districts)} districts:", ", ".join(f"{d} ({n})" for d, (n, _) in sorted(districts.items())))


if __name__ == "__main__":
    main()
