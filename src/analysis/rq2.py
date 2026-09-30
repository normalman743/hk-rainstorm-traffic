"""RQ2: can road attributes and rain / warning features predict the 15-min speed ratio (and
congestion) during rainstorms better than a time-only baseline?

    python -m src.analysis.rq2

Data: the L3 slots of event days (TC signal < 8, not interpolated), an event day being a day
with a warning or district rain >= RAIN_HEAVY somewhere; consecutive event days form one event.
Cross-validation: GroupKFold by event (FOLDS folds), so a storm is never in both train and
test. Scores on the test slots: all, wet (district rain > 0 or a warning), severe (Red/Black).

Targets: speed ratio (regression, MAE); congested = speed ratio < CONGESTED (classification, F1).
Models:
    baseline   ratio = 1 (the detector's dry speed for that day type and slot of day), never
               congested
    linear     ridge regression / logistic regression (one-hot categoricals, scaled numbers)
    lightgbm   gradient boosting (categoricals native)
Feature sets for LightGBM (which information helps): time+road, +rain, +warning, +rain+warning.

Output: report/results/rq2.json, figures rq2_*.pdf.
"""

from __future__ import annotations

import time as clock

import lightgbm as lgb
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import f1_score, mean_absolute_error
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from src.analysis.common import FIG_DIR, con_l3, save_json, style
from src.l3 import Options, TC_MAX

RAIN_HEAVY = 10
CONGESTED = 0.7
FOLDS = 5
SEED = 5001

TIME = ["slot_of_day", "day_type", "holiday"]
ROAD = ["latitude", "longitude", "base_speed", "base_occupancy", "n_lanes", "direction", "rain_district"]
RAIN = ["rain", "rain_lag1", "rain_max"]
WARN = ["warn_level", "warn_minutes"]
CATEGORICAL = ["day_type", "direction", "rain_district"]
FEATURE_SETS = {"time+road": TIME + ROAD, "+rain": TIME + ROAD + RAIN,
                "+warning": TIME + ROAD + WARN, "+rain+warning": TIME + ROAD + RAIN + WARN}
LGB_PARAMS = dict(n_estimators=300, learning_rate=0.05, num_leaves=63, min_child_samples=200,
                  subsample=0.8, subsample_freq=1, colsample_bytree=0.8, random_state=SEED, verbose=-1)


def data(o: Options = Options(), tc_max: int = TC_MAX) -> pd.DataFrame:
    con = con_l3(o)
    days = con.sql(f"""select date from t where tc_signal < {tc_max}
                       group by date having max(warn_level) > 0 or max(rain_mid) >= {RAIN_HEAVY}
                       order by date""").df()
    d = pd.to_datetime(days.date)
    days["event"] = (d.diff() != pd.Timedelta(days=1)).cumsum()
    con.register("days", days)
    df = con.sql(f"""select t.*, days.event from t join days using (date)
                     where tc_signal < {tc_max} and not interpolated""").df()
    for c in CATEGORICAL:
        df[c] = df[c].astype("category")
    df["holiday"] = df.holiday.astype(int)
    return df


def _scores(y: np.ndarray, pred: np.ndarray, cls: np.ndarray | None, masks: dict) -> dict:
    out = {}
    for name, m in masks.items():
        r = {"mae": mean_absolute_error(y[m], pred[m]), "n": int(m.sum())}
        if cls is not None:
            r["f1"] = f1_score(y[m] < CONGESTED, cls[m], zero_division=0)
        out[name] = r
    return out


def _linear(features: list[str]):
    cat = [c for c in features if c in CATEGORICAL]
    num = [c for c in features if c not in CATEGORICAL]
    return ColumnTransformer([("cat", OneHotEncoder(handle_unknown="ignore"), cat),
                              ("num", StandardScaler(), num)])


def cross_validate(df: pd.DataFrame, out: dict) -> pd.DataFrame:
    """Per fold and model: MAE and F1 on the test events. Returns LightGBM gain importance."""
    y = df.ratio.to_numpy()
    wet = ((df.rain_mid > 0) | (df.warn_level > 0)).to_numpy()
    severe = (df.warn_level >= 2).to_numpy()
    rows, importance = [], []
    for fold, (tr, te) in enumerate(GroupKFold(FOLDS).split(df, groups=df.event)):
        masks = {"all": np.ones(len(te), bool), "wet": wet[te], "severe": severe[te]}
        yt = y[te]
        rows.append({"fold": fold, "model": "baseline", "features": "-",
                     **_flat(_scores(yt, np.ones(len(te)), np.zeros(len(te), bool), masks))})
        start = clock.time()
        feats = FEATURE_SETS["+rain+warning"]
        lin = make_pipeline(_linear(feats), Ridge(alpha=1.0)).fit(df.iloc[tr][feats], y[tr])
        logit = make_pipeline(_linear(feats), LogisticRegression(max_iter=300, class_weight="balanced")) \
            .fit(df.iloc[tr][feats], y[tr] < CONGESTED)
        rows.append({"fold": fold, "model": "linear", "features": "+rain+warning",
                     **_flat(_scores(yt, lin.predict(df.iloc[te][feats]), logit.predict(df.iloc[te][feats]), masks))})
        for name, feats in FEATURE_SETS.items():
            reg = lgb.LGBMRegressor(objective="l1", **LGB_PARAMS).fit(df.iloc[tr][feats], y[tr])
            clf = lgb.LGBMClassifier(is_unbalance=True, **LGB_PARAMS).fit(df.iloc[tr][feats], y[tr] < CONGESTED)
            rows.append({"fold": fold, "model": "lightgbm", "features": name,
                         **_flat(_scores(yt, reg.predict(df.iloc[te][feats]), clf.predict(df.iloc[te][feats]), masks))})
            if name == "+rain+warning":
                gain = reg.booster_.feature_importance("gain")
                importance.append(pd.Series(gain / gain.sum(), index=feats, name=fold))
        print(f"rq2: fold {fold} ({len(tr):,} train / {len(te):,} test) in {clock.time() - start:.0f} s", flush=True)
    res = pd.DataFrame(rows)
    out["folds"] = res.round(5).to_dict(orient="records")
    summary = res.drop(columns="fold").groupby(["model", "features"], sort=False).agg(["mean", "std"])
    summary.columns = [f"{a}_{b}" for a, b in summary.columns]
    out["summary"] = summary.round(5).reset_index().to_dict(orient="records")
    return pd.concat(importance, axis=1).mean(axis=1).sort_values(ascending=False)


def _flat(scores: dict) -> dict:
    return {f"{k}_{m}": v for k, r in scores.items() for m, v in r.items()}


def main() -> None:
    style()
    out: dict = {}
    df = data()
    out["data"] = {"slots": len(df), "events": int(df.event.nunique()), "days": int(df.date.nunique()),
                   "detectors": int(df.detector_id.nunique()),
                   "congested_share_all": float((df.ratio < CONGESTED).mean()),
                   "congested_share_severe": float((df.ratio[df.warn_level >= 2] < CONGESTED).mean())}
    print(out["data"], flush=True)
    imp = cross_validate(df, out)
    out["importance_gain"] = imp.round(4).to_dict()
    save_json("rq2", out)
    figures(pd.DataFrame(out["summary"]), imp)


def figures(summary: pd.DataFrame, imp: pd.Series) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(7, 2.4))
    labels = [m if f in ("-", "+rain+warning") and m != "lightgbm" else f"lgb {f}" for m, f in zip(summary.model, summary.features)]
    for ax, col, title in ((axes[0], "wet_mae_mean", "MAE, wet slots"), (axes[1], "severe_f1_mean", "F1 congested, Red/Black")):
        ax.barh(labels, summary[col], xerr=summary[col.replace("mean", "std")], color="#4c72b0")
        ax.set_title(title)
        ax.tick_params(axis="y", labelsize=6)
        ax.invert_yaxis()
    axes[1].set_yticks([])
    imp.head(10).iloc[::-1].plot.barh(ax=axes[2], color="#dd8452")
    axes[2].set_title("LightGBM gain (all features)")
    axes[2].tick_params(axis="y", labelsize=6)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "rq2_models.pdf")
    plt.close(fig)


if __name__ == "__main__":
    main()
