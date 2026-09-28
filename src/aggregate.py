"""Lane readings -> detector x 15-minute table: python -m src.aggregate ...

Reads data/processed/traffic_lane/ (via src.data.load_traffic_lane) and writes
data/processed/traffic_15min/<YYYY>/<YYYYMMDD>.parquet, one row per detector and
15-minute bin.

No cleaning rule is baked in. The table carries the counts needed to judge data
quality, and two speed columns so the effect of the basic cleaning rule can be
measured directly:

  speed_naive   plain mean over all lane readings (what you get with no cleaning)
  speed_clean   volume-weighted mean over readings with valid == 'Y' and volume > 0
                (drops TD's placeholder speeds for lanes with no traffic)

Other cleaning choices (P1-P6 in PROPOSAL.md) are applied in later steps.
"""

from __future__ import annotations

import argparse
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from tqdm import tqdm

from src.config import PROCESSED_DIR
from src.data import load_traffic_lane
from src.download.select_days import read_manifest
from src.pipeline import table_path
from src.storage import file_version, read_meta, write_parquet

BIN = "15min"
# Bump when the output of `aggregate` changes. Files are also rebuilt when the
# traffic_lane files they were built from change (see `_inputs`).
#   1: initial
VERSION = 1


def out_path(day: date) -> Path:
    return PROCESSED_DIR / "traffic_15min" / f"{day:%Y}" / f"{day:%Y%m%d}.parquet"


def aggregate(lanes: pd.DataFrame, freq: str = BIN) -> pd.DataFrame:
    """Aggregate lane-level readings to detector x `freq` bins."""
    valid = (lanes["valid"] == "Y").to_numpy()
    volume = lanes["volume"].astype("float64").to_numpy()
    speed = lanes["speed"].astype("float64").to_numpy()
    usable = valid & (volume > 0)
    df = pd.DataFrame({
        "detector_id": lanes["detector_id"],
        "t_bin": lanes["time"].dt.floor(freq),
        "speed": speed,
        "is_invalid": ~valid,
        "is_zero_volume": volume == 0,
        "is_speed_over_130": speed > 130,
        "w_speed": np.where(usable, speed * volume, 0.0),
        "w_volume": np.where(usable, volume, 0.0),
        "volume_valid": np.where(valid, volume, np.nan),
        "occupancy_valid": np.where(valid, lanes["occupancy"].astype("float64").to_numpy(), np.nan),
        "period": lanes["time"],
    })
    g = df.groupby(["detector_id", "t_bin"], observed=True, sort=True)
    out = g.agg(
        n_readings=("speed", "size"),
        n_periods=("period", "nunique"),
        n_invalid=("is_invalid", "sum"),
        n_zero_volume=("is_zero_volume", "sum"),
        n_speed_over_130=("is_speed_over_130", "sum"),
        speed_naive=("speed", "mean"),
        w_speed=("w_speed", "sum"),
        w_volume=("w_volume", "sum"),
        volume_sum=("volume_valid", "sum"),
        occupancy_mean=("occupancy_valid", "mean"),
    ).reset_index()
    out["speed_clean"] = (out["w_speed"] / out["w_volume"]).where(out["w_volume"] > 0)
    out = out.drop(columns=["w_speed", "w_volume"])
    out["detector_id"] = out["detector_id"].astype("category")
    for col in ("n_readings", "n_periods", "n_invalid", "n_zero_volume", "n_speed_over_130"):
        out[col] = out[col].astype("int32")
    for col in ("speed_naive", "speed_clean", "volume_sum", "occupancy_mean"):
        out[col] = out[col].astype("float32")
    return out


def _inputs(day: date) -> dict[str, int | None]:
    """Versions of the traffic_lane files a day's table is built from (None = file missing).

    The next day's file matters too: it holds the last minutes of `day`.
    """
    return {d.isoformat(): file_version(table_path("traffic", d)) for d in (day, day + timedelta(days=1))}


def is_current(day: date) -> bool:
    meta = read_meta(out_path(day))
    return meta is not None and meta.get("version") == VERSION and meta.get("inputs") == _inputs(day)


def aggregate_day(day: date, overwrite: bool = False) -> tuple[str, int]:
    """Returns (status, rows): ok / stale (rebuilt) / skip / missing."""
    out = out_path(day)
    existed = out.exists()
    if not overwrite and is_current(day):
        return "skip", 0
    inputs = _inputs(day)
    lanes = load_traffic_lane([day])
    if lanes.empty:
        return "missing", 0
    table = aggregate(lanes)
    write_parquet(table, out, {"table": "traffic_15min", "version": VERSION, "date": day.isoformat(),
                               "inputs": inputs})
    return ("stale" if existed and not overwrite else "ok"), len(table)


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m src.aggregate", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    when = parser.add_mutually_exclusive_group(required=True)
    when.add_argument("--manifest", action="store_true", help="days in data/interim/day_manifest.csv")
    when.add_argument("--days", nargs="+", type=date.fromisoformat, help="YYYY-MM-DD ...")
    when.add_argument("--range", nargs=2, type=date.fromisoformat, metavar=("START", "END"))
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    if args.manifest:
        days = read_manifest()
    elif args.range:
        start, end = args.range
        days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    else:
        days = args.days

    counts = {"ok": 0, "stale": 0, "skip": 0, "missing": 0}
    with tqdm(days, desc="aggregate", unit="day") as bar:
        for day in bar:
            status, rows = aggregate_day(day, overwrite=args.overwrite)
            counts[status] += 1
            if status == "missing":
                tqdm.write(f"[missing] {day}: no traffic_lane data (run src.pipeline first)")
            elif status == "stale":
                tqdm.write(f"[stale] {day}: code or input traffic_lane files changed; rebuilt")
            bar.set_postfix(counts)
    print(f"done: {counts} -> {PROCESSED_DIR / 'traffic_15min'}")


if __name__ == "__main__":
    main()
