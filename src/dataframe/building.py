"""
building.py — builds the analysis-ready dataframes (the "build"
step of main.py) from the processed per-source CSVs in data/processed/,
written by the scripts in src/imports/.

HOW A DATAFRAME IS DEFINED
--------------------------
main.py lists, per dataframe, its ENDOGENOUS and EXOGENOUS variables.
make_spec() adds every column those variables are computed from — their
INPUTS, followed recursively down to the raw source columns — so the
construction of every variable can be checked in the data. Only the sources
holding those columns are loaded and only the derived features needed are
computed.

TWO REGISTRIES
--------------
    SOURCES           raw columns pulled in from the processed CSVs.
    DERIVED_FEATURES  columns computed from other columns (source columns or
                      other derived features; the dependencies are resolved
                      automatically, so the order of the entries is free).
To make a new variable available, add ONE entry to either registry, plus its
documentation in documentation.py. Rule: a quantity that can be
computed from columns already available is a DERIVED feature, never a second
source column — so there is exactly one source of truth for it.

Naming convention: da_ day-ahead, id_ intraday, b_ balancing, c_ physical
fundamentals (forecasts, actuals, hydro), x_ cross-market, fe_ calendar
dummies (stored as category identifiers; expanded to dummies in the model).

TIMEZONE NOTE (verified 2026-10-07): EVERY source is genuinely UTC — all Nord
Pool feeds (day-ahead prices / volumes / flows, mFRR / imbalance, intraday,
Power System forecasts / actuals) and ENTSO-E / Energinet aFRR. The raw Nord
Pool responses say so: delivery day 2025-03-01 (CET) starts at
"2025-02-28T23:00:00Z" in every feed. Three data checks agree: imbalance
price == DA price in 99.7 % of no-regulation hours unshifted (0.7 % after a
-1 h shift); intraday VWAP tracks the DA price best unshifted; solar output
peaks at solar noon in UTC. An earlier "-1 h Nord Pool CET fix" on mFRR,
intraday and forecasts was wrong (it put those columns one hour early) and
was removed; results produced before then are invalid.
"""

import math
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

# ----------------------- CONFIG -----------------------
PROJECT_ROOT = Path(__file__).resolve().parents[2]  # src/dataframe/<this file> -> project root
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
OUTPUT_DIR = PROJECT_ROOT / "data" / "dataframes"
DOCUMENTATION_DIR = OUTPUT_DIR / "documentation"

KEY = ["datetime_utc", "bidding_zone"]  # every dataframe: one row per (delivery hour UTC, bidding zone)
LOCAL_TZ = "Europe/Copenhagen"          # calendar dummies and seasonal profiles use local time
CALENDAR_PREFIX = "fe_"                 # calendar dummies: category identifiers, not measurements

# ---------------------------------------------------------------------------
# SOURCE REGISTRY
#   path        processed CSV
#   time_col    column holding the UTC delivery-hour start
#   area_col    column holding the bidding zone (or other area)
#   rename      {column in the file: final column name}. Only these can be
#               pulled in; the build takes the ones a dataframe needs.
#   value_map   optional {final column: {raw value: number}} for text columns;
#               a non-empty value not in the map is reported and becomes NaN.
#   fill_empty  optional {final column: value} for EMPTY cells in rows the
#               source contains (only where an empty cell has a verified
#               meaning). Hours missing from the source stay NaN.
#   prepare     optional function(raw frame) -> raw frame, applied right after
#               reading (e.g. to add columns computed from another file).
#   pivot_area  True for a file of OTHER areas than the bidding zones (e.g.
#               NO / SE / FI reservoirs): each area becomes its own column
#               '<file column>_<area>', copied to every bidding zone.
#   system_wide True for one value per hour for the whole system (e.g. the
#               Nord Pool system price): copied to every bidding zone.
# ---------------------------------------------------------------------------
FLOW_QUANTITIES = [("Import", "import"), ("Export", "export"), ("NetPosition", "net_position")]
RESERVOIR_AREAS = ["NO", "SE", "FI", "NO1", "NO2", "NO3", "NO4", "NO5", "SE1", "SE2", "SE3", "SE4"]
RESERVOIR_WEEKLY_PATH = PROCESSED_DIR / "reservoir" / "reservoir_weekly.csv"


def _add_reservoir_history_median(hourly: pd.DataFrame) -> pd.DataFrame:
    """Adds ReservoirUtilizationMedian_pct: per area, the median filling of the
    same ISO week over all EARLIER ISO years in reservoir_weekly.csv (which
    starts in 2021, before the hourly file). Only earlier years, so the
    reference holds no information from the future; a week without earlier
    years (2021, or an ISO week 53 never seen before) has no median (NaN).
    Matched to the hours via WeekStartDate, the week assignment of the import."""
    weekly = pd.read_csv(RESERVOIR_WEEKLY_PATH).sort_values(["Area", "IsoWeek", "IsoYear"])
    weekly["ReservoirUtilizationMedian_pct"] = (
        weekly.groupby(["Area", "IsoWeek"])["ReservoirUtilization_pct"]
        .transform(lambda s: s.expanding().median().shift(1)))
    return hourly.merge(weekly[["Area", "WeekStartDate", "ReservoirUtilizationMedian_pct"]],
                        on=["Area", "WeekStartDate"], how="left")


SOURCES = {
    "mfrr": {
        # Nord Pool mFRR / imbalance. Empty dominating direction = no
        # regulation: in empty hours of 2022-2024 the balancing price equals
        # the DA price and mFRR activation is zero in 99-100 % of cases; 2025
        # is less clean (40 % / 52 %), as hourly values aggregate 15-min states.
        "path": PROCESSED_DIR / "mfrr" / "mfrr_DK1_DK2_2021_2025_MW.csv",
        "time_col": "DeliveryStartUTC",
        "area_col": "Area",
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
        "value_map": {"b_dominating_direction": {"Up": 1, "Down": -1}},
        "fill_empty": {"b_dominating_direction": 0},
    },
    "intraday": {
        "path": PROCESSED_DIR / "intraday" / "intraday_DK1_DK2_2021_2025.csv",
        "time_col": "DeliveryStartUTC",
        "area_col": "Area",
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
        # One stitched hourly series: Energinet (pre-PICASSO) + ENTSO-E
        # (post-PICASSO). No _MW suffix on the activated columns in this file.
        "path": PROCESSED_DIR / "afrr" / "afrr_DK1_DK2_2022_2025_hourly.csv",
        "time_col": "HourUTC",
        "area_col": "Area",
        "rename": {
            "aFRR_UpActivated": "b_afrr_activated_up_mw",
            "aFRR_DownActivated": "b_afrr_activated_down_mw",
            "aFRR_UpOffered_MW": "b_afrr_offered_up_mw",
            "aFRR_DownOffered_MW": "b_afrr_offered_down_mw",
            "aFRR_UpUnavailable_MW": "b_afrr_unavailable_up_mw",
            "aFRR_DownUnavailable_MW": "b_afrr_unavailable_down_mw",
        },
    },
    "da_nordpool_flows": {
        # Day-ahead scheduled exchange per border (not physical flows). A
        # border the zone does not have is a structural 0.0, set in the import.
        "path": PROCESSED_DIR / "day_ahead" / "flows_DK1_DK2_2021_2025_hourly.csv",
        "time_col": "DeliveryStartUTC",
        "area_col": "Area",
        "rename": {
            **{f"Total{q}_MW": f"da_flow_total_{s}_mw" for q, s in FLOW_QUANTITIES},
            **{f"{border}_{q}_MW": f"da_flow_{border.lower()}_{s}_mw"
               for border in ["NL", "GER", "SE3", "NO2", "DK2", "DK1", "SE4"] for q, s in FLOW_QUANTITIES},
        },
    },
    "da_forecasts_and_actual": {
        # The file's own renewables totals are NOT pulled in: they are sums of
        # the columns below and are computed in DERIVED_FEATURES instead.
        "path": PROCESSED_DIR / "da_forecasts" / "da_forecasts_and_actual.csv",
        "time_col": "time_utc",
        "area_col": "area",
        "rename": {c: c for c in [
            "c_solar_forecast_mw", "c_wind_offshore_forecast_mw", "c_wind_onshore_forecast_mw",
            "c_solar_actual_mw", "c_wind_offshore_actual_mw", "c_wind_onshore_actual_mw",
            "c_load_forecast_mw", "c_load_actual_mw",
        ]},
    },
    "da_nordpool_prices": {
        "path": PROCESSED_DIR / "day_ahead" / "prices_DK1_DK2_2021_2025_hourly.csv",
        "time_col": "HourUTC",
        "area_col": "Area",
        "rename": {"Price_EUR": "da_price"},
    },
    "da_nordpool_volumes": {
        "path": PROCESSED_DIR / "day_ahead" / "volumes_DK1_DK2_2021_2025_hourly.csv",
        "time_col": "HourUTC",
        "area_col": "Area",
        "rename": {"BuyVolume_MW": "da_buy_volume_mw", "SellVolume_MW": "da_sell_volume_mw"},
    },
    "reservoir": {
        # Weekly hydro reservoir filling (Nord Pool), spread over the hours of
        # its Monday-Sunday week in the import (src/imports/import_extras.py),
        # so hours early in a week see a value published after that week
        # (look-ahead, documented). Filling in % of capacity, plus its median
        # of the same week in earlier years (_add_reservoir_history_median).
        "path": PROCESSED_DIR / "reservoir" / "reservoir_2022_2025_hourly.csv",
        "time_col": "HourUTC",
        "area_col": "Area",
        "prepare": _add_reservoir_history_median,
        "pivot_area": True,
        "rename": {
            **{f"ReservoirUtilization_pct_{a}": f"c_reservoir_fill_pct_{a.lower()}" for a in RESERVOIR_AREAS},
            **{f"ReservoirUtilizationMedian_pct_{a}": f"c_reservoir_fill_median_pct_{a.lower()}"
               for a in RESERVOIR_AREAS},
        },
    },
    "da_nordpool_system_price": {
        # Nord Pool day-ahead SYSTEM price and turnover (unconstrained Nordic
        # reference): one value per hour, copied to every zone.
        "path": PROCESSED_DIR / "day_ahead" / "system_price_turnover_2022_2025_hourly.csv",
        "time_col": "HourUTC",
        "area_col": "Area",
        "system_wide": True,
        "rename": {"Price_EUR": "da_system_price", "Turnover_MW": "da_system_turnover_mw"},
    },
}

SOURCE_OF = {final: name for name, cfg in SOURCES.items() for final in cfg["rename"].values()}
assert len(SOURCE_OF) == sum(len(cfg["rename"]) for cfg in SOURCES.values()), \
    "A final column name appears in two SOURCES entries"

# ---------------------------------------------------------------------------
# DERIVED FEATURES
#   inputs  columns this feature is computed from (source or derived)
#   func    function(df) -> pd.Series
#   meta    documentation (meaning, transformation, direction; optional unit,
#           market, fva). Timing fields (availability, leakage, horizon) are
#           inherited from the inputs in documentation.py.
#
# PER ZONE: the panel interleaves the zones, so every lag / rolling operation
# runs per bidding_zone on the complete hourly grid sorted by time (1 row =
# 1 hour). Windows are trailing (t-N+1 .. t, never forward); a change is NaN
# if t or t-1 is missing; a rolling statistic needs ROLLING_MIN_FRACTION of
# its window observed (no interpolation). The grid starts WARMUP_HOURS before
# the requested start, so the first hours get complete windows from real past
# observations; the warm-up is trimmed afterwards.
# ---------------------------------------------------------------------------
ROLLING_MIN_FRACTION = 0.8
WARMUP_HOURS = 168  # >= the longest window used below


def _difference(a: str, b: str):
    return lambda df: df[a] - df[b]


def _sum(a: str, b: str):
    return lambda df: df[a] + df[b]


def _per_zone(df: pd.DataFrame, col: str):
    return df.groupby("bidding_zone", sort=False)[col]


def _rolling(df: pd.DataFrame, col: str, window: int, stat: str) -> pd.Series:
    min_periods = math.ceil(ROLLING_MIN_FRACTION * window)
    return _per_zone(df, col).transform(lambda s: getattr(s.rolling(window, min_periods=min_periods), stat)())


def _local_time(df: pd.DataFrame) -> pd.Series:
    return df["datetime_utc"].dt.tz_convert(LOCAL_TZ)


DERIVED_FEATURES = {
    # --- net activations ---
    "b_mfrr_net_activation_mw": {
        "inputs": ["b_mfrr_activated_up_mw", "b_mfrr_activated_down_mw"],
        "func": _difference("b_mfrr_activated_up_mw", "b_mfrr_activated_down_mw"),
        "meta": {"meaning": "Net mFRR activation: up-regulation minus down-regulation volume",
                 "transformation": "Difference (up - down)",
                 "direction": "Positive = system short (net upward regulation); negative = system long"},
    },
    "b_afrr_net_activation_mw": {
        "inputs": ["b_afrr_activated_up_mw", "b_afrr_activated_down_mw"],
        "func": _difference("b_afrr_activated_up_mw", "b_afrr_activated_down_mw"),
        "meta": {"meaning": "Net aFRR activation: up-regulation minus down-regulation volume",
                 "transformation": "Difference (up - down)",
                 "direction": "Positive = system short (net upward regulation); negative = system long"},
    },
    # --- renewables totals (computed here, not taken from the source's own totals) ---
    "c_wind_total_forecast_mw": {
        "inputs": ["c_wind_onshore_forecast_mw", "c_wind_offshore_forecast_mw"],
        "func": _sum("c_wind_onshore_forecast_mw", "c_wind_offshore_forecast_mw"),
        "meta": {"meaning": "Day-ahead forecast of total wind generation (onshore + offshore)",
                 "transformation": "Sum",
                 "direction": "Higher wind -> lower DA price, higher down-regulation risk"},
    },
    "c_wind_total_actual_mw": {
        "inputs": ["c_wind_onshore_actual_mw", "c_wind_offshore_actual_mw"],
        "func": _sum("c_wind_onshore_actual_mw", "c_wind_offshore_actual_mw"),
        "meta": {"meaning": "Actual total wind generation (onshore + offshore)",
                 "transformation": "Sum",
                 "direction": "Higher wind -> lower prices; relevant mainly via its deviation from forecast"},
    },
    "c_renewables_total_forecast_mw": {
        "inputs": ["c_solar_forecast_mw", "c_wind_total_forecast_mw"],
        "func": _sum("c_solar_forecast_mw", "c_wind_total_forecast_mw"),
        "meta": {"meaning": "Day-ahead forecast of total variable renewable generation (solar + wind)",
                 "transformation": "Sum",
                 "direction": "Higher -> lower DA price (merit-order effect)"},
    },
    "c_renewables_total_actual_mw": {
        "inputs": ["c_solar_actual_mw", "c_wind_total_actual_mw"],
        "func": _sum("c_solar_actual_mw", "c_wind_total_actual_mw"),
        "meta": {"meaning": "Actual total variable renewable generation (solar + wind)",
                 "transformation": "Sum",
                 "direction": "Higher -> lower prices; relevant mainly via its deviation from forecast"},
    },
    # --- residual load: load net of renewables, the quantity that drives balancing ---
    "c_residual_load_forecast_mw": {
        "inputs": ["c_load_forecast_mw", "c_renewables_total_forecast_mw"],
        "func": _difference("c_load_forecast_mw", "c_renewables_total_forecast_mw"),
        "meta": {"meaning": "Day-ahead forecast residual load (load - solar - wind)",
                 "transformation": "Difference (load - renewables)",
                 "direction": "Higher -> more dispatchable/imported supply needed -> higher DA price"},
    },
    "c_residual_load_actual_mw": {
        "inputs": ["c_load_actual_mw", "c_renewables_total_actual_mw"],
        "func": _difference("c_load_actual_mw", "c_renewables_total_actual_mw"),
        "meta": {"meaning": "Actual residual load (load - solar - wind)",
                 "transformation": "Difference (load - renewables)",
                 "direction": "Higher -> tighter system -> higher prices"},
    },
}

# --- forecast errors: FORECAST - ACTUAL (positive = over-forecast), the sign
# convention of the baseline literature (WE_t = W^_t - W_t, LE_t = L^_t - L_t).
# error column -> (forecast, actual, what it measures, what an over-forecast means)
FORECAST_ERRORS = {
    "c_solar_err": ("c_solar_forecast_mw", "c_solar_actual_mw", "Solar",
                    "less solar than planned -> system short -> up-regulation, higher balancing price"),
    "c_wind_onshore_err": ("c_wind_onshore_forecast_mw", "c_wind_onshore_actual_mw", "Onshore wind",
                           "less wind than planned -> system short -> up-regulation, higher balancing price"),
    "c_wind_offshore_err": ("c_wind_offshore_forecast_mw", "c_wind_offshore_actual_mw", "Offshore wind",
                            "less wind than planned -> system short -> up-regulation, higher balancing price"),
    "c_wind_total_err": ("c_wind_total_forecast_mw", "c_wind_total_actual_mw", "Total wind",
                         "less wind than planned -> system short -> up-regulation, higher balancing price"),
    "c_renewables_total_err": ("c_renewables_total_forecast_mw", "c_renewables_total_actual_mw", "Total renewables",
                               "less renewable output than planned -> system short -> up-regulation"),
    "c_load_err": ("c_load_forecast_mw", "c_load_actual_mw", "Demand",
                   "less demand than planned -> system long -> down-regulation, lower balancing price"),
    "c_residual_load_err": ("c_residual_load_forecast_mw", "c_residual_load_actual_mw", "Residual load",
                            "less residual load than planned -> system long -> down-regulation"),
}
for _name, (_forecast, _actual, _what, _over) in FORECAST_ERRORS.items():
    DERIVED_FEATURES[_name] = {
        "inputs": [_forecast, _actual],
        "func": _difference(_forecast, _actual),
        "meta": {"meaning": f"{_what} forecast error: day-ahead forecast - actual (positive = over-forecast)",
                 "transformation": "Forecast error (forecast - actual)",
                 "fva": "Forecast error (forecast - actual)",
                 "direction": f"Positive = over-forecast: {_over}"},
    }

# --- price dynamics, cross-market spreads and physical ramps, generated from
# the three small configs below. op name (column-name suffix) -> definition.
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
    "lag_1": {
        "make": lambda col: (lambda df: _per_zone(df, col).shift(1)),
        "transformation": "Previous hour's value: x[t-1]",
        "meaning": "{col} one hour earlier",
        "direction": "As {col}, one hour earlier: refers to an hour that has passed when hour t starts",
    },
}


def _register_variability(col: str, ops: list[str]):
    for op in ops:
        spec = VARIABILITY_OPS[op]
        DERIVED_FEATURES[f"{col}_{op}"] = {
            "inputs": [col],
            "func": spec["make"](col),
            "meta": {"meaning": spec["meaning"].format(col=col), "transformation": spec["transformation"],
                     "direction": spec["direction"]},
        }


# One representative price per market (id_vwap / id_close_price / ... move
# almost together, so features on each would be near-duplicates).
MARKET_PRICES = {"da": "da_price", "id": "id_vwap", "bal": "b_imbalance_price"}
PRICE_OPS = ["change_1", "abs_change_1", "std_24", "std_168", "range_24"]

# (first, second) -> x_<first>_<second>_spread = first - second.
MARKET_SPREADS = [("da", "id"), ("id", "bal"), ("da", "bal")]

# Prices as used in the spreads (baseline literature definitions):
#   DA  = day-ahead price.
#   ID  = hourly intraday VWAP; hours WITHOUT intraday trades (zero traded
#         volume, where Nord Pool leaves the VWAP empty) take the DA price,
#         so the DA-ID spread is 0 there ("no need for trade adjustment").
#         Applied inside the spread only. An hour missing from the intraday
#         data altogether stays NaN (missing data, not "no trades").
#   BAL = balancing price: the mFRR price in the dominating direction, i.e. the
#         up price in up-regulation hours, the down price in down-regulation
#         hours, the DA price without regulation (verified 2022-2024: 100 % /
#         100 % / 99.7 %); Nord Pool's 'ImbalancePrice' field, as the Nordic
#         single imbalance price is set this way. From 2025 the hourly mean of
#         the 15-min values.
# key -> (input columns, price as used in the spread, description)
SPREAD_PRICES = {
    "da": (["da_price"], lambda df: df["da_price"], "da_price"),
    "id": (["id_vwap", "da_price", "id_transaction_volume_mwh"],
           lambda df: df["id_vwap"].where(df["id_transaction_volume_mwh"] != 0, df["da_price"]),
           "id_vwap, hours without intraday trades = da_price"),
    "bal": (["b_imbalance_price"], lambda df: df["b_imbalance_price"], "b_imbalance_price"),
}

# Physical variables that get ramp / variability features. std_24 is left off
# solar and load: their 24 h std mostly measures the deterministic daily shape.
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
        "meta": {"meaning": f"Cross-market spread {_a.upper()} - {_b.upper()}: ({_da}) - ({_db})",
                 "transformation": "Spread (difference of prices)",
                 "market": f"Cross-market ({_a.upper()}-{_b.upper()})",
                 "direction": f"Positive = {_a.upper()} priced above {_b.upper()}; "
                              f"non-zero = the two market stages disagree (decoupling)"},
    }
    DERIVED_FEATURES[f"{_spread}_abs"] = {
        "inputs": [_spread],
        "func": (lambda s: lambda df: df[s].abs())(_spread),
        "meta": {"meaning": f"Absolute cross-market spread |{_a.upper()} - {_b.upper()}|",
                 "transformation": "Absolute spread",
                 "market": f"Cross-market ({_a.upper()}-{_b.upper()})",
                 "direction": "Higher = larger disagreement between market stages, regardless of sign"},
    }
    _register_variability(_spread, ["std_24"])

for _col, _ops in PHYSICAL_VARIABILITY.items():
    _register_variability(_col, _ops)

# The wind ramp one hour earlier. In the same hour, the ramp W(t) - W(t-1) shares the actual wind W(t)
# with the wind forecast error F(t) - W(t), which ties the two by an accounting identity
# (e(t) - e(t-1) = dF(t) - r(t)); one hour earlier it does not.
_register_variability("c_wind_total_actual_mw_change_1", ["lag_1"])

# --- cross-border flows, one column per interconnection. SIGN: positive =
# export from the row's zone, negative = import. Day-ahead scheduled exchange
# (hourly mean of MW = MWh per hour). A counterpart not connected to the zone
# (e.g. NL for DK2) is a structural 0.0.
FLOW_COUNTERPARTS = {"ger": "Germany", "nl": "Netherlands", "no2": "Norway (NO2)", "se3": "Sweden (SE3)",
                     "se4": "Sweden (SE4)", "dk1": "DK1 (Great Belt)", "dk2": "DK2 (Great Belt)"}
for _code, _counterpart in FLOW_COUNTERPARTS.items():
    DERIVED_FEATURES[f"da_flow_{_code}_net_export_mw"] = {
        "inputs": [f"da_flow_{_code}_export_mw", f"da_flow_{_code}_import_mw"],
        "func": _difference(f"da_flow_{_code}_export_mw", f"da_flow_{_code}_import_mw"),
        "meta": {"meaning": f"Cross-border flow between the zone and {_counterpart}: day-ahead scheduled "
                            f"exchange, export minus import (Nord Pool DayAheadFlow)",
                 "unit": "MW",
                 "transformation": "Difference (export - import), hourly mean of MW",
                 "market": "Day-ahead",
                 "direction": "Positive = export from the zone, negative = import; 0 in every hour where the "
                              "zone has no interconnection with this counterpart"},
    }

# --- hydro conditions: reservoir filling minus its median of the same ISO
# week in earlier years (see _add_reservoir_history_median).
for _area in RESERVOIR_AREAS:
    _a = _area.lower()
    DERIVED_FEATURES[f"c_reservoir_deviation_pct_{_a}"] = {
        "inputs": [f"c_reservoir_fill_pct_{_a}", f"c_reservoir_fill_median_pct_{_a}"],
        "func": _difference(f"c_reservoir_fill_pct_{_a}", f"c_reservoir_fill_median_pct_{_a}"),
        "meta": {"meaning": f"Hydro reservoir filling of {_area} minus its median for the same ISO week in "
                            f"earlier years (hydro deviation)",
                 "unit": "percentage points",
                 "transformation": "Difference (filling - median of the same ISO week in earlier years)",
                 "market": "Fundamentals (hydro)",
                 "direction": "Positive = more water than usual for the time of year -> more low-cost hydro "
                              "supply -> lower Nordic prices"},
    }

# --- calendar dummies (stored as category identifiers) ---
# Meteorological seasons (also used by the seasonal profiles in visualisation.py).
SEASON_OF_MONTH = {12: "Winter", 1: "Winter", 2: "Winter", 3: "Spring", 4: "Spring", 5: "Spring",
                   6: "Summer", 7: "Summer", 8: "Summer", 9: "Autumn", 10: "Autumn", 11: "Autumn"}
SEASONS = ["Winter", "Spring", "Summer", "Autumn"]


def _season(df: pd.DataFrame) -> pd.Series:
    """0 = winter (Dec-Feb), 1 = spring, 2 = summer, 3 = autumn (local time)."""
    return _local_time(df).dt.month.map(SEASON_OF_MONTH).map(SEASONS.index)


DERIVED_FEATURES.update({
    "fe_hour": {
        "inputs": [],
        "func": lambda df: _local_time(df).dt.hour.astype(float),
        "meta": {"meaning": "Hour of day (0-23, Copenhagen local time) — identifier for the hour-of-day dummies "
                            "(one dummy per hour; drop one if the model has a constant)",
                 "unit": "category (0-23)", "transformation": "Calendar identifier (expand to dummies in the model)",
                 "market": "Calendar", "fva": "Deterministic (calendar)",
                 "direction": "Captures the diurnal pattern"},
    },
    "fe_week_of_sample": {
        # absolute week number here; renumbered 1..N within the dataframe after trimming
        "inputs": [],
        "func": lambda df: ((_local_time(df).dt.tz_localize(None).dt.normalize()
                             - pd.Timestamp("1970-01-05")).dt.days // 7).astype(float),
        "meta": {"meaning": "Week of the sample (1 = first Monday-Sunday week in the dataframe, Copenhagen local "
                            "time) — identifier for the week-of-sample dummies",
                 "unit": "category (1..N)", "transformation": "Calendar identifier (expand to dummies in the model)",
                 "market": "Calendar", "fva": "Deterministic (calendar)",
                 "direction": "Captures seasonal / slow-moving level changes"},
    },
    "fe_month_of_sample": {
        # absolute month number (year * 12 + month); renumbered 1..N after trimming
        "inputs": [],
        "func": lambda df: (_local_time(df).dt.year * 12 + _local_time(df).dt.month).astype(float),
        "meta": {"meaning": "Month of the sample (1 = first calendar month in the dataframe, Copenhagen local "
                            "time) — identifier for the month-of-sample dummies",
                 "unit": "category (1..N)", "transformation": "Calendar identifier (expand to dummies in the model)",
                 "market": "Calendar", "fva": "Deterministic (calendar)",
                 "direction": "Captures slow level changes at monthly resolution (coarser than weekly)"},
    },
    "fe_season": {
        "inputs": [],
        "func": lambda df: (_season(df) + 1).astype(float),
        "meta": {"meaning": "Meteorological season (1 = winter Dec-Feb, 2 = spring, 3 = summer, 4 = autumn; "
                            "Copenhagen local time) — identifier for the season dummies",
                 "unit": "category (1-4)", "transformation": "Calendar identifier (expand to dummies in the model)",
                 "market": "Calendar", "fva": "Deterministic (calendar)",
                 "direction": "Captures seasonal level changes (coarser than monthly)"},
    },
    "fe_hour_of_season": {
        "inputs": [],
        "func": lambda df: (_season(df) * 24 + _local_time(df).dt.hour).astype(float),
        "meta": {"meaning": "Hour of day within the season (season x 24 + hour: 0-23 winter, 24-47 spring, "
                            "48-71 summer, 72-95 autumn; Copenhagen local time) — identifier for hour x season "
                            "dummies: a separate 24 h profile per season",
                 "unit": "category (0-95)", "transformation": "Calendar identifier (expand to dummies in the model)",
                 "market": "Calendar", "fva": "Deterministic (calendar)",
                 "direction": "Captures a diurnal pattern whose shape differs between seasons"},
    },
    "fe_hour_of_week": {
        "inputs": [],
        "func": lambda df: (_local_time(df).dt.dayofweek * 24 + _local_time(df).dt.hour).astype(float),
        "meta": {"meaning": "Hour of the week (weekday x 24 + hour: 0 = Monday 00:00, 167 = Sunday 23:00; "
                            "Copenhagen local time) — identifier for hour-of-week dummies: a separate 24 h profile "
                            "per weekday",
                 "unit": "category (0-167)", "transformation": "Calendar identifier (expand to dummies in the model)",
                 "market": "Calendar", "fva": "Deterministic (calendar)",
                 "direction": "Captures a diurnal pattern whose shape differs between weekdays"},
    },
})

RENUMBER_WITHIN_SAMPLE = ["fe_week_of_sample", "fe_month_of_sample"]  # value -> rank 1..N after trimming
MIN_EDGE_MONTH_HOURS = 24  # a first / last local month with fewer hours is merged into its neighbour


# ---------------------------------------------------------------------------
# SPEC — the columns of one dataframe and their role in the model
# ---------------------------------------------------------------------------
ROLES = ("Endogenous", "Exogenous", "Input")


@dataclass(frozen=True)
class Spec:
    """endogenous / exogenous: the model variables, as listed in main.py.
    inputs: every column they are computed from (found by make_spec)."""
    endogenous: tuple
    exogenous: tuple
    inputs: tuple

    @property
    def columns(self) -> list:
        return [*self.endogenous, *self.exogenous, *self.inputs]

    @property
    def calendar(self) -> list:
        """The calendar dummies (exogenous, stored as category identifiers)."""
        return [c for c in self.exogenous if c.startswith(CALENDAR_PREFIX)]

    def role(self, col: str) -> str:
        return ("Endogenous" if col in self.endogenous else "Exogenous" if col in self.exogenous
                else "Input" if col in self.inputs else "")

    def by_role(self, calendar: bool = False) -> dict:
        """{role: columns}; calendar dummies left out unless calendar=True."""
        return {role: [c for c in self.columns if self.role(c) == role and (calendar or c not in self.calendar)]
                for role in ROLES}


def _inputs_of(col: str) -> list:
    return DERIVED_FEATURES[col]["inputs"] if col in DERIVED_FEATURES else []


def make_spec(endogenous: list, exogenous: list) -> Spec:
    """The spec of a dataframe: the variables plus all their inputs, followed
    recursively (e.g. c_wind_total_err -> wind total forecast / actual ->
    onshore / offshore forecast / actual), in order of discovery."""
    variables = [*endogenous, *exogenous]
    repeated = sorted({c for c in variables if variables.count(c) > 1})
    if repeated:
        raise ValueError(f"Listed more than once (or as both endogenous and exogenous): {repeated}")
    unknown = [c for c in variables if c not in SOURCE_OF and c not in DERIVED_FEATURES]
    if unknown:
        raise ValueError(f"Unknown column(s) {unknown}: not a SOURCES column or a DERIVED_FEATURES entry "
                         f"in src/dataframe/building.py")
    found = []

    def collect(col: str):
        for c in _inputs_of(col):
            if c not in found:
                found.append(c)
                collect(c)

    for v in variables:
        collect(v)
    return Spec(tuple(endogenous), tuple(exogenous), tuple(c for c in found if c not in variables))


# ---------------------------------------------------------------------------
# BUILD
# ---------------------------------------------------------------------------
def _pivot_areas(df: pd.DataFrame, time_col: str, area_col: str, name: str) -> pd.DataFrame:
    """One row per (hour, area) -> one row per hour, one numeric column per
    (value, area): '<value>_<area>'. A repeated (hour, area) is refused."""
    value_cols = [c for c in df.columns if c not in (time_col, area_col) and pd.api.types.is_numeric_dtype(df[c])]
    dup = df.duplicated([time_col, area_col])
    if dup.any():
        raise ValueError(f"[{name}] {int(dup.sum())} repeated ({time_col}, {area_col}) rows — cannot pivot")
    wide = df.pivot(index=time_col, columns=area_col, values=value_cols)
    wide.columns = [f"{value}_{area}" for value, area in wide.columns]
    wide = wide.astype(float).reset_index()
    wide[area_col] = "SYSTEM"
    return wide


def _apply_value_maps(out: pd.DataFrame, cfg: dict, name: str) -> pd.DataFrame:
    """value_map (text -> number) and fill_empty (cells empty in the file)."""
    empty = {col: out[col].isna() for col in cfg.get("fill_empty", {}) if col in out.columns}
    for col, mapping in cfg.get("value_map", {}).items():
        if col in out.columns:
            unmapped = sorted(set(out[col].dropna()) - set(mapping))
            if unmapped:
                print(f"[{name}] WARNING — {col}: value(s) {unmapped} not in value_map, set to NaN")
            out[col] = out[col].map(mapping).astype(float)
    for col, mask in empty.items():
        out.loc[mask, col] = cfg["fill_empty"][col]
        print(f"[{name}] {col}: {int(mask.sum())} empty cell(s) set to {cfg['fill_empty'][col]}")
    return out


def load_source(name: str, columns: list, areas: list) -> pd.DataFrame | None:
    """The requested final columns of one SOURCES entry as a (datetime_utc,
    bidding_zone, <columns>) frame; None if the file does not exist."""
    cfg = SOURCES[name]
    if not cfg["path"].exists():
        print(f"[{name}] WARNING — file not found, its columns are left empty: {cfg['path']}")
        return None
    df = pd.read_csv(cfg["path"])
    time_col, area_col = cfg["time_col"], cfg["area_col"]
    for col in (time_col, area_col):
        if col not in df.columns:
            raise KeyError(f"[{name}] column '{col}' not in {cfg['path'].name}: {list(df.columns)}")
    if "prepare" in cfg:
        df = cfg["prepare"](df)
    if cfg.get("pivot_area"):
        df = _pivot_areas(df, time_col, area_col, name)
    raw = {final: col for col, final in cfg["rename"].items()}
    missing = [raw[c] for c in columns if raw[c] not in df.columns]
    if missing:
        raise KeyError(f"[{name}] configured column(s) not in {cfg['path'].name}: {missing}")
    out = df[[time_col, area_col, *(raw[c] for c in columns)]].rename(
        columns={time_col: "datetime_utc", area_col: "bidding_zone", **{raw[c]: c for c in columns}})
    out["datetime_utc"] = pd.to_datetime(out["datetime_utc"], utc=True)
    out["bidding_zone"] = out["bidding_zone"].astype(str)
    out = _apply_value_maps(out, cfg, name)
    if cfg.get("system_wide") or cfg.get("pivot_area"):
        out = pd.concat([out.assign(bidding_zone=zone) for zone in areas], ignore_index=True)
    dup = out.duplicated(KEY)
    if dup.any():
        keys = out.loc[dup, KEY].astype(str).agg(" ".join, axis=1).tolist()
        print(f"[{name}] WARNING — {int(dup.sum())} duplicate {tuple(KEY)} row(s), first one kept: "
              f"{keys[:10]}{' ...' if len(keys) > 10 else ''}")
        out = out[~dup]
    print(f"[{name}] loaded {len(columns)} column(s) from {cfg['path'].name}")
    return out


def _hourly_index(start, end) -> pd.DatetimeIndex:
    """Hourly UTC grid for [start, end], both dates INCLUSIVE (end's 24 hours included)."""
    end_exclusive = pd.Timestamp(end) + pd.Timedelta(days=1)
    return pd.date_range(start, end_exclusive, freq="h", tz="UTC", inclusive="left")


def _dependency_order(columns: list) -> list:
    """The derived features among `columns`, each after the derived inputs it needs."""
    order, seen = [], set()

    def visit(col: str):
        if col in seen or col not in DERIVED_FEATURES:
            return
        seen.add(col)
        for c in _inputs_of(col):
            visit(c)
        order.append(col)

    for col in columns:
        visit(col)
    return order


def _merge_partial_edge_months(grid: pd.DataFrame) -> pd.Series:
    """fe_month_of_sample with a tiny first or last month merged into the
    adjacent one: a sample ending at 23:00 UTC on 31 December ends at 00:00 on
    1 January in Copenhagen, and that single hour would get its own dummy."""
    month = grid["fe_month_of_sample"].copy()
    hours = grid.groupby("fe_month_of_sample")["datetime_utc"].nunique().sort_index()
    if len(hours) > 1 and hours.iloc[-1] < MIN_EDGE_MONTH_HOURS:
        month[month == hours.index[-1]] = hours.index[-2]
    if len(hours) > 1 and hours.iloc[0] < MIN_EDGE_MONTH_HOURS:
        month[month == hours.index[0]] = hours.index[1]
    return month


def build_dataframe(start: str, end: str, spec: Spec, areas: list) -> pd.DataFrame:
    """Hourly UTC x bidding-zone grid for [start, end] (inclusive) with the
    spec's columns: source columns left-joined, then the derived ones."""
    warmup_start = pd.Timestamp(start) - pd.Timedelta(hours=WARMUP_HOURS)
    grid = pd.MultiIndex.from_product([_hourly_index(warmup_start, end), areas], names=KEY).to_frame(index=False)

    by_source = {}
    for col in spec.columns:
        if col in SOURCE_OF:
            by_source.setdefault(SOURCE_OF[col], []).append(col)
    for name, cols in by_source.items():
        src = load_source(name, cols, areas)
        if src is None:
            grid[cols] = float("nan")
        else:
            grid = grid.merge(src, on=KEY, how="left")

    grid = grid.sort_values(KEY).reset_index(drop=True)  # per-zone lags / windows need time order
    for col in _dependency_order(spec.columns):
        grid[col] = DERIVED_FEATURES[col]["func"](grid)

    grid = grid[grid["datetime_utc"] >= pd.Timestamp(start, tz="UTC")].reset_index(drop=True)
    if "fe_month_of_sample" in grid.columns:
        grid["fe_month_of_sample"] = _merge_partial_edge_months(grid)
    for col in RENUMBER_WITHIN_SAMPLE:
        if col in grid.columns:
            grid[col] = grid[col].rank(method="dense")
    return grid[KEY + spec.columns]


# ---------------------------------------------------------------------------
# CHECKS AND SAVE
# ---------------------------------------------------------------------------
def sanity_check(df: pd.DataFrame, start: str, end: str, areas: list):
    """Row count = hourly grid x zones, unique key, no duplicate columns."""
    expected = len(_hourly_index(start, end)) * len(areas)
    problems = []
    if len(df) != expected:
        problems.append(f"row count {len(df)} != expected {expected}")
    if df.duplicated(KEY).any():
        problems.append(f"{int(df.duplicated(KEY).sum())} duplicate {tuple(KEY)} rows")
    if df.columns.duplicated().any():
        problems.append(f"duplicate column names: {df.columns[df.columns.duplicated()].tolist()}")
    if problems:
        raise RuntimeError("Sanity check failed: " + "; ".join(problems))
    print(f"  Sanity check OK: {len(df)} rows, {len(df.columns)} columns, key is unique.")


def coverage_report(df: pd.DataFrame) -> pd.DataFrame:
    """Per column: % missing and the first / last observed hour."""
    rows = []
    for col in df.columns.drop(KEY):
        observed = df[col].notna()
        rows.append({"column": col, "pct_missing": round(100 * (1 - observed.mean()), 2),
                     "first_non_null": df.loc[observed, "datetime_utc"].min() if observed.any() else None,
                     "last_non_null": df.loc[observed, "datetime_utc"].max() if observed.any() else None})
    return pd.DataFrame(rows)


def report_constant_by_zone(df: pd.DataFrame):
    """Columns constant within one zone's rows — e.g. a cross-border flow to a
    counterpart the zone is not connected to (a structural 0). Expected data,
    not a bug; the analysis steps leave such a column out for that zone."""
    print("\n  Columns constant within a zone:")
    for zone, g in df.groupby("bidding_zone"):
        constant = [f"{c} = {g[c].dropna().iloc[0]}" for c in df.columns.drop(KEY)
                    if g[c].notna().any() and g[c].nunique() == 1]
        print(f"    {zone}: {', '.join(constant) if constant else 'none'}")


def create_dataframe(name: str, start: str, end: str, spec: Spec, areas: list) -> pd.DataFrame:
    """Build, check and save data/dataframes/<name>.csv."""
    print(f"  {start} to {end}, zones {areas}")
    for role, cols in spec.by_role(calendar=True).items():
        print(f"  {role} ({len(cols)}): {', '.join(cols)}")
    df = build_dataframe(start, end, spec, areas)
    sanity_check(df, start, end, areas)
    print(coverage_report(df).to_string(index=False))
    report_constant_by_zone(df)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / f"{name}.csv"
    df.to_csv(path, index=False)
    print(f"  Saved {path} ({len(df)} rows, {len(df.columns)} columns)")
    return df


def load_dataframe(name: str, spec: Spec) -> pd.DataFrame:
    """A dataframe built earlier (for runs with the build step off)."""
    path = OUTPUT_DIR / f"{name}.csv"
    if not path.exists():
        raise FileNotFoundError(f"{path} does not exist — turn the build step on.")
    df = pd.read_csv(path)
    missing = [c for c in KEY + spec.columns if c not in df.columns]
    if missing:
        raise ValueError(f"{path.name} lacks {missing} — the spec changed since it was built; rebuild it.")
    df["datetime_utc"] = pd.to_datetime(df["datetime_utc"], utc=True)
    return df[KEY + spec.columns]
