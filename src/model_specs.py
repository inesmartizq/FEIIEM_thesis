"""
model_specs.py

Model specifications: which columns a model uses and in what ROLE
(endogenous / exogenous), with the literature definition, the data source
actually used here, and every known deviation from the literature.

A DATAFRAMES entry in main.py can name a spec ("model_spec": "<key>"). The
pipeline then:
    - keeps only the spec's columns (variables + inputs) in the dataframe,
    - adds a "Model role" column to the documentation workbook's metadata
      sheet and a "model_variables" sheet with the table below,
    - lists the spec in ANALYSIS_SUMMARY.md.

Roles:
    Endogenous - explained by the model; own equation, own + others' lags.
    Exogenous  - taken as given; enters every equation, no equation of its own.
    Input      - NOT a model variable: a raw series a model variable is
                 constructed from, kept so the construction can be checked.
    Not included - in the literature model, but not available here.
"""

SPODNIAK_BASELINE = {
    "title": "Baseline VAR (Spodniak et al. 2019; also Nieminen et al. 2023)",
    "reference": "spodniak2019relevance",
    # Cross-border flows: a connection is dropped from an area's VAR when its
    # mean |hourly flow| is below this share of the sum over all the area's
    # connections (select_flow_columns below).
    "flow_min_share": 0.05,
    "notes": [
        "Time resolution: hourly. Per bidding zone (DK1, DK2): estimate one VAR per zone.",
        "The three spreads are linearly dependent: (DA-BAL) = (DA-ID) + (ID-BAL) holds exactly in "
        "every hour. With all three as endogenous variables in ONE VAR the lagged regressors are "
        "perfectly collinear and the residual covariance is singular; check how the reference "
        "paper handles this (e.g. separate VARs per spread, or two of the three) before estimating.",
        "Lags in the literature: 1-24 and 48 (25 lags); a shorter version is compared via AIC/BIC "
        "and residual autocorrelation tests (see the thesis chapter).",
        "Fixed effects are stored as identifiers (fe_hour 0-23, fe_week_of_sample 1..N); expand "
        "them to dummy variables at estimation time (drop one category each if a constant is "
        "included).",
        "Hydro deviation (in the original study) is not included: reservoir filling (NO, SE, FI) is "
        "available for 2022-2025 only, too short for its running historical median.",
    ],
    "variables": [
        {
            "name": "DA-ID spread", "column": "x_da_id_spread", "role": "Endogenous",
            "market": "Cross-market (DA-ID)", "unit": "EUR/MWh",
            "definition": "S_DA-ID = P_DA - P_ID; P_ID = hourly volume-weighted intraday price, hours "
                          "without intraday trades replaced by P_DA",
            "interpretation": "Adjustment need due to supply/demand forecasting errors",
            "literature_source": "ENTSO-E / Nord Pool (DA); Nord Pool FTP (ID)",
            "source_here": "Nord Pool Data Portal API: day-ahead prices; intraday hourly statistics (VWAP)",
            "deviation": "ID VWAP from the Nord Pool Data Portal (continuous intraday, SIDC) instead of "
                         "the Nord Pool FTP server; where Nord Pool delivers 15-min products the hourly "
                         "VWAP is their volume-weighted mean.",
        },
        {
            "name": "DA-BAL spread", "column": "x_da_bal_spread", "role": "Endogenous",
            "market": "Cross-market (DA-BAL)", "unit": "EUR/MWh",
            "definition": "S_DA-BAL = P_DA - P_BAL; P_BAL = regulating power price by regulation "
                          "direction (up price / down price / DA price when no regulation)",
            "interpretation": "Scarcity of balancing resources; computed ex-post (imbalance price "
                              "disclosed with a delay)",
            "literature_source": "ENTSO-E / Nord Pool (DA); ENTSO-E (BAL)",
            "source_here": "Nord Pool Data Portal API: day-ahead prices; mFRR / imbalance price",
            "deviation": "P_BAL = Nord Pool imbalance price. Verified for 2022-2024 to equal the "
                         "direction-based regulating price (up hours: = up price 100 %; down hours: = "
                         "down price 100 %; no regulation: = DA price 99.7 %). From March 2025 (mFRR "
                         "EAM, 15-min settlement) it is the hourly mean of the 15-min imbalance prices, "
                         "which cannot be rebuilt from an hourly direction.",
        },
        {
            "name": "ID-BAL spread", "column": "x_id_bal_spread", "role": "Endogenous",
            "market": "Cross-market (ID-BAL)", "unit": "EUR/MWh",
            "definition": "S_ID-BAL = P_ID - P_BAL (P_ID and P_BAL as above)",
            "interpretation": "Incentive (opportunity cost) to reduce imbalances in the intraday market",
            "literature_source": "Nord Pool FTP (ID); ENTSO-E (BAL)",
            "source_here": "Nord Pool Data Portal API: intraday hourly statistics; mFRR / imbalance price",
            "deviation": "As for the DA-ID and DA-BAL spreads.",
        },
        {
            "name": "Wind forecast error", "column": "c_wind_total_err", "role": "Endogenous",
            "market": "Fundamentals (wind)", "unit": "MWh (hourly mean MW = MWh per hour)",
            "definition": "WE_t = W^_t - W_t (forecast - actual; positive = over-forecast), onshore + "
                          "offshore wind",
            "interpretation": "Wind surprise the short-term markets must absorb",
            "literature_source": "ENTSO-E: forecast 14.1.D (published 18:00 CET on D-1) and actual "
                                 "generation",
            "source_here": "Nord Pool Data Portal API (Power System): day-ahead production prognosis "
                           "and actual production",
            "deviation": "Forecast is Nord Pool's day-ahead prognosis, not ENTSO-E 14.1.D; its "
                         "publication time is NOT in the data, so it may differ from the 18:00 CET D-1 "
                         "forecast of the literature. Verify before comparing magnitudes.",
        },
        {
            "name": "Demand forecast error", "column": "c_load_err", "role": "Endogenous",
            "market": "Fundamentals (demand)", "unit": "MWh (hourly mean MW = MWh per hour)",
            "definition": "LE_t = L^_t - L_t (forecast - actual; positive = over-forecast)",
            "interpretation": "Demand surprise the short-term markets must absorb",
            "literature_source": "ENTSO-E: load forecast and actual load",
            "source_here": "Nord Pool Data Portal API (Power System): consumption prognosis and actual "
                           "consumption",
            "deviation": "Nord Pool consumption prognosis instead of the ENTSO-E load forecast; "
                         "publication time not in the data.",
        },
        {
            "name": "Wind ramp", "column": "c_wind_total_actual_mw_change_1", "role": "Exogenous",
            "market": "Fundamentals (wind)", "unit": "MWh/h",
            "definition": "R_t = W_t - W_(t-1) (hourly change in actual wind production; positive = "
                          "ramping up)",
            "interpretation": "Sudden changes in intermittent output that flexible resources must "
                              "accommodate",
            "literature_source": "ENTSO-E: actual wind generation",
            "source_here": "Nord Pool Data Portal API (Power System): actual production, onshore + "
                           "offshore",
            "deviation": "Nord Pool actual production instead of ENTSO-E.",
        },
        # Cross-border flows, one variable per interconnection. They replace
        # the literature's price-based bottleneck indicator (zone price !=
        # system price), which was 1 in 99.6-99.9 % of hours for DK1/DK2.
        *[{
            "name": f"Cross-border flow, {counterpart}", "column": f"da_flow_{code}_net_export_mw",
            "role": "Exogenous", "market": "Cross-border flows", "unit": "MWh/h",
            "definition": f"F_t = export_t - import_t on the interconnection with {counterpart} "
                          f"(positive = export from the zone, negative = import)",
            "interpretation": "Use of the interconnection: how much of the zone's imbalance is "
                              "moved across the border",
            "literature_source": "— (replaces the price-based bottleneck indicator of the literature)",
            "source_here": "Nord Pool Data Portal API: DayAheadFlow (import / export per connection)",
            "deviation": "Day-ahead scheduled exchange, not physical flows (physical flows are not in "
                         "the data); no Great Britain (Viking Link) connection in the data. Per zone only "
                         "the connections above flow_min_share enter the VAR (select_flow_columns).",
        } for code, counterpart in [("ger", "Germany"), ("nl", "Netherlands"), ("no2", "Norway (NO2)"),
                                    ("se3", "Sweden (SE3)"), ("se4", "Sweden (SE4)"),
                                    ("dk1", "DK1 (Great Belt)"), ("dk2", "DK2 (Great Belt)")]],
        {
            "name": "Hour fixed effects", "column": "fe_hour", "role": "Exogenous",
            "market": "Calendar", "unit": "category (0-23)",
            "definition": "D_hour,h,t = 1[hour(t) = h], one dummy per hour",
            "interpretation": "Diurnal pattern",
            "literature_source": "Calendar",
            "source_here": "Calendar (Copenhagen local time)",
            "deviation": "Stored as an identifier; expand to dummies at estimation.",
        },
        {
            "name": "Week fixed effects", "column": "fe_week_of_sample", "role": "Exogenous",
            "market": "Calendar", "unit": "category (1..N)",
            "definition": "D_week,w,t = 1[week(t) = w], one dummy per week of the sample",
            "interpretation": "Seasonal pattern",
            "literature_source": "Calendar",
            "source_here": "Calendar (Monday-Sunday weeks, Copenhagen local time)",
            "deviation": "Stored as an identifier; expand to dummies at estimation. Used only if the "
                         "monthly effects are not enough (calendar controls chosen coarse to fine in "
                         "stationarity_lag_selection.py).",
        },
        {
            "name": "Month fixed effects", "column": "fe_month_of_sample", "role": "Exogenous",
            "market": "Calendar", "unit": "category (1..N)",
            "definition": "D_month,m,t = 1[month(t) = m], one dummy per calendar month of the sample",
            "interpretation": "Slow movement of the level (coarser than the weekly effects)",
            "literature_source": "— (coarser alternative to the weekly effects)",
            "source_here": "Calendar (calendar months, Copenhagen local time)",
            "deviation": "Stored as an identifier; expand to dummies at estimation. The VARX uses hour + "
                         "month effects if, after removing them, every endogenous series is stationary; "
                         "otherwise hour + week effects (stationarity_lag_selection.py).",
        },
        {
            "name": "Hydro deviation", "column": None, "role": "Not included",
            "market": "Fundamentals (hydro)", "unit": "%",
            "definition": "Reservoir filling minus its running historical median (NO, SE, FI)",
            "interpretation": "Seasonal hydrological conditions",
            "literature_source": "Reservoir data",
            "source_here": "Nord Pool Data Portal API: Reservoir report (weekly filling, NO / SE / FI)",
            "deviation": "Reservoir filling for NO, SE, FI and the sub-areas NO1-NO5 / SE1-SE4 is in the "
                         "dataframe (inputs c_reservoir_fill_pct_*, 2022-2025), but there are no years before 2022 "
                         "for the running historical median, so the deviation itself is not computed.",
        },
    ],
    # Raw series the model variables are built from (role "Input"), grouped
    # by market. Kept so every construction can be checked in the data.
    "inputs": {
        "Day-ahead": ["da_price", "da_system_price"],
        "Intraday": ["id_vwap", "id_transaction_volume_mwh"],
        "Balancing": ["b_imbalance_price", "b_mfrr_up_price", "b_mfrr_down_price", "b_dominating_direction"],
        "Fundamentals (wind)": ["c_wind_total_forecast_mw", "c_wind_total_actual_mw"],
        "Fundamentals (demand)": ["c_load_forecast_mw", "c_load_actual_mw"],
        # Country totals (the literature's hydro areas) and every sub-area, since
        # hydro conditions in a single neighbouring area (e.g. NO2, SE3, SE4 —
        # all connected to DK) may matter for the Danish spreads.
        "Fundamentals (hydro)": ["c_reservoir_fill_pct_no", "c_reservoir_fill_pct_se", "c_reservoir_fill_pct_fi",
                                 "c_reservoir_fill_pct_no1", "c_reservoir_fill_pct_no2", "c_reservoir_fill_pct_no3",
                                 "c_reservoir_fill_pct_no4", "c_reservoir_fill_pct_no5",
                                 "c_reservoir_fill_pct_se1", "c_reservoir_fill_pct_se2", "c_reservoir_fill_pct_se3",
                                 "c_reservoir_fill_pct_se4"],
    },
}

MODEL_SPECS = {
    "spodniak2019_baseline": SPODNIAK_BASELINE,
}


def spec_columns(spec: dict) -> list:
    """Dataframe columns for a spec: inputs grouped by market, then the model
    variables (endogenous, exogenous)."""
    cols = [c for group in spec["inputs"].values() for c in group]
    for role in ("Endogenous", "Exogenous"):
        cols += [v["column"] for v in spec["variables"] if v["role"] == role and v["column"]]
    return list(dict.fromkeys(cols))


def spec_roles(spec: dict) -> dict:
    """{column: role} — 'Endogenous' / 'Exogenous' / 'Input'."""
    roles = {c: "Input" for group in spec["inputs"].values() for c in group}
    roles.update({v["column"]: v["role"] for v in spec["variables"] if v["column"]})
    return roles


def flow_columns(spec: dict) -> list:
    """The spec's cross-border flow columns (exogenous, market 'Cross-border flows')."""
    return [v["column"] for v in spec["variables"] if v.get("market") == "Cross-border flows"]


def select_flow_columns(df, spec: dict, group_col: str = "bidding_zone", verbose: bool = True) -> dict:
    """{zone: [flow columns kept]}. Per zone, a connection is kept when its mean
    absolute hourly flow is at least spec['flow_min_share'] of the sum of the
    mean absolute flows of all that zone's connections; counterparts the zone
    is not connected to (flow 0 in every hour) are dropped by the same rule.
    Prints the table and the kept / dropped connections per zone."""
    import pandas as pd

    threshold = spec.get("flow_min_share", 0.05)
    cols = [c for c in flow_columns(spec) if c in df.columns]
    kept = {}
    for zone, g in df.groupby(group_col):
        mean_abs = g[cols].abs().mean()
        share = mean_abs / mean_abs.sum() if mean_abs.sum() > 0 else mean_abs * 0
        table = pd.DataFrame({"mean_abs_flow_mwh_h": mean_abs.round(1), "share_pct": (100 * share).round(1),
                              "missing_hours": g[cols].isna().sum(), "kept": share >= threshold})
        kept[zone] = [c for c in cols if share[c] >= threshold]
        if verbose:
            print(f"\n  Cross-border flows, {zone} (threshold {threshold:.0%} of the zone's total mean |flow|):")
            print("    " + table[table["mean_abs_flow_mwh_h"] > 0].to_string().replace("\n", "\n    "))
            dropped = [c for c in cols if c not in kept[zone] and mean_abs[c] > 0]
            print(f"    kept: {kept[zone]}")
            print(f"    dropped (below threshold): {dropped or 'none'}; "
                  f"not connected (0 in every hour): {[c for c in cols if mean_abs[c] == 0]}")
    return kept


def spec_input_markets(spec: dict) -> dict:
    """{input column: market group} as listed in the spec."""
    return {c: market for market, cols in spec["inputs"].items() for c in cols}
