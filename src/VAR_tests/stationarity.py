"""
stationarity.py — stationarity tests of the ENDOGENOUS variables, per bidding
zone (the "stationarity" step of main.py). Nothing is differenced or
transformed: the tests only report.

TESTS ON THE SERIES AS THEY ARE (levels)
    ADF   H0 unit root. Constant; lag by AIC up to 48, searched again up to 168
          when 48 itself is selected.
    KPSS  H0 stationary. Constant; automatic bandwidth; the exact asymptotic
          p-value (statsmodels truncates its p-value at 0.01 / 0.10).
    PP    Phillips-Perron, H0 unit root, constant: reported, not in the decision.
    Decision at alpha (a test rejects when p < alpha):
        ADF rejects,         KPSS does not reject -> STATIONARY
        ADF does not reject, KPSS rejects         -> UNIT ROOT
        both reject                               -> CONFLICT
        neither rejects                           -> INCONCLUSIVE
    Missing hours are dropped before testing (the series is joined across
    them), never interpolated.

TESTS AFTER THE CALENDAR DUMMIES
    ADF and KPSS on the residuals of an OLS of each series on a constant and
    the dataframe's calendar dummies (its fe_* exogenous columns). After the
    dummies the standard critical values do not apply (the KPSS partial sums
    return to ~0 in every dummy period, so the statistic is small by
    construction), so they are simulated per series:
      KPSS  AR(p) (BIC, max 48) fitted to the residuals, innovations resampled
            in moving blocks of 168 h, N stationary series, the SAME dummies
            projected out, KPSS with the same bandwidth rule: 95th percentile.
            For the automatic bandwidth and for 168; when the two verdicts
            differ the decision is BANDWIDTH-SENSITIVE.
      ADF   random walks with steps resampled in 168-h blocks from the AR
            innovations, the same dummies projected out, ADF with the lag fixed
            at the data's lag: 5th percentile.

ROBUSTNESS (levels): expanding windows ending in the last year (when the
data spans several years), KPSS with fixed bandwidths 48 and 168, and the
decision at alpha 1 % and 10 %.
ROBUSTNESS (after the dummies): the same bandwidths, each against its own
simulated critical value (simulated on the same series as the automatic one),
and the decision at alpha 1 % and 10 % from the simulated p-values; no windows.

OUTPUT (plots/<name>/stationarity_tests/)
    stationarity_levels.png          the tests on the series as they are
    stationarity_after_dummies.png   the tests after the calendar dummies
    stationarity_robustness.png      decision per robustness check (levels)
    stationarity_robustness_after_dummies.png   the same, after the dummies
    STATIONARITY.md                  every number and the settings
    levels.csv, after_dummies.csv,   the same results as data (read by the web step)
    robustness.csv, robustness_after_dummies.csv
"""

import math
import textwrap
import warnings
import zlib

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from arch.unitroot import PhillipsPerron
from scipy.integrate import quad
from scipy.linalg import cho_factor, cho_solve
from scipy.optimize import brentq
from scipy.signal import lfilter
from scipy.special import binom, kv
from statsmodels.tools.sm_exceptions import InterpolationWarning
from statsmodels.tsa.stattools import adfuller, kpss

from common import FONT_SCALE, label, md_table, zone_frame, zones
from dataframe.building import Spec

FOLDERS = ["stationarity_tests"]

STATIONARY, UNIT_ROOT, CONFLICT, INCONCLUSIVE = "STATIONARY", "UNIT ROOT", "CONFLICT", "INCONCLUSIVE"
BW_SENSITIVE = "BANDWIDTH-SENSITIVE"
DECISION_COLORS = {STATIONARY: "#4CAF50", CONFLICT: "#FF9800", UNIT_ROOT: "#E53935", INCONCLUSIVE: "#9E9E9E",
                   BW_SENSITIVE: "#FFD54F"}
DECISION_CODES = {STATIONARY: "S", UNIT_ROOT: "U", CONFLICT: "C", INCONCLUSIVE: "I", BW_SENSITIVE: "B"}

ADF_MAX_LAG, ADF_MAX_LAG_LONG = 48, 168  # ADF searched again up to the long limit when the short one is selected
KPSS_BANDWIDTHS = [48, 168]              # robustness: fixed KPSS bandwidths next to the automatic one
BW_CHECK = 168                           # after the dummies: BANDWIDTH-SENSITIVE when this one and the automatic disagree
ROBUSTNESS_ALPHAS = [0.01, 0.10]
KPSS_CRITICAL_5PCT = 0.463               # KPSS level-stationarity 5 % critical value (Kwiatkowski et al. 1992)
AR_MAX = 48                              # BIC bound of the AR fitted for the simulations
BLOCK_HOURS = 168                        # moving-block length of the resampled innovations
BURN_IN = 500


# ---------------------------------------------------------------------------
# DECISION AND TESTS
# ---------------------------------------------------------------------------
def _classify(adf_rejects: bool, kpss_rejects: bool) -> str:
    if adf_rejects and not kpss_rejects:
        return STATIONARY
    if kpss_rejects and not adf_rejects:
        return UNIT_ROOT
    return CONFLICT if adf_rejects else INCONCLUSIVE


def decide(adf_p: float, kpss_p: float, alpha: float = 0.05) -> str:
    """A test rejects when p < alpha (p exactly at alpha does not reject)."""
    return _classify(adf_p < alpha, kpss_p < alpha)


def kpss_asymptotic_pvalue(stat: float) -> float:
    """Exact asymptotic p-value of the KPSS level-stationarity statistic: under
    H0 it converges to the integral of a squared Brownian bridge (the
    Cramér-von Mises omega^2 distribution behind the critical values 0.347 /
    0.463 / 0.739).
      - stat < 0.2: Anderson & Darling (1952) series for the CDF;
      - stat >= 0.2: Smirnov's integral formula for the upper tail, accurate for
        tiny p (1 - CDF loses all precision below ~1e-11); endpoint
        singularities removed with t = a + (b - a)(1 - cos phi) / 2."""
    x = float(stat)
    if x <= 0:
        return 1.0
    if x < 0.2:
        total = 0.0
        for j in range(40):
            y = (4 * j + 1) ** 2 / (16 * x)
            total += abs(binom(-0.5, j)) * math.sqrt(4 * j + 1) * math.exp(-y) * kv(0.25, y)
        return float(min(1.0, max(0.0, 1 - total / (math.pi * math.sqrt(x)))))
    total = 0.0
    for k in range(1, 201):
        a, b = (2 * k - 1) * math.pi, 2 * k * math.pi

        def integrand(phi, a=a, b=b):
            t = a + (b - a) * (1 - math.cos(phi)) / 2
            s = -math.sin(t)
            if s <= 0:
                return 0.0
            return 2 * math.sqrt(t / s) * math.exp(-x * t * t / 2) / t * (b - a) / 2 * math.sin(phi)

        v, _ = quad(integrand, 0, math.pi, limit=200, epsabs=0, epsrel=1e-11)
        total += (-1) ** (k + 1) * v
        if v == 0 or abs(v) <= 1e-15 * abs(total):
            break
    return float(min(1.0, max(0.0, total / math.pi)))


def _kpss_test(x: np.ndarray, nlags="auto") -> dict:
    """KPSS with a constant; the p-value is the exact asymptotic one."""
    if nlags != "auto" and not nlags < len(x):
        raise ValueError(f"KPSS nlags={nlags} must be smaller than the number of observations ({len(x)})")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", InterpolationWarning)
        stat, _, lags, _ = kpss(x, regression="c", nlags=nlags, result_object=False)
    return {"kpss_stat": float(stat), "kpss_p": kpss_asymptotic_pvalue(stat), "kpss_lags": int(lags)}


def _adf_lag(x: np.ndarray, max_lag: int, ic: str = "aic") -> int:
    """The lag statsmodels' adfuller(autolag='AIC' or 'BIC', regression='c')
    selects, computed exactly but fast: the max_lag + 1 nested regressions
    [const, x_(t-1), dx_(t-1), ..., dx_(t-k)] of dx_t on one common sample all
    come from ONE QR decomposition (RSS_k = y'y - sum of the first k + 2
    squared elements of Q'y). ~30x faster at max_lag = 168."""
    dx = np.diff(x)
    n = len(dx) - max_lag
    y = dx[max_lag:]
    X = np.column_stack([np.ones(n), x[max_lag:-1]] + [dx[max_lag - k:-k] for k in range(1, max_lag + 1)])
    q, _ = np.linalg.qr(X)
    rss = y @ y - np.cumsum((q.T @ y) ** 2)
    penalty = math.log(n) if ic == "bic" else 2.0
    crit = n * np.log(rss / n) + penalty * np.arange(1, X.shape[1] + 1)
    return int(np.argmin(crit[1:]))  # crit[1] = 0 lags (constant + x_(t-1))


def _adf_test(x: np.ndarray, max_lag: int = ADF_MAX_LAG, max_lag_long: int | None = ADF_MAX_LAG_LONG) -> dict:
    """ADF with a constant, lag by AIC up to max_lag (up to max_lag_long when
    max_lag itself is selected); the final regression is statsmodels' adfuller."""
    lags, used = _adf_lag(x, max_lag), max_lag
    if max_lag_long and lags == max_lag:
        lags, used = _adf_lag(x, max_lag_long), max_lag_long
    stat, p, _, _, crit = adfuller(x, maxlag=lags, regression="c", autolag=None, result_object=False)
    return {"adf_stat": float(stat), "adf_p": float(p), "adf_lags": int(lags), "adf_max_lag": used,
            "adf_crit_5": float(crit["5%"])}


def stationarity_tests(series: pd.Series, alpha: float = 0.05, kpss_nlags="auto") -> dict:
    """ADF, KPSS and Phillips-Perron on the series with missing hours dropped
    (counted, never interpolated), plus the decision (ADF + KPSS)."""
    x = series.dropna().to_numpy(dtype=float)
    adf, k = _adf_test(x), _kpss_test(x, kpss_nlags)
    pp = PhillipsPerron(x, trend="c")
    return {"n_obs": len(x), "n_dropped": int(series.isna().sum()), **adf, **k,
            "pp_stat": float(pp.stat), "pp_p": float(pp.pvalue), "decision": decide(adf["adf_p"], k["kpss_p"], alpha)}


# ---------------------------------------------------------------------------
# CALENDAR DUMMIES AND SIMULATED CRITICAL VALUES
# ---------------------------------------------------------------------------
def _dummy_design(y: pd.Series, categories: list) -> tuple[np.ndarray, pd.Series]:
    """[constant, one dummy per category of each series in `categories`] on
    the hours where y and every category are observed (first category
    present dropped, so no perfect collinearity with the constant)."""
    ok = y.notna()
    for c in categories:
        ok &= c.notna()
    parts = [pd.Series(1.0, index=y.index[ok])]
    for i, c in enumerate(categories):
        parts.append(pd.get_dummies(c[ok].astype("Int64"), prefix=f"d{i}", drop_first=True, dtype=float))
    return pd.concat(parts, axis=1).to_numpy(float), ok


def residualise(y: pd.Series, categories: list) -> tuple[pd.Series, float, int]:
    """Residuals of an OLS of y on [constant, dummies], on y's index (hours not
    used: NaN). y itself is never changed. Returns (residuals, R², number of
    dummy columns)."""
    X, ok = _dummy_design(y, categories)
    v = y[ok].to_numpy(float)
    e = v - X @ np.linalg.lstsq(X, v, rcond=None)[0]
    resid = pd.Series(np.nan, index=y.index)
    resid[ok] = e
    r2 = 1 - (e @ e) / ((v - v.mean()) @ (v - v.mean())) if len(v) else np.nan
    return resid, float(r2), X.shape[1] - 1


def _fit_ar_bic(e: np.ndarray, max_lag: int = AR_MAX) -> tuple[np.ndarray, np.ndarray]:
    """AR(p) without constant on the centred series, p by BIC up to max_lag on
    the common sample (as statsmodels' ar_select_order, from one QR
    decomposition), refitted by OLS. Returns (phi_1..phi_p, centred innovations)."""
    e = np.asarray(e, float) - np.mean(e)
    n = len(e) - max_lag
    y = e[max_lag:]
    q, _ = np.linalg.qr(np.column_stack([e[max_lag - k:-k] for k in range(1, max_lag + 1)]))
    rss = np.r_[y @ y, y @ y - np.cumsum((q.T @ y) ** 2)]
    p = int(np.argmin(n * np.log(rss / n) + np.arange(max_lag + 1) * math.log(n)))
    if p == 0:
        return np.zeros(0), e
    Xp = np.column_stack([e[p - k:-k] for k in range(1, p + 1)])
    phi = np.linalg.lstsq(Xp, e[p:], rcond=None)[0]
    resid = e[p:] - Xp @ phi
    return phi, resid - resid.mean()


def _block_indices(n_innov: int, length: int, n_sim: int, block: int, rng) -> np.ndarray:
    """(n_sim, length) indices into the innovations: consecutive runs of
    `block` indices from random starts (moving-block bootstrap)."""
    block = min(block, n_innov)
    starts = rng.integers(0, n_innov - block + 1, size=(n_sim, -(-length // block)))
    return (starts[:, :, None] + np.arange(block)[None, None, :]).reshape(n_sim, -1)[:, :length]


def _resample(innov: np.ndarray, length: int, n_sim: int, rng, block: int | None) -> np.ndarray:
    """(n_sim, length) innovations, in moving blocks (block=None: i.i.d.)."""
    if block:
        return innov[_block_indices(len(innov), length, n_sim, block, rng)]
    return rng.choice(innov, size=(n_sim, length), replace=True)


def _project_out(q: np.ndarray | None, y: np.ndarray) -> np.ndarray:
    """Residuals of each column of y after [constant, dummies] (orthonormal
    basis q), or after a constant only (q=None)."""
    return y - q @ (q.T @ y) if q is not None else y - y.mean(axis=0)


def kpss_null(phi: np.ndarray, innov: np.ndarray, n: int, q, n_sim: int, rng, bandwidths=("auto", 168),
              block: int | None = BLOCK_HOURS, chunk: int = 500) -> dict:
    """KPSS statistics of n_sim stationary AR(phi) series of length n after
    the projection q, per bandwidth rule: {bandwidth: array}."""
    out = {bw: [] for bw in bandwidths}
    for start in range(0, n_sim, chunk):
        m = min(chunk, n_sim - start)
        eps = _resample(innov, n + BURN_IN, m, rng, block)
        paths = (lfilter([1.0], np.r_[1.0, -phi], eps, axis=1) if len(phi) else eps)[:, BURN_IN:].T
        paths = _project_out(q, paths)
        for bw in bandwidths:
            out[bw].extend(_kpss_test(paths[:, j], bw)["kpss_stat"] for j in range(m))
    return {bw: np.array(v) for bw, v in out.items()}


def _adf_tstat(x: np.ndarray, lag: int) -> float:
    """ADF t-statistic (constant, `lag` lagged differences): the regression of
    adfuller(autolag=None), solved through the normal equations (Cholesky). The
    same statistic, several times faster than a general least-squares solver,
    which matters for the thousands of simulated paths."""
    dx = np.diff(x)
    n = len(dx) - lag
    X = np.column_stack([np.ones(n), x[lag:-1]] + [dx[lag - k:-k] for k in range(1, lag + 1)])
    y = dx[lag:]
    factor = cho_factor(X.T @ X)
    beta = cho_solve(factor, X.T @ y)
    resid = y - X @ beta
    s2 = resid @ resid / (n - X.shape[1])
    var_gamma = cho_solve(factor, np.eye(X.shape[1])[:, 1])[1]  # [(X'X)^-1]_{11}
    return float(beta[1] / math.sqrt(s2 * var_gamma))


def adf_null(innov: np.ndarray, n: int, q, lag: int, n_sim: int, rng, block: int | None = BLOCK_HOURS) -> np.ndarray:
    """ADF statistics (lag fixed) of n_sim random walks of length n whose steps
    are resampled from the innovations, after the projection q. (An AR on the
    differences of a stationary series would over-difference it.)"""
    steps = _resample(innov, n, n_sim, rng, block).T
    paths = _project_out(q, np.cumsum(steps, axis=0))
    return np.array([_adf_tstat(paths[:, j], lag) for j in range(n_sim)])


def _rng(seed: int, zone: str, col: str) -> np.random.Generator:
    """One reproducible stream per (zone, variable): adding or removing a
    variable does not change the others' simulated critical values."""
    return np.random.default_rng([seed, zlib.crc32(f"{zone}|{col}".encode())])


# ---------------------------------------------------------------------------
# THE THREE TABLES
# ---------------------------------------------------------------------------
def kpss_critical_value(alpha: float) -> float:
    """The KPSS statistic whose exact asymptotic p-value is alpha (0.463 at 5 %)."""
    return float(brentq(lambda s: kpss_asymptotic_pvalue(s) - alpha, 0.01, 10.0))


def run_levels(df: pd.DataFrame, endogenous: list, alpha: float) -> pd.DataFrame:
    rows = []
    kpss_crit = kpss_critical_value(alpha)
    for zone in zones(df):
        dz = zone_frame(df, zone)
        for col in endogenous:
            print(f"  [{zone}] levels: {col}")
            rows.append({"zone": zone, "series": col, **stationarity_tests(dz[col], alpha), "kpss_crit": kpss_crit})
    return pd.DataFrame(rows)


def run_after_dummies(df: pd.DataFrame, endogenous: list, calendar: list, alpha: float, kpss_draws: int,
                      adf_draws: int, seed: int) -> pd.DataFrame:
    rows = []
    for zone in zones(df):
        dz = zone_frame(df, zone)
        for col in endogenous:
            print(f"  [{zone}] after the dummies: {col} (KPSS N = {kpss_draws}, ADF N = {adf_draws})")
            rng = _rng(seed, zone, col)
            resid, r2, n_dummies = residualise(dz[col], [dz[c] for c in calendar])
            X, ok = _dummy_design(dz[col], [dz[c] for c in calendar])
            q = np.linalg.qr(X)[0]
            e = resid.to_numpy()[ok]
            adf = _adf_test(e)
            bandwidths = ["auto", *KPSS_BANDWIDTHS]  # every bandwidth on the same simulated series
            k = {bw: _kpss_test(e, bw)["kpss_stat"] for bw in bandwidths}
            phi, innov = _fit_ar_bic(e)
            null_kpss = kpss_null(phi, innov, len(e), q, kpss_draws, rng, bandwidths)
            crit = {bw: float(np.quantile(null_kpss[bw], 0.95)) for bw in bandwidths}
            null_adf = adf_null(innov, len(e), q, adf["adf_lags"], adf_draws, rng)
            adf_crit = float(np.quantile(null_adf, 0.05))
            passes = {bw: k[bw] < crit[bw] for bw in bandwidths}
            decision = (BW_SENSITIVE if passes["auto"] != passes[BW_CHECK]
                        else _classify(adf["adf_stat"] < adf_crit, not passes["auto"]))
            rows.append({"zone": zone, "series": col, "n_obs": len(e), "n_dummies": n_dummies, "r2": r2,
                         "adf_stat": adf["adf_stat"], "adf_lags": adf["adf_lags"], "adf_max_lag": adf["adf_max_lag"],
                         "adf_crit_sim": adf_crit, "adf_p_sim": float((null_adf <= adf["adf_stat"]).mean()),
                         "ar_order": len(phi),
                         "kpss_stat": k["auto"], "kpss_crit_sim": crit["auto"],
                         "kpss_p_sim": float((null_kpss["auto"] >= k["auto"]).mean()),
                         **{key: value for bw in KPSS_BANDWIDTHS for key, value in (
                             (f"kpss_stat_{bw}", k[bw]), (f"kpss_crit_{bw}_sim", crit[bw]),
                             (f"kpss_p_{bw}_sim", float((null_kpss[bw] >= k[bw]).mean())))},
                         "decision": decision})
    return pd.DataFrame(rows)


def run_robustness(df: pd.DataFrame, endogenous: list, levels: pd.DataFrame, alpha: float) -> pd.DataFrame:
    """One row per (zone, variable), one column per check: decision labels."""
    grid = levels[["zone", "series"]].copy()
    grid["Levels"] = levels["decision"].to_numpy()
    base = levels.set_index(["zone", "series"])
    years = df["datetime_utc"].dt.year
    first, last = int(years.min()), int(years.max())
    for first_year in range(last, first, -1):  # the full window is the levels test itself
        name = f"{first_year}-{str(last)[2:]}" if first_year < last else f"{last}"
        window = df[years >= first_year]
        decisions = []
        for zone, col in zip(grid["zone"], grid["series"]):
            print(f"  [{zone}] window {name}: {col}")
            decisions.append(stationarity_tests(zone_frame(window, zone)[col], alpha)["decision"])
        grid[f"Window {name}"] = decisions
    for bw in KPSS_BANDWIDTHS:
        decisions = []
        for zone, col in zip(grid["zone"], grid["series"]):
            x = zone_frame(df, zone)[col].dropna().to_numpy(dtype=float)
            decisions.append(decide(base.loc[(zone, col), "adf_p"], _kpss_test(x, bw)["kpss_p"], alpha))
        grid[f"KPSS bw {bw}"] = decisions
    for a in ROBUSTNESS_ALPHAS:
        grid[f"alpha {a:.0%}"] = [decide(r.adf_p, r.kpss_p, a) for r in levels.itertuples()]
    return grid


def run_robustness_after(after: pd.DataFrame) -> pd.DataFrame:
    """The decision after the dummies under the same checks as the levels (no windows: each would need its own
    simulations): KPSS with each fixed bandwidth against its own simulated critical value (ADF unchanged), and
    the decision at the other significance levels from the simulated p-values. One row per (zone, variable)."""
    grid = after[["zone", "series"]].copy()
    grid["After dummies"] = after["decision"].to_numpy()
    adf_rejects = (after["adf_stat"] < after["adf_crit_sim"]).to_numpy()
    for bw in KPSS_BANDWIDTHS:
        kpss_rejects = (after[f"kpss_stat_{bw}"] >= after[f"kpss_crit_{bw}_sim"]).to_numpy()
        grid[f"KPSS bw {bw}"] = [_classify(a, k) for a, k in zip(adf_rejects, kpss_rejects)]
    for a in ROBUSTNESS_ALPHAS:
        grid[f"alpha {a:.0%}"] = [decide(r.adf_p_sim, r.kpss_p_sim, a) for r in after.itertuples()]
    return grid


# ---------------------------------------------------------------------------
# OUTPUT
# ---------------------------------------------------------------------------
def _fmt_p(p: float, exact: bool = False) -> str:
    """p-value: 4 decimals; below 0.0001 '< 0.0001', or (exact) scientific."""
    if p >= 1e-4:
        return f"{p:.4f}"
    return ("< 1e-300" if p == 0 else f"{p:.2e}") if exact else "< 0.0001"


def _stat_with_p(stat: float, p: float, exact: bool = False) -> str:
    ps = _fmt_p(p, exact)
    return f"{stat:.3f} (p {ps})" if ps.startswith("<") else f"{stat:.3f} (p = {ps})"


def _lags(lags: int, max_lag: int) -> str:
    return f"{lags} (max {max_lag})" if max_lag != ADF_MAX_LAG else f"{lags}"


def _png_table(table: pd.DataFrame, out_path, title: str, notes: list, decisions: dict | None = None,
               shade: dict | None = None, red: dict | None = None, font: float = 8.5):
    """Table image. decisions: {(row, col): decision} colour-coded cells;
    shade: {(row, col): True / False} light green (points to stationarity) /
    light red; red: {(row, col): True} red bold text."""
    decisions, shade, red = decisions or {}, shade or {}, red or {}
    fig, ax = plt.subplots(figsize=(1.3 + 1.1 * len(table.columns), 0.3 * len(table) + 1.0))
    ax.axis("off")
    tab = ax.table(cellText=table.astype(str).values, colLabels=list(table.columns), cellLoc="center", loc="center")
    tab.auto_set_font_size(False)
    tab.set_fontsize(font * FONT_SCALE)
    tab.scale(1, 1.45)
    tab.auto_set_column_width(list(range(len(table.columns))))
    for (r, c), cell in tab.get_celld().items():
        if r == 0:
            cell.set_text_props(weight="bold")
            cell.set_facecolor("#E0E0E0")
            cell.set_height(cell.get_height() * 2)
        elif (r - 1, c) in decisions:
            d = decisions[(r - 1, c)]
            cell.set_facecolor(DECISION_COLORS[d])
            cell.set_text_props(weight="bold", color="white" if d in (STATIONARY, UNIT_ROOT) else "black")
        else:
            if (r - 1, c) in shade:
                cell.set_facecolor("#D4EDDA" if shade[(r - 1, c)] else "#F8D7DA")
            if red.get((r - 1, c)):
                cell.get_text().set_color("#C62828")
                cell.get_text().set_fontweight("bold")
    ax.set_title(title, fontsize=11 * FONT_SCALE, pad=14 * FONT_SCALE)
    ax.text(0.5, -0.02, "\n".join(textwrap.fill(n, 170 // FONT_SCALE) for n in notes), transform=ax.transAxes,
            ha="center", va="top", fontsize=8.5 * FONT_SCALE)
    fig.savefig(out_path, dpi=140, bbox_inches="tight", pad_inches=0.25)
    plt.close(fig)
    print(f"  wrote {out_path.name}")


def _verdict(table: pd.DataFrame) -> str:
    flagged = [f"{r.series} ({r.zone}): {r.decision}" for r in table.itertuples() if r.decision != STATIONARY]
    return "All stationary." if not flagged else "Not stationary: " + "; ".join(flagged)


def _missing_note(levels: pd.DataFrame) -> str:
    dropped = levels[levels["n_dropped"] > 0]
    if dropped.empty:
        return "No missing hours."
    return ("Missing hours dropped before testing (not interpolated): "
            + "; ".join(f"{r.series} {r.zone} {r.n_dropped}" for r in dropped.itertuples()) + ".")


def table_levels(levels: pd.DataFrame, alpha: float, path):
    t = pd.DataFrame({
        "Area": levels["zone"], "Variable": levels["series"].map(label),
        "ADF statistic (p-value)": [_stat_with_p(s, p) for s, p in zip(levels["adf_stat"], levels["adf_p"])],
        "ADF lags": [_lags(l, m) for l, m in zip(levels["adf_lags"], levels["adf_max_lag"])],
        "Phillips-Perron statistic (p-value)": [_stat_with_p(s, p) for s, p in zip(levels["pp_stat"], levels["pp_p"])],
        "KPSS statistic (p-value)": [_stat_with_p(s, p, exact=True) for s, p in zip(levels["kpss_stat"], levels["kpss_p"])],
        "Decision": levels["decision"],
    })
    col = list(t.columns).index
    shade, red = {}, {}
    for i, r in enumerate(levels.itertuples()):
        shade[(i, col("ADF statistic (p-value)"))] = r.adf_p < alpha
        shade[(i, col("Phillips-Perron statistic (p-value)"))] = r.pp_p < alpha
        shade[(i, col("KPSS statistic (p-value)"))] = r.kpss_p >= alpha
        red[(i, col("KPSS statistic (p-value)"))] = r.kpss_p < 0.01
    crit = levels["adf_crit_5"]
    _png_table(t, path, f"Stationarity of the endogenous variables as they are (levels, alpha = {alpha})", [
        _verdict(levels),
        f"ADF and Phillips-Perron (H0: unit root): the more negative, the stronger the evidence against a unit root "
        f"(ADF 5 % critical value {crit.min():.2f}). KPSS (H0: stationary): the larger, the stronger the evidence "
        f"against stationarity (5 % critical value {KPSS_CRITICAL_5PCT}).",
        f"Green = the test points to stationarity at {alpha:.0%}, light red = it does not; KPSS text red if p < 0.01. "
        f"ADF: constant, lag by AIC up to {ADF_MAX_LAG}, searched again up to {ADF_MAX_LAG_LONG} where "
        f"{ADF_MAX_LAG} was selected ('max {ADF_MAX_LAG_LONG}'). KPSS: constant, automatic bandwidth, exact "
        f"asymptotic p-value. Decision from ADF and KPSS; Phillips-Perron is supporting only.",
        _missing_note(levels)],
        decisions={(i, col("Decision")): d for i, d in enumerate(levels["decision"])}, shade=shade, red=red)


def table_after_dummies(after: pd.DataFrame, calendar: list, kpss_draws: int, adf_draws: int, seed: int, path):
    t = pd.DataFrame({
        "Area": after["zone"], "Variable": after["series"].map(label),
        "Dummy R²": after["r2"].map("{:.3f}".format),
        "ADF statistic": after["adf_stat"].map("{:.2f}".format),
        "ADF lags": [_lags(l, m) for l, m in zip(after["adf_lags"], after["adf_max_lag"])],
        "ADF 5% crit. (sim.)": after["adf_crit_sim"].map("{:.2f}".format),
        "KPSS statistic": after["kpss_stat"].map("{:.3f}".format),
        "KPSS 5% crit. (sim.)": after["kpss_crit_sim"].map("{:.3f}".format),
        "KPSS statistic (bw 168)": after["kpss_stat_168"].map("{:.3f}".format),
        "KPSS 5% crit. bw 168 (sim.)": after["kpss_crit_168_sim"].map("{:.3f}".format),
        "Decision": after["decision"],
    })
    col = list(t.columns).index
    shade = {}
    for i, r in enumerate(after.itertuples()):
        shade[(i, col("ADF statistic"))] = r.adf_stat < r.adf_crit_sim
        shade[(i, col("KPSS statistic"))] = r.kpss_stat < r.kpss_crit_sim
        shade[(i, col("KPSS statistic (bw 168)"))] = r.kpss_stat_168 < r.kpss_crit_168_sim
    _png_table(t, path, f"Stationarity after the calendar dummies ({' + '.join(calendar)})", [
        _verdict(after),
        f"Residuals of an OLS of each variable on a constant + {after['n_dummies'].iloc[0]} dummies "
        f"({', '.join(calendar)}); the data are unchanged. Each statistic is compared with its SIMULATED 5 % "
        f"critical value, not the standard one (which does not apply after dummies).",
        f"KPSS: AR(p) by BIC (max {AR_MAX}) on the residuals, innovations resampled in {BLOCK_HOURS}-h blocks, "
        f"N = {kpss_draws}, the same dummies projected out; automatic bandwidth and 168 ({BW_SENSITIVE} when "
        f"they disagree). ADF: random walks with {BLOCK_HOURS}-h block steps, the same dummies, lag fixed at the "
        f"data's lag, N = {adf_draws}. Seed {seed}. Green = the test points to stationarity."],
        decisions={(i, col("Decision")): d for i, d in enumerate(after["decision"])}, shade=shade)


def table_robustness(grid: pd.DataFrame, alpha: float, path, after: bool = False):
    """The decision per check: of the levels tests, or (after=True) of the tests after the dummies."""
    t = grid.rename(columns={"zone": "Area", "series": "Variable"})
    t["Variable"] = t["Variable"].map(label)
    checks = [c for c in grid.columns if c not in ("zone", "series")]
    decisions = {}
    for j, c in enumerate(checks, start=2):
        decisions.update({(i, j): d for i, d in enumerate(grid[c])})
        t[c] = grid[c].map(DECISION_CODES)
    notes = (["KPSS bw = fixed KPSS bandwidth against its own simulated critical value (ADF as after the dummies). "
              "alpha = the simulated p-values at another significance level. No windows: each would need its own "
              "simulations."] if after else
             [f"Window = the data from that year to the last year (only when the data spans several years). KPSS bw = "
              f"fixed KPSS bandwidth (ADF as in the levels test). alpha = the levels p-values at another significance "
              f"level (levels alpha = {alpha})."])
    _png_table(t, path, "Stationarity robustness after the calendar dummies: decision per check" if after
               else "Stationarity robustness: decision per check (same rule as the levels test)", [
        "S = stationary, U = unit root, C = conflict (both tests reject), I = inconclusive (neither rejects), "
        "B = bandwidth-sensitive.", *notes], decisions=decisions, font=9)


def _numbers(table: pd.DataFrame) -> pd.DataFrame:
    out = table.copy()
    for c in out.columns:
        if out[c].dtype.kind == "f":
            out[c] = out[c].map(lambda v: "" if pd.isna(v) else f"{v:.4g}")
    return out


def write_report(levels, after, grid, grid_after, calendar, alpha, kpss_draws, adf_draws, seed, path):
    text = [
        "# Stationarity tests — endogenous variables",
        "",
        f"Per bidding zone; alpha = {alpha}. ADF (H0 unit root; constant; AIC lag up to {ADF_MAX_LAG}, searched "
        f"again up to {ADF_MAX_LAG_LONG} where {ADF_MAX_LAG} was selected) and KPSS (H0 stationary; constant; "
        "automatic bandwidth; exact asymptotic p-value) decide; Phillips-Perron (H0 unit root) is supporting only. "
        "STATIONARY: ADF rejects, KPSS does not. UNIT ROOT: the reverse. CONFLICT: both reject. INCONCLUSIVE: "
        "neither rejects. Nothing is differenced or transformed.",
        "",
        "## 1. Levels (the series as they are)",
        "",
        md_table(_numbers(levels.drop(columns=["adf_crit_5", "kpss_crit"]))),
        "",
        f"**{_verdict(levels)}** {_missing_note(levels)}",
        "",
    ]
    if after is not None:
        text += [
            f"## 2. After the calendar dummies ({', '.join(calendar)})",
            "",
            f"Residuals of an OLS on a constant + the dummies; statistics compared with simulated 5 % critical "
            f"values (KPSS: AR(p) by BIC max {AR_MAX}, {BLOCK_HOURS}-h block bootstrap, N = {kpss_draws}; ADF: block "
            f"random walks, lag fixed at the data's lag, N = {adf_draws}; seed {seed}, one stream per zone and "
            f"variable). {BW_SENSITIVE}: the KPSS verdict differs between the automatic bandwidth and 168.",
            "",
            md_table(_numbers(after)),
            "",
            f"**{_verdict(after)}**",
            "",
        ]
    codes = lambda g: g.assign(**{c: g[c].map(DECISION_CODES) for c in g.columns if c not in ("zone", "series")})  # noqa: E731
    text += ["## 3. Robustness (levels)", "", md_table(codes(grid)), "",
             "S stationary, U unit root, C conflict, I inconclusive.", ""]
    if grid_after is not None:
        text += ["## 4. Robustness (after the calendar dummies)", "",
                 "The same checks on the tests after the dummies: KPSS with each fixed bandwidth against its own "
                 "simulated critical value (ADF unchanged), and the simulated p-values at the other significance "
                 "levels. No windows (each would need its own simulations).", "", md_table(codes(grid_after)), "",
                 "S stationary, U unit root, C conflict, I inconclusive, B bandwidth-sensitive.", ""]
    path.write_text("\n".join(text), encoding="utf-8")
    print(f"  wrote {path.name}")


def run(df: pd.DataFrame, spec: Spec, plot_dir, alpha: float = 0.05, kpss_draws: int = 5000,
        adf_draws: int = 1000, seed: int = 2025):
    out = plot_dir / "stationarity_tests"
    out.mkdir(parents=True, exist_ok=True)
    endogenous = list(spec.endogenous)
    levels = run_levels(df, endogenous, alpha)
    table_levels(levels, alpha, out / "stationarity_levels.png")
    levels.to_csv(out / "levels.csv", index=False)
    grid = run_robustness(df, endogenous, levels, alpha)
    table_robustness(grid, alpha, out / "stationarity_robustness.png")
    grid.to_csv(out / "robustness.csv", index=False)
    after = grid_after = None
    if spec.calendar:
        after = run_after_dummies(df, endogenous, spec.calendar, alpha, kpss_draws, adf_draws, seed)
        table_after_dummies(after, spec.calendar, kpss_draws, adf_draws, seed, out / "stationarity_after_dummies.png")
        after.to_csv(out / "after_dummies.csv", index=False)
        grid_after = run_robustness_after(after)
        table_robustness(grid_after, alpha, out / "stationarity_robustness_after_dummies.png", after=True)
        grid_after.to_csv(out / "robustness_after_dummies.csv", index=False)
    else:
        print("  no calendar dummies among the exogenous variables — tests after dummies skipped")
    write_report(levels, after, grid, grid_after, spec.calendar, alpha, kpss_draws, adf_draws, seed,
                 out / "STATIONARITY.md")
    print(f"  Levels: {_verdict(levels)}")
    if after is not None:
        print(f"  After the dummies: {_verdict(after)}")
