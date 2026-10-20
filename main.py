"""
main.py — single entry point for the dataframe pipeline.

For every dataframe in DATAFRAMES below, runs these steps IN ORDER:
    1. build          src/dataframe_building.py
                      -> data/dataframes/<name>.csv
    2. documentation  src/dataframe_documentation.py
                      -> data/dataframes/documentation/<name>_documentation.xlsx
    3. visualisation  src/visualisation/visualize_dataframe.py
                      -> plots/<name>/{missingness,timeseries,distributions,seasonals,stats}/
    4. correlation    src/statsistics/correlation_analysis.py
                      -> plots/<name>/correlation/
    5. structural_breaks  src/statsistics/structural_breaks.py
                      -> plots/<name>/structural_breaks/ (mean/variance breaks of DA/ID/balancing prices)
    6. var_tests      src/model/stationarity_lag_selection.py
                      -> plots/<name>/var_tests/ (stationarity tests and lag selection only —
                         no VAR is estimated; model_spec dataframes)
    7. summary        src/analysis_summary.py
                      -> plots/<name>/ANALYSIS_SUMMARY.md (what was built/checked/plotted,
                         to paste into another AI so it does not repeat the work)

TO CREATE A NEW DATAFRAME: add one entry to DATAFRAMES — a name (also the
output file/folder name), a date range, the markets to include and the
bidding zones. Selecting a market pulls in all of its source columns plus
every derived feature whose inputs are present: e.g. the DA-ID spread
features only appear when both "day_ahead" and "intraday" are selected.

Usage (from the project root):
    python main.py                  # every dataframe in DATAFRAMES
    python main.py baseline_2022_2025   # only the named one(s)
"""

import shutil
import sys
import time
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent
SRC_DIR = PROJECT_ROOT / "src"
for _p in (SRC_DIR, SRC_DIR / "visualisation", SRC_DIR / "statsistics", SRC_DIR / "model"):
    sys.path.insert(0, str(_p))

import dataframe_building as building  # noqa: E402
from dataframe_documentation import write_documentation_excel  # noqa: E402
from visualize_dataframe import OUTPUT_SUBDIRS as VISUALISATION_SUBDIRS, visualize  # noqa: E402
from correlation_analysis import run_correlation_analysis  # noqa: E402
from structural_breaks import run_structural_breaks  # noqa: E402
from stationarity_lag_selection import run_stationarity_and_lag_selection  # noqa: E402
from analysis_utils import PLOTS_DIR  # noqa: E402
from analysis_summary import write_analysis_summary  # noqa: E402
from model_specs import MODEL_SPECS, spec_columns  # noqa: E402

# ---------------------------------------------------------------------------
# DATAFRAMES — one entry per dataframe to create.
#   start / end - inclusive delivery dates (UTC), "YYYY-MM-DD".
#   markets     - any of: "day_ahead", "intraday", "balancing", "fundamentals"
#                 (fundamentals = load / wind / solar forecasts & actuals),
#                 or None for all of them.
#   areas       - bidding zones, e.g. ["DK1", "DK2"].
#   model_spec  - optional key of src/model_specs.py MODEL_SPECS: keep only
#                 that model's columns (variables + the inputs they're built
#                 from) and mark each column Endogenous / Exogenous / Input
#                 in the documentation workbook.
# ---------------------------------------------------------------------------
DATAFRAMES = {
    # The literature baseline (Spodniak et al. 2019) — the reference model
    # the thesis progresses from. Variables, roles, sources and deviations:
    # src/model_specs.py and the workbook's "model_variables" sheet.
    # ON HOLD (2025 is studied alone for now; uncomment to run it again —
    # its previous outputs in plots/baseline_2022_2025/ are kept as they are):
    # "baseline_2022_2025": {
    #     "start": "2022-01-01", "end": "2025-12-31",
    #     "markets": ["day_ahead", "intraday", "balancing", "fundamentals"],
    #     "areas": ["DK1", "DK2"],
    #     "model_spec": "spodniak2019_baseline",
    # },
    # Same baseline model, 2025 only (the year of the methods chapter).
    "baseline_2025": {
        "start": "2025-01-01", "end": "2025-12-31",
        "markets": ["day_ahead", "intraday", "balancing", "fundamentals"],
        "areas": ["DK1", "DK2"],
        "model_spec": "spodniak2019_baseline",
    },
    # Previous exploratory dataframe (all columns, 2025 only):
    # "df_2025": {
    #     "start": "2025-01-01", "end": "2025-12-31",
    #     "markets": None,
    #     "areas": ["DK1", "DK2"],
    # },
    # Examples:
    # "df_balancing_intraday_2025": {
    #     "start": "2025-01-01", "end": "2025-12-31",
    #     "markets": ["intraday", "balancing", "fundamentals"],
    #     "areas": ["DK1", "DK2"],
    # },
    # "df_2022_2025": {
    #     "start": "2022-01-01", "end": "2025-12-31",
    #     "markets": None,
    #     "areas": ["DK1", "DK2"],
    # },
}

# Which steps to run. Turning "build" off re-uses the existing
# data/dataframes/<name>.csv for the later steps.
STEPS = {
    "build": True,
    "documentation": True,
    "visualisation": True,
    "correlation": True,
    "structural_breaks": True,
    "var_tests": True,  # only for dataframes with a model_spec
    "summary": True,  # plots/<name>/ANALYSIS_SUMMARY.md, a handoff for another AI
}

VISUALISATION_SETTINGS = {
    "freq": "raw",  # time-series resolution: "raw" = hourly values; "D" = daily mean, "W" = weekly mean
    # Key features for plots/<name>/stats/ (std, variance, hourly and %
    # change). None = the default list in visualize_dataframe.py
    # (DEFAULT_STATS_FEATURES); columns not in the dataframe are skipped.
    "stats_features": None,
}

CORRELATION_SETTINGS = {
    "lags": [0, 1, 4, 24, 168],  # hours: same hour, 1 h, 4 h, day, week
    "method": "pearson",         # or "spearman"
    "min_abs_corr": 0.10,        # threshold for weak_columns.txt
}

# Mean / variance break detection on the DA, ID and balancing prices
# (CUSUM test with HAC long-run variance, binary segmentation; see
# src/statsistics/structural_breaks.py for the method).
# Stationarity tests and lag selection (src/model/stationarity_lag_selection.py),
# per zone and spread of the model spec: ADF / KPSS / PP, and AIC / BIC over lag
# structures. No VAR / VARX is estimated.
VAR_TEST_SETTINGS = {
    "start": None, "end": None,              # sub-period, e.g. "2025-01-01" / "2025-12-31"; None = whole dataframe
    "full_lags": list(range(1, 25)) + [48],  # literature lag structure (lags 1-24 + 48)
    "candidate_lags": [1, 2, 3, 4, 6, 12, 24, 48],  # contiguous orders compared by AIC / BIC
    "alpha": 0.05,
    # dataframes whose before / after stationarity tables use simulated critical values
    # after the calendar dummies (bootstrap, ~minutes): stationarity_lag_selection.run_calendar_check
    "calendar_check": ["baseline_2025"],
    "sensitivity": True,  # stationarity robustness: windows, KPSS bandwidths, calendar removed, alpha 1 % / 10 %
}

STRUCTURAL_BREAK_SETTINGS = {
    "alpha": 0.01,            # significance level per test
    "min_segment_days": 30,   # minimum days between two breaks
}

# Delete this dataframe's previous plots before regenerating them, so plots
# of columns/markets no longer in the dataframe don't linger next to the
# new ones. Only touches plots/<name>/ — never data or other dataframes.
CLEAN_OLD_PLOTS = True


def _banner(text: str):
    print("\n" + "=" * 78 + f"\n{text}\n" + "=" * 78)


def _load_existing(name: str) -> pd.DataFrame:
    path = building.OUTPUT_DIR / f"{name}.csv"
    if not path.exists():
        raise FileNotFoundError(f"STEPS['build'] is off but {path} doesn't exist — build it first.")
    df = pd.read_csv(path)
    df["datetime_utc"] = pd.to_datetime(df["datetime_utc"], utc=True)
    return df


def _clean_plots(name: str, step: str):
    plot_dir = PLOTS_DIR / name
    if step == "visualisation":
        # The visualisation subfolders, plus loose PNGs from the old flat
        # layout. Never correlation/ — that belongs to step 4.
        for png in plot_dir.glob("*.png"):
            png.unlink()
        for sub in VISUALISATION_SUBDIRS:
            shutil.rmtree(plot_dir / sub, ignore_errors=True)
    elif step in ("correlation", "structural_breaks", "var_tests"):
        shutil.rmtree(plot_dir / step, ignore_errors=True)


def run_pipeline(name: str, cfg: dict):
    markets, areas = cfg.get("markets"), cfg.get("areas", building.AREAS)
    building.sources_for_markets(markets)  # fail fast on a typo before anything runs
    spec = MODEL_SPECS[cfg["model_spec"]] if cfg.get("model_spec") else None
    t0 = time.time()

    _banner(f"[{name}] 1/7 BUILD")
    if STEPS["build"]:
        df = building.create_dataframe(name, cfg["start"], cfg["end"], markets=markets, areas=areas,
                                       columns=spec_columns(spec) if spec else None)
    else:
        print("  skipped (STEPS['build'] = False) — using the existing CSV")
        df = _load_existing(name)

    _banner(f"[{name}] 2/7 DOCUMENTATION")
    if STEPS["documentation"]:
        write_documentation_excel(
            df, name, building.DOCUMENTATION_DIR / f"{name}_documentation.xlsx",
            sources=building.SOURCES, derived=building.DERIVED_FEATURES, key=building.KEY,
            settings={"requested period": f"{cfg['start']} to {cfg['end']}",
                      "markets": markets or list(building.MARKETS), "areas": areas,
                      **({"model spec": cfg["model_spec"]} if spec else {})},
            model_spec=spec,
        )
    else:
        print("  skipped")

    _banner(f"[{name}] 3/7 VISUALISATION")
    if STEPS["visualisation"]:
        if CLEAN_OLD_PLOTS:
            _clean_plots(name, "visualisation")
        visualize(name, **VISUALISATION_SETTINGS, model_spec=spec)
    else:
        print("  skipped")

    _banner(f"[{name}] 4/7 CORRELATION ANALYSIS")
    if STEPS["correlation"]:
        if CLEAN_OLD_PLOTS:
            _clean_plots(name, "correlation")
        run_correlation_analysis(name, **CORRELATION_SETTINGS, model_spec=spec)
    else:
        print("  skipped")

    _banner(f"[{name}] 5/7 STRUCTURAL BREAKS")
    if STEPS["structural_breaks"]:
        if CLEAN_OLD_PLOTS:
            _clean_plots(name, "structural_breaks")
        run_structural_breaks(name, **STRUCTURAL_BREAK_SETTINGS)
    else:
        print("  skipped")

    _banner(f"[{name}] 6/7 VAR TESTS")
    if STEPS["var_tests"] and spec is not None:
        if CLEAN_OLD_PLOTS:
            _clean_plots(name, "var_tests")
        run_stationarity_and_lag_selection(name, spec, **VAR_TEST_SETTINGS)
    else:
        print("  skipped" + ("" if spec is not None else " (no model_spec for this dataframe)"))

    _banner(f"[{name}] 7/7 ANALYSIS SUMMARY")
    if STEPS["summary"]:
        write_analysis_summary(name, cfg, model_spec=spec)
    else:
        print("  skipped")

    print(f"\n[{name}] finished in {time.time() - t0:.0f}s")


def main():
    names = sys.argv[1:] or list(DATAFRAMES)
    unknown = [n for n in names if n not in DATAFRAMES]
    if unknown:
        raise SystemExit(f"Unknown dataframe(s) {unknown}. Defined in DATAFRAMES: {list(DATAFRAMES)}")
    for name in names:
        run_pipeline(name, DATAFRAMES[name])


if __name__ == "__main__":
    main()
