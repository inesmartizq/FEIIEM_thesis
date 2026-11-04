"""
residual_checks.py — checks of the chosen VARX(p, 0), per bidding zone and
system (the "residual_checks" step of main.py). The lag order p is the one
chosen by the lag_selection step (its lag_orders.csv); the model is fitted by
least squares on every hour valid for that p, with the regressors of
lag_selection.py. The checks report; they do not change the lag order.

AUTOCORRELATION — do the residuals still depend on their own past?
    LM(h)       multivariate Breusch-Godfrey test of no residual
                autocorrelation up to lag h; chi²(h K²) under no
                autocorrelation. Both forms use r_t, the residuals of hours
                t-1..t-h (0 before the sample and in hours not used).
                Robust form, the test: valid also when the residual variance
                changes over time,
                    q_t = r_t net of the model's regressors (least squares)
                    g_t = u_t ⊗ q_t,   LM = (Σ g_t)' (Σ g_t g_t')⁻¹ (Σ g_t).
                Standard form, for comparison: LM = T (K - tr(S⁻¹ S_e)), S_e
                the residual covariance of u_t regressed on the model's
                regressors and r_t. Assumes the same residual variance in
                every hour; when it changes, it rejects too often.
    Size        the largest residual autocorrelation (any pair of variables)
                within a day (lags 1..h) and at whole weeks (168, 336, ... h);
                white noise stays within about ±1.96/√T.
VARIANCE — is the residual variance the same in every hour?
    ARCH-LM(h)  per equation: the squared residual regressed on a constant
                and its own values of hours t-1..t-h; n R² ~ chi²(h) under
                constant variance (n = hours used).
    Kurtosis    per equation: 3 for normal residuals, larger with extreme hours.
STABILITY — the largest modulus of the eigenvalues of the companion matrix:
                below 1, the effect of a shock dies out.
WEEKLY PATTERN — each equation's residual autocorrelation at whole weeks
(168, 336, ... hours, up to acf_lags), for three models fitted on the same
hours (those valid for the longest weekly lag):
    baseline        the chosen model
    weekly lags     the chosen model plus the lags in weekly_lags
    weekly dummies  the chosen model with the calendar dummies weekly_calendar
                    (e.g. hour-of-week instead of hour of day)
    For the baseline also per quarter (Copenhagen local time): the correlation
    within the hours t of the quarter.
RAMP TIMING (ramp_check = (error, ramp) in main.py) — per zone, the hourly
change of the forecast error against the ramp in the same and in the
previous hour. The error (forecast - actual) and the ramp (actual(t) -
actual(t-1)) share actual(t), so in the same hour the points follow a slope
of -1: the reason the model's ramp enters one hour late.

OUTPUT (plots/<name>/residual_checks/)
    residual_autocorrelation.png  per (zone, system): each equation's residual
                                  autocorrelation by lag, white-noise band
    ramp_timing.png               the ramp timing, per zone (with ramp_check)
    RESIDUAL_CHECKS.md            the checks per (zone, system) and equation
    checks.csv, variance.csv,     the same results as data (read by the web step)
    weekly.csv, weekly_quarters.csv, autocorrelation.csv
"""

import math

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.ticker import MultipleLocator
from scipy.stats import chi2, kurtosis

from common import (FONT_SCALE, column_units, md_table, name, save_figure, style_axes, with_unit, zone_color,
                    zone_frame, zones)
from dataframe.building import DERIVED_FEATURES, LOCAL_TZ, Spec
from dataframe.documentation import LITERATURE
from VAR_tests import lag_selection as ls

FOLDERS = ["residual_checks"]
WEEK = 168
RAMP_TIMINGS = {"same hour": 0, "previous hour": 1}  # timing: hours the ramp is shifted by
EQUATION_COLORS = ["#0072B2", "#009E73", "#D55E00", "#CC79A7", "#E69F00", "#56B4E9"]


# ---------------------------------------------------------------------------
# CHECKS
# ---------------------------------------------------------------------------
def _residual_grid(model: dict) -> np.ndarray:
    """The residuals on the zone's full hourly grid, NaN in the hours not used."""
    grid = np.full((len(model["ok"]), model["resid"].shape[1]), np.nan)
    grid[model["ok"]] = model["resid"]
    return grid


def _lagged_residuals(model: dict, h: int) -> np.ndarray:
    """r_t: the residuals of hours t-1..t-h at the hours used (T x hK), 0
    before the sample and in hours not used."""
    K = model["resid"].shape[1]
    grid = np.nan_to_num(_residual_grid(model))
    return np.column_stack([np.vstack([np.zeros((j, K)), grid[:-j]])[model["ok"]] for j in range(1, h + 1)])


def lm_test(model: dict, h: int) -> tuple[float, int, float]:
    """(statistic, degrees of freedom, p-value) of the standard LM(h) test."""
    resid = model["resid"]
    T, K = resid.shape
    aux = np.column_stack([model["X"], _lagged_residuals(model, h)])
    e = resid - aux @ np.linalg.lstsq(aux, resid, rcond=None)[0]
    stat = float(T * (K - np.trace(np.linalg.solve(model["sigma"], e.T @ e / T))))
    df = h * K * K
    return stat, df, float(chi2.sf(stat, df))


def robust_lm_test(model: dict, h: int) -> tuple[float, int, float]:
    """(statistic, degrees of freedom, p-value) of the LM(h) test robust to a
    changing residual variance."""
    resid = model["resid"]
    T, K = resid.shape
    lagged = _lagged_residuals(model, h)
    q = lagged - model["X"] @ np.linalg.lstsq(model["X"], lagged, rcond=None)[0]
    g = (resid[:, :, None] * q[:, None, :]).reshape(T, -1)
    s = g.sum(axis=0)
    stat = float(s @ np.linalg.solve(g.T @ g, s))
    df = h * K * K
    return stat, df, float(chi2.sf(stat, df))


def _lagged_correlation(grid: np.ndarray, j: int, hours: np.ndarray | None = None) -> np.ndarray:
    """corr(u_a at t, u_b at t-j) over the hours t (inside `hours`, a mask of
    the grid, if given) where t and t-j are both used, with the residual
    standard deviations of the used hours (inside `hours`)."""
    used = ~np.isnan(grid).any(axis=1)
    if hours is not None:
        used &= hours
    sd = np.sqrt((grid[used] ** 2).mean(axis=0))  # residuals have mean 0 (in every month, with month dummies)
    now, before = grid[j:], grid[:-j]
    both = used[j:] & ~np.isnan(before).any(axis=1)
    return (now[both].T @ before[both]) / both.sum() / np.outer(sd, sd)


def residual_autocorrelation(model: dict, max_lag: int) -> np.ndarray:
    """R[j - 1, a, b] = corr(u_a at t, u_b at t-j), j = 1..max_lag, over the
    pairs of hours both used."""
    grid = _residual_grid(model)
    return np.array([_lagged_correlation(grid, j) for j in range(1, max_lag + 1)])


def largest_autocorrelation(R: np.ndarray, lags: list, y_cols: list) -> dict:
    """The largest |R| over the given lags: {"r", "lag", "pair": "a on b"} (a at t, b at t - lag)."""
    sub = R[np.asarray(lags) - 1]
    j, a, b = np.unravel_index(np.abs(sub).argmax(), sub.shape)
    return {"r": float(sub[j, a, b]), "lag": int(lags[j]), "pair": f"{y_cols[a]} on {y_cols[b]}"}


def _largest_text(largest: dict) -> str:
    return f"{largest['r']:+.3f} (lag {largest['lag']}, {largest['pair']})"


def arch_lm_test(u: np.ndarray, h: int) -> tuple[float, float]:
    """(statistic, p-value) of the ARCH-LM(h) test for one residual series on
    the hourly grid (NaN = hour not used)."""
    sq = pd.Series(u ** 2)
    lagged = pd.concat({j: sq.shift(j) for j in range(1, h + 1)}, axis=1)
    ok = (sq.notna() & lagged.notna().all(axis=1)).to_numpy()
    y = sq.to_numpy()[ok]
    X = np.column_stack([np.ones(ok.sum()), lagged.to_numpy()[ok]])
    e = y - X @ np.linalg.lstsq(X, y, rcond=None)[0]
    stat = float(ok.sum() * (1 - (e @ e) / ((y - y.mean()) @ (y - y.mean()))))
    return stat, float(chi2.sf(stat, h))


def weekly_pattern(dz: pd.DataFrame, system: list, p: int, exog: list, calendar: list, weekly_lags: list,
                   weekly_calendar: list, weeks: list, quarter: np.ndarray) -> tuple[list, list]:
    """Per equation: {variant: {week: residual autocorrelation}} rows, and the
    baseline's autocorrelation per quarter (see WEEKLY PATTERN above)."""
    lags = list(range(1, p + 1))
    sample = (ls._design(dz, system, lags + list(weekly_lags), exog, calendar)[3]
              & ls._design(dz, system, lags, exog, weekly_calendar)[3])
    models = {"baseline": ls.fit(dz, system, lags, exog, calendar, sample=sample),
              "weekly lags": ls.fit(dz, system, lags + list(weekly_lags), exog, calendar, sample=sample),
              "weekly dummies": ls.fit(dz, system, lags, exog, weekly_calendar, sample=sample)}
    grids = {v: _residual_grid(m) for v, m in models.items()}
    R = {v: {w: _lagged_correlation(g, w) for w in weeks} for v, g in grids.items()}
    by_variant = [{"equation": col, **{f"{w} h, {v}": round(float(R[v][w][i, i]), 3) for w in weeks for v in R}}
                  for i, col in enumerate(system)]
    quarters = sorted(set(quarter))
    by_quarter = [{"equation": col, "lag": f"{w} h", **{f"Q{q}": round(float(
        _lagged_correlation(grids["baseline"], w, quarter == q)[i, i]), 3) for q in quarters}}
        for i, col in enumerate(system) for w in weeks]
    return by_variant, by_quarter


def ramp_timing(df: pd.DataFrame, error: str, ramp: str) -> list[dict]:
    """Per zone: the hourly change of `error` and `ramp` shifted by each of
    RAMP_TIMINGS, with their correlations (see RAMP TIMING above)."""
    rows = []
    for zone in zones(df):
        dz = zone_frame(df, zone)
        change = dz[error].diff()
        shifted = {timing: dz[ramp].shift(k) for timing, k in RAMP_TIMINGS.items()}
        rows.append({"zone": zone, "change": change, **shifted,
                     **{f"r, {timing}": float(change.corr(x)) for timing, x in shifted.items()}})
    return rows


def companion_max_modulus(model: dict) -> float:
    """Largest modulus of the eigenvalues of the companion matrix (< 1 = stable)."""
    A = ls.lag_matrices(model)
    p, K, _ = A.shape
    companion = np.vstack([A.transpose(1, 0, 2).reshape(K, K * p), np.eye(K * (p - 1), K * p)])  # [A_1 ... A_p]
    return float(np.abs(np.linalg.eigvals(companion)).max())


# ---------------------------------------------------------------------------
# OUTPUT
# ---------------------------------------------------------------------------
def _fmt_p(p: float) -> str:
    return "< 0.0001" if p < 1e-4 else f"{p:.4f}"


def plot_autocorrelation(panels: list, endogenous: list, path):
    """panels: [(zone, system label, R, y_cols, T)]."""
    zone_names = list(dict.fromkeys(z for z, *_ in panels))
    ncols = max(sum(1 for z, *_ in panels if z == zone) for zone in zone_names)
    fig, grid = plt.subplots(len(zone_names), ncols, figsize=(5 * ncols, 3.8 * len(zone_names)), squeeze=False)
    used = []
    for r, zone in enumerate(zone_names):
        zone_panels = [p for p in panels if p[0] == zone]
        for c, (_, system, R, y_cols, T) in enumerate(zone_panels):
            ax = grid[r][c]
            used.append(ax)
            lags = np.arange(1, R.shape[0] + 1)
            band = 1.96 / math.sqrt(T)
            ax.axhspan(-band, band, color="0.88", label="white-noise band ±1.96/√T")
            for week in range(WEEK, R.shape[0] + 1, WEEK):
                ax.axvline(week, color="0.5", linewidth=0.8, linestyle=":", label="whole weeks")
            for i, col in enumerate(y_cols):
                ax.plot(lags, R[:, i, i], linewidth=0.9, label=name(col),
                        color=EQUATION_COLORS[endogenous.index(col) % len(EQUATION_COLORS)])
            ax.set_xlim(0, R.shape[0] * 1.03)  # room for the spike at the last whole week
            ax.xaxis.set_major_locator(MultipleLocator(24 * max(1, R.shape[0] // 168)))
            style_axes(ax, f"{zone} — {', '.join(map(name, system.split(', ')))}", "Lag (hours)",
                       "Residual autocorrelation")
        for ax in grid[r][len(zone_panels):]:
            ax.axis("off")
    save_figure(fig, used, "Residual autocorrelation of each equation of the chosen VARX", path)


def plot_ramp_timing(rows: list, error: str, ramp: str, path):
    """One row per zone; columns: the ramp in the same and in the previous hour."""
    units = column_units([error, ramp])
    name = {c: LITERATURE.get(c, {}).get("name", c) for c in (error, ramp)}
    fig, grid = plt.subplots(len(rows), len(RAMP_TIMINGS), figsize=(5 * len(RAMP_TIMINGS), 4.2 * len(rows)),
                             squeeze=False, sharex=True, sharey=True)
    for r, row in enumerate(rows):
        for c, (timing, k) in enumerate(RAMP_TIMINGS.items()):
            ax = grid[r][c]
            ax.scatter(row[timing], row["change"], s=3, alpha=0.2, linewidths=0, color=zone_color(row["zone"]),
                       rasterized=True)
            ax.axline((0, 0), slope=-1, color="0.3", linewidth=1.2, linestyle="--")  # the identity: slope -1
            r_text = f"{row[f'r, {timing}']:+.2f}".replace("-", "−")
            ax.text(0.97, 0.95, f"r = {r_text}", transform=ax.transAxes, ha="right", va="top",
                    fontsize=9 * FONT_SCALE)
            style_axes(ax, f"{row['zone']}, {timing}",
                       with_unit(f"{name[ramp]} at t" + (f"−{k}" if k else ""), units[ramp]) if r == len(rows) - 1
                       else "", with_unit(f"Δ {name[error].split()[0].lower()} error", units[error]) if c == 0 else "")
    save_figure(fig, list(grid.ravel()), f"{name[error]} change vs {name[ramp].lower()}", path, title_size=11)


def _checks_table(checks: pd.DataFrame, h: int) -> pd.DataFrame:
    """The checks as shown in the report."""
    return pd.DataFrame({
        "zone": checks["zone"], "system": checks["system"], "p": checks["p"], "T": checks["T"],
        f"robust LM({h})": checks["robust_lm"].round(1), "robust p": checks["robust_p"].map(_fmt_p),
        f"standard LM({h})": checks["standard_lm"].round(1), "standard p": checks["standard_p"].map(_fmt_p),
        f"largest autocorr., lags 1-{h}": [_largest_text({"r": r, "lag": l, "pair": pr}) for r, l, pr in
                                           zip(checks["day_r"], checks["day_lag"], checks["day_pair"])],
        "largest autocorr., whole weeks": [_largest_text({"r": r, "lag": l, "pair": pr}) if l else "-" for r, l, pr in
                                           zip(checks["week_r"], checks["week_lag"], checks["week_pair"])],
        "white-noise band": checks["band"].map("±{:.3f}".format),
        "max eigenvalue modulus": checks["modulus"].round(4)})


def _variance_table(variance: pd.DataFrame, arch_h: int) -> pd.DataFrame:
    return pd.DataFrame({"zone": variance["zone"], "system": variance["system"], "equation": variance["equation"],
                         f"ARCH-LM({arch_h})": variance["arch_lm"].round(1), "p": variance["arch_p"].map(_fmt_p),
                         "kurtosis": variance["kurtosis"].round(1)})


def write_report(checks: pd.DataFrame, variance: pd.DataFrame, weekly: pd.DataFrame, by_quarter: pd.DataFrame,
                 h: int, arch_h: int, alpha: float, weekly_lags: list, weekly_calendar: list, path,
                 ramp: pd.DataFrame | None = None, ramp_check: tuple = ()):
    unstable = checks[checks["max eigenvalue modulus"] >= 1]
    text = [
        "# Residual checks", "",
        "The VARX(p, 0) with the lag order chosen by the lag_selection step, fitted by least squares on every hour "
        f"valid for it. p < {alpha} = the test rejects.", "",
        f"**Autocorrelation:** LM({h}) tests no residual autocorrelation up to lag {h} (chi²({h} K²)). The robust "
        "form is valid also when the residual variance changes over time; the standard form assumes it does not. "
        "Size: the largest residual autocorrelation (any pair of variables; 'a on b' = a at t, b at t - lag) within "
        "a day and at whole weeks; white noise stays within the band ±1.96/√T.", "",
        f"**Variance:** ARCH-LM({arch_h}) per equation tests a constant residual variance (chi²({arch_h})); kurtosis is "
        "3 for normal residuals.", "",
        "**Stability:** " + ("every model is stable (largest eigenvalue modulus of the companion matrix below 1)."
                             if unstable.empty else "UNSTABLE: " + "; ".join(
                                 f"{r['zone']} {r['system']} ({r['max eigenvalue modulus']:.4f})"
                                 for r in unstable.to_dict("records"))), "",
        "## Autocorrelation and stability", "", md_table(checks), "",
        "## Variance", "", md_table(variance), "",
        "## Weekly pattern", "",
        "Each equation's residual autocorrelation at whole weeks, for three models fitted on the same hours: the "
        f"chosen model (baseline), the chosen model plus lags {', '.join(map(str, weekly_lags))} (weekly lags), and "
        f"the chosen model with the calendar dummies {', '.join(weekly_calendar)} (weekly dummies).", "",
        md_table(weekly), "",
        "Baseline, per quarter (Copenhagen local time): the correlation within the quarter's hours.", "",
        md_table(by_quarter), "",
    ]
    if ramp is not None:
        text += ["## Ramp timing", "",
                 f"Correlation of the hourly change of {ramp_check[0]} with {ramp_check[1]} in the same and in the "
                 "previous hour (ramp_timing.png). In the same hour the two share the actual value, so the points "
                 "follow a slope of -1.", "", md_table(ramp), ""]
    path.write_text("\n".join(text), encoding="utf-8")
    print(f"  wrote {path.name}")


# ---------------------------------------------------------------------------
# ENTRY POINT
# ---------------------------------------------------------------------------
def run(df: pd.DataFrame, spec: Spec, plot_dir, lm_lags: int = 24, arch_lags: int = 24, acf_lags: int = 336,
        alpha: float = 0.05, weekly_lags: list = (), weekly_calendar: list = (), ramp_check: tuple = ()) -> pd.DataFrame:
    """ramp_check: (forecast error, ramp in the same hour), both dataframe columns, for the RAMP TIMING figure."""
    out = plot_dir / "residual_checks"
    out.mkdir(parents=True, exist_ok=True)
    orders = ls.read_orders(plot_dir)
    weeks = list(range(WEEK, acf_lags + 1, WEEK))
    checks, variance, panels, weekly, by_quarter, acf = [], [], [], [], [], []
    for zone in zones(df):
        dz, exog, systems = ls.zone_inputs(df, spec, zone)
        for c in weekly_calendar:  # identifiers not in the dataframe, from their registry entry
            if c not in dz:
                dz[c] = DERIVED_FEATURES[c]["func"](dz)
        quarter = dz["datetime_utc"].dt.tz_convert(LOCAL_TZ).dt.quarter.to_numpy()
        for system in systems:
            if (zone, tuple(system)) not in orders:
                raise KeyError(f"{zone} ({', '.join(system)}) has no lag order in {ls.ORDERS_FILE}: run the "
                               f"lag_selection step first")
            p = orders[(zone, tuple(system))]["p"]
            name = ls.system_label(system, systems)
            print(f"  [{zone}] residual checks: {', '.join(system)}, p = {p}")
            m = ls.fit(dz, system, list(range(1, p + 1)), exog, spec.calendar)
            T = len(m["resid"])
            R = residual_autocorrelation(m, acf_lags)
            robust, standard = robust_lm_test(m, lm_lags), lm_test(m, lm_lags)
            day = largest_autocorrelation(R, list(range(1, lm_lags + 1)), system)
            week = largest_autocorrelation(R, weeks, system) if weeks else {"r": np.nan, "lag": 0, "pair": ""}
            checks.append({"zone": zone, "system": name, "p": p, "T": T, "lm_df": robust[1],
                           "lm_crit_5": float(chi2.ppf(1 - alpha, robust[1])), "robust_lm": robust[0],
                           "robust_p": robust[2], "standard_lm": standard[0], "standard_p": standard[2],
                           "day_r": day["r"], "day_lag": day["lag"], "day_pair": day["pair"],
                           "week_r": week["r"], "week_lag": week["lag"], "week_pair": week["pair"],
                           "band": 1.96 / math.sqrt(T), "modulus": companion_max_modulus(m)})
            grid = _residual_grid(m)
            for i, col in enumerate(system):
                stat, p_arch = arch_lm_test(grid[:, i], arch_lags)
                variance.append({"zone": zone, "system": name, "equation": col, "arch_lm": stat, "arch_p": p_arch,
                                 "kurtosis": float(kurtosis(m["resid"][:, i], fisher=False))})
            acf += [{"zone": zone, "system": name, "equation": col, "lag": j + 1, "r": R[j, i, i]}
                    for i, col in enumerate(system) for j in range(acf_lags)]
            panels.append((zone, name, R, system, T))
            if weeks:
                rows, quarter_rows = weekly_pattern(dz, system, p, exog, spec.calendar, weekly_lags, weekly_calendar,
                                                    weeks, quarter)
                weekly += [{"zone": zone, "system": name, **r} for r in rows]
                by_quarter += [{"zone": zone, "system": name, **r} for r in quarter_rows]
    tables = {"checks": pd.DataFrame(checks), "variance": pd.DataFrame(variance), "weekly": pd.DataFrame(weekly),
              "weekly_quarters": pd.DataFrame(by_quarter), "autocorrelation": pd.DataFrame(acf)}
    for file, table in tables.items():  # the results as data (read by the web step)
        table.to_csv(out / f"{file}.csv", index=False)
    plot_autocorrelation(panels, list(spec.endogenous), out / "residual_autocorrelation.png")
    ramp = None
    if ramp_check:
        rows = ramp_timing(df, *ramp_check)
        plot_ramp_timing(rows, *ramp_check, out / "ramp_timing.png")
        ramp = pd.DataFrame([{"zone": r["zone"], **{f"r, {t}": round(r[f"r, {t}"], 3) for t in RAMP_TIMINGS}}
                             for r in rows])
    write_report(_checks_table(tables["checks"], lm_lags), _variance_table(tables["variance"], arch_lags),
                 tables["weekly"], tables["weekly_quarters"], lm_lags, arch_lags, alpha, weekly_lags, weekly_calendar,
                 out / "RESIDUAL_CHECKS.md", ramp, ramp_check)
    for r in checks:
        print(f"  {r['zone']} {r['system']}: p = {r['p']}, robust LM({lm_lags}) p {_fmt_p(r['robust_p'])}, "
              f"modulus {r['modulus']:.4f}")
    return tables["checks"]
