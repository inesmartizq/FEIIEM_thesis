"""
visualisation.py — descriptive plots of every column of a dataframe except
the calendar dummies (the "visualisation" step of main.py). One file per
column, in a folder per role (endogenous / exogenous / inputs):

    timeseries/<role>/<col>.png     hourly values, one panel per zone
    distributions/<role>/<col>.png  histogram, zones overlaid
    seasonals/<role>/<col>.png      one row per zone: 24 h profile across days (min-max,
                                    10-90 % and 25-75 % bands, mean, median), 24 h mean
                                    by season, 168 h week profile, mean per month
    stats/<role>/<col>.png          std of the hourly values within each day / Mon-Sun
                                    week / month, trailing 7-day rolling std, daily mean
                                    of the absolute 1-hour change

Calendar profiles and periods use Copenhagen local time (so DST does not
smear the daily pattern). A zone where a column does not vary (e.g. a
cross-border flow the zone is not connected to: 0 in every hour) is left out
of that column's plots.
"""

import matplotlib.patheffects as patheffects
import matplotlib.pyplot as plt
import pandas as pd

from common import (ROLE_FOLDERS, column_units, label, save_figure, style_axes, time_axis, with_unit, zone_color,
                    zones_with_data)
from dataframe.building import LOCAL_TZ, SEASON_OF_MONTH, Spec

FOLDERS = ["timeseries", "distributions", "seasonals", "stats"]

SEASON_COLORS = {"Winter": "#0072B2", "Spring": "#009E73", "Summer": "#E69F00", "Autumn": "#D55E00"}
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

# stats: within-period std (a period counts when >= 80 % of its hours are
# observed, so a half week at the edge of the sample is not shown), rolling std
PERIODS = {"day": "_period_day", "Mon-Sun week": "_period_week", "month": "_period_month"}
PERIOD_MIN_FRACTION = 0.8
ROLLING_WINDOW, ROLLING_MIN_HOURS = "7D", 134  # 80 % of the 168 hours


def _calendar(times: pd.Series) -> pd.DataFrame:
    local = times.dt.tz_convert(LOCAL_TZ)
    naive = local.dt.tz_localize(None)
    return pd.DataFrame({
        "_hour": local.dt.hour, "_month": local.dt.month, "_season": local.dt.month.map(SEASON_OF_MONTH),
        "_hour_of_week": local.dt.dayofweek * 24 + local.dt.hour,
        "_period_day": naive.dt.to_period("D"), "_period_week": naive.dt.to_period("W-SUN"),
        "_period_month": naive.dt.to_period("M"),
    }, index=times.index)


# ---------------------------------------------------------------------------
# PLOTS — `data` is {zone: that zone's rows (with the calendar columns)}
# ---------------------------------------------------------------------------
def plot_timeseries(data: dict, col: str, unit: str, path):
    fig, axes = plt.subplots(len(data), 1, figsize=(15, 2.9 * len(data)), sharex=True, sharey=True, squeeze=False)
    axes = list(axes[:, 0])
    for ax, (zone, g) in zip(axes, data.items()):
        ax.plot(g["datetime_utc"], g[col], linewidth=0.3, alpha=0.85, color=zone_color(zone))
        ax.axhline(0, color="black", linewidth=0.6, alpha=0.5)
        style_axes(ax, f"{zone}   (n = {g[col].notna().sum():,} h, {g[col].isna().sum():,} missing)",
                   "Delivery time (UTC)" if ax is axes[-1] else "", with_unit("Value", unit))
        time_axis(ax)
    save_figure(fig, axes, f"{label(col)} — hourly values", path)


def plot_distribution(data: dict, col: str, unit: str, path):
    fig, ax = plt.subplots(figsize=(10, 4.5))
    for zone, g in data.items():
        ax.hist(g[col].dropna(), bins=50, alpha=0.55, label=zone, color=zone_color(zone))
    style_axes(ax, "", with_unit("Value", unit), "Count [hours]")
    save_figure(fig, [ax], f"{label(col)} — distribution of the hourly values", path)


def _hour_of_day(ax, g: pd.DataFrame, col: str, color: str):
    """Per hour of the day: min-max over all days (faintest band), 10-90 %,
    25-75 % (darkest), mean (solid) and median (dashed). The median matters
    for skewed series, where a few large values pull the mean up."""
    hours = range(24)
    by_hour = g.groupby("_hour")[col]
    if by_hour.count().sum() == 0:
        return
    q = by_hour.quantile([0.0, 0.10, 0.25, 0.75, 0.90, 1.0]).unstack().reindex(hours)
    outline = [patheffects.Stroke(linewidth=3.2, foreground="white"), patheffects.Normal()]
    for (lo, hi), alpha in (((0.0, 1.0), 0.08), ((0.10, 0.90), 0.2), ((0.25, 0.75), 0.45)):
        ax.fill_between(hours, q[lo], q[hi], color=color, alpha=alpha, linewidth=0)
    ax.plot(hours, by_hour.mean().reindex(hours), color=color, linewidth=2, path_effects=outline)
    ax.plot(hours, by_hour.median().reindex(hours), color=color, linewidth=1.6, linestyle="--", path_effects=outline)


def plot_seasonals(data: dict, col: str, unit: str, path):
    fig, grid = plt.subplots(len(data), 4, figsize=(22, 3.6 * len(data)), sharey="col", squeeze=False)
    for (zone, g), row in zip(data.items(), grid):
        color = zone_color(zone)
        _hour_of_day(row[0], g, col, color)
        for season, season_color in SEASON_COLORS.items():
            mean = g[g["_season"] == season].groupby("_hour")[col].mean()
            if mean.notna().any():
                row[1].plot(mean.index, mean.values, color=season_color, linewidth=1.5, label=season)
        week = g.groupby("_hour_of_week")[col].mean()
        row[2].plot(week.index, week.values, color=color, linewidth=1)
        month = g.groupby("_month")[col].mean()
        row[3].plot(month.index, month.values, color=color, marker="o", markersize=3, linewidth=1.2)

        for ax in row[:2]:
            ax.set_xticks(range(0, 24, 3))
            ax.set_xlim(0, 23)
        for day in range(1, 7):
            row[2].axvline(day * 24, color="0.85", linewidth=0.8, zorder=0)
        row[2].set_xticks([day * 24 + 12 for day in range(7)], WEEKDAYS)
        row[2].set_xlim(0, 167)
        row[3].set_xticks(range(1, 13), MONTHS, rotation=45)
        ylabel = with_unit("Value", unit)
        style_axes(row[0], f"{zone} — 24 h profile across days", "Hour (local time)", ylabel)
        style_axes(row[1], f"{zone} — 24 h mean by season", "Hour (local time)", ylabel)
        style_axes(row[2], f"{zone} — week profile (hourly means)", "Day of week (local time)", ylabel)
        style_axes(row[3], f"{zone} — mean per month", "Month (local time)", ylabel)

    # legend proxies: what the bands and lines of the 24 h profile mean
    ax0 = grid[0][0]
    for alpha, text in ((0.08, "Min–max (all days)"), (0.2, "10–90 % of days"), (0.45, "25–75 % of days")):
        ax0.fill_between([], [], [], color="0.3", alpha=alpha, linewidth=0, label=text)
    ax0.plot([], [], color="0.3", linewidth=2, label="Mean")
    ax0.plot([], [], color="0.3", linewidth=1.6, linestyle="--", label="Median")
    save_figure(fig, list(grid.flat), f"{label(col)} — seasonal profiles (Copenhagen local time; winter = "
                                      f"Dec–Feb, spring = Mar–May, summer = Jun–Aug, autumn = Sep–Nov)", path)


def _within_period_std(g: pd.DataFrame, col: str, period_col: str) -> pd.Series:
    """Std of the hourly values within each complete period, indexed by the period start."""
    rows = {}
    for period, block in g.groupby(period_col):
        expected = round((period.end_time - period.start_time).total_seconds() / 3600)
        if block[col].notna().sum() >= PERIOD_MIN_FRACTION * expected:
            rows[period.start_time] = block[col].std()
    return pd.Series(rows, dtype=float)


def plot_stats(data: dict, col: str, unit: str, path):
    fig, axes = plt.subplots(5, 1, figsize=(13, 2.5 * 5), sharex=True)
    for zone, g in data.items():
        color = zone_color(zone)
        for ax, period_col in zip(axes[:3], PERIODS.values()):
            std = _within_period_std(g, col, period_col)
            daily = period_col == "_period_day"
            ax.plot(std.index, std.values, color=color, linewidth=1 if daily else 1.2,
                    marker=None if daily else "o", markersize=3, label=zone)
        s = g.set_index("datetime_utc")[col]
        rolling = s.rolling(ROLLING_WINDOW, min_periods=ROLLING_MIN_HOURS).std().resample("D").mean()
        axes[3].plot(rolling.index, rolling.values, color=color, linewidth=1)
        change = (s - s.shift(1, freq="h").reindex(s.index)).abs()  # previous HOUR by time, so gaps give NaN
        daily_change = change.resample("D").mean()
        axes[4].plot(daily_change.index, daily_change.values, color=color, linewidth=1)
    for ax, period in zip(axes[:3], PERIODS):
        style_axes(ax, f"Std of the hourly values within each {period} (local time)", "", with_unit("Std", unit))
    style_axes(axes[3], "Trailing 7-day rolling std of the hourly values (daily mean shown)", "",
               with_unit("Std", unit))
    style_axes(axes[4], "Daily mean of the absolute 1-hour change |x[t] - x[t-1]|", "Date",
               with_unit("Mean |change|", unit))
    for ax in axes:
        time_axis(ax)
    save_figure(fig, list(axes), f"{label(col)} — variability over time, per bidding zone", path)


# ---------------------------------------------------------------------------
# ENTRY POINT
# ---------------------------------------------------------------------------
def run(df: pd.DataFrame, spec: Spec, plot_dir):
    with_calendar = pd.concat([df, _calendar(df["datetime_utc"])], axis=1)
    by_zone = {z: g.sort_values("datetime_utc") for z, g in with_calendar.groupby("bidding_zone")}
    units = column_units(spec.columns)
    for role, cols in spec.by_role().items():
        folder = ROLE_FOLDERS[role]
        for col in cols:
            zs = zones_with_data(df, col)
            if not zs:
                print(f"  {col}: does not vary in any zone — not plotted")
                continue
            data = {z: by_zone[z] for z in zs}
            plot_timeseries(data, col, units[col], plot_dir / "timeseries" / folder / f"{col}.png")
            plot_distribution(data, col, units[col], plot_dir / "distributions" / folder / f"{col}.png")
            plot_seasonals(data, col, units[col], plot_dir / "seasonals" / folder / f"{col}.png")
            plot_stats(data, col, units[col], plot_dir / "stats" / folder / f"{col}.png")
