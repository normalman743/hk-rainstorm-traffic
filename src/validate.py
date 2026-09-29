"""Check processed data and write a report: python -m src.validate --manifest|--days|--range

Every check gets a level:
  FAIL  an invariant is broken, so the data is wrong: NA in a required column,
        duplicate keys, misdated midnight rows, unknown category values, a file
        written by an outdated code version, ...
  WARN  suspicious but possible: low coverage, truncated source files,
        detectors missing from the location table, next day not processed, ...
  INFO  facts to be aware of before cleaning: placeholder speeds, out-of-range
        values, rows flagged invalid. Nothing is cleaned here.
  OK    the check passed.

The report also profiles each table: per column NA count, number of unique
values and the most frequent values.

Output: data/processed/validation_report.md and validation_checks.csv.
Exit code 1 if any check FAILs. `python -m src.pipeline` runs this after each run.
"""

from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta

import pandas as pd
from tqdm import tqdm

from src import aggregate
from src.config import PROCESSED_DIR, RAW_DIR
from src.data import load_rainfall_district, load_traffic_lane
from src.download.select_days import read_manifest
from src.parse import traffic, weather
from src.pipeline import COVERAGE, table_path
from src.storage import file_version

REPORT = PROCESSED_DIR / "validation_report.md"
CHECKS_CSV = PROCESSED_DIR / "validation_checks.csv"

KNOWN_LANES = {"Fast Lane", "Middle Lane", "Slow Lane", "Middle Lane 1", "Middle Lane 2",
               "Middle Lane 3", "Middle Lane 4"}
PERIODS_PER_DAY = 2880              # 30-second periods
SD_FIRST_DAY = date(2021, 11, 18)   # <s.d.> exists from here on
PLACEHOLDER_SPEEDS = [50, 70, 80, 100, 110]
ALL_TABLES = ["traffic_lane", "rainfall_district", "traffic_15min"]


@dataclass
class Check:
    table: str
    day: str
    name: str
    level: str      # FAIL / WARN / INFO / OK
    value: object
    detail: str = ""


def _plain(value):
    """numpy scalars -> Python numbers, so reports show 0.27 rather than np.float64(0.27)."""
    return value.item() if hasattr(value, "item") else value


class Checks(list):
    def append(self, check: Check) -> None:
        check.value = _plain(check.value)
        super().append(check)

    def expect_zero(self, table, day, name, count, level="FAIL", detail=""):
        """A problem count that should be 0: OK if it is, otherwise `level`."""
        self.append(Check(table, day, name, "OK" if count == 0 else level, int(count), detail))

    def info(self, table, day, name, value, detail=""):
        self.append(Check(table, day, name, "INFO", value, detail))


def _distinct(s: pd.Series) -> set[str]:
    """Distinct non-null values as strings (fast: no per-row Python objects)."""
    return {str(v) for v in pd.unique(s.dropna())}


# --- traffic_lane ------------------------------------------------------------

def check_traffic_file(c: Checks, day: date, df: pd.DataFrame) -> None:
    """Checks on one day's file as stored (before cross-day merging)."""
    d = day.isoformat()
    c.expect_zero("traffic_lane", d, "duplicate keys in file", df.duplicated(traffic.KEY).sum())
    prev = pd.Timestamp(day - timedelta(days=1))
    # The file for `day` may hold the last minutes of the previous day (files lag
    # measurement time), but never its first minutes: those are misdated 00:00 periods.
    misdated = (df["time"] >= prev) & (df["time"] < prev + pd.Timedelta(hours=1))
    c.expect_zero("traffic_lane", d, "misdated midnight rows (previous day 00:xx)", misdated.sum(),
                  detail="00:00 periods carrying the previous day's <date>; file predates the fix?")
    outside = (df["time"] < prev + pd.Timedelta(hours=23)) | (df["time"] >= pd.Timestamp(day + timedelta(days=1)))
    c.expect_zero("traffic_lane", d, "rows outside [previous day 23:00, next day 00:00)",
                  (outside & ~misdated).sum())


def check_traffic_day(c: Checks, day: date, df: pd.DataFrame, known_detectors: set[str] | None,
                      next_day_present: bool) -> None:
    """Checks on a day as loaded (merged with the next day's file, filtered to `day`)."""
    t, d = "traffic_lane", day.isoformat()
    for col in ["time", "detector_id", "lane", "speed", "occupancy", "volume", "valid"]:
        c.expect_zero(t, d, f"NA in {col}", df[col].isna().sum())
    sd_na = df["sd"].isna().sum()
    if day < SD_FIRST_DAY:
        c.info(t, d, "NA in sd (expected before 2021-11-18)", int(sd_na))
    else:
        c.expect_zero(t, d, "NA in sd", sd_na, level="WARN")
    c.expect_zero(t, d, "duplicate keys (time, detector_id, lane)", df.duplicated(traffic.KEY).sum())
    c.expect_zero(t, d, "rows dated outside the day", (df["time"].dt.normalize() != pd.Timestamp(day)).sum())
    c.expect_zero(t, d, "unknown valid values", (~df["valid"].isin(["Y", "N"])).sum(),
                  detail=str(sorted(_distinct(df["valid"]) - {"Y", "N"})))
    c.expect_zero(t, d, "unknown lane labels", (~df["lane"].isin(KNOWN_LANES)).sum(),
                  detail=str(sorted(_distinct(df["lane"]) - KNOWN_LANES)))
    if known_detectors is not None:
        unknown = _distinct(df["detector_id"]) - known_detectors
        c.expect_zero(t, d, "detectors missing from the location table", len(unknown), level="WARN",
                      detail=", ".join(sorted(unknown)[:10]))
    if not next_day_present:
        c.append(Check(t, d, "next day processed", "WARN", False,
                       "the last ~10 min of the day are stored in the next day's file"))

    periods = df["time"].nunique()
    share = periods / PERIODS_PER_DAY
    c.append(Check(t, d, "share of 30-s periods present", "OK" if share >= 0.5 else "WARN", round(share, 3),
                   f"{periods} of {PERIODS_PER_DAY}"))
    c.info(t, d, "rows", len(df))
    c.info(t, d, "detectors reporting", df["detector_id"].nunique())

    n = len(df) or 1
    zero_vol = df["volume"] == 0
    c.info(t, d, "share volume == 0 (speed is a placeholder)", round(zero_vol.sum() / n, 4),
           f"top speeds when volume == 0: {df.loc[zero_vol, 'speed'].value_counts().head(5).to_dict()}")
    c.info(t, d, "rows speed == 0 and volume > 0", int(((df["speed"] == 0) & ~zero_vol).sum()))
    c.info(t, d, "rows speed > 130", int((df["speed"] > 130).sum()))
    c.expect_zero(t, d, "rows speed < 0", (df["speed"] < 0).sum(), level="WARN")
    c.info(t, d, "rows occupancy < 0", int((df["occupancy"] < 0).sum()))
    c.expect_zero(t, d, "rows occupancy > 100", (df["occupancy"] > 100).sum(), level="WARN")
    c.info(t, d, "rows occupancy == 100", int((df["occupancy"] == 100).sum()))
    c.info(t, d, "share valid == N", round(float((df["valid"] == "N").mean()), 4))


# --- rainfall_district -----------------------------------------------------------

def check_rainfall_day(c: Checks, day: date, df: pd.DataFrame) -> None:
    t, d = "rainfall_district", day.isoformat()
    for col in df.columns:
        c.expect_zero(t, d, f"NA in {col}", df[col].isna().sum())
    c.expect_zero(t, d, "duplicate keys (district, period_end)", df.duplicated(["district", "period_end"]).sum())
    hours = df["period_end"].nunique()
    c.append(Check(t, d, "hours present", "OK" if hours == 24 else "WARN", hours, "expected 24"))
    per_hour = df.groupby("period_end").size()
    c.expect_zero(t, d, "hours without exactly 18 districts", (per_hour != len(weather.DISTRICTS)).sum())
    c.expect_zero(t, d, "unknown districts", (~df["district"].isin(weather.DISTRICTS)).sum())
    c.expect_zero(t, d, "rain_min_mm > rain_max_mm", (df["rain_min_mm"] > df["rain_max_mm"]).sum())
    c.expect_zero(t, d, "not listed but rain > 0", ((~df["listed"]) & (df["rain_max_mm"] > 0)).sum())
    c.expect_zero(t, d, "listed but rain_max_mm == 0", (df["listed"] & (df["rain_max_mm"] == 0)).sum(),
                  level="WARN")
    c.info(t, d, "hours without a rainfall sentence (no rain anywhere)",
           int((~df.groupby("period_end")["section_present"].first()).sum()))
    c.info(t, d, "max rain_max_mm", float(df["rain_max_mm"].max()) if len(df) else None)


# --- traffic_15min --------------------------------------------------------------

def check_15min_day(c: Checks, day: date, df: pd.DataFrame) -> None:
    t, d = "traffic_15min", day.isoformat()
    for col in ["detector_id", "t_bin", "n_readings", "n_periods", "speed_naive", "volume_sum"]:
        c.expect_zero(t, d, f"NA in {col}", df[col].isna().sum())
    c.expect_zero(t, d, "duplicate keys (detector_id, t_bin)", df.duplicated(["detector_id", "t_bin"]).sum())
    c.expect_zero(t, d, "bins dated outside the day", (df["t_bin"].dt.normalize() != pd.Timestamp(day)).sum())
    c.expect_zero(t, d, "n_periods > 30", (df["n_periods"] > 30).sum())
    c.expect_zero(t, d, "n_readings == 0", (df["n_readings"] == 0).sum())
    n = len(df) or 1
    c.info(t, d, "share speed_clean NA (no valid reading with volume > 0)", round(df["speed_clean"].isna().sum() / n, 4))
    c.info(t, d, "share occupancy_mean NA (all readings invalid)", round(df["occupancy_mean"].isna().sum() / n, 4))
    c.info(t, d, "bins speed_clean > 130", int((df["speed_clean"] > 130).sum()))
    c.info(t, d, "bins", len(df))


# --- reference tables ---------------------------------------------------------------

def check_reference(c: Checks) -> None:
    det_path = RAW_DIR / "td" / "traffic_speed_volume_occ_info.csv"
    if det_path.exists():
        det = pd.read_csv(det_path, encoding="utf-8-sig")
        c.expect_zero("detectors", "", "duplicate AID_ID_Number", det["AID_ID_Number"].duplicated().sum())
        c.info("detectors", "", "rows", len(det))
        variants = det["District"].str.strip().value_counts()
        c.info("detectors", "", "District spellings", len(variants), "normalise 'Central and Western' -> 'Central & Western'")
        c.info("detectors", "", "Road_EN with trailing spaces", int(det["Road_EN"].str.endswith(" ").sum()))
        c.info("detectors", "", "Road_EN shared by 2+ detectors", int(det["Road_EN"].duplicated(keep=False).sum()),
               "different detectors ~30 m apart: always join on the ID")
    else:
        c.append(Check("detectors", "", "file present", "WARN", False, "run python -m src.download static"))

    warn_path = RAW_DIR / "hko" / "rainstorm_warnings.csv"
    if warn_path.exists():
        w = pd.read_csv(warn_path, parse_dates=["start", "end"]).sort_values("start")
        c.expect_zero("rainstorm_warnings", "", "end <= start", (w["end"] <= w["start"]).sum())
        c.expect_zero("rainstorm_warnings", "", "overlapping signals",
                      (w["start"].iloc[1:].to_numpy() < w["end"].iloc[:-1].to_numpy()).sum(), level="WARN")
        c.info("rainstorm_warnings", "", "provisional rows", int(w["provisional"].sum()))
    else:
        c.append(Check("rainstorm_warnings", "", "file present", "WARN", False, "run python -m src.download warnings"))

    hol_path = RAW_DIR / "calendar" / "public_holidays.csv"
    if hol_path.exists():
        h = pd.read_csv(hol_path, parse_dates=["date"])
        c.expect_zero("public_holidays", "", "duplicate dates", h["date"].duplicated().sum())
        per_year = h["date"].dt.year.value_counts().sort_index()
        c.info("public_holidays", "", "holidays per year", per_year.to_dict())
    else:
        c.append(Check("public_holidays", "", "file present", "WARN", False, "run python -m src.download holidays"))

    rf_path = RAW_DIR / "hko" / "daily_HKO_RF_ALL.csv"
    if rf_path.exists():
        rf = pd.read_csv(rf_path, skiprows=2, encoding="utf-8-sig", dtype=str)
        values = rf.iloc[:, 3][rf.iloc[:, 0].str.fullmatch(r"\d{4}", na=False)]
        text = values[pd.to_numeric(values, errors="coerce").isna()]
        c.info("daily_HKO_RF", "", "non-numeric values", text.value_counts().to_dict(),
               "'Trace' = < 0.05 mm (treat as ~0, not NaN); '***' = unavailable")


# --- markdown -----------------------------------------------------------------------

def _md(df: pd.DataFrame, index: bool = True) -> str:
    """Minimal Markdown table (avoids an extra dependency on `tabulate`)."""
    if index:
        df = df.reset_index()
    cell = lambda v: str(v).replace("|", "\\|").replace("\n", " ")
    rows = ["| " + " | ".join(cell(c) for c in df.columns) + " |", "|" + "---|" * len(df.columns)]
    rows += ["| " + " | ".join(cell(v) for v in row) + " |" for row in df.itertuples(index=False)]
    return "\n".join(rows)


# --- profiles -----------------------------------------------------------------------

def _fmt(value) -> str:
    """Short display: float32 values like 4.199999809 -> 4.2."""
    return f"{value:.4g}" if isinstance(value, float) else str(value)


def profile(df: pd.DataFrame, top: int = 5) -> str:
    """Markdown table: per column dtype, NA, unique values, range and most frequent values."""
    lines = ["| column | dtype | NA | NA % | unique | min | max | most frequent (count) |",
             "|---|---|---|---|---|---|---|---|"]
    n = len(df) or 1
    for col in df.columns:
        s = df[col]
        na = int(s.isna().sum())
        numeric = pd.api.types.is_numeric_dtype(s) and not pd.api.types.is_bool_dtype(s)
        rng = (s.min(), s.max()) if numeric or pd.api.types.is_datetime64_any_dtype(s) else ("", "")
        rng = tuple(_fmt(v) for v in rng)
        freq = "; ".join(f"`{_fmt(k)}` ({v:,})" for k, v in s.value_counts(dropna=False).head(top).items())
        lines.append(f"| {col} | {s.dtype} | {na:,} | {na / n:.1%} | {s.nunique():,} | {rng[0]} | {rng[1]} | {freq} |")
    return "\n".join(lines)


# --- driver ---------------------------------------------------------------------------

def _staleness(c: Checks, table: str, day: date) -> bool:
    """Record file presence / version checks; True if the file can be checked further."""
    d = day.isoformat()
    if table == "traffic_15min":
        path = aggregate.out_path(day)
        if not path.exists():
            c.append(Check(table, d, "file present", "FAIL", False, "run python -m src.aggregate"))
            return False
        c.append(Check(table, d, "file up to date", "OK" if aggregate.is_current(day) else "FAIL",
                       file_version(path), "code or input traffic_lane files changed; re-run python -m src.aggregate"))
        return True
    source = "traffic" if table == "traffic_lane" else "weather"
    path = table_path(source, day)
    if not path.exists():
        c.append(Check(table, d, "file present", "FAIL", False, "run python -m src.pipeline"))
        return False
    current = traffic.VERSION if source == "traffic" else weather.VERSION
    version = file_version(path)
    c.append(Check(table, d, "file up to date", "OK" if version == current else "FAIL", version,
                   f"parser version {version}, current {current}; re-run python -m src.pipeline"))
    return True


def run(days: list[date], tables: list[str] | None = None) -> int:
    """Run all checks, write the report, print a summary. Returns the number of FAILs."""
    tables = tables or ALL_TABLES
    days = sorted(set(days))
    c = Checks()
    check_reference(c)
    det_path = RAW_DIR / "td" / "traffic_speed_volume_occ_info.csv"
    known = set(pd.read_csv(det_path, encoding="utf-8-sig")["AID_ID_Number"]) if det_path.exists() else None
    truncated = {}
    if COVERAGE.exists():
        with COVERAGE.open() as f:
            truncated = {r["date"]: r.get("n_truncated_files") for r in csv.DictReader(f) if r["source"] == "traffic"}

    samples: dict[str, pd.DataFrame] = {}
    for day in tqdm(days, desc="validate", unit="day"):
        d = day.isoformat()
        n_before = len(c)
        if "traffic_lane" in tables and _staleness(c, "traffic_lane", day):
            check_traffic_file(c, day, pd.read_parquet(table_path("traffic", day), columns=["time", "detector_id", "lane"]))
            lanes = load_traffic_lane([day])
            check_traffic_day(c, day, lanes, known, table_path("traffic", day + timedelta(days=1)).exists())
            n_trunc = truncated.get(d)
            if n_trunc not in (None, ""):
                c.expect_zero("traffic_lane", d, "truncated source files", int(float(n_trunc)), level="WARN",
                              detail="complete readings before the cut are kept")
            samples["traffic_lane"] = lanes
        if "rainfall_district" in tables and _staleness(c, "rainfall_district", day):
            rain = load_rainfall_district([day])
            check_rainfall_day(c, day, rain)
            samples["rainfall_district"] = pd.concat([samples.get("rainfall_district"), rain])
        if "traffic_15min" in tables and _staleness(c, "traffic_15min", day):
            t15 = pd.read_parquet(aggregate.out_path(day))
            check_15min_day(c, day, t15)
            samples["traffic_15min"] = pd.concat([samples.get("traffic_15min"), t15])
        for x in c[n_before:]:
            if x.level in ("FAIL", "WARN"):
                tqdm.write(f"  [{x.level}] {x.table} {x.day} {x.name}: {x.value} {x.detail}")

    _write(c, days, tables, samples)
    counts = pd.Series([x.level for x in c]).value_counts().to_dict()
    fails = counts.get("FAIL", 0)
    print(f"validation: {counts.get('OK', 0)} OK, {counts.get('INFO', 0)} INFO, "
          f"{counts.get('WARN', 0)} WARN, {fails} FAIL -> {REPORT}")
    for x in c:
        if x.level in ("FAIL", "WARN"):
            print(f"  [{x.level}] {x.table} {x.day} {x.name}: {x.value} {x.detail}")
    return fails


def _write(c: Checks, days: list[date], tables: list[str], samples: dict[str, pd.DataFrame]) -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    with CHECKS_CSV.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(asdict(c[0]).keys()) if c else ["table"])
        writer.writeheader()
        writer.writerows(asdict(x) for x in c)

    df = pd.DataFrame([asdict(x) for x in c])
    out = [f"# Validation report", "",
           f"Generated {datetime.now():%Y-%m-%d %H:%M}. Days: {len(days)} "
           f"({days[0] if days else '-'} .. {days[-1] if days else '-'}). Tables: {', '.join(tables)}.", "",
           "Levels: **FAIL** = data is wrong; **WARN** = suspicious; **INFO** = facts before cleaning; OK = passed.", "",
           "## Summary", "", _md(df.groupby(["table", "level"]).size().unstack(fill_value=0)), ""]
    problems = df[df["level"].isin(["FAIL", "WARN"])]
    out += ["## Problems (FAIL / WARN)", "",
            _md(problems[["level", "table", "day", "name", "value", "detail"]], index=False)
            if len(problems) else "None.", ""]
    for table in tables:
        per_day = df[(df["table"] == table) & (df["day"] != "")]
        if len(per_day):
            out += [f"## {table}: checks per day", "",
                    _md(per_day.pivot_table(index="name", columns="day", values="value", aggfunc="first")), ""]
    ref = df[df["day"] == ""]
    out += ["## Reference tables", "", _md(ref[["table", "name", "level", "value", "detail"]], index=False), ""]
    for table, sample in samples.items():
        scope = "last checked day" if table == "traffic_lane" else "all checked days"
        out += [f"## Profile: {table} ({scope}, {len(sample):,} rows)", "", profile(sample.reset_index(drop=True)), ""]
    REPORT.write_text("\n".join(out))


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m src.validate", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    when = parser.add_mutually_exclusive_group(required=True)
    when.add_argument("--manifest", action="store_true", help="days in data/interim/day_manifest.csv")
    when.add_argument("--days", nargs="+", type=date.fromisoformat, help="YYYY-MM-DD ...")
    when.add_argument("--range", nargs=2, type=date.fromisoformat, metavar=("START", "END"))
    parser.add_argument("--tables", nargs="+", choices=ALL_TABLES, default=ALL_TABLES)
    args = parser.parse_args()
    if args.manifest:
        days = read_manifest()
    elif args.range:
        start, end = args.range
        days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    else:
        days = args.days
    sys.exit(1 if run(days, args.tables) else 0)


if __name__ == "__main__":
    main()
