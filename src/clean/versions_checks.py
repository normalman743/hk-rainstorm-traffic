"""Checks on S2, S10, S14 L1: empties, spaces, repeated IDs, formats, values, changes, coverage.

    python -m src.clean.versions_checks

Reads data/interim/l1/{s2,s10,s14}/*.parquet (python -m src.clean.versions_parse) and, for
coverage, the L1 of the readings (s1, s9, s11). Changes nothing.

- ID column of a version: `AID_ID_Number` (S2, S10), `irn_id` or `Segment ID` (S14).
- Formats (S2, S10): Easting, Northing, Rotation integers; Latitude, Longitude decimals.
- Changes: between successive versions of a source, IDs added and removed, and for IDs in both
  the columns whose value changed (only when both versions have the same header).
- Coverage: IDs in the readings of a month (S1 detector_id -> S2, S9 -> S10, S11 segment_id ->
  S14) that are not in the last version before the month, not in the first version after it,
  and not in any version. Which version was in force during a month is not known: the archive
  only shows when a version was captured.
- Directions (S2, S10): for the same two versions, the detectors whose `direction` in the
  readings of the month is not the version's `Direction`, both as written. Readings without a
  direction (absent, see S1) are not compared.

Output, in data/interim/checks/:
- versions_summary.csv     source, version, check, n
- versions_values.csv      source, version, column, value, n   (District, Direction; S14 route)
- versions_changes.csv     source, from_version, to_version, id, change
- versions_coverage.csv    source, month, readings_ids, previous_version, not_in_previous,
                           next_version, not_in_next, not_in_any, not_in_any_ids
- versions_directions.csv  source, month, version, id, readings_direction, version_direction
"""

from __future__ import annotations

import csv
import re
from collections import Counter

import duckdb
import pyarrow.parquet as pq

from src.clean.s1_parse import L1_DIR
from src.clean.s1_periods import OUT_DIR as CHECKS_DIR

SOURCES = ["s2", "s10", "s14"]
ID_COLUMNS = ["AID_ID_Number", "irn_id", "Segment ID"]
FORMATS = {"Easting": r"-?\d+", "Northing": r"-?\d+", "Rotation": r"-?\d+",
           "Latitude": r"-?\d+\.\d+", "Longitude": r"-?\d+\.\d+"}
LISTED = ["District", "Direction", "route", "ucase(route)", "Road Name"]
READINGS = {"s2": ("s1", "detector_id"), "s10": ("s9", "detector_id"), "s14": ("s11", "segment_id")}
DIRECTIONS = ["s2", "s10"]


def _id_column(header: list[str], where: str) -> str:
    found = [c for c in ID_COLUMNS if c in header]
    if len(found) != 1:
        raise ValueError(f"{where}: ID columns {found} in header {header}")
    return found[0]


def main() -> None:
    summary: list[tuple] = []
    values: list[tuple] = []
    changes: list[tuple] = []
    coverage: list[tuple] = []
    directions: list[tuple] = []
    versions: dict[str, dict[str, set]] = {}
    version_direction: dict[tuple[str, str], dict[str, str]] = {}
    for source in SOURCES:
        prev = None
        versions[source] = {}
        for path in sorted((L1_DIR / source).glob("*.parquet")):
            version = path.stem
            rows = pq.read_table(path).to_pylist()
            header = [c for c in pq.read_schema(path).names if c not in ("file", "row")]
            key = _id_column(header, f"{source} {version}")
            n: Counter = Counter()
            n["rows"] = len(rows)
            ids = Counter(r[key] for r in rows)
            n[f"{key}: distinct"] = len(ids)
            n[f"{key}: in 2+ rows"] = sum(1 for c in ids.values() if c > 1)
            for c in header:
                n[f"{c}: empty"] = sum(1 for r in rows if r[c] == "")
                n[f"{c}: leading or trailing space"] = sum(1 for r in rows if r[c] != r[c].strip())
                if c in FORMATS:
                    n[f"{c}: not {FORMATS[c]}"] = sum(1 for r in rows if not re.fullmatch(FORMATS[c], r[c]))
                if c in LISTED:
                    values += [(source, version, c, v, k) for v, k in Counter(r[c] for r in rows).most_common()]
            if key != "AID_ID_Number":
                n[f"{key}: not digits"] = sum(1 for r in rows if not r[key].isdigit())
            summary += [(source, version, c, v) for c, v in n.items()]
            by_id = {r[key]: r for r in rows}
            versions[source][version] = set(by_id)
            if source in DIRECTIONS:
                version_direction[(source, version)] = {i: r["Direction"] for i, r in by_id.items()}
            if prev:
                pv, pheader, pby = prev
                for i in sorted(set(by_id) - set(pby)):
                    changes.append((source, pv, version, i, "added"))
                for i in sorted(set(pby) - set(by_id)):
                    changes.append((source, pv, version, i, "removed"))
                if pheader == header:
                    for i in sorted(set(by_id) & set(pby)):
                        diff = [c for c in header if by_id[i][c] != pby[i][c]]
                        if diff:
                            changes.append((source, pv, version, i, "changed: " + ";".join(diff)))
                else:
                    changes.append((source, pv, version, "", "header differs, values not compared"))
            prev = (version, header, by_id)

    con = duckdb.connect()
    con.execute("SET enable_progress_bar=false")
    for source, (readings, column) in READINGS.items():
        path = L1_DIR / readings
        seen: dict[str, list[tuple[str, str]]] = {}
        if source in DIRECTIONS:
            for month, i, d in con.execute(f"""
                    SELECT DISTINCT left(bundle, 6), {column}, direction FROM read_parquet('{path}/*.parquet')
                    WHERE direction IS NOT NULL ORDER BY ALL""").fetchall():
                seen.setdefault(month, []).append((i, d))
        for month, ids in con.execute(f"""
                SELECT left(bundle, 6), list(DISTINCT {column}) FROM read_parquet('{path}/*.parquet')
                GROUP BY 1 ORDER BY 1""").fetchall():
            ids = set(ids)
            vs = sorted(versions[source])
            before = [v for v in vs if v[:6] <= month]
            after = [v for v in vs if v[:6] > month]
            pv = before[-1] if before else ""
            nv = after[0] if after else ""
            any_ids = set().union(*versions[source].values())
            missing = sorted(ids - any_ids)
            coverage.append((source, month, len(ids), pv, len(ids - versions[source][pv]) if pv else "",
                             nv, len(ids - versions[source][nv]) if nv else "", len(missing), ";".join(missing)))
            if source in DIRECTIONS:
                for v in [v for v in (pv, nv) if v]:
                    table = version_direction[(source, v)]
                    directions += [(source, month, v, i, d, table[i]) for i, d in seen[month]
                                   if i in table and d != table[i]]

    CHECKS_DIR.mkdir(parents=True, exist_ok=True)
    out = {
        "versions_summary.csv": (["source", "version", "check", "n"], summary),
        "versions_values.csv": (["source", "version", "column", "value", "n"], values),
        "versions_changes.csv": (["source", "from_version", "to_version", "id", "change"], changes),
        "versions_coverage.csv": (["source", "month", "readings_ids", "previous_version", "not_in_previous",
                                   "next_version", "not_in_next", "not_in_any", "not_in_any_ids"], coverage),
        "versions_directions.csv": (["source", "month", "version", "id", "readings_direction",
                                     "version_direction"], directions),
    }
    for name, (header, rows) in out.items():
        with (CHECKS_DIR / name).open("w", newline="") as f:
            w = csv.writer(f)
            w.writerow(header)
            w.writerows(rows)
    print(f"written to {CHECKS_DIR}: {', '.join(out)}\n")
    for source in SOURCES:
        vs = sorted({v for s, v, _, _ in summary if s == source})
        print(f"{source:5}{'check':45}" + "".join(f"{v:>10}" for v in vs))
        table = {(v, c): k for s, v, c, k in summary if s == source}
        for c in dict.fromkeys(c for s, _, c, _ in summary if s == source):
            if any(table.get((v, c)) for v in vs):
                print(f"{'':5}{c[:45]:45}" + "".join(f"{table.get((v, c), ''):>10}" for v in vs))
    print("\nchanges:", Counter((s, f, t, c.split(":")[0]) for s, f, t, _, c in changes))
    for row in coverage:
        print("coverage", row[:8], row[8][:200])
    print("directions differ:", Counter(r[:3] for r in directions))


if __name__ == "__main__":
    main()
