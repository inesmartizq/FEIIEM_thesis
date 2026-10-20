"""
Assembles the analysis-ready DataFrame(s) for the VAR thesis from the
processed, per-source CSVs already produced by:
    - import_balancing_pipeline.py     (mFRR, aFRR combined)
    - import_intraday_pipeline.py      (intraday)
    - import_da_pipeline.py            (day-ahead prices/volumes/flows, Nord Pool)
    - import_da_forecasts_pipeline.py  (production/consumption forecast vs actual)

DESIGN
------
Two registries drive everything: SOURCES (raw columns pulled in from
processed CSVs) and DERIVED_FEATURES (columns computed from columns already
in the merged DataFrame — from SOURCES or from each other). Adding a new
feature never touches the join logic, the grid construction, or the save
step:
    A) A feature that lives in a processed CSV as its own column:
       1. Have the processed CSV sitting in its folder.
       2. Add ONE entry to SOURCES below.
    B) A feature that's a COMBINATION of other features (a spread, a net
       value, a forecast error, a ratio):
       1. Add ONE entry to DERIVED_FEATURES below.
       DERIVED_FEATURES entries can depend on each other in ANY order —
       apply_derived_features() resolves dependencies automatically (see
       its docstring), so you never have to think about "what order do I
       list these in."
    C) A price-dynamics / volatility / cross-market-spread / physical-ramp
       feature: edit MARKET_PRICES, MARKET_SPREADS or PHYSICAL_VARIABILITY
       (below DERIVED_FEATURES) — those entries are generated in a loop.

RULE: if a quantity can be computed from other quantities you're already
pulling in, it belongs in DERIVED_FEATURES, not as a second, independently
computed SOURCES column. Carrying both a raw source's own precomputed total
AND the components that sum to it risks the two silently disagreeing
(rounding, a stale export, a units mismatch) — computing the total here
instead means there is exactly one source of truth for it.

BUILDING DIFFERENT DATAFRAMES: which dataframes get built (date range,
markets, zones) is configured in main.py at the project root, NOT here —
main.py calls create_dataframe() below and then runs documentation,
visualisation and correlation analysis on the result. MARKETS below maps
each market name main.py can use to its SOURCES entries; derived features
are included automatically whenever all their inputs are present (so a
cross-market spread only appears when both of its markets are selected).

Every source is loaded defensively: load_source() reads the file's actual
header and compares it against what this script expects. If a column you
configured in `rename` isn't actually in the file, it's reported loudly
instead of silently dropped — so a wrong guess about a source's column
names surfaces immediately, not three steps later in the VAR.

TIMEZONE NOTE (verified 2026-10-07): EVERY source here is genuinely UTC —
all Nord Pool feeds (day-ahead prices/volumes/flows, mFRR/imbalance,
intraday, Power System forecasts/actuals) and ENTSO-E/Energinet aFRR. The
raw Nord Pool responses say so themselves: delivery day 2025-03-01 (CET)
starts at "2025-02-28T23:00:00Z" in the mFRR, intraday, forecast AND
day-ahead files alike. Three independent data checks agree:
  - imbalance price == DA price in 99.7 % of no-regulation hours with the
    timestamps as delivered, vs 0.7 % after a -1 h shift;
  - intraday VWAP tracks the DA price best with no shift (r 0.975 vs 0.953);
  - solar output peaks at solar noon in UTC (~11 UTC in Denmark).
An earlier version shifted mFRR, intraday and forecasts by -1 h ("Nord Pool
CET fix"), based on a DST check that could not tell UTC from fixed CET; that
put those columns one hour early (row t held hour t+1). The
`nordpool_cet_fix` flag is kept for a genuinely mislabeled future source,
but is False for every current one — verify against raw data before ever
setting it: a wrong value silently shifts every timestamp of that source.

Usage: run main.py from the project root (this module is a library).
    pip install pandas openpyxl matplotlib
"""

import math
from pathlib import Path

import pandas as pd

# ----------------------- CONFIG -----------------------
PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
OUTPUT_DIR = PROJECT_ROOT / "data" / "dataframes"
# Documentation workbooks (<name>_documentation.xlsx: per-column metadata,
# coverage and distribution statistics -- see dataframe_documentation.py)
# go in their own subfolder, kept separate from the actual dataframe CSVs
# in OUTPUT_DIR -- these are a diagnostic side-output, not analysis-ready
# data, and mixing the two made the dataframes folder harder to scan.
DOCUMENTATION_DIR = OUTPUT_DIR / "documentation"

AREAS = ["DK1", "DK2"]

# Final key column names in every built DataFrame: full UTC date+time, and
# the bidding zone. Every source gets renamed onto these two, whatever the
# raw file calls them.
KEY = ["datetime_utc", "bidding_zone"]

# ---------------------------------------------------------------------------
# MARKETS — the names main.py uses to pick what goes into a dataframe,
# mapped to the SOURCES entries (below) that belong to each. A new SOURCES
# entry must be added to exactly one market here (checked at import).
# "fundamentals" = load / wind / solar forecasts and actuals: not a market
# you trade on, but the physical system data driving all three.
# ---------------------------------------------------------------------------
MARKETS = {
    "day_ahead": ["da_nordpool_prices", "da_nordpool_volumes", "da_nordpool_flows",
                  "da_nordpool_system_price"],
    "intraday": ["intraday"],
    "balancing": ["mfrr", "afrr"],
    "fundamentals": ["da_forecasts_and_actual", "reservoir"],
}

# ---------------------------------------------------------------------------
# SOURCE REGISTRY
#
# Each entry:
#   path       - CSV location (PROCESSED_DIR-relative, built below)
#   time_col   - the column in the source CSV holding the UTC timestamp
#   area_col   - the column in the source CSV holding the bidding zone
#   rename     - {source_column: final_feature_name}. Only columns listed
#                here are pulled into the merged DataFrame; anything else in
#                the source file is left behind. Final names follow your
#                naming convention: da_ / id_ / b_ / c_ prefixes.
#   value_map  - optional {final_feature_name: {raw_value: number}} to turn
#                a text column into a numeric one. Any non-empty value not
#                in the map is reported and becomes NaN.
#   fill_empty - optional {final_feature_name: value} for EMPTY cells in rows
#                the source does contain (only where an empty cell has a
#                verified meaning). Hours missing from the source stay NaN.
#   pivot_area - True for a file holding OTHER areas than the DK zones (one
#                row per hour per area, e.g. NO / SE / FI reservoirs): each
#                area becomes its own column '<source column>_<area>' (use
#                those names in `rename`), and the result is system_wide.
#   system_wide - True for a series with one value for the whole system
#                (e.g. the Nord Pool system price): it is copied to every
#                bidding zone instead of being matched on area_col.
#   nordpool_cet_fix - True if this source's "...UTC" column is actually
#                Nord Pool wall-clock CET/CEST mislabeled as UTC (see the
#                TIMEZONE NOTE in the module docstring). False/omitted for
#                genuinely-UTC sources (ENTSO-E/Energinet). Get this wrong
#                and every timestamp for that source is silently off by
#                1-2h — verify the true origin before setting it, don't
#                guess.
#
# TO ADD A NEW FEATURE LATER: add a new dict entry here. Nothing else in
# this file needs to change. But first ask: can this feature be computed
# from columns I'm already pulling in? If so, it belongs in DERIVED_FEATURES
# instead (see the module docstring).
# ---------------------------------------------------------------------------
SOURCES = {
    "mfrr": {
        # Nord Pool — "DeliveryStartUTC" is genuine UTC (see TIMEZONE NOTE:
        # imbalance price == DA price in 99.7 % of no-regulation hours only
        # without a shift).
        "path": PROCESSED_DIR / "mfrr" / "mfrr_DK1_DK2_2021_2025_MW.csv",
        "time_col": "DeliveryStartUTC",
        "area_col": "Area",
        "nordpool_cet_fix": False,
        "rename": {
            "AcceptedUpBidVolume_MW": "b_mfrr_accepted_up_mw",
            "AcceptedDownBidVolume_MW": "b_mfrr_accepted_down_mw",
            "ActivatedUpVolume_MW": "b_mfrr_activated_up_mw",
            "ActivatedDownVolume_MW": "b_mfrr_activated_down_mw",
            "UpPrice": "b_mfrr_up_price",
            "DownPrice": "b_mfrr_down_price",
            "ImbalancePrice": "b_imbalance_price",
            "DominatingDirection": "b_dominating_direction",
        },
        # Text -> number, so the column is usable in correlations / the VAR.
        # Empty -> 0 = no regulation: with correct (UTC) alignment, in empty
        # hours of 2022-2024 the imbalance price equals the DA price in
        # 99-100 % and mFRR activation is zero in 99-100 % of cases. 2025 is
        # less clean (40 % / 52 %), as hourly values there aggregate 15-min
        # regulation states — see the documentation workbook.
        "value_map": {
            "b_dominating_direction": {"Up": 1, "Down": -1},
        },
        "fill_empty": {
            "b_dominating_direction": 0,
        },
    },
    "intraday": {
        # Nord Pool — "DeliveryStartUTC" is genuine UTC (see TIMEZONE NOTE).
        "path": PROCESSED_DIR / "intraday" / "intraday_DK1_DK2_2021_2025.csv",
        "time_col": "DeliveryStartUTC",
        "area_col": "Area",
        "nordpool_cet_fix": False,
        "rename": {
            "HighPrice": "id_high_price",
            "LowPrice": "id_low_price",
            "OpenPrice": "id_open_price",
            "ClosePrice": "id_close_price",
            "VWAP": "id_vwap",
            "VWAP1H": "id_vwap_1h",
            "VWAP3H": "id_vwap_3h",
            "TransactionVolume_MWh": "id_transaction_volume_mwh",
            "BuyVolume_MWh": "id_buy_volume_mwh",
            "SellVolume_MWh": "id_sell_volume_mwh",
        },
    },
    "afrr": {
        # Using the single combined, stitched file (Energinet pre-PICASSO +
        # ENTSO-E post-PICASSO already merged into one continuous hourly
        # series) rather than the two raw per-source files.
        # Energinet (pre-PICASSO) + ENTSO-E (post-PICASSO), genuinely UTC —
        # no CET fix, confirmed. Header confirmed from a real run, so this
        # is hardcoded now rather than auto-detected via TIME_COL_CANDIDATES/
        # AREA_COL_CANDIDATES (those remain below as a fallback mechanism
        # for any future source whose header isn't pinned down yet).
        "path": PROCESSED_DIR / "afrr" / "afrr_DK1_DK2_2022_2025_hourly.csv",
        "time_col": "HourUTC",
        "area_col": "Area",
        "nordpool_cet_fix": False,
        "rename": {
            # NOTE: no _MW suffix in the real combined file's header
            # (confirmed from a real run's column listing) — unlike the
            # Offered/Unavailable columns below, which do have it.
            "aFRR_UpActivated": "b_afrr_activated_up_mw",
            "aFRR_DownActivated": "b_afrr_activated_down_mw",
            "aFRR_UpOffered_MW": "b_afrr_offered_up_mw",
            "aFRR_DownOffered_MW": "b_afrr_offered_down_mw",
            "aFRR_UpUnavailable_MW": "b_afrr_unavailable_up_mw",
            "aFRR_DownUnavailable_MW": "b_afrr_unavailable_down_mw",
        },
    },
    "da_nordpool_flows": {
        # "DeliveryStartUTC" is genuinely UTC, like every source here (see
        # TIMEZONE NOTE) — first confirmed via import_da_pipeline.py's
        # daily-completeness diagnostic: requesting a CET calendar day (e.g.
        # date=2020-12-31) returns a raw entry that falls under the
        # PREVIOUS UTC calendar day (2020-12-30 23:00). A naive CET value
        # with a fake "+00:00" tacked on (like mfrr/intraday/forecasts)
        # could never do that — it would just read as 2020-12-31T00:00
        # onward, no cross-midnight spillover possible. Only a real,
        # already-converted UTC value produces this.
        "path": PROCESSED_DIR / "day_ahead" / "flows_DK1_DK2_2021_2025_hourly.csv",
        "time_col": "DeliveryStartUTC",
        "area_col": "Area",
        "nordpool_cet_fix": False,
        "rename": {
            "TotalImport_MW": "da_flow_total_import_mw",
            "TotalExport_MW": "da_flow_total_export_mw",
            "TotalNetPosition_MW": "da_flow_total_net_position_mw",
            "NL_Import_MW": "da_flow_nl_import_mw",
            "NL_Export_MW": "da_flow_nl_export_mw",
            "NL_NetPosition_MW": "da_flow_nl_net_position_mw",
            "GER_Import_MW": "da_flow_ger_import_mw",
            "GER_Export_MW": "da_flow_ger_export_mw",
            "GER_NetPosition_MW": "da_flow_ger_net_position_mw",
            "SE3_Import_MW": "da_flow_se3_import_mw",
            "SE3_Export_MW": "da_flow_se3_export_mw",
            "SE3_NetPosition_MW": "da_flow_se3_net_position_mw",
            "NO2_Import_MW": "da_flow_no2_import_mw",
            "NO2_Export_MW": "da_flow_no2_export_mw",
            "NO2_NetPosition_MW": "da_flow_no2_net_position_mw",
            "DK2_Import_MW": "da_flow_dk2_import_mw",
            "DK2_Export_MW": "da_flow_dk2_export_mw",
            "DK2_NetPosition_MW": "da_flow_dk2_net_position_mw",
            "DK1_Import_MW": "da_flow_dk1_import_mw",
            "DK1_Export_MW": "da_flow_dk1_export_mw",
            "DK1_NetPosition_MW": "da_flow_dk1_net_position_mw",
            "SE4_Import_MW": "da_flow_se4_import_mw",
            "SE4_Export_MW": "da_flow_se4_export_mw",
            "SE4_NetPosition_MW": "da_flow_se4_net_position_mw",
        },
    },
    "da_forecasts_and_actual": {
        # From import_da_forecasts_pipeline.py. Deliberately NOT pulling in
        # c_renewables_total_forecast_mw / c_renewables_total_actual_mw here
        # even though the CSV has them — they're just sums of the solar +
        # wind_onshore + wind_offshore columns below, so carrying both risks
        # the two disagreeing. They're computed instead in DERIVED_FEATURES,
        # from these same atomic columns, so there's one source of truth.
        # Nord Pool Power System API — "time_utc" is genuine UTC (see
        # TIMEZONE NOTE; solar output peaks at solar noon in UTC).
        "path": PROCESSED_DIR / "da_forecasts" / "da_forecasts_and_actual.csv",
        "time_col": "time_utc",
        "area_col": "area",
        "nordpool_cet_fix": False,
        "rename": {
            "c_solar_forecast_mw": "c_solar_forecast_mw",
            "c_wind_offshore_forecast_mw": "c_wind_offshore_forecast_mw",
            "c_wind_onshore_forecast_mw": "c_wind_onshore_forecast_mw",
            "c_solar_actual_mw": "c_solar_actual_mw",
            "c_wind_offshore_actual_mw": "c_wind_offshore_actual_mw",
            "c_wind_onshore_actual_mw": "c_wind_onshore_actual_mw",
            "c_load_forecast_mw": "c_load_forecast_mw",
            "c_load_actual_mw": "c_load_actual_mw",
        },
    },
    "da_nordpool_prices": {
        # Genuinely UTC, same as da_nordpool_flows above — see that entry's
        # comment for the evidence (cross-midnight spillover at the request
        # range's boundary days, only possible for a real UTC value).
        "path": PROCESSED_DIR / "day_ahead" / "prices_DK1_DK2_2021_2025_hourly.csv",
        "time_col": "HourUTC",
        "area_col": "Area",
        "nordpool_cet_fix": False,
        "rename": {
            "Price_EUR": "da_price",
        },
    },
    "da_nordpool_volumes": {
        # Genuinely UTC, same as da_nordpool_flows above — see that entry's
        # comment for the evidence.
        "path": PROCESSED_DIR / "day_ahead" / "volumes_DK1_DK2_2021_2025_hourly.csv",
        "time_col": "HourUTC",
        "area_col": "Area",
        "nordpool_cet_fix": False,
        "rename": {
            "BuyVolume_MW": "da_buy_volume_mw",
            "SellVolume_MW": "da_sell_volume_mw",
        },
    },
    "reservoir": {
        # Hydro reservoir filling (Nord Pool "Reservoir" report), written by
        # src/imports/import_extras.py (download_reservoir). Weekly values,
        # already spread over the hours of their Monday-Sunday week (Nordic
        # local time) in the import — so hours early in a week see a value
        # published only after that week (documented as look-ahead).
        # Areas are NOT the DK zones: each area gets its own column, copied to
        # every DK zone row. Only the filling in % of capacity is pulled in:
        # the GWh level is that % x a capacity that changes only a few times,
        # so it would be a near-duplicate; the capacity itself is not a signal.
        # Country totals (NO, SE, FI — the baseline literature's hydro areas)
        # and the NO / SE sub-areas.
        "path": PROCESSED_DIR / "reservoir" / "reservoir_2022_2025_hourly.csv",
        "time_col": "HourUTC",
        "area_col": "Area",
        "nordpool_cet_fix": False,
        "pivot_area": True,
        "rename": {
            "ReservoirUtilization_pct_NO": "c_reservoir_fill_pct_no",
            "ReservoirUtilization_pct_SE": "c_reservoir_fill_pct_se",
            "ReservoirUtilization_pct_FI": "c_reservoir_fill_pct_fi",
            "ReservoirUtilization_pct_NO1": "c_reservoir_fill_pct_no1",
            "ReservoirUtilization_pct_NO2": "c_reservoir_fill_pct_no2",
            "ReservoirUtilization_pct_NO3": "c_reservoir_fill_pct_no3",
            "ReservoirUtilization_pct_NO4": "c_reservoir_fill_pct_no4",
            "ReservoirUtilization_pct_NO5": "c_reservoir_fill_pct_no5",
            "ReservoirUtilization_pct_SE1": "c_reservoir_fill_pct_se1",
            "ReservoirUtilization_pct_SE2": "c_reservoir_fill_pct_se2",
            "ReservoirUtilization_pct_SE3": "c_reservoir_fill_pct_se3",
            "ReservoirUtilization_pct_SE4": "c_reservoir_fill_pct_se4",
        },
    },
    "da_nordpool_system_price": {
        # Nord Pool day-ahead SYSTEM price and turnover (unconstrained Nordic
        # reference, "SYS"). It was the input of the baseline's former
        # price-based bottleneck indicator, which has been replaced by the
        # cross-border flows (da_flow_*_net_export_mw); kept as a day-ahead
        # reference series. One value per hour for the whole
        # system, so it's copied to every zone. Written by
        # src/imports/import_extras.py (download_system_price); until that
        # has been run the file is missing and the dependent columns are NaN.
        "path": PROCESSED_DIR / "day_ahead" / "system_price_turnover_2022_2025_hourly.csv",
        "time_col": "HourUTC",
        "area_col": "Area",
        "nordpool_cet_fix": False,
        "system_wide": True,
        "rename": {
            "Price_EUR": "da_system_price",
            "Turnover_MW": "da_system_turnover_mw",
        },
    },
}

_assigned = [s for srcs in MARKETS.values() for s in srcs]
assert sorted(_assigned) == sorted(SOURCES), (
    f"MARKETS must assign every SOURCES entry to exactly one market. "
    f"Unassigned: {sorted(set(SOURCES) - set(_assigned))}; "
    f"unknown or duplicated: {sorted(s for s in set(_assigned) if s not in SOURCES or _assigned.count(s) > 1)}"
)


def sources_for_markets(markets: list | None) -> list:
    """SOURCES keys for the given market names (None = every market)."""
    if markets is None:
        return list(SOURCES)
    unknown = [m for m in markets if m not in MARKETS]
    if unknown:
        raise ValueError(f"Unknown market(s) {unknown}. Valid: {list(MARKETS)}")
    return [s for m in markets for s in MARKETS[m]]


# Candidate column names to try, in order, when a source's time/bidding-zone
# column name isn't pinned down in its SOURCES entry (used only for "afrr"
# above, since we haven't confirmed the combined file's exact header).
TIME_COL_CANDIDATES = ["HourUTC", "DeliveryStartUTC", "time_utc", "datetime_utc", "Time", "TimeUTC"]
AREA_COL_CANDIDATES = ["Area", "area", "BiddingZone", "bidding_zone", "PriceArea"]

# ---------------------------------------------------------------------------
# DERIVED FEATURES
#
# Features computed from columns that already exist in the merged
# DataFrame — from SOURCES, or from another DERIVED_FEATURES entry (any
# order; see apply_derived_features()).
#
# Each entry:
#   inputs - list of final feature-column names this derived feature needs
#            (source columns and/or other derived-feature names).
#   func   - callable(df) -> pd.Series, using the already-computed columns.
#   meta   - documentation for the Excel workbook written by
#            dataframe_documentation.py: meaning, transformation, direction
#            (expected economic sign/intuition), and optionally unit /
#            market / fva (forecast vs actual). Timing fields (availability,
#            leakage, horizon) are NOT written here — they're inherited
#            automatically from the inputs, so they can't drift out of sync.
#
# A derived feature whose inputs aren't all available yet (source not wired
# in, or a dependency that itself couldn't be computed) is filled with NaN
# and reported, never crashes the build.
#
# TO ADD A NEW DERIVED FEATURE: add one entry here, in any position — no
# other part of this file needs to change.
# ---------------------------------------------------------------------------
DERIVED_FEATURES = {
    # --- simple nets ---
    "b_mfrr_net_activation_mw": {
        "inputs": ["b_mfrr_activated_up_mw", "b_mfrr_activated_down_mw"],
        "func": lambda df: df["b_mfrr_activated_up_mw"] - df["b_mfrr_activated_down_mw"],
        "meta": {
            "meaning": "Net mFRR activation: up-regulation minus down-regulation volume",
            "transformation": "Difference (up - down)",
            "direction": "Positive = system short (net upward regulation); negative = system long",
        },
    },
    "b_afrr_net_activation_mw": {
        "inputs": ["b_afrr_activated_up_mw", "b_afrr_activated_down_mw"],
        "func": lambda df: df["b_afrr_activated_up_mw"] - df["b_afrr_activated_down_mw"],
        "meta": {
            "meaning": "Net aFRR activation: up-regulation minus down-regulation volume",
            "transformation": "Difference (up - down)",
            "direction": "Positive = system short (net upward regulation); negative = system long",
        },
    },

    # (The cross-market price spreads live in the generated section below
    # — x_da_id_spread, x_id_bal_spread, x_da_bal_spread. They replaced the
    # old id_da_spread / b_da_spread, which were the same quantities with
    # the sign flipped, i.e. duplicates.)

    # --- renewables totals (computed here, not double-sourced — see note
    # on da_forecasts_and_actual in SOURCES above) ---
    "c_wind_total_forecast_mw": {
        "inputs": ["c_wind_onshore_forecast_mw", "c_wind_offshore_forecast_mw"],
        "func": lambda df: df["c_wind_onshore_forecast_mw"] + df["c_wind_offshore_forecast_mw"],
        "meta": {
            "meaning": "Day-ahead forecast of total wind generation (onshore + offshore)",
            "transformation": "Sum",
            "direction": "Higher wind -> lower DA price, higher down-regulation risk",
        },
    },
    "c_wind_total_actual_mw": {
        "inputs": ["c_wind_onshore_actual_mw", "c_wind_offshore_actual_mw"],
        "func": lambda df: df["c_wind_onshore_actual_mw"] + df["c_wind_offshore_actual_mw"],
        "meta": {
            "meaning": "Actual total wind generation (onshore + offshore)",
            "transformation": "Sum",
            "direction": "Higher wind -> lower prices; relevant mainly via its deviation from forecast",
        },
    },
    "c_renewables_total_forecast_mw": {
        "inputs": ["c_solar_forecast_mw", "c_wind_total_forecast_mw"],
        "func": lambda df: df["c_solar_forecast_mw"] + df["c_wind_total_forecast_mw"],
        "meta": {
            "meaning": "Day-ahead forecast of total variable renewable generation (solar + wind)",
            "transformation": "Sum",
            "direction": "Higher -> lower DA price (merit-order effect)",
        },
    },
    "c_renewables_total_actual_mw": {
        "inputs": ["c_solar_actual_mw", "c_wind_total_actual_mw"],
        "func": lambda df: df["c_solar_actual_mw"] + df["c_wind_total_actual_mw"],
        "meta": {
            "meaning": "Actual total variable renewable generation (solar + wind)",
            "transformation": "Sum",
            "direction": "Higher -> lower prices; relevant mainly via its deviation from forecast",
        },
    },

    # --- forecast errors: FORECAST minus ACTUAL (positive = over-forecast),
    # the sign convention of the baseline literature (Spodniak et al. 2019:
    # WE_t = W^_t - W_t, LE_t = L^_t - L_t). One convention for every error
    # column, so no sign-flipped duplicates. Generated below by
    # _register_forecast_error() — see FORECAST_ERRORS. ---

    # --- residual load: load net of renewable generation. This is the
    # quantity that actually drives balancing/reserve activation — a big
    # miss here (from either a load surprise or a renewables surprise) is
    # exactly the kind of event this thesis is about. ---
    "c_residual_load_forecast_mw": {
        "inputs": ["c_load_forecast_mw", "c_renewables_total_forecast_mw"],
        "func": lambda df: df["c_load_forecast_mw"] - df["c_renewables_total_forecast_mw"],
        "meta": {
            "meaning": "Day-ahead forecast residual load (load - solar - wind)",
            "transformation": "Difference (load - renewables)",
            "direction": "Higher -> more dispatchable/imported supply needed -> higher DA price",
        },
    },
    "c_residual_load_actual_mw": {
        "inputs": ["c_load_actual_mw", "c_renewables_total_actual_mw"],
        "func": lambda df: df["c_load_actual_mw"] - df["c_renewables_total_actual_mw"],
        "meta": {
            "meaning": "Actual residual load (load - solar - wind)",
            "transformation": "Difference (load - renewables)",
            "direction": "Higher -> tighter system -> higher prices",
        },
    },
}


# Forecast errors, forecast - actual (positive = over-forecast; see the
# comment in DERIVED_FEATURES). error name -> (forecast col, actual col,
# what it measures, what an OVER-forecast means for the system).
FORECAST_ERRORS = {
    "c_solar_err": ("c_solar_forecast_mw", "c_solar_actual_mw", "Solar",
                    "less solar than planned -> system short -> up-regulation, higher imbalance price"),
    "c_wind_onshore_err": ("c_wind_onshore_forecast_mw", "c_wind_onshore_actual_mw", "Onshore wind",
                           "less wind than planned -> system short -> up-regulation, higher imbalance price"),
    "c_wind_offshore_err": ("c_wind_offshore_forecast_mw", "c_wind_offshore_actual_mw", "Offshore wind",
                            "less wind than planned -> system short -> up-regulation, higher imbalance price"),
    "c_wind_total_err": ("c_wind_total_forecast_mw", "c_wind_total_actual_mw", "Total wind (WE_t in the baseline)",
                         "less wind than planned -> system short -> up-regulation, higher imbalance price"),
    "c_renewables_total_err": ("c_renewables_total_forecast_mw", "c_renewables_total_actual_mw",
                               "Total renewables",
                               "less renewable output than planned -> system short -> up-regulation"),
    "c_load_err": ("c_load_forecast_mw", "c_load_actual_mw", "Demand (LE_t in the baseline)",
                   "less demand than planned -> system long -> down-regulation, lower imbalance price"),
    "c_residual_load_err": ("c_residual_load_forecast_mw", "c_residual_load_actual_mw", "Residual load",
                            "less residual load than planned -> system long -> down-regulation"),
}


def _register_forecast_error(name: str, forecast: str, actual: str, what: str, over: str):
    DERIVED_FEATURES[name] = {
        "inputs": [forecast, actual],
        "func": (lambda f, a: lambda df: df[f] - df[a])(forecast, actual),
        "meta": {
            "meaning": f"{what} forecast error: day-ahead forecast - actual (positive = over-forecast)",
            "transformation": "Forecast error (forecast - actual)",
            "fva": "Forecast error (forecast - actual)",
            "direction": f"Positive = over-forecast: {over}",
        },
    }


for _name, _args in FORECAST_ERRORS.items():
    _register_forecast_error(_name, *_args)


# ---------------------------------------------------------------------------
# GENERATED DERIVED FEATURES — price dynamics, volatility, cross-market
# spreads, physical ramps. Same DERIVED_FEATURES registry as above; these
# entries are just generated in loops from the three small configs below
# instead of being typed out one by one.
#
# PER-ZONE: the panel interleaves DK1 and DK2 rows, so every lag/rolling
# operation runs per bidding_zone (a plain .diff() would subtract DK2 from
# DK1). build_dataframe() guarantees a complete hourly grid sorted by time,
# so "1 period" = 1 hour and an N-row window = the N most recent delivery
# hours. Frequency is hourly for every market in this dataframe (the
# imports already aggregated any 15-min data to hourly), so the same
# window lengths are correct for every market.
#
# NO LOOK-AHEAD: every window is trailing and ends AT row t (rows t-N+1 ..
# t) — nothing from t+1 or later is ever used. A feature at row t therefore
# becomes known exactly when its input at row t becomes known: e.g.
# b_imbalance_price_std_24 at t is ex-post, like b_imbalance_price at t.
# The documentation Excel carries each input's availability/leakage over
# automatically.
#
# NO INTERPOLATION: a change is NaN if t or t-1 is missing; a rolling
# statistic is NaN unless at least ROLLING_MIN_FRACTION of its window was
# actually observed.
#
# WARM-UP: build_dataframe() builds the grid WARMUP_HOURS before the
# requested start and trims afterwards, so the first hours of the requested
# range get complete windows from real, earlier (past) observations.
# ---------------------------------------------------------------------------
ROLLING_MIN_FRACTION = 0.8
WARMUP_HOURS = 168  # >= the longest window used below


def _per_zone(df: pd.DataFrame, col: str):
    return df.groupby("bidding_zone", sort=False)[col]


def _rolling(df: pd.DataFrame, col: str, window: int, stat: str) -> pd.Series:
    min_periods = math.ceil(ROLLING_MIN_FRACTION * window)
    return _per_zone(df, col).transform(
        lambda s: getattr(s.rolling(window, min_periods=min_periods), stat)()
    )


# op name (used as the column-name suffix) -> how to compute it + docs.
VARIABILITY_OPS = {
    "change_1": {
        "make": lambda col: (lambda df: _per_zone(df, col).diff(1)),
        "transformation": "First difference: x[t] - x[t-1]",
        "meaning": "1-hour change in {col}",
        "direction": "Sign = direction of the move; large magnitude = shock/ramp",
    },
    "abs_change_1": {
        "make": lambda col: (lambda df: _per_zone(df, col).diff(1).abs()),
        "transformation": "Absolute first difference: |x[t] - x[t-1]|",
        "meaning": "Absolute 1-hour change in {col} (instantaneous variability, no sign cancellation)",
        "direction": "Higher = more turbulent hour; expected to rise with balancing stress",
    },
    "std_24": {
        "make": lambda col: (lambda df: _rolling(df, col, 24, "std")),
        "transformation": "Rolling std, trailing 24 h window (t-23..t)",
        "meaning": "Daily-horizon volatility of {col}",
        "direction": "Higher = more volatile recent regime; expected to rise with balancing stress",
    },
    "std_168": {
        "make": lambda col: (lambda df: _rolling(df, col, 168, "std")),
        "transformation": "Rolling std, trailing 168 h window (t-167..t)",
        "meaning": "Weekly-horizon volatility regime of {col}",
        "direction": "Higher = persistently volatile week; slow-moving regime indicator",
    },
    "range_24": {
        "make": lambda col: (lambda df: _rolling(df, col, 24, "max") - _rolling(df, col, 24, "min")),
        "transformation": "Rolling max - rolling min, trailing 24 h window (t-23..t)",
        "meaning": "Daily-horizon price range (extremes) of {col}",
        "direction": "Higher = recent price extremes/spikes (also driven by the daily price shape)",
    },
}


def _register_variability(col: str, ops: list[str]):
    for op in ops:
        spec = VARIABILITY_OPS[op]
        DERIVED_FEATURES[f"{col}_{op}"] = {
            "inputs": [col],
            "func": spec["make"](col),
            "meta": {
                "meaning": spec["meaning"].format(col=col),
                "transformation": spec["transformation"],
                "direction": spec["direction"],
            },
        }


# One representative price per market. Deliberately ONE each: id_vwap /
# id_close_price / id_vwap_1h (or b_imbalance_price / b_mfrr_up_price) move
# almost together, so building the same 5 features on each would mostly
# create near-duplicates. Swap a column here to change the representative.
MARKET_PRICES = {
    "da": "da_price",
    "id": "id_vwap",
    "bal": "b_imbalance_price",
}
PRICE_OPS = ["change_1", "abs_change_1", "std_24", "std_168", "range_24"]

# (first, second) -> x_<first>_<second>_spread = first - second. "x_" =
# cross-market, a system-level feature, created once (not per market).
MARKET_SPREADS = [("da", "id"), ("id", "bal"), ("da", "bal")]

# Prices the spreads are built from — the baseline-literature definitions
# (Spodniak et al. 2019; see src/model_specs.py):
#   DA  = day-ahead price.
#   ID  = hourly intraday VWAP; hours WITHOUT intraday trades (zero traded
#         volume — exactly when Nord Pool leaves the VWAP empty) take the DA
#         price, so the DA-ID spread is 0 there instead of missing ("no need
#         for trade adjustment"). Applied inside the spread only — no
#         separate filled-price column. An hour missing from the intraday
#         data altogether stays NaN: that's missing data, not "no trades".
#   BAL = Nord Pool imbalance (regulating power) price: the up price in
#         up-regulation hours, the down price in down-regulation hours, the
#         DA price without regulation (verified on 2022-2024: 100 % / 100 % /
#         99.7 %); from 2025 the hourly mean of the 15-min imbalance prices.
# key -> (input columns, price as used in the spread, description)
SPREAD_PRICES = {
    "da": (["da_price"], lambda df: df["da_price"], "da_price"),
    "id": (["id_vwap", "da_price", "id_transaction_volume_mwh"],
           lambda df: df["id_vwap"].where(df["id_transaction_volume_mwh"] != 0, df["da_price"]),
           "id_vwap, hours without intraday trades = da_price"),
    "bal": (["b_imbalance_price"], lambda df: df["b_imbalance_price"], "b_imbalance_price"),
}

# Physical variables that get ramp/variability features, in priority order.
# Not every c_ column: only the ones that drive balancing. std_24 is left
# off solar and load on purpose — their 24 h std is dominated by the
# deterministic daily cycle (daylight / day-night demand), so it would
# measure the daily shape rather than variability. Solar/load use the
# forecast only: their hour-to-hour ramps are mostly that same
# deterministic profile, so the actual-series ramp would largely duplicate
# it (the surprise part is already in c_solar_err / c_load_err).
PHYSICAL_VARIABILITY = {
    "c_residual_load_forecast_mw": ["change_1", "std_24"],
    "c_residual_load_actual_mw": ["change_1", "std_24"],
    "c_wind_total_forecast_mw": ["change_1", "std_24"],
    "c_wind_total_actual_mw": ["change_1", "std_24"],
    "c_solar_forecast_mw": ["change_1"],
    "c_load_forecast_mw": ["change_1"],
}

for _price_col in MARKET_PRICES.values():
    _register_variability(_price_col, PRICE_OPS)

for _a, _b in MARKET_SPREADS:
    (_in_a, _fa, _da), (_in_b, _fb, _db) = SPREAD_PRICES[_a], SPREAD_PRICES[_b]
    _spread = f"x_{_a}_{_b}_spread"
    DERIVED_FEATURES[_spread] = {
        "inputs": list(dict.fromkeys(_in_a + _in_b)),
        "func": (lambda fa, fb: lambda df: fa(df) - fb(df))(_fa, _fb),
        "meta": {
            "meaning": f"Cross-market spread {_a.upper()} - {_b.upper()} ({_da}) - ({_db})",
            "transformation": "Spread (difference of prices)",
            "market": f"Cross-market ({_a.upper()}-{_b.upper()})",
            "direction": f"Positive = {_a.upper()} priced above {_b.upper()}; "
                         f"non-zero = the two market stages disagree (decoupling)",
        },
    }
    DERIVED_FEATURES[f"{_spread}_abs"] = {
        "inputs": [_spread],
        "func": (lambda s: lambda df: df[s].abs())(_spread),
        "meta": {
            "meaning": f"Absolute cross-market spread |{_a.upper()} - {_b.upper()}|",
            "transformation": "Absolute spread",
            "market": f"Cross-market ({_a.upper()}-{_b.upper()})",
            "direction": "Higher = larger disagreement between market stages, regardless of sign",
        },
    }
    _register_variability(_spread, ["std_24"])

for _col, _ops in PHYSICAL_VARIABILITY.items():
    _register_variability(_col, _ops)


# ---------------------------------------------------------------------------
# BASELINE-MODEL FEATURES (Spodniak et al. 2019; see src/model_specs.py)
# ---------------------------------------------------------------------------
LOCAL_TZ = "Europe/Copenhagen"


def _local_time(df: pd.DataFrame) -> pd.Series:
    return df["datetime_utc"].dt.tz_convert(LOCAL_TZ)


# Cross-border flows, one column per interconnection (they replace the
# baseline's former price-based bottleneck indicator, which was 1 in
# 99.6-99.9 % of hours). SIGN CONVENTION: positive = export from the row's
# bidding zone to the counterpart, negative = import. Built from the Nord
# Pool DayAheadFlow import / export columns (scheduled day-ahead exchange,
# not physical flows), which are hourly means of MW (15-min data averaged
# in import_da_pipeline.py), i.e. MWh per hour. A counterpart that is not
# connected to the row's zone (e.g. NL for DK2) is a structural 0.0 — see
# report_zero_variance_by_area(). Missing values stay missing.
FLOW_COUNTERPARTS = {"ger": "Germany", "nl": "Netherlands", "no2": "Norway (NO2)", "se3": "Sweden (SE3)",
                     "se4": "Sweden (SE4)", "dk1": "DK1 (Great Belt)", "dk2": "DK2 (Great Belt)"}


def _net_export(code: str):
    return lambda df: df[f"da_flow_{code}_export_mw"] - df[f"da_flow_{code}_import_mw"]


DERIVED_FEATURES.update({
    f"da_flow_{code}_net_export_mw": {
        "inputs": [f"da_flow_{code}_import_mw", f"da_flow_{code}_export_mw"],
        "func": _net_export(code),
        "meta": {
            "meaning": f"Cross-border flow between the zone and {name}: day-ahead scheduled exchange, "
                       f"export minus import (Nord Pool DayAheadFlow)",
            "unit": "MWh/h",
            "transformation": "Difference (export - import), hourly mean of MW",
            "market": "Day-ahead",
            "direction": "Positive = export from the zone, negative = import; 0 in every hour where the "
                         "zone has no interconnection with this counterpart",
        },
    }
    for code, name in FLOW_COUNTERPARTS.items()
})


DERIVED_FEATURES.update({
    "fe_hour": {
        "inputs": [],
        "func": lambda df: _local_time(df).dt.hour.astype(float),
        "meta": {
            "meaning": "Hour of day (0-23, Copenhagen local time) — identifier for the hour-of-day fixed "
                       "effects: enter as one dummy per hour (drop one if the model has a constant)",
            "unit": "category (0-23)",
            "transformation": "Calendar identifier (expand to dummies in the model)",
            "market": "Calendar",
            "fva": "Deterministic (calendar)",
            "direction": "Captures the diurnal pattern",
        },
    },
    "fe_week_of_sample": {
        # Absolute week number here; renumbered 1..N within the dataframe
        # after trimming (see build_dataframe), so it is week-OF-SAMPLE.
        "inputs": [],
        "func": lambda df: ((_local_time(df).dt.tz_localize(None).dt.normalize()
                             - pd.Timestamp("1970-01-05")).dt.days // 7).astype(float),
        "meta": {
            "meaning": "Week of the sample (1 = first Monday-Sunday week in the dataframe, Copenhagen "
                       "local time) — identifier for the week-of-sample fixed effects: enter as one dummy "
                       "per week (drop one if the model has a constant)",
            "unit": "category (1..N)",
            "transformation": "Calendar identifier (expand to dummies in the model)",
            "market": "Calendar",
            "fva": "Deterministic (calendar)",
            "direction": "Captures seasonal / slow-moving level changes",
        },
    },
    "fe_month_of_sample": {
        # Absolute month number here (year * 12 + month); renumbered 1..N
        # within the dataframe after trimming, like fe_week_of_sample. The
        # coarser alternative to the weekly effects (stationarity_lag_selection.CONTROL_SETS).
        "inputs": [],
        "func": lambda df: (_local_time(df).dt.year * 12 + _local_time(df).dt.month).astype(float),
        "meta": {
            "meaning": "Month of the sample (1 = first calendar month in the dataframe, Copenhagen local "
                       "time) — identifier for the month-of-sample fixed effects: enter as one dummy per "
                       "month (drop one if the model has a constant)",
            "unit": "category (1..N)",
            "transformation": "Calendar identifier (expand to dummies in the model)",
            "market": "Calendar",
            "fva": "Deterministic (calendar)",
            "direction": "Captures slow level changes at monthly resolution (coarser than weekly)",
        },
    },
})

MIN_EDGE_MONTH_HOURS = 24  # a first / last local month with fewer hours is merged into its neighbour


def _merge_partial_edge_months(grid: pd.DataFrame) -> pd.Series:
    """fe_month_of_sample with a tiny first or last month merged into the
    adjacent month. A sample ending at 23:00 UTC on 31 December ends at 00:00
    on 1 January in Copenhagen time, so that single hour would otherwise form
    its own month (and its own dummy, fitting that hour exactly)."""
    month = grid["fe_month_of_sample"].copy()
    hours = grid.groupby("fe_month_of_sample")["datetime_utc"].nunique().sort_index()
    if len(hours) > 1 and hours.iloc[-1] < MIN_EDGE_MONTH_HOURS:
        month[month == hours.index[-1]] = hours.index[-2]
    if len(hours) > 1 and hours.iloc[0] < MIN_EDGE_MONTH_HOURS:
        month[month == hours.index[0]] = hours.index[1]
    return month


# Calendar identifiers numbered within the final dataframe (after the
# warm-up rows are trimmed): value -> rank 1..N.
RENUMBER_WITHIN_SAMPLE = ["fe_week_of_sample", "fe_month_of_sample"]


def apply_derived_features(df: pd.DataFrame, derived: dict = None) -> pd.DataFrame:
    """Compute DERIVED_FEATURES with automatic dependency resolution: this
    makes repeated passes over the (not-yet-computed) entries, computing any
    whose inputs are now all available (from SOURCES columns or from a
    derived feature computed in an earlier pass), until a pass makes no
    further progress. This means entries can be listed in ANY order in the
    dict — you never have to manually sequence "compute the totals before
    the things that use the totals," which is a real mistake to make by
    hand as this list grows. Anything left over after the loop stabilizes
    has a genuinely missing (not just not-yet-computed) input, and is filled
    with NaN and reported."""
    derived = derived if derived is not None else DERIVED_FEATURES
    df = df.copy()
    remaining = dict(derived)

    made_progress = True
    while remaining and made_progress:
        made_progress = False
        for name in list(remaining.keys()):
            cfg = remaining[name]
            missing_inputs = [c for c in cfg["inputs"] if c not in df.columns]
            if missing_inputs:
                continue  # maybe computable in a later pass, or genuinely missing
            try:
                df[name] = cfg["func"](df)
                print(f"[derived:{name}] computed from {cfg['inputs']}")
            except Exception as e:
                print(f"[derived:{name}] ERROR computing feature: {e}")
                df[name] = pd.NA
            del remaining[name]
            made_progress = True

    for name, cfg in remaining.items():
        missing_inputs = [c for c in cfg["inputs"] if c not in df.columns]
        print(f"[derived:{name}] SKIPPED — missing input column(s): {missing_inputs}")
        df[name] = pd.NA

    return df


def _fix_nordpool_mislabeled_cet(out: pd.DataFrame, source_name: str) -> pd.DataFrame:
    """Unconditional -1 h shift, for a source whose '...UTC' column holds
    fixed CET (UTC+1) times. NOT USED by any current source: every Nord Pool
    feed turned out to be genuine UTC (see the TIMEZONE NOTE in the module
    docstring). It was previously applied to mFRR, intraday and forecasts on
    the strength of a DST check (24 rows on every day) — but genuine UTC
    gives 24 rows every day too, so that check could not distinguish the
    two. Kept only for a future source that is verifiably mislabeled."""
    out = out.copy()
    naive = out["datetime_utc"].dt.tz_localize(None)
    out["datetime_utc"] = (naive - pd.Timedelta(hours=1)).dt.tz_localize("UTC")
    return out


def _resolve_column(df: pd.DataFrame, configured: str | None, candidates: list[str], role: str, source_name: str) -> str:
    """Return the actual column name to use for a role (time/bidding-zone),
    given either an explicit configured name or a list of candidates to
    try."""
    if configured is not None:
        if configured not in df.columns:
            raise KeyError(
                f"[{source_name}] configured {role} column '{configured}' not found. "
                f"Actual columns: {list(df.columns)}"
            )
        return configured
    for c in candidates:
        if c in df.columns:
            return c
    raise KeyError(
        f"[{source_name}] could not auto-detect {role} column. "
        f"Tried {candidates}. Actual columns: {list(df.columns)}"
    )


def load_source(name: str, cfg: dict) -> pd.DataFrame:
    """Load one processed CSV, verify its columns against what's configured,
    rename to final feature names, and return a (datetime_utc, bidding_zone,
    <features>) frame ready to merge."""
    path = cfg["path"]
    if not path.exists():
        print(f"[{name}] SKIPPED — file not found: {path}")
        return pd.DataFrame(columns=KEY)

    df = pd.read_csv(path)
    print(f"[{name}] loaded {path.name}: {len(df)} rows, columns: {list(df.columns)}")

    time_col = _resolve_column(df, cfg.get("time_col"), TIME_COL_CANDIDATES, "time", name)
    area_col = _resolve_column(df, cfg.get("area_col"), AREA_COL_CANDIDATES, "bidding-zone", name)

    if cfg.get("pivot_area", False):
        # One row per (hour, other area) -> one row per hour, one column per
        # (value, area). A repeated (hour, area) would be ambiguous: refuse.
        # Numeric value columns only: a text column (e.g. WeekStartDate) in the
        # pivot would turn every resulting column into dtype object.
        value_cols = [c for c in df.columns
                      if c not in (time_col, area_col) and pd.api.types.is_numeric_dtype(df[c])]
        dup = df.duplicated([time_col, area_col])
        if dup.any():
            raise ValueError(f"[{name}] {int(dup.sum())} repeated ({time_col}, {area_col}) rows — cannot pivot")
        wide = df.pivot(index=time_col, columns=area_col, values=value_cols)
        wide.columns = [f"{value}_{area}" for value, area in wide.columns]
        wide = wide.astype(float)
        df = wide.reset_index()
        df[area_col] = "SYSTEM"
        print(f"[{name}] areas spread into columns: {len(wide.columns)} columns, {len(df)} hours")

    rename = cfg["rename"]
    missing = [c for c in rename if c not in df.columns]
    found = [c for c in rename if c in df.columns]
    if missing:
        print(f"[{name}] WARNING — {len(missing)} configured column(s) not found in file "
              f"(these features will be ALL-NaN for this source): {missing}")
    if not found:
        print(f"[{name}] WARNING — none of the configured feature columns matched. "
              f"Check SOURCES['{name}']['rename'] against the real header above.")

    keep_cols = [time_col, area_col] + found
    out = df[keep_cols].copy()
    out = out.rename(columns={time_col: "datetime_utc", area_col: "bidding_zone", **rename})
    out["datetime_utc"] = pd.to_datetime(out["datetime_utc"], utc=True)
    out["bidding_zone"] = out["bidding_zone"].astype(str)

    empty_before_map = {col: out[col].isna() for col in cfg.get("fill_empty", {}) if col in out.columns}
    for col, mapping in cfg.get("value_map", {}).items():
        if col not in out.columns:
            continue
        unmapped = sorted(set(out[col].dropna()) - set(mapping))
        if unmapped:
            print(f"[{name}] WARNING — {col}: value(s) {unmapped} not in value_map, set to NaN.")
        out[col] = out[col].map(mapping).astype(float)
        print(f"[{name}] {col} mapped {mapping}")
    for col, value in cfg.get("fill_empty", {}).items():
        if col in empty_before_map:
            out.loc[empty_before_map[col], col] = value
            print(f"[{name}] {col}: {int(empty_before_map[col].sum())} empty cell(s) set to {value}")

    if cfg.get("system_wide", False) or cfg.get("pivot_area", False):
        # One system-wide series (e.g. area "SYS") -> one copy per zone.
        print(f"[{name}] system-wide series: copied to zones {AREAS}")
        out = pd.concat([out.assign(bidding_zone=zone) for zone in AREAS], ignore_index=True)

    if cfg.get("nordpool_cet_fix", False):
        print(f"[{name}] correcting Nord Pool timestamps: header says UTC, "
              f"values are actually Europe/Copenhagen local time (CET/CEST)...")
        out = _fix_nordpool_mislabeled_cet(out, name)

    dupe_mask = out.duplicated(subset=KEY, keep=False)
    n_dupes = dupe_mask.sum()
    if n_dupes:
        print(f"[{name}] WARNING — {n_dupes} duplicate {tuple(KEY)} rows; keeping first, dropping the rest.")
        if "Source" in df.columns:
            breakdown = df.loc[out.index[dupe_mask], "Source"].value_counts()
            print(f"[{name}]   duplicate rows by 'Source' column: {breakdown.to_dict()}")
        else:
            # No 'Source' column to break down by (e.g. mfrr) — first print
            # EVERY duplicated key compactly (so the full pattern is visible
            # — e.g. whether all of them fall on known DST transition
            # dates), then the raw original rows (all original columns, not
            # just the ones kept in `out`) for a handful of them, so the
            # pattern can be eyeballed directly instead of guessed at.
            all_keys = out.loc[dupe_mask, KEY].drop_duplicates().sort_values(KEY)
            print(f"[{name}]   no 'Source' column — all {len(all_keys)} duplicated key(s):")
            print(all_keys.to_string(index=False))
            sample_keys = all_keys.head(5)
            print(f"[{name}]   raw rows for the first {len(sample_keys)} of them:")
            for _, key_row in sample_keys.iterrows():
                match = out.index[dupe_mask & (out["datetime_utc"] == key_row["datetime_utc"])
                                   & (out["bidding_zone"] == key_row["bidding_zone"])]
                print(df.loc[match].to_string())
        out = out.drop_duplicates(subset=KEY, keep="first")

    return out


def _hourly_datetime_index(start: str, end: str) -> pd.DatetimeIndex:
    """The single, shared definition of 'the hourly grid for [start, end]',
    used by both build_dataframe() and sanity_check() so they can never
    silently disagree about what range is expected. start/end are calendar
    dates and BOTH ARE INCLUSIVE — end's full 24 hours are included, not
    just up to end's midnight. (A plain
    pd.date_range(start, end, inclusive="left") stops at end's 00:00, one
    day short of what "2022-01-01 to 2025-12-31" actually means.)"""
    end_exclusive = pd.Timestamp(end) + pd.Timedelta(days=1)
    return pd.date_range(start, end_exclusive, freq="h", tz="UTC", inclusive="left")


def _derivable_features(available_cols, derived: dict) -> dict:
    """The derived features whose inputs will all exist, given the source
    columns present — following chains (a spread's std needs the spread,
    which needs both prices). Registry order is kept."""
    available = set(available_cols)
    reachable = set()
    progress = True
    while progress:
        progress = False
        for name, cfg in derived.items():
            if name not in reachable and all(c in available for c in cfg["inputs"]):
                reachable.add(name)
                available.add(name)
                progress = True
    return {k: v for k, v in derived.items() if k in reachable}


def build_dataframe(start: str, end: str, sources: list = None, areas: list = None,
                     derived: list = None) -> pd.DataFrame:
    """Build one analysis-ready DataFrame: an hourly UTC x bidding-zone grid,
    with the given SOURCES (or all of them if sources=None) left-joined onto
    it, then DERIVED_FEATURES computed on top: derived=None means every
    derived feature whose inputs are all present (the rest are left out
    entirely — e.g. no DA-ID spread when intraday isn't selected); an
    explicit list is computed as given, NaN-filled if an input is missing.
    Any (datetime, bidding_zone, feature) combination not covered by a
    source is NaN — this is expected and correct, not an error, for periods
    before a source starts. start/end are both inclusive."""
    areas = areas if areas is not None else AREAS
    source_dict = SOURCES if sources is None else {k: SOURCES[k] for k in sources}

    # Grid starts WARMUP_HOURS early so trailing lag/rolling features have
    # real past observations for the first hours of [start, end]; the
    # warm-up rows are trimmed off again after the derived features are
    # computed.
    warmup_start = pd.Timestamp(start) - pd.Timedelta(hours=WARMUP_HOURS)
    idx = pd.MultiIndex.from_product(
        [_hourly_datetime_index(warmup_start, end), areas],
        names=KEY,
    )
    grid = pd.DataFrame(index=idx).reset_index()

    for name, cfg in source_dict.items():
        src_df = load_source(name, cfg)
        if src_df.empty:
            continue
        grid = grid.merge(src_df, on=KEY, how="left")

    if derived is None:
        derived_dict = _derivable_features(grid.columns, DERIVED_FEATURES)
        left_out = [k for k in DERIVED_FEATURES if k not in derived_dict]
        if left_out:
            print(f"[derived] {len(left_out)} feature(s) left out — inputs not available "
                  f"(market not selected, or source file missing): {left_out}")
    else:
        derived_dict = {k: DERIVED_FEATURES[k] for k in derived}

    # Sorted BEFORE deriving: the per-zone diff/rolling features rely on
    # each zone's rows being in time order.
    grid = grid.sort_values(KEY).reset_index(drop=True)
    n_cols_before = len(grid.columns)
    grid = apply_derived_features(grid, derived_dict)
    new_cols = list(grid.columns[n_cols_before:])
    print(f"[derived] {len(new_cols)} derived column(s) created: {new_cols}")

    grid = grid[grid["datetime_utc"] >= pd.Timestamp(start, tz="UTC")].reset_index(drop=True)
    if "fe_month_of_sample" in grid.columns:
        grid["fe_month_of_sample"] = _merge_partial_edge_months(grid)
    for col in RENUMBER_WITHIN_SAMPLE:
        if col in grid.columns:
            grid[col] = grid[col].rank(method="dense")
    return grid


def coverage_report(df: pd.DataFrame) -> pd.DataFrame:
    """Per-feature-column: first/last non-null timestamp and % missing.
    Run this after every build, especially after adding a new source —
    it's the fastest way to catch a bad join before it reaches the VAR."""
    feature_cols = [c for c in df.columns if c not in KEY]
    rows = []
    for col in feature_cols:
        s = df[col]
        non_null = s.notna()
        rows.append({
            "feature": col,
            "pct_missing": round(100 * (1 - non_null.mean()), 2),
            "first_non_null": df.loc[non_null, "datetime_utc"].min() if non_null.any() else None,
            "last_non_null": df.loc[non_null, "datetime_utc"].max() if non_null.any() else None,
        })
    report = pd.DataFrame(rows).sort_values("feature").reset_index(drop=True)
    return report


def report_zero_variance_by_area(df: pd.DataFrame, areas: list = None):
    """Flags feature columns that are constant within one bidding_zone's own
    rows of the panel. The clearest example: da_flow_se4_* is always 0.0
    for every DK1 row (SE4 is only physically connected to DK2 via
    Oresund, not to DK1), da_flow_nl_*/se3_*/no2_* are always 0.0 for every
    DK2 row (those are DK1-exclusive interconnectors), and da_flow_dk1_*/
    da_flow_dk2_* are always 0.0 for that SAME area's own rows (an area
    can't be its own interconnector neighbor) — see da_nordpool_flows'
    comment above and import_da_pipeline.py's _fix_structural_flow_zeros(),
    which is what fills these in as 0.0 rather than leaving them NaN.

    This is expected, correct data — NOT a bug to fix here — but it does
    mean these columns carry zero information (and can make a VAR's design
    matrix singular) if fed into a model fit on that one area alone. Don't
    drop them from THIS combined panel: the same column is real, non-
    constant data for the OTHER area's rows, so dropping it here would
    destroy that area's data too. Drop it only from a single-area frame,
    e.g. via filter_to_area(), right before fitting that area's VAR."""
    areas = areas if areas is not None else sorted(df["bidding_zone"].unique())
    feature_cols = [c for c in df.columns if c not in KEY]
    print(f"\n  Zero-variance-by-area check (columns constant within one area's own rows — "
          f"drop these before fitting a VAR on that area alone, via filter_to_area()):")
    any_found = False
    for area in areas:
        sub = df[df["bidding_zone"] == area]
        constant_cols = []
        for col in feature_cols:
            vals = sub[col].dropna()
            if len(vals) > 0 and vals.nunique() == 1:
                constant_cols.append((col, vals.iloc[0]))
        if constant_cols:
            any_found = True
            print(f"    {area}: {len(constant_cols)} constant column(s):")
            for col, val in constant_cols:
                print(f"      {col} = {val} for all {len(sub)} non-NaN rows")
    if not any_found:
        print(f"    none found.")


def filter_to_area(df: pd.DataFrame, area: str, drop_zero_variance: bool = True) -> pd.DataFrame:
    """Subset the combined panel to one bidding_zone, ready to hand to a
    single-area VAR. By default (drop_zero_variance=True) also drops any
    feature column that's constant across that area's rows — most often
    the structural-zero flow columns described in
    report_zero_variance_by_area() above. A zero-variance regressor adds
    no information to a VAR and can make its design matrix singular or
    numerically unstable, so it's worth dropping automatically rather than
    hoping it gets caught during estimation. Prints exactly what got
    dropped and why, so nothing disappears silently — pass
    drop_zero_variance=False to keep every column as-is."""
    sub = df[df["bidding_zone"] == area].copy().reset_index(drop=True)
    if not drop_zero_variance:
        return sub
    feature_cols = [c for c in sub.columns if c not in KEY]
    dropped = []
    for col in feature_cols:
        vals = sub[col].dropna()
        if len(vals) > 0 and vals.nunique() == 1:
            dropped.append((col, vals.iloc[0]))
    if dropped:
        print(f"[filter_to_area:{area}] dropping {len(dropped)} zero-variance column(s):")
        for col, val in dropped:
            print(f"  {col} (constant {val})")
        sub = sub.drop(columns=[c for c, _ in dropped])
    else:
        print(f"[filter_to_area:{area}] no zero-variance columns found — nothing dropped.")
    return sub


def sanity_check(df: pd.DataFrame, expected_start: str, expected_end: str, areas: list):
    """Cheap structural checks that catch build mistakes early: row count
    matches the expected hourly grid exactly, the key is unique, and no
    accidental duplicate columns from a bad merge."""
    expected_hours = len(_hourly_datetime_index(expected_start, expected_end))
    expected_rows = expected_hours * len(areas)
    problems = []
    if len(df) != expected_rows:
        problems.append(f"row count {len(df)} != expected {expected_rows} "
                         f"({expected_hours} hours x {len(areas)} areas)")
    if df.duplicated(subset=KEY).any():
        problems.append(f"{df.duplicated(subset=KEY).sum()} duplicate {tuple(KEY)} rows")
    dupe_cols = df.columns[df.columns.duplicated()].tolist()
    if dupe_cols:
        problems.append(f"duplicate column names: {dupe_cols}")

    if problems:
        print("  SANITY CHECK FAILED:")
        for p in problems:
            print(f"    - {p}")
    else:
        print(f"  Sanity check OK: {len(df)} rows, {len(df.columns)} columns, key is unique.")


def save_dataframe(df: pd.DataFrame, analysis_name: str):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / f"{analysis_name}.csv"
    df.to_csv(out_path, index=False)
    print(f"  Saved {out_path} ({len(df)} rows, {len(df.columns)} columns)")


SCRIPT_VERSION = "2026-10-07-utc-fix-baseline-v9"


def create_dataframe(name: str, start: str, end: str, markets: list | None = None,
                     areas: list | None = None, columns: list | None = None) -> pd.DataFrame:
    """Build, check and save one dataframe (data/dataframes/<name>.csv) —
    the "build" step of main.py. markets=None means every market.
    columns: keep only these (plus the key), in this order — e.g. the
    variables of a model spec. Everything is computed first, so derived
    columns can still use inputs that are not kept. A requested column that
    could not be built is kept as all-NaN, with a loud warning."""
    areas = areas if areas is not None else AREAS
    print(f"dataframe_building.py VERSION MARKER: {SCRIPT_VERSION}")
    print(f"Markets: {markets or list(MARKETS)} | zones: {areas} | {start} to {end}")
    df = build_dataframe(start, end, sources=sources_for_markets(markets), areas=areas)
    if columns is not None:
        missing = [c for c in columns if c not in df.columns]
        if missing:
            print(f"WARNING — requested column(s) could not be built, kept as all-NaN: {missing}")
            for c in missing:
                df[c] = float("nan")
        df = df[KEY + list(columns)]
        print(f"Kept {len(columns)} requested column(s) (+ key).")
    sanity_check(df, start, end, areas)
    report = coverage_report(df)
    print(report.to_string(index=False))
    report_zero_variance_by_area(df, areas)
    save_dataframe(df, name)
    return df


if __name__ == "__main__":
    raise SystemExit("dataframe_building.py is now a library — run main.py from the project root "
                     "(the dataframes to build are configured there).")