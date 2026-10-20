# Analysis summary — `baseline_2025`

_Generated 2026-10-14 18:31 by `main.py` (step 6). Purpose: tell another assistant what has already been built, verified and plotted, so it is not repeated._

## 1. Dataframe
- File: `data/dataframes/baseline_2025.csv` — panel, one row per (delivery hour UTC, bidding zone).
- Period: 2025-01-01 00:00 to 2025-12-31 23:00 UTC; 17,520 rows; zones: DK1, DK2.
- Markets selected: day_ahead, intraday, balancing, fundamentals.
- **42 columns**: 2 key (datetime_utc, bidding_zone), 22 from sources, 18 derived.
- **Day-ahead** (`da_*`, 9): `da_price`, `da_system_price`, `da_flow_ger_net_export_mw`, `da_flow_nl_net_export_mw`, `da_flow_no2_net_export_mw`, `da_flow_se3_net_export_mw`, `da_flow_se4_net_export_mw`, `da_flow_dk1_net_export_mw`, `da_flow_dk2_net_export_mw`
- **Intraday** (`id_*`, 2): `id_vwap`, `id_transaction_volume_mwh`
- **Balancing** (`b_*`, 4): `b_imbalance_price`, `b_mfrr_up_price`, `b_mfrr_down_price`, `b_dominating_direction`
- **Fundamentals** (`c_*`, 19): `c_wind_total_forecast_mw`, `c_wind_total_actual_mw`, `c_load_forecast_mw`, `c_load_actual_mw`, `c_reservoir_fill_pct_no`, `c_reservoir_fill_pct_se`, `c_reservoir_fill_pct_fi`, `c_reservoir_fill_pct_no1`, `c_reservoir_fill_pct_no2`, `c_reservoir_fill_pct_no3`, `c_reservoir_fill_pct_no4`, `c_reservoir_fill_pct_no5`, `c_reservoir_fill_pct_se1`, `c_reservoir_fill_pct_se2`, `c_reservoir_fill_pct_se3`, `c_reservoir_fill_pct_se4`, `c_wind_total_err`, `c_load_err`, `c_wind_total_actual_mw_change_1`
- **Cross-market** (`x_*`, 3): `x_da_id_spread`, `x_da_bal_spread`, `x_id_bal_spread`
- **Calendar (fixed-effect identifiers)** (`fe_*`, 3): `fe_hour`, `fe_week_of_sample`, `fe_month_of_sample`

### Model specification (endogenous / exogenous)
**Baseline VAR (Spodniak et al. 2019; also Nieminen et al. 2023)** — full table incl. sources and deviations from the literature in the documentation workbook's `model_variables` sheet (`src/model_specs.py`).

| role | market | variable | column | definition |
|---|---|---|---|---|
| Endogenous | Cross-market (DA-ID) | DA-ID spread | `x_da_id_spread` | S_DA-ID = P_DA - P_ID; P_ID = hourly volume-weighted intraday price, hours without intraday trades replaced by P_DA |
| Endogenous | Cross-market (DA-BAL) | DA-BAL spread | `x_da_bal_spread` | S_DA-BAL = P_DA - P_BAL; P_BAL = regulating power price by regulation direction (up price / down price / DA price when no regulation) |
| Endogenous | Cross-market (ID-BAL) | ID-BAL spread | `x_id_bal_spread` | S_ID-BAL = P_ID - P_BAL (P_ID and P_BAL as above) |
| Endogenous | Fundamentals (wind) | Wind forecast error | `c_wind_total_err` | WE_t = W^_t - W_t (forecast - actual; positive = over-forecast), onshore + offshore wind |
| Endogenous | Fundamentals (demand) | Demand forecast error | `c_load_err` | LE_t = L^_t - L_t (forecast - actual; positive = over-forecast) |
| Exogenous | Fundamentals (wind) | Wind ramp | `c_wind_total_actual_mw_change_1` | R_t = W_t - W_(t-1) (hourly change in actual wind production; positive = ramping up) |
| Exogenous | Cross-border flows | Cross-border flow, Germany | `da_flow_ger_net_export_mw` | F_t = export_t - import_t on the interconnection with Germany (positive = export from the zone, negative = import) |
| Exogenous | Cross-border flows | Cross-border flow, Netherlands | `da_flow_nl_net_export_mw` | F_t = export_t - import_t on the interconnection with Netherlands (positive = export from the zone, negative = import) |
| Exogenous | Cross-border flows | Cross-border flow, Norway (NO2) | `da_flow_no2_net_export_mw` | F_t = export_t - import_t on the interconnection with Norway (NO2) (positive = export from the zone, negative = import) |
| Exogenous | Cross-border flows | Cross-border flow, Sweden (SE3) | `da_flow_se3_net_export_mw` | F_t = export_t - import_t on the interconnection with Sweden (SE3) (positive = export from the zone, negative = import) |
| Exogenous | Cross-border flows | Cross-border flow, Sweden (SE4) | `da_flow_se4_net_export_mw` | F_t = export_t - import_t on the interconnection with Sweden (SE4) (positive = export from the zone, negative = import) |
| Exogenous | Cross-border flows | Cross-border flow, DK1 (Great Belt) | `da_flow_dk1_net_export_mw` | F_t = export_t - import_t on the interconnection with DK1 (Great Belt) (positive = export from the zone, negative = import) |
| Exogenous | Cross-border flows | Cross-border flow, DK2 (Great Belt) | `da_flow_dk2_net_export_mw` | F_t = export_t - import_t on the interconnection with DK2 (Great Belt) (positive = export from the zone, negative = import) |
| Exogenous | Calendar | Hour fixed effects | `fe_hour` | D_hour,h,t = 1[hour(t) = h], one dummy per hour |
| Exogenous | Calendar | Week fixed effects | `fe_week_of_sample` | D_week,w,t = 1[week(t) = w], one dummy per week of the sample |
| Exogenous | Calendar | Month fixed effects | `fe_month_of_sample` | D_month,m,t = 1[month(t) = m], one dummy per calendar month of the sample |
| Not included | Fundamentals (hydro) | Hydro deviation | — | Reservoir filling minus its running historical median (NO, SE, FI) |

- Inputs (role 'Input': raw series the variables are built from, not model variables): Day-ahead: `da_price`, `da_system_price`; Intraday: `id_vwap`, `id_transaction_volume_mwh`; Balancing: `b_imbalance_price`, `b_mfrr_up_price`, `b_mfrr_down_price`, `b_dominating_direction`; Fundamentals (wind): `c_wind_total_forecast_mw`, `c_wind_total_actual_mw`; Fundamentals (demand): `c_load_forecast_mw`, `c_load_actual_mw`; Fundamentals (hydro): `c_reservoir_fill_pct_no`, `c_reservoir_fill_pct_se`, `c_reservoir_fill_pct_fi`, `c_reservoir_fill_pct_no1`, `c_reservoir_fill_pct_no2`, `c_reservoir_fill_pct_no3`, `c_reservoir_fill_pct_no4`, `c_reservoir_fill_pct_no5`, `c_reservoir_fill_pct_se1`, `c_reservoir_fill_pct_se2`, `c_reservoir_fill_pct_se3`, `c_reservoir_fill_pct_se4`.
- Time resolution: hourly. Per bidding zone (DK1, DK2): estimate one VAR per zone.
- The three spreads are linearly dependent: (DA-BAL) = (DA-ID) + (ID-BAL) holds exactly in every hour. With all three as endogenous variables in ONE VAR the lagged regressors are perfectly collinear and the residual covariance is singular; check how the reference paper handles this (e.g. separate VARs per spread, or two of the three) before estimating.
- Lags in the literature: 1-24 and 48 (25 lags); a shorter version is compared via AIC/BIC and residual autocorrelation tests (see the thesis chapter).
- Fixed effects are stored as identifiers (fe_hour 0-23, fe_week_of_sample 1..N); expand them to dummy variables at estimation time (drop one category each if a constant is included).
- Hydro deviation (in the original study) is not included: reservoir filling (NO, SE, FI) is available for 2022-2025 only, too short for its running historical median.


## 2. Pipeline (code)
- `main.py` (project root): configure DATAFRAMES / STEPS, then build -> documentation -> visualisation -> correlation -> structural breaks -> this summary.
- `src/dataframe_building.py`: SOURCES, MARKETS, DERIVED_FEATURES (one registry each).
- `src/dataframe_documentation.py`: metadata + distribution workbook.
- `src/visualisation/visualize_dataframe.py`, `src/statsistics/correlation_analysis.py`.
- `src/imports/*.py`: download + cache raw data -> `data/processed/` (not run by main.py).

### Derived feature configuration
- Representative prices: da=`da_price`, id=`id_vwap`, bal=`b_imbalance_price`; each gets change_1, abs_change_1, std_24, std_168, range_24.
- Cross-market spreads: `x_da_id_spread`, `x_id_bal_spread`, `x_da_bal_spread`, each with `_abs` and `_std_24`.
- Physical ramp/variability: `c_residual_load_forecast_mw` (change_1/std_24), `c_residual_load_actual_mw` (change_1/std_24), `c_wind_total_forecast_mw` (change_1/std_24), `c_wind_total_actual_mw` (change_1/std_24), `c_solar_forecast_mw` (change_1), `c_load_forecast_mw` (change_1).
- Rolling windows need >= 80% of the window observed; warm-up 168 h before the start date.

## 3. Settled facts and decisions (do not re-investigate)
- Timestamps: EVERY source is genuine UTC (all Nord Pool feeds and ENTSO-E/Energinet). Verified 2026-10-07 from the raw responses (delivery day CET starts at 23:00Z the day before) and three data checks (imbalance = DA price in 99.7 % of no-regulation hours; ID VWAP tracks DA best unshifted; solar peaks at solar noon UTC). An earlier '-1 h Nord Pool CET fix' on mFRR/intraday/forecasts was WRONG (it put those columns one hour early) and was removed; any result produced before then (e.g. 'intraday leads DA by 1 h') is invalid.
- All sources are hourly in the dataframe; 15-min data was aggregated in the import scripts (MW values: hourly mean; intraday VWAPs: volume-weighted; intraday volumes: summed).
- Flow columns that are always 0 in one zone are STRUCTURAL, not a bug: a zone's own border (da_flow_dk1_* in DK1 rows) and borders it doesn't have (SE4 for DK1; NL/SE3/NO2 for DK2). Drop them per zone before a single-zone VAR (dataframe_building.filter_to_area).
- Flow net position sign: positive = row zone is a net IMPORTER (checked: corr = -1 with export - import; matches the Nord Pool 'Net Exchange' chart).
- b_dominating_direction: Up = +1, Down = -1, empty = 0 (no regulation: in 2022-2024 imbalance price = DA price and zero mFRR activation in 99-100 % of empty hours; 2025 less clean, 40 % / 52 %). Hourly value = majority of the 15-min values in that hour; ties broken by that hour's net mFRR activation, not alphabetically.
- Imbalance price (P_BAL): equals the up price in up-regulation hours, the down price in down hours and the DA price without regulation (2022-2024: 100 / 100 / 99.7 %); from 2025 it is the hourly mean of 15-min prices and cannot be rebuilt from an hourly direction.
- Forecast errors (all c_*_err) are FORECAST - ACTUAL (positive = over-forecast), the baseline literature convention. Intraday hours with zero traded volume have no VWAP; for the spreads they take the DA price inside the spread calculation (no separate filled column), as in the literature.
- Derived lag/rolling features are computed per bidding zone, trailing windows ending at t (no look-ahead), no interpolation; the grid is built a week early (warm-up) and trimmed.
- One representative price per market is used for price-dynamics features (avoids near-duplicates); old id_da_spread / b_da_spread were removed as sign-flipped duplicates of the x_ spreads.
- No percentage changes for prices/spreads (can be 0 or negative); renewables totals are computed from components in DERIVED_FEATURES, not taken from the source's own totals.
- The literature's price-based bottleneck indicator (zone DA price != Nord Pool system price) was 1 in 99.6-99.9 % of hours for DK1/DK2 in 2022-2025 and has been replaced by cross-border flows (da_flow_<counterpart>_net_export_mw, Nord Pool day-ahead scheduled exchange, positive = export); per zone only connections with >= 5 % of the zone's total mean |flow| enter the VAR.
- Reservoir filling (Nord Pool, weekly, % of capacity) for NO, SE, FI and NO1-NO5 / SE1-SE4: weekly value applied to every hour of its own Monday-Sunday week (look-ahead up to ~7 days, flagged); copied to both DK zones. NO differs from the sum of NO1-NO5 by up to 0.67 % in 19 of 300 weeks; SE matches its sub-areas exactly. Only 2022-2025: no historical median for the hydro deviation.
- Leakage/timing: each column's delivery time vs. availability time and a leakage flag are in the documentation workbook's metadata sheet. Forecast publication times are an ASSUMPTION (D-1; the data has no issue timestamp).

## 4. Documentation workbook findings
- Workbook: `data/dataframes/documentation/baseline_2025_documentation.xlsx` — sheets README, metadata (meaning, unit, delivery vs availability time, leakage, source, ...), distribution (mean/median/std/quantiles/skew/kurtosis/zero/negative/extreme %, per zone).
- Columns flagged potential leakage (not known before delivery): 23 of 40.
- Suspected duplicate pairs (|r| >= 0.99): `x_da_bal_spread` ~ `x_id_bal_spread` (r=+0.992); `fe_month_of_sample` ~ `fe_week_of_sample` (r=+0.996); `c_reservoir_fill_pct_no` ~ `c_reservoir_fill_pct_no5` (r=+0.993)
- Missingness > 1 %: `c_wind_total_err` 1.4 %, `c_wind_total_forecast_mw` 1.4 %

## 5. Plots and tables produced
- `plots/baseline_2025/timeseries/` — 13 PNG, 0 CSV. Model variables only, split into endogenous/ and exogenous/: hourly values, one panel per zone (without a model spec: every feature, one figure per column family).
- `plots/baseline_2025/distributions/` — 13 PNG, 0 CSV. Histogram per variable, DK1 vs DK2 overlaid (endogenous/ and exogenous/).
- `plots/baseline_2025/seasonals/hour_of_day/` — 13 PNG, 0 CSV. 24 h profile (Copenhagen local time), one panel per zone: min-max, 10-90 % and 25-75 % bands across days, mean (solid) and median (dashed).
- `plots/baseline_2025/seasonals/hour_of_day_by_season/` — 20 PNG, 0 CSV. 24 h profile per meteorological season, one file per zone.
- `plots/baseline_2025/seasonals/hour_of_week/` — 13 PNG, 0 CSV. Average 7-day profile: 168 hourly means, Mon -> Sun.
- `plots/baseline_2025/seasonals/month_of_year/` — 13 PNG, 0 CSV. Mean per calendar month (years pooled).
- `plots/baseline_2025/stats/` — 16 PNG, 0 CSV. Per role (endogenous/, exogenous/): std & variance within each day / week / month, 7-day rolling std, mean absolute hourly change.
- `plots/baseline_2025/correlation/` — 54 PNG, 2 CSV. Per zone + pooled: pair ranking (most to least correlated pair of different columns, at its strongest lag; pair_ranking_clean: without forecast-vs-actual pairs, reservoir-vs-reservoir pairs and |r| < 0.3), model/: endogenous + exogenous correlation matrix per lag and cross-correlation curves over all lags; all_columns/: matrix per lag without the reservoirs plus reservoirs x other columns; per-zone numbers in tables/.
- `plots/baseline_2025/structural_breaks/` — 3 PNG, 0 CSV. Mean and variance breaks of the DA / ID / balancing prices per zone (CUSUM + HAC, binary segmentation): STRUCTURAL_BREAKS.md (break table, classification), plots.

## 6. Statistics of the model variables
Both zones pooled, hourly values:

| feature | unit | mean | std | variance | mean abs 1h change |
|---|---|---|---|---|---|
| x_da_id_spread | EUR/MWh | 0.35 | 19.67 | 387 | 7.25 |
| x_da_bal_spread | EUR/MWh | -1.81 | 158.38 | 25,084 | 78.55 |
| x_id_bal_spread | EUR/MWh | -2.16 | 156.88 | 24,611 | 78.78 |
| c_wind_total_err | MW | -121.34 | 400.15 | 160,116 | 82.03 |
| c_load_err | MW | -16.62 | 162.78 | 26,497 | 57.62 |
| c_wind_total_actual_mw_change_1 | MW | -0.07 | 155.49 | 24,176 | 92.31 |
| da_flow_ger_net_export_mw | MWh/h | 832.68 | 1,214.06 | 1,473,930 | 213.70 |
| da_flow_nl_net_export_mw | MWh/h | -35.68 | 397.19 | 157,759 | 75.43 |
| da_flow_no2_net_export_mw | MWh/h | -441.20 | 764.70 | 584,766 | 69.23 |
| da_flow_se3_net_export_mw | MWh/h | -200.46 | 340.80 | 116,143 | 35.45 |
| da_flow_se4_net_export_mw | MWh/h | -436.08 | 561.83 | 315,656 | 47.41 |
| da_flow_dk1_net_export_mw | MWh/h | -32.39 | 238.98 | 57,113 | 48.58 |
| da_flow_dk2_net_export_mw | MWh/h | 32.39 | 238.98 | 57,113 | 48.58 |

## 7. Correlation headline
Pairs whose two columns share a source input (e.g. a spread's volatility vs. the price it contains) are left out as mechanical; a lag-0 pair is listed once.

**DK1** — strongest cross-market pairs (col_1 at t -> col_2 at t + lag):

| col_1 | col_2 | lag (h) | r |
|---|---|---|---|
| da_price | id_vwap | 0 | +0.938 |
| da_price | b_mfrr_down_price | 0 | +0.795 |
| id_vwap | b_mfrr_down_price | 0 | +0.795 |
| b_mfrr_up_price | x_id_bal_spread | 0 | -0.711 |
| b_mfrr_up_price | x_da_bal_spread | 0 | -0.706 |
| da_system_price | id_vwap | 0 | +0.635 |
| id_vwap | da_flow_no2_net_export_mw | 0 | -0.602 |
| da_system_price | b_mfrr_down_price | 0 | +0.570 |
| b_mfrr_down_price | da_flow_no2_net_export_mw | 0 | -0.526 |
| id_transaction_volume_mwh | c_wind_total_actual_mw | 1 | +0.505 |

Weakly related to everything (max |r| below threshold): none

**DK2** — strongest cross-market pairs (col_1 at t -> col_2 at t + lag):

| col_1 | col_2 | lag (h) | r |
|---|---|---|---|
| da_price | id_vwap | 0 | +0.928 |
| da_price | b_mfrr_down_price | 0 | +0.749 |
| id_vwap | b_mfrr_down_price | 0 | +0.746 |
| b_mfrr_up_price | x_id_bal_spread | 0 | -0.706 |
| b_mfrr_up_price | x_da_bal_spread | 0 | -0.704 |
| da_system_price | id_vwap | 0 | +0.642 |
| da_system_price | b_mfrr_down_price | 0 | +0.546 |
| id_vwap | c_wind_total_forecast_mw | 1 | -0.385 |
| id_vwap | b_mfrr_up_price | 0 | +0.383 |
| da_price | b_mfrr_up_price | 0 | +0.377 |

Weakly related to everything (max |r| below threshold): none

## 8. Structural breaks (prices)
Statistical detection only (method and caveats: `structural_breaks/STRUCTURAL_BREAKS.md`). Daily series; mean = CUSUM on daily mean price, variance = CUSUM on log within-day variance; HAC long-run variance; binary segmentation.

### Detected breaks

| Market | Zone | Break date | Break type | Before | After | Change | Statistical evidence |
|---|---|---|---|---|---|---|---|
| Day-ahead | DK1 | 2025-03-17 | Variance | var 2,775; within-day std 25.8 | var 2,560; within-day std 40.9 | var x0.92; within-day std x1.59 (tested) | var: CUSUM 3.47, adj. p = 0.0015 |
| Day-ahead | DK1 | 2025-07-05 | Variance | var 2,560; within-day std 40.9 | var 2,402; within-day std 34.0 | var x0.94; within-day std x0.83 (tested) | var: CUSUM 2.78, adj. p = 0.0050 |
| Day-ahead | DK1 | 2025-10-03 | Variance | var 2,402; within-day std 34.0 | var 1,930; within-day std 18.9 | var x0.80; within-day std x0.56 (tested) | var: CUSUM 3.76, adj. p = 0.0005 |
| Day-ahead | DK2 | 2025-07-05 | Variance | var 3,060; within-day std 34.3 | var 2,292; within-day std 35.6 | var x0.75; within-day std x1.04 (tested) | var: CUSUM 2.70, adj. p = 0.0100 |
| Day-ahead | DK2 | 2025-10-03 | Variance | var 2,292; within-day std 35.6 | var 2,279; within-day std 22.4 | var x0.99; within-day std x0.63 (tested) | var: CUSUM 3.22, adj. p = 0.0015 |
| Intraday | DK1 | 2025-03-16 | Variance | var 2,650; within-day std 25.4 | var 2,957; within-day std 40.7 | var x1.12; within-day std x1.60 (tested) | var: CUSUM 3.06, adj. p = 0.0015 |
| Intraday | DK1 | 2025-07-05 | Variance | var 2,957; within-day std 40.7 | var 2,573; within-day std 34.4 | var x0.87; within-day std x0.84 (tested) | var: CUSUM 2.82, adj. p = 0.0015 |
| Intraday | DK1 | 2025-10-04 | Variance | var 2,573; within-day std 34.4 | var 1,777; within-day std 19.8 | var x0.69; within-day std x0.57 (tested) | var: CUSUM 3.42, adj. p = 0.0005 |
| Balancing | DK1 | 2025-03-10 | Variance | var 20,361; within-day std 55.3 | var 31,996; within-day std 107.8 | var x1.57; within-day std x1.95 (tested) | var: CUSUM 4.02, adj. p = 0.0005 |
| Balancing | DK1 | 2025-10-31 | Variance | var 31,996; within-day std 107.8 | var 9,593; within-day std 50.3 | var x0.30; within-day std x0.47 (tested) | var: CUSUM 3.16, adj. p = 0.0005 |
| Balancing | DK2 | 2025-03-13 | Variance | var 13,074; within-day std 60.3 | var 37,487; within-day std 116.6 | var x2.87; within-day std x1.93 (tested) | var: CUSUM 3.69, adj. p = 0.0005 |
| Balancing | DK2 | 2025-11-08 | Variance | var 37,487; within-day std 116.6 | var 9,175; within-day std 62.6 | var x0.24; within-day std x0.54 (tested) | var: CUSUM 2.90, adj. p = 0.0010 |

### Regime classification (statistical)

| Market | Zone | Price column | Mean | Variance | Distinct regimes | Range of regime means | Range of regime variances |
|---|---|---|---|---|---|---|---|
| Day-ahead | DK1 | da_price | relatively stable mean | significant variance shifts (3 breaks) | yes — 1 mean regime(s), 4 variance regime(s) | 81.1 to 81.1 | 1,930 to 2,775 |
| Day-ahead | DK2 | da_price | relatively stable mean | significant variance shifts (2 breaks) | yes — 1 mean regime(s), 3 variance regime(s) | 82.5 to 82.5 | 2,279 to 3,060 |
| Intraday | DK1 | id_vwap | relatively stable mean | significant variance shifts (3 breaks) | yes — 1 mean regime(s), 4 variance regime(s) | 79.7 to 79.7 | 1,777 to 2,957 |
| Intraday | DK2 | id_vwap | relatively stable mean | relatively stable variance | no — one regime over the period | 83.3 to 83.3 | 2,912 to 2,912 |
| Balancing | DK1 | b_imbalance_price | relatively stable mean | significant variance shifts (2 breaks) | yes — 1 mean regime(s), 3 variance regime(s) | 84.6 to 84.6 | 9,593 to 31,996 |
| Balancing | DK2 | b_imbalance_price | relatively stable mean | significant variance shifts (2 breaks) | yes — 1 mean regime(s), 3 variance regime(s) | 82.7 to 82.7 | 9,175 to 37,487 |

## 9. Not done yet
- Correlation-break and autocorrelation-break analysis (planned separately; only mean and variance breaks of the three market prices are done).
- Stationarity tests (ADF / KPSS) and any differencing decisions.
- Granger causality tests, VAR lag-order selection and VAR estimation.
- Final feature selection (the correlation and duplicate outputs are inputs to it, not the decision).
