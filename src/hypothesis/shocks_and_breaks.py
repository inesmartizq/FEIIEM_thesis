"""
shocks_and_breaks.py — the evidence for the hypothesis before any model (the
"shocks_and_breaks" step of main.py): the structural breaks of every column,
the shocks of the forecast errors, and how the spreads move around a shock.
Read-only: nothing in the dataframe is changed or removed.

SHOCKS (the forecast errors of expected_signs, per zone)
    Regimes: the periods between the variance breaks of the error (below).
    Within each regime r, the robust z-score of every hour:
        z_t = (e_t - median_r(e)) / (1.4826 * MAD_r(e)),  MAD = median |e - median(e)|
    (1.4826 * MAD is the standard deviation of normal data; median and MAD are
    not pulled by the extreme hours they are meant to find). An hour is a
    shock hour when |z_t| > z_threshold; consecutive shock hours of the same
    sign are one shock, its onset the first of them. Sign + = over-forecast
    (e.g. less wind than planned).

HOW THE SPREADS MOVE AROUND A SHOCK (event study)
    Normal level of a spread: its mean at the same hour of the day over the
    hours without a shock of the error. Deviation d_t = spread_t - normal.
        D_h = mean over the shocks of d at (onset + h),  h = -before ... after
    with the 95 % interval D_h +- 1.96 sd / sqrt(n). Effect during the shocks:
    the mean over the shocks of each shock's average d, with its 95 % interval.
    Compared with the expected sign of expected_signs (for an over-forecast;
    an under-forecast flips it): "as expected", "opposite", or "no clear
    effect" when the interval includes 0. Shocks can follow each other within
    a window, so the intervals are approximate.

BREAKS (every column except the calendar dummies, per zone)
    Detection runs on DAILY series (Copenhagen local days; a day needs >= 80 %
    of its hours observed): at hourly resolution a level test mostly
    "detects" the daily cycle.
    Mean breaks:     the daily mean.
    Variance breaks: the log of each day's within-day variance of the hourly
                     values (a robust Inclán-Tiao-type test, Sansó, Aragó &
                     Carrion 2004); days without variation are left out.
    Both are capped at their 1st / 99th percentiles FOR DETECTION ONLY, so a
    single extreme day cannot create a break.
    Statistic: CUSUM max_k |S_k| / sqrt(n * LRV), with LRV a HAC long-run
    variance (Bartlett kernel, Andrews (1991) AR(1) plug-in bandwidth) of the
    residuals around the candidate break (each side demeaned), at least
    min_segment_days on each side.
    Multiple breaks: seeded binary segmentation (Kovács et al. 2023) — the
    statistic on ~30 overlapping windows; the most significant window gives a
    break, then both sides are searched again. Finds changes that later
    reverse, unlike plain binary segmentation.
    Significance: parametric bootstrap of the LARGEST statistic over all
    windows, on AR(1) series with the data's own persistence (rho from first
    differences, which a level shift does not inflate). p_value_adjusted
    (the decision) is this bootstrap p-value; p_value is the single-window
    Kolmogorov p, for reference.
    Before / after values are computed on the unmodified HOURLY values of the
    adjacent segments; for variance breaks the typical within-day std (what
    the test compares) is shown too.

STATISTICAL DETECTION != ECONOMIC MEANING: a break says the level or
volatility differs between segments; with one year of data this can be
seasonality as much as structural change.

OUTPUT (plots/<name>/shocks_and_breaks/)
    <role>/<col>.png         daily mean with regime means and breaks; daily and
                             weekly std with regime std and breaks; one column per zone
    event_study_<zone>.png   the spreads around the shocks of each forecast error
    SHOCKS_AND_BREAKS.md     method, shocks, effects, break table, regime classification
    hypothesis.csv           the expected sign of every (error, spread) and its mechanism
    shocks.csv, regimes.csv  the shocks; the regimes with their median and shock thresholds
    event_study.csv          D_h with its interval, per zone, error, spread and sign
    effects.csv              the effect during the shocks, with the verdict
    breaks.csv, segments.csv the breaks and the regime means / variances of every column
"""

import math
import warnings

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.signal import lfilter

from common import (FONT_SCALE, ROLE_FOLDERS, column_units, label, md_table, save_figure, style_axes, time_axis, with_unit,
                    zones_with_data)
from dataframe.building import FORECAST_ERRORS, LOCAL_TZ, Spec

FOLDERS = ["shocks_and_breaks"]

MIN_DAY_COVERAGE = 0.8
BOTH_WINDOW_DAYS = 14   # a mean and a variance break this close -> "Both"
WINSOR_QUANTILE = 0.01  # detection series capped at the 1st / 99th percentile
NULL_DRAWS = 2000       # simulations of the max-over-windows null distribution
NULL_SEED = 20250101
MAD_TO_SD = 1.4826      # 1.4826 * MAD = the standard deviation of normal data
MEAN_COLOR, VAR_COLOR, SERIES_COLOR = "#D55E00", "#6A3D9A", "#0072B2"
SIGN_COLORS = {1: "#D55E00", -1: "#0072B2"}  # over-forecast, under-forecast
SIGN_NAMES = {1: "over-forecast (error > 0)", -1: "under-forecast (error < 0)"}


# ---------------------------------------------------------------------------
# TEST
# ---------------------------------------------------------------------------
def _kolmogorov_sf(x: float) -> float:
    """P(sup |Brownian bridge| > x)."""
    if x <= 0:
        return 1.0
    k = np.arange(1, 101)
    return float(np.clip(2 * np.sum((-1.0) ** (k + 1) * np.exp(-2 * k ** 2 * x ** 2)), 0.0, 1.0))


def _long_run_variance(e: np.ndarray) -> np.ndarray:
    """Bartlett-kernel HAC variance of every row of e, with the Andrews (1991)
    AR(1) plug-in bandwidth — adapts to how persistent each row is."""
    e = e - e.mean(axis=1, keepdims=True)
    n = e.shape[1]
    denom = (e[:, :-1] ** 2).sum(axis=1)
    rho = np.where(denom > 0, np.clip((e[:, 1:] * e[:, :-1]).sum(axis=1) / np.where(denom > 0, denom, 1),
                                      -0.97, 0.97), 0.0)
    alpha = 4 * rho ** 2 / ((1 - rho) ** 2 * (1 + rho) ** 2)
    bandwidth = np.minimum((1.1447 * (alpha * n) ** (1 / 3)).astype(int), n - 1)
    lrv = (e * e).sum(axis=1) / n
    for lag in range(1, int(bandwidth.max()) + 1):
        weight = np.where(lag <= bandwidth, 2 * (1 - lag / (bandwidth + 1)), 0.0)
        lrv += weight * (e[:, lag:] * e[:, :-lag]).sum(axis=1) / n
    return np.maximum(lrv, 1e-12)


def _cusum(x: np.ndarray, min_seg: int):
    """(statistics, k) for every row of x: the largest |CUSUM| over split
    points leaving >= min_seg observations on each side (k = observations left
    of the break), standardised by the long-run variance of the residuals
    AROUND THAT BREAK (each side demeaned). Around the overall mean, a genuine
    shift would look like persistence, inflate the variance and hide itself.
    None if the series is too short for a split."""
    rows, n = x.shape
    cusum = np.abs(np.cumsum(x - x.mean(axis=1, keepdims=True), axis=1)[:, :-1])[:, min_seg - 1:n - min_seg]
    if cusum.shape[1] == 0:
        return None, None
    j = cusum.argmax(axis=1)
    k = j + min_seg
    totals = np.cumsum(x, axis=1)
    left = totals[np.arange(rows), k - 1]
    side_mean = np.where(np.arange(n)[None, :] < k[:, None], (left / k)[:, None],
                         ((totals[:, -1] - left) / (n - k))[:, None])
    return cusum[np.arange(rows), j] / np.sqrt(n * _long_run_variance(x - side_mean)), k


def _ar1_from_differences(x: np.ndarray) -> float:
    """AR(1) persistence from FIRST DIFFERENCES: corr(dx_t, dx_t-1) = -(1 - rho) / 2
    for an AR(1). Differencing removes level shifts, so a genuine break does
    not inflate rho (which would make the test needlessly conservative)."""
    d = np.diff(x)
    d = d - d.mean()
    denom = d @ d
    return float(np.clip(1 + 2 * (d[1:] @ d[:-1]) / denom, 0.0, 0.95)) if denom > 0 else 0.0


def _seeded_intervals(n: int, min_len: int, decay: float = 2 ** -0.5) -> list[tuple[int, int]]:
    """The full sample, then layers of shorter, evenly spaced, overlapping
    windows (length shrinking by `decay` per layer) down to min_len."""
    intervals, layer = set(), 1
    while (length := n * decay ** (layer - 1)) >= min_len:
        count = 2 * math.ceil((1 / decay) ** (layer - 1)) - 1
        shift = (n - length) / (count - 1) if count > 1 else 0
        for i in range(count):
            start = int(round(i * shift))
            intervals.add((start, min(n, start + int(round(length)))))
        layer += 1
    return sorted(intervals)


_NULL_CACHE: dict = {}


def _null_max_statistics(n: int, min_seg: int, rho: float) -> np.ndarray:
    """Distribution, under 'no break', of the LARGEST statistic over all
    seeded windows, simulated on AR(1) series with persistence rho (rounded
    to 0.05 for caching). Fixed seed: reproducible."""
    rho = round(rho * 20) / 20
    key = (n, min_seg, rho)
    if key not in _NULL_CACHE:
        burn = 100
        e = np.random.default_rng(NULL_SEED).standard_normal((NULL_DRAWS, n + burn))
        x = lfilter([1.0], [1.0, -rho], e, axis=1)[:, burn:]  # x_t = rho x_t-1 + e_t
        stats = np.zeros(NULL_DRAWS)
        for a, b in _seeded_intervals(n, 2 * min_seg):
            if b - a >= 2 * min_seg:
                stats = np.maximum(stats, _cusum(x[:, a:b], min_seg)[0])
        _NULL_CACHE[key] = np.sort(stats)
    return _NULL_CACHE[key]


def seeded_segmentation(x: np.ndarray, min_seg: int, alpha: float) -> list[dict]:
    """Breaks of x (sorted by position). Greedy: the most significant window
    gives a break, then both sides are searched again."""
    n = len(x)
    if n < 2 * min_seg:
        return []
    intervals = [(a, b) for a, b in _seeded_intervals(n, 2 * min_seg) if b - a >= 2 * min_seg]
    rho = _ar1_from_differences(x)
    null = _null_max_statistics(n, min_seg, rho)
    found = []

    def search(lo: int, hi: int):
        best = None
        for a, b in intervals:
            if a < lo or b > hi:
                continue
            stat, k = _cusum(x[None, a:b], min_seg)
            if stat is None:
                continue
            stat, k = float(stat[0]), int(k[0])
            p_adj = (1 + np.sum(null >= stat)) / (len(null) + 1)
            if p_adj < alpha and (best is None or stat > best["statistic"]):
                best = {"index": a + k, "statistic": stat, "p_value": _kolmogorov_sf(stat),
                        "p_adjusted": float(p_adj), "ar1_rho": rho}
        if best:
            found.append(best)
            search(lo, best["index"])
            search(best["index"], hi)

    search(0, n)
    return sorted(found, key=lambda b: b["index"])


def _winsorize(x: np.ndarray, q: float = WINSOR_QUANTILE) -> np.ndarray:
    lo, hi = np.quantile(x, [q, 1 - q])
    return np.clip(x, lo, hi)


# ---------------------------------------------------------------------------
# ANALYSIS OF ONE SERIES
# ---------------------------------------------------------------------------
def _hourly_series(df: pd.DataFrame, zone: str, col: str) -> pd.Series:
    """Hourly values of one zone, indexed by Copenhagen local time."""
    g = df[df["bidding_zone"] == zone]
    s = g.set_index("datetime_utc")[col].sort_index()
    s.index = s.index.tz_convert(LOCAL_TZ)
    return s


def _daily(s: pd.Series) -> pd.DataFrame:
    grouped = s.groupby(s.index.tz_localize(None).normalize())
    daily = pd.DataFrame({"mean": grouped.mean(), "var": grouped.var(), "n": grouped.count(),
                          "hours": grouped.size()})
    return daily[daily["n"] >= MIN_DAY_COVERAGE * daily["hours"]]


def _segments(s: pd.Series, dates: list, stat) -> list[dict]:
    """stat(...) and std of the hourly values within each segment between break dates."""
    day = s.index.tz_localize(None).normalize()
    edges = [day.min(), *dates, day.max() + pd.Timedelta(days=1)]
    out = []
    for start, end in zip(edges[:-1], edges[1:]):
        part = s[(day >= start) & (day < end)].dropna()
        out.append({"start": start, "end": end - pd.Timedelta(days=1), "value": stat(part), "std": part.std()})
    return out


def analyse_series(s: pd.Series, alpha: float, min_seg: int) -> dict:
    daily = _daily(s)
    mean_breaks = seeded_segmentation(_winsorize(daily["mean"].to_numpy()), min_seg, alpha) if len(daily) else []
    for b in mean_breaks:
        b["date"] = daily.index[b["index"]]
    var_daily = daily[daily["var"] > 0]
    var_tested = len(var_daily) >= 2 * min_seg
    var_breaks = (seeded_segmentation(_winsorize(np.log(var_daily["var"].to_numpy())), min_seg, alpha)
                  if var_tested else [])
    for b in var_breaks:
        b["date"] = var_daily.index[b["index"]]
    mean_segs = _segments(s, [b["date"] for b in mean_breaks], lambda p: p.mean())
    var_segs = _segments(s, [b["date"] for b in var_breaks], lambda p: p.var())
    for seg in var_segs:  # what the variance test compares: the typical within-day std
        days = var_daily[(var_daily.index >= seg["start"]) & (var_daily.index <= seg["end"])]
        seg["within_day_std"] = float(np.sqrt(np.exp(np.log(days["var"]).mean()))) if len(days) else np.nan
    return {"hourly": s, "daily": daily, "mean_breaks": mean_breaks, "var_breaks": var_breaks,
            "mean_segs": mean_segs, "var_segs": var_segs, "var_tested": var_tested,
            "daily_mean_std": float(daily["mean"].std())}


# ---------------------------------------------------------------------------
# SHOCKS AND HOW THE SPREADS MOVE AROUND THEM
# ---------------------------------------------------------------------------
def regime_scores(e: pd.Series, var_breaks: list) -> pd.DataFrame:
    """Robust z-score of every hour within its regime (the period between two variance breaks):
    z_t = (e_t - median_r) / (1.4826 MAD_r). Columns: e, regime, median, scale, z."""
    days = e.index.tz_localize(None).normalize()
    dates = np.array([b["date"] for b in var_breaks], dtype="datetime64[ns]")
    out = pd.DataFrame({"e": e.to_numpy(), "regime": np.searchsorted(dates, days.to_numpy(), side="right")},
                       index=e.index)
    out["median"] = out.groupby("regime")["e"].transform("median")
    out["scale"] = MAD_TO_SD * (out["e"] - out["median"]).abs().groupby(out["regime"]).transform("median")
    out["z"] = (out["e"] - out["median"]) / out["scale"].where(out["scale"] > 0)
    return out


def shock_runs(z: np.ndarray, threshold: float) -> list[tuple[int, int, int]]:
    """(first hour, last hour, sign) of every run of consecutive hours with |z| > threshold and the same sign."""
    s = np.where(np.abs(np.nan_to_num(z)) > threshold, np.sign(np.nan_to_num(z)), 0)
    starts = np.flatnonzero((s != 0) & (s != np.r_[0, s[:-1]]))
    ends = np.flatnonzero((s != 0) & (s != np.r_[s[1:], 0]))
    return [(int(a), int(b), int(s[a])) for a, b in zip(starts, ends)]


def deviation(spread: pd.Series, calm: np.ndarray) -> np.ndarray:
    """The spread minus its normal level: its mean at the same hour of the day over the calm hours."""
    hour = spread.index.hour
    normal = spread[calm].groupby(hour[calm]).mean()
    return spread.to_numpy() - normal.reindex(hour).to_numpy()


def mean_band(values: np.ndarray):
    """(mean, lower, upper, n) over the rows of values, ignoring missing values: mean +- 1.96 sd / sqrt(n)."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)  # a column with fewer than 2 values gives NaN
        n = np.sum(~np.isnan(values), axis=0)
        mean = np.nanmean(values, axis=0)
        half = 1.96 * np.nanstd(values, axis=0, ddof=1) / np.sqrt(n)
    return mean, mean - half, mean + half, n


def windows(d: np.ndarray, onsets: np.ndarray, before: int, after: int) -> tuple[np.ndarray, np.ndarray]:
    """(hours -before ... after, values: one row per onset): d around every onset, NaN outside the data."""
    hours = np.arange(-before, after + 1)
    idx = onsets[:, None] + hours[None, :]
    return hours, np.where((idx >= 0) & (idx < len(d)), d[np.clip(idx, 0, len(d) - 1)], np.nan)


def event_study(d: np.ndarray, onsets: np.ndarray, before: int, after: int) -> pd.DataFrame:
    """D_h = mean deviation of the spread h hours after the shock onsets, h = -before ... after."""
    hours, values = windows(d, onsets, before, after)
    mean, lower, upper, n = mean_band(values)
    return pd.DataFrame({"h": hours, "mean": mean, "lower": lower, "upper": upper, "n": n})


def verdict(lower: float, upper: float, expected: int, shocks: int) -> str:
    if shocks < 2:
        return "too few shocks"
    if lower > 0 or upper < 0:
        return "as expected" if (1 if lower > 0 else -1) == expected else "opposite"
    return "no clear effect"


def _utc(ts) -> str:
    return f"{pd.Timestamp(ts).tz_convert('UTC'):%Y-%m-%dT%H:%M:%SZ}"


def _local_day_utc(day) -> str:
    """The start of a Copenhagen local day, in UTC."""
    return _utc(pd.Timestamp(day).tz_localize(LOCAL_TZ))


def shock_tables(df: pd.DataFrame, results: dict, expected_signs: dict, threshold: float, before: int,
                 after: int) -> dict:
    """The shocks of every forecast error in expected_signs and how each spread moves around them, per zone."""
    rows = {k: [] for k in ("hypothesis", "regimes", "shocks", "events", "effects")}
    for error, signs in expected_signs.items():
        for spread, expected in signs.items():
            rows["hypothesis"].append({"error": error, "spread": spread, "expected": expected,
                                       "over_forecast": FORECAST_ERRORS[error][3] if error in FORECAST_ERRORS else ""})
        for zone, r in results[error][1].items():
            scores = regime_scores(r["hourly"], r["var_breaks"])
            runs = shock_runs(scores["z"].to_numpy(), threshold)
            for k, g in scores.groupby("regime"):
                rows["regimes"].append({"zone": zone, "variable": error, "regime": k, "start": _utc(g.index[0]),
                                        "end": _utc(g.index[-1]), "median": g["median"].iloc[0],
                                        "scale": g["scale"].iloc[0],
                                        "lower": g["median"].iloc[0] - threshold * g["scale"].iloc[0],
                                        "upper": g["median"].iloc[0] + threshold * g["scale"].iloc[0]})
            for a, b, sign in runs:
                peak = a + int(np.nanargmax(np.abs(scores["z"].to_numpy()[a:b + 1])))
                rows["shocks"].append({"zone": zone, "variable": error, "onset": _utc(scores.index[a]),
                                       "end": _utc(scores.index[b]), "hours": b - a + 1, "sign": sign,
                                       "peak": _utc(scores.index[peak]), "peak_z": scores["z"].iloc[peak],
                                       "peak_value": scores["e"].iloc[peak]})
            calm = (scores["z"].abs() <= threshold).to_numpy()
            for spread, expected in signs.items():
                d = deviation(_hourly_series(df, zone, spread), calm)
                for sign in (1, -1):
                    sel = [(a, b) for a, b, s in runs if s == sign]
                    study = event_study(d, np.array([a for a, _ in sel], dtype=int), before, after)
                    rows["events"] += [{"zone": zone, "error": error, "spread": spread, "sign": sign, **row}
                                       for row in study.to_dict("records")]
                    per_shock = np.array([[np.nanmean(d[a:b + 1]) if np.isfinite(d[a:b + 1]).any() else np.nan]
                                          for a, b in sel]).reshape(-1, 1)
                    mean, lower, upper, n = (float(v[0]) for v in mean_band(per_shock))
                    rows["effects"].append({"zone": zone, "error": error, "spread": spread, "sign": sign,
                                            "shocks": len(sel), "mean": mean, "lower": lower, "upper": upper,
                                            "expected": expected * sign,
                                            "verdict": verdict(lower, upper, expected * sign, int(n))})
    return {k: pd.DataFrame(v) for k, v in rows.items()}


def break_tables(results: dict) -> dict:
    """The breaks and the regime means / variances of every column, with UTC times (for the dashboard)."""
    breaks, segments = [], []
    for col, (_, per_zone) in results.items():
        for zone, r in per_zone.items():
            for kind in ("mean", "var"):
                breaks += [{"zone": zone, "column": col, "kind": kind, "date": _local_day_utc(b["date"]),
                            "statistic": b["statistic"], "p_adjusted": b["p_adjusted"]} for b in r[f"{kind}_breaks"]]
                segments += [{"zone": zone, "column": col, "kind": kind, "start": _local_day_utc(s["start"]),
                              "end": _local_day_utc(s["end"] + pd.Timedelta(days=1)), "value": s["value"],
                              "std": s["std"]} for s in r[f"{kind}_segs"]]
    return {"breaks": pd.DataFrame(breaks), "segments": pd.DataFrame(segments)}


# ---------------------------------------------------------------------------
# REPORT
# ---------------------------------------------------------------------------
def _num(v: float) -> str:
    return "" if pd.isna(v) else f"{v:.4g}"


def _evidence(b: dict) -> str:
    p = b["p_adjusted"]
    return f"CUSUM {b['statistic']:.2f}, adj. p {'< 0.0001' if p < 1e-4 else f'= {p:.4f}'}"


def _break_rows(col: str, role: str, zone: str, r: dict, unit: str) -> list[dict]:
    """One row per break; a mean and a variance break within BOTH_WINDOW_DAYS
    of each other become one 'Both' row."""
    rows, used = [], set()
    ms, vs = r["mean_segs"], r["var_segs"]

    def var_text(i):
        return f"var {_num(vs[i]['value'])}; within-day std {_num(vs[i]['within_day_std'])}"

    def var_change(i):
        return (f"var x{vs[i + 1]['value'] / vs[i]['value']:.2f}; within-day std "
                f"x{vs[i + 1]['within_day_std'] / vs[i]['within_day_std']:.2f}")

    for i, b in enumerate(r["mean_breaks"]):
        before, after = ms[i]["value"], ms[i + 1]["value"]
        # a % change is shown only when the level is large relative to its day-to-day variation
        rel = f" ({100 * (after - before) / abs(before):+.0f} %)" if abs(before) >= r["daily_mean_std"] else ""
        row = {"Date": f"{b['date']:%Y-%m-%d}", "Type": "Mean", "Before": f"mean {_num(before)}",
               "After": f"mean {_num(after)}", "Change": f"mean {after - before:+.4g}{rel}",
               "Evidence": f"mean: {_evidence(b)}"}
        close = [j for j, v in enumerate(r["var_breaks"])
                 if j not in used and abs((v["date"] - b["date"]).days) <= BOTH_WINDOW_DAYS]
        if close:
            j = min(close, key=lambda j: abs((r["var_breaks"][j]["date"] - b["date"]).days))
            used.add(j)
            v = r["var_breaks"][j]
            row.update({"Type": "Both", "Before": f"{row['Before']}; {var_text(j)}",
                        "After": f"{row['After']}; {var_text(j + 1)}", "Change": f"{row['Change']}; {var_change(j)}",
                        "Evidence": f"{row['Evidence']}; var: {_evidence(v)}"})
            if v["date"] != b["date"]:
                row["Date"] += f" / {v['date']:%Y-%m-%d} (var)"
        rows.append(row)
    for j, v in enumerate(r["var_breaks"]):
        if j not in used:
            rows.append({"Date": f"{v['date']:%Y-%m-%d}", "Type": "Variance", "Before": var_text(j),
                         "After": var_text(j + 1), "Change": var_change(j), "Evidence": f"var: {_evidence(v)}"})
    return [{"Column": col, "Role": role, "Zone": zone, "Unit": unit, **row}
            for row in sorted(rows, key=lambda x: x["Date"])]


def _classification_row(col: str, role: str, zone: str, r: dict) -> dict:
    nm, nv = len(r["mean_breaks"]), len(r["var_breaks"])
    return {
        "Column": col, "Role": role, "Zone": zone,
        "Mean": f"{nm} break{'s' if nm != 1 else ''}" if nm else "stable",
        "Variance": ("not tested (no within-day variation)" if not r["var_tested"] else
                     f"{nv} break{'s' if nv != 1 else ''}" if nv else "stable"),
        "Range of regime means": " to ".join(_num(f(s["value"] for s in r["mean_segs"])) for f in (min, max)),
        "Range of regime variances": (" to ".join(_num(f(s["value"] for s in r["var_segs"])) for f in (min, max))
                                      if r["var_tested"] else ""),
    }


def _shock_sections(tables: dict, units: dict, threshold: float, before: int, after: int) -> list[str]:
    shocks, effects = tables["shocks"], tables["effects"]
    name = lambda c: label(c).split(" (")[0]  # noqa: E731
    counts = pd.DataFrame()
    if len(shocks):
        g = shocks.groupby(["zone", "variable", "sign"], sort=False)
        counts = pd.DataFrame({"Shocks": g.size(), "Shock hours": g["hours"].sum(), "Median hours": g["hours"].median(),
                               "Largest |z|": g["peak_z"].agg(lambda z: f"{z.abs().max():.1f}")}).reset_index()
        counts = counts.assign(variable=counts["variable"].map(name), sign=counts["sign"].map(SIGN_NAMES)).rename(
            columns={"zone": "Zone", "variable": "Forecast error", "sign": "Sign"})
    table = effects.assign(**{
        "Forecast error": effects["error"].map(name), "Spread": effects["spread"].map(name),
        "Shock": effects["sign"].map(SIGN_NAMES),
        "Effect during the shocks": [f"{m:+.2f} [{lo:+.2f}, {hi:+.2f}] {units[s]}" if np.isfinite(m) else ""
                                     for m, lo, hi, s in zip(effects["mean"], effects["lower"], effects["upper"],
                                                             effects["spread"])],
        "Expected": effects["expected"].map({1: "up", -1: "down"}), "Verdict": effects["verdict"]})
    table = table.rename(columns={"zone": "Zone", "shocks": "Shocks"})[
        ["Zone", "Forecast error", "Shock", "Spread", "Shocks", "Effect during the shocks", "Expected", "Verdict"]]
    tally = effects["verdict"].value_counts()
    return [
        "## Shocks",
        "",
        "**Rule.** Regimes are the periods between the variance breaks of the forecast error (below). Within each "
        "regime, z_t = (e_t − median) / (1.4826 · MAD), where MAD = median |e_t − median| and 1.4826 · MAD is the "
        f"standard deviation of normal data. An hour is a shock hour when |z_t| > {threshold:g}; consecutive shock "
        "hours of the same sign form one shock, which starts at its first hour. Over-forecast = error > 0 (e.g. less "
        "wind than planned).",
        "",
        md_table(counts) if len(counts) else "No shocks.",
        "",
        "## How the spreads move around a shock",
        "",
        "**Method.** The normal level of a spread is its mean at the same hour of the day over the hours without a "
        "shock of the error; d_t = spread_t − normal. D_h = mean over the shocks of d at onset + h "
        f"(h = −{before} … {after}), with the 95 % interval D_h ± 1.96 · sd / √n (event_study.csv, "
        "event_study_<zone>.png). The effect during the shocks is the mean over the shocks of each shock's average d, "
        "with its 95 % interval. Expected: the sign the hypothesis gives (main.py, EXPECTED_SIGNS); an "
        "under-forecast flips it. Verdict: 'as expected' or 'opposite' when the interval excludes 0, else 'no clear "
        "effect'. Shocks can follow each other within a window, so the intervals are approximate.",
        "",
        md_table(table),
        "",
        "Verdicts: " + ", ".join(f"{k} {v}" for k, v in tally.items()) + ".",
        "",
    ]


def _write_report(results: dict, units: dict, alpha: float, min_seg: int, period: str, path, shock_sections: list):
    breaks, classes = [], []
    for col, (role, per_zone) in results.items():
        for zone, r in per_zone.items():
            breaks += _break_rows(col, role, zone, r, units[col])
            classes.append(_classification_row(col, role, zone, r))
    text = [
        "# Shocks and breaks",
        "",
        f"Period {period}. The shocks of the forecast errors and how the spreads move around them; then the "
        "structural breaks of every column except the calendar dummies, per bidding zone.",
        "",
        *shock_sections,
        "## Structural breaks",
        "",
        "**Method.** Daily series (Copenhagen local days). Mean breaks: CUSUM test on the daily mean. Variance "
        "breaks: the same test on the log of the within-day variance (days without variation left out). Both are "
        "standardised by a HAC long-run variance (Bartlett kernel, Andrews bandwidth) estimated around the "
        "candidate break, and capped at their 1st/99th percentiles for detection only. Multiple breaks by seeded "
        "binary segmentation (Kovács et al. 2023), which also catches changes that later reverse. Significance: "
        "a parametric AR(1) bootstrap of the largest statistic over all windows, with the series' own persistence "
        f"(estimated from first differences, robust to level shifts); cut-off α = {alpha} on that adjusted "
        f"p-value, at least {min_seg} days between breaks. Before/after values are computed on the unmodified "
        "hourly values of the adjacent segments; a % change is shown only when the level is at least one "
        "standard deviation of the daily means. A mean and a variance break within "
        f"{BOTH_WINDOW_DAYS} days of each other are reported as 'Both'.",
        "",
        "### Detected breaks",
        "",
        md_table(pd.DataFrame(breaks)) if breaks else "No breaks detected.",
        "",
        "### Regime classification (statistical)",
        "",
        md_table(pd.DataFrame(classes)),
        "",
        "### Reading this",
        "- Statistical detection only: a break means the level or volatility differs between segments, not why.",
        "- With a single year of data, breaks can reflect seasonality (e.g. solar-driven midday prices in "
        "spring/summer, the hydro cycle) as much as structural change.",
        "- Candidate explanations to check before interpreting a break (not tested here): seasonal fuel and "
        "weather patterns; the Nordic mFRR energy-activation market go-live (March 2025); the day-ahead 15-minute "
        "MTU go-live (1 Oct 2025).",
        "",
    ]
    path.write_text("\n".join(text), encoding="utf-8")
    print(f"  wrote {path.name}")


# ---------------------------------------------------------------------------
# PLOT
# ---------------------------------------------------------------------------
def _weekly_std(s: pd.Series) -> pd.Series:
    """Std of the hourly values within each Monday-Sunday week (local time);
    weeks with < 80 % of their hours observed are left out."""
    g = s.groupby(s.index.tz_localize(None).to_period("W-SUN"))
    std = g.std()[g.count() >= 0.8 * 168]
    return pd.Series(std.to_numpy(), index=std.index.start_time)


def _break_lines(ax, r: dict):
    for i, b in enumerate(r["mean_breaks"]):
        ax.axvline(b["date"], color=MEAN_COLOR, linewidth=1.6, label="Mean break" if i == 0 else None, zorder=3)
    for i, b in enumerate(r["var_breaks"]):
        ax.axvline(b["date"], color=VAR_COLOR, linestyle="--", linewidth=1.6,
                   label="Variance break" if i == 0 else None, zorder=3)


def plot_breaks(col: str, per_zone: dict, unit: str, path):
    fig, axes = plt.subplots(2, len(per_zone), figsize=(8 * len(per_zone), 7.5), squeeze=False, sharex="col")
    for j, (zone, r) in enumerate(per_zone.items()):
        ax = axes[0][j]
        ax.plot(r["daily"].index, r["daily"]["mean"], color=SERIES_COLOR, linewidth=0.9, label="Daily mean")
        for i, seg in enumerate(r["mean_segs"]):
            ax.hlines(seg["value"], seg["start"], seg["end"] + pd.Timedelta(days=1), color=MEAN_COLOR, linewidth=2.2,
                      label="Regime mean (between mean breaks)" if i == 0 else None, zorder=4)
        _break_lines(ax, r)
        style_axes(ax, zone, "", with_unit("Daily mean", unit))

        ax = axes[1][j]
        d_std = np.sqrt(r["daily"]["var"])
        ax.plot(d_std.index, d_std.values, color="0.6", linewidth=0.7, label="Daily std (within day)")
        w_std = _weekly_std(r["hourly"])
        if not w_std.empty:
            ax.step(w_std.index, w_std.values, where="post", color=SERIES_COLOR, linewidth=1.4,
                    label="Weekly std (within Mon–Sun week)")
        for i, seg in enumerate(r["var_segs"]):
            ax.hlines(seg["std"], seg["start"], seg["end"] + pd.Timedelta(days=1), color=VAR_COLOR, linewidth=2.2,
                      label="Regime std (between variance breaks)" if i == 0 else None, zorder=4)
        _break_lines(ax, r)
        if (d_std > 0).any():
            ax.set_yscale("log")
        style_axes(ax, "", "Delivery date (Copenhagen local time)", with_unit("Std of the hourly values", unit))
        time_axis(ax)
    save_figure(fig, list(axes.flat), f"{label(col)} — structural breaks (CUSUM/HAC, seeded binary segmentation)",
                path, legend_ncol=4)


def plot_event_study(events: pd.DataFrame, effects: pd.DataFrame, zone: str, units: dict, path):
    """The spreads around the shocks of each forecast error: one row per error, one column per spread."""
    ev = events[events["zone"] == zone]
    errors, spreads = list(dict.fromkeys(ev["error"])), list(dict.fromkeys(ev["spread"]))
    fig, axes = plt.subplots(len(errors), len(spreads), figsize=(5.2 * len(spreads), 3.6 * len(errors)),
                             squeeze=False, sharex=True)
    for i, error in enumerate(errors):
        for j, spread in enumerate(spreads):
            ax = axes[i][j]
            for sign in (1, -1):
                g = ev[(ev["error"] == error) & (ev["spread"] == spread) & (ev["sign"] == sign)]
                n = effects.loc[(effects["zone"] == zone) & (effects["error"] == error) & (effects["spread"] == spread)
                                & (effects["sign"] == sign), "shocks"].iloc[0]
                ax.fill_between(g["h"], g["lower"], g["upper"], color=SIGN_COLORS[sign], alpha=0.18, linewidth=0)
                ax.plot(g["h"], g["mean"], color=SIGN_COLORS[sign], linewidth=1.6,
                        label=f"{SIGN_NAMES[sign]} shocks" if i == j == 0 else None)
                ax.annotate(f"{n} shocks", xy=(0.98, 0.95 if sign == 1 else 0.05), xycoords="axes fraction",
                            ha="right", va="top" if sign == 1 else "bottom", fontsize=8 * FONT_SCALE,
                            color=SIGN_COLORS[sign])
            ax.axhline(0, color="0.4", linewidth=0.8)
            ax.axvline(0, color="0.6", linewidth=0.8, linestyle=":")
            style_axes(ax, f"{label(spread).split(' (')[0]} — {label(error).split(' (')[0]} shocks",
                       "Hours from the shock onset" if i == len(errors) - 1 else "",
                       with_unit("Spread minus its normal level", units[spread]) if j == 0 else "")
    save_figure(fig, list(axes.flat), f"{zone} — the spreads around forecast-error shocks (mean, 95 % interval)", path)


# ---------------------------------------------------------------------------
# ENTRY POINT
# ---------------------------------------------------------------------------
def run(df: pd.DataFrame, spec: Spec, plot_dir, alpha: float = 0.01, min_segment_days: int = 30,
        expected_signs: dict | None = None, z_threshold: float = 3.0, before: int = 6, after: int = 24):
    expected_signs = expected_signs or {}
    unknown = sorted({c for e, signs in expected_signs.items() for c in (e, *signs)} - set(spec.columns))
    if unknown:
        raise ValueError(f"expected_signs names columns that are not in the dataframe: {unknown}")
    out = plot_dir / "shocks_and_breaks"
    out.mkdir(parents=True, exist_ok=True)
    units = column_units(spec.columns)
    results = {}
    for role, cols in spec.by_role().items():
        for col in cols:
            per_zone = {z: analyse_series(_hourly_series(df, z, col), alpha, min_segment_days)
                        for z in zones_with_data(df, col)}
            if not per_zone:
                continue
            results[col] = (role, per_zone)
            print("  " + "; ".join(f"{col} {z}: {len(r['mean_breaks'])} mean, {len(r['var_breaks'])} variance"
                                   for z, r in per_zone.items()))
            plot_breaks(col, per_zone, units[col], out / ROLE_FOLDERS[role] / f"{col}.png")
    tables = {**shock_tables(df, results, expected_signs, z_threshold, before, after), **break_tables(results)}
    for key, table in tables.items():
        table.to_csv(out / f"{'event_study' if key == 'events' else key}.csv", index=False)
    for zone in tables["events"]["zone"].unique() if len(tables["events"]) else []:
        plot_event_study(tables["events"], tables["effects"], zone, units, out / f"event_study_{zone}.png")
    for (zone, error, sign), g in tables["shocks"].groupby(["zone", "variable", "sign"]) if len(tables["shocks"]) else []:
        print(f"  {zone} {error} {SIGN_NAMES[sign]}: {len(g)} shocks, {g['hours'].sum()} shock hours")
    period = f"{df['datetime_utc'].min():%Y-%m-%d} to {df['datetime_utc'].max():%Y-%m-%d}"
    _write_report(results, units, alpha, min_segment_days, period, out / "SHOCKS_AND_BREAKS.md",
                  _shock_sections(tables, units, z_threshold, before, after))
