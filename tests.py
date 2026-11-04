"""
tests.py — checks of the pipeline's own calculations. From the project root:

    python tests.py

Every test_* function raises AssertionError on failure. Tests on the real
data (data/processed/, data/dataframes/baseline_2025.csv) are skipped when
the files are missing.
"""

import sys
import time
import traceback
import warnings
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from dataframe import building  # noqa: E402
from dataframe.documentation import _MetadataResolver  # noqa: E402
from models import VARX  # noqa: E402
from VAR_tests import lag_selection  # noqa: E402
from VAR_tests import residual_checks as rc  # noqa: E402
from VAR_tests import stationarity as st  # noqa: E402
from hypothesis import error_spreads as es  # noqa: E402
from hypothesis import forecast_errors as fe  # noqa: E402
from hypothesis import shocks_and_breaks as sb  # noqa: E402

DATAFRAME = building.OUTPUT_DIR / "baseline_2025.csv"


class Skip(Exception):
    pass


def _hourly(values: np.ndarray) -> pd.Series:
    return pd.Series(values, index=pd.date_range("2025-01-01", periods=len(values), freq="h", tz="UTC"))


def _dataframe() -> pd.DataFrame:
    if not DATAFRAME.exists():
        raise Skip(f"{DATAFRAME.name} not built")
    df = pd.read_csv(DATAFRAME)
    df["datetime_utc"] = pd.to_datetime(df["datetime_utc"], utc=True)
    return df


# --- LaTeX outputs -------------------------------------------------------------
def test_latex_numbers():
    import latex_outputs

    assert latex_outputs._number(-1234.6) == "$-$1{,}235" and latex_outputs._number(12.34) == "12.3"
    assert latex_outputs._number(-0.04) == "0.0"  # no minus sign on a value that rounds to zero


def test_descriptive_table_has_one_row_per_variable_and_zone():
    import latex_outputs
    from common import zone_frame

    df = _dataframe()
    spec = building.make_spec(["x_da_id_spread", "c_wind_total_err"], ["fe_hour"])
    rows = [line for line in latex_outputs.descriptive_table(df, spec).splitlines()
            if line.endswith(r"\\") and r"\textbf" not in line]
    assert len(rows) == 4
    mean = zone_frame(df, "DK1")["c_wind_total_err"].mean()
    assert any(" & DK1 & " in r and f"& {latex_outputs._number(mean)} &" in r for r in rows)


def test_descriptive_table_shows_a_variable_shared_by_all_zones_once():
    import latex_outputs

    df = _dataframe()
    spec = building.make_spec(["c_wind_total_err"], ["c_reservoir_deviation_pct_no", "fe_hour"])
    table = latex_outputs.descriptive_table(df, spec, "Exogenous")
    rows = [line for line in table.splitlines() if line.endswith(r"\\") and r"\textbf" not in line]
    assert len(rows) == 1 and " & all & " in rows[0] and "Calendar dummies are left out" in table


# --- dataframe building ------------------------------------------------------
def test_spec_finds_the_inputs_recursively():
    spec = building.make_spec(["c_wind_total_err"], ["fe_hour"])
    assert spec.inputs == ("c_wind_total_forecast_mw", "c_wind_onshore_forecast_mw", "c_wind_offshore_forecast_mw",
                           "c_wind_total_actual_mw", "c_wind_onshore_actual_mw", "c_wind_offshore_actual_mw")
    assert spec.calendar == ["fe_hour"] and spec.role("c_wind_onshore_actual_mw") == "Input"


def test_a_variable_is_never_also_an_input():
    spec = building.make_spec(["c_wind_total_err"], ["c_wind_total_actual_mw"])
    assert "c_wind_total_actual_mw" not in spec.inputs and spec.role("c_wind_total_actual_mw") == "Exogenous"


def test_spec_rejects_unknown_and_repeated_columns():
    for endogenous, exogenous in ((["no_such_column"], []), (["c_load_err"], ["c_load_err"])):
        try:
            building.make_spec(endogenous, exogenous)
        except ValueError:
            continue
        raise AssertionError(f"no error for {endogenous} / {exogenous}")


def test_every_derived_input_exists():
    for name, cfg in building.DERIVED_FEATURES.items():
        for col in cfg["inputs"]:
            assert col in building.SOURCE_OF or col in building.DERIVED_FEATURES, (name, col)


def test_every_column_is_documented():
    resolver = _MetadataResolver()
    for col in [*building.SOURCE_OF, *building.DERIVED_FEATURES]:
        resolver.describe(col)
    assert not resolver.undocumented, sorted(set(resolver.undocumented))


def test_season_and_hour_of_season_identifiers():
    t = pd.date_range("2025-01-01", "2025-12-31 23:00", freq="h", tz="Europe/Copenhagen").tz_convert("UTC")
    frame = pd.DataFrame({"datetime_utc": t})
    season = building.DERIVED_FEATURES["fe_season"]["func"](frame)
    hour_of_season = building.DERIVED_FEATURES["fe_hour_of_season"]["func"](frame)
    local = t.tz_convert("Europe/Copenhagen")
    assert sorted(season.unique()) == [1, 2, 3, 4] and hour_of_season.nunique() == 96
    assert (hour_of_season % 24 == local.hour).all()                    # the hour inside the season block
    assert (hour_of_season // 24 + 1 == season).all()                   # the season block
    assert (season[local.month.isin([12, 1, 2])] == 1).all() and (season[local.month == 7] == 3).all()


def test_hour_of_week_identifier():
    t = pd.date_range("2025-03-24", "2025-04-06 23:00", freq="h", tz="Europe/Copenhagen").tz_convert("UTC")
    how = building.DERIVED_FEATURES["fe_hour_of_week"]["func"](pd.DataFrame({"datetime_utc": t}))
    local = t.tz_convert("Europe/Copenhagen")
    assert how.nunique() == 168 and (how % 24 == local.hour).all() and (how // 24 == local.dayofweek).all()


def test_copied_check_finds_a_forecast_filled_with_past_actuals():
    from dataframe.documentation import _copied_check

    rng = np.random.default_rng(15)
    t = pd.date_range("2025-01-01", periods=2000, freq="h", tz="UTC")
    actual = pd.Series(1000 + rng.normal(0, 50, len(t)))
    honest = actual + rng.normal(0, 30, len(t))
    copied = actual.shift(168).fillna(honest)  # the forecast is last week's actual
    for forecast, expected in ((honest, "No"), (copied, "Yes")):
        df = pd.DataFrame({"datetime_utc": t, "bidding_zone": "DK1", "c_load_forecast_mw": forecast,
                           "c_load_actual_mw": actual})
        assert _copied_check(df, "c_load_forecast_mw", ["DK1"])[0] == expected
    assert _copied_check(df, "c_load_actual_mw", ["DK1"]) == ("", "")  # not a forecast


def test_reservoir_median_uses_only_earlier_years():
    if not building.RESERVOIR_WEEKLY_PATH.exists():
        raise Skip("reservoir data missing")
    hourly = building.load_source("reservoir", ["c_reservoir_fill_median_pct_no"], ["DK1"])
    weekly = pd.read_csv(building.RESERVOIR_WEEKLY_PATH)
    no = weekly[weekly["Area"] == "NO"]
    for week in (1, 20, 40):
        wednesday = date.fromisocalendar(2025, week, 3)
        hour = pd.Timestamp(f"{wednesday} 12:00", tz="Europe/Oslo").tz_convert("UTC")
        got = hourly.loc[hourly["datetime_utc"] == hour, "c_reservoir_fill_median_pct_no"].item()
        expected = no[(no["IsoWeek"] == week) & (no["IsoYear"] < 2025)]["ReservoirUtilization_pct"].median()
        assert np.isclose(got, expected), (week, got, expected)


def test_flow_sign_matches_the_raw_file():
    df = _dataframe()
    raw = pd.read_csv(building.SOURCES["da_nordpool_flows"]["path"])
    raw["datetime_utc"] = pd.to_datetime(raw["DeliveryStartUTC"], utc=True)
    m = df.merge(raw, left_on=["datetime_utc", "bidding_zone"], right_on=["datetime_utc", "Area"])
    assert len(m) == len(df)
    for code in building.FLOW_COUNTERPARTS:
        col = f"da_flow_{code}_net_export_mw"
        if col in df.columns:  # positive = export
            expected = m[f"{code.upper()}_Export_MW"] - m[f"{code.upper()}_Import_MW"]
            assert np.allclose(m[col], expected, equal_nan=True), code


def test_lagged_ramp_is_the_previous_hour():
    df = _dataframe()
    col, ramp = "c_wind_total_actual_mw_change_1_lag_1", "c_wind_total_actual_mw_change_1"
    if col not in df.columns:
        raise Skip("lagged ramp not in the dataframe")
    for zone, g in df.groupby("bidding_zone"):
        g = g.sort_values("datetime_utc")
        assert np.allclose(g[col].iloc[1:], g[ramp].shift(1).iloc[1:], equal_nan=True), zone
        assert g[col].iloc[0] == g[col].iloc[0]  # first hour filled from the warm-up, not NaN


def test_month_of_sample_is_one_per_local_month():
    df = _dataframe()
    for zone, g in df.groupby("bidding_zone"):
        local = g["datetime_utc"].dt.tz_convert(building.LOCAL_TZ)
        month = local.dt.year * 12 + local.dt.month
        hours = g.groupby("fe_month_of_sample").size()
        assert hours.min() >= building.MIN_EDGE_MONTH_HOURS, zone           # no tiny edge month
        assert hours.index.tolist() == list(range(1, len(hours) + 1)), zone  # renumbered 1..N
        assert (g.groupby(month)["fe_month_of_sample"].nunique() == 1).all(), zone


# --- stationarity ---------------------------------------------------------------
def test_decide_four_cases_and_strict_threshold():
    for adf_p, kpss_p, expected in [(0.001, 0.10, st.STATIONARY), (0.40, 0.01, st.UNIT_ROOT),
                                    (0.001, 0.01, st.CONFLICT), (0.40, 0.10, st.INCONCLUSIVE)]:
        assert st.decide(adf_p, kpss_p, alpha=0.05) == expected, (adf_p, kpss_p)
    assert st.decide(0.05, 0.05, alpha=0.05) == st.INCONCLUSIVE  # p exactly at alpha does NOT reject


def test_white_noise_is_stationary_and_random_walk_is_unit_root():
    rng = np.random.default_rng(42)
    assert st.stationarity_tests(_hourly(rng.standard_normal(2000)))["decision"] == st.STATIONARY
    assert st.stationarity_tests(_hourly(np.cumsum(rng.standard_normal(2000))))["decision"] == st.UNIT_ROOT


def test_missing_hours_are_dropped_and_counted():
    values = np.random.default_rng(0).standard_normal(500)
    values[[3, 50, 400]] = np.nan
    res = st.stationarity_tests(_hourly(values))
    assert res["n_dropped"] == 3 and res["n_obs"] == 497


def test_kpss_asymptotic_pvalue():
    for stat, p_expected, tol in [(0.347, 0.10, 0.002), (0.463, 0.05, 0.002), (0.739, 0.01, 0.001)]:
        assert abs(st.kpss_asymptotic_pvalue(stat) - p_expected) < tol, stat  # the published critical values
    ps = [st.kpss_asymptotic_pvalue(s) for s in [0.05, 0.1, 0.19, 0.2, 0.21, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0]]
    assert all(a > b for a, b in zip(ps, ps[1:]))
    assert abs(st.kpss_asymptotic_pvalue(0.2 - 1e-9) - st.kpss_asymptotic_pvalue(0.2)) < 1e-7  # formulas join


def test_kpss_critical_value_is_the_standard_one():
    assert abs(st.kpss_critical_value(0.05) - 0.463) < 0.002  # Kwiatkowski et al. (1992), level stationarity
    assert np.isclose(st.kpss_asymptotic_pvalue(st.kpss_critical_value(0.05)), 0.05)


def test_kpss_bandwidth_must_be_below_sample_size():
    try:
        st._kpss_test(np.random.default_rng(0).standard_normal(100), 168)
    except ValueError:
        return
    raise AssertionError("no ValueError for nlags >= n")


def test_fast_adf_lag_search_matches_statsmodels():
    from statsmodels.tsa.stattools import adfuller

    rng = np.random.default_rng(7)
    for phi in (0.0, 0.5, 0.95, 1.0):
        e = rng.standard_normal(4000)
        x = np.zeros_like(e)
        for t in range(1, len(x)):
            x[t] = phi * x[t - 1] + e[t] + 0.4 * e[t - 1]
        for ic in ("AIC", "BIC"):
            ref = adfuller(x, maxlag=24, regression="c", autolag=ic, result_object=False)
            assert st._adf_lag(x, 24, ic.lower()) == ref[2], (phi, ic)
        ref = adfuller(x, maxlag=24, regression="c", autolag="AIC", result_object=False)
        mine = st._adf_test(x, max_lag=24, max_lag_long=None)
        assert np.isclose(mine["adf_stat"], ref[0]) and np.isclose(mine["adf_p"], ref[1]), phi


def test_fast_adf_tstat_matches_statsmodels():
    from statsmodels.tsa.stattools import adfuller

    rng = np.random.default_rng(13)
    for phi in (0.5, 1.0):
        x = np.zeros(3000)
        for t in range(1, len(x)):
            x[t] = phi * x[t - 1] + rng.standard_normal()
        for lag in (0, 5, 48):
            ref = adfuller(x, maxlag=lag, regression="c", autolag=None, result_object=False)[0]
            assert np.isclose(st._adf_tstat(x, lag), ref, rtol=1e-8), (phi, lag)


def test_residualise_drops_one_category_per_block():
    t = pd.date_range("2025-01-06", periods=24 * 7 * 4, freq="h", tz="UTC")
    hour = pd.Series(t.hour.to_numpy(dtype=float))
    week = pd.Series((np.arange(len(t)) // 168 + 1).astype(float))
    y = pd.Series(5 * np.sin(hour / 24 * 2 * np.pi) + 3 * week + np.random.default_rng(2).standard_normal(len(t)))
    y.iloc[[5, 6]] = np.nan
    resid, r2, k = st.residualise(y, [hour, week])
    assert k == 23 + 3                                     # 24 hours - 1, 4 weeks - 1
    assert resid.isna().sum() == 2 and y.isna().sum() == 2  # the input series is not changed
    assert resid.groupby(hour).mean().abs().max() < 1e-8   # no hour pattern left
    assert r2 > 0.8


def test_block_indices_are_consecutive_runs():
    idx = st._block_indices(n_innov=1000, length=500, n_sim=20, block=168, rng=np.random.default_rng(0))
    assert idx.shape == (20, 500) and idx.min() >= 0 and idx.max() < 1000
    for row in idx:
        for start in range(0, 500, 168):
            assert (np.diff(row[start:start + 168]) == 1).all()


def test_fast_ar_bic_matches_statsmodels():
    from statsmodels.tsa.ar_model import ar_select_order

    e = np.random.default_rng(4).standard_normal(4000)
    x = np.zeros_like(e)
    for t in range(2, len(x)):
        x[t] = 0.6 * x[t - 1] - 0.2 * x[t - 2] + e[t]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        ref = ar_select_order(x - x.mean(), maxlag=12, ic="bic", trend="n").ar_lags
    phi, _ = st._fit_ar_bic(x, 12)
    assert len(phi) == max(ref) and np.allclose(phi, [0.6, -0.2], atol=0.05)


def test_simulated_nulls_reproduce_the_standard_critical_values():
    rng = np.random.default_rng(8)
    noise = rng.standard_normal(2000)
    kpss = st.kpss_null(np.zeros(0), noise, 2000, None, 400, rng, bandwidths=("auto",), block=None)
    assert 0.38 < np.quantile(kpss["auto"], 0.95) < 0.56                       # standard 0.463
    adf = st.adf_null(noise - noise.mean(), 2000, None, 0, 400, rng, block=None)
    assert -3.15 < np.quantile(adf, 0.05) < -2.6                               # standard -2.86
    long_noise = rng.standard_normal(8000)  # block steps add dispersion: a year of hours, wider band
    adf_block = st.adf_null(long_noise - long_noise.mean(), 8000, None, 0, 300, rng, block=168)
    assert -3.3 < np.quantile(adf_block, 0.05) < -2.5


# --- lag selection -----------------------------------------------------------------
def _simulated_var(lags: dict, n: int = 3000, seed: int = 3) -> pd.DataFrame:
    """A 3-variable VAR with coefficient matrices {lag: A}, standard normal errors."""
    rng = np.random.default_rng(seed)
    y = np.zeros((n, 3))
    for t in range(max(lags), n):
        y[t] = sum(A @ y[t - lag] for lag, A in lags.items()) + rng.standard_normal(3)
    return pd.DataFrame(y, columns=["a", "b", "c"])


A1 = np.array([[0.5, 0.1, 0.0], [0.0, 0.4, 0.2], [0.3, 0.0, 0.3]])
A2 = np.array([[0.1, 0.0, 0.0], [0.0, 0.1, 0.0], [0.2, 0.1, 0.1]])


def _statsmodels_var(dz: pd.DataFrame, p: int):
    from statsmodels.tsa.api import VAR

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return VAR(dz).fit(p, trend="c")


def test_fit_and_information_criteria_match_statsmodels_var():
    dz = _simulated_var({1: A1, 2: A2})
    model = lag_selection.fit(dz, ["a", "b", "c"], [1, 2], [], [])
    ref = _statsmodels_var(dz, 2)
    assert np.allclose(model["coef"], ref.params.values) and np.allclose(model["sigma"], ref.sigma_u_mle)
    T, K = model["resid"].shape
    ics = lag_selection.information_criteria(model["sigma"], T, 2, K)
    # statsmodels also penalises the K constants: the same shift for every p, so the choice is unchanged
    for ic, ref_value in (("aic", ref.aic), ("hq", ref.hqic), ("bic", ref.bic)):
        assert np.isclose(ics[ic] + lag_selection.CRITERIA[ic](T) / T * K, ref_value), ic


def test_structure_from_the_shared_design_equals_a_direct_fit():
    dz = _simulated_var({1: A1, 2: A2})
    dz["cat"] = (np.arange(len(dz)) // 500).astype(float)  # a calendar-like category
    full = lag_selection._design(dz, ["a", "b", "c"], [1, 2, 3, 4], [], ["cat"])
    shared = lag_selection.fit_structure(full, [1, 2], ["a", "b", "c"])
    direct = lag_selection.fit(dz, ["a", "b", "c"], [1, 2], [], ["cat"], sample=full[3])
    assert shared["names"] == direct["names"]
    assert np.allclose(shared["coef"], direct["coef"]) and np.allclose(shared["sigma"], direct["sigma"])


def test_criteria_find_the_order_of_a_simulated_var():
    dz = _simulated_var({1: A1, 2: A2})
    sel = lag_selection.select_order(dz, ["a", "b", "c"], [], [], "aic", 8, [1, 2])
    assert sel["best"]["bic"] == sel["best"]["hq"] == 2  # the true order
    assert sel["best"]["bic"] <= sel["best"]["hq"] <= sel["best"]["aic"] < 8 and sel["bound"] == 8


def test_search_widens_when_the_choice_is_at_the_bound():
    dz = _simulated_var({lag: 0.12 * np.eye(3) for lag in range(1, 7)})  # true order 6
    sel = lag_selection.select_order(dz, ["a", "b", "c"], [], [], "bic", 4, [1, 2])
    assert sel["bound"] == 8 and sel["best"]["bic"] == 6


def test_systems_separate_exactly_dependent_variables():
    rng = np.random.default_rng(5)
    dz = pd.DataFrame(rng.standard_normal((500, 3)), columns=["a", "b", "d"])
    dz["c"] = dz["a"] + dz["b"]  # like DA-BAL = DA-ID + ID-BAL
    assert lag_selection.endogenous_systems(dz, ["a", "b", "c", "d"]) == [["d", "a"], ["d", "b"], ["d", "c"]]
    assert lag_selection.endogenous_systems(dz, ["a", "b", "d"]) == [["a", "b", "d"]]


# --- residual checks -----------------------------------------------------------------
def test_lm_test_matches_breusch_godfrey_for_one_variable():
    import statsmodels.api as sm
    from statsmodels.stats.diagnostic import acorr_breusch_godfrey

    rng = np.random.default_rng(12)
    x = np.zeros(2000)
    for t in range(2, len(x)):
        x[t] = 0.5 * x[t - 1] + 0.3 * x[t - 2] + rng.standard_normal()
    dz = pd.DataFrame({"a": x})
    model = lag_selection.fit(dz, ["a"], [1], [], [])  # one lag too few
    stat, df, p = rc.lm_test(model, 4)
    with warnings.catch_warnings():  # statsmodels warns about its own internal call
        warnings.simplefilter("ignore", FutureWarning)
        ref = acorr_breusch_godfrey(sm.OLS(dz["a"].iloc[1:].to_numpy(), model["X"]).fit(), nlags=4,
                                    result_object=False)
    assert df == 4 and np.isclose(stat, ref[0]) and np.isclose(p, ref[1])


def test_both_lm_tests_find_a_missing_lag():
    dz = _simulated_var({1: A1, 2: A2})
    too_short = lag_selection.fit(dz, ["a", "b", "c"], [1], [], [])
    right = lag_selection.fit(dz, ["a", "b", "c"], [1, 2], [], [])
    for test in (rc.lm_test, rc.robust_lm_test):
        assert test(too_short, 4)[2] < 0.001 and test(right, 4)[2] > 0.01, test.__name__


def test_robust_lm_keeps_its_size_when_the_variance_changes():
    rng = np.random.default_rng(21)
    rejections, reps = {"standard": 0, "robust": 0}, 60
    for _ in range(reps):  # no autocorrelation left, residual variance x9 in the last quarter
        e = rng.standard_normal((2000, 3))
        e[1500:] *= 3
        y = np.zeros_like(e)
        for t in range(1, len(y)):
            y[t] = 0.5 * y[t - 1] + e[t]
        model = lag_selection.fit(pd.DataFrame(y, columns=["a", "b", "c"]), ["a", "b", "c"], [1], [], [])
        rejections["standard"] += rc.lm_test(model, 4)[2] < 0.05
        rejections["robust"] += rc.robust_lm_test(model, 4)[2] < 0.05
    assert rejections["robust"] / reps < 0.15 and rejections["standard"] / reps > 0.4, rejections


def test_arch_lm_matches_statsmodels():
    from statsmodels.stats.diagnostic import het_arch

    rng = np.random.default_rng(13)
    u = rng.standard_normal(3000) * np.repeat([1.0, 2.0, 1.0], 1000)  # variance changes over time
    stat, p = rc.arch_lm_test(u, 6)
    with warnings.catch_warnings():  # statsmodels warns about its own internal call
        warnings.simplefilter("ignore", FutureWarning)
        ref = het_arch(u, nlags=6)
    assert np.isclose(stat, ref[0]) and np.isclose(p, ref[1]) and p < 0.001


def test_lagged_correlation_within_selected_hours():
    rng = np.random.default_rng(16)
    x = rng.standard_normal(20000)
    for t in range(5, 10000):  # first half: correlated with 5 hours earlier; second half: white noise
        x[t] += 0.8 * x[t - 5]
    grid = x[:, None] - x.mean()
    first = np.arange(len(x)) < 10000
    assert abs(rc._lagged_correlation(grid, 5, first)[0, 0] - 0.8) < 0.05  # x_t = 0.8 x_(t-5) + e_t
    assert abs(rc._lagged_correlation(grid, 5, ~first)[0, 0]) < 0.05


def test_stability_matches_statsmodels_roots():
    dz = _simulated_var({1: A1, 2: A2})
    model = lag_selection.fit(dz, ["a", "b", "c"], [1, 2], [], [])
    ref = _statsmodels_var(dz, 2)
    assert np.isclose(rc.companion_max_modulus(model), 1 / np.abs(ref.roots).min())
    assert rc.companion_max_modulus(model) < 1


# --- VARX ----------------------------------------------------------------------------
def test_impulse_responses_match_statsmodels():
    dz = _simulated_var({1: A1, 2: A2})
    model = lag_selection.fit(dz, ["a", "b", "c"], [1, 2], [], [])
    ref = _statsmodels_var(dz, 2)
    A = lag_selection.lag_matrices(model)
    assert np.allclose(VARX.ma_coefficients(A, 10), ref.ma_rep(10))
    assert np.allclose(VARX.impulse_responses(A, ref.sigma_u, 10), ref.irf(10).orth_irfs)


def test_another_cholesky_order_equals_refitting_in_that_order():
    dz = _simulated_var({1: A1, 2: A2})
    model = lag_selection.fit(dz, ["a", "b", "c"], [1, 2], [], [])
    reordered = lag_selection.fit(dz, ["c", "a", "b"], [1, 2], [], [])
    k = np.array([2, 0, 1])  # positions of c, a, b in the first model
    theta = VARX.impulse_responses(lag_selection.lag_matrices(model), model["sigma"], 10, k)
    expected = VARX.impulse_responses(lag_selection.lag_matrices(reordered), reordered["sigma"], 10)
    assert np.allclose(theta[:, k[:, None], k], expected)
    assert np.allclose(VARX.impulse_responses(lag_selection.lag_matrices(model), model["sigma"], 10, [0, 1, 2]),
                       VARX.impulse_responses(lag_selection.lag_matrices(model), model["sigma"], 10))


def test_band_of_another_order_is_zero_where_that_order_rules_out_a_same_hour_response():
    dz = _simulated_var({1: A1, 2: A2})
    model = lag_selection.fit(dz, ["a", "b", "c"], [1, 2], [], [])
    coefs, sigmas = VARX.bootstrap_draws(model, 50, 99, np.random.default_rng(18))
    A_draws = np.array([lag_selection.lag_matrices(model, c) for c in coefs])
    lower, upper = VARX.response_band(A_draws, sigmas, 10, 0.95, [2, 0, 1])  # c first
    assert np.all(lower[0, 2, :2] == 0) and np.all(upper[0, 2, :2] == 0)  # a and b cannot move c within the hour
    assert np.all(lower[1, 2, :2] < upper[1, 2, :2])  # one hour later they can


def test_granger_wald_matches_statsmodels_and_the_bootstrap_separates_causes():
    import statsmodels.api as sm

    dz = _simulated_var({1: A1, 2: A2})  # b causes a (A1[0, 1] = 0.1); c does not (A1[0, 2] = A2[0, 2] = 0)
    model = lag_selection.fit(dz, ["a", "b", "c"], [1, 2], [], [])
    XtX_inv = np.linalg.inv(model["X"].T @ model["X"])
    idx = [model["names"].index(f"L{lag}.b") for lag in (1, 2)]
    y = model["resid"][:, 0] + model["X"] @ model["coef"][:, 0]  # equation of a
    ref = sm.OLS(y, model["X"]).fit(cov_type="HC0").wald_test(np.eye(model["X"].shape[1])[idx], use_f=False,
                                                                scalar=True)
    rng = np.random.default_rng(17)
    W, df, p = VARX.granger_test(model, XtX_inv, "b", "a", 24, 199, rng)
    assert df == 2 and np.isclose(W, float(np.squeeze(ref.statistic))) and p < 0.01
    assert VARX.granger_test(model, XtX_inv, "c", "a", 24, 199, rng)[2] > 0.05


def test_block_wild_bootstrap_reproduces_the_block_covariance():
    dz = _simulated_var({1: A1})
    model = lag_selection.fit(dz, ["a", "b", "c"], [1], [], [])
    window = 50
    coefs, _ = VARX.bootstrap_draws(model, window, 4000, np.random.default_rng(14))
    X, u = model["X"], model["resid"][:, 0]
    block = np.flatnonzero(model["ok"]) // window
    g = np.array([X[block == b].T @ u[block == b] for b in np.unique(block)])  # Σ_t x_t u_t per block
    XtX_inv = np.linalg.inv(X.T @ X)
    expected = np.sqrt(np.diag(XtX_inv @ g.T @ g @ XtX_inv))
    assert np.allclose(coefs[:, :, 0].mean(axis=0), model["coef"][:, 0], atol=0.1 * expected.max())
    assert np.allclose(coefs[:, :, 0].std(axis=0), expected, rtol=0.05)


def test_robustness_structures_follow_the_criteria():
    s = VARX.robustness_structures({"p": 25, "BIC": 2, "HQ": 3, "AIC": 25}, [*range(1, 25), 48], [167, 168])
    assert s["BIC order"] == [1, 2] and s["HQ order"] == [1, 2, 3] and s["literature"][-1] == 48
    assert s["weekly lags"] == [*range(1, 26), 167, 168]
    assert lag_selection.lag_ranges(s["literature"]) == "lags 1-24, 48"


def test_block_wild_bootstrap_varies_the_residual_covariance_like_a_mean():
    dz = _simulated_var({1: A1})
    model = lag_selection.fit(dz, ["a", "b", "c"], [1], [], [])
    window = 50
    _, sigmas = VARX.bootstrap_draws(model, window, 4000, np.random.default_rng(18))
    u2 = model["resid"][:, 0] ** 2 - model["sigma"][0, 0]
    block = np.flatnonzero(model["ok"]) // window
    expected = np.sqrt(sum(u2[block == b].sum() ** 2 for b in np.unique(block))) / len(u2)  # s.d. of a block mean
    assert abs(sigmas[:, 0, 0].mean() - model["sigma"][0, 0]) < 0.1 * expected
    assert abs(sigmas[:, 0, 0].std() / expected - 1) < 0.05


# --- web dashboard -------------------------------------------------------------------
def test_dashboard_data_match_the_dataframe():
    from common import zone_frame
    from web import build as web

    df = _dataframe()
    spec = building.make_spec(["x_da_id_spread", "c_wind_total_err"], ["da_flow_nl_net_export_mw", "fe_hour"])
    df = df[["datetime_utc", "bidding_zone", *spec.columns]]
    records = {r["id"]: r for r in web.variables(df, spec)}
    assert all(r["label"] and r["sources"] for r in records.values())
    assert records["da_flow_nl_net_export_mw"]["zones"] == ["DK1"]          # no Netherlands border in DK2
    assert records["fe_hour"]["calendar"] and not records["fe_hour"]["zones"]
    assert len(records["x_da_id_spread"]["sources"]) >= 2                   # day-ahead and intraday data
    s = web.series(df, "c_wind_total_err", ["DK1", "DK2"])
    for zone in ("DK1", "DK2"):
        dz = zone_frame(df, zone)
        assert s["t0_ms"] == int(dz["datetime_utc"].iloc[0].timestamp() * 1000) and s["step_ms"] == 3_600_000
        shown, original = np.array(s["values"][zone], dtype=float), dz["c_wind_total_err"].to_numpy()
        assert len(shown) == len(original) and np.array_equal(np.isnan(shown), np.isnan(original))
        assert np.nanmax(np.abs(shown - original)) <= 0.0005 + 1e-9  # rounded to 3 decimals, nothing else


def test_dashboard_reads_the_test_results():
    from common import PLOTS_DIR
    from web import build as web

    results = web.tests(PLOTS_DIR / "baseline_2025")
    if results["checks"] is None:
        raise Skip("residual_checks not run")
    acf = pd.read_csv(PLOTS_DIR / "baseline_2025" / "residual_checks" / "autocorrelation.csv")
    assert len(results["acf"]) == acf.groupby(["zone", "system", "equation"]).ngroups
    first = results["acf"][0]
    expected = acf[(acf["zone"] == first["zone"]) & (acf["system"] == first["system"])
                   & (acf["equation"] == first["equation"])]["r"].round(4).tolist()
    assert first["r"] == expected
    assert all(v is None or isinstance(v, (int, float, str)) for row in results["checks"] for v in row.values())
    irf_path = PLOTS_DIR / "baseline_2025" / "varx" / "impulse_responses.csv"
    if irf_path.exists():  # one array per (zone, system, response, shock); other lag structures, other orders with band
        irf = pd.read_csv(irf_path)
        grouped = web.results(PLOTS_DIR / "baseline_2025", {"irf": "varx/impulse_responses.csv"})["irf"]
        r = grouped[-1]
        g = irf[(irf["zone"] == r["zone"]) & (irf["system"] == r["system"]) & (irf["response"] == r["response"])
                & (irf["shock"] == r["shock"])]
        assert r["estimate"] == g["estimate"].round(4).tolist() and r["upper"] == g["upper"].round(4).tolist()
        assert set(r["robust"]) | set(r["orders"]) == {c.removeprefix("estimate_").replace("_", " ")
                                                       for c in irf if c.startswith("estimate_")}
        assert set(r["orders"]) == {c.removeprefix("lower_").replace("_", " ") for c in irf if c.startswith("lower_")}
        for name, o in r["orders"].items():
            col = name.replace(" ", "_")
            assert o["lower"] == g[f"lower_{col}"].round(4).tolist() and o["estimate"] == g[f"estimate_{col}"].round(4).tolist()


def test_dashboard_reads_the_shocks_and_breaks():
    from common import PLOTS_DIR
    from web import build as web

    hyp = web.hypothesis(PLOTS_DIR / "baseline_2025")
    if hyp["events"] is None:
        raise Skip("shocks_and_breaks not run")
    events = pd.read_csv(PLOTS_DIR / "baseline_2025" / "shocks_and_breaks" / "event_study.csv")
    assert len(hyp["events"]) == events.groupby(["zone", "error", "spread", "sign"]).ngroups
    r = hyp["events"][0]
    g = events[(events["zone"] == r["zone"]) & (events["error"] == r["error"]) & (events["spread"] == r["spread"])
               & (events["sign"] == r["sign"])]
    assert r["h"] == g["h"].tolist() and r["mean"] == [None if pd.isna(v) else round(v, 4) for v in g["mean"]]
    shown = {x["error"] for x in hyp["hypothesis"]} | {x["spread"] for x in hyp["hypothesis"]}
    assert hyp["breaks"] and {b["column"] for b in hyp["breaks"] + hyp["segments"]} <= shown
    assert all(s["sign"] in (1, -1) and s["hours"] >= 1 for s in hyp["shocks"])


# --- forecast errors -----------------------------------------------------------------
def test_forecast_error_numbers_on_a_known_series():
    hours = pd.date_range("2025-01-01", periods=10, freq="h", tz="Europe/Copenhagen")
    e = pd.Series([1, 2, 3, -1, -1, 0, 5, np.nan, -2, -2], index=hours, dtype=float)
    runs = fe.sign_runs(e)  # a 0 or a missing hour ends a run
    assert runs["length"].tolist() == [3, 2, 1, 2] and runs["sign"].tolist() == [1, -1, 1, -1]
    d = fe.describe(e, 0.95)
    assert np.isclose(d["same_sign_share"], 4 / 7)  # 7 pairs of observed hours, 4 with the same sign
    assert np.isclose(d["over_share"], 4 / 9) and np.isclose(d["under_share"], 4 / 9)
    assert d["longest_run"] == 3 and d["longest_run_sign"] == 1 and d["longest_run_start"] == "2025-01-01 00:00"
    assert d["median_run_of_hour"] == 2  # the hours' run lengths: 3, 3, 3, 2, 2, 1, 2, 2


def test_spread_means_by_the_sign_of_large_errors():
    e = pd.Series([0, 10, -10, 9, 2, 3, 4, 5, 6, 7.0])  # large: |e| above its 0.7 quantile (7.6) -> hours 1, 2, 3
    s = pd.Series([0, -20, 30, -10, 1, 1, 1, 1, 1, 6.0])
    groups = {g["group"]: g for g in es.by_sign(e, s, 0.7)}
    assert (groups["over"]["hours"], groups["under"]["hours"], groups["all"]["hours"]) == (2, 1, 10)
    assert np.isclose(groups["over"]["mean"], (-20 - 10) / 2) and np.isclose(groups["under"]["mean"], 30)
    assert np.isclose(groups["all"]["mean"], s.mean())


def test_lag_views_on_a_known_series():
    e = pd.Series([0, 0, 5, 6, 0, 0, -5, 0, 0, 0, 5, 0.0])  # runs with |e| > 4: over at 2-3 and 10, under at 6
    s = pd.Series([0, 0, 0, -10, 0, 0, 0, 20, 0, 0, 0, -30.0])
    around = pd.DataFrame(es.around_runs(e, s, 4, before=1, after=1))
    over = around[around["sign"] == 1].set_index("h")
    assert over["runs"].iloc[0] == 2 and over.loc[1, "mean"] == -20 and over.loc[0, "mean"] == 0  # (-10 - 30) / 2
    assert around[(around["sign"] == -1) & (around["h"] == 1)]["mean"].iloc[0] == 20
    corr = {r["lag"]: r for r in es.lagged_correlation(e, s, [0, 1])}
    assert np.isclose(corr[1]["corr"], e.corr(s.shift(-1))) and corr[1]["pairs"] == 11
    x = pd.Series(np.arange(20.0))
    t = pd.DataFrame(es.tenths(x, x * 2, [0, 1]))
    assert sorted(t["tenth"].unique()) == list(range(1, 11)) and (t[t["lag"] == 0]["hours"] == 2).all()
    first = t[(t["lag"] == 0) & (t["tenth"] == 1)].iloc[0]
    assert first["error_mean"] == 0.5 and first["mean"] == 1.0  # hours 0 and 1: spread 0 and 2
    assert t[(t["lag"] == 1) & (t["tenth"] == 1)].iloc[0]["mean"] == 3.0  # one hour later: 2 and 4


# --- shocks and breaks ---------------------------------------------------------------
def test_shock_runs_split_at_gaps_and_sign_changes():
    z = np.array([0, 4, 5, 0, -4, -4, 4, 0, np.nan, 4, 2])
    assert sb.shock_runs(z, 3.0) == [(1, 2, 1), (4, 5, -1), (6, 6, 1), (9, 9, 1)]


def test_regime_scores_standardise_within_each_regime():
    hours = pd.date_range("2025-03-10", periods=96, freq="h", tz="Europe/Copenhagen")
    rng = np.random.default_rng(3)
    e = pd.Series(np.r_[rng.standard_normal(48), 10 * rng.standard_normal(48)], index=hours)
    e.iloc[10], e.iloc[60] = 6.0, 20.0  # extreme in the calm regime; ordinary in the volatile one
    scores = sb.regime_scores(e, [{"date": pd.Timestamp("2025-03-12")}])
    assert scores["regime"].tolist() == [0] * 48 + [1] * 48
    for k in (0, 1):
        part = e[scores["regime"] == k]
        mad = 1.4826 * (part - part.median()).abs().median()
        assert np.allclose(scores.loc[scores["regime"] == k, "z"], (part - part.median()) / mad)
    assert abs(scores["z"].iloc[10]) > 3 > abs(scores["z"].iloc[60])


def test_event_study_recovers_a_known_response():
    d = np.zeros(200)
    onsets = np.array([20, 60, 120])
    d[onsets + 2] = [4.0, 5.0, 6.0]
    study = sb.event_study(d, onsets, before=3, after=5)
    assert study["h"].tolist() == list(range(-3, 6)) and study["n"].tolist() == [3] * 9
    assert np.isclose(study.loc[study["h"] == 2, "mean"].iloc[0], 5.0)
    assert np.allclose(study.loc[study["h"] != 2, "mean"], 0.0)
    half = 1.96 * np.std([4.0, 5.0, 6.0], ddof=1) / np.sqrt(3)
    assert np.isclose(study.loc[study["h"] == 2, "upper"].iloc[0], 5.0 + half)


def test_deviation_removes_the_normal_level_of_each_hour():
    hours = pd.date_range("2025-01-01", periods=24 * 20, freq="h", tz="Europe/Copenhagen")
    spread = pd.Series(np.tile(np.arange(24.0), 20), index=hours)  # the spread is its hour of the day
    calm = np.ones(len(spread), dtype=bool)
    calm[::7] = False
    spread.iloc[::7] += 100  # shock hours: far from normal, but left out of the normal level
    d = sb.deviation(spread, calm)
    assert np.allclose(d[calm], 0.0) and np.allclose(d[~calm], 100.0)


def test_vectorised_cusum_matches_a_direct_computation():
    x = np.random.default_rng(6).standard_normal(150).cumsum() * 0.1 + np.random.default_rng(7).standard_normal(150)
    stat, k = sb._cusum(x[None, :], 20)
    cusum = np.abs(np.cumsum(x - x.mean()))[:-1]
    k_ref = int(np.argmax(cusum[19:150 - 20])) + 20
    resid = np.concatenate([x[:k_ref] - x[:k_ref].mean(), x[k_ref:] - x[k_ref:].mean()])
    e = resid - resid.mean()
    rho = np.clip((e[1:] @ e[:-1]) / (e[:-1] @ e[:-1]), -0.97, 0.97)
    bw = min(int(1.1447 * (4 * rho ** 2 / ((1 - rho) ** 2 * (1 + rho) ** 2) * 150) ** (1 / 3)), 149)
    lrv = e @ e / 150 + sum(2 * (1 - j / (bw + 1)) * (e[j:] @ e[:-j]) / 150 for j in range(1, bw + 1))
    assert k[0] == k_ref and np.isclose(stat[0], cusum[k_ref - 1] / np.sqrt(150 * lrv))


def test_a_mean_shift_is_found_and_noise_gives_no_break():
    rng = np.random.default_rng(11)
    noise = rng.standard_normal(200)
    shifted = noise + np.r_[np.zeros(100), np.full(100, 2.0)]
    breaks = sb.seeded_segmentation(shifted, 30, 0.01)
    assert len(breaks) == 1 and abs(breaks[0]["index"] - 100) <= 3, breaks
    assert sb.seeded_segmentation(noise, 30, 0.01) == []


# ---------------------------------------------------------------------------------------
def run_all() -> bool:
    tests = [(n, f) for n, f in globals().items() if n.startswith("test_") and callable(f)]
    passed = failed = skipped = 0
    for name, func in tests:
        t0 = time.time()
        try:
            func()
            passed += 1
            print(f"  PASSED   {name} ({time.time() - t0:.1f}s)")
        except Skip as reason:
            skipped += 1
            print(f"  SKIPPED  {name} ({reason})")
        except Exception:
            failed += 1
            print(f"  FAILED   {name}\n{traceback.format_exc()}")
    print(f"\n{passed} passed, {failed} failed, {skipped} skipped")
    return failed == 0


if __name__ == "__main__":
    sys.exit(0 if run_all() else 1)
