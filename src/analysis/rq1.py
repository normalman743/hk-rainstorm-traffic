"""RQ1: which detectors (roads) and districts are most sensitive to rainstorms?

    python -m src.analysis.rq1

Per detector, from the L3 table (TC signal >= 8 left out, interpolated slots left out):
    s_warn   median speed ratio under Red or Black, minus 1 (the proposal's measure; Red and
             Black pooled because Black alone is 4 episodes)
    s_rain   median speed ratio with district rain (midpoint) >= RAIN_HEAVY mm/h, minus 1
    s_warn_adj  s_warn adjusted for exposure: minus b x (exposure - mean exposure), b the slope
             of s_warn on exposure over the detectors, exposure the median district rain
             while Red / Black was in force
    slope    the detector's slope of speed ratio on district rain (per 10 mm/h) from a mixed
             model: ratio ~ rain + (1 + rain | detector), on the slots with rain or a warning
A detector is ranked on a measure only with at least MIN_SLOTS slots behind it.

Stability: the rainy days are split in two halves by rain event (odd / even event number, an
event being a calendar day with a warning or district rain >= RAIN_HEAVY somewhere), each
measure computed per half, and the Spearman correlation of the halves reported.

Output: report/results/rq1.json, report/results/rq1_detectors.csv, figures rq1_*.pdf.
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from scipy.stats import spearmanr

from src.analysis.common import FIG_DIR, RESULTS_DIR, con_l3, save_json, style
from src.l3 import Options, TC_MAX

RAIN_HEAVY = 10
MIN_SLOTS = 20
MIXED_SAMPLE = 300_000
SEED = 5001


def slots(o: Options = Options(), tc_max: int = TC_MAX) -> pd.DataFrame:
    """The slots RQ1 uses, with the rain-event number of their day."""
    con = con_l3(o)
    days = con.sql(f"""select date from t where tc_signal < {tc_max}
                       group by date having max(warn_level) > 0 or max(rain_mid) >= {RAIN_HEAVY}
                       order by date""").df()
    days["event"] = range(len(days))
    con.register("days", days)
    return con.sql(f"""select detector_id, t.date, rain_district as district, latitude, longitude, road, direction,
                              n_lanes, base_speed, base_occupancy, ratio, flow_ratio, rain_mid, warn_level, days.event
                       from t left join days using (date)
                       where tc_signal < {tc_max} and not interpolated""").df()


def measures(df: pd.DataFrame) -> pd.DataFrame:
    """s_warn and s_rain per detector, with their slot counts."""
    warn = df[df.warn_level >= 2].groupby("detector_id").ratio.agg(["median", "size"])
    rain = df[df.rain_mid >= RAIN_HEAVY].groupby("detector_id").ratio.agg(["median", "size"])
    out = pd.DataFrame({"s_warn": warn["median"] - 1, "n_warn": warn["size"],
                        "s_rain": rain["median"] - 1, "n_rain": rain["size"]})
    out.loc[out.n_warn < MIN_SLOTS, "s_warn"] = np.nan
    out.loc[out.n_rain < MIN_SLOTS, "s_rain"] = np.nan
    return out


def mixed_slopes(df: pd.DataFrame, out: dict) -> pd.Series:
    """Per-detector slope of speed ratio on rain (per 10 mm/h): fixed + random slope."""
    wet = df[(df.rain_mid > 0) | (df.warn_level > 0)]
    sample = wet.sample(min(MIXED_SAMPLE, len(wet)), random_state=SEED).assign(rain10=lambda d: d.rain_mid / 10)
    model = smf.mixedlm("ratio ~ rain10", sample, groups=sample.detector_id, re_formula="~rain10")
    fit = model.fit(method="lbfgs")
    out["mixed_model"] = {"rows": len(sample), "fixed_intercept": fit.fe_params["Intercept"],
                          "fixed_rain_per_10mm": fit.fe_params["rain10"],
                          "fixed_rain_se": fit.bse["rain10"],
                          "random_sd_intercept": float(np.sqrt(fit.cov_re.iloc[0, 0])),
                          "random_sd_slope": float(np.sqrt(fit.cov_re.iloc[1, 1])),
                          "converged": bool(fit.converged)}
    re = pd.DataFrame(fit.random_effects).T
    return fit.fe_params["rain10"] + re["rain10"]


def stability(df: pd.DataFrame, out: dict) -> None:
    halves = [measures(df[(df.event % 2 == k) | df.event.isna() & (df.warn_level == 0)]) for k in (0, 1)]
    res = {}
    for m in ("s_warn", "s_rain"):
        both = pd.concat([halves[0][m], halves[1][m]], axis=1, keys=["a", "b"]).dropna()
        rho = spearmanr(both.a, both.b)[0] if len(both) > 2 else float("nan")
        top_a = set(both.a.nsmallest(50).index)
        top_b = set(both.b.nsmallest(50).index)
        res[m] = {"detectors": len(both), "spearman": rho, "top50_overlap": len(top_a & top_b)}
    out["split_half"] = res


def main() -> None:
    style()
    out: dict = {}
    df = slots()
    det = measures(df)
    det["slope"] = mixed_slopes(df, out)
    attrs = df.groupby("detector_id").agg(district=("district", "first"), road=("road", "first"),
                                          latitude=("latitude", "first"), longitude=("longitude", "first"),
                                          direction=("direction", "first"), n_lanes=("n_lanes", "median"),
                                          base_speed=("base_speed", "median"))
    det = attrs.join(det)
    severe = df[df.warn_level >= 2]
    det["flow_warn"] = severe.groupby("detector_id").flow_ratio.median() - 1
    # Exposure: how much rain the detector's district had while Red / Black was in force.
    det["exposure"] = severe.groupby("detector_id").rain_mid.median()
    det["base_occupancy"] = df.groupby("detector_id").base_occupancy.median()
    e = det.dropna(subset=["s_warn", "exposure"])
    b = np.polyfit(e.exposure, e.s_warn, 1)
    out["s_warn_on_exposure"] = {"slope_per_mm": b[0], "intercept": b[1],
                                 "spearman": spearmanr(e.s_warn, e.exposure)[0]}
    det["s_warn_adj"] = det.s_warn - b[0] * (det.exposure - e.exposure.mean())
    det = det.sort_values("s_warn")
    det.to_csv(RESULTS_DIR / "rq1_detectors.csv")

    ranked = det.dropna(subset=["s_warn", "s_rain", "slope"])
    out["detectors_ranked"] = {"s_warn": int(det.s_warn.notna().sum()), "s_rain": int(det.s_rain.notna().sum()),
                               "all_three": len(ranked)}
    out["measure_summary"] = det[["s_warn", "s_rain", "slope", "s_warn_adj", "flow_warn", "exposure"]].describe().round(4).to_dict()
    out["spearman_between_measures"] = {
        "s_warn~s_rain": spearmanr(ranked.s_warn, ranked.s_rain)[0],
        "s_warn~slope": spearmanr(ranked.s_warn, ranked.slope)[0],
        "s_rain~slope": spearmanr(ranked.s_rain, ranked.slope)[0],
        "s_warn~s_warn_adj": spearmanr(ranked.s_warn, ranked.s_warn_adj)[0],
        "s_warn_adj~slope": spearmanr(ranked.s_warn_adj, ranked.slope)[0]}
    out["spearman_with_attributes"] = {
        f"{m}~{a}": spearmanr(det[[m, a]].dropna()[m], det[[m, a]].dropna()[a])[0]
        for m in ("s_warn", "s_rain", "s_warn_adj") for a in ("base_speed", "base_occupancy", "n_lanes",
                                                           "flow_warn", "exposure")}
    stability(df, out)
    top = det.dropna(subset=["s_warn"]).head(20)
    out["top20_s_warn"] = top[["road", "district", "s_warn", "n_warn", "s_rain", "slope", "s_warn_adj",
                               "exposure", "base_speed"]].round(4).reset_index().to_dict(orient="records")
    top_adj = det.dropna(subset=["s_warn_adj"]).sort_values("s_warn_adj").head(20)
    out["top20_s_warn_adj"] = top_adj[["road", "district", "s_warn", "s_warn_adj", "exposure"]] \
        .round(4).reset_index().to_dict(orient="records")
    out["top20_overlap_raw_vs_adj"] = len(set(top.index) & set(top_adj.index))
    dist = det.groupby("district").agg(detectors=("s_warn", "count"), s_warn=("s_warn", "median"),
                                       s_rain=("s_rain", "median"), slope=("slope", "median"),
                                       s_warn_adj=("s_warn_adj", "median"),
                                       exposure=("exposure", "median")).sort_values("s_warn")
    out["districts"] = dist.round(4).reset_index().to_dict(orient="records")
    save_json("rq1", out)
    figures(det, dist)


def figures(det: pd.DataFrame, dist: pd.DataFrame) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(7, 3.0))
    d = det.dropna(subset=["s_warn"])
    sc = axes[0].scatter(d.longitude, d.latitude, c=d.s_warn, cmap="RdYlBu", s=6, vmin=-0.25, vmax=0.05)
    axes[0].scatter(d.head(20).longitude, d.head(20).latitude, facecolors="none", edgecolors="k", s=30, lw=0.6)
    fig.colorbar(sc, ax=axes[0], label="s_warn", shrink=0.8)
    axes[0].set_xlabel("longitude")
    axes[0].set_ylabel("latitude")
    axes[0].set_title("circled: 20 most sensitive", fontsize=7)
    axes[0].set_aspect(1 / np.cos(np.radians(22.35)))
    y = range(len(dist))
    axes[1].barh(list(y), dist.s_warn, color="#4c72b0", label="s_warn (Red / Black)")
    axes[1].plot(dist.s_warn_adj, list(y), "o", color="#dd8452", ms=3, label="s_warn adjusted for exposure")
    axes[1].set_yticks(list(y), dist.index, fontsize=6)
    axes[1].axvline(0, color="k", lw=0.6)
    axes[1].set_xlabel("median over the district's detectors")
    axes[1].legend(fontsize=6, loc="lower center", bbox_to_anchor=(0.5, 1.0), ncol=2, frameon=False)
    axes[1].invert_yaxis()
    axes[1].xaxis.set_major_locator(plt.MaxNLocator(4))
    fig.tight_layout()
    fig.savefig(FIG_DIR / "rq1_map_districts.pdf")
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(7, 2.5))
    r = det.dropna(subset=["s_warn", "s_rain"])
    axes[0].scatter(r.s_rain, r.s_warn, s=4, alpha=0.6)
    axes[0].set_xlabel(f"s_rain (district rain ≥ {RAIN_HEAVY} mm/h)")
    axes[0].set_ylabel("s_warn (Red / Black)")
    b = det.dropna(subset=["s_warn", "exposure"])
    axes[1].scatter(b.exposure, b.s_warn, s=4, alpha=0.6)
    axes[1].set_xlabel("exposure: district rain under Red / Black (mm/h, median)")
    axes[1].set_ylabel("s_warn")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "rq1_measures.pdf")
    plt.close(fig)


if __name__ == "__main__":
    main()
