"""
visualize_dataframe.py

Quick, standardized visual sanity-check for any of the analysis-ready
dataframes produced by dataframe_building.py (full_2022_2025.csv,
df_2025.csv, or anything else added to ANALYSES later). This is purely
for eyeballing the data before moving on to correlation analysis / VAR
modeling -- not a polished, presentation-ready deliverable.

USAGE
    Normally run as the "visualisation" step of main.py (project root),
    which calls visualize(). Standalone, on an already-built dataframe:
    python visualize_dataframe.py df_2025
    python visualize_dataframe.py full_2022_2025
    python visualize_dataframe.py "C:\\...\\some_other_dataframe.csv"

    Optional flags:
      --freq D          Resample frequency for the time-series plots
                         (default: "D" = daily mean). Hourly data plotted
                         raw over months/years is an unreadable blob, so
                         this resamples for readability. Pass "raw" to
                         skip resampling (only sensible for a short
                         dataframe, e.g. a single week).
      --time-col NAME    Override auto-detected datetime column.
      --group-col NAME   Override auto-detected grouping column
                         (bidding zone / area).

WHY THIS WORKS FOR FUTURE DATAFRAMES TOO, NOT JUST TODAY'S COLUMNS:
  - The datetime/group columns are auto-detected (analysis_utils.py),
    same candidate-list-plus-override pattern as dataframe_building.py.
  - EVERY numeric feature column gets plotted automatically -- nothing
    is hardcoded to today's specific column names (except the short,
    configurable stats key-feature list, which skips absent columns).
  - Panels are grouped by column NAME PREFIX (the project's own
    b_/c_/da_/id_/x_ naming convention, falling back to "other" for
    anything unrecognized), with large sub-families (like the 24
    da_flow_* columns) automatically split into their own panel so one
    family never crowds out a whole figure.

OUTPUT (written to plots/<dataframe_name>/, one subfolder per plot type)
    timeseries/timeseries_<category>.png     -- one multi-panel figure per category
                                                (dataframes WITHOUT a model spec)

    Dataframes WITH a model spec: every folder below holds only the model's
    variables, split by role (calendar fixed effects are not plotted):
    timeseries/{endogenous,exogenous}/<column>.png        -- hourly, one panel per zone
    distributions/{endogenous,exogenous}/<column>.png
    seasonals/<profile>/{endogenous,exogenous}/<column>.png
        (hour_of_day_by_season: <column>_<zone>.png)
    stats/{endogenous,exogenous}/                          -- the files listed under stats/
                                                              below, for that role's variables
    distributions/distributions_<category>.png
    seasonals/                               -- calendar profiles, in Copenhagen
                                                LOCAL time (so DST doesn't smear
                                                the daily pattern by an hour)
        hour_of_day/hour_of_day_<category>.png                      -- 24 h profile per zone: min-max / 10-90 / 25-75 % bands, mean, median
        hour_of_day_by_season/hour_of_day_by_season_<category>_<zone>.png
        hour_of_week/hour_of_week_<category>.png                    -- 7-day (168 h) profile
        month_of_year/month_of_year_<category>.png
    stats/                                   -- key features only (stats_features); no CSVs
        {daily,weekly,monthly}_std.png, {daily,weekly,monthly}_variance.png
                                             -- std and variance of the hourly values
                                                within each day / Mon-Sun week / month
        rolling_std_7d.png
        absolute_change_timeseries.png       -- daily mean |x[t] - x[t-1]|, in units
"""

import argparse
import math
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # write PNG files directly, no display needed
import matplotlib.dates as mdates
import matplotlib.patheffects as patheffects
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# analysis_utils.py may not be sitting next to this script -- e.g. this
# file can live in src/statsistics/visualisation/ while analysis_utils.py
# stays in src/. Search upward from this file for the folder that has
# it, and add THAT to sys.path, rather than assuming a fixed relative
# depth. Works no matter how these scripts get reorganized later.
_here = Path(__file__).resolve()
for _parent in [_here.parent, *_here.parents]:
    if (_parent / "analysis_utils.py").exists():
        if str(_parent) not in sys.path:
            sys.path.insert(0, str(_parent))
        break
else:
    raise ImportError(
        f"Could not find analysis_utils.py anywhere above {_here} -- "
        f"make sure it's still somewhere in this project's src/ tree."
    )

from analysis_utils import PLOTS_DIR, load_dataframe
from dataframe_building import DERIVED_FEATURES, SOURCES
from dataframe_documentation import column_units

# Subfolders of plots/<name>/ this script owns (main.py clears exactly
# these before a re-run; correlation/ belongs to correlation_analysis.py).
OUTPUT_SUBDIRS = ["missingness", "timeseries", "distributions", "seasonals", "stats"]  # missingness: no longer written, still cleared

# ---------------------------------------------------------------------------
# SEASONAL / STATS CONFIG
# ---------------------------------------------------------------------------
LOCAL_TZ = "Europe/Copenhagen"
SEASON_OF_MONTH = {12: "Winter", 1: "Winter", 2: "Winter", 3: "Spring", 4: "Spring", 5: "Spring",
                   6: "Summer", 7: "Summer", 8: "Summer", 9: "Autumn", 10: "Autumn", 11: "Autumn"}
SEASON_COLORS = {"Winter": "#0072B2", "Spring": "#009E73", "Summer": "#E69F00", "Autumn": "#D55E00"}
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

# Key features for the stats/ folder (main.py can override via
# VISUALISATION_SETTINGS["stats_features"]). Absent columns are skipped.
DEFAULT_STATS_FEATURES = [
    "da_price", "id_vwap", "b_imbalance_price",
    "x_da_id_spread", "x_id_bal_spread",
    "b_mfrr_net_activation_mw", "b_afrr_net_activation_mw",
    "id_transaction_volume_mwh",
    "c_residual_load_actual_mw", "c_residual_load_err",
    "c_wind_total_actual_mw", "c_load_actual_mw",
]
ROLLING_STD_WINDOW = "7D"
ROLLING_STD_MIN_HOURS = 134  # 80% of the 168 hours in the window, same rule as dataframe_building

# ---------------------------------------------------------------------------
# AXIS LABELS — units come from the same metadata as the documentation
# workbook (dataframe_documentation.column_units), so a plot and the Excel
# can never disagree about a column's unit.
# ---------------------------------------------------------------------------
_FREQ_LABELS = {"h": "hourly", "D": "daily mean", "W": "weekly mean", "MS": "monthly mean",
                "ME": "monthly mean", "M": "monthly mean"}


def _freq_label(freq: str | None) -> str:
    if freq is None:
        return "hourly value"
    return _FREQ_LABELS.get(freq, f"{freq} mean")


def _with_unit(text: str, unit: str) -> str:
    return f"{text} [{unit}]" if unit else text


def _squared(unit: str) -> str:
    if not unit:
        return ""
    return f"({unit})²" if ("/" in unit or " " in unit) else f"{unit}²"


def _format_time_axis(ax):
    locator = mdates.AutoDateLocator()
    ax.xaxis.set_major_locator(locator)
    ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(locator))

# ---------------------------------------------------------------------------
# COLOR — fixed, colorblind-safe categorical palette (Okabe-Ito), assigned
# to each group value ONCE and reused everywhere. DK1/DK2 are pinned
# explicitly so they're always the same color across every plot and every
# run; any other group value picks the next unused color, in order, the
# first time it's seen, and keeps it for the rest of the run.
# ---------------------------------------------------------------------------
_PALETTE = ["#0072B2", "#E69F00", "#009E73", "#CC79A7", "#56B4E9", "#D55E00"]
_FIXED_GROUP_COLORS = {"DK1": _PALETTE[0], "DK2": _PALETTE[1]}


def _color_for_group(group: str, seen: dict) -> str:
    if group in _FIXED_GROUP_COLORS:
        return _FIXED_GROUP_COLORS[group]
    if group not in seen:
        seen[group] = _PALETTE[len(seen) % len(_PALETTE)]
    return seen[group]


def _style_axes(ax):
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)


# ---------------------------------------------------------------------------
# FIGURE HELPERS — every multi-panel figure goes through these, so layout,
# legend and saving behave the same everywhere.
# ---------------------------------------------------------------------------
def _grid(n: int, ncols: int, panel_w: float, panel_h: float = 3.1):
    ncols = max(1, min(ncols, n))
    nrows = math.ceil(n / ncols)
    if n == 1:  # one variable per file: wide enough for the title and the legend row
        panel_w, panel_h = max(panel_w, 10), max(panel_h, 4.5)
    fig, axes = plt.subplots(nrows, ncols, figsize=(panel_w * ncols, panel_h * nrows), squeeze=False)
    flat = [axes[i // ncols][i % ncols] for i in range(nrows * ncols)]
    for ax in flat[n:]:
        ax.axis("off")
    return fig, flat[:n]


def _label_panel(ax, title: str, xlabel: str, ylabel: str):
    ax.set_title(title, fontsize=10)
    ax.set_xlabel(xlabel, fontsize=8)
    ax.set_ylabel(ylabel, fontsize=8)
    ax.tick_params(labelsize=8)
    _style_axes(ax)


def _save(fig, axes, title: str, out_path: Path):
    # Legend from ALL panels (deduplicated by label), not just the first —
    # the first panel can be empty, e.g. a column that's constant in a zone.
    handles = {}
    for ax in axes:
        for h, lbl in zip(*ax.get_legend_handles_labels()):
            handles.setdefault(lbl, h)
    # Title, then the legend on its own row underneath it (so a long title
    # and the legend can't overlap), then the panels. Space reserved in
    # inches, so it looks the same for a 1-row and a 10-row figure.
    fig_h = fig.get_size_inches()[1]
    fig.suptitle(title, fontsize=13, y=1 - 0.12 / fig_h, va="top")
    extra_in = 0.25 * title.count("\n")  # each extra title line pushes the legend and panels down
    top_in = 0.55 + extra_in
    if handles:
        legend = fig.legend(list(handles.values()), list(handles.keys()), loc="upper center",
                            bbox_to_anchor=(0.5, 1 - (0.5 + extra_in) / fig_h), ncol=len(handles),
                            frameon=False)
        for line in legend.get_lines():  # very thin data lines (hourly plots): readable legend sample
            if line.get_linewidth() < 1:
                line.set_linewidth(2)
                line.set_alpha(1)
        top_in = 0.9 + extra_in
    fig.tight_layout(rect=(0, 0, 1, 1 - top_in / fig_h))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=130)
    plt.close(fig)
    print(f"  wrote {out_path.parent.name}/{out_path.name}")


# ---------------------------------------------------------------------------
# COLUMN GROUPING
# ---------------------------------------------------------------------------

KNOWN_PREFIXES = ("b", "c", "da", "id", "x")
PREFIX_LABELS = {"b": "balancing", "c": "forecasts_actuals", "da": "day_ahead", "id": "intraday",
                 "x": "cross_market"}


def categorize_columns(feature_cols: list, min_subgroup_size: int = 4) -> dict:
    """Group feature columns into readable panels.

    Step 1: group by the single naming-convention prefix (b_/c_/da_/id_,
    else "other").
    Step 2: within each of those, if a two-token prefix (e.g. "da_flow")
    covers at least `min_subgroup_size` columns, split it out into its
    own panel -- otherwise one big family (like the 24 da_flow_*
    columns) would dominate a single oversized, unreadable figure.

    Fully automatic: no column names are hardcoded, so a future
    dataframe with different columns still gets sensibly sized panels.
    """
    top: dict = {}
    for col in feature_cols:
        first = col.split("_")[0]
        prefix = first if first in KNOWN_PREFIXES else "other"
        top.setdefault(prefix, []).append(col)

    groups: dict = {}
    for prefix, cols in top.items():
        two_token_groups: dict = {}
        for col in cols:
            parts = col.split("_")
            two = "_".join(parts[:2]) if len(parts) > 1 else prefix
            two_token_groups.setdefault(two, []).append(col)
        leftover = []
        for two, sub_cols in two_token_groups.items():
            if two != prefix and len(sub_cols) >= min_subgroup_size:
                groups[two] = sub_cols
            else:
                leftover.extend(sub_cols)
        if leftover:
            groups[prefix] = leftover
    return groups


# ---------------------------------------------------------------------------
# BASIC PLOTS — missingness, time series, distributions
# ---------------------------------------------------------------------------

def plot_timeseries_group(df, time_col, group_col, cols, freq, out_path, label, units):
    fig, axes = _grid(len(cols), 2, 7)
    seen_colors: dict = {}
    for ax, col in zip(axes, cols):
        for group, g in df.groupby(group_col):
            s = g.set_index(time_col)[col].sort_index()
            if freq:
                s = s.resample(freq).mean()
            # Hourly data: thin, slightly transparent lines — tens of thousands
            # of points at the usual width merge into a solid block and the
            # second zone hides the first.
            ax.plot(s.index, s.values, label=str(group), linewidth=1 if freq else 0.3,
                    alpha=1 if freq else 0.75, color=_color_for_group(str(group), seen_colors))
        _label_panel(ax, col, "Delivery time (UTC)",
                     _with_unit(_freq_label(freq).capitalize(), units.get(col, "")))
        _format_time_axis(ax)
    _save(fig, axes, f"{label} — time series ({_freq_label(freq)} per bidding zone)", out_path)


def plot_variable_timeseries(df, time_col, group_col, col, name, role, out_path, unit):
    """One model variable at its hourly values, one panel per zone (stacked,
    shared axes), so neither zone hides the other."""
    zones = sorted(df[group_col].astype(str).unique())
    fig, axes = plt.subplots(len(zones), 1, figsize=(15, 2.9 * len(zones)), sharex=True, sharey=True,
                             squeeze=False)
    axes = axes[:, 0]
    seen_colors: dict = {}
    for ax, zone in zip(axes, zones):
        s = df[df[group_col].astype(str) == zone].set_index(time_col)[col].sort_index()
        ax.plot(s.index, s.values, linewidth=0.3, alpha=0.85, color=_color_for_group(zone, seen_colors))
        ax.axhline(0, color="black", linewidth=0.6, alpha=0.5)
        _label_panel(ax, f"{zone}   (n = {s.notna().sum():,} h, {s.isna().sum():,} missing)",
                     "Delivery time (UTC)" if ax is axes[-1] else "", _with_unit(col, unit))
        _format_time_axis(ax)
    fig.suptitle(f"{name} ({role.lower()}) — hourly values", fontsize=13)
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=130)
    plt.close(fig)
    print(f"  wrote timeseries/{out_path.parent.name}/{out_path.name}")


def model_variables(model_spec, df) -> list:
    """[(column, name, role)] of the spec's endogenous and exogenous
    variables that are in the dataframe. Calendar fixed effects (stored as
    hour / week identifiers) are left out — plots of an index are not
    informative."""
    out = []
    for v in model_spec["variables"]:
        role, col = v["role"], v["column"]
        if role not in ("Endogenous", "Exogenous") or not col or v.get("market") == "Calendar":
            continue
        if col not in df.columns:
            print(f"  WARNING: {col} ({v['name']}) is not in the dataframe — not plotted")
            continue
        out.append((col, v["name"], role))
    return out


def plot_model_variables(df, time_col, group_col, model_spec, out_dir, units, stats=True):
    """Every visualisation folder, for the model's variables only, split
    into endogenous/ and exogenous/ (one file per variable)."""
    variables = model_variables(model_spec, df)
    seasonal_dir = out_dir / "seasonals"
    # A zone where a column is 0 in every hour has no such variable (e.g. a
    # cross-border flow to a counterpart the zone is not connected to): it
    # is left out of that variable's plots, and masked (NaN) for stats/.
    zone_str = df[group_col].astype(str)
    absent = {col: [z for z in sorted(zone_str.unique()) if (df.loc[zone_str == z, col].fillna(0) == 0).all()]
              for col, _, _ in variables}
    df_stats = df.copy()
    for col, zs in absent.items():
        df_stats.loc[zone_str.isin(zs), col] = np.nan
    full_df = df
    for col, name, role in variables:
        r = role.lower()
        df = full_df[~zone_str.isin(absent[col])]
        zones = sorted(df[group_col].astype(str).unique())
        if not zones:
            print(f"  {col}: 0 in every zone — not plotted")
            continue
        plot_variable_timeseries(df, time_col, group_col, col, name, role,
                                 out_dir / "timeseries" / r / f"{col}.png", units.get(col, ""))
        plot_distribution_group(df, group_col, [col], out_dir / "distributions" / r / f"{col}.png",
                                name, units)
        plot_hour_of_day(df, group_col, [col], seasonal_dir / "hour_of_day" / r / f"{col}.png", name, units)
        for zone in zones:
            plot_hour_of_day_by_season(df[df[group_col].astype(str) == zone], zone, [col],
                                       seasonal_dir / "hour_of_day_by_season" / r / f"{col}_{zone}.png",
                                       name, units)
        plot_hour_of_week(df, group_col, [col], seasonal_dir / "hour_of_week" / r / f"{col}.png", name, units)
        plot_month_of_year(df, group_col, [col], seasonal_dir / "month_of_year" / r / f"{col}.png",
                           name, units)
    if stats:
        for role in ("Endogenous", "Exogenous"):
            cols = [c for c, _, rl in variables if rl == role]
            if cols:
                print(f"\n  stats ({role.lower()} variables):")
                make_stats(df_stats, time_col, group_col, cols, out_dir / "stats" / role.lower(), units,
                           label=f"{role} variables")


def plot_distribution_group(df, group_col, cols, out_path, label, units):
    fig, axes = _grid(len(cols), 3, 4.5)
    seen_colors: dict = {}
    for ax, col in zip(axes, cols):
        for group, g in df.groupby(group_col):
            vals = g[col].dropna()
            if vals.empty or vals.nunique() == 1:
                continue  # constant/all-NaN for this group -- nothing to histogram
            ax.hist(vals, bins=50, alpha=0.55, label=str(group),
                     color=_color_for_group(str(group), seen_colors))
        _label_panel(ax, col, _with_unit("Value", units.get(col, "")), "Count [hours]")
    _save(fig, axes, f"{label} — distributions", out_path)


# ---------------------------------------------------------------------------
# SEASONAL PROFILES — averages over calendar position, in Copenhagen local
# time. Each profile pools every year in the dataframe.
# ---------------------------------------------------------------------------

def _add_calendar_columns(df: pd.DataFrame, time_col: str) -> pd.DataFrame:
    local = df[time_col].dt.tz_convert(LOCAL_TZ)
    naive = local.dt.tz_localize(None)
    calendar = pd.DataFrame({
        "_hour": local.dt.hour,
        "_month": local.dt.month,
        "_season": local.dt.month.map(SEASON_OF_MONTH),
        "_hour_of_week": local.dt.dayofweek * 24 + local.dt.hour,
        # Calendar periods for the stats/ std & variance (local time):
        "_period_daily": naive.dt.to_period("D"),
        "_period_weekly": naive.dt.to_period("W-SUN"),  # Monday-Sunday weeks
        "_period_monthly": naive.dt.to_period("M"),
    }, index=df.index)
    return pd.concat([df, calendar], axis=1)  # one concat: avoids a fragmented 100+ column frame


def plot_hour_of_day(df, group_col, cols, out_path, label, units):
    """24 h profile per bidding zone, one panel per zone (same y-axis, so
    the zones are compared on the same scale without hiding each other).
    Per hour of the day: the min-max range over all days (faintest band,
    so the whole dataset is inside the plot), the 10-90 % range (light
    band), the 25-75 % range (dark band), the mean (solid) and the median
    (dashed). The median matters for skewed series: e.g. mFRR activation
    is 0 in ~60 % of hours, so the median sits at 0 while a few large
    activations pull the mean up.
    Layout: one variable -> zones stacked; several -> one row per
    variable, zones side by side."""
    zones = sorted(df[group_col].astype(str).unique())
    single = len(cols) == 1
    nrows, ncols = (len(zones), 1) if single else (len(cols), len(zones))
    panel_w, panel_h = (10, 3.4) if single else (5.5, 3.1)
    fig, grid = plt.subplots(nrows, ncols, figsize=(panel_w * ncols, panel_h * nrows),
                             sharey="col" if single else "row", squeeze=False)
    seen_colors: dict = {}
    outline = [patheffects.Stroke(linewidth=3.2, foreground="white"), patheffects.Normal()]
    hours = range(24)
    axes = []
    for i, col in enumerate(cols):
        for j, zone in enumerate(zones):
            ax = grid[j][0] if single else grid[i][j]
            axes.append(ax)
            color = _color_for_group(zone, seen_colors)
            by_hour = df[df[group_col].astype(str) == zone].groupby("_hour")[col]
            if by_hour.count().sum() > 0:
                q = by_hour.quantile([0.0, 0.10, 0.25, 0.75, 0.90, 1.0]).unstack().reindex(hours)
                mean, median = by_hour.mean().reindex(hours), by_hour.median().reindex(hours)
                ax.fill_between(hours, q[0.0], q[1.0], color=color, alpha=0.08, linewidth=0, zorder=1)
                ax.fill_between(hours, q[0.10], q[0.90], color=color, alpha=0.2, linewidth=0, zorder=1)
                ax.fill_between(hours, q[0.25], q[0.75], color=color, alpha=0.45, linewidth=0, zorder=2)
                ax.plot(hours, mean.values, color=color, linewidth=2, path_effects=outline, zorder=3)
                ax.plot(hours, median.values, color=color, linewidth=1.6, linestyle="--",
                        path_effects=outline, zorder=3)
            ax.set_xticks(range(0, 24, 3))
            ax.set_xlim(0, 23)
            _label_panel(ax, zone if single else f"{col} — {zone}",
                         "Hour (Copenhagen local time)", _with_unit("Value", units.get(col, "")))
    # Legend: what the bands and lines mean (the zone is in each panel's title).
    axes[0].fill_between([], [], [], color="0.3", alpha=0.08, linewidth=0, label="Min–max (all days)")
    axes[0].fill_between([], [], [], color="0.3", alpha=0.2, linewidth=0, label="10–90 % of days")
    axes[0].fill_between([], [], [], color="0.3", alpha=0.45, linewidth=0, label="25–75 % of days")
    axes[0].plot([], [], color="0.3", linewidth=2, label="Mean")
    axes[0].plot([], [], color="0.3", linewidth=1.6, linestyle="--", label="Median")
    _save(fig, axes, f"{label} — 24 h profile per bidding zone: mean, median and spread across days",
          out_path)


def plot_hour_of_day_by_season(df_zone, zone, cols, out_path, label, units):
    fig, axes = _grid(len(cols), 3, 4.5)
    for ax, col in zip(axes, cols):
        for season, color in SEASON_COLORS.items():
            mean = df_zone[df_zone["_season"] == season].groupby("_hour")[col].mean()
            if mean.notna().any():
                ax.plot(mean.index, mean.values, label=season, color=color, linewidth=1.5)
        ax.set_xticks(range(0, 24, 3))
        ax.set_xlim(0, 23)
        _label_panel(ax, col, "Hour", _with_unit("Mean", units.get(col, "")))
    _save(fig, axes, f"{label} — 24 h profile by season, {zone}\n(mean; winter = Dec–Feb, "
                     f"spring = Mar–May, summer = Jun–Aug, autumn = Sep–Nov)", out_path)


def plot_hour_of_week(df, group_col, cols, out_path, label, units):
    fig, axes = _grid(len(cols), 2, 7)
    seen_colors: dict = {}
    for ax, col in zip(axes, cols):
        for zone, g in df.groupby(group_col):
            mean = g.groupby("_hour_of_week")[col].mean()
            if mean.notna().any():
                ax.plot(mean.index, mean.values, label=str(zone), linewidth=1,
                        color=_color_for_group(str(zone), seen_colors))
        for day in range(1, 7):
            ax.axvline(day * 24, color="0.85", linewidth=0.8, zorder=0)
        ax.set_xticks([day * 24 + 12 for day in range(7)])
        ax.set_xticklabels(WEEKDAYS)
        ax.set_xlim(0, 167)
        _label_panel(ax, col, "Day of week, hourly (Copenhagen local time)",
                     _with_unit("Mean", units.get(col, "")))
    _save(fig, axes, f"{label} — average 7-day profile (168 hourly means per bidding zone)", out_path)


def plot_month_of_year(df, group_col, cols, out_path, label, units):
    fig, axes = _grid(len(cols), 3, 4.5)
    seen_colors: dict = {}
    for ax, col in zip(axes, cols):
        for zone, g in df.groupby(group_col):
            mean = g.groupby("_month")[col].mean()
            if mean.notna().any():
                ax.plot(mean.index, mean.values, marker="o", markersize=3, label=str(zone),
                        linewidth=1.2, color=_color_for_group(str(zone), seen_colors))
        ax.set_xticks(range(1, 13))
        ax.set_xticklabels(MONTHS, rotation=45)
        _label_panel(ax, col, "Month (Copenhagen local time)", _with_unit("Mean", units.get(col, "")))
    _save(fig, axes, f"{label} — month-of-year profile (mean per month, all years pooled)", out_path)


# ---------------------------------------------------------------------------
# STATS — std / variance / changes for a short list of key features
# ---------------------------------------------------------------------------

def _hourly_changes(g: pd.DataFrame, time_col: str, col: str):
    """Per-zone series plus its 1-hour change and % change. The previous
    value is looked up by TIME (t - 1 h), not by row, so a gap in the data
    gives NaN instead of silently comparing non-adjacent hours."""
    s = g.set_index(time_col)[col].sort_index()
    prev = s.shift(1, freq="h").reindex(s.index)
    return s, s - prev, (s / prev - 1) * 100


def _stats_summary(df, time_col, group_col, features, units):
    rows, series = [], {}
    for col in features:
        per_zone = {str(z): _hourly_changes(g, time_col, col) for z, g in df.groupby(group_col)}
        values = pd.concat([v for v, _, _ in per_zone.values()]).dropna()
        pct_valid = not values.empty and values.min() > 0
        note = "" if pct_valid else "not computed: series has zero/negative values, so % change is undefined"
        series[col] = per_zone
        scopes = {"all": list(per_zone.values()), **{z: [per_zone[z]] for z in per_zone}}
        for scope, parts in scopes.items():
            v = pd.concat([p[0] for p in parts]).dropna()
            ch = pd.concat([p[1] for p in parts]).dropna()
            pct = pd.concat([p[2] for p in parts]).dropna() if pct_valid else pd.Series(dtype=float)
            rows.append({
                "feature": col, "scope": scope, "unit": units.get(col, ""), "n_obs": len(v),
                "mean": v.mean(), "std": v.std(), "variance": v.var(), "min": v.min(), "max": v.max(),
                "mean_abs_change_1h": ch.abs().mean(), "std_change_1h": ch.std(),
                "pct_change_valid": pct_valid,
                "median_abs_pct_change_1h": pct.abs().median() if pct_valid else None,
                "p95_abs_pct_change_1h": pct.abs().quantile(0.95) if pct_valid else None,
                "pct_change_note": note,
            })
    return pd.DataFrame(rows).round(4), series


def _period_std_var(df, group_col, features, period_col):
    """Std and variance of the hourly values WITHIN each calendar period
    (day / week / month, Copenhagen local time), per zone. A period counts
    as complete when >= 80% of its hours are observed; only complete
    periods are plotted, so a half week at the start or end of the
    dataframe doesn't show up as a misleading point."""
    rows = []
    for zone, g in df.groupby(group_col):
        for period, block in g.groupby(period_col):
            expected_hours = round((period.end_time - period.start_time).total_seconds() / 3600)
            for col in features:
                vals = block[col]
                n = int(vals.notna().sum())
                rows.append({"feature": col, "zone": str(zone), "period": str(period),
                             "period_start": period.start_time, "n_obs": n,
                             "complete": n >= PERIOD_MIN_FRACTION * expected_hours,
                             "std": vals.std(), "variance": vals.var()})
    return pd.DataFrame(rows).round({"std": 4, "variance": 4})


def plot_period_stat(table, features, stat, period_name, out_path, units, label="Key features"):
    fig, axes = _grid(len(features), 2, 7)
    seen_colors: dict = {}
    daily = period_name == "daily"
    within = {"daily": "day", "weekly": "week", "monthly": "month"}[period_name]
    for ax, col in zip(axes, features):
        sub = table[(table["feature"] == col) & table["complete"]]
        for zone, z in sub.groupby("zone"):
            ax.plot(z["period_start"], z[stat].values, marker=None if daily else "o", markersize=3,
                    linewidth=1 if daily else 1.2, label=zone,
                    color=_color_for_group(zone, seen_colors))
        unit = units.get(col, "")
        ylabel = (_with_unit(f"Std within {within}", unit) if stat == "std"
                  else _with_unit(f"Variance within {within}", _squared(unit)))
        _label_panel(ax, col, f"{within.capitalize()} (start, Copenhagen local time)", ylabel)
        _format_time_axis(ax)
    name = "standard deviation" if stat == "std" else "variance"
    extra = " (within-day spread mostly reflects the 24 h shape)" if daily else ""
    _save(fig, axes, f"{label} — {period_name} {name} of hourly values, per bidding zone{extra}",
          out_path)


def plot_rolling_std(df, time_col, group_col, features, out_path, units, label="Key features"):
    fig, axes = _grid(len(features), 2, 7)
    seen_colors: dict = {}
    for ax, col in zip(axes, features):
        for zone, g in df.groupby(group_col):
            s = g.set_index(time_col)[col].sort_index()
            rolling = s.rolling(ROLLING_STD_WINDOW, min_periods=ROLLING_STD_MIN_HOURS).std()
            daily = rolling.resample("D").mean()
            ax.plot(daily.index, daily.values, label=str(zone), linewidth=1,
                    color=_color_for_group(str(zone), seen_colors))
        _label_panel(ax, col, "Delivery time (UTC)",
                     _with_unit("Rolling std, trailing 7 days", units.get(col, "")))
        _format_time_axis(ax)
    _save(fig, axes, f"{label} — trailing 7-day rolling standard deviation (daily mean shown)", out_path)


def plot_abs_change_timeseries(series, features, out_path, units, label="Key features"):
    fig, axes = _grid(len(features), 2, 7)
    seen_colors: dict = {}
    for ax, col in zip(axes, features):
        for zone, (_, change, _) in series[col].items():
            daily = change.abs().resample("D").mean()
            ax.plot(daily.index, daily.values, label=zone, linewidth=1,
                    color=_color_for_group(zone, seen_colors))
        _label_panel(ax, col, "Delivery time (UTC)",
                     _with_unit("Mean |hourly change|", units.get(col, "")))
        _format_time_axis(ax)
    _save(fig, axes, f"{label} — daily mean of the absolute 1-hour change", out_path)


# Calendar periods for the within-period std / variance (columns added by
# _add_calendar_columns), in the order they're written.
STAT_PERIODS = {"daily": "_period_daily", "weekly": "_period_weekly", "monthly": "_period_monthly"}
PERIOD_MIN_FRACTION = 0.8


def make_stats(df, time_col, group_col, stats_features, out_dir, units, label="Key features"):
    wanted = stats_features if stats_features is not None else DEFAULT_STATS_FEATURES
    features = [c for c in wanted if c in df.columns]
    absent = [c for c in wanted if c not in df.columns]
    if absent:
        print(f"  stats: skipping feature(s) not in this dataframe: {absent}")
    if not features:
        print("  stats: no key features present — nothing to do.")
        return
    out_dir.mkdir(parents=True, exist_ok=True)

    _, series = _stats_summary(df, time_col, group_col, features, units)

    for period_name, period_col in STAT_PERIODS.items():
        table = _period_std_var(df, group_col, features, period_col)
        for stat in ("std", "variance"):
            plot_period_stat(table, features, stat, period_name,
                             out_dir / f"{period_name}_{stat}.png", units, label)

    plot_rolling_std(df, time_col, group_col, features, out_dir / "rolling_std_7d.png", units, label)
    plot_abs_change_timeseries(series, features, out_dir / "absolute_change_timeseries.png", units, label)


# ---------------------------------------------------------------------------
# ENTRY POINT
# ---------------------------------------------------------------------------

def visualize(input_arg: str, freq: str = "D", time_col: str | None = None,
              group_col: str | None = None, stats_features: list | None = None,
              model_spec: dict | None = None):
    """The "visualisation" step of main.py (also what the CLI below runs).
    input_arg: dataframe name (e.g. df_2025), filename, or path.
    stats_features: key features for stats/ (None = DEFAULT_STATS_FEATURES).
    model_spec: if given, every folder holds only the model's variables,
    split into endogenous/ and exogenous/ (one file per variable), instead
    of one figure per column category; stats_features is then ignored."""
    df, time_col, group_col, feature_cols, stem = load_dataframe(
        input_arg, time_col, group_col)
    df = _add_calendar_columns(df, time_col)

    out_dir = PLOTS_DIR / stem
    print(f"Writing plots to {out_dir}\n")

    groups = categorize_columns(feature_cols)
    units = column_units(feature_cols, SOURCES, DERIVED_FEATURES)
    freq = None if freq.lower() == "raw" else freq
    zones = sorted(df[group_col].astype(str).unique())
    if model_spec:
        plot_model_variables(df, time_col, group_col, model_spec, out_dir, units)
    else:
        zones = sorted(df[group_col].astype(str).unique())
        seasonal_dir = out_dir / "seasonals"
        for prefix, cols in sorted(groups.items()):
            label = PREFIX_LABELS.get(prefix, prefix)
            plot_timeseries_group(df, time_col, group_col, cols, freq,
                                  out_dir / "timeseries" / f"timeseries_{label}.png", label, units)
            plot_distribution_group(df, group_col, cols,
                                    out_dir / "distributions" / f"distributions_{label}.png", label, units)
            plot_hour_of_day(df, group_col, cols,
                             seasonal_dir / "hour_of_day" / f"hour_of_day_{label}.png", label, units)
            for zone in zones:
                plot_hour_of_day_by_season(
                    df[df[group_col].astype(str) == zone], zone, cols,
                    seasonal_dir / "hour_of_day_by_season" / f"hour_of_day_by_season_{label}_{zone}.png",
                    label, units)
            plot_hour_of_week(df, group_col, cols,
                              seasonal_dir / "hour_of_week" / f"hour_of_week_{label}.png", label, units)
            plot_month_of_year(df, group_col, cols,
                               seasonal_dir / "month_of_year" / f"month_of_year_{label}.png", label, units)

        print("\n  stats (key features):")
        make_stats(df, time_col, group_col, stats_features, out_dir / "stats", units)

    print(f"\nDone. {len(feature_cols)} feature(s) across {len(groups)} "
          f"categor{'y' if len(groups) == 1 else 'ies'} -> {out_dir}")


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("input", help="Dataframe name (e.g. df_2025), filename, or full path to a dataframe CSV.")
    parser.add_argument("--freq", default="D",
                         help="Resample frequency for time-series plots (default 'D' = daily mean). "
                              "Use 'raw' to skip resampling.")
    parser.add_argument("--time-col", default=None)
    parser.add_argument("--group-col", default=None)
    args = parser.parse_args()
    visualize(args.input, args.freq, args.time_col, args.group_col)


if __name__ == "__main__":
    main()
