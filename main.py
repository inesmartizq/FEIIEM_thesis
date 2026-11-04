"""
main.py — single entry point of the pipeline.

A dataframe is defined by its ENDOGENOUS and EXOGENOUS variables (DATAFRAMES
below). Every column they are computed from is added automatically as an
INPUT (src/dataframe/building.py), and every step adapts to the columns:
change the lists and the whole pipeline follows.

Code layout (src/):
    dataframe/   building.py, documentation.py, visualisation.py, correlation.py
    hypothesis/  forecast_errors.py (step 1: what the forecast errors look like),
                 error_spreads.py (step 2: what the forecast errors do to the price spreads),
                 shocks_and_breaks.py (the shocks of the forecast errors, the breaks, the spreads around a shock)
    VAR_tests/   stationarity.py, lag_selection.py, residual_checks.py
    models/      VARX.py (the model, Granger causality, impulse responses)
    web/         build.py + assets/ (the dashboard for the supervisors)
    latex_outputs.py  the figures and tables of the LaTeX thesis
    imports/     download scripts for the raw data (not run by main.py)
    common.py    helpers shared by all steps

For every dataframe, the steps run in this order:
    build              data/dataframes/<name>.csv
    documentation      data/dataframes/documentation/<name>_documentation.xlsx
    visualisation      plots/<name>/{timeseries,distributions,seasonals,stats}/<role>/<column>.png
    correlation        plots/<name>/correlation/
    forecast_errors    plots/<name>/forecast_errors/
    error_spreads      plots/<name>/error_spreads/
    shocks_and_breaks  plots/<name>/shocks_and_breaks/
    stationarity       plots/<name>/stationarity_tests/   (endogenous variables only)
    lag_selection      plots/<name>/lag_selection/
    residual_checks    plots/<name>/residual_checks/      (the VARX with the chosen lag order)
    varx               plots/<name>/varx/                 (the VARX: Granger causality, impulse responses)
    web                web/<name>/index.html              (the dashboard: open it in a browser)
    latex              latex_outputs/<name>/              (the figures and tables used in the LaTeX thesis)

Usage (from the project root):
    python main.py                                  # every dataframe in DATAFRAMES
    python main.py baseline_2025                    # only the named one(s)
    python main.py baseline_2025 --only web         # only the named step(s), on the existing outputs
"""

import os
import shutil
import sys
import time
from pathlib import Path

# One CPU thread for the numerical libraries. The pipeline's linear algebra is many small
# problems (e.g. 1,000 simulated ADF regressions per series), for which multithreading is
# several times slower, not faster. Must be set before numpy is first imported.
for _var in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_var, "1")

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

import latex_outputs  # noqa: E402
from common import PLOTS_DIR  # noqa: E402
from dataframe import building, correlation, visualisation  # noqa: E402
from dataframe.documentation import write_documentation  # noqa: E402
from hypothesis import error_spreads, forecast_errors, shocks_and_breaks  # noqa: E402
from models import VARX  # noqa: E402
from VAR_tests import lag_selection, residual_checks, stationarity  # noqa: E402
from web import build as web  # noqa: E402

# ---------------------------------------------------------------------------
# DATAFRAMES — one entry per dataframe.
#   start / end   inclusive delivery dates (UTC), "YYYY-MM-DD"
#   areas         bidding zones
#   endogenous    explained by the model (own equation)
#   exogenous     taken as given; fe_* columns are calendar dummies
# Every column name must be a SOURCES column or a DERIVED_FEATURES entry of
# src/dataframe/building.py (an unknown name stops the run with a message).
# ---------------------------------------------------------------------------
CROSS_BORDER_FLOWS = [f"da_flow_{code}_net_export_mw" for code in building.FLOW_COUNTERPARTS]
HYDRO_DEVIATIONS = ["c_reservoir_deviation_pct_no", "c_reservoir_deviation_pct_se", "c_reservoir_deviation_pct_fi"]
SPREADS = ["x_da_id_spread", "x_id_bal_spread", "x_da_bal_spread"]

BASELINE = {  # the literature baseline (Spodniak et al. 2019)
    "endogenous": [
        *SPREADS,                                               # price spreads
        "c_wind_total_err",                                     # wind forecast error
        "c_load_err",                                           # demand forecast error
    ],
    "exogenous": [
        "c_wind_total_actual_mw_change_1_lag_1",  # wind ramping, previous hour (see the residual-check section)
        *HYDRO_DEVIATIONS,                  # hydro conditions
        *CROSS_BORDER_FLOWS,                # cross-border flows
        "fe_hour", "fe_month_of_sample",    # diurnal and seasonal patterns (dummies)
    ],
}

# THE HYPOTHESIS: the forecast errors move the price spreads. For each forecast error, the expected sign of
# each spread's response to an over-forecast (error > 0); an under-forecast has the opposite sign.
#   less wind than planned:   system short -> intraday and balancing prices up   -> P_DA - P_ID, P_ID - P_BAL,
#                             P_DA - P_BAL down
#   less demand than planned: system long  -> intraday and balancing prices down -> the spreads up
# Tested model-free in the shocks_and_breaks step; on the dashboard, the VARX results page compares the
# same-hour impulse responses with these signs.
EXPECTED_SIGNS = {
    "c_wind_total_err": {"x_da_id_spread": -1, "x_id_bal_spread": -1, "x_da_bal_spread": -1},
    "c_load_err": {"x_da_id_spread": +1, "x_id_bal_spread": +1, "x_da_bal_spread": +1},
}

DATAFRAMES = {
    "baseline_2025": {"start": "2025-01-01", "end": "2025-12-31", "areas": ["DK1", "DK2"], **BASELINE},
    # "baseline_2022_2025": {"start": "2022-01-01", "end": "2025-12-31", "areas": ["DK1", "DK2"], **BASELINE},
}

# Which steps to run. With "build" off, the existing data/dataframes/<name>.csv is used.
STEPS = {
    "build": True,
    "documentation": True,
    "visualisation": True,
    "correlation": True,
    "forecast_errors": True,
    "error_spreads": True,
    "shocks_and_breaks": True,
    "stationarity": True,
    "lag_selection": True,
    "residual_checks": True,
    "varx": True,
    "web": True,
    "latex": True,
}

# The analysis steps: module (with run() and FOLDERS) and settings. Before a
# step runs, its folders under plots/<name>/ are deleted, so no plot of a
# column that is no longer in the dataframe is left behind.
# LITERATURE_LAGS: the lag structure of Spodniak et al. (2019), scored in lag_selection and a robustness model in varx.
# WEEKLY_LAGS: the hours around one and two weeks back, used to check the weekly residual pattern
# (residual_checks) and as a robustness model (varx).
LITERATURE_LAGS = [*range(1, 25), 48]
LARGE_QUANTILE = 0.95  # the hypothesis: a "large" forecast error is above the 95th percentile of the zone's hours
WEEKLY_LAGS = [167, 168, 169, 335, 336, 337]
# LATEX_FIGURES: the plots used in the LaTeX thesis (paths under plots/<name>/), copied to latex_outputs/<name>/
LATEX_FIGURES = ["lag_selection/lag_selection.png", "residual_checks/residual_autocorrelation.png",
                 "residual_checks/ramp_timing.png", "varx/irf_DK1.png", "varx/irf_DK2.png"]
ANALYSES = {
    "visualisation": (visualisation, {}),
    "correlation": (correlation, {"method": "pearson", "max_lag": 168}),
    # large error: |e| above its LARGE_QUANTILE (per zone and error), in step 1 and step 2
    "forecast_errors": (forecast_errors, {"large_quantile": LARGE_QUANTILE}),
    # lags: the spread from `before` to `after` hours around a run of large errors; corr(e_t, s_t+k) for k in
    # correlation_lags (from, to); the error's tenths against the spread k hours later for k in tenth_lags.
    # Intervals: block bootstrap, blocks of block_hours (two weeks, as in varx), `draws` draws
    "error_spreads": (error_spreads, {"quantile": LARGE_QUANTILE, "before": 12, "after": 24, "correlation_lags": (-24, 48),
                                      "tenth_lags": (0, 1, 2, 3, 6, 12, 24), "block_hours": 336, "draws": 1000,
                                      "seed": 2025}),
    # shocks: |robust z| > z_threshold within the regimes between variance breaks; the spreads are followed
    # from `before` hours before to `after` hours after each shock
    "shocks_and_breaks": (shocks_and_breaks, {"alpha": 0.01, "min_segment_days": 30, "expected_signs": EXPECTED_SIGNS,
                                              "z_threshold": 3.0, "before": 6, "after": 24}),
    "stationarity": (stationarity, {"alpha": 0.05, "kpss_draws": 5000, "adf_draws": 1000, "seed": 2025}),
    "lag_selection": (lag_selection, {"criterion": "aic", "max_lag": 48, "literature_lags": LITERATURE_LAGS}),
    "residual_checks": (residual_checks, {"lm_lags": 24, "arch_lags": 24, "acf_lags": 336, "alpha": 0.05,
                                          "weekly_lags": WEEKLY_LAGS,
                                          "weekly_calendar": ["fe_hour_of_week", "fe_month_of_sample"],
                                          # ramp_check: (forecast error, same-hour ramp): why the ramp enters one hour late
                                          "ramp_check": ("c_wind_total_err", "c_wind_total_actual_mw_change_1")}),
    # shock_order: the Cholesky order (listed variables first, then the rest of each model: the spread);
    # other_orders: other Cholesky orders, given like shock_order, as robustness for the impulse responses;
    # window_hours: the block length of the bootstrap (Granger p-values and response bands): residual
    # dependence within a block is kept
    "varx": (VARX, {"shock_order": ["c_wind_total_err", "c_load_err"],
                    "other_orders": {"spread first": [*SPREADS, "c_wind_total_err", "c_load_err"]},
                    "horizon": 48, "window_hours": 336, "draws": 1000, "band": 0.95, "alpha": 0.05, "seed": 2025,
                    "literature_lags": LITERATURE_LAGS, "weekly_lags": WEEKLY_LAGS}),
    "web": (web, {"title": "Forecast errors and price spreads in DK1 and DK2", "expected_signs": EXPECTED_SIGNS}),
    # descriptive: file name of the descriptive-statistics table of the endogenous variables (appendix; "" = none)
    "latex": (latex_outputs, {"figures": LATEX_FIGURES, "descriptive": "descriptive_statistics.tex"}),
}


def _banner(text: str):
    print("\n" + "=" * 78 + f"\n{text}\n" + "=" * 78)


def run_pipeline(name: str, cfg: dict, only: list | None = None):
    """Runs the steps switched on in STEPS, or only the steps in `only` (whatever STEPS says)."""
    spec = building.make_spec(cfg["endogenous"], cfg["exogenous"])  # fails fast on an unknown column
    plot_dir = PLOTS_DIR / name
    steps = [s for s, on in STEPS.items() if (s in only if only else on)]
    t0 = time.time()

    def banner(step: str):
        _banner(f"[{name}] {steps.index(step) + 1}/{len(steps)} {step.upper()}")

    if "build" in steps:
        banner("build")
        df = building.create_dataframe(name, cfg["start"], cfg["end"], spec, cfg["areas"])
    else:
        df = building.load_dataframe(name, spec)

    if "documentation" in steps:
        banner("documentation")
        write_documentation(df, name, spec, building.DOCUMENTATION_DIR / f"{name}_documentation.xlsx",
                            settings={"requested period": f"{cfg['start']} to {cfg['end']}", "areas": cfg["areas"]})

    for step, (module, settings) in ANALYSES.items():
        if step in steps:
            banner(step)
            for folder in module.FOLDERS:
                shutil.rmtree(plot_dir / folder, ignore_errors=True)
            module.run(df, spec, plot_dir, **settings)

    print(f"\n[{name}] finished in {time.time() - t0:.0f}s")


def main():
    args = sys.argv[1:]
    only = args[args.index("--only") + 1:] if "--only" in args else None
    names = (args[:args.index("--only")] if only is not None else args) or list(DATAFRAMES)
    unknown = [n for n in names if n not in DATAFRAMES]
    if unknown:
        raise SystemExit(f"Unknown dataframe(s) {unknown}. Defined in DATAFRAMES: {list(DATAFRAMES)}")
    if only is not None and (not only or set(only) - set(STEPS)):
        raise SystemExit(f"--only needs step names from STEPS: {list(STEPS)}")
    for name in names:
        run_pipeline(name, DATAFRAMES[name], only)


if __name__ == "__main__":
    main()
