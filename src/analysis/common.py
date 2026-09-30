"""What the analysis scripts share: where figures and numbers go, the L3 connection, labels."""

from __future__ import annotations

import json

import duckdb
import matplotlib
import numpy as np

from src.config import ROOT
from src.l3 import L3_DIR, Options

matplotlib.use("Agg")

FIG_DIR = ROOT / "report" / "figures"
RESULTS_DIR = ROOT / "report" / "results"
LEVEL_NAMES = {0: "none", 1: "Amber", 2: "Red", 3: "Black"}
LEVEL_COLOURS = {1: "#f2b701", 2: "#d62728", 3: "#222222"}
# District rain (midpoint, mm/h) bins above 0: (label, upper bound); the last is open.
RAIN_BINS = [("0-5", 5), ("5-10", 10), ("10-20", 20), ("20-40", 40), (">40", None)]


def style() -> None:
    import matplotlib.pyplot as plt

    FIG_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.size": 8, "axes.titlesize": 8, "figure.dpi": 150,
                         "axes.spines.top": False, "axes.spines.right": False})


def con_l3(o: Options = Options()) -> duckdb.DuckDBPyConnection:
    """A DuckDB connection with view `t` on the L3 table of options `o`."""
    con = duckdb.connect()
    con.sql("set enable_progress_bar = false")
    con.sql(f"create view t as select * from read_parquet('{L3_DIR / (o.name() + '.parquet')}')")
    return con


def _plain(x):
    if isinstance(x, dict):
        return {str(k): _plain(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_plain(v) for v in x]
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (np.floating,)):
        return float(x)
    if isinstance(x, (np.bool_,)):
        return bool(x)
    return x


def save_json(name: str, out: dict) -> None:
    path = RESULTS_DIR / f"{name}.json"
    path.write_text(json.dumps(_plain(out), indent=1, default=str))
    print(f"{path}")
