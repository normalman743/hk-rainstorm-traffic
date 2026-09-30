"""The L1 tables against the structure we presume: how many values hit, and what the others look like.

    python -m src.clean.structure [s4 s5 s6 s8 s12]

EXPECT gives, per source and column, the form we presume: a regular expression that the whole
value must match, taken from the data dictionaries and docs/raw_data.md (None = no presumption,
the column is only described). Every value is checked. The report gives the hits and groups the
misses by value when there are at most MAX_VALUES distinct ones, otherwise by shape (each digit
-> 9, a run of A-Z -> A, a run of a-z -> a, other characters as they are), each with a count
and its first example (row id and value). With `context`, the misses of a column are also split
by the value of another column in the same row (e.g. S5 direction by intensity). Rows marked by
`skip` (the `UUUU` line) are listed and left out of the column checks.

L1 keeps the text as written, so this is the structure of the raw files; the row id (line, or
bundle:position) points back into them. S12 is typed, not text: for it the report compares the
layers across versions (fields, geometry type, CRS, number of features, from
checks/s12_layers.csv) and counts the geometry types found in the WKB, with Z / M and curves.

Output: printed, and data/interim/checks/structure.csv, one row per group:
    source, table, column, expected, n, hits, group, count, example
"""

from __future__ import annotations

import argparse
import csv
import re
from collections import Counter, defaultdict

import pyarrow.parquet as pq

from src.clean.s1_parse import L1_DIR
from src.clean.s1_periods import OUT_DIR as CHECKS_DIR

OUT = CHECKS_DIR / "structure.csv"
MAX_VALUES = 8     # misses grouped by value up to this many distinct values, else by shape
PRINT_GROUPS = 16  # groups printed per column (all of them go to the CSV)
D12, D4 = r"\d{1,2}", r"\d{4}"
TEXT = r"\S(.*\S)?"  # not empty, no space at either end
EXPECT = {
    "s4": {"table": "s4/rstorm.parquet", "id": ["line"], "skip": ("colour", "UUUU"), "columns": {
        "colour": "A|R|B",
        **{f"{e}_{p}": D4 if p == "year" else D12
           for e in ("start", "end") for p in ("year", "month", "day", "hour", "minute")},
        "duration_hours": D12, "duration_minutes": D12, "trailing_tabs": "0"}},
    "s5": {"table": "s5/tc.parquet", "id": ["line"], "skip": ("cyclone", "UUUU"),
           "context": {"cyclone": "intensity", "signal": "intensity", "direction": "intensity"}, "columns": {
        "cyclone": r"\d{6}", "intensity": "TD|TS|STS|T|ST|SuperT", "name": "[A-Z]+(-[A-Z]+)*",
        "signal": "1|3|8|9|10", "direction": "NE|NW|SE|SW|X",
        **{f"{e}_{p}": {"time": r"\d{1,4}", "day": D12, "month": D12, "year": D4, "flag": "X|S"}[p]
           for e in ("start", "end") for p in ("time", "day", "month", "year", "flag")},
        "duration": r"\d{1,5}", "trailing_tabs": "0"}},
    "s6": {"table": "s6/en.parquet", "id": ["bundle", "position"], "columns": {
        **{c: None for c in ["prodid", "version", "calscale", "x-wr-timezone", "x-wr-calname", "x-wr-caldesc"]},
        "dtstart": r"\d{8}", "dtstart_params": re.escape('{"value": "DATE"}'),
        "dtend": r"\d{8}", "dtend_params": re.escape('{"value": "DATE"}'),
        "dtstamp": None, "transp": "TRANSPARENT", "uid": r"\d{8}@1823\.gov\.hk", "summary": TEXT}},
    "s8": {"table": "s8/daily_HKO_RF_ALL.parquet", "id": ["line"], "columns": {
        "年/Year": D4, "月/Month": D12, "日/Day": D12, "數值/Value": r"\d+\.\d",
        "數據完整性/data Completeness": "C"}},
}
ISO_BASE = {1: "Point", 2: "LineString", 3: "Polygon", 4: "MultiPoint", 5: "MultiLineString",
            6: "MultiPolygon", 7: "GeometryCollection", 8: "CircularString", 9: "CompoundCurve",
            10: "CurvePolygon", 11: "MultiCurve", 12: "MultiSurface"}
ISO_DIM = {0: "", 1: " Z", 2: " M", 3: " ZM"}


def shape(value) -> str:
    if value is None:
        return "<null>"
    if value == "":
        return "<empty>"
    s = re.sub(r"[0-9]", "9", str(value))
    return re.sub(r"[a-z]+", "a", re.sub(r"[A-Z]+", "A", s))


def check_table(source: str, spec: dict, out: list[dict]) -> None:
    t = pq.read_table(L1_DIR / spec["table"]).to_pydict()
    n_rows = len(t[spec["id"][0]])
    ids = [":".join(str(t[c][i]) for c in spec["id"]) for i in range(n_rows)]
    unknown = set(t) - set(spec["columns"]) - set(spec["id"]) - {"bundle", "member"}
    if unknown:
        raise ValueError(f"{source}: columns without a presumption in EXPECT: {sorted(unknown)}")
    rows = list(range(n_rows))
    print(f"== {source} {spec['table']}: {n_rows} rows")
    if "skip" in spec:
        col, val = spec["skip"]
        marked = [i for i in rows if t[col][i] == val]
        print(f"   rows with {col} = {val!r} (left out below): {[ids[i] for i in marked]}")
        rows = [i for i in rows if t[col][i] != val]
    for column, expected in spec["columns"].items():
        rx = re.compile(expected) if expected is not None else None
        ctx = spec.get("context", {}).get(column)
        values = [(i, t[column][i]) for i in rows]
        misses = [(i, v) for i, v in values if rx is None or v is None or not rx.fullmatch(str(v))]
        by_value = len({v for _, v in misses}) <= MAX_VALUES
        groups: dict[str, list] = defaultdict(list)
        for i, v in misses:
            g = repr(v) if by_value else shape(v)
            if ctx:
                g += f"  ({ctx} {t[ctx][i]!r})"
            groups[g].append((ids[i], v))
        hits = "-" if rx is None else f"{len(values) - len(misses)}/{len(values)}"
        print(f"   {column:30} {expected or '(no presumption)':34} hits {hits}")
        for g, members in sorted(groups.items(), key=lambda kv: -len(kv[1]))[:PRINT_GROUPS]:
            print(f"       {g:40} {len(members):>7}   first: {members[0][0]} {members[0][1]!r}")
        if len(groups) > PRINT_GROUPS:
            print(f"       ... {len(groups) - PRINT_GROUPS} more groups (all in {OUT.name})")
        for g, members in groups.items():
            out.append({"source": source, "table": spec["table"], "column": column, "expected": expected,
                        "n": len(values), "hits": None if rx is None else len(values) - len(misses),
                        "group": g, "count": len(members), "example": f"{members[0][0]} {members[0][1]!r}"})


def iso_type(wkb: bytes | None) -> str:
    if wkb is None:
        return "null"
    code = int.from_bytes(wkb[1:5], "little" if wkb[0] == 1 else "big")
    return ISO_BASE.get(code % 1000, f"type {code % 1000}") + ISO_DIM.get(code // 1000, f" dim {code // 1000}")


def check_s12(out: list[dict]) -> None:
    with (CHECKS_DIR / "s12_layers.csv").open() as f:
        rows = list(csv.DictReader(f))
    versions = sorted({(r["bundle"], r["index"]) for r in rows})
    print(f"== s12: {len(versions)} versions, {len({r['layer'] for r in rows})} layers")
    by_layer = defaultdict(list)
    for r in rows:
        by_layer[r["layer"]].append(r)
    for layer, rs in sorted(by_layer.items()):
        wkb = Counter()
        for p in sorted((L1_DIR / "s12" / layer).glob("*.parquet")):
            binary = [f.name for f in pq.read_schema(p) if str(f.type) == "binary"]
            if len(binary) > 1:
                raise ValueError(f"{p}: several binary columns {binary}")
            for w in pq.read_table(p, columns=binary).column(0).to_pylist() if binary else []:
                wkb[iso_type(w)] += 1
        fields = Counter(r["fields"] for r in rs)
        facts = {"versions": f"{len(rs)}/{len(versions)}",
                 "fields": "same in all" if len(fields) == 1 else f"{len(fields)} different lists",
                 "layer type": " | ".join(sorted({r["geometry_type"] for r in rs})),
                 "crs": " | ".join(sorted({r["crs"] for r in rs})),
                 "features": " ".join(r["n_features"] for r in rs),
                 "wkb": ", ".join(f"{k} {v}" for k, v in wkb.most_common())}
        print(f"   {layer}: " + "; ".join(f"{k} {v}" for k, v in facts.items()))
        if len(fields) > 1:
            first = rs[0]["fields"].split(";")
            for r in rs[1:]:
                other = r["fields"].split(";")
                if other != first:
                    print(f"       {r['bundle']}:{r['index']} vs {rs[0]['bundle']}:{rs[0]['index']}: "
                          f"added {sorted(set(other) - set(first))}, removed {sorted(set(first) - set(other))}")
        for k, v in facts.items():
            out.append({"source": "s12", "table": layer, "column": k, "expected": None, "n": len(rs),
                        "hits": None, "group": v, "count": None, "example": None})


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("sources", nargs="*", help=f"any of {', '.join([*EXPECT, 's12'])} (default: all)")
    args = ap.parse_args()
    sources = args.sources or [*EXPECT, "s12"]
    if set(sources) - {*EXPECT, "s12"}:
        ap.error(f"unknown sources {sorted(set(sources) - {*EXPECT, 's12'})}")
    out: list[dict] = []
    for source in sources:
        if source == "s12":
            check_s12(out)
        else:
            check_table(source, EXPECT[source], out)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="") as f:
        w = csv.DictWriter(f, ["source", "table", "column", "expected", "n", "hits", "group", "count", "example"])
        w.writeheader()
        w.writerows(out)
    print(f"written: {OUT}")


if __name__ == "__main__":
    main()
