"""
error_spreads.py — step 2 of the hypothesis: what the forecast errors do to the
price spreads (the "error_spreads" step of main.py). Averages only, no model.
Per zone, for every forecast error (forecast_errors.error_columns) and every
price spread (the other endogenous variables: the thesis spreads DA-ID, ID-BAL,
DA-BAL):

    large error  |e_t| above its quantile q (as in step 1), split by sign:
                 over-forecast (e > 0) and under-forecast (e < 0)
    spread       its mean in the large over-forecast hours, in the large
                 under-forecast hours and in all hours

LAGS (when, and how much) — plain spreads, no model:
    around       the mean spread from `before` hours before to `after` hours
                 after the first hour of each run of large errors of one sign,
                 with its 95 % interval
    correlation  r_k = corr(e_t, s_t+k) for every lag k in correlation_lags
                 (no interval)
    tenths       the error's ten equal groups (by value: from the largest
                 under-forecasts to the largest over-forecasts) and the mean
                 spread k hours later in each, for every k in tenth_lags, with
                 its 95 % interval

INTERVALS: block bootstrap. Errors come in long runs and neighbouring hours are
alike, so runs and hours are not independent and mean +- 1.96 sd / sqrt(n)
would be too narrow. The year is cut into blocks of block_hours; each of
`draws` draws takes as many blocks with replacement and recomputes the mean from
the runs (by the hour they start) or hours in them, so what lies close in time
stays together. The interval is the 2.5-97.5 % range of the draws. It needs
items from at least MIN_BLOCKS different blocks: from fewer, the draws can only
reshuffle a handful of values and the interval would be too narrow, so none is
given (e.g. 4 runs of large over-forecasts: the mean only).

OUTPUT (plots/<name>/error_spreads/)
    spreads.csv        per zone, error, spread and group (over, under, all): hours and mean spread
    around.csv         per zone, error, spread, sign and hour from the run's start: mean, interval, runs
    correlation.csv    per zone, error, spread and lag: r_k and the number of pairs
    tenths.csv         per zone, error, spread, lag and tenth: mean error, mean spread, interval, hours
    ERROR_SPREADS.md   the means by sign and the key numbers of the lags
"""

import math
import warnings
import zlib

import numpy as np
import pandas as pd

from common import label, md_table, zones_with_data
from dataframe.building import Spec
from hypothesis.forecast_errors import error_columns, hourly
from hypothesis.shocks_and_breaks import shock_runs, windows

FOLDERS = ["error_spreads"]
GROUPS = {"over": "large over-forecast", "under": "large under-forecast", "all": "all hours"}
MIN_BLOCKS = 10  # an interval needs items from at least this many blocks of time (see INTERVALS)


def spread_columns(spec: Spec) -> list:
    """The price spreads: the endogenous variables that are not forecast errors."""
    errors = set(error_columns(spec))
    return [c for c in spec.by_role()["Endogenous"] if c not in errors]


def by_sign(e: pd.Series, spread: pd.Series, quantile: float) -> list[dict]:
    """The mean spread in the large over-forecast hours, the large under-forecast hours and all hours."""
    both = pd.DataFrame({"e": e.to_numpy(), "s": spread.to_numpy()}).dropna()
    large = both["e"].abs() > e.abs().quantile(quantile)
    groups = {"over": large & (both["e"] > 0), "under": large & (both["e"] < 0), "all": both["e"].notna()}
    return [{"group": g, "hours": int(m.sum()), "mean": both.loc[m, "s"].mean()} for g, m in groups.items()]


def block_counts(hours: int, block_hours: int, draws: int, rng) -> np.ndarray:
    """(draws, blocks): how often each block of block_hours is drawn when the blocks are resampled with replacement."""
    n = math.ceil(hours / block_hours)
    return rng.multinomial(n, np.full(n, 1 / n), size=draws)


def block_band(values: np.ndarray, blocks: np.ndarray, counts: np.ndarray):
    """(mean, lower, upper, n) per column of values (items x columns, NaN = missing), each item in its block of time:
    the mean, and the 95 % block-bootstrap interval of it (counts: block_counts); no interval (NaN) where the items
    come from fewer than MIN_BLOCKS blocks."""
    ok = ~np.isnan(values)
    sums, ns = np.zeros((counts.shape[1], values.shape[1])), np.zeros((counts.shape[1], values.shape[1]))
    np.add.at(sums, blocks, np.where(ok, values, 0.0))
    np.add.at(ns, blocks, ok)
    with warnings.catch_warnings(), np.errstate(invalid="ignore", divide="ignore"):
        warnings.simplefilter("ignore", RuntimeWarning)  # a draw without any item gives NaN, left out
        lower, upper = np.nanquantile((counts @ sums) / (counts @ ns), [0.025, 0.975], axis=0)
        enough = (ns > 0).sum(axis=0) >= MIN_BLOCKS
        return (sums.sum(axis=0) / ns.sum(axis=0), np.where(enough, lower, np.nan), np.where(enough, upper, np.nan),
                ns.sum(axis=0))


def around_runs(e: pd.Series, spread: pd.Series, threshold: float, before: int, after: int, block_hours: int = 336,
                draws: int = 1000, rng=None) -> list[dict]:
    """The mean spread from `before` hours before to `after` hours after the first hour of each run of large errors
    (|e| > threshold) of one sign, with its 95 % block-bootstrap interval."""
    runs = shock_runs(e.to_numpy(), threshold)  # runs of consecutive hours with |e| > threshold and one sign
    counts = block_counts(len(e), block_hours, draws, rng if rng is not None else np.random.default_rng(0))
    out = []
    for sign in (1, -1):
        starts = np.array([a for a, _, k in runs if k == sign], dtype=int)
        hours, values = windows(spread.to_numpy(float), starts, before, after)
        mean, lower, upper, n = block_band(values, starts // block_hours, counts)
        out += [{"sign": sign, "runs": len(starts), "h": int(h), "mean": m, "lower": lo, "upper": up, "n": int(k)}
                for h, m, lo, up, k in zip(hours, mean, lower, upper, n)]
    return out


def lagged_correlation(e: pd.Series, spread: pd.Series, lags) -> list[dict]:
    """r_k = corr(e_t, s_t+k) for every lag k."""
    return [{"lag": k, "corr": e.corr(spread.shift(-k)), "pairs": int((e.notna() & spread.shift(-k).notna()).sum())}
            for k in lags]


def tenths(e: pd.Series, spread: pd.Series, lags, block_hours: int = 336, draws: int = 1000, rng=None) -> list[dict]:
    """The error's ten equal groups by value and the mean spread k hours later in each, with its 95 % block-bootstrap
    interval."""
    group = pd.qcut(e, 10, labels=False)
    counts = block_counts(len(e), block_hours, draws, rng if rng is not None else np.random.default_rng(0))
    out = []
    for k in lags:
        frame = pd.DataFrame({"g": group.to_numpy(), "e": e.to_numpy(), "s": spread.shift(-k).to_numpy(),
                              "block": np.arange(len(e)) // block_hours}).dropna()
        for g, part in frame.groupby("g"):
            mean, lower, upper, n = (float(v[0]) for v in block_band(part[["s"]].to_numpy(),
                                                                     part["block"].to_numpy(int), counts))
            out.append({"lag": k, "tenth": int(g) + 1, "error_mean": part["e"].mean(), "mean": mean, "lower": lower,
                        "upper": upper, "hours": int(n)})
    return out


def run(df: pd.DataFrame, spec: Spec, plot_dir, quantile: float = 0.95, before: int = 12, after: int = 24,
        correlation_lags: tuple = (-24, 48), tenth_lags: tuple = (0, 1, 2, 3, 6, 12, 24), block_hours: int = 336,
        draws: int = 1000, seed: int = 2025):
    out = plot_dir / "error_spreads"
    out.mkdir(parents=True, exist_ok=True)
    rows = {k: [] for k in ("spreads", "around", "correlation", "tenths")}
    for error in error_columns(spec):
        for zone in zones_with_data(df, error):
            e = hourly(df, zone, error)
            threshold = e.abs().quantile(quantile)
            for spread in spread_columns(spec):
                s = hourly(df, zone, spread)
                key = {"zone": zone, "error": error, "spread": spread}
                rng = np.random.default_rng([seed, zlib.crc32(f"{zone}|{error}|{spread}".encode())])  # one stream each
                groups = by_sign(e, s, quantile)
                rows["spreads"] += [{**key, **g} for g in groups]
                rows["around"] += [{**key, **r} for r in around_runs(e, s, threshold, before, after, block_hours,
                                                                     draws, rng)]
                rows["correlation"] += [{**key, **r} for r in lagged_correlation(e, s, range(correlation_lags[0],
                                                                                              correlation_lags[1] + 1))]
                rows["tenths"] += [{**key, **r} for r in tenths(e, s, tenth_lags, block_hours, draws, rng)]
                print(f"  {zone} {error} / {spread}: mean " + ", ".join(
                    f"{g['mean']:+.1f} ({GROUPS[g['group']]}, {g['hours']} h)" for g in groups))
    tables = {k: pd.DataFrame(v) for k, v in rows.items()}
    for name, table in tables.items():
        table.to_csv(out / f"{name}.csv", index=False)
    _write_report(tables, quantile, f"95 % block-bootstrap intervals (blocks of {block_hours} h, {draws} draws, seed "
                                    f"{seed})", out / "ERROR_SPREADS.md")


def _write_report(tables: dict, quantile: float, intervals: str, path):
    table = tables["spreads"]
    name = lambda c: label(c).split(" (")[0]  # noqa: E731
    wide = table.pivot_table(index=["zone", "error", "spread"], columns="group", values=["mean", "hours"], sort=False)
    report = pd.DataFrame({
        "Zone": [z for z, _, _ in wide.index], "Forecast error": [name(e) for _, e, _ in wide.index],
        "Spread": [name(s) for _, _, s in wide.index],
        **{f"Mean in {GROUPS[g]} hours (EUR/MWh)": [f"{v:+.1f}" for v in wide[("mean", g)]] for g in GROUPS},
        **{f"{GROUPS[g].capitalize()} hours": wide[("hours", g)].astype(int).to_numpy() for g in ("over", "under")}})
    text = [
        "# What the forecast errors do to the price spreads",
        "",
        f"Step 2 of the hypothesis, first look. A large error is |e| above its {100 * quantile:g}th percentile (as in "
        "step 1); over-forecast: e > 0 (e.g. less wind than planned), under-forecast: e < 0. The mean spread in those "
        "hours against its mean in all hours.",
        "",
        md_table(report),
        "",
        *_lag_sections(tables, name, intervals),
    ]
    path.write_text("\n".join(text), encoding="utf-8")
    print(f"  wrote {path.name}")


def _lag_sections(tables: dict, name, intervals: str) -> list[str]:
    keys = ["zone", "error", "spread"]
    around = tables["around"][tables["around"]["h"].isin([-1, 0, 1, 2, 3, 6])]
    around_wide = around.pivot_table(index=[*keys, "sign", "runs"], columns="h", values="mean", sort=False).reset_index()
    around_table = pd.DataFrame({
        "Zone": around_wide["zone"], "Forecast error": around_wide["error"].map(name), "Spread": around_wide["spread"].map(name),
        "Runs of large": [f"{'over' if s > 0 else 'under'}-forecasts ({n})" for s, n in zip(around_wide["sign"], around_wide["runs"])],
        **{f"h = {h:+d}": [f"{v:+.0f}" for v in around_wide[h]] for h in (-1, 0, 1, 2, 3, 6)}})
    corr = tables["correlation"]
    strongest = corr.loc[corr.groupby(keys, sort=False)["corr"].apply(lambda r: r.abs().idxmax())]
    at_zero = corr[corr["lag"] == 0].set_index(keys)["corr"]
    corr_table = pd.DataFrame({
        "Zone": strongest["zone"], "Forecast error": strongest["error"].map(name), "Spread": strongest["spread"].map(name),
        "r at lag 0": [f"{at_zero[tuple(k)]:+.2f}" for k in strongest[keys].to_numpy()],
        "Strongest lag (h)": strongest["lag"], "r there": strongest["corr"].map(lambda v: f"{v:+.2f}")})
    ends = tables["tenths"][(tables["tenths"]["lag"] == 0) & tables["tenths"]["tenth"].isin([1, 10])]
    ends_wide = ends.pivot_table(index=keys, columns="tenth", values=["error_mean", "mean"], sort=False).reset_index()
    tenth_table = pd.DataFrame({
        "Zone": ends_wide["zone"], "Forecast error": ends_wide["error"].map(name), "Spread": ends_wide["spread"].map(name),
        "1st tenth: mean error (MW)": [f"{v:+.0f}" for v in ends_wide[("error_mean", 1)]],
        "mean spread": [f"{v:+.1f}" for v in ends_wide[("mean", 1)]],
        "10th tenth: mean error (MW)": [f"{v:+.0f}" for v in ends_wide[("error_mean", 10)]],
        "mean spread ": [f"{v:+.1f}" for v in ends_wide[("mean", 10)]]})
    return [
        "## Lags: when, and how much",
        "",
        f"Plain spreads (EUR/MWh); {intervals}. **Around a large error**: the mean spread h hours after the first hour "
        "of each run of large errors of one sign (around.csv, h from the first to the last lag, with the intervals).",
        "",
        md_table(around_table),
        "",
        "**Correlation by lag**: r_k = corr(e_t, s_t+k) (correlation.csv, every lag). No interval: errors and spreads "
        "persist, so the band for independent hours would be too narrow.",
        "",
        md_table(corr_table),
        "",
        "**Tenths**: the error in ten equal groups by value, and the mean spread in the same hour (tenths.csv: also later "
        "hours, with the intervals). The first and the last tenth:",
        "",
        md_table(tenth_table),
        "",
    ]
