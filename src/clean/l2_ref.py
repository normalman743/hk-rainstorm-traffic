"""L2 of the small reference sources: S2 detectors, S4 rainstorm signals, S5 tropical cyclone
signals, S6 public holidays, S8 daily rainfall.

    python -m src.clean.l2_ref

Input: data/interim/l1/{s2,s4,s5,s6,s8}/ (src.clean.versions_parse, signals_parse, s6_parse,
s8_parse). Output under data/interim/l2/, and the counts in data/interim/checks/l2_ref_counts.csv:
- s2/detectors.parquet   S2 version S2_VERSION (D2), every field trimmed (D3) and typed, with
      the field names as written, plus `rain_district`: the S3 district of `District` (D11)
- s4/rainstorm.parquet   one row per signal: line, colour, level (1 Amber, 2 Red, 3 Black),
      start, end (D20: `24:00` = next day 00:00), provisional (after the `UUUU` line)
- s5/tc.parquet          one row per signal, `MSN` rows left out (D18), fields trimmed (D17):
      line, cyclone, intensity, name, signal (integer), direction, start, end (`2400` = next
      day 00:00, as in S4; a time flagged `S` is summer time and moves 1 h back to HKT, D22)
- s6/holidays.parquet    date, name, version: for each date, the latest version that lists it
- s8/daily.parquet       date, rain_mm (`Trace` = 0, D19), trace, completeness; the one row
      with `***` (1900-02-29, a date that does not exist) is left out (D19)

Raises on: an S2 `District` not in the D11 map, a value that does not cast, an S4 / S5 time or
duration in another form or a duration that differs from end - start, `24:xx` other than
`24:00`, an S6 holiday that is not one day long, and an S8 value other than a number, `Trace`
or the one `***`.
"""

from __future__ import annotations

import csv
from datetime import date, datetime, timedelta

import duckdb
import pandas as pd

from src.clean.l2_s1 import CHECKS_DIR, L2_DIR
from src.clean.l2_s3 import DISTRICTS
from src.clean.s1_parse import L1_DIR

S2_VERSION = "20251001"
D11 = {"Eastern": "Eastern District", "Southern": "Southern District", "Islands": "Islands District",
       "North": "North District", "Central & Western": "Central & Western District",
       "Central and Western": "Central & Western District",
       **{d: d for d in DISTRICTS if not d.endswith("District")}}
S2_NUMBERS = {"Easting": float, "Northing": float, "Latitude": float, "Longitude": float, "Rotation": int}
LEVELS = {"A": 1, "R": 2, "B": 3}


def _read(path: str) -> pd.DataFrame:
    return duckdb.sql(f"select * from read_parquet('{path}')").df()


def detectors(s2: pd.DataFrame) -> pd.DataFrame:
    out = s2.drop(columns=["file", "row"]).apply(lambda c: c.str.strip())
    for c, t in S2_NUMBERS.items():
        out[c] = out[c].astype(t)
    bad = sorted(set(out.District) - set(D11))
    if bad:
        raise ValueError(f"D11: S2 districts not in the map: {bad}")
    out["rain_district"] = out.District.map(D11)
    if out.AID_ID_Number.duplicated().any():
        raise ValueError("S2: detector twice")
    return out


def _hm(hhmm: str, where: str) -> tuple[int, int]:
    """'215' -> (2, 15); '2400' -> (24, 0)."""
    if not hhmm.isdigit() or not 1 <= len(hhmm) <= 4:
        raise ValueError(f"{where}: time {hhmm!r}")
    h, m = divmod(int(hhmm), 100)
    if m > 59 or h > 24 or (h == 24 and m):
        raise ValueError(f"{where}: time {hhmm!r}")
    return h, m


def _at(y: str, mo: str, d: str, h: int, m: int) -> datetime:
    """Date plus hours and minutes, so that 24:00 is the next day 00:00 (D20)."""
    return datetime(int(y), int(mo), int(d)) + timedelta(hours=h, minutes=m)


def rainstorm(s4: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    marker = s4.index[s4.colour == "UUUU"]
    rows, n2400 = [], 0
    for r in s4[s4.colour != "UUUU"].itertuples():
        where = f"S4 line {r.line}"
        if r.colour not in LEVELS:
            raise ValueError(f"{where}: colour {r.colour!r}")
        sh, sm, eh, em = (int(x) for x in (r.start_hour, r.start_minute, r.end_hour, r.end_minute))
        if eh == 24 and em:
            raise ValueError(f"{where}: end {eh}:{em}")
        n2400 += eh == 24
        start = _at(r.start_year, r.start_month, r.start_day, sh, sm)
        end = _at(r.end_year, r.end_month, r.end_day, eh, em)
        if end - start != timedelta(hours=int(r.duration_hours), minutes=int(r.duration_minutes)):
            raise ValueError(f"{where}: duration {r.duration_hours}:{r.duration_minutes} is not {end - start}")
        rows.append((r.line, r.colour, LEVELS[r.colour], start, end,
                     bool(len(marker)) and r.Index > marker[0]))
    return pd.DataFrame(rows, columns=["line", "colour", "level", "start", "end", "provisional"]), n2400


def _summer(flag: str, where: str) -> timedelta:
    """D22: a time flagged `S` is Hong Kong summer time (HKT + 1 h, used until 1979)."""
    if flag not in ("S", "X"):
        raise ValueError(f"{where}: flag {flag!r}")
    return timedelta(hours=flag == "S")


def tropical(s5: pd.DataFrame) -> tuple[pd.DataFrame, int, int, int, int]:
    s5 = s5[s5.cyclone != "UUUU"]
    fields = [c for c in s5.columns if c not in ("line", "trailing_tabs")]
    spaced = int(sum((s5[c].str.strip() != s5[c]).sum() for c in fields))
    s5 = s5.assign(**{c: s5[c].str.strip() for c in fields})
    msn = s5.intensity == "MSN"
    rows, n2400 = [], 0
    for r in s5[~msn].itertuples():
        where = f"S5 line {r.line}"
        sh, sm = _hm(r.start_time, where)
        eh, em = _hm(r.end_time, where)
        n2400 += eh == 24
        start = _at(r.start_year, r.start_month, r.start_day, sh, sm) - _summer(r.start_flag, where)
        end = _at(r.end_year, r.end_month, r.end_day, eh, em) - _summer(r.end_flag, where)
        dh, dm = divmod(int(r.duration), 100)
        if end - start != timedelta(hours=dh, minutes=dm):
            raise ValueError(f"{where}: duration {r.duration} is not {end - start}")
        rows.append((r.line, r.cyclone, r.intensity, r.name, int(r.signal), r.direction, start, end))
    out = pd.DataFrame(rows, columns=["line", "cyclone", "intensity", "name", "signal", "direction", "start", "end"])
    summer = int(((s5.start_flag == "S") | (s5.end_flag == "S"))[~msn].sum())
    return out, int(msn.sum()), spaced, n2400, summer


def holidays(s6: pd.DataFrame) -> pd.DataFrame:
    s6 = s6.assign(date=pd.to_datetime(s6.dtstart, format="%Y%m%d").dt.date,
                   end=pd.to_datetime(s6.dtend, format="%Y%m%d").dt.date)
    long = s6[s6.end - s6.date != timedelta(days=1)]
    if len(long):
        raise ValueError(f"S6: holidays not one day long: {long[['bundle', 'dtstart', 'dtend']].head()}")
    latest = s6.sort_values("bundle").groupby("date").tail(1)
    return latest[["date", "summary", "bundle"]].rename(columns={"summary": "name", "bundle": "version"}) \
        .sort_values("date").reset_index(drop=True)


def daily(s8: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    s8 = s8.rename(columns={"年/Year": "y", "月/Month": "m", "日/Day": "d", "數值/Value": "v",
                            "數據完整性/data Completeness": "completeness"})
    missing = s8[s8.v == "***"]
    if missing[["y", "m", "d"]].values.tolist() != [["1900", "2", "29"]]:
        raise ValueError(f"S8: `***` rows {missing[['line', 'y', 'm', 'd']].values.tolist()}")
    s8 = s8[s8.v != "***"]
    other = s8[(s8.v != "Trace") & ~s8.v.str.fullmatch(r"\d+\.\d")]
    if len(other):
        raise ValueError(f"S8: values {other.v.unique()[:10]}")
    out = pd.DataFrame({"date": [date(int(y), int(m), int(d)) for y, m, d in zip(s8.y, s8.m, s8.d)],
                        "rain_mm": s8.v.where(s8.v != "Trace", "0").astype(float),
                        "trace": s8.v == "Trace", "completeness": s8.completeness})
    return out, len(missing)


def build() -> None:
    counts = []
    out = {}
    s2 = _read(f"{L1_DIR / 's2' / S2_VERSION}.parquet")
    out["s2/detectors"] = detectors(s2)
    counts += [("D2", f"S2 detectors (version {S2_VERSION})", len(s2)),
               ("D11", "S2 District renamed to the S3 name", int((out["s2/detectors"].District
                                                                   != out["s2/detectors"].rain_district).sum()))]
    out["s4/rainstorm"], n = rainstorm(_read(f"{L1_DIR / 's4' / 'rstorm.parquet'}"))
    counts += [("S4", "signals", len(out["s4/rainstorm"])), ("D20", "S4 end 24:00 -> next day 00:00", n)]
    out["s5/tc"], msn, spaced, n, summer = tropical(_read(f"{L1_DIR / 's5' / 'tc.parquet'}"))
    counts += [("S5", "signals", len(out["s5/tc"])), ("D18", "S5 MSN rows left out", msn),
               ("D17", "S5 values that lost a space", spaced), ("S5", "end 2400 -> next day 00:00", n),
               ("D22", "S5 signals with a summer-time (S) time, shifted -1 h", summer)]
    out["s6/holidays"] = holidays(_read(f"{L1_DIR / 's6' / 'en.parquet'}"))
    counts.append(("S6", "holiday dates", len(out["s6/holidays"])))
    out["s8/daily"], n = daily(_read(f"{L1_DIR / 's8' / 'daily_HKO_RF_ALL.parquet'}"))
    counts += [("D19", "S8 rows left out (1900-02-29, ***)", n),
               ("D19", "S8 Trace -> 0 mm", int(out["s8/daily"].trace.sum())), ("S8", "days", len(out["s8/daily"]))]
    for name, table in out.items():
        path = L2_DIR / f"{name}.parquet"
        path.parent.mkdir(parents=True, exist_ok=True)
        table.to_parquet(path, index=False)
        print(f"{path}: {len(table):,} rows")
    with (CHECKS_DIR / "l2_ref_counts.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["rule", "what", "n"])
        w.writerows(counts)
    for c in counts:
        print(f"{c[0]:>4} {c[1]}: {c[2]:,}")


if __name__ == "__main__":
    build()
