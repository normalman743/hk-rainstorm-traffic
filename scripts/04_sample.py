"""Build the small, committed pilot sample: detector x 15-minute table.

Reads lane-level Parquet from data/interim/traffic/ and writes
data/sample/traffic_15min_<start>_<end>.csv.gz

Two speed columns are kept on purpose, so the effect of the cleaning rule can be
measured directly:
  speed_naive   plain mean over all lane readings (what you get with no cleaning)
  speed_clean   volume-weighted mean over readings with valid == 'Y' and volume > 0
                (drops the placeholder speeds that TD reports when a lane has no traffic)

Usage:  python scripts/04_sample.py 2025-07-27 2025-08-16
"""
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from hkrt.archive import daterange  # noqa: E402
from hkrt.parse import fix_midnight_date  # noqa: E402

IN = ROOT / "data" / "interim" / "traffic"
OUT = ROOT / "data" / "sample"


def aggregate(df: pd.DataFrame) -> pd.DataFrame:
    df = df.drop_duplicates(["obs_time", "detector_id", "lane"])  # same 30-s period can appear in 2 snapshots
    df["t15"] = df["obs_time"].dt.floor("15min")
    ok = (df["valid"] == "Y") & (df["volume"] > 0)
    df["w_speed"] = np.where(ok, df["speed"] * df["volume"], 0.0)
    df["w_vol"] = np.where(ok, df["volume"], 0.0)
    df["vol_valid"] = np.where(df["valid"] == "Y", df["volume"], np.nan)
    df["occ_valid"] = np.where(df["valid"] == "Y", df["occupancy"], np.nan)
    g = df.groupby(["detector_id", "t15"], observed=True)
    out = g.agg(
        n_readings=("speed", "size"),
        n_invalid=("valid", lambda s: (s == "N").sum()),
        n_zero_volume=("volume", lambda s: (s == 0).sum()),
        n_speed_over_130=("speed", lambda s: (s > 130).sum()),
        speed_naive=("speed", "mean"),
        w_speed=("w_speed", "sum"),
        w_vol=("w_vol", "sum"),
        volume_sum=("vol_valid", "sum"),
        occupancy_mean=("occ_valid", "mean"),
    ).reset_index()
    out["speed_clean"] = (out["w_speed"] / out["w_vol"]).where(out["w_vol"] > 0)
    out = out.drop(columns=["w_speed", "w_vol"])
    num = out.select_dtypes("number").columns
    out[num] = out[num].round(2)
    return out


COLS = ["snapshot", "obs_time", "detector_id", "lane", "speed", "occupancy", "volume", "valid"]


def load(d: date) -> pd.DataFrame | None:
    p = IN / f"lanes_{d:%Y%m%d}.parquet"
    return pd.read_parquet(p, columns=COLS) if p.exists() else None


def main(start: str, end: str):
    # Observations lag snapshots by ~5-10 min, so the last minutes of day d sit
    # in the file for day d+1. Load both and keep obs_time within day d.
    frames = []
    for d in daterange(date.fromisoformat(start), date.fromisoformat(end)):
        parts = [x for x in (load(d), load(d + timedelta(days=1))) if x is not None]
        if not parts:
            print("missing", d); continue
        x = fix_midnight_date(pd.concat(parts, ignore_index=True))
        x = x[x["obs_time"].dt.date == d]
        frames.append(aggregate(x))
    df = pd.concat(frames, ignore_index=True).sort_values(["t15", "detector_id"])
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"traffic_15min_{start.replace('-', '')}_{end.replace('-', '')}.csv.gz"
    df.to_csv(path, index=False, compression="gzip")
    print(path.name, df.shape, f"{path.stat().st_size/1e6:.1f} MB")


if __name__ == "__main__":
    main(*sys.argv[1:3])
