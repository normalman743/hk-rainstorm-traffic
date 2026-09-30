"""RQ3: how much do the preprocessing choices change the RQ1 ranking and the RQ2 accuracy?

    python -m src.analysis.rq3

One step changed at a time (PROPOSAL.md P1-P11), the others at their defaults. P1-P8 and P10
rebuild the L3 table (src.l3); P9 changes the warning features and P11 the slots used.

Per variant:
    RQ1   s_warn and s_rain per detector (src.analysis.rq1.measures): Spearman with the default
          over the detectors ranked in both, overlap of the 20 most sensitive (s_warn), and
          the median speed and flow ratio under each warning level
    RQ2   LightGBM with all features (src.analysis.rq2), folds fixed by event
          ((event - 1) mod FOLDS, the same for every variant), each fold's training slots
          subsampled to TRAIN_ROWS: MAE on the wet test slots, skill = 1 - MAE / MAE of the
          baseline (ratio = 1) on the same slots (the target itself changes with the
          variant, so skill is the comparable number), F1 of congestion under Red / Black

Output: report/results/rq3.json, report/results/rq3.csv, figure rq3_ablation.pdf.
"""

from __future__ import annotations

import time as clock

import lightgbm as lgb
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.metrics import f1_score, mean_absolute_error

from src import l3
from src.analysis import rq1, rq2
from src.analysis.common import FIG_DIR, RESULTS_DIR, save_json, style
from src.l3 import L3_DIR, Options

FOLDS = 5
TRAIN_ROWS = 1_000_000
TOP = 20
LGB_PARAMS = {**rq2.LGB_PARAMS, "n_estimators": 200}

# (step, label, L3 options, analysis change)
VARIANTS = [
    ("-", "default", Options(), None),
    ("P1", "keep valid = N", Options(valid="keep"), None),
    ("P1", "drop block if any lane N", Options(valid="drop_block"), None),
    ("P2", "no outlier bounds", Options(outliers="none"), None),
    ("P2", "bounds + robust z per lane", Options(outliers="robust_z"), None),
    ("P3", "keep stuck lanes", Options(stuck="keep"), None),
    ("P4", "mean speed (all readings)", Options(speed_agg="mean"), None),
    ("P4", "slowest lane", Options(speed_agg="slowest"), None),
    ("P5", "5-min slots", Options(minutes=5), None),
    ("P5", "60-min slots", Options(minutes=60), None),
    ("P6", "no gap interpolation", Options(gaps="none"), None),
    ("P7", "rain: upper bound", Options(rain_value="high"), None),
    ("P7", "rain: territory max", Options(rain_value="max"), None),
    ("P8", "rain: hour before", Options(rain_lag=1), None),
    ("P9", "warning: any / none", Options(), "warn_binary"),
    ("P9", "no warning features", Options(), "warn_none"),
    ("P10", "baseline per month", Options(baseline="month"), None),
    ("P10", "baseline all months", Options(baseline="all"), None),
    ("P11", "keep TC signal >= 8", Options(), "keep_tc"),
]


def _rq1(o: Options, change: str | None) -> tuple[pd.DataFrame, pd.DataFrame]:
    df = rq1.slots(o, tc_max=99 if change == "keep_tc" else l3.TC_MAX)
    levels = df.groupby("warn_level").agg(speed=("ratio", "median"), flow=("flow_ratio", "median"))
    return rq1.measures(df), levels


def _rq2(o: Options, change: str | None) -> dict:
    df = rq2.data(o, tc_max=99 if change == "keep_tc" else l3.TC_MAX)
    feats = list(rq2.FEATURE_SETS["+rain+warning"])
    if change == "warn_binary":
        df["warn_any"] = (df.warn_level > 0).astype(int)
        feats = [f for f in feats if f != "warn_level"] + ["warn_any"]
    elif change == "warn_none":
        feats = [f for f in feats if f not in rq2.WARN]
    fold = (df.event.to_numpy() - 1) % FOLDS
    y = df.ratio.to_numpy()
    wet = ((df.rain_mid > 0) | (df.warn_level > 0)).to_numpy()
    severe = (df.warn_level >= 2).to_numpy()
    pred = np.full(len(df), np.nan)
    cls = np.zeros(len(df), bool)
    rng = np.random.default_rng(rq2.SEED)
    for k in range(FOLDS):
        tr = np.flatnonzero(fold != k)
        te = np.flatnonzero(fold == k)
        if len(tr) > TRAIN_ROWS:
            tr = rng.choice(tr, TRAIN_ROWS, replace=False)
        X = df[feats]
        pred[te] = lgb.LGBMRegressor(objective="l1", **LGB_PARAMS).fit(X.iloc[tr], y[tr]).predict(X.iloc[te])
        cls[te] = lgb.LGBMClassifier(is_unbalance=True, **LGB_PARAMS).fit(X.iloc[tr], y[tr] < rq2.CONGESTED) \
            .predict(X.iloc[te])
    mae = mean_absolute_error(y[wet], pred[wet])
    mae0 = mean_absolute_error(y[wet], np.ones(wet.sum()))
    return {"slots": len(df), "mae_wet": mae, "mae_wet_baseline": mae0, "skill_wet": 1 - mae / mae0,
            "f1_severe": f1_score(y[severe] < rq2.CONGESTED, cls[severe], zero_division=0),
            "congested_share_severe": float((y[severe] < rq2.CONGESTED).mean())}


def main() -> None:
    style()
    rows, default = [], None
    for step, label, o, change in VARIANTS:
        start = clock.time()
        if not (L3_DIR / f"{o.name()}.parquet").exists():
            l3.build(o)
        m, levels = _rq1(o, change)
        if default is None:
            default = m
        r = {"step": step, "variant": label, "l3": o.name(), "analysis": change or "-"}
        for col in ("s_warn", "s_rain"):
            both = pd.concat([default[col], m[col]], axis=1, keys=["d", "v"]).dropna()
            r[f"{col}_spearman"] = spearmanr(both.d, both.v)[0]
            r[f"{col}_detectors"] = len(both)
        r["top20_overlap"] = len(set(default.s_warn.dropna().nsmallest(TOP).index)
                                 & set(m.s_warn.dropna().nsmallest(TOP).index))
        for lv, name in ((1, "amber"), (2, "red"), (3, "black")):
            r[f"speed_{name}"] = levels.speed.get(lv, np.nan)
            r[f"flow_{name}"] = levels.flow.get(lv, np.nan)
        r.update(_rq2(o, change))
        rows.append(r)
        print(f"rq3: {step} {label}: {clock.time() - start:.0f} s  "
              f"rho={r['s_warn_spearman']:.3f} top20={r['top20_overlap']} skill={r['skill_wet']:.3f} "
              f"f1={r['f1_severe']:.3f}", flush=True)
        pd.DataFrame(rows).to_csv(RESULTS_DIR / "rq3.csv", index=False)
    res = pd.DataFrame(rows)
    save_json("rq3", {"variants": res.round(5).to_dict(orient="records"),
                      "train_rows": TRAIN_ROWS, "folds": FOLDS, "top": TOP})
    figure(res)


def figure(res: pd.DataFrame) -> None:
    lab = [f"{s} {v}" for s, v in zip(res.step, res.variant)]
    fig, axes = plt.subplots(1, 4, figsize=(7, 3.6), sharey=True)
    for ax, col, title in ((axes[0], "s_warn_spearman", "RQ1 ranking ρ"),
                           (axes[1], "top20_overlap", f"top-{TOP} overlap"),
                           (axes[2], "speed_black", "speed ratio, Black"),
                           (axes[3], "skill_wet", "RQ2 skill (wet)")):
        ax.barh(lab, res[col], color=["#888888"] + ["#4c72b0"] * (len(res) - 1))
        ax.axvline(res[col].iloc[0], color="k", lw=0.6)
        ax.set_title(title)
    axes[0].tick_params(axis="y", labelsize=6)
    axes[0].invert_yaxis()
    fig.tight_layout()
    fig.savefig(FIG_DIR / "rq3_ablation.pdf")
    plt.close(fig)


if __name__ == "__main__":
    main()
