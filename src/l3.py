"""L3: the analysis table, one row per detector and time slot, from the L2 tables.

    python -m src.l3                   # the default table
    python -m src.l3 speed_agg=mean    # a variant (RQ3): any Options field=value

Output: data/interim/l3/<name>.parquet (`default`, or the changed options joined by `__`) and
data/interim/checks/l3_<name>_counts.csv. Columns:
    detector_id, slot (start, HKT), month (YYYYMM), date, slot_of_day (minutes since 00:00),
    day_type (weekday / saturday / sunday_holiday), holiday
    direction (S1), district (S2 District), rain_district (D11), latitude, longitude, road
    n_lanes, periods (30-s periods seen in the slot), coverage (periods / periods possible)
    speed (km/h), flow (vehicles per hour, all lanes), occupancy (%, mean of lane readings)
    interpolated (P6: the slot was missing and is the mean of its neighbours)
    rain (mm in the hour of the slot, P7 / P8), rain_mid, rain_high, rain_max (the highest
        `high` of the 18 districts), rain_lag1 (rain of the hour before), rain_rule (S3 l2_rule)
    warn_level (0 none, 1 Amber, 2 Red, 3 Black), warn_minutes (minutes since the warning
        episode began; 0 without warning), tc_signal (0 none, else the highest TC signal)
    dry (no rain in the district this hour and the hour before, no rainstorm warning, TC
        signal below 8)
    season, base_speed, base_flow, base_occupancy, base_n: median (and count) over the
        detector's dry slots of the same season, day_type and slot_of_day (P10); ratio = speed / base_speed,
        flow_ratio = flow / base_flow

Steps and their options (PROPOSAL.md P1-P10; P9 and P11 are applied by the analysis):
    P1 valid      drop: lane readings with valid = N are left out; keep: kept;
                  drop_block: the whole detector period is left out if any lane is N
    P2 outliers   bounds: a reading with volume > 0 and speed 0 or speed > SPEED_MAX is left
                  out; none; robust_z: bounds, and a reading with volume > 0 whose speed is
                  more than Z_MAX robust z from its lane's median is left out
    P3 stuck      drop: a lane slot whose readings are all identical, with occupancy or
                  volume above 0, and the same in the slot before or after (>= 2 slots) is
                  left out; keep
    P4 speed_agg  vol_weighted: sum(speed x volume) / sum(volume) over the lane readings;
                  mean: mean of every lane reading (with the placeholder speeds of volume 0);
                  slowest: the lowest of the lanes' volume-weighted speeds
    P5 minutes    slot length: 15; 5; 60
    P6 gaps       interp: a run of 1-2 missing slots between two present ones is the linear
                  interpolation of its neighbours, flagged; none
    P7 rain_value mid: (low + high) / 2 of the detector's district; high; max: the highest
                  `high` of all districts
    P8 rain_lag   0: the hour the slot is in; 1: the hour before
    P10 baseline  season: per detector x season x day_type x slot_of_day, the seasons being
                  2024-05 and 2025-07 + 2025-08 (both school summer holidays; a month alone has
                  only 4-5 Saturdays); month: per month; all: the three months together

Rows are left out (counted): a slot in which no lane has a vehicle (vol_weighted and slowest:
no speed), a slot with no rain period (after 22:45 on a month's last day: that bulletin is
in the next month's files),
and a slot without BASE_MIN dry slots behind its baseline.
"""

from __future__ import annotations

import csv
import dataclasses
import sys
import time as clock
from dataclasses import dataclass

import duckdb
import pandas as pd

from src.clean.l2_s1 import CHECKS_DIR, L2_DIR
from src.config import INTERIM_DIR, ROOT

L3_DIR = INTERIM_DIR / "l3"
MONTHS = ["202405", "202507", "202508"]
SPEED_MAX = 130
Z_MAX = 5
BASE_MIN = 3
TC_MAX = 8  # a TC signal from here up keeps a slot out of the baseline (and, P11, out of the analysis)
MAX_GAP_SLOTS = 2


@dataclass(frozen=True)
class Options:
    valid: str = "drop"
    outliers: str = "bounds"
    stuck: str = "drop"
    speed_agg: str = "vol_weighted"
    minutes: int = 15
    gaps: str = "interp"
    rain_value: str = "mid"
    rain_lag: int = 0
    baseline: str = "season"

    def name(self) -> str:
        changed = [f"{f.name}={getattr(self, f.name)}" for f in dataclasses.fields(self)
                   if getattr(self, f.name) != f.default]
        return "__".join(changed) or "default"


CHOICES = {"valid": ("drop", "keep", "drop_block"), "outliers": ("bounds", "none", "robust_z"),
           "stuck": ("drop", "keep"), "speed_agg": ("vol_weighted", "mean", "slowest"),
           "minutes": (15, 5, 60), "gaps": ("interp", "none"), "rain_value": ("mid", "high", "max"),
           "rain_lag": (0, 1), "baseline": ("season", "month", "all")}


def _check(o: Options) -> None:
    for f, allowed in CHOICES.items():
        if getattr(o, f) not in allowed:
            raise ValueError(f"{f}={getattr(o, f)!r}, not one of {allowed}")


def _readings(con: duckdb.DuckDBPyConnection, o: Options, counts: list) -> None:
    """View `r`: the L2 S1 lane readings that P1 and P2 keep."""
    con.sql(f"create or replace view l2 as select * from read_parquet('{L2_DIR / 's1'}/*.parquet')")
    where = []
    if o.valid == "drop":
        where.append("valid")
    if o.outliers in ("bounds", "robust_z"):
        where.append(f"not (volume > 0 and (speed = 0 or speed > {SPEED_MAX}))")
    src = "l2"
    if o.valid == "drop_block":
        con.sql("create or replace table bad_blocks as select distinct detector_id, time from l2 where not valid")
        src = "(select * from l2 anti join bad_blocks using (detector_id, time))"
    if o.outliers == "robust_z":
        con.sql(f"""create or replace table lane_med as
            select detector_id, lane_id, approx_quantile(speed, 0.5) as med
            from l2 where volume > 0 group by all""")
        con.sql(f"""create or replace table lane_mad as
            select detector_id, lane_id, any_value(m.med) as med,
                   approx_quantile(abs(speed - m.med), 0.5) * 1.4826 as mad
            from l2 join lane_med m using (detector_id, lane_id) where volume > 0 group by all""")
        src = f"""(select l.* from {src} l join lane_mad z using (detector_id, lane_id)
                   where l.volume = 0 or z.mad = 0 or abs(l.speed - z.med) / z.mad <= {Z_MAX})"""
    con.sql(f"create or replace view r as select * from {src} "
            + ("where " + " and ".join(where) if where else ""))
    n_all = con.sql("select count(*) from l2").fetchone()[0]
    n_r = con.sql("select count(*) from r").fetchone()[0]
    n_invalid = con.sql("select count(*) from l2 where not valid").fetchone()[0]
    n_bounds = con.sql(f"select count(*) from l2 where volume > 0 and (speed = 0 or speed > {SPEED_MAX})").fetchone()[0]
    counts += [("L2", "lane readings", n_all), ("P1", "lane readings with valid = N", n_invalid),
               ("P2", f"lane readings with volume > 0 and speed 0 or > {SPEED_MAX}", n_bounds),
               ("P1+P2", "lane readings left out", n_all - n_r)]


def _lanes(con: duckdb.DuckDBPyConnection, o: Options, counts: list) -> None:
    """Table `lane`: one row per detector, lane and slot; P3."""
    con.sql(f"""create or replace table lane as
        select detector_id, lane_id, time_bucket(interval '{o.minutes} minutes', time) as slot,
               any_value(direction) as direction, count(*) as n,
               sum(volume) as vol, sum(speed * volume) as sv, sum(speed) as s_all,
               sum(occupancy) as occ,
               min(speed) = max(speed) and min(volume) = max(volume) and min(occupancy) = max(occupancy)
                   and count(*) > 1 and (max(volume) > 0 or max(occupancy) > 0) as constant,
               min(speed) as s0, min(volume) as v0, min(occupancy) as o0
        from r group by detector_id, lane_id, slot""")
    counts.append(("lane", "lane slots", con.sql("select count(*) from lane").fetchone()[0]))
    con.sql(f"""create or replace table stuck as
        select detector_id, lane_id, slot from (
            select *, lag(constant) over w and lag(s0) over w = s0 and lag(v0) over w = v0
                          and lag(o0) over w = o0
                          and lag(slot) over w = slot - interval '{o.minutes} minutes' as same_prev,
                      lead(constant) over w and lead(s0) over w = s0 and lead(v0) over w = v0
                          and lead(o0) over w = o0
                          and lead(slot) over w = slot + interval '{o.minutes} minutes' as same_next
            from lane window w as (partition by detector_id, lane_id order by slot))
        where constant and (coalesce(same_prev, false) or coalesce(same_next, false))""")
    counts.append(("P3", "lane slots stuck (identical readings >= 2 slots)",
                   con.sql("select count(*) from stuck").fetchone()[0]))
    if o.stuck == "drop":
        con.sql("create or replace table lane as select * from lane anti join stuck using (detector_id, lane_id, slot)")


def _detectors(con: duckdb.DuckDBPyConnection, o: Options, counts: list) -> None:
    """Table `det`: one row per detector and slot; P4."""
    speed = {"vol_weighted": "sum(sv) / nullif(sum(vol), 0)",
             "mean": "sum(s_all) / sum(n)",
             "slowest": "min(sv / nullif(vol, 0))"}[o.speed_agg]
    con.sql(f"""create or replace table det as
        select detector_id, slot, any_value(direction) as direction, count(*) as n_lanes,
               max(n) as periods, max(n) / {o.minutes * 2} as coverage,
               {speed} as speed,
               sum(vol / n) * 120 as flow,
               sum(occ) / sum(n) as occupancy
        from lane group by detector_id, slot""")
    counts.append(("P4", "detector slots", con.sql("select count(*) from det").fetchone()[0]))
    counts.append(("P4", "detector slots left out: no vehicle, so no speed",
                   con.sql("select count(*) from det where speed is null").fetchone()[0]))
    con.sql("delete from det where speed is null")


def _gaps(con: duckdb.DuckDBPyConnection, o: Options, counts: list) -> None:
    """P6: 1-2 missing slots between two present slots of a detector, interpolated."""
    con.sql("alter table det add column interpolated boolean default false")
    if o.gaps == "none":
        return
    step = f"interval '{o.minutes} minutes'"
    con.sql(f"""insert into det by name
        select detector_id, direction, n_lanes, 0 as periods, 0.0 as coverage,
               slot + k * {step} as slot,
               speed + (next_speed - speed) * k / gap as speed,
               flow + (next_flow - flow) * k / gap as flow,
               occupancy + (next_occ - occupancy) * k / gap as occupancy,
               true as interpolated
        from (select *, lead(slot) over w as next_slot, lead(speed) over w as next_speed,
                     lead(flow) over w as next_flow, lead(occupancy) over w as next_occ,
                     cast(epoch(lead(slot) over w - slot) / {o.minutes * 60} as int) as gap
              from det window w as (partition by detector_id order by slot)) x,
             range(1, {MAX_GAP_SLOTS + 1}) g(k)
        where gap between 2 and {MAX_GAP_SLOTS + 1} and k < gap""")
    counts.append(("P6", "detector slots interpolated",
                   con.sql("select count(*) from det where interpolated").fetchone()[0]))


def _month_edge(t) -> bool:
    """In the first hour of a month, or after 22:45 on its last day: the bulletin for the
    period 22:45-23:45 comes out after midnight, in the next month's files."""
    return (t.day == 1 and t.hour == 0) or ((t + pd.Timedelta(hours=1, minutes=15)).day == 1
                                            and (t.hour, t.minute) >= (22, 45))


def _episodes(s4: pd.DataFrame) -> pd.DataFrame:
    """Rainstorm warning episodes: signals that follow on without a break (an upgrade or a
    downgrade ends one signal at the minute the next begins) are one episode."""
    s4 = s4.sort_values("start").reset_index(drop=True)
    episode, starts, last_end = [], [], None
    for r in s4.itertuples():
        if last_end is None or r.start > last_end:
            starts.append(r.start)
        episode.append(len(starts) - 1)
        last_end = r.end if last_end is None or r.start > last_end else max(last_end, r.end)
    return s4.assign(episode=episode, episode_start=[starts[e] for e in episode])


def _context(con: duckdb.DuckDBPyConnection, o: Options, counts: list) -> None:
    """Joins S2, S3, S4, S5, S6 onto `det`: table `ctx`."""
    months = f"strftime(slot, '%Y%m') not in {tuple(MONTHS)}"
    out = con.sql(f"select count(*) from det where {months}").fetchone()[0]
    counts.append(("L3", "slots left out: outside the three months (the first files of a month hold "
                         "the last minutes of the day before)", out))
    con.sql(f"delete from det where {months}")
    s4 = _episodes(con.sql(f"select * from read_parquet('{L2_DIR / 's4' / 'rainstorm.parquet'}')").df())
    con.register("s4_df", s4)
    con.sql("create or replace table s4 as select * from s4_df")
    step = f"interval '{o.minutes} minutes'"
    con.sql(f"""create or replace table s2 as select AID_ID_Number as detector_id, District as district,
               rain_district, Latitude as latitude, Longitude as longitude, Road_EN as road
        from read_parquet('{L2_DIR / 's2' / 'detectors.parquet'}')""")
    missing = con.sql("select distinct detector_id from det anti join s2 using (detector_id)").fetchall()
    if missing:
        raise ValueError(f"S1 detectors not in S2: {missing}")
    con.sql(f"""create or replace table rain as
        select *, (low + high) / 2 as mid, max(high) over (partition by period_start) as max_high
        from read_parquet('{L2_DIR / 's3' / 'rain.parquet'}')""")
    rain_value = {"mid": "mid", "high": "high", "max": "max_high"}[o.rain_value]
    # The hour of a slot: the rain period it starts in (periods run HH:45 -> HH:45).
    con.sql(f"""create or replace table ctx as
        select d.*, s2.district, s2.rain_district, s2.latitude, s2.longitude, s2.road,
               r.mid as rain_mid, r.high as rain_high, r.max_high as rain_max, r.l2_rule as rain_rule,
               r.{rain_value} as rain_now, p.{rain_value} as rain_lag1, p.high as rain_high_lag1,
               r.period_start as rain_period
        from det d join s2 using (detector_id)
        left join rain r on r.district = s2.rain_district
             and d.slot >= r.period_start and d.slot < r.period_end
        left join rain p on p.district = s2.rain_district and p.period_end = r.period_start""")
    no_rain = con.sql("""select min(slot), max(slot), count(*), count(distinct detector_id)
                         from ctx where rain_now is null""").fetchone()
    if no_rain[2]:
        edges = con.sql("select distinct slot from ctx where rain_now is null").fetchall()
        bad = [h for (h,) in edges if not _month_edge(h)]
        if bad:
            raise ValueError(f"slots without a rain period outside the first / last hour of a month: {bad[:10]}")
    counts.append(("P7", "slots left out: no rain period (first hour / after 22:45 on the last day of a month)",
                   no_rain[2]))
    con.sql("delete from ctx where rain_now is null")
    lag_missing = con.sql("select count(*) from ctx where rain_lag1 is null").fetchone()[0]
    if lag_missing:
        edges = con.sql("select distinct rain_period from ctx where rain_lag1 is null").fetchall()
        bad = [h for (h,) in edges if not (h.day == 1 and h.hour == 0 or (h + pd.Timedelta(hours=1)).day == 1)]
        if bad:
            raise ValueError(f"rain hour without the hour before, not at a month's start: {bad[:10]}")
    counts.append(("P8", "slots whose hour before has no rain period (first hour of a month): "
                         "rain_lag1 = the hour's own rain", lag_missing))
    con.sql("update ctx set rain_lag1 = rain_now, rain_high_lag1 = rain_high where rain_lag1 is null")
    con.sql(f"alter table ctx add column rain double")
    con.sql(f"update ctx set rain = {'rain_now' if o.rain_lag == 0 else 'rain_lag1'}")

    # Warning and TC signal per slot: the highest signal in force at any time in the slot.
    con.sql(f"""create or replace table slots as
        select s.slot, coalesce(max(w.level), 0) as warn_level,
               coalesce(max(epoch(s.slot - w.episode_start)) / 60, 0) as warn_minutes
        from (select distinct slot from ctx) s
        left join s4 w on w.start < s.slot + {step} and w."end" > s.slot group by s.slot""")
    con.sql(f"""create or replace table slots as
        select s.*, coalesce(max(t.signal), 0) as tc_signal from slots s
        left join read_parquet('{L2_DIR / 's5' / 'tc.parquet'}') t
             on t.start < s.slot + {step} and t."end" > s.slot group by all""")
    con.sql("create or replace table ctx as select * from ctx join slots using (slot)")
    con.sql(f"""create or replace table ctx as
        select c.*, strftime(c.slot, '%Y%m') as month, cast(c.slot as date) as date,
               hour(c.slot) * 60 + minute(c.slot) as slot_of_day,
               h.date is not null as holiday,
               case when h.date is not null or dayofweek(c.slot) = 0 then 'sunday_holiday'
                    when dayofweek(c.slot) = 6 then 'saturday' else 'weekday' end as day_type
        from ctx c left join read_parquet('{L2_DIR / 's6' / 'holidays.parquet'}') h
             on h.date = cast(c.slot as date)""")
    con.sql("""alter table ctx add column dry boolean""")
    con.sql(f"update ctx set dry = rain_high = 0 and rain_high_lag1 = 0 and warn_level = 0 and tc_signal < {TC_MAX}")


def _baseline(con: duckdb.DuckDBPyConnection, o: Options, counts: list) -> None:
    con.sql("alter table ctx add column season varchar")
    con.sql("update ctx set season = case when month = '202405' then '2024-05' else '2025-07/08' end")
    by = "detector_id, day_type, slot_of_day" + {"season": ", season", "month": ", month", "all": ""}[o.baseline]
    con.sql(f"""create or replace table base as
        select {by}, median(speed) as base_speed, median(flow) as base_flow,
               median(occupancy) as base_occupancy, count(*) as base_n
        from ctx where dry and not interpolated group by {by}""")
    con.sql(f"""create or replace table l3 as
        select c.*, b.base_speed, b.base_flow, b.base_occupancy, b.base_n,
               c.speed / nullif(b.base_speed, 0) as ratio, c.flow / nullif(b.base_flow, 0) as flow_ratio
        from ctx c join base b using ({by}) where b.base_n >= {BASE_MIN}""")
    n_ctx = con.sql("select count(*) from ctx").fetchone()[0]
    n_l3 = con.sql("select count(*) from l3").fetchone()[0]
    counts.append(("P10", f"slots left out: fewer than {BASE_MIN} dry slots behind the baseline", n_ctx - n_l3))
    con.sql("update l3 set flow_ratio = 1 where flow_ratio is null and flow = 0")
    nulls = con.sql("select count(*) from l3 where flow_ratio is null or ratio is null").fetchone()[0]
    counts.append(("P10", "left out: base_speed 0, or base_flow 0 with flow > 0", nulls))
    con.sql("delete from l3 where flow_ratio is null or ratio is null")


def build(o: Options) -> None:
    _check(o)
    start = clock.time()
    tmp = ROOT / ".tmp"
    tmp.mkdir(exist_ok=True)
    db = tmp / f"l3_{o.name()}.duckdb"
    con = duckdb.connect(str(db))
    con.sql(f"set temp_directory = '{tmp}'")
    con.sql("set preserve_insertion_order = false")
    con.sql("set enable_progress_bar = false")
    counts: list = []
    _readings(con, o, counts)
    _lanes(con, o, counts)
    _detectors(con, o, counts)
    _gaps(con, o, counts)
    _context(con, o, counts)
    _baseline(con, o, counts)
    cols = ["detector_id", "slot", "month", "date", "slot_of_day", "day_type", "holiday", "direction",
            "district", "rain_district", "latitude", "longitude", "road", "n_lanes", "periods", "coverage",
            "speed", "flow", "occupancy", "interpolated", "rain", "rain_mid", "rain_high", "rain_max",
            "rain_lag1", "rain_rule", "warn_level", "warn_minutes", "tc_signal", "dry", "base_speed",
            "base_flow", "base_occupancy", "base_n", "season", "ratio", "flow_ratio"]
    nulls = con.sql("select " + ", ".join(f"count(*) filter (where {c} is null) as {c}" for c in cols
                                          if c != "rain_rule") + " from l3").df().iloc[0]
    if nulls.any():
        raise ValueError(f"null left in L3: {nulls[nulls > 0].to_dict()}")
    n = con.sql("select count(*) from l3").fetchone()[0]
    counts.append(("L3", "rows", n))
    L3_DIR.mkdir(parents=True, exist_ok=True)
    con.sql(f"copy (select {', '.join(cols)} from l3 order by detector_id, slot) "
            f"to '{L3_DIR / (o.name() + '.parquet')}' (format parquet, compression zstd)")
    con.close()
    db.unlink()
    with (CHECKS_DIR / f"l3_{o.name()}_counts.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["step", "what", "n"])
        w.writerows(counts)
    for c in counts:
        print(f"{o.name()} {c[0]:>5} {c[1]}: {c[2]:,}")
    print(f"{o.name()}: {n:,} rows in {clock.time() - start:.0f} s", flush=True)


def options(args: list[str]) -> Options:
    kw = {}
    for a in args:
        k, v = a.split("=")
        kw[k] = int(v) if isinstance(getattr(Options, k), int) else v
    return Options(**kw)


if __name__ == "__main__":
    build(options(sys.argv[1:]))
