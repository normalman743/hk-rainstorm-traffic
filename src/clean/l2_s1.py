"""S1 L2: the detector readings of one month, typed and cleaned by the rules of docs/cleaning.md.

    python -m src.clean.l2_s1 202405 202507 202508

Input: data/interim/l1/s1/<YYYYMM>.parquet (src.clean.s1_parse) and the S1 manifest
(data/interim/manifest/rawSpeedVol-all.xml.csv) for the fetch time of each file.
Output: data/interim/l2/s1/<YYYYMM>.parquet, one row per lane and 30-s period:
    time           start of the period (TIMESTAMP, HKT), after D6
    detector_id
    direction      trimmed (D3); filled for the four detectors of D16
    lane_id        unique within a detector and period (D4 numbers repeated `Middle Lane`s)
    speed, volume, occupancy, sd    DOUBLE (volume and occupancy are whole numbers except
                   in the rows of D5 and D13)
    valid          BOOLEAN (`Y` = true)
    l2_rule        the rules that changed or made this row, comma-separated (D5, D13, D16,
                   D21); null if none did
    bundle, index  the L1 file the row comes from (for D5 / D13 rows: the block's first file)
and data/interim/checks/l2_s1_counts.csv (month, rule, what, n) plus
data/interim/checks/l2_s1_dropped.csv (month, rule, detector_id, time, n_lanes): the blocks
that D12 and D14 drop.

Rules (docs/cleaning.md): D3 trim `direction`; D4 number repeated `Middle Lane`s in file order;
D5 average the one block that lists Fast and Slow twice; D6 the 00:00:00 and 00:00:30 periods
carry the previous day's date, so one day is added; D12 drop TDS90026's 3-lane blocks of
2025; D13 estimate TDS90036's missing Slow Lane; D14 drop single blocks with lanes missing;
D16 fill the missing `direction` of four detectors from their other S1 readings; D21
`occupancy = -1` (only ever with `volume = 0`) becomes 0. D7 needs nothing here (the truncated
files are not in L1).

Raises on (each with the offending rows): a `period_to` that is not `period_from` + 30 s, a
`valid` other than Y / N, a value that does not cast, a period that is not 0–60 min before
its file's fetch time after D6, a lane listed twice other than by D4 / D5, the D5 block in
another form, `occupancy` < 0 other than -1 with volume 0, a detector whose lanes differ
from its usual list in a way no rule covers, a D13 hour without a ratio, a D16 detector
without exactly one direction, a null left in any column but `l2_rule`, and a (detector,
time, lane) twice.
"""

from __future__ import annotations

import argparse
import csv
import time as clock

import duckdb

from src.clean.manifest import OUT_DIR as MANIFEST_DIR
from src.clean.s1_parse import L1_DIR
from src.config import INTERIM_DIR, ROOT

L2_DIR = INTERIM_DIR / "l2"
CHECKS_DIR = INTERIM_DIR / "checks"
MANIFEST = MANIFEST_DIR / "rawSpeedVol-all.xml.csv"

D5_KEY = ("AID02215", "2024-05-30 08:25:00")
D5_LANES = "Fast Lane | Fast Lane | Slow Lane | Slow Lane"
D12_DETECTOR = "TDS90026"
D13_DETECTOR = "TDS90036"
D13_PARTIAL = "Fast Lane | Middle Lane 1 | Middle Lane 2"
D13_FULL = D13_PARTIAL + " | Slow Lane"
VALUES = ["speed", "volume", "occupancy", "sd"]


def _raise_if(con: duckdb.DuckDBPyConnection, sql: str, what: str, limit: int = 20) -> None:
    """Raise with up to `limit` rows of `sql` if it returns any."""
    rows = con.sql(f"select * from ({sql}) limit {limit}").fetchall()
    if rows:
        n = con.sql(f"select count(*) from ({sql})").fetchone()[0]
        cols = con.sql(f"select * from ({sql}) limit 0").columns
        raise ValueError(f"{what}: {n} rows; first {len(rows)} ({', '.join(cols)}):\n"
                         + "\n".join(map(str, rows)))


def _by_day(con: duckdb.DuckDBPyConnection, name: str, sql: str) -> None:
    """Table `name` from `sql` run on one day of `t` at a time (`{day}` in `sql` is the day
    filter). For aggregates DuckDB cannot spill to disk (ordered string_agg, count distinct):
    on a whole month they run out of memory. A block never spans two days."""
    days = [d for (d,) in con.sql("select distinct cast(time as date) from t order by 1").fetchall()]
    for i, d in enumerate(days):
        q = sql.format(day=f"cast(time as date) = date '{d}'")
        con.sql(f"create or replace table {name} as {q}" if i == 0 else f"insert into {name} {q}")


def clean(con: duckdb.DuckDBPyConnection, month: str) -> list[tuple[str, str, int]]:
    """Build table `l2` from view `l1` (one month of L1 rows), view `l1_all` (every L1 month,
    for D16) and view `fetches` (bundle, index, fetch time). Returns (rule, what, n) counts."""
    counts: list[tuple[str, str, int]] = []

    def count(rule: str, what: str, sql: str) -> None:
        counts.append((rule, what, con.sql(f"select count(*) from ({sql})").fetchone()[0]))

    count("L1", "rows in", "select * from l1")
    _raise_if(con, """select * from l1 where strptime(period_to, '%H:%M:%S')
        <> strptime(period_from, '%H:%M:%S') + interval 30 second
        and not (period_from = '23:59:30' and period_to = '00:00:00')""",
              "period_to is not period_from + 30 s")
    _raise_if(con, "select * from l1 where valid is null or valid not in ('Y', 'N')", "valid not Y / N")
    _raise_if(con, "select * from l1 where cast(occupancy as int) < 0 and not "
                   "(occupancy = '-1' and volume = '0')", "negative occupancy other than -1 with volume 0")

    # Typed rows; D6 (re-date), D3 (trim), D21 (occupancy -1 -> 0). Casts are strict: a value
    # that does not cast raises here.
    con.sql(f"""create or replace table t as
        select bundle, index,
               cast(date as date) + (period_from in ('00:00:00', '00:00:30'))::int
                   + cast(period_from as time) as time,
               period_from in ('00:00:00', '00:00:30') as redated,
               detector_id, trim(direction) as direction, direction <> trim(direction) as trimmed,
               lane_position, lane_id,
               cast(speed as double) as speed, cast(volume as double) as volume,
               case when occupancy = '-1' then 0 else cast(occupancy as double) end as occupancy,
               cast(sd as double) as sd, valid = 'Y' as valid,
               case when occupancy = '-1' then 'D21' end as l2_rule
        from l1""")
    count("D6", "rows re-dated (00:00:00, 00:00:30)", "select * from t where redated")
    count("D3", "rows whose direction lost a space", "select * from t where trimmed")
    count("D21", "rows with occupancy -1 set to 0", "select * from t where l2_rule = 'D21'")
    _raise_if(con, """select bundle, index, min(t.time) as first, max(t.time) as last,
               any_value(f.fetch_time) as fetch_time
        from t join fetches f using (bundle, index) group by bundle, index
        having min(t.time) < any_value(f.fetch_time) - interval 60 minute
            or max(t.time) > any_value(f.fetch_time)""",
              "period not 0-60 min before its file's fetch time")

    # Blocks (detector x period) as listed in the file.
    _by_day(con, "b", """select detector_id, time, count(*) as n, count(distinct lane_id) as nd,
               count(*) filter (where lane_id = 'Middle Lane') as n_ml,
               count(*) filter (where regexp_full_match(lane_id, 'Middle Lane \\d+')) as n_mlk,
               string_agg(lane_id, ' | ' order by lane_position) as lanes
        from t where {day} group by all""")
    d5 = f"detector_id = '{D5_KEY[0]}' and time = timestamp '{D5_KEY[1]}'"
    d4 = "n > nd and n_ml > 1 and n_mlk = 0 and n - nd = n_ml - 1"
    _raise_if(con, f"select * from b where {d5} and lanes <> '{D5_LANES}'", "D5 block in another form")
    _raise_if(con, f"select * from b where n > nd and not ({d5}) and not ({d4})",
              "a lane listed twice, not covered by D4 / D5")

    # D4: number the repeated Middle Lanes in file order.
    con.sql(f"create or replace table b4 as select detector_id, time from b where {d4}")
    count("D4", "blocks with Middle Lane numbered", "select * from b4")
    con.sql("""create or replace table t as
        select * from t anti join b4 using (detector_id, time)
        union all by name
        select * replace (case when lane_id = 'Middle Lane' then 'Middle Lane ' || row_number()
            over (partition by detector_id, time, lane_id order by lane_position) else lane_id end as lane_id)
        from t semi join b4 using (detector_id, time)""")

    # D5: the lanes listed twice in one block become their mean.
    in_d5 = f"select * from t where {d5}"
    count("D5", "rows averaged (in)", in_d5)
    con.sql(f"""create or replace table t as
        select * from t where not ({d5})
        union all by name
        select min(bundle) as bundle, min(index) as index, time, bool_or(redated) as redated,
               detector_id, any_value(direction) as direction, bool_or(trimmed) as trimmed,
               min(lane_position) as lane_position, lane_id,
               avg(speed) as speed, avg(volume) as volume, avg(occupancy) as occupancy,
               avg(sd) as sd, bool_and(valid) as valid,
               concat_ws(',', string_agg(distinct l2_rule, ','), 'D5') as l2_rule
        from ({in_d5}) group by detector_id, time, lane_id""")
    count("D5", "rows averaged (out)", f"select * from t where {d5}")

    # Blocks again, with unique lane names; each detector's usual list in this month.
    _by_day(con, "b", """select detector_id, time, count(*) as n,
               string_agg(lane_id, ' | ' order by lane_position) as lanes,
               list(lane_id) as lane_set
        from t where {day} group by all""")
    con.sql("""create or replace table usual as
        select detector_id, arg_max(lanes, k) as usual, arg_max(lane_set, k) as usual_set
        from (select detector_id, lanes, any_value(lane_set) as lane_set, count(*) as k
              from b group by all) group by detector_id""")

    # D12: TDS90026's 3-lane blocks of 2025.
    con.sql(f"""create or replace table drop_blocks as
        select 'D12' as rule, detector_id, time, n from b
        where detector_id = '{D12_DETECTOR}' and year(time) = 2025 and n = 3""")

    # D13: TDS90036's blocks without Slow Lane (checked against its usual list).
    con.sql(f"""create or replace table b13 as
        select b.detector_id, b.time from b join usual using (detector_id)
        where b.detector_id = '{D13_DETECTOR}' and b.lanes = '{D13_PARTIAL}' and usual = '{D13_FULL}'""")

    # D14: a single block whose lanes are a strict subset of the usual ones, between blocks
    # with the usual lanes (or at the month's edge).
    con.sql(f"""insert into drop_blocks
        select 'D14', detector_id, time, n from (
            select detector_id, time, b.n, b.lanes = u.usual as is_usual,
                   list_has_all(u.usual_set, b.lane_set) and len(b.lane_set) < len(u.usual_set) as is_subset,
                   lag(b.lanes = u.usual) over w as prev_usual, lead(b.lanes = u.usual) over w as next_usual
            from b join usual u using (detector_id)
            where not (b.detector_id = '{D12_DETECTOR}' and year(b.time) = 2025 and b.n = 3)
            window w as (partition by b.detector_id order by b.time)) x
        anti join b13 using (detector_id, time)
        where not is_usual and is_subset and coalesce(prev_usual, true) and coalesce(next_usual, true)""")
    for rule in ("D12", "D14"):
        count(rule, "blocks dropped", f"select * from drop_blocks where rule = '{rule}'")
        count(rule, "rows dropped", f"select * from t semi join (select detector_id, time from drop_blocks "
                                    f"where rule = '{rule}') using (detector_id, time)")
    _raise_if(con, """select b.detector_id, b.time, b.lanes, u.usual from b join usual u using (detector_id)
        anti join drop_blocks using (detector_id, time) anti join b13 using (detector_id, time)
        where b.lanes <> u.usual order by b.detector_id, b.time""",
              "lanes differ from the detector's usual list, no rule")
    con.sql("create or replace table t as select * from t anti join drop_blocks using (detector_id, time)")

    # D13: Slow Lane = the other lanes of the block x the detector's ratio for the hour of day,
    # from its complete blocks of this month.
    con.sql(f"""create or replace table full13 as
        select time, hour(time) as h,
               sum(volume) filter (where lane_id <> 'Slow Lane') as vol_o,
               sum(occupancy) filter (where lane_id <> 'Slow Lane') as occ_o,
               avg(speed) filter (where lane_id <> 'Slow Lane') as sp_o,
               avg(sd) filter (where lane_id <> 'Slow Lane') as sd_o,
               any_value(volume) filter (where lane_id = 'Slow Lane') as vol_s,
               any_value(occupancy) filter (where lane_id = 'Slow Lane') as occ_s,
               any_value(speed) filter (where lane_id = 'Slow Lane') as sp_s,
               any_value(sd) filter (where lane_id = 'Slow Lane') as sd_s
        from t semi join (select detector_id, time from b
                          where detector_id = '{D13_DETECTOR}' and lanes = '{D13_FULL}') using (detector_id, time)
        group by time""")
    con.sql("""create or replace table ratio13 as
        select h, sum(vol_s) / nullif(sum(vol_o), 0) as r_vol, sum(occ_s) / nullif(sum(occ_o), 0) as r_occ,
               median(sp_s / sp_o) filter (where sp_o > 0) as r_sp,
               median(sd_s / sd_o) filter (where sd_o > 0) as r_sd, count(*) as blocks
        from full13 group by h""")
    if con.sql("select count(*) from b13").fetchone()[0]:
        _raise_if(con, """select distinct hour(time) as h from b13
            where hour(time) not in (select h from ratio13
                                     where r_vol is not null and r_occ is not null
                                       and r_sp is not null and r_sd is not null)""",
                  "D13: an hour without a ratio")
    con.sql(f"""insert into t by name
        select min(t.bundle) as bundle, min(t.index) as index, t.time, bool_or(t.redated) as redated,
               t.detector_id, any_value(t.direction) as direction, bool_or(t.trimmed) as trimmed,
               max(t.lane_position) + 1 as lane_position, 'Slow Lane' as lane_id,
               avg(t.speed) * any_value(r.r_sp) as speed, sum(t.volume) * any_value(r.r_vol) as volume,
               sum(t.occupancy) * any_value(r.r_occ) as occupancy, avg(t.sd) * any_value(r.r_sd) as sd,
               bool_and(t.valid) as valid, 'D13' as l2_rule
        from t semi join b13 using (detector_id, time) join ratio13 r on r.h = hour(t.time)
        group by t.detector_id, t.time""")
    count("D13", "blocks with Slow Lane estimated", "select * from b13")

    # D16: a detector without direction in some rows takes its one direction from L1.
    con.sql("""create or replace table dir16 as
        select detector_id, list(distinct trim(direction)) filter (where direction is not null) as dirs
        from l1_all where detector_id in (select detector_id from t where direction is null)
        group by detector_id""")
    _raise_if(con, "select * from dir16 where len(dirs) <> 1", "D16: not exactly one direction")
    count("D16", "rows with direction filled", "select * from t where direction is null")
    con.sql("""create or replace table t as
        select t.* replace (coalesce(t.direction, d.dirs[1]) as direction,
            case when t.direction is null then concat_ws(',', t.l2_rule, 'D16') else t.l2_rule end as l2_rule)
        from t left join dir16 d using (detector_id)""")

    con.sql("""create or replace table l2 as
        select time, detector_id, direction, lane_id, speed, volume, occupancy, sd, valid,
               l2_rule, bundle, index
        from t""")
    cols = [c for c in con.sql("select * from l2 limit 0").columns if c != "l2_rule"]
    _raise_if(con, "select * from l2 where " + " or ".join(f"{c} is null" for c in cols),
              "null left in L2")
    _raise_if(con, """select detector_id, time, lane_id, count(*) as n from l2
        group by all having count(*) > 1""", "a (detector, time, lane) twice")
    count("L2", "rows out", "select * from l2")
    return counts


def _connect() -> duckdb.DuckDBPyConnection:
    tmp = ROOT / ".tmp"
    tmp.mkdir(exist_ok=True)
    con = duckdb.connect(str(tmp / "l2_s1.duckdb"))
    con.sql(f"set temp_directory = '{tmp}'")
    con.sql("set preserve_insertion_order = false")
    return con


def build(months: list[str]) -> None:
    out_dir = L2_DIR / "s1"
    out_dir.mkdir(parents=True, exist_ok=True)
    CHECKS_DIR.mkdir(parents=True, exist_ok=True)
    all_counts, dropped = [], []
    for month in months:
        start = clock.time()
        con = _connect()
        con.sql(f"create or replace view l1 as select * from read_parquet('{L1_DIR / 's1' / f'{month}.parquet'}')")
        con.sql(f"create or replace view l1_all as select * from read_parquet('{L1_DIR / 's1'}/*.parquet')")
        con.sql(f"""create or replace view fetches as
            select bundle, cast(index as int) as index, strptime(fetch_time, '%Y%m%d-%H%M') as fetch_time
            from read_csv('{MANIFEST}', all_varchar = true)""")
        counts = clean(con, month)
        out = out_dir / f"{month}.parquet"
        part = out.with_suffix(".parquet.part")
        con.sql(f"copy (select * from l2 order by time, detector_id) to '{part}' "
                f"(format parquet, compression zstd)")
        part.replace(out)
        dropped += [(month, *r) for r in con.sql("select rule, detector_id, time, n from drop_blocks "
                                                 "order by rule, detector_id, time").fetchall()]
        con.close()
        (ROOT / ".tmp" / "l2_s1.duckdb").unlink()
        all_counts += [(month, *c) for c in counts]
        for c in counts:
            print(f"{month} {c[0]:>4} {c[1]}: {c[2]:,}")
        print(f"{month}: {out} in {clock.time() - start:.0f} s", flush=True)
    for name, header, rows in (("l2_s1_counts.csv", ["month", "rule", "what", "n"], all_counts),
                               ("l2_s1_dropped.csv", ["month", "rule", "detector_id", "time", "n_lanes"], dropped)):
        with (CHECKS_DIR / name).open("w", newline="") as f:
            w = csv.writer(f)
            w.writerow(header)
            w.writerows(rows)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("months", nargs="+", help="YYYYMM, e.g. 202405")
    build(ap.parse_args().months)


if __name__ == "__main__":
    main()
