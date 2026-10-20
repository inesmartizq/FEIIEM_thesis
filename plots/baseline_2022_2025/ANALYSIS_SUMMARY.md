# Analysis summary — `baseline_2022_2025`

_Generated 2026-10-14 18:30 by `main.py` (step 6). Purpose: tell another assistant what has already been built, verified and plotted, so it is not repeated._

## 1. Dataframe
- File: `data/dataframes/baseline_2022_2025.csv` — panel, one row per (delivery hour UTC, bidding zone).
- Period: 2022-01-01 00:00 to 2025-12-31 23:00 UTC; 70,128 rows; zones: DK1, DK2.
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
- Workbook: `data/dataframes/documentation/baseline_2022_2025_documentation.xlsx` — sheets README, metadata (meaning, unit, delivery vs availability time, leakage, source, ...), distribution (mean/median/std/quantiles/skew/kurtosis/zero/negative/extreme %, per zone).
- Columns flagged potential leakage (not known before delivery): 23 of 40.
- Suspected duplicate pairs (|r| >= 0.99): `fe_month_of_sample` ~ `fe_week_of_sample` (r=+1.000); `c_reservoir_fill_pct_no3` ~ `c_reservoir_fill_pct_se` (r=+0.990)

## 5. Plots and tables produced
- `plots/baseline_2022_2025/timeseries/` — 13 PNG, 0 CSV. Model variables only, split into endogenous/ and exogenous/: hourly values, one panel per zone (without a model spec: every feature, one figure per column family).
- `plots/baseline_2022_2025/distributions/` — 13 PNG, 0 CSV. Histogram per variable, DK1 vs DK2 overlaid (endogenous/ and exogenous/).
- `plots/baseline_2022_2025/seasonals/hour_of_day/` — 13 PNG, 0 CSV. 24 h profile (Copenhagen local time), one panel per zone: min-max, 10-90 % and 25-75 % bands across days, mean (solid) and median (dashed).
- `plots/baseline_2022_2025/seasonals/hour_of_day_by_season/` — 20 PNG, 0 CSV. 24 h profile per meteorological season, one file per zone.
- `plots/baseline_2022_2025/seasonals/hour_of_week/` — 13 PNG, 0 CSV. Average 7-day profile: 168 hourly means, Mon -> Sun.
- `plots/baseline_2022_2025/seasonals/month_of_year/` — 13 PNG, 0 CSV. Mean per calendar month (years pooled).
- `plots/baseline_2022_2025/stats/` — 16 PNG, 0 CSV. Per role (endogenous/, exogenous/): std & variance within each day / week / month, 7-day rolling std, mean absolute hourly change.
- `plots/baseline_2022_2025/correlation/` — 54 PNG, 2 CSV. Per zone + pooled: pair ranking (most to least correlated pair of different columns, at its strongest lag; pair_ranking_clean: without forecast-vs-actual pairs, reservoir-vs-reservoir pairs and |r| < 0.3), model/: endogenous + exogenous correlation matrix per lag and cross-correlation curves over all lags; all_columns/: matrix per lag without the reservoirs plus reservoirs x other columns; per-zone numbers in tables/.
- `plots/baseline_2022_2025/structural_breaks/` — 3 PNG, 0 CSV. Mean and variance breaks of the DA / ID / balancing prices per zone (CUSUM + HAC, binary segmentation): STRUCTURAL_BREAKS.md (break table, classification), plots.

## 6. Statistics of the model variables
Both zones pooled, hourly values:

| feature | unit | mean | std | variance | mean abs 1h change |
|---|---|---|---|---|---|
| x_da_id_spread | EUR/MWh | 1.15 | 23.41 | 548 | 7.87 |
| x_da_bal_spread | EUR/MWh | 0.24 | 106.31 | 11,302 | 41.90 |
| x_id_bal_spread | EUR/MWh | -0.91 | 103.51 | 10,714 | 43.62 |
| c_wind_total_err | MW | -107.81 | 356.47 | 127,068 | 76.69 |
| c_load_err | MW | -2.37 | 93.66 | 8,772 | 37.19 |
| c_wind_total_actual_mw_change_1 | MW | 0.03 | 144.81 | 20,969 | 84.18 |
| da_flow_ger_net_export_mw | MWh/h | 735.29 | 1,070.91 | 1,146,853 | 182.34 |
| da_flow_nl_net_export_mw | MWh/h | 32.91 | 395.24 | 156,212 | 70.71 |
| da_flow_no2_net_export_mw | MWh/h | -271.81 | 782.91 | 612,944 | 69.87 |
| da_flow_se3_net_export_mw | MWh/h | -130.68 | 379.44 | 143,977 | 37.86 |
| da_flow_se4_net_export_mw | MWh/h | -406.41 | 602.25 | 362,705 | 51.49 |
| da_flow_dk1_net_export_mw | MWh/h | 15.22 | 267.70 | 71,663 | 46.66 |
| da_flow_dk2_net_export_mw | MWh/h | -15.22 | 267.70 | 71,663 | 46.66 |

## 7. Correlation headline
Pairs whose two columns share a source input (e.g. a spread's volatility vs. the price it contains) are left out as mechanical; a lag-0 pair is listed once.

**DK1** — strongest cross-market pairs (col_1 at t -> col_2 at t + lag):

| col_1 | col_2 | lag (h) | r |
|---|---|---|---|
| da_price | id_vwap | 0 | +0.977 |
| da_price | b_mfrr_down_price | 0 | +0.919 |
| id_vwap | b_mfrr_down_price | 0 | +0.918 |
| id_vwap | b_mfrr_up_price | 0 | +0.797 |
| da_price | b_mfrr_up_price | 0 | +0.794 |
| da_system_price | id_vwap | 0 | +0.785 |
| da_system_price | b_mfrr_down_price | 0 | +0.772 |
| id_vwap | b_imbalance_price | 0 | +0.703 |
| da_price | b_imbalance_price | 0 | +0.683 |
| da_system_price | b_mfrr_up_price | 0 | +0.620 |

Weakly related to everything (max |r| below threshold): none

**DK2** — strongest cross-market pairs (col_1 at t -> col_2 at t + lag):

| col_1 | col_2 | lag (h) | r |
|---|---|---|---|
| da_price | id_vwap | 0 | +0.973 |
| da_price | b_mfrr_down_price | 0 | +0.916 |
| id_vwap | b_mfrr_down_price | 0 | +0.913 |
| da_system_price | id_vwap | 0 | +0.781 |
| da_system_price | b_mfrr_down_price | 0 | +0.773 |
| id_vwap | b_mfrr_up_price | 0 | +0.765 |
| da_price | b_mfrr_up_price | 0 | +0.763 |
| id_vwap | b_imbalance_price | 0 | +0.711 |
| da_price | b_imbalance_price | 0 | +0.691 |
| da_system_price | b_mfrr_up_price | 0 | +0.593 |

Weakly related to everything (max |r| below threshold): none

## 8. Structural breaks (prices)
Statistical detection only (method and caveats: `structural_breaks/STRUCTURAL_BREAKS.md`). Daily series; mean = CUSUM on daily mean price, variance = CUSUM on log within-day variance; HAC long-run variance; binary segmentation.

### Detected breaks

| Market | Zone | Break date | Break type | Before | After | Change | Statistical evidence |
|---|---|---|---|---|---|---|---|
| Day-ahead | DK1 | 2022-06-18 | Variance | var 7,460; within-day std 36.0 | var 24,639; within-day std 77.0 | var x3.30; within-day std x2.14 (tested) | var: CUSUM 5.56, adj. p = 0.0005 |
| Day-ahead | DK1 | 2022-10-05 | Variance | var 24,639; within-day std 77.0 | var 16,653; within-day std 39.2 | var x0.68; within-day std x0.51 (tested) | var: CUSUM 4.38, adj. p = 0.0005 |
| Day-ahead | DK1 | 2022-12-25 | Variance | var 16,653; within-day std 39.2 | var 2,377; within-day std 24.6 | var x0.14; within-day std x0.63 (tested) | var: CUSUM 4.51, adj. p = 0.0005 |
| Day-ahead | DK1 | 2023-12-15 | Variance | var 2,377; within-day std 24.6 | var 744; within-day std 13.4 | var x0.31; within-day std x0.54 (tested) | var: CUSUM 2.97, adj. p = 0.0045 |
| Day-ahead | DK1 | 2024-04-08 | Variance | var 744; within-day std 13.4 | var 3,218; within-day std 29.0 | var x4.33; within-day std x2.17 (tested) | var: CUSUM 5.91, adj. p = 0.0005 |
| Day-ahead | DK1 | 2025-03-17 | Variance | var 3,218; within-day std 29.0 | var 2,503; within-day std 37.7 | var x0.78; within-day std x1.30 (tested) | var: CUSUM 3.37, adj. p = 0.0005 |
| Day-ahead | DK1 | 2025-10-03 | Variance | var 2,503; within-day std 37.7 | var 1,930; within-day std 18.9 | var x0.77; within-day std x0.50 (tested) | var: CUSUM 3.74, adj. p = 0.0005 |
| Day-ahead | DK2 | 2022-06-18 | Variance | var 9,074; within-day std 41.9 | var 29,519; within-day std 80.6 | var x3.25; within-day std x1.93 (tested) | var: CUSUM 4.38, adj. p = 0.0005 |
| Day-ahead | DK2 | 2022-10-05 | Variance | var 29,519; within-day std 80.6 | var 16,756; within-day std 42.5 | var x0.57; within-day std x0.53 (tested) | var: CUSUM 3.92, adj. p = 0.0005 |
| Day-ahead | DK2 | 2022-12-25 | Variance | var 16,756; within-day std 42.5 | var 2,504; within-day std 25.5 | var x0.15; within-day std x0.60 (tested) | var: CUSUM 5.39, adj. p = 0.0005 |
| Day-ahead | DK2 | 2023-12-15 | Variance | var 2,504; within-day std 25.5 | var 1,171; within-day std 14.8 | var x0.47; within-day std x0.58 (tested) | var: CUSUM 3.04, adj. p = 0.0015 |
| Day-ahead | DK2 | 2024-04-07 | Variance | var 1,171; within-day std 14.8 | var 3,058; within-day std 32.6 | var x2.61; within-day std x2.21 (tested) | var: CUSUM 5.87, adj. p = 0.0005 |
| Day-ahead | DK2 | 2025-10-03 | Variance | var 3,058; within-day std 32.6 | var 2,279; within-day std 22.4 | var x0.75; within-day std x0.69 (tested) | var: CUSUM 3.21, adj. p = 0.0010 |
| Intraday | DK1 | 2022-06-16 | Variance | var 7,414; within-day std 36.7 | var 26,149; within-day std 78.6 | var x3.53; within-day std x2.14 (tested) | var: CUSUM 5.57, adj. p = 0.0005 |
| Intraday | DK1 | 2022-10-05 | Variance | var 26,149; within-day std 78.6 | var 17,919; within-day std 40.0 | var x0.69; within-day std x0.51 (tested) | var: CUSUM 3.43, adj. p = 0.0005 |
| Intraday | DK1 | 2022-12-21 | Variance | var 17,919; within-day std 40.0 | var 2,450; within-day std 22.1 | var x0.14; within-day std x0.55 (tested) | var: CUSUM 3.93, adj. p = 0.0005 |
| Intraday | DK1 | 2024-04-07 | Variance | var 2,450; within-day std 22.1 | var 3,971; within-day std 28.6 | var x1.62; within-day std x1.30 (tested) | var: CUSUM 5.67, adj. p = 0.0005 |
| Intraday | DK1 | 2025-03-16 | Variance | var 3,971; within-day std 28.6 | var 2,807; within-day std 37.8 | var x0.71; within-day std x1.32 (tested) | var: CUSUM 3.05, adj. p = 0.0030 |
| Intraday | DK1 | 2025-10-04 | Variance | var 2,807; within-day std 37.8 | var 1,777; within-day std 19.8 | var x0.63; within-day std x0.52 (tested) | var: CUSUM 3.41, adj. p = 0.0005 |
| Intraday | DK2 | 2022-06-11 | Variance | var 8,688; within-day std 39.8 | var 30,164; within-day std 75.8 | var x3.47; within-day std x1.90 (tested) | var: CUSUM 4.70, adj. p = 0.0005 |
| Intraday | DK2 | 2022-10-15 | Variance | var 30,164; within-day std 75.8 | var 17,007; within-day std 42.8 | var x0.56; within-day std x0.57 (tested) | var: CUSUM 3.60, adj. p = 0.0005 |
| Intraday | DK2 | 2022-12-25 | Variance | var 17,007; within-day std 42.8 | var 2,767; within-day std 27.1 | var x0.16; within-day std x0.63 (tested) | var: CUSUM 4.83, adj. p = 0.0005 |
| Intraday | DK2 | 2023-12-08 | Variance | var 2,767; within-day std 27.1 | var 1,221; within-day std 15.5 | var x0.44; within-day std x0.57 (tested) | var: CUSUM 2.77, adj. p = 0.0090 |
| Intraday | DK2 | 2024-04-07 | Variance | var 1,221; within-day std 15.5 | var 3,531; within-day std 31.3 | var x2.89; within-day std x2.02 (tested) | var: CUSUM 5.05, adj. p = 0.0005 |
| Balancing | DK1 | 2022-02-28 | Variance | var 5,019; within-day std 37.6 | var 12,912; within-day std 67.7 | var x2.57; within-day std x1.80 (tested) | var: CUSUM 3.15, adj. p = 0.0005 |
| Balancing | DK1 | 2022-06-16 | Variance | var 12,912; within-day std 67.7 | var 51,779; within-day std 117.2 | var x4.01; within-day std x1.73 (tested) | var: CUSUM 4.08, adj. p = 0.0005 |
| Balancing | DK1 | 2022-10-22 | Variance | var 51,779; within-day std 117.2 | var 14,672; within-day std 46.3 | var x0.28; within-day std x0.40 (tested) | var: CUSUM 4.58, adj. p = 0.0005 |
| Balancing | DK1 | 2022-12-25 | Mean | mean 214.5 | mean 81.2 | mean -133.3 (-62 %) | mean: CUSUM 3.93, adj. p = 0.0020 |
| Balancing | DK1 | 2023-10-03 | Variance | var 14,672; within-day std 46.3 | var 3,530; within-day std 25.6 | var x0.24; within-day std x0.55 (tested) | var: CUSUM 2.70, adj. p = 0.0050 |
| Balancing | DK1 | 2024-05-03 | Variance | var 3,530; within-day std 25.6 | var 7,397; within-day std 50.7 | var x2.10; within-day std x1.98 (tested) | var: CUSUM 4.72, adj. p = 0.0005 |
| Balancing | DK1 | 2025-02-22 | Variance | var 7,397; within-day std 50.7 | var 34,424; within-day std 106.0 | var x4.65; within-day std x2.09 (tested) | var: CUSUM 4.70, adj. p = 0.0005 |
| Balancing | DK1 | 2025-10-30 | Variance | var 34,424; within-day std 106.0 | var 9,550; within-day std 50.7 | var x0.28; within-day std x0.48 (tested) | var: CUSUM 3.26, adj. p = 0.0005 |
| Balancing | DK2 | 2022-02-28 | Variance | var 6,142; within-day std 44.6 | var 15,319; within-day std 68.7 | var x2.49; within-day std x1.54 (tested) | var: CUSUM 3.04, adj. p = 0.0010 |
| Balancing | DK2 | 2022-06-03 | Variance | var 15,319; within-day std 68.7 | var 42,931; within-day std 115.0 | var x2.80; within-day std x1.67 (tested) | var: CUSUM 3.94, adj. p = 0.0005 |
| Balancing | DK2 | 2022-10-16 | Variance | var 42,931; within-day std 115.0 | var 23,250; within-day std 62.3 | var x0.54; within-day std x0.54 (tested) | var: CUSUM 2.96, adj. p = 0.0020 |
| Balancing | DK2 | 2022-12-25 / 2022-12-20 (var) | Both | mean 209.6; var 23,250; within-day std 62.3 | mean 79.2; var 7,441; within-day std 43.2 | mean -130.4 (-62 %); var x0.32; within-day std x0.69 (tested) | mean: CUSUM 4.11, adj. p = 0.0015; var: CUSUM 4.68, adj. p = 0.0005 |
| Balancing | DK2 | 2023-10-03 | Variance | var 7,441; within-day std 43.2 | var 4,511; within-day std 27.4 | var x0.61; within-day std x0.64 (tested) | var: CUSUM 2.57, adj. p = 0.0095 |
| Balancing | DK2 | 2024-05-03 | Variance | var 4,511; within-day std 27.4 | var 8,151; within-day std 52.0 | var x1.81; within-day std x1.90 (tested) | var: CUSUM 4.61, adj. p = 0.0005 |
| Balancing | DK2 | 2025-01-09 | Variance | var 8,151; within-day std 52.0 | var 32,755; within-day std 104.2 | var x4.02; within-day std x2.00 (tested) | var: CUSUM 5.30, adj. p = 0.0005 |
| Balancing | DK2 | 2025-11-08 | Variance | var 32,755; within-day std 104.2 | var 9,175; within-day std 62.6 | var x0.28; within-day std x0.60 (tested) | var: CUSUM 2.94, adj. p = 0.0020 |

### Regime classification (statistical)

| Market | Zone | Price column | Mean | Variance | Distinct regimes | Range of regime means | Range of regime variances |
|---|---|---|---|---|---|---|---|
| Day-ahead | DK1 | da_price | relatively stable mean | significant variance shifts (7 breaks) | yes — 1 mean regime(s), 8 variance regime(s) | 114.4 to 114.4 | 744 to 24,639 |
| Day-ahead | DK2 | da_price | relatively stable mean | significant variance shifts (6 breaks) | yes — 1 mean regime(s), 7 variance regime(s) | 111.2 to 111.2 | 1,171 to 29,519 |
| Intraday | DK1 | id_vwap | relatively stable mean | significant variance shifts (6 breaks) | yes — 1 mean regime(s), 7 variance regime(s) | 112.0 to 112.0 | 1,777 to 26,149 |
| Intraday | DK2 | id_vwap | relatively stable mean | significant variance shifts (5 breaks) | yes — 1 mean regime(s), 6 variance regime(s) | 111.2 to 111.2 | 1,221 to 30,164 |
| Balancing | DK1 | b_imbalance_price | significant mean shifts (1 break) | significant variance shifts (7 breaks) | yes — 2 mean regime(s), 8 variance regime(s) | 81.2 to 214.5 | 3,530 to 51,779 |
| Balancing | DK2 | b_imbalance_price | significant mean shifts (1 break) | significant variance shifts (8 breaks) | yes — 2 mean regime(s), 9 variance regime(s) | 79.2 to 209.6 | 4,511 to 42,931 |

## 9. Not done yet
- Correlation-break and autocorrelation-break analysis (planned separately; only mean and variance breaks of the three market prices are done).
- Stationarity tests (ADF / KPSS) and any differencing decisions.
- Granger causality tests, VAR lag-order selection and VAR estimation.
- Final feature selection (the correlation and duplicate outputs are inputs to it, not the decision).
