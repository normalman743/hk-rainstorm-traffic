"""EDA of the L3 table: coverage, the rain events of the three months, speed and flow against
rain and warning level, and the 2025-08-05 Black Rainstorm.

    python -m src.analysis.eda

Figures: report/figures/eda_*.pdf. Numbers: report/results/eda.json (the report cites them).
Slots with a TC signal >= 8 are left out (P11) unless a figure says otherwise.
"""

from __future__ import annotations

import duckdb
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

from src.analysis.common import FIG_DIR, LEVEL_COLOURS, LEVEL_NAMES, RAIN_BINS, con_l3, save_json, style
from src.l3 import L2_DIR, TC_MAX


def coverage(con: duckdb.DuckDBPyConnection, out: dict) -> None:
    df = con.sql("""select date, month, avg(coverage) as coverage, count(distinct detector_id) as detectors
                    from t where not interpolated group by all order by date""").df()
    out["coverage"] = {m: {"mean_share_of_periods": round(g.coverage.mean(), 3),
                           "detectors_per_day_median": int(g.detectors.median())}
                       for m, g in df.groupby("month")}
    fig, axes = plt.subplots(1, 3, figsize=(7, 2.2), sharey=True)
    for ax, (m, g) in zip(axes, df.groupby("month")):
        ax.bar(g.date, g.coverage, color="#4c72b0", width=0.8)
        ax.set_title(f"{m[:4]}-{m[4:]}")
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%d"))
        ax.set_ylim(0, 1)
    axes[0].set_ylabel("share of 30-s\nperiods present")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "eda_coverage.pdf")
    plt.close(fig)


def events(con: duckdb.DuckDBPyConnection, out: dict) -> None:
    """Territory rain (highest district `high`) and warning level per hour, per month."""
    df = con.sql("""select date_trunc('hour', slot) as hour, month, max(rain_max) as rain_max,
                           max(warn_level) as warn, max(tc_signal) as tc
                    from t group by all order by hour""").df()
    s4 = con.sql(f"""select * from read_parquet('{L2_DIR / 's4' / 'rainstorm.parquet'}')
                     where strftime(start, '%Y%m') in ('202405', '202507', '202508')""").df()
    out["warnings"] = {LEVEL_NAMES[lv]: {"signals": int((s4.level == lv).sum()),
                                          "hours": round(float(((s4.end - s4.start)[s4.level == lv]).dt.total_seconds().sum() / 3600), 1)}
                       for lv in (1, 2, 3)}
    fig, axes = plt.subplots(3, 1, figsize=(7, 4.6))
    for ax, (m, g) in zip(axes, df.groupby("month")):
        ax.bar(g.hour, g.rain_max, width=1 / 24, color="#4c72b0", label="highest district rain (mm/h)")
        for r in s4[s4.start.dt.strftime("%Y%m") == m].itertuples():
            ax.axvspan(r.start, r.end, color=LEVEL_COLOURS[r.level], alpha=0.35, lw=0)
        tc = g[g.tc >= TC_MAX]
        if len(tc):
            ax.plot(tc.hour, [g.rain_max.max() * 1.05] * len(tc), "k|", ms=4)
        ax.set_ylabel(f"{m[:4]}-{m[4:]}\nmm/h")
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%d"))
        ax.margins(x=0)
    from matplotlib.patches import Patch
    handles = [Patch(color="#4c72b0", label="highest district rain (mm/h)")] + [
        Patch(color=LEVEL_COLOURS[lv], alpha=0.35, label=LEVEL_NAMES[lv]) for lv in (1, 2, 3)] + [
        plt.Line2D([], [], color="k", marker="|", ls="", label=f"TC signal ≥ {TC_MAX}")]
    axes[0].legend(handles=handles, loc="upper right", fontsize=6, ncol=5)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "eda_events.pdf")
    plt.close(fig)


def by_warning_and_rain(con: duckdb.DuckDBPyConnection, out: dict) -> None:
    lv = con.sql(f"""select warn_level, count(*) as slots, count(distinct detector_id) as detectors,
                            median(ratio) as speed_ratio, quantile_cont(ratio, 0.1) as speed_p10,
                            median(flow_ratio) as flow_ratio, median(occupancy / nullif(base_occupancy, 0)) as occ_ratio
                     from t where tc_signal < {TC_MAX} and not interpolated group by 1 order by 1""").df()
    out["by_warning"] = lv.round(4).to_dict(orient="records")
    cases = " ".join(f"when rain_mid <= {hi} then '{lab}'" for lab, hi in RAIN_BINS[:-1])
    rb = con.sql(f"""select case when rain_mid = 0 then '0' {cases} else '{RAIN_BINS[-1][0]}' end as rain_bin,
                            warn_level = 0 as no_warning, count(*) as slots, median(ratio) as speed_ratio,
                            median(flow_ratio) as flow_ratio
                     from t where tc_signal < {TC_MAX} and not interpolated group by all""").df()
    order = ["0"] + [lab for lab, _ in RAIN_BINS]
    rb["rain_bin"] = pd.Categorical(rb.rain_bin, order)
    rb = rb.sort_values(["no_warning", "rain_bin"])
    out["by_rain"] = rb.assign(rain_bin=rb.rain_bin.astype(str)).round(4).to_dict(orient="records")

    fig, axes = plt.subplots(1, 2, figsize=(7, 2.6))
    x = range(len(lv))
    axes[0].bar([i - 0.2 for i in x], lv.speed_ratio, 0.4, label="speed", color="#4c72b0")
    axes[0].bar([i + 0.2 for i in x], lv.flow_ratio, 0.4, label="flow", color="#dd8452")
    axes[0].set_xticks(list(x), [LEVEL_NAMES[v] for v in lv.warn_level])
    axes[0].axhline(1, color="k", lw=0.6)
    axes[0].set_ylim(0.5, 1.05)
    axes[0].set_ylabel("median ratio to dry baseline")
    axes[0].legend(fontsize=7)
    axes[0].set_title("by warning level")
    for nw, g in rb.groupby("no_warning", observed=True):
        lab = "no warning" if nw else "warning"
        axes[1].plot(g.rain_bin.astype(str), g.speed_ratio, "o-", label=f"speed, {lab}")
        axes[1].plot(g.rain_bin.astype(str), g.flow_ratio, "s--", label=f"flow, {lab}")
    axes[1].axhline(1, color="k", lw=0.6)
    axes[1].set_xlabel("district rain, midpoint (mm/h)")
    axes[1].tick_params(axis="x", labelsize=7)
    axes[1].legend(fontsize=6)
    axes[1].set_title("by rain intensity")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "eda_by_warning_rain.pdf")
    plt.close(fig)


def by_hour(con: duckdb.DuckDBPyConnection, out: dict) -> None:
    """Weekdays: the speed and flow ratio by hour of day, dry vs any warning."""
    df = con.sql(f"""select slot_of_day // 60 as hour, warn_level > 0 as warning, median(ratio) as speed_ratio,
                            median(flow_ratio) as flow_ratio, count(*) as slots
                     from t where tc_signal < {TC_MAX} and day_type = 'weekday' and not interpolated
                       and (warn_level > 0 or dry) group by all order by all""").df()
    w = df[df.warning]
    out["by_hour_weekday_warning"] = w.round(4).to_dict(orient="records")
    fig, ax = plt.subplots(figsize=(3.5, 2.4))
    ax.plot(w.hour, w.speed_ratio, "o-", label="speed ratio")
    ax.plot(w.hour, w.flow_ratio, "s--", label="flow ratio")
    ax.axhline(1, color="k", lw=0.6)
    ax.set_xlabel("hour of day (weekdays, under a warning)")
    ax.set_ylabel("median ratio")
    ax.legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "eda_by_hour.pdf")
    plt.close(fig)


def level_at_equal_rain(con: duckdb.DuckDBPyConnection, out: dict) -> None:
    """Speed and flow ratio by warning level within the same district-rain bin: separates the
    warning (territory-wide) from the rain where the detector is."""
    cases = " ".join(f"when rain_mid <= {hi} then '{lab}'" for lab, hi in RAIN_BINS[:-1])
    df = con.sql(f"""select case when rain_mid = 0 then '0' {cases} else '{RAIN_BINS[-1][0]}' end as rain_bin,
                            warn_level, count(*) as slots, median(ratio) as speed_ratio,
                            median(flow_ratio) as flow_ratio
                     from t where tc_signal < {TC_MAX} and not interpolated group by all""").df()
    df["rain_bin"] = pd.Categorical(df.rain_bin, ["0"] + [lab for lab, _ in RAIN_BINS])
    df = df.sort_values(["rain_bin", "warn_level"])
    out["by_rain_and_level"] = df.assign(rain_bin=df.rain_bin.astype(str)).round(4).to_dict(orient="records")
    fig, axes = plt.subplots(1, 2, figsize=(7, 2.4), sharex=True)
    for lv, g in df.groupby("warn_level"):
        g = g[g.slots >= 300]
        colour = LEVEL_COLOURS.get(lv, "#4c72b0")
        axes[0].plot(g.rain_bin.astype(str), g.speed_ratio, "o-", color=colour, label=LEVEL_NAMES[lv])
        axes[1].plot(g.rain_bin.astype(str), g.flow_ratio, "s--", color=colour, label=LEVEL_NAMES[lv])
    for ax, what in zip(axes, ("speed", "flow")):
        ax.axhline(1, color="k", lw=0.6)
        ax.set_xlabel("district rain, midpoint (mm/h)")
        ax.set_ylabel(f"median {what} ratio")
    axes[0].legend(fontsize=7, title="warning", title_fontsize=7)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "eda_level_at_equal_rain.pdf")
    plt.close(fig)


def onset(con: duckdb.DuckDBPyConnection, out: dict) -> None:
    """Speed and flow ratio by minutes since the warning episode began, per current level."""
    bins = [0, 30, 60, 120, 240, 480, 10_000]
    labels = ["0-30", "30-60", "60-120", "120-240", "240-480", ">480"]
    case = " ".join(f"when warn_minutes < {hi} then '{lab}'" for lab, hi in zip(labels, bins[1:]))
    df = con.sql(f"""select case {case} end as since, warn_level, count(*) as slots,
                            median(ratio) as speed_ratio, median(flow_ratio) as flow_ratio,
                            median(rain_mid) as rain_mid
                     from t where warn_level > 0 and tc_signal < {TC_MAX} and not interpolated
                     group by all""").df()
    df["since"] = pd.Categorical(df.since, labels)
    df = df.sort_values(["warn_level", "since"])
    out["by_minutes_since_issue"] = df.assign(since=df.since.astype(str)).round(4).to_dict(orient="records")
    fig, axes = plt.subplots(1, 2, figsize=(7, 2.4), sharex=True)
    for lv, g in df.groupby("warn_level"):
        g = g[g.slots >= 500]
        axes[0].plot(g.since.astype(str), g.speed_ratio, "o-", color=LEVEL_COLOURS[lv], label=LEVEL_NAMES[lv])
        axes[1].plot(g.since.astype(str), g.flow_ratio, "s--", color=LEVEL_COLOURS[lv], label=LEVEL_NAMES[lv])
    for ax, what in zip(axes, ("speed", "flow")):
        ax.axhline(1, color="k", lw=0.6)
        ax.set_xlabel("minutes since the warning episode began")
        ax.set_ylabel(f"median {what} ratio")
        ax.tick_params(axis="x", labelsize=7)
    axes[0].legend(fontsize=7, title="level now", title_fontsize=7)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "eda_onset.pdf")
    plt.close(fig)


def black_rainstorm(con: duckdb.DuckDBPyConnection, out: dict) -> None:
    """2025-08-05: the territory median ratio per slot, 08-04 18:00 to 08-06 06:00."""
    df = con.sql("""select slot, median(ratio) as speed_ratio, median(flow_ratio) as flow_ratio,
                           max(warn_level) as warn, avg(rain_mid) as rain_mean, max(rain_max) as rain_max,
                           count(*) as detectors
                    from t where slot between '2025-08-04 18:00' and '2025-08-06 06:00' group by 1 order by 1""").df()
    black = df[df.warn == 3]
    out["black_2025_08_05"] = {
        "slots_black": int(len(black)),
        "median_speed_ratio_black": round(float(black.speed_ratio.median()), 4),
        "median_flow_ratio_black": round(float(black.flow_ratio.median()), 4),
        "min_speed_ratio": round(float(df.speed_ratio.min()), 4),
        "min_speed_ratio_slot": str(df.slot[df.speed_ratio.idxmin()]),
        "min_flow_ratio": round(float(df.flow_ratio.min()), 4),
        "rain_max_mm_h": float(df.rain_max.max()),
    }
    fig, ax = plt.subplots(figsize=(7, 2.6))
    ax.plot(df.slot, df.speed_ratio, label="speed ratio (median of detectors)")
    ax.plot(df.slot, df.flow_ratio, "--", label="flow ratio (median of detectors)")
    ax.axhline(1, color="k", lw=0.6)
    for lv in (1, 2, 3):
        on = df.warn == lv
        for s in df.slot[on]:
            ax.axvspan(s, s + pd.Timedelta(minutes=15), color=LEVEL_COLOURS[lv], alpha=0.3, lw=0)
    ax2 = ax.twinx()
    ax2.bar(df.slot, df.rain_max, width=15 / 1440, color="#4c72b0", alpha=0.3)
    ax2.set_ylabel("highest district rain (mm/h)")
    ax.set_ylabel("ratio to dry baseline")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %H:%M"))
    ax.legend(fontsize=7, loc="lower left")
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(FIG_DIR / "eda_black_20250805.pdf")
    plt.close(fig)


def main() -> None:
    style()
    con = con_l3()
    out: dict = {}
    for step in (coverage, events, by_warning_and_rain, level_at_equal_rain, by_hour, onset, black_rainstorm):
        step(con, out)
        print(f"eda: {step.__name__} done", flush=True)
    save_json("eda", out)


if __name__ == "__main__":
    main()
