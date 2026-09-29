"""Row-level checks on S1 L1: repeated keys (same or different values), nulls / empty strings, values that are not numbers.

    python -m src.clean.s1_rows

Reads data/interim/l1/s1/*.parquet (python -m src.clean.s1_parse). Changes nothing.
Key of a reading: (date, period_from, detector_id, lane_id), as written in the file.
TODO: repeated keys with a null key column are not counted or listed (the join does not
match nulls); the null counts of the key columns show whether this matters.

Output, in data/interim/checks/:
- s1_rows_summary.csv   one row per month and check
- s1_rows_repeated.csv  every row whose key occurs more than once (with its bundle:index)
- s1_rows_bad_values.csv  every non-null value of speed / occupancy / volume / sd that is not a
                        number, of date that is not YYYY-MM-DD, or of period_from / period_to
                        that is not HH:MM:SS
"""

from __future__ import annotations

import duckdb

from src.clean.s1_parse import OUT_DIR as L1_DIR
from src.clean.s1_periods import OUT_DIR as CHECKS_DIR

COLUMNS = ["date", "period_from", "period_to", "detector_id", "direction",
           "lane_id", "speed", "occupancy", "volume", "sd", "valid"]
KEY = "date, period_from, detector_id, lane_id"
VALUES = "period_to, direction, speed, occupancy, volume, sd, valid"
# column -> DuckDB check that is TRUE for a well-formed non-null value
FORMATS = {
    "speed": "TRY_CAST(v AS INTEGER) IS NOT NULL",
    "occupancy": "TRY_CAST(v AS INTEGER) IS NOT NULL",
    "volume": "TRY_CAST(v AS INTEGER) IS NOT NULL",
    "sd": "TRY_CAST(v AS DOUBLE) IS NOT NULL",
    "date": "regexp_full_match(v, '\\d{4}-\\d{2}-\\d{2}') AND TRY_CAST(v AS DATE) IS NOT NULL",
    "period_from": "regexp_full_match(v, '\\d{2}:\\d{2}:\\d{2}') AND TRY_CAST(v AS TIME) IS NOT NULL",
    "period_to": "regexp_full_match(v, '\\d{2}:\\d{2}:\\d{2}') AND TRY_CAST(v AS TIME) IS NOT NULL",
}


def main() -> None:
    con = duckdb.connect()
    con.execute(f"SET temp_directory = '{L1_DIR.parent / 'duckdb_tmp'}'")
    con.execute(f"""CREATE VIEW l1 AS SELECT *, substr(bundle, 1, 6) AS month
                    FROM read_parquet('{L1_DIR}/*.parquet')""")
    summary = []

    # rows and repeated keys: first find the keys (count only), then compare their rows
    for month, rows in con.execute("SELECT month, count(*) FROM l1 GROUP BY month ORDER BY month").fetchall():
        summary.append((month, "rows", rows))
    con.execute(f"CREATE TABLE rk AS SELECT month, {KEY} FROM l1 GROUP BY month, {KEY} HAVING count(*) > 1")
    con.execute(f"CREATE TABLE rows_ AS SELECT * FROM l1 SEMI JOIN rk USING (month, {KEY})")
    con.execute(f"""
        CREATE TABLE repeated AS
        SELECT r.*, g.n_rows, g.n_value_sets FROM rows_ r JOIN (
            SELECT month, {KEY}, count(*) AS n_rows, count(DISTINCT ({VALUES})) AS n_value_sets
            FROM rows_ GROUP BY month, {KEY}) g USING (month, {KEY})""")
    for month, n_keys, n_same, n_diff in con.execute(f"""
            SELECT month, count(DISTINCT ({KEY})),
                   count(DISTINCT ({KEY})) FILTER (WHERE n_value_sets = 1),
                   count(DISTINCT ({KEY})) FILTER (WHERE n_value_sets > 1)
            FROM repeated GROUP BY month ORDER BY month""").fetchall():
        summary += [(month, "keys with >1 row", n_keys), (month, "  ... all rows equal", n_same),
                    (month, "  ... rows differ", n_diff)]
    con.execute(f"""COPY (SELECT * EXCLUDE (month) FROM repeated ORDER BY {KEY}, bundle, index)
                    TO '{CHECKS_DIR}/s1_rows_repeated.csv' (HEADER)""")

    # nulls (element absent) and empty strings (element empty)
    for c in COLUMNS:
        for month, n_null, n_empty in con.execute(f"""
                SELECT month, count(*) FILTER (WHERE {c} IS NULL), count(*) FILTER (WHERE {c} = '')
                FROM l1 GROUP BY month ORDER BY month""").fetchall():
            summary += [(month, f"{c}: null", n_null), (month, f"{c}: empty", n_empty)]

    # values that are present but not well-formed
    bad = " UNION ALL ".join(
        f"""SELECT month, bundle, index, {KEY}, '{c}' AS col, v FROM
            (SELECT *, {c} AS v FROM l1) WHERE v IS NOT NULL AND v <> '' AND NOT ({cond})"""
        for c, cond in FORMATS.items())
    con.execute(f"CREATE TABLE bad AS {bad}")
    for month, col, n in con.execute(
            "SELECT month, col, count(*) FROM bad GROUP BY ALL ORDER BY ALL").fetchall():
        summary.append((month, f"{col}: not well-formed", n))
    con.execute(f"""COPY (SELECT * EXCLUDE (month) FROM bad ORDER BY col, {KEY})
                    TO '{CHECKS_DIR}/s1_rows_bad_values.csv' (HEADER)""")

    with (CHECKS_DIR / "s1_rows_summary.csv").open("w") as f:
        f.write("month,check,n\n")
        f.writelines(f"{m},{c.strip()},{n}\n" for m, c, n in summary)
    print(f"written to {CHECKS_DIR}: s1_rows_summary.csv, s1_rows_repeated.csv, s1_rows_bad_values.csv\n")
    months = sorted({m for m, _, _ in summary})
    checks = list(dict.fromkeys(c for _, c, _ in summary))
    table = {(m, c): n for m, c, n in summary}
    print(f"{'check':28}" + "".join(f"{m:>14}" for m in months))
    for c in checks:
        print(f"{c:28}" + "".join(f"{table.get((m, c), 0):>14,}" for m in months))


if __name__ == "__main__":
    main()
