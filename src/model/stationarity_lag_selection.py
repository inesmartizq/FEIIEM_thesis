"""
stationarity_lag_selection.py

The pre-modelling tests of the methods chapter — NOT the VAR / VARX itself
(nothing here estimates or interprets a VAR): stationarity tests of the
endogenous series and the lag selection for a later VAR. Which columns are
endogenous (the spreads x_* and the forecast errors) and exogenous (wind
ramp, cross-border flows, fe_* calendar identifiers) comes from the
dataframe's model spec (src/model_specs.py).

STEPS (the "var_tests" step of main.py; the name is kept for the output folder)
    1. Stationarity of the endogenous series, per zone (10 series): ADF (H0:
       unit root; constant, lags by AIC up to 48 — rerun up to 168 when 48 is
       selected), KPSS (H0: stationary; constant, automatic bandwidth) and
       Phillips-Perron (H0: unit root; reported, not used in the decision).
       Decision at alpha:
           ADF rejects,         KPSS does not reject -> STATIONARY
           ADF does not reject, KPSS rejects         -> UNIT ROOT
           ADF rejects,         KPSS rejects         -> CONFLICT
           ADF does not reject, KPSS does not reject -> INCONCLUSIVE
       Nothing is differenced or transformed: the checks only report.
       Robustness checks, the calendar decomposition, the calendar check
       (simulated critical values after the dummies) and the diagnostics
       further down.
    2. Exogenous block, per zone: shape and rank of [constant, exogenous,
       calendar dummies]; a perfectly collinear flow column is dropped.
    3. Lag selection: AIC(p) = ln|S(p)| + 2 p K^2 / T and BIC(p) =
       ln|S(p)| + p K^2 ln T / T for contiguous orders 1..p (candidate_lags)
       and for the literature structure (lags 1-24 + 48), all on the SAME
       sample so the criteria are comparable. S(p) comes from an equation-by-
       equation OLS fit used ONLY for the criteria; no model is estimated or
       reported. "p" = number of lag matrices (25 for the literature structure).

NOTES
    - Lag selection uses an hour only when y, all its lags and x are observed
      (listwise); the number of hours is reported per structure.
    - Unit-root tests need a gap-free series; the few missing hours are
      dropped before testing (the series is joined across them), never
      interpolated.
    - KPSS p-values: statsmodels interpolates a table and truncates at
      0.01 / 0.10; here the exact asymptotic p-value of the same statistic
      is reported and used (kpss_asymptotic_pvalue), so nothing is truncated.

OUTPUT (plots/<name>/var_tests/)
    stationarity_before_dummies.png  main table on the series as they are: one row per series, one
                                 column per test (test statistic and p-value), decision, verdict
    stationarity_after_dummies.png   the same after removing the calendar controls
    stationarity_robustness.png  one row per series, one column per check, codes S / U / C / I
    stationarity_plots/{zone}_{series}.png   series + 30-day rolling mean, 30-day rolling std, for
                                 every tested series (baseline decision in the title)
    lag_selection.png
    VAR_TESTS.md                 the tables (stationarity, lag selection) and the marked sections
    No CSV or LaTeX files are written.

TESTS
    Every test of the project is at the end of this file (decision rule,
    unit-root tests on simulated data, KPSS p-values, robustness windows,
    calendar removal, the lag-selection OLS fit against statsmodels, the
    cross-border flow columns). Run: python src/model/stationarity_lag_selection.py --test [--slow]
"""

import math
import re
import sys
import textwrap
import warnings
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

_here = Path(__file__).resolve()
for _parent in [_here.parent, *_here.parents]:
    if (_parent / "analysis_utils.py").exists():
        if str(_parent) not in sys.path:
            sys.path.insert(0, str(_parent))
        break

from analysis_utils import DATAFRAMES_DIR, PLOTS_DIR

FULL_LAGS = list(range(1, 25)) + [48]          # Spodniak et al. 2019: each hour of the previous day + lag 48
CANDIDATE_LAGS = [1, 2, 3, 4, 6, 12, 24, 48]   # contiguous orders compared by AIC / BIC


# ---------------------------------------------------------------------------
# STATIONARITY
# ---------------------------------------------------------------------------
STATIONARY, UNIT_ROOT, CONFLICT, INCONCLUSIVE = "STATIONARY", "UNIT ROOT", "CONFLICT", "INCONCLUSIVE"
DECISION_COLORS = {STATIONARY: "#4CAF50", CONFLICT: "#FF9800", UNIT_ROOT: "#E53935", INCONCLUSIVE: "#9E9E9E"}
DECISION_CODES = {STATIONARY: "S", UNIT_ROOT: "U", CONFLICT: "C", INCONCLUSIVE: "I"}
DECISION_ORDER = [STATIONARY, CONFLICT, UNIT_ROOT, INCONCLUSIVE]
ADF_MAX_LAG, ADF_MAX_LAG_LONG = 48, 168  # ADF is rerun with the long limit when the short one is selected
KPSS_BANDWIDTHS = [48, 168]              # robustness: fixed KPSS bandwidths next to nlags="auto"
ROBUSTNESS_ALPHAS = [0.01, 0.10]
ROLLING_WINDOW = "30D"
KPSS_CRITICAL_5PCT = 0.463  # KPSS level-stationarity 5 % critical value (Kwiatkowski et al. 1992)


def _fmt_p_exact(p: float) -> str:
    """A p-value at full precision: 4 decimals, scientific below 0.0001."""
    if p == 0:
        return "< 1e-300"
    return f"{p:.4f}" if p >= 1e-4 else f"{p:.2e}"


def _fmt_p(p: float) -> str:
    return "< 0.0001" if p < 1e-4 else f"{p:.4f}"


def decide(adf_p: float, kpss_p: float, alpha: float = 0.05) -> str:
    """Stationarity decision from the ADF and KPSS p-values. A test rejects
    when p < alpha (p exactly at alpha does not reject)."""
    adf_rejects = adf_p < alpha       # rejects the unit root
    kpss_rejects = kpss_p < alpha     # rejects stationarity
    if adf_rejects and not kpss_rejects:
        return STATIONARY
    if not adf_rejects and kpss_rejects:
        return UNIT_ROOT
    if adf_rejects and kpss_rejects:
        return CONFLICT
    return INCONCLUSIVE


def kpss_asymptotic_pvalue(stat: float) -> float:
    """Exact asymptotic p-value of the KPSS level-stationarity statistic.

    Under H0 the statistic converges to the integral of a squared Brownian
    bridge, i.e. the Cramer-von Mises omega^2 distribution — the distribution
    the published KPSS critical values (0.347 / 0.463 / 0.739) come from.
    statsmodels only interpolates a table and truncates p at 0.01 / 0.10;
    this gives the value itself:
      - stat < 0.2: Anderson & Darling (1952) series for the CDF;
      - stat >= 0.2: Smirnov's integral formula for the upper tail, which
        stays accurate for tiny p (computing 1 - CDF loses all precision
        below ~1e-11). Endpoint singularities are removed with the
        substitution t = a + (b - a)(1 - cos phi) / 2.
    Checked against scipy's reference implementation (identical to 7
    digits for stat <= 3) and the KPSS critical values.
    """
    from scipy.integrate import quad
    from scipy.special import binom, kv

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
            s_ = -math.sin(t)
            if s_ <= 0:
                return 0.0
            return 2 * math.sqrt(t / s_) * math.exp(-x * t * t / 2) / t * (b - a) / 2 * math.sin(phi)

        v, _ = quad(integrand, 0, math.pi, limit=200, epsabs=0, epsrel=1e-11)
        total += (-1) ** (k + 1) * v
        if v == 0 or abs(v) <= 1e-15 * abs(total):
            break
    return float(min(1.0, max(0.0, total / math.pi)))


def _kpss_test(x: np.ndarray, nlags="auto") -> dict:
    """KPSS with a constant (statsmodels); the p-value is the exact
    asymptotic one of the statistic (statsmodels' truncated p is not used)."""
    from statsmodels.tools.sm_exceptions import InterpolationWarning
    from statsmodels.tsa.stattools import kpss

    if nlags != "auto" and not nlags < len(x):
        raise ValueError(f"KPSS nlags={nlags} must be smaller than the number of observations ({len(x)})")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", InterpolationWarning)
        stat, _, lags, _ = kpss(x, regression="c", nlags=nlags, result_object=False)
    return {"kpss_stat": float(stat), "kpss_p": kpss_asymptotic_pvalue(stat), "kpss_lags": int(lags)}


def _adf_aic_lag(x: np.ndarray, max_lag: int, ic: str = "aic") -> int:
    """The ADF lag order statsmodels' adfuller(autolag='AIC', regression='c')
    selects, computed exactly but fast. statsmodels fits max_lag + 1 nested
    OLS regressions [const, x_(t-1), dx_(t-1), ..., dx_(t-k)] of dx_t on the
    same sample (the one left after max_lag lags) and takes the smallest AIC
    (first one on ties). The regressions are nested, so every residual sum of
    squares comes from ONE QR decomposition: RSS_k = y'y - sum of the first
    k + 2 squared elements of Q'y. AIC differences between the orders are
    n ln(RSS/n) + 2 (number of regressors), the same ranking statsmodels
    uses (ic='bic': penalty ln(n) per regressor instead of 2, as statsmodels'
    autolag='BIC'). ~30x faster at max_lag = 168 on 35,000 hours."""
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
    """ADF with a constant, lags by AIC up to max_lag; if AIC picks max_lag
    itself, the search is repeated up to max_lag_long. The final regression
    is statsmodels' adfuller with the selected lag (identical to its own
    autolag result; see _adf_aic_lag)."""
    from statsmodels.tsa.stattools import adfuller

    lags, used = _adf_aic_lag(x, max_lag), max_lag
    if max_lag_long and lags == max_lag:
        lags, used = _adf_aic_lag(x, max_lag_long), max_lag_long
    stat, p, _, _, crit = adfuller(x, maxlag=lags, regression="c", autolag=None, result_object=False)
    return {"adf_stat": float(stat), "adf_p": float(p), "adf_lags": int(lags), "adf_max_lag": used,
            "adf_crit_5": float(crit["5%"])}


def stationarity_tests(series: pd.Series, alpha: float = 0.05, max_lag: int = ADF_MAX_LAG,
                       max_lag_long: int | None = ADF_MAX_LAG_LONG, kpss_nlags="auto") -> dict:
    """ADF, KPSS and Phillips-Perron on the series with missing hours dropped
    (counted, never interpolated), plus the decision label (ADF + KPSS)."""
    from arch.unitroot import PhillipsPerron

    x = series.dropna().to_numpy(dtype=float)
    adf = _adf_test(x, max_lag, max_lag_long)
    k = _kpss_test(x, kpss_nlags)
    pp = PhillipsPerron(x, trend="c")
    return {"n_obs": len(x), "n_dropped": int(series.isna().sum()), **adf, **k,
            "pp_stat": float(pp.stat), "pp_p": float(pp.pvalue),
            "decision": decide(adf["adf_p"], k["kpss_p"], alpha)}


def load_data(name: str, start: str | None = None, end: str | None = None) -> pd.DataFrame:
    """The dataframe data/dataframes/<name>.csv, optionally cut to [start, end]."""
    df = pd.read_csv(DATAFRAMES_DIR / f"{name}.csv")
    df["datetime_utc"] = pd.to_datetime(df["datetime_utc"], utc=True)
    if start:
        df = df[df["datetime_utc"] >= pd.Timestamp(start, tz="UTC")]
    if end:
        df = df[df["datetime_utc"] < pd.Timestamp(end, tz="UTC") + pd.Timedelta(days=1)]
    return df


def _zone_frame(df: pd.DataFrame, zone: str) -> pd.DataFrame:
    return df[df["bidding_zone"] == zone].sort_values("datetime_utc").reset_index(drop=True)


def run_tests(df: pd.DataFrame, series_cols: list, zones: list, alpha: float = 0.05,
              controls: list | None = None) -> pd.DataFrame:
    """Every series on the full sample, one row per (zone, series): in levels
    (baseline), or — with `controls` — the residuals after those calendar
    dummies (computed on copies)."""
    rows = []
    for zone in zones:
        dz = _zone_frame(df, zone)
        for col in series_cols:
            print(f"  [{zone}] stationarity: {col}" + (" (after the calendar dummies)" if controls else ""))
            s = residualise(dz[col], [dz[c] for c in controls])[0] if controls else dz[col]
            rows.append({"zone": zone, "series": col, **stationarity_tests(s, alpha)})
    return pd.DataFrame(rows)


def select_window(dz: pd.DataFrame, first_year: int, last_year: int) -> pd.DataFrame:
    """Rows whose UTC delivery year lies in [first_year, last_year]."""
    years = dz["datetime_utc"].dt.year
    return dz[(years >= first_year) & (years <= last_year)]


def window_label(first_year: int, last_year: int) -> str:
    return f"{first_year}-{str(last_year)[2:]}" if first_year < last_year else f"{last_year}"


def run_windows(df: pd.DataFrame, series_cols: list, zones: list, alpha: float = 0.05,
                first_years: list | None = None) -> pd.DataFrame:
    """The tests on expanding windows that all end with the latest year:
    last year only, last two years, ... down to the first year of the data
    (= the full sample, i.e. the baseline)."""
    first, last = int(df["datetime_utc"].dt.year.min()), int(df["datetime_utc"].dt.year.max())
    first_years = first_years or list(range(last, first - 1, -1))
    rows = []
    for fy in first_years:
        label = window_label(fy, last)
        for zone in zones:
            dz = select_window(_zone_frame(df, zone), fy, last)
            for col in series_cols:
                print(f"    window {label} {zone} {col}")
                rows.append({"check": label, "first_year": fy, "zone": zone, "series": col,
                             **stationarity_tests(dz[col].reset_index(drop=True), alpha)})
    return pd.DataFrame(rows)


def run_bandwidths(df: pd.DataFrame, series_cols: list, zones: list, baseline: pd.DataFrame,
                   alpha: float = 0.05, bandwidths: list = KPSS_BANDWIDTHS) -> pd.DataFrame:
    """KPSS with fixed bandwidths on the full sample; ADF as in the baseline."""
    base = baseline.set_index(["zone", "series"])
    rows = []
    for zone in zones:
        dz = _zone_frame(df, zone)
        for col in series_cols:
            x = dz[col].dropna().to_numpy(dtype=float)
            adf_p = base.loc[(zone, col), "adf_p"]
            for bw in bandwidths:
                print(f"    KPSS bandwidth {bw} {zone} {col}")
                k = _kpss_test(x, bw)
                rows.append({"check": f"KPSS bw {bw}", "zone": zone, "series": col, "adf_p": adf_p, **k,
                             "decision": decide(adf_p, k["kpss_p"], alpha)})
    return pd.DataFrame(rows)


def residualise(y: pd.Series, categories: list) -> tuple[pd.Series, float, int]:
    """OLS of y on a constant and one dummy per category of each series in
    `categories` (first category present dropped, so no perfect collinearity
    with the constant). Fitted only on the hours where y and every category
    are observed — the same hours that are then tested; the residuals are
    placed back on y's index (other hours NaN). Works on a copy: y itself is
    never changed. Returns (residuals, R-squared, number of dummy columns)."""
    ok = y.notna()
    for c in categories:
        ok &= c.notna()
    parts = [pd.Series(1.0, index=y.index[ok], name="const")]
    for i, c in enumerate(categories):
        parts.append(pd.get_dummies(c[ok].astype("Int64"), prefix=f"d{i}", drop_first=True, dtype=float))
    X = pd.concat(parts, axis=1).to_numpy(float)
    v = y[ok].to_numpy(float)
    beta = np.linalg.lstsq(X, v, rcond=None)[0]
    e = v - X @ beta
    resid = pd.Series(np.nan, index=y.index)
    resid[ok] = e
    r2 = 1 - (e @ e) / ((v - v.mean()) @ (v - v.mean())) if len(v) else np.nan
    return resid, float(r2), X.shape[1] - 1


def remove_calendar(dz: pd.DataFrame, col: str, fe_cols: list) -> pd.Series:
    """Residuals of an OLS of the series on a constant and the hour-of-day and
    week-of-sample dummies (the VAR's fixed effects; first category of each
    dropped). Diagnostic only: computed on a copy, never written back."""
    return residualise(dz[col], [dz[c] for c in fe_cols])[0]


def week_of_year(dz: pd.DataFrame) -> pd.Series:
    """ISO week of the year (1-52 in 2022-2025, Monday-Sunday weeks,
    Copenhagen local time): repeats across years, unlike week of sample."""
    local = dz["datetime_utc"].dt.tz_convert("Europe/Copenhagen")
    return local.dt.isocalendar().week.astype(float)


# Calendar controls, from coarse to fine (thesis: "the controls
# are chosen as coarse as possible: monthly means first, weekly means only if
# these are not enough"). (label, fixed-effect columns, decomposition case).
CONTROL_SETS = [
    ("hour + month of sample", ["fe_hour", "fe_month_of_sample"], "5 Hour + month of sample"),
    ("hour + week of sample", ["fe_hour", "fe_week_of_sample"], "7 Hour + week of sample"),
]


def calendar_decomposition(df: pd.DataFrame, series_cols: list, zones: list, alpha: float = 0.05,
                           bandwidths: tuple = ("auto", 168)) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Diagnostic for the ADF-KPSS conflicts: the tests on the residuals of the
    series on each dummy set, from coarse to fine (1 raw, 2 hour, 3 week of
    year, 4 month of sample, 5 hour + month of sample, 6 week of sample,
    7 hour + week of sample) and on the raw series without the first year (8).
    Same settings as the baseline (ADF constant / AIC / maxlag 48 -> 168; KPSS
    with each bandwidth). Everything on copies. Returns (decisions, R2)."""
    first, last = int(df["datetime_utc"].dt.year.min()), int(df["datetime_utc"].dt.year.max())
    rows, fit_rows = [], []
    for zone in zones:
        dz = _zone_frame(df, zone)
        sets = {"1 Raw": [], "2 Hour": [dz["fe_hour"]], "3 Week of year": [week_of_year(dz)],
                "4 Month of sample": [dz["fe_month_of_sample"]],
                "5 Hour + month of sample": [dz["fe_hour"], dz["fe_month_of_sample"]],
                "6 Week of sample": [dz["fe_week_of_sample"]],
                "7 Hour + week of sample": [dz["fe_hour"], dz["fe_week_of_sample"]]}
        for col in series_cols:
            fit = {"zone": zone, "series": col}
            cases = {}
            for case, cats in sets.items():
                resid, r2, k = residualise(dz[col], cats)
                cases[case] = resid
                if cats:
                    fit[f"{case}|k"], fit[f"{case}|R2"] = k, r2
            if first < last:
                cases[f"8 Raw {first + 1}-{str(last)[2:]}"] = select_window(dz, first + 1, last)[col]
            fit_rows.append(fit)
            for case, s in cases.items():
                print(f"    calendar decomposition {zone} {col}: {case}")
                x = s.dropna().to_numpy(dtype=float)
                adf = _adf_test(x)
                row = {"zone": zone, "series": col, "case": case, "n_obs": len(x), **adf}
                for bw in bandwidths:
                    k = _kpss_test(x, bw)
                    row[f"kpss_stat_{bw}"], row[f"kpss_p_{bw}"] = k["kpss_stat"], k["kpss_p"]
                    row[f"decision_{bw}"] = decide(adf["adf_p"], k["kpss_p"], alpha)
                rows.append(row)
    return pd.DataFrame(rows), pd.DataFrame(fit_rows)


def select_calendar_controls(dec: pd.DataFrame, control_sets: list = CONTROL_SETS) -> dict:
    """The coarsest control set after whose removal EVERY tested series is
    STATIONARY (KPSS automatic bandwidth, as in the baseline). If none
    suffices, the finest set is used and flagged. Returns {label, columns,
    case, sufficient, passed, total, per_set: {label: (passed, total)}}."""
    per_set = {}
    for label, cols, case in control_sets:
        d = dec[dec["case"] == case]
        per_set[label] = (int((d["decision_auto"] == STATIONARY).sum()), len(d))
    for label, cols, case in control_sets:
        passed, total = per_set[label]
        if total and passed == total:
            return {"label": label, "columns": cols, "case": case, "sufficient": True,
                    "passed": passed, "total": total, "per_set": per_set}
    label, cols, case = control_sets[-1]
    return {"label": label, "columns": cols, "case": case, "sufficient": False,
            "passed": per_set[label][0], "total": per_set[label][1], "per_set": per_set}


def controls_sentence(choice: dict) -> str:
    """The controls used, without verdicts: after dummies the standard critical
    values do not apply, so the verdicts live in 'Final verdicts' (simulated
    critical values), not here."""
    return (f"Calendar controls: {choice['label']} (fixed in the stationarity step). The tests after "
            f"these controls use simulated critical values; see 'Calendar check' and 'Final verdicts'.")


def make_decomposition_tables(dec: pd.DataFrame, fits: pd.DataFrame, out_dir: Path, choice: dict,
                              bandwidths: tuple = ("auto", 168)):
    """stationarity_calendar_decomposition.png (verdict per case and KPSS
    bandwidth) and stationarity_calendar_fit.png (dummy columns and R2)."""
    keys = list(dict.fromkeys(zip(dec["zone"], dec["series"])))
    cases = list(dict.fromkeys(dec["case"]))
    by = dec.set_index(["zone", "series", "case"])
    table = pd.DataFrame({"Area": [z for z, _ in keys], "Series": [s for _, s in keys]})
    colors = {}
    for case in cases:
        for bw in bandwidths:
            name = f"{case}\nKPSS {bw}"
            decisions = [by.loc[(z, s, case), f"decision_{bw}"] for z, s in keys]
            j = len(table.columns)
            table[name] = [DECISION_CODES[d] for d in decisions]
            colors.update({(i, j): d for i, d in enumerate(decisions)})
    _png_table(table, colors, out_dir / "stationarity_calendar_decomposition.png",
               "Why do ADF and KPSS conflict? Tests after removing each set of calendar dummies (coarse to fine)",
               ["S = stationary, U = unit root, C = conflict, I = inconclusive. Cases 2-7 = residuals of OLS on a "
                "constant + the dummies (copies; the data are unchanged).",
                "Monthly means (4-5) are tried before weekly means (6-7): weekly dummies give each week its own mean "
                "and absorb almost any slow movement, so a pass with them is partly mechanical.",
                "If '3 Week of year' does not pass but the sample-specific dummies do, the slow movement does not "
                "repeat across years. If the last case (first year left out) passes, the conflict comes from that "
                "year.",
                controls_sentence(choice)],
               font=8.5, header_rows=2)
    fit_cases = [c for c in cases if c[0] in "234567"]
    fit = pd.DataFrame({"Area": fits["zone"], "Series": fits["series"]})
    for case in fit_cases:
        fit[f"{case}\ndummies"] = fits[f"{case}|k"].astype(int)
        fit[f"{case}\nR²"] = fits[f"{case}|R2"].map("{:.3f}".format)
    _png_table(fit, {}, out_dir / "stationarity_calendar_fit.png",
               "Calendar dummy sets: number of dummy columns (first category dropped, plus a constant) and R²",
               ["R² = share of the series' variance explained by the dummy set (OLS with a constant)."],
               font=8, header_rows=2)


def adf_lag_check(df: pd.DataFrame, series: list, zones: list, controls: list, out_path: Path,
                  alpha: float = 0.05,
                  configs: tuple = (("AIC", 168), ("AIC", 336), ("BIC", 336))) -> pd.DataFrame:
    """ADF on the residuals after the calendar controls, with each lag rule
    (information criterion, maximum lag). One PNG table: statistic, selected
    lag, p-value, verdict."""
    from statsmodels.tsa.stattools import adfuller

    rows = []
    for zone in zones:
        dz = _zone_frame(df, zone)
        for col in series:
            x = residualise(dz[col], [dz[c] for c in controls])[0].dropna().to_numpy(dtype=float)
            for ic, max_lag in configs:
                print(f"    ADF lag check {zone} {col} {ic} max {max_lag}")
                lag = _adf_aic_lag(x, max_lag, ic.lower())
                stat, p, _, _, crit = adfuller(x, maxlag=lag, regression="c", autolag=None, result_object=False)
                rows.append({"Area": zone, "Series": col, "Lag rule": f"{ic}, max {max_lag}",
                             "ADF stat": round(float(stat), 3), "Selected lag": lag, "p-value": _fmt_p(p),
                             "Verdict": "rejects unit root" if p < alpha else "does not reject",
                             "_ok": p < alpha, "_crit": crit["5%"]})
    out = pd.DataFrame(rows)
    shade = {(i, 6): ok for i, ok in enumerate(out["_ok"])}
    _png_table(out.drop(columns=["_ok", "_crit"]), {}, out_path,
               "ADF on the residuals after " + " + ".join(controls) + " (demand forecast errors)",
               [f"Constant in the test regression; 5 % critical value {out['_crit'].min():.2f}. Green = rejects the "
                f"unit root at {alpha:.0%}, light red = does not."], shade=shade, font=9)
    return out


def adf_lag_check_main(name: str):
    """CLI: python src/model/stationarity_lag_selection.py --adf-lag-check <dataframe>"""
    df = load_data(name)
    controls = CONTROL_SETS[0][1]  # hour + month of sample
    out = adf_lag_check(df, ["c_load_err"], sorted(df["bidding_zone"].unique()), controls,
                        PLOTS_DIR / name / "var_tests" / "stationarity_adf_lag_check.png")
    print(out.drop(columns=["_ok", "_crit"]).to_string(index=False))


def adf_bound_check(df: pd.DataFrame, stat_df: pd.DataFrame, max_lag: int = 2 * ADF_MAX_LAG_LONG,
                    alpha: float = 0.05) -> pd.DataFrame:
    """For the series whose AIC lag is the upper bound (168): ADF again with a
    larger bound (336) — reported next to the main table; the baseline rule is
    not changed."""
    from statsmodels.tsa.stattools import adfuller

    rows = []
    for r in stat_df[stat_df["adf_lags"] == stat_df["adf_max_lag"]].itertuples(index=False):
        x = _zone_frame(df, r.zone)[r.series].dropna().to_numpy(dtype=float)
        print(f"    ADF bound check {r.zone} {r.series} (max {max_lag})")
        lag = _adf_aic_lag(x, max_lag)
        stat, p, *_ = adfuller(x, maxlag=lag, regression="c", autolag=None, result_object=False)
        rows.append({"zone": r.zone, "series": r.series, "max_lag": max_lag, "adf_lags": lag,
                     "adf_stat": float(stat), "adf_p": float(p), "rejects": p < alpha,
                     "baseline_rejects": r.adf_p < alpha})
    return pd.DataFrame(rows)


def bound_check_sentence(bound: pd.DataFrame) -> str:
    if bound.empty:
        return "ADF: no series at the upper lag bound."
    parts = [f"{r.series} {r.zone} lag {r.adf_lags}, stat {r.adf_stat:.2f}" for r in bound.itertuples()]
    same = bool((bound["rejects"] == bound["baseline_rejects"]).all())
    return (f"ADF bound check for the series at the 168-lag limit, rerun with max {int(bound['max_lag'].iloc[0])}: "
            + "; ".join(parts) + f" — {'same ADF verdict' if same else 'ADF VERDICT CHANGES'}.")


def run_alphas(baseline: pd.DataFrame, alphas: list = ROBUSTNESS_ALPHAS) -> pd.DataFrame:
    """The baseline p-values classified at other significance levels."""
    rows = []
    for a in alphas:
        for r in baseline.itertuples(index=False):
            rows.append({"check": f"alpha {a:.0%}", "zone": r.zone, "series": r.series,
                         "decision": decide(r.adf_p, r.kpss_p, a)})
    return pd.DataFrame(rows)


def _check_reproduces_baseline(window_df: pd.DataFrame, baseline: pd.DataFrame, first_year: int):
    """The full-sample window must reproduce the baseline exactly (same n, statistics, decision)."""
    full = window_df[window_df["first_year"] == first_year].set_index(["zone", "series"])
    base = baseline.set_index(["zone", "series"])
    cols = ["n_obs", "adf_stat", "adf_lags", "kpss_stat", "decision"]
    diff = (full.loc[base.index, cols] != base[cols]).any(axis=1)
    if diff.any():
        raise RuntimeError(f"The full-sample window does not reproduce the baseline for {list(base.index[diff])} "
                           f"— stopping.")
    print(f"  check passed: the window {window_label(first_year, int(window_df['first_year'].max()))} "
          f"reproduces the baseline exactly")


def robustness_grid(baseline: pd.DataFrame, checks: list) -> pd.DataFrame:
    """One row per (zone, series), one column per check (Baseline first), decision labels."""
    grid = baseline[["zone", "series"]].copy()
    grid["Baseline"] = baseline["decision"].to_numpy()
    for d in checks:
        for check, g in d.groupby("check", sort=False):
            grid[check] = g.set_index(["zone", "series"]).loc[list(zip(grid.zone, grid.series)), "decision"].to_numpy()
    return grid


def stationarity_verdict(stat_df: pd.DataFrame) -> str:
    flagged = [f"{r.series} ({r.zone}): {r.decision}" for r in stat_df.itertuples() if r.decision != STATIONARY]
    return "VAR can be applied in levels" if not flagged else "Review needed: " + "; ".join(flagged)


def _color_decision_cell(cell, label: str):
    cell.set_facecolor(DECISION_COLORS[label])
    cell.set_text_props(weight="bold", color="white" if label in (STATIONARY, UNIT_ROOT) else "black")


def _png_table(table_df: pd.DataFrame, colors: dict, out_path: Path, title: str, notes: list,
               red: dict | None = None, font: float = 8.5, header_rows: int = 1, shade: dict | None = None):
    """Table image with a tight bounding box. colors: {(row, col): decision}
    for colour-coded cells; red: {(row, col): True} for red bold text;
    shade: {(row, col): True / False} for a light green (passes) / light red
    (fails) background; header_rows: lines of text in the header cells."""
    fig, ax = plt.subplots(figsize=(1.3 + 1.1 * len(table_df.columns), 0.3 * len(table_df) + 1.0))
    ax.axis("off")
    table = ax.table(cellText=table_df.astype(str).values, colLabels=list(table_df.columns),
                     cellLoc="center", loc="center")
    table.auto_set_font_size(False)
    table.set_fontsize(font)
    table.scale(1, 1.45)
    table.auto_set_column_width(list(range(len(table_df.columns))))
    for (r, c), cell in table.get_celld().items():
        if r == 0:
            cell.set_text_props(weight="bold")
            cell.set_facecolor("#E0E0E0")
            cell.set_height(cell.get_height() * header_rows)
        elif (r - 1, c) in colors:
            _color_decision_cell(cell, colors[(r - 1, c)])
        else:
            if shade and (r - 1, c) in shade:
                cell.set_facecolor("#D4EDDA" if shade[(r - 1, c)] else "#F8D7DA")
            if red and red.get((r - 1, c)):
                cell.get_text().set_color("#C62828")
                cell.get_text().set_fontweight("bold")
    ax.set_title(title, fontsize=11, pad=14)
    ax.text(0.5, -0.02, "\n".join(notes), transform=ax.transAxes, ha="center", va="top", fontsize=8.5)
    fig.savefig(out_path, dpi=140, bbox_inches="tight", pad_inches=0.25)
    plt.close(fig)


def _stat_with_p(stat: float, p: float, exact: bool = False) -> str:
    """'-8.989 (p < 0.0001)' — the test statistic with its p-value (exact:
    full precision, used for KPSS; otherwise below 0.0001 is '< 0.0001')."""
    ps = _fmt_p_exact(p) if exact else _fmt_p(p)
    return f"{stat:.3f} (p {ps})" if ps.startswith("<") else f"{stat:.3f} (p = {ps})"


def _main_table(stat_df: pd.DataFrame, alpha: float, out_path: Path, title: str, notes: list,
                verdict: str | None = None):
    """One row per series; one column per test, each cell = test statistic
    (p-value), shaded light green when that test points to stationarity and
    light red when it does not; the decision colour-coded."""
    table = pd.DataFrame({
        "Area": stat_df["zone"], "Series": stat_df["series"],
        "ADF test statistic (p-value)": [_stat_with_p(s, p) for s, p in zip(stat_df["adf_stat"], stat_df["adf_p"])],
        "ADF lags": [f"{l} (max {m})" if m != ADF_MAX_LAG else f"{l}"
                     for l, m in zip(stat_df["adf_lags"], stat_df["adf_max_lag"])],
        "Phillips-Perron test statistic (p-value)": [_stat_with_p(s, p)
                                                     for s, p in zip(stat_df["pp_stat"], stat_df["pp_p"])],
        "KPSS test statistic (p-value)": [_stat_with_p(s, p, exact=True)
                                          for s, p in zip(stat_df["kpss_stat"], stat_df["kpss_p"])],
        "Decision": stat_df["decision"],
    })
    col = list(table.columns).index
    shade, red = {}, {}
    for i, r in enumerate(stat_df.itertuples(index=False)):
        shade[(i, col("ADF test statistic (p-value)"))] = r.adf_p < alpha
        shade[(i, col("Phillips-Perron test statistic (p-value)"))] = r.pp_p < alpha
        shade[(i, col("KPSS test statistic (p-value)"))] = r.kpss_p >= alpha
        red[(i, col("KPSS test statistic (p-value)"))] = r.kpss_p < 0.01
    dec_col = col("Decision")
    _png_table(table, {(i, dec_col): d for i, d in enumerate(table["Decision"])}, out_path, title,
               [textwrap.fill(verdict or stationarity_verdict(stat_df), 150), *notes], red=red, shade=shade)


def _test_notes(stat_df: pd.DataFrame, alpha: float) -> list:
    crit = stat_df["adf_crit_5"]
    crit_txt = f"{crit.min():.2f}" + (f" to {crit.max():.2f}" if f"{crit.min():.2f}" != f"{crit.max():.2f}" else "")
    return [
        "Test statistic = the number each test computes from the data and compares with its critical value. "
        "ADF and Phillips-Perron (H0: unit root):",
        f"the more negative, the stronger the evidence against a unit root (5 % critical value {crit_txt}). "
        f"KPSS (H0: stationary): the larger, the stronger the evidence",
        f"against stationarity (5 % critical value {KPSS_CRITICAL_5PCT}). Green = the test points to stationarity "
        f"at {alpha:.0%}, light red = it does not; KPSS text red if p < 0.01.",
        "ADF: constant, lags by AIC up to 48, rerun up to 168 where 48 was selected (marked 'max 168'). KPSS: "
        "constant, automatic bandwidth, exact asymptotic p-value.",
        "Decision from ADF and KPSS; Phillips-Perron is a supporting check, not used in the decision.",
    ]


def make_tables(stat_df: pd.DataFrame, after_df: pd.DataFrame, controls_label: str, grid: pd.DataFrame | None,
                alpha: float, out_dir: Path, extra_notes: list | None = None):
    """stationarity_before_dummies.png (the series as they are),
    stationarity_after_dummies.png (after removing the calendar
    controls) and stationarity_robustness.png (grid)."""
    dropped = stat_df[stat_df["n_dropped"] > 0]
    dropped_note = ("Missing hours dropped before testing (not interpolated): " + "; ".join(
        f"{r.series} {r.zone} {r.n_dropped}" for r in dropped.itertuples()) + f" (of {stat_df['n_obs'].max():,} "
        f"hours max)." if len(dropped) else "No missing hours.")
    _main_table(stat_df, alpha, out_dir / "stationarity_before_dummies.png",
                f"Stationarity BEFORE the calendar dummies: the series as they are (levels, alpha = {alpha})",
                [*_test_notes(stat_df, alpha), dropped_note, *[textwrap.fill(n, 170) for n in (extra_notes or [])]])
    _main_table(after_df, alpha, out_dir / "stationarity_after_dummies.png",
                f"Stationarity AFTER the calendar dummies: residuals after {controls_label} (alpha = {alpha})",
                [*_test_notes(after_df, alpha),
                 f"Residuals of an OLS of each series on a constant + {controls_label} dummies (the calendar "
                 f"controls), computed on copies; the data are unchanged."],
                verdict=("All series stationary conditional on the calendar controls" if
                         (after_df["decision"] == STATIONARY).all() else
                         "Not stationary after the calendar controls: " + "; ".join(
                             f"{r.series} ({r.zone}): {r.decision}" for r in after_df.itertuples()
                             if r.decision != STATIONARY)))
    if grid is None:
        return
    checks = [c for c in grid.columns if c not in ("zone", "series")]
    codes = grid.rename(columns={"zone": "Area", "series": "Series"})
    colors = {}
    for j, c in enumerate(checks, start=2):
        for i, d in enumerate(grid[c]):
            colors[(i, j)] = d
        codes[c] = grid[c].map(DECISION_CODES)
    _png_table(codes, colors, out_dir / "stationarity_robustness.png",
               "Stationarity robustness: decision per check (same rule as the baseline)",
               ["S = stationary, U = unit root, C = conflict (both tests reject), I = inconclusive (neither "
                "rejects). Windows end in the last year; KPSS bw = fixed KPSS bandwidth;",
                "Calendar removed = residuals after the hour and week-of-sample fixed effects; alpha = "
                f"baseline p-values at another significance level (baseline alpha = {alpha})."], font=9)


def make_plots(df: pd.DataFrame, stat_df: pd.DataFrame, out_dir: Path):
    """For every tested series: the series with its 30-day rolling mean, and
    its 30-day rolling standard deviation (baseline decision in the title)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    for r in stat_df.itertuples(index=False):
        dz = _zone_frame(df, r.zone)
        s = pd.Series(dz[r.series].to_numpy(dtype=float), index=pd.DatetimeIndex(dz["datetime_utc"]))
        roll = s.rolling(ROLLING_WINDOW, min_periods=int(0.8 * 30 * 24))
        fig, axes = plt.subplots(2, 1, figsize=(12, 6.5), sharex=True)
        axes[0].plot(s.index, s.values, linewidth=0.3, color="0.6", label="hourly values")
        axes[0].plot(s.index, roll.mean().values, linewidth=1.4, color="#D55E00", label="30-day rolling mean")
        axes[0].set_ylabel("Value")
        axes[0].legend(fontsize=8, frameon=False, loc="upper left")
        axes[1].plot(s.index, roll.std().values, linewidth=1.2, color="#0072B2")
        axes[1].set_ylabel("30-day rolling std")
        axes[1].set_xlabel("Delivery time (UTC)")
        for ax in axes:
            for side in ("top", "right"):
                ax.spines[side].set_visible(False)
        fig.suptitle(f"{r.zone} — {r.series} (baseline decision: {r.decision})", fontsize=12)
        fig.tight_layout()
        fig.savefig(out_dir / f"{r.zone}_{r.series}.png", dpi=110)
        plt.close(fig)


def run_stationarity(df: pd.DataFrame, series_cols: list, zones: list, alpha: float, out_dir: Path,
                     robustness: bool = True) -> tuple[pd.DataFrame, pd.DataFrame | None, dict]:
    """Baseline tests, the calendar decomposition (which also selects the
    calendar controls, coarse to fine), the ADF bound check, the
    robustness checks, tables, plots and the console summary. Returns
    (baseline table, robustness grid or None, chosen controls)."""
    stat_df = run_tests(df, series_cols, zones, alpha)
    print("  [calendar] decomposition (diagnostic, on copies) and choice of the calendar controls")
    dec, fits = calendar_decomposition(df, series_cols, zones, alpha)
    choice = select_calendar_controls(dec)
    make_decomposition_tables(dec, fits, out_dir, choice)
    print("  [ADF] bound check")
    bound = adf_bound_check(df, stat_df, alpha=alpha)
    grid = None
    if robustness:
        first = int(df["datetime_utc"].dt.year.min())
        print("  [robustness] expanding windows")
        windows = run_windows(df, series_cols, zones, alpha)
        _check_reproduces_baseline(windows, stat_df, first)
        windows = windows[windows["first_year"] != first]  # the full window IS the baseline
        print("  [robustness] KPSS bandwidths")
        bands = run_bandwidths(df, series_cols, zones, stat_df, alpha)
        # No "calendar removed" column: after dummies the standard KPSS critical value
        # does not apply (see run_calendar_check and 'Final verdicts').
        grid = robustness_grid(stat_df, [windows, bands, run_alphas(stat_df)])
    for stale in ("stationarity_normalised_comparison.png", "stationarity.png"):
        if (out_dir / stale).exists():
            (out_dir / stale).unlink()
    after_df = run_tests(df, series_cols, zones, alpha, controls=choice["columns"])
    make_tables(stat_df, after_df, choice["label"], grid, alpha, out_dir,
                extra_notes=[controls_sentence(choice), bound_check_sentence(bound)])
    for old in (out_dir / "stationarity_plots").glob("*.png"):
        old.unlink()
    make_plots(df, stat_df, out_dir / "stationarity_plots")

    counts = stat_df["decision"].value_counts()
    print("\n  Baseline: " + ", ".join(f"{d} {int(counts.get(d, 0))}" for d in DECISION_ORDER))
    if grid is not None:
        print("  STATIONARY per check (of %d): " % len(grid) + ", ".join(
            f"{c} {int((grid[c] == STATIONARY).sum())}" for c in grid.columns if c not in ("zone", "series")))
    print("  " + controls_sentence(choice))
    print("  " + bound_check_sentence(bound))
    choice["bound_check"] = bound
    return stat_df, grid, choice


# ---------------------------------------------------------------------------
# CALENDAR CHECK — valid critical values after the calendar dummies
#   After removing hour + month-of-sample means, the KPSS partial sums return
#   to ~0 every month, so the statistic is small by construction and the
#   standard critical value (0.463) does not apply. Parametric bootstrap:
#   AR(p) (BIC) fitted to the residuals, innovations resampled in moving
#   blocks of 168 h (keeps heavy tails and time-varying variance), N
#   stationary series simulated, the SAME dummy matrix projected out, KPSS
#   with the same bandwidth rule -> 95th percentile = 5 % critical value.
#   ADF under H0 (unit root): a pure random walk with steps resampled in 168-h blocks
#   from the innovations of the level AR, the same dummies projected out, ADF
#   with the lag fixed at the data's lag -> 5th percentile.
#   Everything on copies; the dataframe, the controls and the raw decisions
#   are not changed.
# ---------------------------------------------------------------------------
CALENDAR_CHECK_N = 5000          # KPSS bootstrap replications
CALENDAR_CHECK_N_ADF = 1000      # ADF bootstrap replications (one regression per path, slower)
CALENDAR_CHECK_SEED = 2025
CALENDAR_CHECK_BURN_IN = 500
CALENDAR_CHECK_BLOCK = 168       # moving-block length for the innovations (hours)
CALENDAR_CHECK_AR_MAX = (48, 168)  # BIC search bounds for the AR order; the first one gives the decision
BW_SENSITIVE = "BANDWIDTH-SENSITIVE"
SERIES_NAMES = {"c_wind_total_err": "Wind forecast error", "c_load_err": "Demand forecast error",
                "x_da_id_spread": "DA-ID spread", "x_da_bal_spread": "DA-BAL spread",
                "x_id_bal_spread": "ID-BAL spread"}
FORECAST_ERRORS = ["c_wind_total_err", "c_load_err"]


def _fit_ar_bic(e: np.ndarray, max_lag: int = 48) -> tuple[np.ndarray, np.ndarray]:
    """AR(p) without constant on the centred series, p by BIC up to max_lag on
    the common sample (as statsmodels' ar_select_order: nested OLS, computed
    from one QR decomposition), then refitted by OLS with p lags. Returns
    (phi_1..phi_p, centred innovations)."""
    e = np.asarray(e, float) - np.mean(e)
    n = len(e) - max_lag
    y = e[max_lag:]
    X = np.column_stack([e[max_lag - k:-k] for k in range(1, max_lag + 1)])
    q, _ = np.linalg.qr(X)
    rss = np.r_[y @ y, y @ y - np.cumsum((q.T @ y) ** 2)]
    bic = n * np.log(rss / n) + np.arange(max_lag + 1) * math.log(n)
    p = int(np.argmin(bic))
    if p == 0:
        return np.zeros(0), e
    Xp = np.column_stack([e[p - k:-k] for k in range(1, p + 1)])
    phi = np.linalg.lstsq(Xp, e[p:], rcond=None)[0]
    resid = e[p:] - Xp @ phi
    return phi, resid - resid.mean()


def _block_indices(n_innov: int, length: int, n_sim: int, block: int, rng) -> np.ndarray:
    """(n_sim, length) indices into the innovations: consecutive runs of
    `block` indices starting at random positions (moving-block bootstrap)."""
    block = min(block, n_innov)
    n_blocks = -(-length // block)
    starts = rng.integers(0, n_innov - block + 1, size=(n_sim, n_blocks))
    idx = (starts[:, :, None] + np.arange(block)[None, None, :]).reshape(n_sim, -1)
    return idx[:, :length]


def _simulate_ar(phi: np.ndarray, innov: np.ndarray, n: int, n_sim: int, rng,
                 burn_in: int = CALENDAR_CHECK_BURN_IN, block: int | None = CALENDAR_CHECK_BLOCK) -> np.ndarray:
    """n_sim AR(phi) paths of length n (columns). Innovations resampled in
    moving blocks of `block` hours (None = i.i.d.), burn-in dropped.
    Shape (n, n_sim)."""
    from scipy.signal import lfilter

    if block:
        eps = innov[_block_indices(len(innov), n + burn_in, n_sim, block, rng)]
    else:
        eps = rng.choice(innov, size=(n_sim, n + burn_in), replace=True)
    x = lfilter([1.0], np.r_[1.0, -phi], eps, axis=1) if len(phi) else eps
    return x[:, burn_in:].T


def _dummy_basis(dz: pd.DataFrame, col: str, controls: list) -> tuple[np.ndarray, np.ndarray]:
    """Orthonormal basis Q of [constant, dummies] on the tested hours (the same
    matrix as residualise), and the boolean mask of those hours."""
    ok = dz[col].notna()
    for c in controls:
        ok &= dz[c].notna()
    parts = [pd.Series(1.0, index=dz.index[ok])]
    for c in controls:
        parts.append(pd.get_dummies(dz.loc[ok, c].astype("Int64"), drop_first=True, dtype=float))
    q, _ = np.linalg.qr(pd.concat(parts, axis=1).to_numpy(float))
    return q, ok.to_numpy()


def _project_out(q: np.ndarray | None, y: np.ndarray) -> np.ndarray:
    """Residuals of each column of y after [constant, dummies] (q) or after a constant only (q=None)."""
    return y - q @ (q.T @ y) if q is not None else y - y.mean(axis=0)


def kpss_critical_value_sim(e: np.ndarray, q: np.ndarray | None, n_sim: int, rng, ar_max: int = 48,
                            block: int | None = CALENDAR_CHECK_BLOCK, bandwidths: tuple = ("auto", 168),
                            chunk: int = 500) -> dict:
    """Simulated KPSS null distributions for residuals e after the projection
    q (None = constant only), per bandwidth rule. {ar_order, bw: array}."""
    phi, innov = _fit_ar_bic(e, ar_max)
    out = {"ar_order": len(phi), **{bw: [] for bw in bandwidths}}
    for start in range(0, n_sim, chunk):
        paths = _project_out(q, _simulate_ar(phi, innov, len(e), min(chunk, n_sim - start), rng, block=block))
        for bw in bandwidths:
            out[bw].extend(_kpss_test(paths[:, j], bw)["kpss_stat"] for j in range(paths.shape[1]))
    return {k: (np.array(v) if k != "ar_order" else v) for k, v in out.items()}


def _adf_tstat_fixed(x: np.ndarray, lag: int) -> float:
    """ADF t-statistic (constant, `lag` lagged differences) by least squares —
    the same regression as adfuller(autolag=None), without its overhead."""
    dx = np.diff(x)
    n = len(dx) - lag
    X = np.column_stack([np.ones(n), x[lag:-1]] + [dx[lag - k:-k] for k in range(1, lag + 1)])
    y = dx[lag:]
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    s2 = resid @ resid / (n - X.shape[1])
    xtx_inv = np.linalg.inv(X.T @ X)
    return float(beta[1] / math.sqrt(s2 * xtx_inv[1, 1]))


def adf_critical_value_sim(e: np.ndarray, q: np.ndarray | None, lag: int, n_sim: int, rng,
                           ar_max: int = 48, block: int | None = CALENDAR_CHECK_BLOCK) -> np.ndarray:
    """Simulated ADF null distribution (unit root): a pure random walk whose
    steps are resampled from the innovations of the level AR(p) of e — in
    moving blocks of `block` hours (None = i.i.d.), like the KPSS null —
    the same projection q (None = constant only), ADF with the lag fixed at
    `lag`. (Fitting an AR to the differences of a stationary series would
    over-difference it and make the 'random walks' behave like noise.)"""
    _, innov = _fit_ar_bic(e, ar_max)
    if block:
        steps = innov[_block_indices(len(innov), len(e), n_sim, block, rng)].T
    else:
        steps = rng.choice(innov, size=(len(e), n_sim), replace=True)
    paths = _project_out(q, np.cumsum(steps, axis=0))
    return np.array([_adf_tstat_fixed(paths[:, j], lag) for j in range(n_sim)])


DECISION_FILL = {STATIONARY: "#4CAF50", CONFLICT: "#FF9800", UNIT_ROOT: "#E53935", INCONCLUSIVE: "#9E9E9E",
                 BW_SENSITIVE: "#FFD54F"}


def _clean_table(table: pd.DataFrame, out_path: Path, title: str, notes: list, decisions: list,
                 group_ends: list, numeric: list, widths: dict):
    """Sparse table image: no grid; horizontal rules drawn separately (top,
    under the header, between the zones, bottom); numbers right-aligned;
    only the Decision column coloured. widths: inches per column (explicit,
    so no text runs into the next column); the same per column name in
    every figure."""
    nrow, ncol = table.shape
    row_h, title_h, note_h = 0.30, 0.45, 0.20
    w = [widths[c] for c in table.columns]
    fig_w = sum(w)
    table_h = row_h * (nrow + 1)
    fig_h = title_h + table_h + 0.12 + note_h * len(notes) + 0.08
    fig = plt.figure(figsize=(fig_w, fig_h))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.axis("off")
    bottom = (0.08 + note_h * len(notes) + 0.12) / fig_h
    tab = ax.table(cellText=table.astype(str).values, colLabels=list(table.columns),
                   colWidths=[x / fig_w for x in w], bbox=[0, bottom, 1, table_h / fig_h])
    tab.auto_set_font_size(False)
    tab.set_fontsize(9.5)
    for (r, c), cell in tab.get_celld().items():
        name = table.columns[c]
        loc = "right" if name in numeric else "left" if c < 2 else "center"
        cell._loc = loc
        cell.set_text_props(ha=loc)
        fill = "white"
        if r == 0:
            cell.set_text_props(weight="bold")
        elif name == "Decision":
            d = decisions[r - 1]
            fill = DECISION_FILL[d]
            cell.set_text_props(weight="bold", color="white" if d in (STATIONARY, UNIT_ROOT) else "black")
        cell.set_facecolor(fill)
        cell.set_edgecolor(fill)  # edges kept (so the fill is drawn) but invisible
    # horizontal rules, drawn separately in axes coordinates
    top = bottom + table_h / fig_h
    step = row_h / fig_h
    rules = [(top, 0.9), (top - step, 0.6), (bottom, 0.9)]
    rules += [(top - step * (g + 2), 0.5) for g in group_ends]
    for y, lw in rules:
        ax.plot([0, 1], [y, y], color="#757575", linewidth=lw, transform=ax.transAxes, clip_on=False)
    ax.text(0.005, 1 - 0.12 / fig_h, title, transform=ax.transAxes, ha="left", va="top", fontsize=12)
    ax.text(0.005, bottom - 0.1 / fig_h, "\n".join(notes), transform=ax.transAxes, ha="left", va="top",
            fontsize=8.5, color="#424242", linespacing=1.4)
    fig.savefig(out_path, dpi=150, bbox_inches="tight", pad_inches=0.15)
    plt.close(fig)


TABLE_WIDTHS = {"Area": 0.6, "Series": 1.9, "Dummy R²": 1.0, "ADF stat": 0.95, "ADF lags": 1.35,
                "KPSS stat": 1.0, "KPSS p": 0.95, "KPSS 5% crit. (sim.)": 1.75, "Decision": 2.0}


def _ordered_rows(df: pd.DataFrame, zones: list, series: list | None = None) -> list:
    return [(z, s) for z in zones for s in (series or SERIES_NAMES) if s in df.columns]


def _replace_md_section(path: Path, key: str, text: str):
    """Write `text` between <!-- key --> markers in a Markdown file (created
    if missing); run_stationarity_and_lag_selection keeps such sections when it rewrites the file."""
    start, end = f"<!-- {key} start -->", f"<!-- {key} end -->"
    old = path.read_text(encoding="utf-8") if path.exists() else ""
    if start in old and end in old:
        old = old[:old.index(start)] + old[old.index(end) + len(end):]
    path.write_text(old.rstrip() + f"\n\n{start}\n{text}\n{end}\n", encoding="utf-8")


def _kpss_verdicts(row: dict, ar_max: int) -> tuple[bool, bool]:
    """(passes with the automatic bandwidth, passes with bandwidth 168) against the simulated critical values."""
    return (row["kpss_stat"] < row[f"kpss_crit_auto_ar{ar_max}"],
            row["kpss_stat_168"] < row[f"kpss_crit_168_ar{ar_max}"])


def run_calendar_check(df: pd.DataFrame, zones: list, out_dir: Path, controls: list | None = None,
                       label: str = "hour + month", alpha: float = 0.05, n_sim: int = CALENDAR_CHECK_N,
                       n_sim_adf: int = CALENDAR_CHECK_N_ADF, seed: int = CALENDAR_CHECK_SEED,
                       adf_sim: bool = True) -> pd.DataFrame:
    """Table 1 (stationarity_baseline.png, all ten raw series), Table 2
    (stationarity_after_calendar.png, the four forecast errors) and every
    number as a Markdown section in VAR_TESTS.md."""
    controls = controls or CONTROL_SETS[0][1]
    rng = np.random.default_rng(seed)
    year = int(df["datetime_utc"].dt.year.max())
    boot_targets = {(z, s) for z in zones for s in FORECAST_ERRORS} | {("DK2", s) for s in SERIES_NAMES
                                                                      if s.startswith("x_")}
    rows = []
    for zone, col in _ordered_rows(df, zones):
        dz = _zone_frame(df, zone)
        print(f"  [calendar check] {zone} {col}")
        raw = stationarity_tests(dz[col], alpha)
        resid, r2, k = residualise(dz[col], [dz[c] for c in controls])
        _, r2_hour, _ = residualise(dz[col], [dz["fe_hour"]])
        after = stationarity_tests(resid, alpha)
        q, ok = _dummy_basis(dz, col, controls)
        e = resid.to_numpy()[ok]
        row = {"zone": zone, "series": col, "name": SERIES_NAMES[col],
               "raw_adf_stat": raw["adf_stat"], "raw_adf_p": raw["adf_p"], "raw_adf_lags": raw["adf_lags"],
               "raw_adf_max_lag": raw["adf_max_lag"], "raw_kpss_stat": raw["kpss_stat"], "raw_kpss_p": raw["kpss_p"],
               "raw_pp_stat": raw["pp_stat"], "raw_pp_p": raw["pp_p"], "raw_decision": raw["decision"],
               "raw_n_dropped": raw["n_dropped"], "n_dummies": k, "r2_hour": r2_hour, "r2_hour_month": r2,
               "adf_stat": after["adf_stat"], "adf_p": after["adf_p"], "adf_lags": after["adf_lags"],
               "adf_max_lag": after["adf_max_lag"], "pp_stat": after["pp_stat"], "pp_p": after["pp_p"],
               "kpss_stat": after["kpss_stat"], "kpss_stat_168": _kpss_test(e, 168)["kpss_stat"]}
        if (zone, col) in boot_targets:
            for ar_max in CALENDAR_CHECK_AR_MAX:
                print(f"    KPSS block bootstrap (AR by BIC, max {ar_max}, N = {n_sim})")
                ks = kpss_critical_value_sim(e, q, n_sim, rng, ar_max=ar_max)
                row[f"kpss_ar_order_ar{ar_max}"] = ks["ar_order"]
                for bw, obs in (("auto", row["kpss_stat"]), (168, row["kpss_stat_168"])):
                    row[f"kpss_crit_{bw}_ar{ar_max}"] = float(np.quantile(ks[bw], 0.95))
                    row[f"kpss_p_{bw}_ar{ar_max}"] = float((ks[bw] >= obs).mean())
            if adf_sim and col in FORECAST_ERRORS:
                print(f"    ADF random-walk bootstrap (lag fixed at {after['adf_lags']}, N = {n_sim_adf})")
                sims = adf_critical_value_sim(e, q, after["adf_lags"], n_sim_adf, rng)
                row["adf_crit_sim"] = float(np.quantile(sims, 0.05))
            adf_rejects = row["adf_stat"] < row.get("adf_crit_sim", -2.86)
            for ar_max in CALENDAR_CHECK_AR_MAX:
                pass_auto, pass_168 = _kpss_verdicts(row, ar_max)
                if pass_auto != pass_168:
                    row[f"decision_ar{ar_max}"] = BW_SENSITIVE
                else:
                    kpss_rejects = not pass_auto
                    row[f"decision_ar{ar_max}"] = (STATIONARY if adf_rejects and not kpss_rejects else UNIT_ROOT
                                                   if kpss_rejects and not adf_rejects else CONFLICT if adf_rejects
                                                   else INCONCLUSIVE)
            row["decision"] = row[f"decision_ar{CALENDAR_CHECK_AR_MAX[0]}"]
        rows.append(row)
    res = pd.DataFrame(rows)

    # A3: validation with a constant only — white noise, and the four raw forecast errors
    n_val = int(res["raw_n_dropped"].rsub(len(_zone_frame(df, zones[0]))).max())
    wn = kpss_critical_value_sim(rng.standard_normal(n_val), None, n_sim, rng, ar_max=1, block=None,
                                 bandwidths=("auto",))
    val = {"white_noise_kpss_crit": float(np.quantile(wn["auto"], 0.95)), "n": n_val, "raw": []}
    for zone, col in _ordered_rows(df, zones, FORECAST_ERRORS):
        x = _zone_frame(df, zone)[col].dropna().to_numpy(float)
        print(f"  [calendar check] raw constant-only bootstrap {zone} {col}")
        ks = kpss_critical_value_sim(x - x.mean(), None, n_sim, rng, ar_max=CALENDAR_CHECK_AR_MAX[0],
                                     bandwidths=("auto",))
        obs = float(res.loc[(res.zone == zone) & (res.series == col), "raw_kpss_stat"].iloc[0])
        val["raw"].append({"zone": zone, "series": col, "kpss_stat": obs, "ar_order": ks["ar_order"],
                           "crit": float(np.quantile(ks["auto"], 0.95)), "p": float((ks["auto"] >= obs).mean())})
    print(f"  [calendar check] white noise, constant only: KPSS 5 % crit {val['white_noise_kpss_crit']:.3f}")

    # --- Table 1: all ten raw series (unchanged content)
    group_ends = lambda r: [i for i in range(len(r) - 1) if r["zone"].iat[i] != r["zone"].iat[i + 1]]
    lags = lambda l, m: f"{l} (max {m})" if m != ADF_MAX_LAG else f"{l}"
    pp_agrees_raw = bool(((res["raw_pp_p"] < alpha) == (res["raw_adf_p"] < alpha)).all())
    dropped = res[res["raw_n_dropped"] > 0]
    dropped_txt = ("Missing hours dropped (not interpolated): " + ", ".join(
        f"{r.name.lower()} {r.zone} {r.raw_n_dropped}" for r in dropped.itertuples()) + ".") if len(dropped) else \
        "No missing hours."
    t1 = pd.DataFrame({
        "Area": res["zone"], "Series": res["name"], "ADF stat": res["raw_adf_stat"].map("{:.2f}".format),
        "ADF lags": [lags(l, m) for l, m in zip(res["raw_adf_lags"], res["raw_adf_max_lag"])],
        "KPSS stat": res["raw_kpss_stat"].map("{:.3f}".format),
        "KPSS p": res["raw_kpss_p"].map(lambda p: "<0.0001" if p < 1e-4 else f"{p:.4f}"),
        "Decision": res["raw_decision"]})
    _clean_table(t1, out_dir / "stationarity_baseline.png", f"Stationarity before calendar controls, {year}",
                 ["5 % critical values: ADF -2.86, KPSS 0.463 (KPSS p = exact asymptotic p-value). "
                  + ("Phillips-Perron agrees with ADF in all cases." if pp_agrees_raw else
                     "Phillips-Perron does not agree with ADF in every case (VAR_TESTS.md)."),
                  dropped_txt],
                 list(res["raw_decision"]), group_ends(res), ["ADF stat", "ADF lags", "KPSS stat", "KPSS p"],
                 TABLE_WIDTHS)

    # --- Table 2: the four forecast errors after the dummies
    fe = res[res["series"].isin(FORECAST_ERRORS)].reset_index(drop=True)
    a = CALENDAR_CHECK_AR_MAX[0]
    t2 = pd.DataFrame({
        "Area": fe["zone"], "Series": fe["name"], "Dummy R²": fe["r2_hour_month"].map("{:.2f}".format),
        "ADF stat": fe["adf_stat"].map("{:.2f}".format),
        "ADF lags": [lags(l, m) for l, m in zip(fe["adf_lags"], fe["adf_max_lag"])],
        "KPSS stat": fe["kpss_stat"].map("{:.3f}".format),
        "KPSS 5% crit. (sim.)": fe[f"kpss_crit_auto_ar{a}"].map("{:.3f}".format), "Decision": fe["decision"]})
    n_dum = int(fe["n_dummies"].iloc[0])
    _clean_table(t2, out_dir / "stationarity_after_calendar.png", f"Stationarity after {label} effects, {year}",
                 [f"Controls: {label} of sample ({n_dum} dummies + constant). KPSS critical values simulated per "
                  f"series: AR(p) by BIC, 168-h block bootstrap, N = {n_sim}, seed {seed}, automatic bandwidth.",
                  "ADF critical values simulated (random walk, 168-h block steps, same dummies, N = 1000): "
                  + (f"{fe['adf_crit_sim'].max():.2f} to {fe['adf_crit_sim'].min():.2f}." if adf_sim and
                     "adf_crit_sim" in fe else "not simulated, -2.86 used."),
                  "KPSS stat is compared with the simulated 5 % critical value, not 0.463. Spreads: the dummies "
                  "absorb about 1 % of the variance or less; the raw result stands."],
                 list(fe["decision"]), group_ends(fe),
                 ["Dummy R²", "ADF stat", "ADF lags", "KPSS stat", "KPSS 5% crit. (sim.)"], TABLE_WIDTHS)
    for stale in ("stationarity_before_dummies.png", "stationarity_after_dummies.png"):
        if (out_dir / stale).exists():
            (out_dir / stale).unlink()

    # --- every number, as Markdown (no CSV)
    num = res.drop(columns=["name"]).copy()
    for c in num.columns:
        if num[c].dtype.kind == "f":
            num[c] = num[c].map(lambda v: "" if pd.isna(v) else f"{v:.4g}")
    changed = [f"{r.zone} {r.name}: {r.decision_ar48} (BIC max 48) vs {r.decision_ar168} (max 168)"
               for r in res.dropna(subset=["decision"]).itertuples() if r.decision_ar48 != r.decision_ar168]
    fe_txt = "; ".join(f"{r.zone} {r.name.lower()} {r.r2_hour_month:.2f} (hour alone {r.r2_hour:.2f})"
                       for r in fe.itertuples())
    text = "\n".join([
        f"## Calendar check ({year}): critical values after {label}",
        "",
        "**In plain words.** After removing the hour-of-day and monthly means (the calendar controls), "
        "the KPSS statistic is small by construction, because the running sums return to zero every month; the "
        "standard critical value 0.463 does not apply. The reference used instead is a simulated one: many "
        "stationary series with the same autocorrelation and the same (block-resampled) shocks as each "
        "residual, with exactly the same dummies removed; the 95th percentile of their KPSS statistics is the "
        f"5 % critical value. Share of variance the dummies absorb: {fe_txt}; spreads <= 1 %.",
        "",
        f"**A3 finding.** With a constant only, white noise gives a simulated 5 % KPSS critical value of "
        f"{val['white_noise_kpss_crit']:.3f} (standard 0.463), so the simulation reproduces the standard test. "
        "For the strongly autocorrelated raw forecast errors the simulated value is higher (KPSS over-rejects "
        "when the bandwidth is short relative to the persistence), but the raw statistics stay far above it: "
        + "; ".join(f"{v['zone']} {SERIES_NAMES[v['series']].lower()} {v['kpss_stat']:.3f} vs {v['crit']:.3f} "
                    f"(p {v['p']:.4f}, AR {v['ar_order']})" for v in val["raw"])
        + ". The raw rejections are not a finite-sample artefact.",
        "",
        f"Settings: AR(p) without constant, p by BIC (max {' and max '.join(map(str, CALENDAR_CHECK_AR_MAX))}); "
        f"innovations resampled in moving blocks of {CALENDAR_CHECK_BLOCK} h; N = {n_sim} (KPSS), "
        f"{n_sim_adf} (ADF); seed {seed}; burn-in {CALENDAR_CHECK_BURN_IN}; KPSS with the automatic bandwidth "
        f"and with 168 (verdict {BW_SENSITIVE} when the two disagree); ADF null = random walk with steps in 168-h blocks "
        f"from the level-AR innovations, the same dummies, lag fixed at the data's lag. Decision (forecast errors, "
        f"BIC max 48): ADF below its simulated critical value and KPSS below its simulated critical value at both "
        f"bandwidths.",
        "",
        "Decision changes between BIC max 48 and max 168: " + ("; ".join(changed) if changed else "none") + ".",
        "",
        _md_table(num),
    ])
    _replace_md_section(out_dir / "VAR_TESTS.md", "calendar-check", text)
    res.attrs["validation"] = val
    return res


def day_of_week(dz: pd.DataFrame) -> pd.Series:
    """Day of the week (0 = Monday .. 6 = Sunday), Copenhagen local time — for
    the day-of-week diagnostic only; not one of the calendar controls."""
    return dz["datetime_utc"].dt.tz_convert("Europe/Copenhagen").dt.dayofweek.astype(float)


def run_dow_check(df: pd.DataFrame, zones: list, out_dir: Path, series: tuple = ("c_load_err",),
                  n_sim: int = CALENDAR_CHECK_N, n_sim_adf: int = CALENDAR_CHECK_N_ADF,
                  seed: int = CALENDAR_CHECK_SEED, bounds: tuple = (168, 336), alpha: float = 0.05) -> pd.DataFrame:
    """DIAGNOSTIC (copies only, the chosen controls are not changed): does a
    weekly cycle that hour + month dummies leave in the demand errors explain
    why the ADF lag search hits its bound? For hour + month and hour + month +
    day of week (6 dummies): R², autocorrelation of the residuals at 24 and
    168 h, the AIC-selected ADF lag with each bound, the ADF statistic and its
    simulated critical value (random walk, 168-h block steps, same dummies,
    lag fixed), the KPSS statistic and its simulated critical value (block
    bootstrap, automatic bandwidth). Written to VAR_TESTS.md."""
    from statsmodels.tsa.stattools import acf

    rng = np.random.default_rng(seed)
    rows = []
    for zone in zones:
        dz = _zone_frame(df, zone).copy()
        dz["_dow"] = day_of_week(dz)
        for col in series:
            for label, controls in (("hour + month", ["fe_hour", "fe_month_of_sample"]),
                                    ("hour + month + day of week", ["fe_hour", "fe_month_of_sample", "_dow"])):
                resid, r2, k = residualise(dz[col], [dz[c] for c in controls])
                q, ok = _dummy_basis(dz, col, controls)
                e = resid.to_numpy()[ok]
                rho = acf(e, nlags=168, fft=True)
                print(f"  [day-of-week check] {zone} {col}: {label} — KPSS bootstrap")
                ks = kpss_critical_value_sim(e, q, n_sim, rng, bandwidths=("auto",))
                k_obs = _kpss_test(e, "auto")["kpss_stat"]
                for bound in bounds:
                    lag = _adf_aic_lag(e, bound)
                    print(f"    ADF bound {bound}: lag {lag}, bootstrap N = {n_sim_adf}")
                    stat = _adf_tstat_fixed(e, lag)
                    crit = float(np.quantile(adf_critical_value_sim(e, q, lag, n_sim_adf, rng), 0.05))
                    rows.append({"zone": zone, "series": col, "controls": label, "dummies": k, "r2": r2,
                                 "acf_24": rho[24], "acf_168": rho[168], "adf_bound": bound, "adf_lag": lag,
                                 "adf_stat": stat, "adf_crit_sim": crit, "adf_rejects": stat < crit,
                                 "kpss_stat": k_obs, "kpss_crit_sim": float(np.quantile(ks["auto"], 0.95)),
                                 "kpss_p_sim": float((ks["auto"] >= k_obs).mean())})
    res = pd.DataFrame(rows)

    # plain-words note
    notes = []
    for zone in zones:
        for col in series:
            d = res[(res.zone == zone) & (res.series == col)]
            base, dow = d[d.controls == "hour + month"], d[d.controls != "hour + month"]
            lag_b = ", ".join(f"{int(r.adf_lag)} (bound {int(r.adf_bound)})" for r in base.itertuples())
            lag_d = ", ".join(f"{int(r.adf_lag)} (bound {int(r.adf_bound)})" for r in dow.itertuples())
            m = lambda x: "; ".join(f"bound {int(r.adf_bound)}: {r.adf_stat:.2f} vs {r.adf_crit_sim:.2f}"
                                    for r in x.itertuples())
            notes.append(f"{zone} {SERIES_NAMES[col].lower()}: selected ADF lag {lag_b} with hour + month, {lag_d} "
                         f"with day of week added. ADF statistic vs simulated 5 % critical value — hour + month: "
                         f"{m(base)}; + day of week: {m(dow)}. R² {base.r2.iloc[0]:.3f} -> {dow.r2.iloc[0]:.3f}; "
                         f"autocorrelation at 168 h {base.acf_168.iloc[0]:.3f} -> {dow.acf_168.iloc[0]:.3f}.")
    num = res.copy()
    for c in num.columns:
        if num[c].dtype.kind == "f":
            num[c] = num[c].map(lambda v: f"{v:.4g}")
    text = "\n".join([
        "## Day-of-week diagnostic (demand forecast errors; copies only, the controls are not changed)",
        "",
        f"Residuals after hour + month, and after hour + month + day of week (6 dummies, Copenhagen local time). "
        f"ADF lag by AIC with bound {' and '.join(map(str, bounds))}; ADF critical value simulated (random walk, "
        f"168-h block steps, the same dummies, lag fixed at the selected lag, N = {n_sim_adf}); KPSS critical value "
        f"simulated (AR(p) by BIC max 48, 168-h block bootstrap, N = {n_sim}, automatic bandwidth); seed {seed}. "
        f"Autocorrelations on the residuals joined across missing hours.",
        "",
        *notes,
        "",
        _md_table(num),
    ])
    _replace_md_section(out_dir / "VAR_TESTS.md", "dow-check", text)
    return res


def dow_check_main(name: str):
    """CLI: python src/model/stationarity_lag_selection.py --dow-check <dataframe>"""
    df = load_data(name)
    res = run_dow_check(df, sorted(df["bidding_zone"].unique()), PLOTS_DIR / name / "var_tests")
    print(res.round(4).to_string(index=False))


LAG_RULES = {  # name -> (information criterion, bound, two-stage 48 -> 168 like the baseline)
    "baseline (AIC 48 -> 168)": ("aic", None, True),
    "AIC bound 168": ("aic", 168, False),
    "AIC bound 336": ("aic", 336, False),
    "BIC bound 168": ("bic", 168, False),
}
MC_SEEDS = (2025, 7, 42)
MC_N_ADF = 2000


def _lag_by_rule(x: np.ndarray, rule: str) -> int:
    ic, bound, two_stage = LAG_RULES[rule]
    if two_stage:
        lag = _adf_aic_lag(x, ADF_MAX_LAG)
        return _adf_aic_lag(x, ADF_MAX_LAG_LONG) if lag == ADF_MAX_LAG else lag
    return _adf_aic_lag(x, bound, ic)


def run_final_checks(df: pd.DataFrame, zones: list, out_dir: Path, controls: list | None = None,
                     n_sim: int = CALENDAR_CHECK_N, n_sim_adf: int = CALENDAR_CHECK_N_ADF) -> dict:
    """Closes the stationarity step for the four forecast errors: month-only
    vs hour + month (T1), one robustness table over lag rules (T2), Monte Carlo
    noise of the simulated critical values over seeds (T3). Writes the
    sections to VAR_TESTS.md and returns all tables."""
    controls = controls or CONTROL_SETS[0][1]
    sets = {"month only": ["fe_month_of_sample"], "hour + month": controls}
    out = {"month": [], "lags": [], "mc_adf": [], "mc_kpss": []}
    for zone, col in _ordered_rows(df, zones, FORECAST_ERRORS):
        dz = _zone_frame(df, zone)
        x_raw = dz[col].dropna().to_numpy(float)
        resid_hm = residualise(dz[col], [dz[c] for c in controls])[0]
        q_hm, ok_hm = _dummy_basis(dz, col, controls)
        e_hm = resid_hm.to_numpy()[ok_hm]

        # --- T1: month only vs hour + month (same design as the calendar check)
        for label, cats in sets.items():
            print(f"  [final] {zone} {col}: {label}")
            rng = np.random.default_rng(CALENDAR_CHECK_SEED)
            resid, r2, k = residualise(dz[col], [dz[c] for c in cats])
            q, ok = _dummy_basis(dz, col, cats)
            e = resid.to_numpy()[ok]
            adf = _adf_test(e)
            crit = float(np.quantile(adf_critical_value_sim(e, q, adf["adf_lags"], n_sim_adf, rng), 0.05))
            ks = kpss_critical_value_sim(e, q, n_sim, rng)
            kauto, k168 = _kpss_test(e, "auto")["kpss_stat"], _kpss_test(e, 168)["kpss_stat"]
            c_auto, c_168 = float(np.quantile(ks["auto"], 0.95)), float(np.quantile(ks[168], 0.95))
            adf_rej = adf["adf_stat"] < crit
            pass_auto, pass_168 = kauto < c_auto, k168 < c_168
            dec = BW_SENSITIVE if pass_auto != pass_168 else (
                STATIONARY if adf_rej and pass_auto else CONFLICT if adf_rej else
                INCONCLUSIVE if pass_auto else UNIT_ROOT)
            out["month"].append({"zone": zone, "series": col, "controls": label, "dummies": k, "r2": r2,
                                 "adf_stat": adf["adf_stat"], "adf_lags": adf["adf_lags"], "adf_crit_sim": crit,
                                 "kpss_auto": kauto, "kpss_crit_auto": c_auto, "kpss_168": k168,
                                 "kpss_crit_168": c_168, "decision": dec})

        # --- T2: lag rules, raw (-2.86) and after hour + month (simulated at the same lag)
        for rule in LAG_RULES:
            print(f"  [final] {zone} {col}: lag rule {rule}")
            rng = np.random.default_rng(CALENDAR_CHECK_SEED)
            lag_r = _lag_by_rule(x_raw, rule)
            stat_r = _adf_tstat_fixed(x_raw, lag_r)
            lag_a = _lag_by_rule(e_hm, rule)
            stat_a = _adf_tstat_fixed(e_hm, lag_a)
            crit_a = float(np.quantile(adf_critical_value_sim(e_hm, q_hm, lag_a, n_sim_adf, rng), 0.05))
            out["lags"].append({"zone": zone, "series": col, "rule": rule,
                                "raw_lag": lag_r, "raw_adf": stat_r, "raw_crit": -2.86, "raw_rejects": stat_r < -2.86,
                                "after_lag": lag_a, "after_adf": stat_a, "after_crit_sim": crit_a,
                                "after_rejects": stat_a < crit_a})

        # --- T3: Monte Carlo noise over seeds
        lag_main = _adf_test(e_hm)["adf_lags"]
        stat_main = _adf_tstat_fixed(e_hm, lag_main)
        crits = []
        for seed in MC_SEEDS:
            print(f"  [final] {zone} {col}: ADF null, seed {seed}, N = {MC_N_ADF}")
            crits.append(float(np.quantile(adf_critical_value_sim(e_hm, q_hm, lag_main, MC_N_ADF,
                                                                  np.random.default_rng(seed)), 0.05)))
        out["mc_adf"].append({"zone": zone, "series": col, "lag": lag_main, "adf_stat": stat_main,
                              **{f"crit_seed_{s}": c for s, c in zip(MC_SEEDS, crits)},
                              "crit_mean": float(np.mean(crits)), "crit_min": min(crits), "crit_max": max(crits),
                              "rejects_all_seeds": all(stat_main < c for c in crits),
                              "rejects_any_seed": any(stat_main < c for c in crits)})
        kcrits, kps = [], []
        obs_raw = _kpss_test(x_raw, "auto")["kpss_stat"]
        for seed in MC_SEEDS:
            ks = kpss_critical_value_sim(x_raw - x_raw.mean(), None, n_sim, np.random.default_rng(seed),
                                         bandwidths=("auto",))
            kcrits.append(float(np.quantile(ks["auto"], 0.95)))
            kps.append(float((ks["auto"] >= obs_raw).mean()))
        out["mc_kpss"].append({"zone": zone, "series": col, "raw_kpss": obs_raw,
                               **{f"crit_seed_{s}": c for s, c in zip(MC_SEEDS, kcrits)},
                               "crit_mean": float(np.mean(kcrits)), "crit_min": min(kcrits), "crit_max": max(kcrits),
                               "p_min": min(kps), "p_max": max(kps)})
    tables = {k: pd.DataFrame(v) for k, v in out.items()}
    _write_final_sections(tables, out_dir)
    return tables


def _fmt_table(d: pd.DataFrame) -> str:
    d = d.copy()
    for c in d.columns:
        if d[c].dtype.kind == "f":
            d[c] = d[c].map(lambda v: f"{v:.4g}")
    return _md_table(d)


def _write_final_sections(t: dict, out_dir: Path):
    md = out_dir / "VAR_TESTS.md"
    m = t["month"]
    diff = []
    for (zone, col), g in m.groupby(["zone", "series"], sort=False):
        d = dict(zip(g["controls"], g["decision"]))
        if d["month only"] != d["hour + month"]:
            diff.append(f"{zone} {SERIES_NAMES[col].lower()}: {d['month only']} (month only) vs {d['hour + month']}")
    _replace_md_section(md, "month-only", "\n".join([
        "## Month-only vs hour + month (forecast errors)",
        "",
        "Same design as the calendar check (ADF lag by the baseline rule, critical values simulated with the "
        f"same dummies; KPSS critical values simulated at both bandwidths, N = {CALENDAR_CHECK_N}, seed "
        f"{CALENDAR_CHECK_SEED}; ADF N = {CALENDAR_CHECK_N_ADF}).",
        "",
        "In plain words: " + ("no decision differs between month only and hour + month." if not diff else
                              "decisions differ: " + "; ".join(diff) + "."),
        "",
        _fmt_table(m),
    ]))
    lg = t["lags"]
    lg_view = lg.assign(raw=lambda d: [f"{l} / {s:.2f} vs {c:.2f} — {'reject' if r else 'do not reject'}"
                                       for l, s, c, r in zip(d.raw_lag, d.raw_adf, d.raw_crit, d.raw_rejects)],
                        after=lambda d: [f"{l} / {s:.2f} vs {c:.2f} — {'reject' if r else 'do not reject'}"
                                         for l, s, c, r in zip(d.after_lag, d.after_adf, d.after_crit_sim,
                                                               d.after_rejects)])
    _replace_md_section(md, "lag-robustness", "\n".join([
        "## ADF lag-rule robustness (forecast errors)",
        "",
        "The main tables use ONE rule everywhere: AIC up to 48, extended to 168 only if 48 is selected. Each "
        "cell: selected lag / ADF statistic vs 5 % critical value — verdict. Raw: standard -2.86. After hour + "
        f"month: simulated at the same lag (random walk, 168-h block steps, same dummies, N = "
        f"{CALENDAR_CHECK_N_ADF}, seed {CALENDAR_CHECK_SEED}).",
        "",
        _md_table(lg_view[["zone", "series", "rule", "raw", "after"]]),
    ]))
    mc, mk = t["mc_adf"], t["mc_kpss"]
    flips = [f"{r.zone} {SERIES_NAMES[r.series].lower()}" for r in mc.itertuples()
             if r.rejects_all_seeds != r.rejects_any_seed]
    _replace_md_section(md, "monte-carlo", "\n".join([
        "## Monte Carlo noise of the simulated critical values",
        "",
        f"ADF after hour + month (baseline lag rule): N = {MC_N_ADF} per seed, seeds {', '.join(map(str, MC_SEEDS))}. "
        "Decision flips across seeds: " + (", ".join(flips) if flips else "none") + ".",
        "",
        _fmt_table(mc),
        "",
        f"Raw size-corrected KPSS (constant only, block bootstrap, automatic bandwidth): N = {CALENDAR_CHECK_N} per "
        f"seed, same seeds.",
        "",
        _fmt_table(mk),
    ]))


def final_checks_main(name: str):
    """CLI: python src/model/stationarity_lag_selection.py --final-checks <dataframe>"""
    df = load_data(name)
    t = run_final_checks(df, sorted(df["bidding_zone"].unique()), PLOTS_DIR / name / "var_tests")
    for k, v in t.items():
        print(f"\n== {k}")
        print(v.round(4).to_string(index=False))


ROLLING_HOURS = 720  # 30 days
SERIES_UNITS = {"c_wind_total_err": "MWh/h", "c_load_err": "MWh/h", "x_da_id_spread": "EUR/MWh",
                "x_da_bal_spread": "EUR/MWh", "x_id_bal_spread": "EUR/MWh"}
ZONE_COLORS = {"DK1": "#0072B2", "DK2": "#E69F00"}


def plot_rolling_figures(df: pd.DataFrame, zones: list, out_dir: Path, window_hours: int = ROLLING_HOURS):
    """rolling_<series>_<year>.png: per endogenous series, 2 rows (rolling mean,
    rolling standard deviation) x 2 columns (DK1, DK2). Trailing window of
    `window_hours` hours on the hourly UTC grid; a value needs >= 80 % of the
    window observed (missing hours are not filled). Rows share the y-axis."""
    year = int(df["datetime_utc"].dt.year.max())
    out_dir.mkdir(parents=True, exist_ok=True)
    for col, name in SERIES_NAMES.items():
        if col not in df.columns:
            continue
        unit = SERIES_UNITS[col]
        fig, axes = plt.subplots(2, len(zones), figsize=(6.2 * len(zones), 6.2), sharex=True, sharey="row",
                                 squeeze=False)
        for j, zone in enumerate(zones):
            dz = _zone_frame(df, zone)
            s = pd.Series(dz[col].to_numpy(float), index=pd.DatetimeIndex(dz["datetime_utc"]))
            roll = s.rolling(f"{window_hours}h", min_periods=int(0.8 * window_hours))
            for i, (stat, label) in enumerate(((roll.mean(), "Rolling mean"), (roll.std(), "Rolling std"))):
                ax = axes[i][j]
                ax.plot(stat.index, stat.values, color=ZONE_COLORS.get(zone, "0.3"), linewidth=1.2)
                if i == 0:
                    ax.axhline(0, color="0.6", linewidth=0.7)
                    ax.set_title(zone, fontsize=11)
                ax.set_ylabel(f"{label} [{unit}]", fontsize=9)
                ax.tick_params(labelsize=8)
                for side in ("top", "right"):
                    ax.spines[side].set_visible(False)
            axes[-1][j].set_xlabel("Delivery time (UTC, end of the trailing window)", fontsize=9)
            locator = mdates.AutoDateLocator()
            axes[-1][j].xaxis.set_major_locator(locator)
            axes[-1][j].xaxis.set_major_formatter(mdates.ConciseDateFormatter(locator))
        fig.suptitle(f"{name}, {year}: {window_hours}-hour ({window_hours // 24}-day) trailing rolling mean and "
                     f"standard deviation [{unit}]", fontsize=12)
        fig.tight_layout()
        fig.savefig(out_dir / f"rolling_{col}_{year}.png", dpi=140)
        plt.close(fig)
        print(f"  wrote rolling_{col}_{year}.png")


def calendar_check_main(name: str):
    """CLI: python src/model/stationarity_lag_selection.py --calendar-check <dataframe>"""
    df = load_data(name)
    res = run_calendar_check(df, sorted(df["bidding_zone"].unique()), PLOTS_DIR / name / "var_tests")
    cols = ["zone", "name", "r2_hour_month", "adf_stat", "adf_crit_sim", "kpss_stat", "kpss_stat_168",
            "kpss_crit_auto_ar48", "kpss_p_auto_ar48", "kpss_crit_168_ar48", "kpss_p_168_ar48",
            "kpss_crit_auto_ar168", "kpss_crit_168_ar168", "kpss_ar_order_ar48", "kpss_ar_order_ar168",
            "decision_ar48", "decision_ar168"]
    print(res[res["decision"].notna()][[c for c in cols if c in res.columns]].round(4).to_string(index=False))
    v = res.attrs["validation"]
    print(f"white noise KPSS crit {v['white_noise_kpss_crit']:.3f}")
    for r in v["raw"]:
        print(f"raw {r['zone']} {r['series']}: stat {r['kpss_stat']:.3f} crit {r['crit']:.3f} p {r['p']:.4f} "
              f"AR {r['ar_order']}")


# ---------------------------------------------------------------------------
# VAR BY OLS (supports non-contiguous lag structures such as 1-24 + 48)
# ---------------------------------------------------------------------------
def _design(dz: pd.DataFrame, y_cols: list, lags: list, exog: list, fe_cols: list,
            sample: pd.Series | None = None):
    """Y (T x K), X (T x m) and regressor names for one zone. dz is that
    zone's complete hourly grid in time order, so a shift of L rows = L
    hours. Only hours where everything is observed (and, if given, inside
    `sample`) are kept. Fixed-effect dummies are built on THOSE hours, with
    the first category present dropped — built on all hours, the dropped
    reference category could be one with no estimation hours (e.g. the first
    week, eaten by the lags), making the dummies sum to the constant."""
    parts = {"const": pd.Series(1.0, index=dz.index)}
    for lag in lags:
        for c in y_cols:
            parts[f"L{lag}.{c}"] = dz[c].shift(lag)
    for c in exog:
        parts[c] = dz[c]
    X = pd.DataFrame(parts)
    Y = dz[y_cols]
    ok = X.notna().all(axis=1) & Y.notna().all(axis=1)
    if sample is not None:
        ok &= sample
    X = X[ok]
    for c in fe_cols:
        X = X.join(pd.get_dummies(dz.loc[ok, c].astype("Int64"), prefix=c, drop_first=True, dtype=float))
    return Y[ok].to_numpy(float), X.to_numpy(float), list(X.columns), ok


def check_exog(dz: pd.DataFrame, exog: list, fe_cols: list, zone: str) -> list:
    """Smoke test of the exogenous block: prints the shape and rank of
    [constant, exog, fixed-effect dummies] on the hours where all are
    observed. A column that is perfectly collinear with the others is
    dropped (last one first) and named. Returns the exog columns kept."""
    exog = list(exog)
    while True:
        _, X, names, _ = _design(dz, [], [], exog, fe_cols)
        rank = np.linalg.matrix_rank(X)
        print(f"  [{zone}] exogenous matrix: {X.shape[0]} hours x {X.shape[1]} columns "
              f"(constant + {len(exog)} exogenous + {X.shape[1] - 1 - len(exog)} dummies), rank {rank}")
        if rank == X.shape[1]:
            return exog
        for c in reversed(exog):
            rest = [e for e in exog if e != c]
            _, Xr, _, _ = _design(dz, [], [], rest, fe_cols)
            if np.linalg.matrix_rank(Xr) == Xr.shape[1]:
                print(f"  [{zone}] WARNING — {c} is perfectly collinear with the other exogenous columns: dropped")
                exog = rest
                break
        else:
            raise RuntimeError(f"{zone}: exogenous matrix rank deficient ({rank} < {X.shape[1]}) and no single "
                               f"column explains it")


class LagSelectionFit:
    """Equation-by-equation OLS of y on [constant, lags of y, exogenous,
    dummies], used ONLY for the information criteria of the lag selection
    (residual covariance S(p)). Not a model estimate: no coefficients are
    reported or interpreted."""

    def __init__(self, Y, X, names, y_cols, lags):
        self.y_cols, self.lags, self.names = y_cols, list(lags), names
        self.T, self.K = Y.shape
        self.coef, _, rank, _ = np.linalg.lstsq(X, Y, rcond=None)  # m x K
        if rank < X.shape[1]:
            print(f"    WARNING — design matrix rank {rank} < {X.shape[1]} columns (collinear regressors)")
        resid = Y - X @ self.coef
        self.sigma = resid.T @ resid / self.T

    def criteria(self) -> tuple[float, float]:
        logdet = np.linalg.slogdet(self.sigma)[1]
        p = len(self.lags)
        return (logdet + 2 * p * self.K ** 2 / self.T,
                logdet + p * self.K ** 2 * math.log(self.T) / self.T)


def fit_lag_structure(dz, y_cols, lags, exog, fe_cols, sample=None) -> LagSelectionFit:
    """sample: optional boolean mask restricting the hours (used to give every
    lag structure the same sample in the lag selection)."""
    Y, X, names, _ = _design(dz, y_cols, lags, exog, fe_cols, sample)
    return LagSelectionFit(Y, X, names, y_cols, lags)


# ---------------------------------------------------------------------------
# PLOTS
# ---------------------------------------------------------------------------
def _plot_lag_selection(lag_df: pd.DataFrame, out_path: Path):
    models = lag_df[["zone", "spread"]].drop_duplicates().itertuples(index=False)
    models = list(models)
    zones = sorted({m.zone for m in models})
    spreads = list(dict.fromkeys(m.spread for m in models))
    fig, axes = plt.subplots(len(zones), len(spreads), figsize=(5 * len(spreads), 3.4 * len(zones)), squeeze=False)
    for r, zone in enumerate(zones):
        for c, spread in enumerate(spreads):
            ax = axes[r][c]
            d = lag_df[(lag_df.zone == zone) & (lag_df.spread == spread)]
            cont = d[d.structure.str.startswith("1..")]
            ax.plot(cont.n_lag_matrices, cont.aic, marker="o", label="AIC (contiguous 1..p)", color="#0072B2")
            ax.plot(cont.n_lag_matrices, cont.bic, marker="s", label="BIC (contiguous 1..p)", color="#D55E00")
            lit = d[~d.structure.str.startswith("1..")]
            ax.scatter(lit.n_lag_matrices, lit.aic, marker="*", s=120, color="#0072B2", zorder=3,
                       label="AIC (lags 1-24 + 48)")
            ax.scatter(lit.n_lag_matrices, lit.bic, marker="*", s=120, color="#D55E00", zorder=3,
                       label="BIC (lags 1-24 + 48)")
            ax.set_xscale("log", base=2)
            ax.set_xticks(sorted(d.n_lag_matrices.unique()))
            ax.set_xticklabels(sorted(d.n_lag_matrices.unique()))
            ax.set_title(f"{zone} — {spread}", fontsize=10)
            ax.set_xlabel("Number of lag matrices p", fontsize=8)
            ax.set_ylabel("Information criterion (lower = better)", fontsize=8)
            ax.tick_params(labelsize=8)
            for s in ("top", "right"):
                ax.spines[s].set_visible(False)
    handles, labels = axes[0][0].get_legend_handles_labels()
    # Title, then the legend on its own row underneath it, then the panels
    # (space reserved in inches, so it doesn't depend on the figure height).
    fig_h = fig.get_size_inches()[1]
    fig.suptitle("VAR lag selection (same estimation sample for every p)", y=1 - 0.12 / fig_h,
                 va="top", fontsize=12)
    fig.legend(handles, labels, loc="upper center", bbox_to_anchor=(0.5, 1 - 0.5 / fig_h), ncol=4,
               frameon=False, fontsize=9)
    fig.tight_layout(rect=(0, 0, 1, 1 - 0.95 / fig_h))
    fig.savefig(out_path, dpi=130)
    plt.close(fig)


# ---------------------------------------------------------------------------
# PIPELINE
# ---------------------------------------------------------------------------
def _md_table(df: pd.DataFrame) -> str:
    lines = ["| " + " | ".join(map(str, df.columns)) + " |", "|" + "|".join("---" for _ in df.columns) + "|"]
    lines += ["| " + " | ".join(str(v) for v in r) + " |" for r in df.itertuples(index=False)]
    return "\n".join(lines)


def run_stationarity_and_lag_selection(name: str, model_spec: dict, zones: list | None = None,
                                       start: str | None = None, end: str | None = None,
                                       full_lags: list = FULL_LAGS, candidate_lags: list = CANDIDATE_LAGS,
                                       alpha: float = 0.05, sensitivity: bool = True,
                                       calendar_check: tuple = ()):
    """The "var_tests" step of main.py: stationarity tests and lag selection
    (no model is estimated). calendar_check: dataframe names for which the
    calendar check (simulated critical values after the dummies, the two
    sparse figures) replaces the before / after tables."""
    from model_specs import flow_columns, select_flow_columns

    endo = [v["column"] for v in model_spec["variables"] if v["role"] == "Endogenous"]
    exo = [v["column"] for v in model_spec["variables"] if v["role"] == "Exogenous" and v["column"]]
    spreads = [c for c in endo if c.startswith("x_")]
    errors = [c for c in endo if not c.startswith("x_")]
    flows = flow_columns(model_spec)
    exog_fixed = [c for c in exo if not c.startswith("fe_") and c not in flows]

    df = load_data(name, start, end)
    empty = [c for c in exog_fixed if df[c].isna().all()]
    if empty:
        print(f"  WARNING — exogenous column(s) with no data, left out of the lag selection: {empty}")
        exog_fixed = [c for c in exog_fixed if c not in empty]
    zones = zones or sorted(df["bidding_zone"].unique())
    out_dir = PLOTS_DIR / name / "var_tests"
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"  period {df['datetime_utc'].min():%Y-%m-%d} .. {df['datetime_utc'].max():%Y-%m-%d}, zones {zones}")

    # 1. stationarity — reported only; the series stay in levels
    stat_df, grid, choice = run_stationarity(df, errors + spreads, zones, alpha, out_dir, robustness=sensitivity)
    verdict = stationarity_verdict(stat_df)
    print(f"\n  Stationarity: {verdict}")
    # The calendar controls (fixed effects) used in the lag-selection regressions
    # (chosen in run_stationarity).
    fe_cols = choice["columns"]
    print(f"  Calendar controls: {choice['label']} ({', '.join(fe_cols)})")
    if name in calendar_check:
        run_calendar_check(df, zones, out_dir, controls=fe_cols, label=choice["label"].replace(" of sample", ""),
                           alpha=alpha)

    # 2. exogenous block per zone: fixed exogenous + the zone's kept flows
    kept_flows = select_flow_columns(df[df["bidding_zone"].isin(zones)], model_spec)
    exog_by_zone = {}
    for zone in zones:
        exog_by_zone[zone] = check_exog(_zone_frame(df, zone), exog_fixed + kept_flows[zone], fe_cols, zone)

    lag_rows = []
    for zone in zones:
        dz = _zone_frame(df, zone)
        exog = exog_by_zone[zone]
        print(f"  [{zone}] endogenous: errors {errors} + one spread of {spreads}; exogenous {exog} + FE {fe_cols}")
        for spread in spreads:
            y_cols = errors + [spread]
            key = f"{zone} — {spread}"
            print(f"  [{key}] lag selection")
            # 3. lag selection on one common sample (valid for the longest structure)
            structures = {f"1..{p}": list(range(1, p + 1)) for p in candidate_lags}
            structures["1-24 + 48"] = list(full_lags)
            common = _design(dz, y_cols, sorted(set().union(*structures.values())), exog, fe_cols)[3]
            crit = {}
            for label, lags in structures.items():
                fit = fit_lag_structure(dz, y_cols, lags, exog, fe_cols, sample=common)
                aic, bic = fit.criteria()
                crit[label] = (aic, bic)
                lag_rows.append({"zone": zone, "spread": spread, "structure": label, "n_lag_matrices": len(lags),
                                 "T": fit.T, "aic": round(aic, 5), "bic": round(bic, 5)})
            contiguous = {k: v for k, v in crit.items() if k.startswith("1..")}
            best_bic = min(contiguous, key=lambda k: contiguous[k][1])
            best_aic = min(contiguous, key=lambda k: contiguous[k][0])
            for row in lag_rows[-len(structures):]:
                row["bic_choice"] = row["structure"] == best_bic
                row["aic_choice"] = row["structure"] == best_aic

    lag_df = pd.DataFrame(lag_rows)
    _plot_lag_selection(lag_df, out_dir / "lag_selection.png")

    report = [
        f"# Stationarity tests and lag selection — `{name}`",
        "",
        "No VAR / VARX is estimated here: only the stationarity tests and the lag selection for a later model.",
        "",
        f"Lag selection: one system per (zone, spread); y = ({', '.join(errors)}, spread); exogenous per zone: "
        + "; ".join(f"{z}: {', '.join(e) or 'none'}" for z, e in exog_by_zone.items())
        + f" + dummies for {', '.join(fe_cols)}. Significance level {alpha}.",
        *([f"Left out (no data yet): {', '.join(empty)}."] if empty else []),
        "",
        "## 1. Stationarity (ADF: H0 unit root; KPSS: H0 stationary; PP: H0 unit root, supporting)",
        "STATIONARY: ADF rejects, KPSS does not. UNIT ROOT: the reverse. CONFLICT: both reject. "
        "INCONCLUSIVE: neither rejects. Nothing is differenced: the series stay in levels. KPSS p = exact "
        "asymptotic p-value (not truncated).",
        "",
        _md_table(pd.DataFrame({
            "zone": stat_df["zone"], "series": stat_df["series"], "n": stat_df["n_obs"],
            "n_dropped": stat_df["n_dropped"], "adf_stat": stat_df["adf_stat"].round(3),
            "adf_p": stat_df["adf_p"].map(_fmt_p), "adf_lags": stat_df["adf_lags"],
            "adf_max_lag": stat_df["adf_max_lag"], "kpss_stat": stat_df["kpss_stat"].round(3),
            "kpss_p": stat_df["kpss_p"].map(_fmt_p_exact), "pp_p": stat_df["pp_p"].map(_fmt_p),
            "decision": stat_df["decision"]})),
        "",
        f"**{verdict}**",
        "",
        controls_sentence(choice),
        "",
        bound_check_sentence(choice["bound_check"]),
        "",
        *(["Robustness (S stationary, U unit root, C conflict, I inconclusive):", "",
           _md_table(grid.assign(**{c: grid[c].map(DECISION_CODES) for c in grid.columns
                                    if c not in ("zone", "series")})), "",
           "After the calendar controls (hour + month of sample) the standard critical values do not apply; see the sections 'Calendar check' (simulated critical values) and 'Final verdicts'.", ""] if grid is not None else []),
        "## 2. Lag selection (same sample for every structure; lower = better)",
        "",
        _md_table(lag_df.pivot_table(index=["zone", "spread"], columns="structure", values="bic", sort=False)
                  .round(4).reset_index()) if len(lag_df) else "",
        "",
        "BIC-preferred contiguous order: " + "; ".join(
            f"{r.zone} {r.spread}: {r.structure}" for r in lag_df[lag_df.bic_choice].itertuples()),
        "",
    ]
    # Keep sections written by other steps (between <!-- key start / end --> markers, e.g. the calendar check).
    md = out_dir / "VAR_TESTS.md"
    old = md.read_text(encoding="utf-8") if md.exists() else ""
    kept = re.findall(r"<!-- [\w-]+ start -->.*?<!-- [\w-]+ end -->", old, re.S)
    md.write_text("\n".join(report + kept) + "\n", encoding="utf-8")
    print(f"  wrote {out_dir}")
    return stat_df, grid, lag_df


# ---------------------------------------------------------------------------
# TESTS — every test of the project, in this one file. Run:
#     python src/model/stationarity_lag_selection.py --test          (fast tests)
#     python src/model/stationarity_lag_selection.py --test --slow   (+ the full-sample window
#                                                    check, ~15 min)
# Each test_* function raises AssertionError on failure; pytest can also
# collect them (pytest src/model/stationarity_lag_selection.py).
# ---------------------------------------------------------------------------
_ROOT = _here.parents[2]
_TEST_DATA = DATAFRAMES_DIR / "baseline_2025.csv"
_TEST_SERIES = ["c_wind_total_err", "c_load_err", "x_da_id_spread", "x_da_bal_spread", "x_id_bal_spread"]


def _hourly(values: np.ndarray) -> pd.Series:
    return pd.Series(values, index=pd.date_range("2025-01-01", periods=len(values), freq="h", tz="UTC"))


def _test_frame() -> pd.DataFrame | None:
    if not _TEST_DATA.exists():
        return None
    df = pd.read_csv(_TEST_DATA)
    df["datetime_utc"] = pd.to_datetime(df["datetime_utc"], utc=True)
    return df


# --- stationarity decision and tests ----------------------------------------
def test_decide_four_cases():
    for adf_p, kpss_p, expected in [(0.001, 0.10, STATIONARY),    # ADF rejects, KPSS does not
                                    (0.40, 0.01, UNIT_ROOT),       # ADF does not reject, KPSS rejects
                                    (0.001, 0.01, CONFLICT),       # both reject
                                    (0.40, 0.10, INCONCLUSIVE)]:   # neither rejects
        assert decide(adf_p, kpss_p, alpha=0.05) == expected, (adf_p, kpss_p)


def test_decide_threshold_is_strict():
    assert decide(0.05, 0.05, alpha=0.05) == INCONCLUSIVE  # p exactly at alpha does NOT reject


def test_white_noise_is_stationary():
    rng = np.random.default_rng(42)
    assert stationarity_tests(_hourly(rng.standard_normal(2000)))["decision"] == STATIONARY


def test_random_walk_is_unit_root():
    rng = np.random.default_rng(42)
    assert stationarity_tests(_hourly(np.cumsum(rng.standard_normal(2000))))["decision"] == UNIT_ROOT


def test_nans_are_dropped_and_counted():
    values = np.random.default_rng(0).standard_normal(500)
    values[[3, 50, 400]] = np.nan
    res = stationarity_tests(_hourly(values))
    assert res["n_dropped"] == 3 and res["n_obs"] == 497


def test_kpss_asymptotic_pvalue_matches_critical_values():
    for stat, p_expected, tol in [(0.347, 0.10, 0.002), (0.463, 0.05, 0.002), (0.739, 0.01, 0.001)]:
        assert abs(kpss_asymptotic_pvalue(stat) - p_expected) < tol, stat  # KPSS 10 / 5 / 1 % critical values


def test_kpss_asymptotic_pvalue_is_decreasing_and_continuous():
    ps = [kpss_asymptotic_pvalue(s) for s in [0.05, 0.1, 0.19, 0.2, 0.21, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0]]
    assert all(a > b for a, b in zip(ps, ps[1:]))
    assert abs(kpss_asymptotic_pvalue(0.2 - 1e-9) - kpss_asymptotic_pvalue(0.2)) < 1e-7  # the two formulas join


def test_fast_adf_lag_search_matches_statsmodels():
    """The exact fast lag search gives statsmodels' autolag lag, statistic and p-value."""
    from statsmodels.tsa.stattools import adfuller

    rng = np.random.default_rng(7)
    for phi in (0.0, 0.5, 0.95, 1.0):
        e = rng.standard_normal(4000)
        x = np.zeros_like(e)
        for t in range(1, len(x)):
            x[t] = phi * x[t - 1] + e[t] + 0.4 * e[t - 1]
        ref = adfuller(x, maxlag=24, regression="c", autolag="AIC", result_object=False)
        mine = _adf_test(x, max_lag=24, max_lag_long=None)
        assert mine["adf_lags"] == ref[2], phi
        assert np.isclose(mine["adf_stat"], ref[0]) and np.isclose(mine["adf_p"], ref[1]), phi


def test_fast_bic_lag_search_matches_statsmodels():
    from statsmodels.tsa.stattools import adfuller

    rng = np.random.default_rng(11)
    for phi in (0.3, 0.9):
        e = rng.standard_normal(3000)
        x = np.zeros_like(e)
        for t in range(1, len(x)):
            x[t] = phi * x[t - 1] + e[t] + 0.5 * e[t - 1]
        ref = adfuller(x, maxlag=30, regression="c", autolag="BIC", result_object=False)
        assert _adf_aic_lag(x, 30, "bic") == ref[2], phi


def test_residualise_drops_one_category_per_block():
    t = pd.date_range("2025-01-06", periods=24 * 7 * 4, freq="h", tz="UTC")
    hour = pd.Series(t.hour.to_numpy(dtype=float))
    week = pd.Series((np.arange(len(t)) // 168 + 1).astype(float))
    y = pd.Series(np.random.default_rng(2).standard_normal(len(t)))
    y.iloc[[5, 6]] = np.nan
    resid, r2, k = residualise(y, [hour, week])
    assert k == 23 + 3                       # 24 hours - 1, 4 weeks - 1
    assert resid.isna().sum() == 2 and 0 <= r2 < 0.05
    assert y.notna().sum() == len(t) - 2     # the input series is not changed


def test_week_of_year_repeats_across_years():
    t = pd.date_range("2022-01-03", "2025-12-28 23:00", freq="h", tz="Europe/Copenhagen").tz_convert("UTC")
    w = week_of_year(pd.DataFrame({"datetime_utc": t}))
    assert w.min() == 1 and w.max() == 52 and w.nunique() == 52


def test_kpss_bandwidth_must_be_below_sample_size():
    try:
        _kpss_test(np.random.default_rng(0).standard_normal(100), 168)
    except ValueError:
        return
    raise AssertionError("no ValueError for nlags >= n")


# --- robustness checks ----------------------------------------------------------
def test_each_window_contains_only_its_years():
    t = pd.date_range("2021-06-01", "2026-06-30", freq="h", tz="UTC")
    frame = pd.DataFrame({"datetime_utc": t, "bidding_zone": "DK1", "v": np.arange(len(t), dtype=float)})
    for first_year in [2025, 2024, 2023, 2022]:
        w = select_window(frame, first_year, 2025)
        assert set(w["datetime_utc"].dt.year) == set(range(first_year, 2026)), first_year
        # every hour of those years is there (no partial years cut off)
        assert len(w) == sum(8784 if y % 4 == 0 else 8760 for y in range(first_year, 2026)), first_year


def test_remove_calendar_removes_hour_and_week_means():
    t = pd.date_range("2025-01-06", periods=24 * 7 * 6, freq="h", tz="UTC")
    hour, week = t.hour.to_numpy(), (np.arange(len(t)) // 168) + 1
    noise = np.random.default_rng(1).standard_normal(len(t))
    dz = pd.DataFrame({"y": 5 * np.sin(hour / 24 * 2 * np.pi) + 3 * week + noise,
                       "fe_hour": hour.astype(float), "fe_week_of_sample": week.astype(float)})
    resid = remove_calendar(dz, "y", ["fe_hour", "fe_week_of_sample"])
    assert abs(resid.mean()) < 1e-8
    assert resid.groupby(dz["fe_hour"]).mean().abs().max() < 1e-8   # no hour pattern left
    assert resid.std() < 1.1                                        # only the noise left


def test_full_window_reproduces_the_baseline():
    """Slow: the full-sample window must reproduce the baseline exactly."""
    df = _test_frame()
    if df is None:
        return
    zones = sorted(df["bidding_zone"].unique())
    first = int(df["datetime_utc"].dt.year.min())
    baseline = run_tests(df, _TEST_SERIES, zones)
    full = run_windows(df, _TEST_SERIES, zones, first_years=[first])
    _check_reproduces_baseline(full, baseline, first)  # raises if anything differs
    assert (full["decision"].to_numpy() == baseline["decision"].to_numpy()).all()


# --- VAR estimation ---------------------------------------------------------------
def test_lag_selection_fit_matches_statsmodels():
    """The OLS fit behind the information criteria matches statsmodels (coefficients and the ML residual
    covariance) on a simulated two-lag system."""
    from statsmodels.tsa.api import VAR

    rng = np.random.default_rng(3)
    A1 = np.array([[0.5, 0.1, 0.0], [0.0, 0.4, 0.2], [0.3, 0.0, 0.3]])
    A2 = np.array([[0.1, 0.0, 0.0], [0.0, 0.1, 0.0], [0.2, 0.1, 0.1]])
    y = np.zeros((3000, 3))
    for t in range(2, len(y)):
        y[t] = A1 @ y[t - 1] + A2 @ y[t - 2] + rng.standard_normal(3)
    dz = pd.DataFrame(y, columns=["a", "b", "c"])
    mine = fit_lag_structure(dz, ["a", "b", "c"], [1, 2], [], [])
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        ref = VAR(dz).fit(2, trend="c")
    assert np.allclose(mine.coef, ref.params.values)
    assert np.allclose(mine.sigma, ref.sigma_u_mle)


# --- cross-border flows (they replace the former price-based bottleneck indicator) ---
_OLD_WORD = "conges" + "tion"  # spelled in two parts so this file doesn't match its own search


def test_no_references_to_the_old_indicator_remain():
    import re

    files = [_ROOT / "main.py", *(_ROOT / "src").rglob("*.py")]
    hits = []
    for f in files:
        if "__pycache__" in f.parts:
            continue
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("#"):
                continue  # comments may explain the change
            if _OLD_WORD in re.sub(r"\s+#.*$", "", line).lower():
                hits.append(f"{f.relative_to(_ROOT)}: {line.strip()}")
    assert not hits, hits


def test_flow_columns_documented_with_the_sign_convention():
    sys.path.insert(0, str(_here.parents[1]))
    from dataframe_building import DERIVED_FEATURES, FLOW_COUNTERPARTS
    from model_specs import MODEL_SPECS, flow_columns

    for code in FLOW_COUNTERPARTS:
        meta = DERIVED_FEATURES[f"da_flow_{code}_net_export_mw"]["meta"]
        assert "Positive = export" in meta["direction"] and "negative = import" in meta["direction"], code
        assert meta["unit"] == "MWh/h", code
    assert set(flow_columns(MODEL_SPECS["spodniak2019_baseline"])) == \
        {f"da_flow_{c}_net_export_mw" for c in FLOW_COUNTERPARTS}


def test_flow_columns_hourly_index_and_sign():
    sys.path.insert(0, str(_here.parents[1]))
    from dataframe_building import FLOW_COUNTERPARTS, PROCESSED_DIR

    df = _test_frame()
    if df is None:
        return
    assert all(f"da_flow_{c}_net_export_mw" in df.columns for c in FLOW_COUNTERPARTS)
    for zone, g in df.groupby("bidding_zone"):
        t = g["datetime_utc"].sort_values()
        assert t.is_unique and (t.diff().dropna() == pd.Timedelta(hours=1)).all(), zone  # gap-free hourly UTC
    # sign: positive = export, i.e. export - import of the raw Nord Pool file
    raw = pd.read_csv(PROCESSED_DIR / "day_ahead" / "flows_DK1_DK2_2021_2025_hourly.csv")
    raw["datetime_utc"] = pd.to_datetime(raw["DeliveryStartUTC"], utc=True)
    m = df.merge(raw, left_on=["datetime_utc", "bidding_zone"], right_on=["datetime_utc", "Area"])
    assert len(m) == len(df)
    for code in FLOW_COUNTERPARTS:
        expected = m[f"{code.upper()}_Export_MW"] - m[f"{code.upper()}_Import_MW"]
        assert np.allclose(m[f"da_flow_{code}_net_export_mw"], expected, equal_nan=True), code


def test_flow_selection_drops_unconnected_counterparts():
    sys.path.insert(0, str(_here.parents[1]))
    from model_specs import MODEL_SPECS, select_flow_columns

    df = _test_frame()
    if df is None:
        return
    kept = select_flow_columns(df, MODEL_SPECS["spodniak2019_baseline"], verbose=False)
    assert "da_flow_se4_net_export_mw" not in kept["DK1"] and "da_flow_nl_net_export_mw" not in kept["DK2"]
    assert "da_flow_dk1_net_export_mw" not in kept["DK1"] and "da_flow_dk2_net_export_mw" not in kept["DK2"]


# --- calendar controls -----------------------------------------------------------------
def test_month_of_sample_is_one_per_local_month():
    df = _test_frame()
    if df is None or "fe_month_of_sample" not in df.columns:
        return
    for zone, g in df.groupby("bidding_zone"):
        local = g["datetime_utc"].dt.tz_convert("Europe/Copenhagen")
        month = local.dt.year * 12 + local.dt.month
        assert (g.groupby(month)["fe_month_of_sample"].nunique() == 1).all(), zone  # constant within a month
        hours = g.groupby("fe_month_of_sample").size()
        assert hours.min() >= 24, zone  # no tiny edge month (the final 00:00 local hour is merged into December)
        assert hours.index.tolist() == list(range(1, len(hours) + 1)), zone  # renumbered 1..N
        assert (g.groupby(month)["fe_month_of_sample"].nunique() == 1).all(), zone


def test_controls_choose_the_coarsest_sufficient_set():
    def dec(month_ok: bool, week_ok: bool) -> pd.DataFrame:
        rows = []
        for case, ok in (("5 Hour + month of sample", month_ok), ("7 Hour + week of sample", week_ok)):
            rows += [{"case": case, "decision_auto": STATIONARY}, {"case": case,
                     "decision_auto": STATIONARY if ok else CONFLICT}]
        return pd.DataFrame(rows)
    assert select_calendar_controls(dec(True, True))["label"] == "hour + month of sample"
    assert select_calendar_controls(dec(False, True))["label"] == "hour + week of sample"
    c = select_calendar_controls(dec(False, False))
    assert c["label"] == "hour + week of sample" and not c["sufficient"]


# --- calendar check (bootstrap) ------------------------------------------------------------
def test_block_indices_are_consecutive_runs():
    rng = np.random.default_rng(0)
    idx = _block_indices(n_innov=1000, length=500, n_sim=20, block=168, rng=rng)
    assert idx.shape == (20, 500) and idx.min() >= 0 and idx.max() < 1000
    for row in idx:
        for start in range(0, 500, 168):  # inside each block the indices run consecutively
            run = row[start:start + 168]
            assert (np.diff(run) == 1).all()


def test_fast_ar_bic_matches_statsmodels():
    from statsmodels.tsa.ar_model import ar_select_order

    rng = np.random.default_rng(4)
    e = rng.standard_normal(4000)
    x = np.zeros_like(e)
    for t in range(2, len(x)):
        x[t] = 0.6 * x[t - 1] - 0.2 * x[t - 2] + e[t]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        ref = ar_select_order(x - x.mean(), maxlag=12, ic="bic", trend="n").ar_lags
    phi, _ = _fit_ar_bic(x, 12)
    assert len(phi) == max(ref) and np.allclose(phi, [0.6, -0.2], atol=0.05)


def test_kpss_bootstrap_reproduces_the_standard_value_for_white_noise():
    rng = np.random.default_rng(8)
    sims = kpss_critical_value_sim(rng.standard_normal(2000), None, 400, rng, ar_max=1, block=None,
                                   bandwidths=("auto",))
    assert 0.38 < np.quantile(sims["auto"], 0.95) < 0.56  # standard 5 % value 0.463


def test_random_walk_adf_null_reproduces_the_standard_value():
    rng = np.random.default_rng(9)
    sims = adf_critical_value_sim(rng.standard_normal(2000), None, 0, 400, rng, ar_max=1, block=None)
    assert -3.15 < np.quantile(sims, 0.05) < -2.6  # standard 5 % value -2.86 (i.i.d. steps)


def test_day_of_week_is_local_monday_to_sunday():
    t = pd.date_range("2025-02-03", periods=24 * 7, freq="h", tz="Europe/Copenhagen").tz_convert("UTC")
    d = day_of_week(pd.DataFrame({"datetime_utc": t}))
    assert d.nunique() == 7 and d.iloc[0] == 0 and d.iloc[-1] == 6  # 2025-02-03 is a Monday (no DST change)


def test_block_random_walk_adf_null_reproduces_the_standard_value():
    # Block-resampled steps add dispersion (blocks are redrawn from one finite innovation sample), so
    # the check uses a realistic length (one year of hours) and a wider band around -2.86.
    rng = np.random.default_rng(10)
    sims = adf_critical_value_sim(rng.standard_normal(8000), None, 0, 300, rng, ar_max=1, block=168)
    assert -3.3 < np.quantile(sims, 0.05) < -2.5


SLOW_TESTS = {"test_full_window_reproduces_the_baseline"}


def self_test(slow: bool = False) -> bool:
    """Runs every test_* function of this file; prints PASSED / FAILED per test."""
    import time
    import traceback

    tests = [(n, f) for n, f in globals().items() if n.startswith("test_") and callable(f)]
    failed = passed = skipped = 0
    for name, func in tests:
        if name in SLOW_TESTS and not slow:
            skipped += 1
            print(f"  SKIPPED  {name} (slow; run with --slow)")
            continue
        t0 = time.time()
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", FutureWarning)
                func()
            passed += 1
            print(f"  PASSED   {name} ({time.time() - t0:.1f}s)")
        except Exception:
            failed += 1
            print(f"  FAILED   {name}\n{traceback.format_exc()}")
    print(f"\n{passed} passed, {failed} failed, {skipped} skipped")
    return failed == 0


def main():
    if "--test" in sys.argv:
        sys.exit(0 if self_test(slow="--slow" in sys.argv) else 1)
    if "--rolling-figures" in sys.argv:
        name = sys.argv[sys.argv.index("--rolling-figures") + 1]
        df = load_data(name)
        plot_rolling_figures(df, sorted(df["bidding_zone"].unique()), PLOTS_DIR / name / "var_tests")
        return
    if "--final-checks" in sys.argv:
        final_checks_main(sys.argv[sys.argv.index("--final-checks") + 1])
        return
    if "--dow-check" in sys.argv:
        dow_check_main(sys.argv[sys.argv.index("--dow-check") + 1])
        return
    if "--calendar-check" in sys.argv:
        calendar_check_main(sys.argv[sys.argv.index("--calendar-check") + 1])
        return
    if "--adf-lag-check" in sys.argv:
        adf_lag_check_main(sys.argv[sys.argv.index("--adf-lag-check") + 1])
        return
    sys.path.insert(0, str(_here.parents[1]))
    from model_specs import MODEL_SPECS
    run_stationarity_and_lag_selection(sys.argv[1] if len(sys.argv) > 1 else "baseline_2025",
                  MODEL_SPECS["spodniak2019_baseline"])


if __name__ == "__main__":
    main()
