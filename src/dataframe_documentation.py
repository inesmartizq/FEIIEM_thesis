"""
Writes the documentation workbook (.xlsx) for one built dataframe — the
"documentation" step of main.py, run right after the dataframe is built.

Sheets:
    README        - what the dataframe is, definitions of every check used
                    below, and the list of derived columns.
    metadata      - one row per column: market, geography, meaning, unit,
                    frequency, DELIVERY timestamp meaning vs. INFORMATION
                    (availability/publication) time, source, forecast vs
                    actual, horizon, transformation, expected direction,
                    potential leakage, missingness, constant/near-constant,
                    suspected duplicates.
    distribution  - per numeric column x scope (all rows, DK1, DK2): mean,
                    median, std, min/max, quantiles, skewness, kurtosis,
                    zero / negative / extreme-value frequency.

WHERE THE METADATA COMES FROM
-----------------------------
    - Source columns: SOURCE_META (facts shared by every column of one
      SOURCES entry: market, source, timing, leakage) + COLUMN_META (per
      column: meaning, unit, direction, and any override of the source
      defaults — e.g. the forecasts file holds both forecasts and actuals,
      which have very different availability).
    - Derived columns: the "meta" dict of their DERIVED_FEATURES entry
      (meaning, transformation, direction). Timing fields — availability,
      leakage, horizon, forecast-vs-actual — are INHERITED from the inputs
      recursively, so e.g. a rolling std of the imbalance price is
      automatically flagged ex-post like the imbalance price itself.
    - Missingness, constant/near-constant, duplicates and all distribution
      statistics are computed from the data.

A column with no metadata gets "UNDOCUMENTED" in its text fields and a
warning is printed — add it to COLUMN_META (source column) or to its
DERIVED_FEATURES entry's "meta" (derived column).
"""

from pathlib import Path

import pandas as pd

# ----------------------- CHECK THRESHOLDS -----------------------
NEAR_CONSTANT_SHARE = 0.95   # most frequent value covers >= this share of a zone's non-null rows
DUPLICATE_ABS_CORR = 0.99    # |Pearson r| at or above this vs. another column -> suspected duplicate
EXTREME_IQR_MULT = 3.0       # outside [Q1 - k*IQR, Q3 + k*IQR] -> extreme value
QUANTILES = [0.01, 0.05, 0.25, 0.50, 0.75, 0.95, 0.99]

UNDOCUMENTED = "UNDOCUMENTED"

# ---------------------------------------------------------------------------
# SOURCE-LEVEL METADATA — keyed by the SOURCES name in dataframe_building.py.
# Fields:
#   market, source, frequency, delivery_ts (what the row timestamp means),
#   availability (when the value is actually known), fva (forecast vs
#   actual), horizon, leakage ("Yes"/"No", see README definition),
#   leakage_note, transformation (default for raw columns).
# ---------------------------------------------------------------------------
_DA_AVAILABILITY = (
    "D-1: SDAC day-ahead results are published ~12:45-13:00 CET on the day "
    "before delivery, for every hour of delivery day D. Known before delivery."
)
_DA_COMMON = {
    "market": "Day-ahead",
    "frequency": "Hourly (60-min MTU until 2025-09-30; 15-min MTU from 2025-10-01, "
                 "averaged to the hourly mean in import_da_pipeline.py)",
    "delivery_ts": "Start of the delivery hour, UTC",
    "availability": _DA_AVAILABILITY,
    "fva": "Market outcome (ex-ante clearing result)",
    "horizon": "D-1 (published 11-35 h before delivery)",
    "leakage": "No",
    "leakage_note": "Known before delivery hour t; usable at row t for any decision "
                    "taken after DA results are published on D-1.",
    "transformation": "Raw (hourly)",
}
_EX_POST_NOTE = ("Not known before delivery hour t is over. Using row t contemporaneously to "
                 "explain/predict anything decided before or during hour t leaks — lag it by "
                 ">= 1 h (more if the publication delay matters).")

SOURCE_META = {
    "mfrr": {
        "market": "Balancing",
        "source": "Nord Pool Data Portal API — Nordic balancing (mFRR) market data "
                  "(import_balancing_pipeline.py)",
        "frequency": "Hourly (any sub-hourly API values averaged to the hourly mean in import)",
        "delivery_ts": "Start of the delivery (operating) hour, UTC",
        "availability": "Ex-post: activations happen during the delivery hour; volumes and "
                        "prices are published after it (imbalance price may be preliminary, "
                        "then final). Exact publication delay is not recorded in the data.",
        "fva": "Actual (realised outcome)",
        "horizon": "None (realised, ex-post)",
        "leakage": "Yes",
        "leakage_note": _EX_POST_NOTE,
        "transformation": "Raw (hourly mean)",
    },
    "intraday": {
        "market": "Intraday",
        "source": "Nord Pool Data Portal API — continuous intraday (SIDC) hourly trading "
                  "statistics (import_intraday_pipeline.py)",
        "frequency": "Hourly per delivery hour (15-min product statistics, where present, "
                     "recombined to hourly in import: prices volume-weighted, volumes summed)",
        "delivery_ts": "Start of the delivery hour of the traded product, UTC",
        "availability": "Builds up while the product trades (from D-1 afternoon CET until "
                        "intraday gate closure shortly before delivery). The hourly statistics "
                        "are FINAL only at gate closure, i.e. just before hour t starts.",
        "fva": "Market outcome (traded prices / volumes)",
        "horizon": "D-1 afternoon up to gate closure before delivery",
        "leakage": "No",
        "leakage_note": "Final just before delivery hour t (at gate closure). No leakage for a "
                        "decision point after ID gate closure (e.g. explaining balancing in "
                        "hour t); DOES leak for an earlier decision point (D-1, or hours ahead).",
        "transformation": "Raw (hourly aggregate of trades)",
    },
    "afrr": {
        "market": "Balancing",
        "source": "Energinet Energi Data Service (pre-PICASSO, until 2024-10-01) + ENTSO-E "
                  "Transparency Platform A24 aggregated balancing energy bids (post-PICASSO, "
                  "from 2024-10-02), stitched in import_balancing_pipeline.py",
        "frequency": "Hourly (ENTSO-E 15-min MW values averaged to the hourly mean in import)",
        "delivery_ts": "Start of the delivery (operating) hour, UTC",
        "availability": "Ex-post: published after the delivery hour. Exact publication "
                        "delay is not recorded in the data.",
        "fva": "Actual (realised outcome)",
        "horizon": "None (realised, ex-post)",
        "leakage": "Yes",
        "leakage_note": _EX_POST_NOTE,
        "transformation": "Raw (hourly mean)",
    },
    "da_nordpool_flows": {
        **_DA_COMMON,
        "source": "Nord Pool Data Portal API — day-ahead scheduled exchanges per border "
                  "(import_da_pipeline.py)",
        "fva": "Scheduled (commercial DA market-coupling schedule, NOT physical flow)",
    },
    "da_nordpool_prices": {
        **_DA_COMMON,
        "source": "Nord Pool Data Portal API — day-ahead (SDAC) prices, EUR "
                  "(import_da_pipeline.py)",
    },
    "da_nordpool_volumes": {
        **_DA_COMMON,
        "source": "Nord Pool Data Portal API — day-ahead (SDAC) cleared volumes "
                  "(import_da_pipeline.py)",
    },
    "reservoir": {
        "market": "Fundamentals (hydro)",
        "source": "Nord Pool Data Portal API — Reservoir report: weekly hydro reservoir filling per area "
                  "(import_extras.py, download_reservoir)",
        "frequency": "Weekly (ISO week, Monday-Sunday in Nordic local time); the week's value is repeated "
                     "on every hour of that week (step), so it changes once a week",
        "delivery_ts": "Start of the delivery hour, UTC; the value is the filling reported for the ISO week "
                       "containing that hour",
        "availability": "Ex-post weekly report, published after the week. Because the value is applied to "
                        "every hour of its OWN week, hours early in the week see a value that was not yet "
                        "published (up to ~7 days of look-ahead).",
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
        "source": "Nord Pool Data Portal API — Power System data: production/consumption "
                  "prognoses and actuals (import_forecasts_pipeline.py)",
        "frequency": "Hourly (production 15-min values averaged to the hourly mean in "
                     "import; consumption natively hourly)",
        "delivery_ts": "Start of the delivery hour the forecast/measurement refers to, UTC",
        "availability": "D-1 day-ahead prognosis. ASSUMPTION, NOT VERIFIED: the data carries "
                        "no issue/publication timestamp, so whether it is published before or "
                        "after DA gate closure (12:00 CET D-1) is unknown.",
        "fva": "Forecast",
        "horizon": "D-1 (day-ahead prognosis)",
        "leakage": "No",
        "leakage_note": "Known before delivery (D-1). Check the issue time before relying on it "
                        "as information available at DA gate closure.",
        "transformation": "Raw (hourly mean)",
    },
}

_ACTUAL_OVERRIDE = {
    "availability": "Ex-post: measured during the delivery hour, published after it. Exact "
                    "publication delay is not recorded in the data.",
    "fva": "Actual (measured)",
    "horizon": "None (measured)",
    "leakage": "Yes",
    "leakage_note": _EX_POST_NOTE,
}

# ---------------------------------------------------------------------------
# COLUMN-LEVEL METADATA for source columns (final names). Fields: meaning,
# unit, direction, optional geography, plus any SOURCE_META field to
# override for this one column.
# ---------------------------------------------------------------------------
COLUMN_META = {
    # --- mFRR / imbalance (Nord Pool) ---
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
        "meaning": "Imbalance settlement (regulating power) price P_BAL: up price in up-regulation hours, "
                   "down price in down-regulation hours, DA price without regulation (verified 2022-2024: "
                   "100 % / 100 % / 99.7 %); from 2025 the hourly mean of the 15-min imbalance prices",
        "unit": "EUR/MWh", "direction": "Above DA price when the system is short, below when long; extremes = balancing stress",
    },
    "b_dominating_direction": {
        "meaning": "Dominating regulation direction in the hour: Nord Pool 'Up' -> +1, 'Down' -> -1, "
                   "empty -> 0 (no regulation: in 2022-2024 the imbalance price equals the DA price and "
                   "mFRR activation is zero in 99-100 % of those hours; in 2025 only 40 % / 52 %, as hourly "
                   "values aggregate 15-min states). Hourly value = most frequent 15-min direction in that "
                   "hour; ties broken by the hour's net mFRR activation (0 -> no direction).",
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
                                  "unit": "MWh", "direction": "Higher = more re-balancing after DA (larger forecast updates)"},
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
    "da_system_price": {"meaning": "Nord Pool day-ahead system price (unconstrained Nordic reference "
                                   "price; the same value for every zone)",
                        "unit": "EUR/MWh", "geography": "Nordic system (copied to every zone row)",
                        "direction": "Zone price differs from it when transmission is congested"},
    "da_system_turnover_mw": {"meaning": "Nord Pool day-ahead system turnover (traded volume of the whole "
                                         "Nordic system; the same value for every zone)",
                              "unit": "MW (hourly mean = MWh per hour)",
                              "geography": "Nordic system (copied to every zone row)",
                              "direction": "Higher = more energy traded day-ahead in the Nordic system"},
    "da_price": {"meaning": "Day-ahead (SDAC) clearing price of the row's bidding zone",
                 "unit": "EUR/MWh", "direction": "Low/negative with high wind+solar; high with high residual load"},
    "da_buy_volume_mw": {"meaning": "Day-ahead cleared buy (demand) volume",
                         "unit": "MW (= MWh per hour)", "direction": "Tracks expected load"},
    "da_sell_volume_mw": {"meaning": "Day-ahead cleared sell (supply) volume",
                          "unit": "MW (= MWh per hour)", "direction": "Tracks expected local generation"},
    # --- forecasts / actuals ---
    "c_solar_forecast_mw": {"meaning": "Day-ahead solar generation forecast", "unit": "MW (hourly mean)",
                            "direction": "Higher -> lower DA price midday"},
    "c_wind_onshore_forecast_mw": {"meaning": "Day-ahead onshore wind generation forecast", "unit": "MW (hourly mean)",
                                   "direction": "Higher -> lower DA price"},
    "c_wind_offshore_forecast_mw": {"meaning": "Day-ahead offshore wind generation forecast", "unit": "MW (hourly mean)",
                                    "direction": "Higher -> lower DA price"},
    "c_load_forecast_mw": {"meaning": "Day-ahead consumption (load) forecast", "unit": "MW",
                           "direction": "Higher -> higher DA price"},
    "c_solar_actual_mw": {"meaning": "Actual solar generation", "unit": "MW (hourly mean)",
                          "direction": "Relevant mainly via its deviation from forecast", **_ACTUAL_OVERRIDE},
    "c_wind_onshore_actual_mw": {"meaning": "Actual onshore wind generation", "unit": "MW (hourly mean)",
                                 "direction": "Relevant mainly via its deviation from forecast", **_ACTUAL_OVERRIDE},
    "c_wind_offshore_actual_mw": {"meaning": "Actual offshore wind generation", "unit": "MW (hourly mean)",
                                  "direction": "Relevant mainly via its deviation from forecast", **_ACTUAL_OVERRIDE},
    "c_load_actual_mw": {"meaning": "Actual consumption (load)", "unit": "MW",
                         "direction": "Relevant mainly via its deviation from forecast", **_ACTUAL_OVERRIDE},
}

# Day-ahead flows: 8 borders x 3 quantities, generated.
_FLOW_BORDERS = {
    "total": "all borders combined", "nl": "NL", "ger": "DE (Germany)", "se3": "SE3",
    "se4": "SE4", "no2": "NO2", "dk1": "DK1", "dk2": "DK2",
}
for _nb, _label in _FLOW_BORDERS.items():
    _geo = ("Row zone (DK1/DK2), all borders" if _nb == "total"
            else f"Row zone (DK1/DK2) <-> {_label} border (structural 0 for a zone without this border)")
    _of = "over all borders" if _nb == "total" else f"with {_label}"
    COLUMN_META[f"da_flow_{_nb}_import_mw"] = {
        "meaning": f"Day-ahead scheduled import {_of}", "unit": "MW", "geography": _geo,
        "direction": "Higher when the row zone is relatively expensive/short vs. neighbours",
    }
    COLUMN_META[f"da_flow_{_nb}_export_mw"] = {
        "meaning": f"Day-ahead scheduled export {_of}", "unit": "MW", "geography": _geo,
        "direction": "Higher when the row zone is relatively cheap/long (e.g. high wind)",
    }
    COLUMN_META[f"da_flow_{_nb}_net_position_mw"] = {
        "meaning": f"Day-ahead scheduled net position {_of} (Nord Pool 'netPosition')", "unit": "MW",
        # Sign checked on df_2025: total net position has corr = -1 with
        # (export - import), i.e. in this data positive = net IMPORT.
        "geography": _geo, "direction": "Positive = row zone is a net importer (checked in the data: "
                                        "moves exactly with import - export)",
    }

# Hydro reservoir filling, one column per area (not a DK zone: the same
# value on every DK1 / DK2 row).
_RESERVOIR_GEO = {'no': 'Norway (country total, NO1-NO5)', 'se': 'Sweden (country total, SE1-SE4)', 'fi': 'Finland', 'no1': 'Norway, bidding area NO1', 'no2': 'Norway, bidding area NO2', 'no3': 'Norway, bidding area NO3', 'no4': 'Norway, bidding area NO4', 'no5': 'Norway, bidding area NO5', 'se1': 'Sweden, bidding area SE1', 'se2': 'Sweden, bidding area SE2', 'se3': 'Sweden, bidding area SE3', 'se4': 'Sweden, bidding area SE4'}
for _a, _g in _RESERVOIR_GEO.items():
    COLUMN_META[f"c_reservoir_fill_pct_{_a}"] = {
        "meaning": f"Hydro reservoir filling, {_g}: stored energy as % of reservoir capacity "
                   f"(Nord Pool 'utilizationPercentage')",
        "unit": "% of capacity",
        "geography": f"{_g} (copied to every DK1 / DK2 row)",
        "direction": "Higher filling -> more low-cost hydro supply in the Nordic system -> lower Nordic "
                     "prices; the seasonal cycle (spring melt) dominates",
    }

KEY_META = {
    "datetime_utc": {
        "meaning": "DELIVERY timestamp: start of the delivery hour, in UTC. This is NOT when any "
                   "value was published; see the availability column for each feature.",
        "unit": "datetime (UTC)", "market": "Key", "transformation": "Key",
    },
    "bidding_zone": {
        "meaning": "Bidding zone the row refers to",
        "unit": "categorical", "market": "Key", "transformation": "Key",
    },
}

METADATA_COLUMNS = [
    ("dataframe", "Dataframe name"),
    ("feature", "Feature"),
    ("role", "Model role"),
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
]


# ---------------------------------------------------------------------------
# METADATA RESOLUTION
# ---------------------------------------------------------------------------
def _combine(values: list[str], mixed_prefix: str = "Mixed") -> str:
    unique = list(dict.fromkeys(v for v in values if v))
    if len(unique) == 1:
        return unique[0]
    return f"{mixed_prefix}: " + " | ".join(unique)


class _MetadataResolver:
    def __init__(self, sources: dict, derived: dict):
        self.derived = derived
        self.col_to_source = {final: name for name, cfg in sources.items()
                              for final in cfg["rename"].values()}
        self.cache: dict[str, dict] = {}
        self.undocumented: list[str] = []

    def describe(self, col: str) -> dict:
        if col not in self.cache:
            self.cache[col] = self._describe(col)
        return self.cache[col]

    def _describe(self, col: str) -> dict:
        if col in KEY_META:
            return {"origin": "Key", "geography": "-", **KEY_META[col]}

        if col in self.col_to_source:
            src = self.col_to_source[col]
            info = {"origin": f"Source ({src})", "geography": "Row zone (DK1/DK2)",
                    **SOURCE_META.get(src, {}), **COLUMN_META.get(col, {})}
            if src not in SOURCE_META or col not in COLUMN_META:
                self.undocumented.append(col)
            return info

        if col in self.derived:
            cfg = self.derived[col]
            meta = cfg.get("meta", {})
            if not meta:
                self.undocumented.append(col)
            if not cfg["inputs"]:  # calendar identifiers: computed from the timestamp alone
                return {
                    "origin": "Derived", "market": meta.get("market", "Calendar"),
                    "geography": "Row zone (DK1/DK2)", "meaning": meta.get("meaning", UNDOCUMENTED),
                    "unit": meta.get("unit", UNDOCUMENTED),
                    "frequency": "Hourly", "delivery_ts": "Start of the delivery hour, UTC",
                    "availability": "Known in advance (calendar)", "source": "Calendar (dataframe_building.py)",
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
                "delivery_ts": "Start of the delivery hour, UTC (same row as its inputs; any "
                               "lag/rolling window trails back from this hour, never forward)",
                "availability": _combine([d.get("availability", "") for d in inputs],
                                         "Latest of its inputs"),
                "source": "Derived in dataframe_building.py from: " + ", ".join(cfg["inputs"]),
                "fva": meta.get("fva") or _combine([d.get("fva", "") for d in inputs]),
                "horizon": _combine([d.get("horizon", "") for d in inputs]),
                "transformation": meta.get("transformation", UNDOCUMENTED),
                "direction": meta.get("direction", UNDOCUMENTED),
                "leakage": "Yes" if leaky else "No",
                "leakage_note": (f"Inherits ex-post timing from: {', '.join(leaky)}. " + _EX_POST_NOTE
                                 if leaky else
                                 _combine([d.get("leakage_note", "") for d in inputs], "From its inputs")),
            }

        self.undocumented.append(col)
        return {"origin": "Unknown"}


def column_units(cols: list, sources: dict, derived: dict) -> dict[str, str]:
    """Short unit per column ("MW", "EUR/MWh", ...) from the same metadata
    the workbook uses — for plot axis labels. Unknown columns get ""."""
    resolver = _MetadataResolver(sources, derived)
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


def _duplicate_check(df: pd.DataFrame, numeric_cols: list) -> dict[str, list[str]]:
    corr = df[numeric_cols].corr(min_periods=100)
    out = {}
    for col in numeric_cols:
        partners = corr[col].drop(col)
        hits = partners[partners.abs() >= DUPLICATE_ABS_CORR]
        out[col] = [f"{other} (r={r:+.3f})" for other, r in hits.sort_values(key=abs, ascending=False).items()]
    return out


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
        "mean": s.mean(), "median": q[0.50], "std": s.std(),
        "min": s.min(),
        **{f"p{int(round(k * 100)):02d}": q[k] for k in QUANTILES if k != 0.50},
        "max": s.max(),
        "skewness": s.skew(), "excess_kurtosis": s.kurt(),
        "zero_pct": 100 * (s == 0).mean(),
        "negative_pct": 100 * (s < 0).mean(),
        "extreme_pct": 100 * ((s < lo) | (s > hi)).mean(),
    })
    return {k: (round(v, 4) if isinstance(v, float) else v) for k, v in row.items()}


# ---------------------------------------------------------------------------
# WORKBOOK
# ---------------------------------------------------------------------------
def _readme(df: pd.DataFrame, analysis_name: str, key: list, meta_df: pd.DataFrame,
            settings: dict | None) -> pd.DataFrame:
    derived_cols = meta_df.loc[meta_df["Origin"] == "Derived", "Feature"].tolist()
    source_cols = meta_df.loc[meta_df["Origin"].str.startswith("Source"), "Feature"].tolist()
    rows = [
        ("Dataframe", analysis_name),
        *[(f"Setting: {k}", str(v)) for k, v in (settings or {}).items()],
        ("Rows", len(df)),
        ("Columns", f"{len(df.columns)} ({len(key)} key, {len(source_cols)} source, {len(derived_cols)} derived)"),
        ("Delivery period (UTC)", f"{_fmt_ts(df['datetime_utc'].min())} to {_fmt_ts(df['datetime_utc'].max())}"),
        ("Bidding zones", ", ".join(sorted(df["bidding_zone"].unique()))),
        ("Row structure", "Panel: one row per (delivery hour, bidding zone)."),
        ("", ""),
        ("DEFINITIONS", ""),
        ("Timestamp meaning (DELIVERY)", "What the row timestamp refers to: the hour in which the power is delivered."),
        ("Availability time (INFORMATION)", "When the value actually becomes known (published/observable). "
                                            "This is what matters for leakage, NOT the delivery timestamp."),
        ("Potential leakage", "Yes = the value in row t is NOT known before delivery hour t starts (realised "
                              "during/after delivery). No = known before delivery. A timing flag, not a "
                              "verdict: compare 'Availability time' with the decision time of your model."),
        ("Derived columns", "Timing fields (availability, leakage, horizon, forecast vs actual) are inherited "
                            "from the inputs. Lag/rolling windows are trailing (t-N+1..t), computed per zone; "
                            "rolling statistics need >= 80% of the window observed, no interpolation."),
        ("Missingness %", "Share of rows (both zones) where the value is NaN."),
        ("Constant/near-constant", f"Per zone: one unique value (constant), or the most frequent value covers "
                                   f">= {NEAR_CONSTANT_SHARE:.0%} of non-null rows (near-constant)."),
        ("Suspected duplicates", f"|Pearson r| >= {DUPLICATE_ABS_CORR} with another column over all rows "
                                 f"(pooled across zones). Includes sign-flipped copies."),
        ("Extreme-value frequency", f"% of non-null values outside [Q1 - {EXTREME_IQR_MULT:g}*IQR, "
                                    f"Q3 + {EXTREME_IQR_MULT:g}*IQR] of the same scope."),
        ("Kurtosis", "Excess kurtosis (normal distribution = 0)."),
        ("Distribution scopes", "'all' = both zones pooled; 'DK1' / 'DK2' = that zone's rows only."),
        ("", ""),
        (f"DERIVED COLUMNS ({len(derived_cols)})", ", ".join(derived_cols)),
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


ROLE_ORDER = {"Key": 0, "Endogenous": 1, "Exogenous": 2, "Input": 3, "": 4}


def _model_variables_sheet(df: pd.DataFrame, spec: dict, resolver) -> pd.DataFrame:
    """The model specification as a table: every model variable (endogenous,
    exogenous, not included) and every input series, grouped by role and
    market, with definition, sources and deviations from the literature."""
    rows = []
    for v in spec["variables"]:
        col = v["column"]
        rows.append({
            "Model role": v["role"], "Market": v["market"], "Variable": v["name"],
            "Column": col or "(not in dataframe)", "Definition": v["definition"], "Unit": v["unit"],
            "Interpretation": v["interpretation"], "Source (literature)": v["literature_source"],
            "Source (this dataframe)": v["source_here"], "Deviation / notes": v["deviation"],
            "Missingness %": round(100 * df[col].isna().mean(), 2) if col in df.columns else "",
        })
    for market, cols in spec["inputs"].items():
        for col in cols:
            info = resolver.describe(col)
            rows.append({
                "Model role": "Input", "Market": market, "Variable": col, "Column": col,
                "Definition": info.get("meaning", ""), "Unit": info.get("unit", ""),
                "Interpretation": "Not a model variable: used to construct one (kept so the construction "
                                  "can be checked)",
                "Source (literature)": "", "Source (this dataframe)": info.get("source", ""),
                "Deviation / notes": "",
                "Missingness %": round(100 * df[col].isna().mean(), 2) if col in df.columns else "",
            })
    order = {"Endogenous": 0, "Exogenous": 1, "Not included": 2, "Input": 3}
    out = pd.DataFrame(rows)
    out["_o"] = out["Model role"].map(order)
    return out.sort_values(["_o", "Market"], kind="stable").drop(columns="_o").reset_index(drop=True)


def write_documentation_excel(df: pd.DataFrame, analysis_name: str, out_path: Path,
                              sources: dict, derived: dict, key: list, settings: dict | None = None,
                              model_spec: dict | None = None):
    """settings: optional {label: value} shown at the top of the README
    sheet (main.py passes the requested date range, markets and zones).
    model_spec: optional spec from model_specs.py — adds the "Model role"
    (Endogenous / Exogenous / Input) and the spec's market per column,
    groups the metadata rows by role and market, and adds a
    "model_variables" sheet."""
    resolver = _MetadataResolver(sources, derived)
    areas = sorted(df["bidding_zone"].unique())
    numeric_cols = [c for c in df.columns if c not in key and pd.api.types.is_numeric_dtype(df[c])]
    duplicates = _duplicate_check(df, numeric_cols)
    roles, spec_markets, spec_units = {}, {}, {}
    if model_spec is not None:
        from model_specs import spec_input_markets, spec_roles
        roles = spec_roles(model_spec)
        spec_markets = {**spec_input_markets(model_spec),
                        **{v["column"]: v["market"] for v in model_spec["variables"] if v["column"]}}
        spec_units = {v["column"]: v["unit"] for v in model_spec["variables"] if v["column"]}

    meta_rows = []
    for col in df.columns:
        info = dict(resolver.describe(col))
        info["dataframe"] = analysis_name
        info["feature"] = col
        info["role"] = "Key" if col in key else roles.get(col, "")
        if col in spec_markets:
            info["market"] = spec_markets[col]
        if col in spec_units:
            info["unit"] = spec_units[col]
        if col not in key:
            non_null = df[col].notna()
            info["pct_missing"] = round(100 * (1 - non_null.mean()), 2)
            info["first_non_null"] = _fmt_ts(df.loc[non_null, "datetime_utc"].min()) if non_null.any() else ""
            info["last_non_null"] = _fmt_ts(df.loc[non_null, "datetime_utc"].max()) if non_null.any() else ""
            info["constant"], info["constant_detail"] = _constant_check(df, col, areas)
            dups = duplicates.get(col, [])
            info["duplicate"] = "Yes" if dups else "No"
            info["duplicate_detail"] = "; ".join(dups)
        meta_rows.append({label: info.get(field, UNDOCUMENTED if field in ("meaning", "unit") else "")
                          for field, label in METADATA_COLUMNS})
    meta_df = pd.DataFrame(meta_rows)
    if model_spec is not None:
        meta_df["_o"] = meta_df["Model role"].map(ROLE_ORDER).fillna(9)
        meta_df = (meta_df.sort_values(["_o", "Market"], kind="stable").drop(columns="_o")
                   .reset_index(drop=True))

    dist_rows = []
    for col in numeric_cols:
        dist_rows.append({"Feature": col, "Scope": "all", **_distribution_row(df[col])})
        for area in areas:
            dist_rows.append({"Feature": col, "Scope": area,
                              **_distribution_row(df.loc[df["bidding_zone"] == area, col])})
    dist_df = pd.DataFrame(dist_rows)

    readme_df = _readme(df, analysis_name, key, meta_df, settings)
    model_df = None
    if model_spec is not None:
        model_df = _model_variables_sheet(df, model_spec, resolver)
        endo = [v["column"] for v in model_spec["variables"] if v["role"] == "Endogenous"]
        exo = [v["column"] for v in model_spec["variables"] if v["role"] == "Exogenous"]
        spec_rows = [("", ""), ("MODEL SPECIFICATION", model_spec["title"]),
                     ("Endogenous variables", ", ".join(endo)), ("Exogenous variables", ", ".join(exo)),
                     ("Model role column", "Endogenous = explained by the model (own equation); Exogenous = "
                                           "taken as given (no equation); Input = raw series a model "
                                           "variable is built from, not itself in the model. Details: "
                                           "'model_variables' sheet."),
                     *[(f"Note {i}", n) for i, n in enumerate(model_spec["notes"], 1)]]
        readme_df = pd.concat([readme_df.iloc[:7], pd.DataFrame(spec_rows, columns=readme_df.columns),
                               readme_df.iloc[7:]], ignore_index=True)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
            readme_df.to_excel(writer, sheet_name="README", index=False)
            if model_df is not None:
                model_df.to_excel(writer, sheet_name="model_variables", index=False)
                _format_sheet(writer.sheets["model_variables"], {
                    "Definition", "Interpretation", "Source (literature)", "Source (this dataframe)",
                    "Deviation / notes", "Variable", "Market"}, max_width=55)
            meta_df.to_excel(writer, sheet_name="metadata", index=False)
            dist_df.to_excel(writer, sheet_name="distribution", index=False)
            _format_sheet(writer.sheets["README"], {"Value"}, max_width=120)
            _format_sheet(writer.sheets["metadata"], {
                "Physical/economic meaning", "Timestamp meaning (DELIVERY time of the row)",
                "Availability time (INFORMATION / publication time)", "Source", "Frequency",
                "Expected direction", "Leakage note", "Constant/near-constant detail",
                "Suspected duplicates detail", "Geography", "Forecast vs actual", "Forecast horizon",
                "Transformation",
            })
            _format_sheet(writer.sheets["distribution"], set())
    except PermissionError:
        print(f"  ERROR — could not write {out_path}: is it open in Excel? Close it and re-run.")
        return

    print(f"  Saved documentation workbook {out_path} "
          f"({len(meta_df)} columns documented, {len(numeric_cols)} with distribution stats)")
    if resolver.undocumented:
        print(f"  WARNING — {len(resolver.undocumented)} column(s) lack hand-written metadata "
              f"(add them to COLUMN_META or their DERIVED_FEATURES 'meta'): {resolver.undocumented}")
