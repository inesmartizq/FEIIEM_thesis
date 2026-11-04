"""
documentation.py — the documentation workbook of one built
dataframe (the "documentation" step of main.py):
data/dataframes/documentation/<name>_documentation.xlsx.

Sheets:
    README        the dataframe (period, zones, endogenous / exogenous
                  variables, inputs) and the definitions of every check.
    metadata      one row per column: model role, literature definition and
                  deviations (model variables), market, meaning, unit, timing
                  (DELIVERY time vs INFORMATION / availability time), source,
                  leakage, missingness, constant / near-constant, duplicates.
    distribution  per column x scope (both zones, DK1, DK2): mean, median, std,
                  quantiles, skewness, kurtosis, zero / negative / extreme %.

Where the metadata comes from:
    source columns   SOURCE_META (shared by every column of a SOURCES entry)
                     + COLUMN_META (per column; may override the source).
    derived columns  the "meta" of their DERIVED_FEATURES entry; timing fields
                     (availability, leakage, horizon) are INHERITED from the
                     inputs, so they cannot drift out of sync.
    model variables  LITERATURE: name, definition, interpretation, literature
                     source and deviation from the literature.
A column without metadata is marked UNDOCUMENTED and reported.
"""

from pathlib import Path

import pandas as pd

from dataframe.building import (DERIVED_FEATURES, FLOW_COUNTERPARTS, FORECAST_ERRORS, KEY, RESERVOIR_AREAS,
                                SOURCE_OF, Spec)

# ----------------------- CHECK THRESHOLDS -----------------------
NEAR_CONSTANT_SHARE = 0.95   # most frequent value covers >= this share of a zone's non-null rows
DUPLICATE_ABS_CORR = 0.99    # |Pearson r| at or above this vs. another column -> suspected duplicate
COPY_LAGS = {24: "1 day", 168: "1 week", 336: "2 weeks"}  # hours back at which a forecast may repeat a value
COPIED_SHARE = 0.05          # a forecast repeating a value in >= this share of hours -> suspected copies
FORECAST_OF = {forecast: actual for forecast, actual, *_ in FORECAST_ERRORS.values()}  # forecast -> its actual
EXTREME_IQR_MULT = 3.0       # outside [Q1 - k*IQR, Q3 + k*IQR] -> extreme value
QUANTILES = [0.01, 0.05, 0.25, 0.50, 0.75, 0.95, 0.99]

UNDOCUMENTED = "UNDOCUMENTED"
LITERATURE_REFERENCE = "Spodniak et al. (2019); also Nieminen et al. (2023)"

# ---------------------------------------------------------------------------
# SOURCE-LEVEL METADATA — keyed by the SOURCES name in building.py.
#   market, source, frequency, delivery_ts (what the row timestamp means),
#   availability (when the value is known), fva (forecast vs actual), horizon,
#   leakage ("Yes"/"No", see README), leakage_note, transformation.
# ---------------------------------------------------------------------------
_DA_COMMON = {
    "market": "Day-ahead",
    "frequency": "Hourly (60-min MTU until 2025-09-30; 15-min MTU from 2025-10-01, "
                 "averaged to the hourly mean in import_da_pipeline.py)",
    "delivery_ts": "Start of the delivery hour, UTC",
    "availability": "D-1: SDAC day-ahead results are published ~12:45-13:00 CET on the day before delivery, "
                    "for every hour of delivery day D. Known before delivery.",
    "fva": "Market outcome (ex-ante clearing result)",
    "horizon": "D-1 (published 11-35 h before delivery)",
    "leakage": "No",
    "leakage_note": "Known before delivery hour t; usable at row t for any decision taken after DA results "
                    "are published on D-1.",
    "transformation": "Raw (hourly)",
}
_EX_POST_NOTE = ("Not known before delivery hour t is over. Using row t contemporaneously to explain/predict "
                 "anything decided before or during hour t leaks — lag it by >= 1 h (more if the publication "
                 "delay matters).")

SOURCE_META = {
    "mfrr": {
        "market": "Balancing",
        "source": "Nord Pool Data Portal API — Nordic balancing (mFRR) market data (import_balancing_pipeline.py)",
        "frequency": "Hourly (any sub-hourly API values averaged to the hourly mean in import)",
        "delivery_ts": "Start of the delivery (operating) hour, UTC",
        "availability": "Ex-post: activations happen during the delivery hour; volumes and prices are published "
                        "after it (balancing price may be preliminary, then final). Exact publication delay is "
                        "not recorded in the data.",
        "fva": "Actual (realised outcome)",
        "horizon": "None (realised, ex-post)",
        "leakage": "Yes",
        "leakage_note": _EX_POST_NOTE,
        "transformation": "Raw (hourly mean)",
    },
    "intraday": {
        "market": "Intraday",
        "source": "Nord Pool Data Portal API — continuous intraday (SIDC) hourly trading statistics "
                  "(import_intraday_pipeline.py)",
        "frequency": "Hourly per delivery hour (15-min product statistics, where present, recombined to hourly "
                     "in import: prices volume-weighted, volumes summed)",
        "delivery_ts": "Start of the delivery hour of the traded product, UTC",
        "availability": "Builds up while the product trades (from D-1 afternoon CET until intraday gate closure "
                        "shortly before delivery). The hourly statistics are FINAL only at gate closure, i.e. "
                        "just before hour t starts.",
        "fva": "Market outcome (traded prices / volumes)",
        "horizon": "D-1 afternoon up to gate closure before delivery",
        "leakage": "No",
        "leakage_note": "Final just before delivery hour t (at gate closure). No leakage for a decision point "
                        "after ID gate closure (e.g. explaining balancing in hour t); DOES leak for an earlier "
                        "decision point (D-1, or hours ahead).",
        "transformation": "Raw (hourly aggregate of trades)",
    },
    "afrr": {
        "market": "Balancing",
        "source": "Energinet Energi Data Service (pre-PICASSO, until 2024-10-01) + ENTSO-E Transparency "
                  "Platform A24 aggregated balancing energy bids (post-PICASSO, from 2024-10-02), stitched in "
                  "import_balancing_pipeline.py",
        "frequency": "Hourly (ENTSO-E 15-min MW values averaged to the hourly mean in import)",
        "delivery_ts": "Start of the delivery (operating) hour, UTC",
        "availability": "Ex-post: published after the delivery hour. Exact publication delay is not recorded "
                        "in the data.",
        "fva": "Actual (realised outcome)",
        "horizon": "None (realised, ex-post)",
        "leakage": "Yes",
        "leakage_note": _EX_POST_NOTE,
        "transformation": "Raw (hourly mean)",
    },
    "da_nordpool_flows": {
        **_DA_COMMON,
        "source": "Nord Pool Data Portal API — day-ahead scheduled exchanges per border (import_da_pipeline.py)",
        "fva": "Scheduled (commercial DA market-coupling schedule, NOT physical flow)",
    },
    "da_nordpool_prices": {
        **_DA_COMMON,
        "source": "Nord Pool Data Portal API — day-ahead (SDAC) prices, EUR (import_da_pipeline.py)",
    },
    "da_nordpool_volumes": {
        **_DA_COMMON,
        "source": "Nord Pool Data Portal API — day-ahead (SDAC) cleared volumes (import_da_pipeline.py)",
    },
    "reservoir": {
        "market": "Fundamentals (hydro)",
        "source": "Nord Pool Data Portal API — Reservoir report: weekly hydro reservoir filling per area "
                  "(import_extras.py, download_reservoir)",
        "frequency": "Weekly (ISO week, Monday-Sunday in Nordic local time); the week's value is repeated on "
                     "every hour of that week (step), so it changes once a week",
        "delivery_ts": "Start of the delivery hour, UTC; the value is the filling reported for the ISO week "
                       "containing that hour",
        "availability": "Ex-post weekly report, published after the week. Because the value is applied to every "
                        "hour of its OWN week, hours early in the week see a value that was not yet published "
                        "(up to ~7 days of look-ahead).",
        "fva": "Actual (measured)",
        "horizon": "None (measured, weekly)",
        "leakage": "Yes",
        "leakage_note": "Weekly value applied to its own week: not known during that week. Lag by one week "
                        "(168 h) to use only published values.",
        "transformation": "Weekly value held constant over the hours of its week",
    },
    "da_nordpool_system_price": {
        **_DA_COMMON,
        "source": "Nord Pool Data Portal API — DayAheadSystem: system price and turnover, EUR "
                  "(import_extras.py, download_system_price)",
    },
    "da_forecasts_and_actual": {
        # Defaults describe the FORECAST columns; actual columns override.
        "market": "Physical (system fundamentals)",
        "source": "Nord Pool Data Portal API — Power System data: production/consumption prognoses and actuals "
                  "(import_forecasts_pipeline.py)",
        "frequency": "Hourly (production 15-min values averaged to the hourly mean in import; consumption "
                     "natively hourly)",
        "delivery_ts": "Start of the delivery hour the forecast/measurement refers to, UTC",
        "availability": "D-1 day-ahead prognosis. ASSUMPTION, NOT VERIFIED: the data carries no issue/publication "
                        "timestamp, so whether it is published before or after DA gate closure (12:00 CET D-1) "
                        "is unknown.",
        "fva": "Forecast",
        "horizon": "D-1 (day-ahead prognosis)",
        "leakage": "No",
        "leakage_note": "Known before delivery (D-1). Check the issue time before relying on it as information "
                        "available at DA gate closure.",
        "transformation": "Raw (hourly mean)",
    },
}

# The wind and solar prognoses: Nord Pool's DayAhead series, which matches the ENTSO-E Transparency "day-ahead
# forecast at 18.00" (Nord Pool shows the same three series: DayAhead, Intraday at 08:00, Current).
_RES_FORECAST_TIMING = {
    "availability": "D-1, 18:00 Brussels time: the ENTSO-E 'day-ahead forecast at 18.00' for wind and solar "
                    "(Transparency Regulation Art. 14.1.d), the most recent forecast at 18:00 the day before delivery, "
                    "republished by Nord Pool as its DayAhead prognosis. That is 6 hours AFTER the day-ahead gate "
                    "closure (12:00 CET): day-ahead bids could not use it.",
    "horizon": "D-1 18:00 (6-30 h before delivery)",
    "leakage_note": "Known before delivery, but after day-ahead gate closure: for a decision taken at gate closure it "
                    "holds 6 hours of later information.",
}

# The consumption prognosis and actual: Nord Pool's republication of the ENTSO-E total load (Art. 6.1.b / 6.1.a).
_LOAD_FORECAST_TIMING = {
    "availability": "D-1, at the latest 2 hours before day-ahead gate closure (so by 10:00 CET): the ENTSO-E day-ahead "
                    "forecast of the total load (Transparency Regulation Art. 6.1.b), republished by Nord Pool. Updated "
                    "only for a change of at least 10 % in an hour. ASSUMPTION: the stored value is this day-ahead "
                    "forecast; Nord Pool's file was last updated on the delivery day, and any later update is taken to "
                    "be minor.",
    "horizon": "D-1 by 10:00 (14-38 h before delivery)",
    "leakage_note": "Known before day-ahead gate closure.",
}

_ACTUAL_OVERRIDE = {
    "availability": "Ex-post: measured during the delivery hour, published after it. Exact publication delay is "
                    "not recorded in the data.",
    "fva": "Actual (measured)",
    "horizon": "None (measured)",
    "leakage": "Yes",
    "leakage_note": _EX_POST_NOTE,
}

# ---------------------------------------------------------------------------
# COLUMN-LEVEL METADATA for source columns: meaning, unit, direction,
# optional geography, plus any SOURCE_META field to override for this column.
# ---------------------------------------------------------------------------
COLUMN_META = {
    # --- mFRR / balancing (Nord Pool) ---
    "b_mfrr_accepted_up_mw": {
        "meaning": "Accepted mFRR up-regulation bid volume (Nord Pool 'acceptedUpBidVolume')",
        "unit": "MW", "direction": "Higher = more upward reserve accepted; tends to rise when the system is short",
    },
    "b_mfrr_accepted_down_mw": {
        "meaning": "Accepted mFRR down-regulation bid volume (Nord Pool 'acceptedDownBidVolume')",
        "unit": "MW", "direction": "Higher = more downward reserve accepted; tends to rise when the system is long",
    },
    "b_mfrr_activated_up_mw": {
        "meaning": "Activated mFRR up-regulation volume",
        "unit": "MW (hourly mean)", "direction": "Rises when the system is short (positive residual-load error)",
    },
    "b_mfrr_activated_down_mw": {
        "meaning": "Activated mFRR down-regulation volume",
        "unit": "MW (hourly mean)", "direction": "Rises when the system is long (negative residual-load error)",
    },
    "b_mfrr_up_price": {
        "meaning": "mFRR up-regulation price",
        "unit": "EUR/MWh", "direction": ">= DA price when up-regulation occurs; spikes in scarcity",
    },
    "b_mfrr_down_price": {
        "meaning": "mFRR down-regulation price",
        "unit": "EUR/MWh", "direction": "<= DA price when down-regulation occurs; can be negative in surplus hours",
    },
    "b_imbalance_price": {
        "label": "Balancing price (P_BAL)",
        "meaning": "Balancing (regulating power) price P_BAL: the mFRR price in the dominating direction, i.e. the "
                   "up price in up-regulation hours, the down price in down-regulation hours, the DA price without "
                   "regulation (verified 2022-2024: 100 % / 100 % / 99.7 %). Taken from Nord Pool's mFRR data, field "
                   "'ImbalancePrice': in the Nordic single-price system the imbalance settlement price is set this "
                   "way. From 2025 the hourly mean of the 15-min values",
        "unit": "EUR/MWh",
        "direction": "Above DA price when the system is short, below when long; extremes = balancing stress",
    },
    "b_dominating_direction": {
        "meaning": "Dominating regulation direction in the hour: Nord Pool 'Up' -> +1, 'Down' -> -1, empty -> 0 "
                   "(no regulation: in 2022-2024 the balancing price equals the DA price and mFRR activation is "
                   "zero in 99-100 % of those hours; in 2025 only 40 % / 52 %, as hourly values aggregate 15-min "
                   "states). Hourly value = most frequent 15-min direction in that hour; ties broken by the "
                   "hour's net mFRR activation (0 -> no direction).",
        "unit": "+1 / 0 / -1",
        "direction": "+1 = system short (up-regulation); -1 = system long (down-regulation); 0 = none",
        "transformation": "Categorical mapped to numeric (Up=+1, none=0, Down=-1)",
    },
    # --- intraday (Nord Pool) ---
    "id_high_price": {"meaning": "Highest intraday trade price for the delivery hour",
                      "unit": "EUR/MWh", "direction": "Spikes signal intraday scarcity / late shortfalls"},
    "id_low_price": {"meaning": "Lowest intraday trade price for the delivery hour",
                     "unit": "EUR/MWh", "direction": "Drops signal intraday surplus / late renewable upside"},
    "id_open_price": {"meaning": "First intraday trade price for the delivery hour",
                      "unit": "EUR/MWh", "direction": "Close to DA price; early intraday information",
                      "availability": "At the first trade for the product (from D-1 afternoon CET onward); "
                                      "known earlier than the other intraday statistics."},
    "id_close_price": {"meaning": "Last intraday trade price before gate closure",
                       "unit": "EUR/MWh", "direction": "Most up-to-date market view before delivery"},
    "id_vwap": {"meaning": "Volume-weighted average intraday price (all trades for the delivery hour)",
                "unit": "EUR/MWh", "direction": "Above DA = market turned shorter after DA; below = longer"},
    "id_vwap_1h": {"meaning": "VWAP of trades in the last 1 h of trading (Nord Pool 'averagePriceLast1H')",
                   "unit": "EUR/MWh", "direction": "Late-trading price; closest ID proxy for the balancing state"},
    "id_vwap_3h": {"meaning": "VWAP of trades in the last 3 h of trading (Nord Pool 'averagePriceLast3H')",
                   "unit": "EUR/MWh", "direction": "Late-trading price; closest ID proxy for the balancing state"},
    "id_transaction_volume_mwh": {"meaning": "Total intraday traded volume for the delivery hour",
                                  "unit": "MWh",
                                  "direction": "Higher = more re-balancing after DA (larger forecast updates)"},
    "id_buy_volume_mwh": {"meaning": "Intraday buy volume for the delivery hour",
                          "unit": "MWh", "direction": "Higher = zone buying back shortfalls intraday"},
    "id_sell_volume_mwh": {"meaning": "Intraday sell volume for the delivery hour",
                           "unit": "MWh", "direction": "Higher = zone selling surplus intraday"},
    # --- aFRR ---
    "b_afrr_activated_up_mw": {"meaning": "Activated aFRR up-regulation energy",
                               "unit": "MW (hourly mean = MWh per hour)", "direction": "Rises when the system is short"},
    "b_afrr_activated_down_mw": {"meaning": "Activated aFRR down-regulation energy",
                                 "unit": "MW (hourly mean = MWh per hour)", "direction": "Rises when the system is long"},
    "b_afrr_offered_up_mw": {"meaning": "Offered aFRR up-regulation energy bid volume",
                             "unit": "MW (hourly mean)", "direction": "Higher = more upward flexibility available",
                             "availability": "Bids are submitted before delivery, but the data is published "
                                             "ex-post; treated as ex-post (conservative)."},
    "b_afrr_offered_down_mw": {"meaning": "Offered aFRR down-regulation energy bid volume",
                               "unit": "MW (hourly mean)", "direction": "Higher = more downward flexibility available",
                               "availability": "Bids are submitted before delivery, but the data is published "
                                               "ex-post; treated as ex-post (conservative)."},
    "b_afrr_unavailable_up_mw": {"meaning": "Unavailable aFRR up-regulation bid volume (ENTSO-E A24)",
                                 "unit": "MW (hourly mean)", "direction": "Higher = less usable upward flexibility"},
    "b_afrr_unavailable_down_mw": {"meaning": "Unavailable aFRR down-regulation bid volume (ENTSO-E A24)",
                                   "unit": "MW (hourly mean)", "direction": "Higher = less usable downward flexibility"},
    # --- day-ahead prices / volumes ---
    "da_system_price": {"meaning": "Nord Pool day-ahead system price (unconstrained Nordic reference price; the "
                                   "same value for every zone)",
                        "unit": "EUR/MWh", "geography": "Nordic system (copied to every zone row)",
                        "direction": "Zone price differs from it when transmission is congested"},
    "da_system_turnover_mw": {"meaning": "Nord Pool day-ahead system turnover (traded volume of the whole Nordic "
                                         "system; the same value for every zone)",
                              "unit": "MW (hourly mean = MWh per hour)",
                              "geography": "Nordic system (copied to every zone row)",
                              "direction": "Higher = more energy traded day-ahead in the Nordic system"},
    "da_price": {"label": "Day-ahead price", "meaning": "Day-ahead (SDAC) clearing price of the row's bidding zone",
                 "unit": "EUR/MWh", "direction": "Low/negative with high wind+solar; high with high residual load"},
    "da_buy_volume_mw": {"meaning": "Day-ahead cleared buy (demand) volume",
                         "unit": "MW (= MWh per hour)", "direction": "Tracks expected load"},
    "da_sell_volume_mw": {"meaning": "Day-ahead cleared sell (supply) volume",
                          "unit": "MW (= MWh per hour)", "direction": "Tracks expected local generation"},
    # --- forecasts / actuals ---
    "c_solar_forecast_mw": {"meaning": "Day-ahead solar generation forecast", "unit": "MW (hourly mean)",
                            "direction": "Higher -> lower DA price midday", **_RES_FORECAST_TIMING},
    "c_wind_onshore_forecast_mw": {"meaning": "Day-ahead onshore wind generation forecast",
                                   "unit": "MW (hourly mean)", "direction": "Higher -> lower DA price",
                                   **_RES_FORECAST_TIMING},
    "c_wind_offshore_forecast_mw": {"meaning": "Day-ahead offshore wind generation forecast",
                                    "unit": "MW (hourly mean)", "direction": "Higher -> lower DA price",
                                    **_RES_FORECAST_TIMING},
    "c_load_forecast_mw": {"meaning": "Day-ahead consumption (load) forecast", "unit": "MW",
                           "direction": "Higher -> higher DA price", **_LOAD_FORECAST_TIMING},
    "c_solar_actual_mw": {"meaning": "Actual solar generation", "unit": "MW (hourly mean)",
                          "direction": "Relevant mainly via its deviation from forecast", **_ACTUAL_OVERRIDE},
    "c_wind_onshore_actual_mw": {"meaning": "Actual onshore wind generation", "unit": "MW (hourly mean)",
                                 "direction": "Relevant mainly via its deviation from forecast", **_ACTUAL_OVERRIDE},
    "c_wind_offshore_actual_mw": {"meaning": "Actual offshore wind generation", "unit": "MW (hourly mean)",
                                  "direction": "Relevant mainly via its deviation from forecast", **_ACTUAL_OVERRIDE},
    "c_load_actual_mw": {"meaning": "Actual total load (ENTSO-E Art. 6.1.a): net generation - exports + imports - "
                                    "energy absorbed by storage, losses included. Not metered consumption: in DK1 and "
                                    "DK2 partly measured, partly extrapolated", "unit": "MW",
                         "direction": "Relevant mainly via its deviation from forecast", **_ACTUAL_OVERRIDE,
                         "availability": "Ex-post: published at the latest one hour after the hour (Art. 6.1.a); for "
                                         "DK1 and DK2 not updated afterwards."},
}

# Day-ahead flows: every border x import / export / net position.
for _code, _label in {"total": "all borders combined", **FLOW_COUNTERPARTS}.items():
    _geo = ("Row zone (DK1/DK2), all borders" if _code == "total"
            else f"Row zone (DK1/DK2) <-> {_label} border (structural 0 for a zone without this border)")
    _of = "over all borders" if _code == "total" else f"with {_label}"
    COLUMN_META[f"da_flow_{_code}_import_mw"] = {
        "meaning": f"Day-ahead scheduled import {_of}", "unit": "MW", "geography": _geo,
        "direction": "Higher when the row zone is relatively expensive/short vs. neighbours"}
    COLUMN_META[f"da_flow_{_code}_export_mw"] = {
        "meaning": f"Day-ahead scheduled export {_of}", "unit": "MW", "geography": _geo,
        "direction": "Higher when the row zone is relatively cheap/long (e.g. high wind)"}
    COLUMN_META[f"da_flow_{_code}_net_position_mw"] = {
        "meaning": f"Day-ahead scheduled net position {_of} (Nord Pool 'netPosition')", "unit": "MW",
        "geography": _geo,
        # sign checked in the data: total net position has corr = -1 with (export - import)
        "direction": "Positive = row zone is a net importer (checked in the data: moves exactly with import - export)"}

# Hydro reservoirs, one column per area (the same value on every DK1 / DK2 row).
_COUNTRIES = {"NO": "Norway", "SE": "Sweden", "FI": "Finland"}


def _reservoir_label(area: str) -> str:
    return f"{_COUNTRIES[area]} (country total)" if area in _COUNTRIES else f"{_COUNTRIES[area[:2]]}, bidding area {area}"


for _area in RESERVOIR_AREAS:
    _label = _reservoir_label(_area)
    COLUMN_META[f"c_reservoir_fill_pct_{_area.lower()}"] = {
        "meaning": f"Hydro reservoir filling, {_label}: stored energy as % of reservoir capacity (Nord Pool "
                   f"'utilizationPercentage')",
        "unit": "% of capacity", "geography": f"{_label} (copied to every DK1 / DK2 row)",
        "direction": "Higher filling -> more low-cost hydro supply in the Nordic system -> lower Nordic prices; "
                     "the seasonal cycle (spring melt) dominates"}
    COLUMN_META[f"c_reservoir_fill_median_pct_{_area.lower()}"] = {
        "label": f"Median reservoir filling of earlier years, {_label}",
        "meaning": f"Median hydro reservoir filling of the same ISO week over the EARLIER years in the data "
                   f"(reservoir_weekly.csv, from 2021), {_label}: the reference of the hydro deviation",
        "unit": "% of capacity", "geography": f"{_label} (copied to every DK1 / DK2 row)",
        "direction": "Typical filling for the time of year",
        "availability": "Known in advance: computed from earlier years only",
        "fva": "Historical reference (median of earlier years)", "horizon": "Known in advance",
        "leakage": "No", "leakage_note": "Uses only ISO years before the row's ISO year.",
        "transformation": "Median of the same ISO week over the earlier ISO years (NaN without earlier years), "
                          "held constant over the hours of its week"}

KEY_META = {
    "datetime_utc": {"meaning": "DELIVERY timestamp: start of the delivery hour, in UTC. This is NOT when any value "
                                "was published; see the availability column for each feature.",
                     "unit": "datetime (UTC)", "market": "Key", "transformation": "Key"},
    "bidding_zone": {"meaning": "Bidding zone the row refers to",
                     "unit": "categorical", "market": "Key", "transformation": "Key"},
}

_WIND_RAMP = {
    "name": "Wind ramp",
    "definition": "R_t = W_t - W_(t-1) (hourly change in actual wind production; positive = ramping up)",
    "interpretation": "Sudden changes in intermittent output that flexible resources must accommodate",
    "literature_source": "ENTSO-E: actual wind generation",
    "deviation": "Nord Pool actual production (onshore + offshore) instead of ENTSO-E.",
}

# ---------------------------------------------------------------------------
# LITERATURE — the model variables of the baseline literature
# (LITERATURE_REFERENCE): name, definition, interpretation, the data source in
# the literature and every known deviation of this dataframe from it.
# ---------------------------------------------------------------------------
LITERATURE = {
    "x_da_id_spread": {
        "name": "DA-ID spread",
        "definition": "S_DA-ID = P_DA - P_ID; P_ID = hourly volume-weighted intraday price, hours without "
                      "intraday trades replaced by P_DA",
        "interpretation": "Adjustment need due to supply/demand forecasting errors",
        "literature_source": "ENTSO-E / Nord Pool (DA); Nord Pool FTP (ID)",
        "deviation": "ID VWAP from the Nord Pool Data Portal (continuous intraday, SIDC) instead of the Nord Pool "
                     "FTP server; where Nord Pool delivers 15-min products the hourly VWAP is their "
                     "volume-weighted mean.",
    },
    "x_da_bal_spread": {
        "name": "DA-BAL spread",
        "definition": "S_DA-BAL = P_DA - P_BAL; P_BAL = balancing (regulating power) price by regulation direction "
                      "(up price / down price / DA price when no regulation)",
        "interpretation": "Scarcity of balancing resources; computed ex-post (balancing price disclosed with a delay)",
        "literature_source": "ENTSO-E / Nord Pool (DA); ENTSO-E (BAL)",
        "deviation": "P_BAL = Nord Pool's mFRR data, field 'ImbalancePrice' (in the Nordic single-price system the "
                     "imbalance settlement price is the mFRR price of the dominating direction). Verified for "
                     "2022-2024 to equal the direction-based regulating price (up hours: = up price 100 %; down "
                     "hours: = down price 100 %; no regulation: = DA price 99.7 %). From March 2025 (mFRR EAM, "
                     "15-min settlement) it is the hourly mean of the 15-min values, which cannot be rebuilt from an "
                     "hourly direction.",
    },
    "x_id_bal_spread": {
        "name": "ID-BAL spread",
        "definition": "S_ID-BAL = P_ID - P_BAL (P_ID and P_BAL as above)",
        "interpretation": "Incentive (opportunity cost) to reduce imbalances in the intraday market",
        "literature_source": "Nord Pool FTP (ID); ENTSO-E (BAL)",
        "deviation": "As for the DA-ID and DA-BAL spreads.",
    },
    "c_wind_total_err": {
        "name": "Wind forecast error",
        "definition": "WE_t = W^_t - W_t (forecast - actual; positive = over-forecast), onshore + offshore wind",
        "interpretation": "Wind surprise the short-term markets must absorb",
        "literature_source": "ENTSO-E: forecast 14.1.D (published 18:00 CET on D-1) and actual generation",
        "deviation": "None in the forecast: Nord Pool republishes the ENTSO-E 14.1.D day-ahead forecast (the TSO's "
                     "forecast as of 18:00 D-1), the one of the literature, and it is used as published. ASSUMPTION, "
                     "as in the literature: curtailment is not treated separately, so in hours when wind farms stop "
                     "(e.g. at negative prices) the error includes the curtailed output.",
    },
    "c_load_err": {
        "name": "Demand forecast error",
        "definition": "LE_t = L^_t - L_t (forecast - actual; positive = over-forecast)",
        "interpretation": "Demand surprise the short-term markets must absorb",
        "literature_source": "ENTSO-E: load forecast and actual load",
        "deviation": "None: Nord Pool republishes the ENTSO-E day-ahead total-load forecast (6.1.B, published by 10:00 "
                     "D-1) and actual total load (6.1.A). ASSUMPTION: the stored forecast is the day-ahead version; "
                     "Nord Pool's file was last updated on the delivery day, and any later update (allowed for a "
                     "change of at least 10 %) is taken to be minor.",
    },
    "c_wind_total_actual_mw_change_1": _WIND_RAMP,
    "c_wind_total_actual_mw_change_1_lag_1": {
        **_WIND_RAMP,
        "name": "Wind ramp, previous hour",
        "definition": "R_(t-1) = W_(t-1) - W_(t-2): the wind ramp of the previous hour (positive = ramping up)",
        "deviation": _WIND_RAMP["deviation"] + " Enters with a one-hour lag: in the same hour the ramp shares the "
                     "actual wind W_t with the wind forecast error F_t - W_t, which ties the two by the identity "
                     "e_t - e_(t-1) = (F_t - F_(t-1)) - R_t. The sources do not state in which hour the ramp enters.",
    },
    **{f"da_flow_{code}_net_export_mw": {
        "name": f"Cross-border flow, {counterpart}",
        "definition": f"F_t = export_t - import_t on the interconnection with {counterpart} (positive = export from "
                      f"the zone, negative = import)",
        "interpretation": "Use of the interconnection: how much of the zone's imbalance is moved across the border",
        "literature_source": "— (replaces the literature's price-based bottleneck indicator)",
        "deviation": "Replaces the bottleneck indicator (zone price != system price), which was 1 in 99.6-99.9 % "
                     "of hours for DK1/DK2. Day-ahead scheduled exchange, not physical flows (not in the data); "
                     "no Great Britain (Viking Link) connection in the data. A connection the zone does not have "
                     "(0 in every hour) is left out for that zone.",
    } for code, counterpart in FLOW_COUNTERPARTS.items()},
    **{f"c_reservoir_deviation_pct_{area.lower()}": {
        "name": f"Hydro deviation, {_reservoir_label(area)}",
        "definition": "H_t = reservoir filling (% of capacity) minus its historical median for the same week of "
                      "the year",
        "interpretation": "Seasonal hydrological conditions: water available for low-cost hydro supply",
        "literature_source": "Reservoir data (NO, SE, FI)",
        "deviation": "Nord Pool weekly reservoir filling; the median uses only the earlier years in the data (from "
                     "2021: 4 years for 2025), not a long historical record. The weekly value is applied to every "
                     "hour of its own Monday-Sunday week (up to ~7 days of look-ahead).",
    } for area in RESERVOIR_AREAS},
    "fe_hour": {
        "name": "Hour dummies",
        "definition": "D_hour,h,t = 1[hour(t) = h], one dummy per hour",
        "interpretation": "Diurnal pattern",
        "literature_source": "Calendar",
        "deviation": "Stored as an identifier; expand to dummies at estimation.",
    },
    "fe_week_of_sample": {
        "name": "Week-of-sample dummies",
        "definition": "D_week,w,t = 1[week(t) = w], one dummy per week of the sample",
        "interpretation": "Seasonal pattern",
        "literature_source": "Calendar",
        "deviation": "Stored as an identifier; expand to dummies at estimation.",
    },
    "fe_month_of_sample": {
        "name": "Month-of-sample dummies",
        "definition": "D_month,m,t = 1[month(t) = m], one dummy per calendar month of the sample",
        "interpretation": "Seasonal pattern (slow movement of the level)",
        "literature_source": "Calendar (the literature uses week-of-sample dummies)",
        "deviation": "Coarser than the literature's week-of-sample dummies. Stored as an identifier; expand to "
                     "dummies at estimation.",
    },
    "fe_season": {
        "name": "Season dummies",
        "definition": "D_season,s,t = 1[season(t) = s], one dummy per meteorological season",
        "interpretation": "Seasonal pattern (level per season)",
        "literature_source": "Calendar (the literature uses week-of-sample dummies)",
        "deviation": "Much coarser than the literature's week-of-sample dummies. Stored as an identifier; expand "
                     "to dummies at estimation.",
    },
    "fe_hour_of_season": {
        "name": "Hour x season dummies",
        "definition": "D_h,s,t = 1[hour(t) = h and season(t) = s], one dummy per hour of each season",
        "interpretation": "Diurnal pattern whose shape differs between seasons (e.g. solar-driven midday hours "
                          "in summer); also the level per season",
        "literature_source": "Calendar (the literature uses separate hour and week-of-sample dummies)",
        "deviation": "Replaces the separate hour and seasonal dummies by their interaction. Stored as an "
                     "identifier; expand to dummies at estimation.",
    },
    "fe_hour_of_week": {
        "name": "Hour-of-week dummies",
        "definition": "D_h,t = 1[hour of week(t) = h], one dummy per hour of the week (168)",
        "interpretation": "Diurnal pattern whose shape differs between weekdays",
        "literature_source": "Calendar (the literature uses hour dummies)",
        "deviation": "Replaces the hour dummies by one per hour of the week. Stored as an identifier; expand to "
                     "dummies at estimation.",
    },
}

METADATA_COLUMNS = [
    ("dataframe", "Dataframe name"),
    ("feature", "Feature"),
    ("role", "Model role"),
    ("name", "Model variable"),
    ("definition", "Definition (literature)"),
    ("interpretation", "Interpretation (literature)"),
    ("literature_source", "Source in the literature"),
    ("deviation", "Deviation from the literature"),
    ("origin", "Origin"),
    ("market", "Market"),
    ("geography", "Geography"),
    ("meaning", "Physical/economic meaning"),
    ("unit", "Unit"),
    ("frequency", "Frequency"),
    ("delivery_ts", "Timestamp meaning (DELIVERY time of the row)"),
    ("availability", "Availability time (INFORMATION / publication time)"),
    ("source", "Source"),
    ("fva", "Forecast vs actual"),
    ("horizon", "Forecast horizon"),
    ("transformation", "Transformation"),
    ("direction", "Expected direction"),
    ("leakage", "Potential leakage"),
    ("leakage_note", "Leakage note"),
    ("pct_missing", "Missingness %"),
    ("first_non_null", "First non-null (UTC)"),
    ("last_non_null", "Last non-null (UTC)"),
    ("constant", "Constant/near-constant"),
    ("constant_detail", "Constant/near-constant detail"),
    ("duplicate", "Suspected duplicates"),
    ("duplicate_detail", "Suspected duplicates detail"),
    ("copied", "Copied forecast values"),
    ("copied_detail", "Copied forecast values detail"),
]
WRAPPED_METADATA = {"Model variable", "Definition (literature)", "Interpretation (literature)",
                    "Source in the literature", "Deviation from the literature", "Physical/economic meaning",
                    "Timestamp meaning (DELIVERY time of the row)", "Availability time (INFORMATION / publication time)",
                    "Source", "Frequency", "Expected direction", "Leakage note", "Constant/near-constant detail",
                    "Suspected duplicates detail", "Geography", "Forecast vs actual", "Forecast horizon",
                    "Transformation", "Copied forecast values detail"}


# ---------------------------------------------------------------------------
# METADATA RESOLUTION
# ---------------------------------------------------------------------------
def _combine(values: list[str], mixed_prefix: str = "Mixed") -> str:
    unique = list(dict.fromkeys(v for v in values if v))
    return unique[0] if len(unique) == 1 else f"{mixed_prefix}: " + " | ".join(unique)


class _MetadataResolver:
    def __init__(self):
        self.cache: dict[str, dict] = {}
        self.undocumented: list[str] = []

    def describe(self, col: str) -> dict:
        if col not in self.cache:
            self.cache[col] = self._describe(col)
        return self.cache[col]

    def _describe(self, col: str) -> dict:
        if col in KEY_META:
            return {"origin": "Key", "geography": "-", **KEY_META[col]}

        if col in SOURCE_OF:
            src = SOURCE_OF[col]
            if src not in SOURCE_META or col not in COLUMN_META:
                self.undocumented.append(col)
            return {"origin": f"Source ({src})", "geography": "Row zone (DK1/DK2)",
                    **SOURCE_META.get(src, {}), **COLUMN_META.get(col, {})}

        if col in DERIVED_FEATURES:
            cfg = DERIVED_FEATURES[col]
            meta = cfg.get("meta", {})
            if not meta:
                self.undocumented.append(col)
            if not cfg["inputs"]:  # calendar identifiers: computed from the timestamp alone
                return {
                    "origin": "Derived", "market": meta.get("market", "Calendar"), "geography": "Row zone (DK1/DK2)",
                    "meaning": meta.get("meaning", UNDOCUMENTED), "unit": meta.get("unit", UNDOCUMENTED),
                    "frequency": "Hourly", "delivery_ts": "Start of the delivery hour, UTC",
                    "availability": "Known in advance (calendar)", "source": "Calendar (src/dataframe/building.py)",
                    "fva": meta.get("fva", "Deterministic (calendar)"), "horizon": "Known in advance",
                    "transformation": meta.get("transformation", UNDOCUMENTED),
                    "direction": meta.get("direction", UNDOCUMENTED), "leakage": "No",
                    "leakage_note": "Deterministic calendar value.",
                }
            inputs = [self.describe(c) for c in cfg["inputs"]]
            leaky = [c for c, d in zip(cfg["inputs"], inputs) if d.get("leakage") == "Yes"]
            markets = list(dict.fromkeys(d.get("market", "") for d in inputs))
            return {
                "origin": "Derived",
                "market": meta.get("market") or (markets[0] if len(markets) == 1 else "Cross-market"),
                "geography": "Row zone (DK1/DK2)",
                "meaning": meta.get("meaning", UNDOCUMENTED),
                "unit": meta.get("unit") or inputs[0].get("unit", UNDOCUMENTED),
                "frequency": "Hourly (computed on the hourly panel, per bidding zone)",
                "delivery_ts": "Start of the delivery hour, UTC (same row as its inputs; any lag/rolling window "
                               "trails back from this hour, never forward)",
                "availability": _combine([d.get("availability", "") for d in inputs], "Latest of its inputs"),
                "source": "Derived in src/dataframe/building.py from: " + ", ".join(cfg["inputs"]),
                "fva": meta.get("fva") or _combine([d.get("fva", "") for d in inputs]),
                "horizon": _combine([d.get("horizon", "") for d in inputs]),
                "transformation": meta.get("transformation", UNDOCUMENTED),
                "direction": meta.get("direction", UNDOCUMENTED),
                "leakage": "Yes" if leaky else "No",
                "leakage_note": (f"Inherits ex-post timing from: {', '.join(leaky)}. " + _EX_POST_NOTE if leaky else
                                 _combine([d.get("leakage_note", "") for d in inputs], "From its inputs")),
            }

        self.undocumented.append(col)
        return {"origin": "Unknown"}


def column_units(cols: list) -> dict[str, str]:
    """Short unit per column ("MW", "EUR/MWh", ...) from the same metadata as
    the workbook — for plot axis labels. Unknown columns get ""."""
    resolver = _MetadataResolver()
    units = {}
    for col in cols:
        unit = resolver.describe(col).get("unit", "")
        units[col] = "" if unit == UNDOCUMENTED else unit.split(" (")[0]
    return units


# ---------------------------------------------------------------------------
# DATA-DRIVEN CHECKS
# ---------------------------------------------------------------------------
def _fmt_ts(ts) -> str:
    return "" if pd.isna(ts) else pd.Timestamp(ts).strftime("%Y-%m-%d %H:%M")


def _constant_check(df: pd.DataFrame, col: str, areas: list) -> tuple[str, str]:
    details = []
    for area in areas:
        vals = df.loc[df["bidding_zone"] == area, col].dropna()
        if vals.empty:
            continue
        counts = vals.value_counts()
        share = counts.iloc[0] / len(vals)
        if len(counts) == 1:
            details.append(f"{area}: constant = {counts.index[0]}")
        elif share >= NEAR_CONSTANT_SHARE:
            details.append(f"{area}: near-constant ({share:.1%} = {counts.index[0]})")
    return ("Yes" if details else "No"), "; ".join(details)


def _duplicate_check(df: pd.DataFrame, cols: list) -> dict[str, list[str]]:
    corr = df[cols].corr(min_periods=100)
    out = {}
    for col in cols:
        partners = corr[col].drop(col)
        hits = partners[partners.abs() >= DUPLICATE_ABS_CORR]
        out[col] = [f"{other} (r={r:+.3f})" for other, r in hits.sort_values(key=abs, ascending=False).items()]
    return out


def _copied_check(df: pd.DataFrame, col: str, areas: list) -> tuple[str, str]:
    """For a forecast column: per zone, the share of hours where it equals its
    own value, or its actual's value, 1 day / 1 week / 2 weeks earlier
    (hours where the forecast is 0, e.g. solar at night, are left out). A
    forecast filled with past values would repeat them. ("", "") for other columns."""
    if col not in FORECAST_OF:
        return "", ""
    actual = FORECAST_OF[col] if FORECAST_OF[col] in df.columns else None
    details, flagged = [], False
    for area in areas:
        z = df[df["bidding_zone"] == area].sort_values("datetime_utc")
        f = z[col]
        shares = {}
        for what, ref in (("own", f), ("actual", z[actual] if actual else None)):
            if ref is None:
                continue
            values = []
            for h in COPY_LAGS:
                earlier = ref.shift(h)
                valid = f.notna() & earlier.notna() & (f != 0)
                values.append((f[valid] == earlier[valid]).mean() if valid.any() else 0.0)
            shares[what] = values
            flagged |= max(values) >= COPIED_SHARE
        details.append(f"{area}: " + ", ".join(f"{what} {' / '.join(f'{100 * v:.1f}' for v in values)} %"
                                               for what, values in shares.items()))
    return ("Yes" if flagged else "No"), "; ".join(details) + f" ({' / '.join(COPY_LAGS.values())} earlier)"


def _distribution_row(s: pd.Series) -> dict:
    n_total = len(s)
    s = s.dropna().astype(float)
    row = {"n_obs": len(s), "missing_pct": round(100 * (1 - len(s) / n_total), 2) if n_total else None}
    if s.empty:
        return row
    q = s.quantile(QUANTILES)
    iqr = q[0.75] - q[0.25]
    lo, hi = q[0.25] - EXTREME_IQR_MULT * iqr, q[0.75] + EXTREME_IQR_MULT * iqr
    row.update({
        "mean": s.mean(), "median": q[0.50], "std": s.std(), "min": s.min(),
        **{f"p{int(round(k * 100)):02d}": q[k] for k in QUANTILES if k != 0.50},
        "max": s.max(), "skewness": s.skew(), "excess_kurtosis": s.kurt(),
        "zero_pct": 100 * (s == 0).mean(), "negative_pct": 100 * (s < 0).mean(),
        "extreme_pct": 100 * ((s < lo) | (s > hi)).mean(),
    })
    return {k: (round(v, 4) if isinstance(v, float) else v) for k, v in row.items()}


# ---------------------------------------------------------------------------
# WORKBOOK
# ---------------------------------------------------------------------------
def _readme(df: pd.DataFrame, name: str, spec: Spec, settings: dict) -> pd.DataFrame:
    rows = [
        ("Dataframe", name),
        *[(f"Setting: {k}", str(v)) for k, v in settings.items()],
        ("Rows", len(df)),
        ("Columns", f"{len(df.columns)} ({len(KEY)} key, {len(spec.endogenous)} endogenous, "
                    f"{len(spec.exogenous)} exogenous, {len(spec.inputs)} inputs)"),
        ("Delivery period (UTC)", f"{_fmt_ts(df['datetime_utc'].min())} to {_fmt_ts(df['datetime_utc'].max())}"),
        ("Bidding zones", ", ".join(sorted(df["bidding_zone"].unique()))),
        ("Row structure", "Panel: one row per (delivery hour, bidding zone)."),
        ("", ""),
        ("MODEL", ""),
        ("Endogenous variables", ", ".join(spec.endogenous)),
        ("Exogenous variables", ", ".join(spec.exogenous)),
        ("Inputs", ", ".join(spec.inputs)),
        ("Model role", "Endogenous = explained by the model (own equation, own and others' lags). Exogenous = "
                       "taken as given (enters every equation, no equation of its own). Input = a column a model "
                       "variable is computed from (found automatically), kept so the construction can be checked."),
        ("Calendar dummies", "fe_* columns are category identifiers: expand them to one dummy per category at "
                             "estimation (drop one category each if the model has a constant)."),
        ("Literature columns", f"Model variable, definition, interpretation, source in the literature and the "
                               f"deviation from it, relative to the baseline literature ({LITERATURE_REFERENCE})."),
        ("", ""),
        ("DEFINITIONS", ""),
        ("Timestamp meaning (DELIVERY)", "What the row timestamp refers to: the hour in which the power is delivered."),
        ("Availability time (INFORMATION)", "When the value actually becomes known (published/observable). "
                                            "This is what matters for leakage, NOT the delivery timestamp."),
        ("Potential leakage", "Yes = the value in row t is NOT known before delivery hour t starts (realised "
                              "during/after delivery). No = known before delivery. A timing flag, not a verdict: "
                              "compare 'Availability time' with the decision time of your model."),
        ("Derived columns", "Timing fields (availability, leakage, horizon, forecast vs actual) are inherited from "
                            "the inputs. Lag/rolling windows are trailing (t-N+1..t), computed per zone; rolling "
                            "statistics need >= 80% of the window observed, no interpolation."),
        ("Missingness %", "Share of rows (both zones) where the value is NaN."),
        ("Constant/near-constant", f"Per zone: one unique value (constant), or the most frequent value covers "
                                   f">= {NEAR_CONSTANT_SHARE:.0%} of non-null rows (near-constant)."),
        ("Suspected duplicates", f"|Pearson r| >= {DUPLICATE_ABS_CORR} with another column over all rows (pooled "
                                 f"across zones). Includes sign-flipped copies."),
        ("Copied forecast values", f"Forecast columns only, per zone: share of hours where the forecast equals its "
                                   f"own value ('own') or the actual's value ('actual') "
                                   f"{' / '.join(COPY_LAGS.values())} earlier; hours where the forecast is 0 are left "
                                   f"out. Yes = a share >= {COPIED_SHARE:.0%}: the forecast may be filled with past "
                                   f"values."),
        ("Extreme-value frequency", f"% of non-null values outside [Q1 - {EXTREME_IQR_MULT:g}*IQR, "
                                    f"Q3 + {EXTREME_IQR_MULT:g}*IQR] of the same scope."),
        ("Kurtosis", "Excess kurtosis (normal distribution = 0)."),
        ("Distribution scopes", "'all' = both zones pooled; 'DK1' / 'DK2' = that zone's rows only."),
    ]
    return pd.DataFrame(rows, columns=["Item", "Value"])


def _format_sheet(ws, wrap_cols: set[str], max_width: int = 60):
    from openpyxl.styles import Alignment, Font

    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.alignment = Alignment(wrap_text=True, vertical="top")
    ws.freeze_panes = "C2" if ws.max_column > 2 else "A2"
    ws.auto_filter.ref = ws.dimensions
    for col_cells in ws.columns:
        header = str(col_cells[0].value or "")
        longest = max(len(str(c.value)) if c.value is not None else 0 for c in col_cells)
        wrap = header in wrap_cols
        ws.column_dimensions[col_cells[0].column_letter].width = min(max(longest, len(header) * 0.6, 8) + 2,
                                                                      max_width if wrap else 45)
        if wrap:
            for c in col_cells[1:]:
                c.alignment = Alignment(wrap_text=True, vertical="top")


def write_documentation(df: pd.DataFrame, name: str, spec: Spec, out_path: Path, settings: dict):
    """settings: {label: value} shown at the top of the README sheet."""
    resolver = _MetadataResolver()
    areas = sorted(df["bidding_zone"].unique())
    measured = [c for c in df.columns if c not in KEY and c not in spec.calendar]
    duplicates = _duplicate_check(df, measured)

    meta_rows = []
    for col in df.columns:
        is_variable = spec.role(col) in ("Endogenous", "Exogenous")
        info = {**resolver.describe(col), **(LITERATURE.get(col, {}) if is_variable else {}),
                "dataframe": name, "feature": col, "role": "Key" if col in KEY else spec.role(col)}
        if col not in KEY:
            observed = df[col].notna()
            info["pct_missing"] = round(100 * (1 - observed.mean()), 2)
            info["first_non_null"] = _fmt_ts(df.loc[observed, "datetime_utc"].min()) if observed.any() else ""
            info["last_non_null"] = _fmt_ts(df.loc[observed, "datetime_utc"].max()) if observed.any() else ""
            info["constant"], info["constant_detail"] = _constant_check(df, col, areas)
            dups = duplicates.get(col, [])
            info["duplicate"], info["duplicate_detail"] = ("Yes" if dups else "No"), "; ".join(dups)
            info["copied"], info["copied_detail"] = _copied_check(df, col, areas)
        meta_rows.append({label: info.get(field, UNDOCUMENTED if field in ("meaning", "unit") else "")
                          for field, label in METADATA_COLUMNS})
    meta_df = pd.DataFrame(meta_rows)

    dist_rows = []
    for col in measured:
        dist_rows.append({"Feature": col, "Role": spec.role(col), "Scope": "all", **_distribution_row(df[col])})
        for area in areas:
            dist_rows.append({"Feature": col, "Role": spec.role(col), "Scope": area,
                              **_distribution_row(df.loc[df["bidding_zone"] == area, col])})
    dist_df = pd.DataFrame(dist_rows)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
            _readme(df, name, spec, settings).to_excel(writer, sheet_name="README", index=False)
            meta_df.to_excel(writer, sheet_name="metadata", index=False)
            dist_df.to_excel(writer, sheet_name="distribution", index=False)
            _format_sheet(writer.sheets["README"], {"Value"}, max_width=120)
            _format_sheet(writer.sheets["metadata"], WRAPPED_METADATA)
            _format_sheet(writer.sheets["distribution"], set())
    except PermissionError:
        raise PermissionError(f"Could not write {out_path}: is it open in Excel? Close it and re-run.") from None

    print(f"  Saved {out_path} ({len(meta_df)} columns documented, {len(measured)} with distribution stats)")
    if resolver.undocumented:
        print(f"  WARNING — column(s) without metadata (add them to COLUMN_META or their DERIVED_FEATURES "
              f"'meta'): {sorted(set(resolver.undocumented))}")
