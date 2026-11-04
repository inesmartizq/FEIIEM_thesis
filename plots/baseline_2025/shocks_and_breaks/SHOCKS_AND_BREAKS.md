# Shocks and breaks

Period 2025-01-01 to 2025-12-31. The shocks of the forecast errors and how the spreads move around them; then the structural breaks of every column except the calendar dummies, per bidding zone.

## Shocks

**Rule.** Regimes are the periods between the variance breaks of the forecast error (below). Within each regime, z_t = (e_t − median) / (1.4826 · MAD), where MAD = median |e_t − median| and 1.4826 · MAD is the standard deviation of normal data. An hour is a shock hour when |z_t| > 3; consecutive shock hours of the same sign form one shock, which starts at its first hour. Over-forecast = error > 0 (e.g. less wind than planned).

| Zone | Forecast error | Sign | Shocks | Shock hours | Median hours | Largest |z| |
|---|---|---|---|---|---|---|
| DK1 | Wind forecast error | under-forecast (error < 0) | 29 | 55 | 2.0 | 3.7 |
| DK1 | Wind forecast error | over-forecast (error > 0) | 4 | 6 | 1.0 | 3.3 |
| DK2 | Wind forecast error | over-forecast (error > 0) | 49 | 196 | 3.0 | 6.9 |
| DK2 | Wind forecast error | under-forecast (error < 0) | 21 | 42 | 1.0 | 5.3 |
| DK1 | Demand forecast error | over-forecast (error > 0) | 80 | 168 | 1.0 | 6.5 |
| DK1 | Demand forecast error | under-forecast (error < 0) | 47 | 132 | 2.0 | 14.4 |
| DK2 | Demand forecast error | over-forecast (error > 0) | 72 | 152 | 2.0 | 9.0 |
| DK2 | Demand forecast error | under-forecast (error < 0) | 37 | 110 | 2.0 | 9.7 |

## How the spreads move around a shock

**Method.** The normal level of a spread is its mean at the same hour of the day over the hours without a shock of the error; d_t = spread_t − normal. D_h = mean over the shocks of d at onset + h (h = −6 … 24), with the 95 % interval D_h ± 1.96 · sd / √n (event_study.csv, event_study_<zone>.png). The effect during the shocks is the mean over the shocks of each shock's average d, with its 95 % interval. Expected: the sign the hypothesis gives (main.py, EXPECTED_SIGNS); an under-forecast flips it. Verdict: 'as expected' or 'opposite' when the interval excludes 0, else 'no clear effect'. Shocks can follow each other within a window, so the intervals are approximate.

| Zone | Forecast error | Shock | Spread | Shocks | Effect during the shocks | Expected | Verdict |
|---|---|---|---|---|---|---|---|
| DK1 | Wind forecast error | over-forecast (error > 0) | DA-ID spread | 4 | +0.41 [-9.38, +10.20] EUR/MWh | down | no clear effect |
| DK1 | Wind forecast error | under-forecast (error < 0) | DA-ID spread | 29 | -2.45 [-11.13, +6.23] EUR/MWh | up | no clear effect |
| DK1 | Wind forecast error | over-forecast (error > 0) | ID-BAL spread | 4 | +89.39 [-84.77, +263.55] EUR/MWh | down | no clear effect |
| DK1 | Wind forecast error | under-forecast (error < 0) | ID-BAL spread | 29 | +15.00 [-14.97, +44.98] EUR/MWh | up | no clear effect |
| DK1 | Wind forecast error | over-forecast (error > 0) | DA-BAL spread | 4 | +89.80 [-93.21, +272.81] EUR/MWh | down | no clear effect |
| DK1 | Wind forecast error | under-forecast (error < 0) | DA-BAL spread | 29 | +12.55 [-21.95, +47.05] EUR/MWh | up | no clear effect |
| DK2 | Wind forecast error | over-forecast (error > 0) | DA-ID spread | 49 | +1.59 [-1.53, +4.72] EUR/MWh | down | no clear effect |
| DK2 | Wind forecast error | under-forecast (error < 0) | DA-ID spread | 21 | +11.63 [+5.89, +17.37] EUR/MWh | up | as expected |
| DK2 | Wind forecast error | over-forecast (error > 0) | ID-BAL spread | 49 | -0.83 [-25.89, +24.23] EUR/MWh | down | no clear effect |
| DK2 | Wind forecast error | under-forecast (error < 0) | ID-BAL spread | 21 | +76.01 [+33.57, +118.45] EUR/MWh | up | as expected |
| DK2 | Wind forecast error | over-forecast (error > 0) | DA-BAL spread | 49 | +0.76 [-24.01, +25.53] EUR/MWh | down | no clear effect |
| DK2 | Wind forecast error | under-forecast (error < 0) | DA-BAL spread | 21 | +87.64 [+45.15, +130.13] EUR/MWh | up | as expected |
| DK1 | Demand forecast error | over-forecast (error > 0) | DA-ID spread | 80 | -2.34 [-7.67, +3.00] EUR/MWh | up | no clear effect |
| DK1 | Demand forecast error | under-forecast (error < 0) | DA-ID spread | 47 | -2.14 [-9.06, +4.78] EUR/MWh | down | no clear effect |
| DK1 | Demand forecast error | over-forecast (error > 0) | ID-BAL spread | 80 | +3.28 [-17.93, +24.49] EUR/MWh | up | no clear effect |
| DK1 | Demand forecast error | under-forecast (error < 0) | ID-BAL spread | 47 | +18.61 [+5.23, +31.99] EUR/MWh | down | opposite |
| DK1 | Demand forecast error | over-forecast (error > 0) | DA-BAL spread | 80 | +0.94 [-19.63, +21.52] EUR/MWh | up | no clear effect |
| DK1 | Demand forecast error | under-forecast (error < 0) | DA-BAL spread | 47 | +16.47 [+2.81, +30.13] EUR/MWh | down | opposite |
| DK2 | Demand forecast error | over-forecast (error > 0) | DA-ID spread | 72 | -1.75 [-5.90, +2.40] EUR/MWh | up | no clear effect |
| DK2 | Demand forecast error | under-forecast (error < 0) | DA-ID spread | 37 | -1.18 [-6.11, +3.76] EUR/MWh | down | no clear effect |
| DK2 | Demand forecast error | over-forecast (error > 0) | ID-BAL spread | 72 | +1.34 [-17.39, +20.07] EUR/MWh | up | no clear effect |
| DK2 | Demand forecast error | under-forecast (error < 0) | ID-BAL spread | 37 | -1.66 [-60.10, +56.79] EUR/MWh | down | no clear effect |
| DK2 | Demand forecast error | over-forecast (error > 0) | DA-BAL spread | 72 | -0.41 [-19.03, +18.21] EUR/MWh | up | no clear effect |
| DK2 | Demand forecast error | under-forecast (error < 0) | DA-BAL spread | 37 | -2.84 [-61.10, +55.43] EUR/MWh | down | no clear effect |

Verdicts: no clear effect 19, as expected 3, opposite 2.

## Structural breaks

**Method.** Daily series (Copenhagen local days). Mean breaks: CUSUM test on the daily mean. Variance breaks: the same test on the log of the within-day variance (days without variation left out). Both are standardised by a HAC long-run variance (Bartlett kernel, Andrews bandwidth) estimated around the candidate break, and capped at their 1st/99th percentiles for detection only. Multiple breaks by seeded binary segmentation (Kovács et al. 2023), which also catches changes that later reverse. Significance: a parametric AR(1) bootstrap of the largest statistic over all windows, with the series' own persistence (estimated from first differences, robust to level shifts); cut-off α = 0.01 on that adjusted p-value, at least 30 days between breaks. Before/after values are computed on the unmodified hourly values of the adjacent segments; a % change is shown only when the level is at least one standard deviation of the daily means. A mean and a variance break within 14 days of each other are reported as 'Both'.

### Detected breaks

| Column | Role | Zone | Unit | Date | Type | Before | After | Change | Evidence |
|---|---|---|---|---|---|---|---|---|---|
| x_da_id_spread | Endogenous | DK1 | EUR/MWh | 2025-07-04 | Variance | var 366.3; within-day std 10.56 | var 126.1; within-day std 7.737 | var x0.34; within-day std x0.73 | var: CUSUM 2.99, adj. p = 0.0005 |
| x_da_id_spread | Endogenous | DK1 | EUR/MWh | 2025-09-01 | Variance | var 126.1; within-day std 7.737 | var 718.9; within-day std 16.37 | var x5.70; within-day std x2.12 | var: CUSUM 2.51, adj. p = 0.0020 |
| x_da_id_spread | Endogenous | DK1 | EUR/MWh | 2025-10-08 | Variance | var 718.9; within-day std 16.37 | var 214.8; within-day std 7.449 | var x0.30; within-day std x0.45 | var: CUSUM 2.65, adj. p = 0.0015 |
| x_id_bal_spread | Endogenous | DK1 | EUR/MWh | 2025-03-06 | Variance | var 3917; within-day std 45.31 | var 3.247e+04; within-day std 99.96 | var x8.29; within-day std x2.21 | var: CUSUM 4.27, adj. p = 0.0005 |
| x_id_bal_spread | Endogenous | DK1 | EUR/MWh | 2025-10-31 | Variance | var 3.247e+04; within-day std 99.96 | var 8161; within-day std 45.49 | var x0.25; within-day std x0.46 | var: CUSUM 3.28, adj. p = 0.0005 |
| x_id_bal_spread | Endogenous | DK2 | EUR/MWh | 2025-03-06 | Variance | var 9285; within-day std 48.76 | var 3.442e+04; within-day std 110.2 | var x3.71; within-day std x2.26 | var: CUSUM 3.66, adj. p = 0.0005 |
| x_id_bal_spread | Endogenous | DK2 | EUR/MWh | 2025-11-08 | Variance | var 3.442e+04; within-day std 110.2 | var 6374; within-day std 56.51 | var x0.19; within-day std x0.51 | var: CUSUM 3.24, adj. p = 0.0005 |
| x_da_bal_spread | Endogenous | DK1 | EUR/MWh | 2025-03-06 | Variance | var 4555; within-day std 46.44 | var 3.294e+04; within-day std 100.9 | var x7.23; within-day std x2.17 | var: CUSUM 4.31, adj. p = 0.0005 |
| x_da_bal_spread | Endogenous | DK1 | EUR/MWh | 2025-10-31 | Variance | var 3.294e+04; within-day std 100.9 | var 8430; within-day std 47.23 | var x0.26; within-day std x0.47 | var: CUSUM 3.18, adj. p = 0.0005 |
| x_da_bal_spread | Endogenous | DK2 | EUR/MWh | 2025-03-09 | Variance | var 1.036e+04; within-day std 49.34 | var 3.509e+04; within-day std 111.8 | var x3.39; within-day std x2.27 | var: CUSUM 3.66, adj. p = 0.0005 |
| x_da_bal_spread | Endogenous | DK2 | EUR/MWh | 2025-11-08 | Variance | var 3.509e+04; within-day std 111.8 | var 6729; within-day std 58.47 | var x0.19; within-day std x0.52 | var: CUSUM 3.07, adj. p = 0.0010 |
| c_wind_total_err | Endogenous | DK1 | MW | 2025-09-17 | Mean | mean -218.8 | mean -448 | mean -229.1 | mean: CUSUM 3.60, adj. p = 0.0025 |
| c_wind_total_err | Endogenous | DK2 | MW | 2025-05-13 | Variance | var 2.11e+04; within-day std 84.87 | var 3.679e+04; within-day std 108.7 | var x1.74; within-day std x1.28 | var: CUSUM 2.86, adj. p = 0.0040 |
| c_wind_total_err | Endogenous | DK2 | MW | 2025-10-07 | Mean | mean 60.17 | mean -14.03 | mean -74.2 | mean: CUSUM 3.16, adj. p = 0.0035 |
| c_load_err | Endogenous | DK1 | MW | 2025-03-05 | Variance | var 6082; within-day std 63.39 | var 3.712e+04; within-day std 136.8 | var x6.10; within-day std x2.16 | var: CUSUM 4.79, adj. p = 0.0005 |
| c_load_err | Endogenous | DK1 | MW | 2025-10-03 | Mean | mean 8.512 | mean -57.02 | mean -65.54 | mean: CUSUM 3.67, adj. p = 0.0005 |
| c_load_err | Endogenous | DK2 | MW | 2025-03-05 | Variance | var 2938; within-day std 46.74 | var 9448; within-day std 73.56 | var x3.22; within-day std x1.57 | var: CUSUM 2.86, adj. p = 0.0040 |
| c_load_err | Endogenous | DK2 | MW | 2025-04-18 / 2025-04-19 (var) | Both | mean 2.514; var 9448; within-day std 73.56 | mean -37.22; var 1.547e+04; within-day std 99.76 | mean -39.73; var x1.64; within-day std x1.36 | mean: CUSUM 2.56, adj. p = 0.0045; var: CUSUM 4.01, adj. p = 0.0005 |
| c_load_err | Endogenous | DK2 | MW | 2025-10-20 | Variance | var 1.547e+04; within-day std 99.76 | var 5.559e+04; within-day std 180.2 | var x3.59; within-day std x1.81 | var: CUSUM 4.71, adj. p = 0.0005 |
| c_reservoir_deviation_pct_no | Exogenous | DK1 | percentage points | 2025-05-26 | Mean | mean 16.49 | mean 2.848 | mean -13.64 (-83 %) | mean: CUSUM 8.20, adj. p = 0.0035 |
| c_reservoir_deviation_pct_no | Exogenous | DK2 | percentage points | 2025-05-26 | Mean | mean 16.49 | mean 2.848 | mean -13.64 (-83 %) | mean: CUSUM 8.20, adj. p = 0.0035 |
| da_flow_ger_net_export_mw | Exogenous | DK1 | MWh/h | 2025-03-30 | Variance | var 1.031e+06; within-day std 440.5 | var 2.579e+06; within-day std 1161 | var x2.50; within-day std x2.64 | var: CUSUM 3.75, adj. p = 0.0005 |
| da_flow_ger_net_export_mw | Exogenous | DK1 | MWh/h | 2025-09-26 | Variance | var 2.579e+06; within-day std 1161 | var 1.735e+06; within-day std 308.1 | var x0.67; within-day std x0.27 | var: CUSUM 4.05, adj. p = 0.0005 |
| da_flow_ger_net_export_mw | Exogenous | DK2 | MWh/h | 2025-03-07 | Variance | var 1.421e+05; within-day std 120.9 | var 2.158e+05; within-day std 298.1 | var x1.52; within-day std x2.47 | var: CUSUM 2.96, adj. p = 0.0040 |
| da_flow_ger_net_export_mw | Exogenous | DK2 | MWh/h | 2025-04-26 | Mean | mean 479.3 | mean 241.8 | mean -237.6 (-50 %) | mean: CUSUM 3.26, adj. p = 0.0060 |
| da_flow_ger_net_export_mw | Exogenous | DK2 | MWh/h | 2025-08-05 | Variance | var 2.158e+05; within-day std 298.1 | var 3.118e+05; within-day std 274.5 | var x1.44; within-day std x0.92 | var: CUSUM 2.68, adj. p = 0.0080 |
| da_flow_no2_net_export_mw | Exogenous | DK1 | MWh/h | 2025-04-26 | Variance | var 5.431e+05; within-day std 283.6 | var 8.332e+05; within-day std 425.9 | var x1.53; within-day std x1.50 | var: CUSUM 2.97, adj. p = 0.0005 |
| da_flow_se3_net_export_mw | Exogenous | DK1 | MWh/h | 2025-06-26 | Variance | var 1.48e+05; within-day std 161.5 | var 1.429e+05; within-day std 119 | var x0.97; within-day std x0.74 | var: CUSUM 2.87, adj. p = 0.0005 |
| da_flow_se3_net_export_mw | Exogenous | DK1 | MWh/h | 2025-07-27 | Mean | mean -502.4 | mean -268.1 | mean +234.3 (+47 %) | mean: CUSUM 4.35, adj. p = 0.0005 |
| da_flow_se4_net_export_mw | Exogenous | DK2 | MWh/h | 2025-06-27 | Variance | var 2.182e+05; within-day std 157.2 | var 2.611e+05; within-day std 145.5 | var x1.20; within-day std x0.93 | var: CUSUM 3.18, adj. p = 0.0040 |
| da_flow_se4_net_export_mw | Exogenous | DK2 | MWh/h | 2025-08-26 | Mean | mean -964.6 | mean -434.5 | mean +530.1 (+55 %) | mean: CUSUM 4.44, adj. p = 0.0005 |
| da_flow_se4_net_export_mw | Exogenous | DK2 | MWh/h | 2025-11-05 | Mean | mean -434.5 | mean -1033 | mean -598.7 (-138 %) | mean: CUSUM 3.40, adj. p = 0.0015 |
| da_flow_dk1_net_export_mw | Exogenous | DK2 | MWh/h | 2025-08-26 | Mean | mean -22.65 | mean -142.7 | mean -120.1 | mean: CUSUM 3.05, adj. p = 0.0040 |
| da_flow_dk2_net_export_mw | Exogenous | DK1 | MWh/h | 2025-08-26 | Mean | mean 22.65 | mean 142.7 | mean +120.1 | mean: CUSUM 3.05, adj. p = 0.0040 |
| da_price | Input | DK1 | EUR/MWh | 2025-03-17 | Variance | var 2775; within-day std 25.81 | var 2560; within-day std 40.92 | var x0.92; within-day std x1.59 | var: CUSUM 3.47, adj. p = 0.0015 |
| da_price | Input | DK1 | EUR/MWh | 2025-07-05 | Variance | var 2560; within-day std 40.92 | var 2402; within-day std 34.01 | var x0.94; within-day std x0.83 | var: CUSUM 2.78, adj. p = 0.0050 |
| da_price | Input | DK1 | EUR/MWh | 2025-10-03 | Variance | var 2402; within-day std 34.01 | var 1930; within-day std 18.93 | var x0.80; within-day std x0.56 | var: CUSUM 3.76, adj. p = 0.0005 |
| da_price | Input | DK2 | EUR/MWh | 2025-07-05 | Variance | var 3060; within-day std 34.35 | var 2292; within-day std 35.56 | var x0.75; within-day std x1.04 | var: CUSUM 2.70, adj. p = 0.0100 |
| da_price | Input | DK2 | EUR/MWh | 2025-10-03 | Variance | var 2292; within-day std 35.56 | var 2279; within-day std 22.44 | var x0.99; within-day std x0.63 | var: CUSUM 3.22, adj. p = 0.0015 |
| id_vwap | Input | DK1 | EUR/MWh | 2025-03-16 | Variance | var 2650; within-day std 25.44 | var 2957; within-day std 40.74 | var x1.12; within-day std x1.60 | var: CUSUM 3.06, adj. p = 0.0015 |
| id_vwap | Input | DK1 | EUR/MWh | 2025-07-05 | Variance | var 2957; within-day std 40.74 | var 2573; within-day std 34.41 | var x0.87; within-day std x0.84 | var: CUSUM 2.82, adj. p = 0.0015 |
| id_vwap | Input | DK1 | EUR/MWh | 2025-10-04 | Variance | var 2573; within-day std 34.41 | var 1777; within-day std 19.78 | var x0.69; within-day std x0.57 | var: CUSUM 3.42, adj. p = 0.0005 |
| id_transaction_volume_mwh | Input | DK1 | MWh | 2025-05-21 | Variance | var 1.327e+06; within-day std 628.5 | var 1.528e+06; within-day std 762.8 | var x1.15; within-day std x1.21 | var: CUSUM 2.43, adj. p = 0.0025 |
| b_imbalance_price | Input | DK1 | EUR/MWh | 2025-03-10 | Variance | var 2.036e+04; within-day std 55.34 | var 3.2e+04; within-day std 107.8 | var x1.57; within-day std x1.95 | var: CUSUM 4.02, adj. p = 0.0005 |
| b_imbalance_price | Input | DK1 | EUR/MWh | 2025-10-31 | Variance | var 3.2e+04; within-day std 107.8 | var 9593; within-day std 50.33 | var x0.30; within-day std x0.47 | var: CUSUM 3.16, adj. p = 0.0005 |
| b_imbalance_price | Input | DK2 | EUR/MWh | 2025-03-13 | Variance | var 1.307e+04; within-day std 60.28 | var 3.749e+04; within-day std 116.6 | var x2.87; within-day std x1.93 | var: CUSUM 3.69, adj. p = 0.0005 |
| b_imbalance_price | Input | DK2 | EUR/MWh | 2025-11-08 | Variance | var 3.749e+04; within-day std 116.6 | var 9175; within-day std 62.6 | var x0.24; within-day std x0.54 | var: CUSUM 2.90, adj. p = 0.0010 |
| c_wind_onshore_forecast_mw | Input | DK2 | MW | 2025-05-13 | Variance | var 1.809e+04; within-day std 35.96 | var 1.223e+04; within-day std 54.79 | var x0.68; within-day std x1.52 | var: CUSUM 2.41, adj. p = 0.0080 |
| c_wind_onshore_forecast_mw | Input | DK2 | MW | 2025-07-07 | Variance | var 1.223e+04; within-day std 54.79 | var 1.392e+04; within-day std 38.88 | var x1.14; within-day std x0.71 | var: CUSUM 2.39, adj. p = 0.0085 |
| c_wind_offshore_actual_mw | Input | DK1 | MW | 2025-09-11 | Mean | mean 582.1 | mean 868.7 | mean +286.6 (+49 %) | mean: CUSUM 3.67, adj. p = 0.0020 |
| c_load_forecast_mw | Input | DK1 | MW | 2025-10-24 | Variance | var 1.761e+05; within-day std 270 | var 9.901e+04; within-day std 206.4 | var x0.56; within-day std x0.76 | var: CUSUM 3.81, adj. p = 0.0005 |
| c_load_forecast_mw | Input | DK2 | MW | 2025-03-06 | Variance | var 5.584e+04; within-day std 209.3 | var 6.848e+04; within-day std 186.9 | var x1.23; within-day std x0.89 | var: CUSUM 3.09, adj. p = 0.0005 |
| c_load_forecast_mw | Input | DK2 | MW | 2025-04-12 | Mean | mean 1850 | mean 1529 | mean -321.3 (-17 %) | mean: CUSUM 5.47, adj. p = 0.0005 |
| c_load_forecast_mw | Input | DK2 | MW | 2025-11-10 | Mean | mean 1529 | mean 1850 | mean +321.3 (+21 %) | mean: CUSUM 4.74, adj. p = 0.0005 |
| c_load_actual_mw | Input | DK1 | MW | 2025-04-01 | Variance | var 1.365e+05; within-day std 260.5 | var 1.564e+05; within-day std 313.5 | var x1.15; within-day std x1.20 | var: CUSUM 2.87, adj. p = 0.0095 |
| c_load_actual_mw | Input | DK1 | MW | 2025-09-27 | Variance | var 1.564e+05; within-day std 313.5 | var 1.372e+05; within-day std 263.7 | var x0.88; within-day std x0.84 | var: CUSUM 3.30, adj. p = 0.0015 |
| c_load_actual_mw | Input | DK2 | MW | 2025-04-28 | Variance | var 7.262e+04; within-day std 207.1 | var 6.224e+04; within-day std 236.3 | var x0.86; within-day std x1.14 | var: CUSUM 3.12, adj. p = 0.0045 |
| c_load_actual_mw | Input | DK2 | MW | 2025-09-25 | Variance | var 6.224e+04; within-day std 236.3 | var 6.886e+04; within-day std 215.5 | var x1.11; within-day std x0.91 | var: CUSUM 2.88, adj. p = 0.0075 |
| c_reservoir_fill_pct_se | Input | DK1 | % of capacity | 2025-06-09 | Mean | mean 59.46 | mean 79.56 | mean +20.1 (+34 %) | mean: CUSUM 7.76, adj. p = 0.0080 |
| c_reservoir_fill_pct_se | Input | DK2 | % of capacity | 2025-06-09 | Mean | mean 59.46 | mean 79.56 | mean +20.1 (+34 %) | mean: CUSUM 7.76, adj. p = 0.0080 |
| da_flow_ger_export_mw | Input | DK1 | MW | 2025-03-03 | Variance | var 6.463e+05; within-day std 351.6 | var 9.688e+05; within-day std 756.9 | var x1.50; within-day std x2.15 | var: CUSUM 3.08, adj. p = 0.0005 |
| da_flow_ger_export_mw | Input | DK1 | MW | 2025-09-24 | Variance | var 9.688e+05; within-day std 756.9 | var 7.845e+05; within-day std 265.1 | var x0.81; within-day std x0.35 | var: CUSUM 4.39, adj. p = 0.0005 |
| da_flow_ger_export_mw | Input | DK2 | MW | 2025-03-05 | Variance | var 7.34e+04; within-day std 102.9 | var 1.129e+05; within-day std 242.9 | var x1.54; within-day std x2.36 | var: CUSUM 2.54, adj. p = 0.0070 |
| da_flow_ger_export_mw | Input | DK2 | MW | 2025-05-04 | Both | mean 533; var 1.129e+05; within-day std 242.9 | mean 371.2; var 9e+04; within-day std 177.8 | mean -161.9 (-30 %); var x0.80; within-day std x0.73 | mean: CUSUM 3.96, adj. p = 0.0010; var: CUSUM 2.53, adj. p = 0.0070 |
| da_flow_no2_import_mw | Input | DK1 | MW | 2025-03-23 | Variance | var 3.178e+05; within-day std 208.9 | var 4.316e+05; within-day std 334.9 | var x1.36; within-day std x1.60 | var: CUSUM 2.45, adj. p = 0.0025 |
| da_flow_no2_import_mw | Input | DK1 | MW | 2025-04-26 | Mean | mean 1233 | mean 896.2 | mean -336.4 (-27 %) | mean: CUSUM 3.55, adj. p = 0.0035 |
| da_flow_se3_import_mw | Input | DK1 | MW | 2025-04-01 | Variance | var 5.93e+04; within-day std 81.38 | var 8.005e+04; within-day std 209.1 | var x1.35; within-day std x2.57 | var: CUSUM 2.46, adj. p = 0.0045 |
| da_flow_se3_import_mw | Input | DK1 | MW | 2025-06-26 | Variance | var 8.005e+04; within-day std 209.1 | var 8.931e+04; within-day std 85.46 | var x1.12; within-day std x0.41 | var: CUSUM 3.25, adj. p = 0.0005 |
| da_flow_se3_import_mw | Input | DK1 | MW | 2025-07-25 | Mean | mean 548 | mean 170.7 | mean -377.3 (-69 %) | mean: CUSUM 5.09, adj. p = 0.0005 |
| da_flow_se3_import_mw | Input | DK1 | MW | 2025-10-17 | Mean | mean 170.7 | mean 490.6 | mean +319.9 | mean: CUSUM 2.85, adj. p = 0.0090 |
| da_flow_se4_import_mw | Input | DK2 | MW | 2025-06-27 | Variance | var 1.625e+05; within-day std 149 | var 1.733e+05; within-day std 129.2 | var x1.07; within-day std x0.87 | var: CUSUM 3.12, adj. p = 0.0040 |
| da_flow_se4_import_mw | Input | DK2 | MW | 2025-08-26 | Mean | mean 985.3 | mean 526.2 | mean -459.1 (-47 %) | mean: CUSUM 5.56, adj. p = 0.0005 |
| da_flow_se4_import_mw | Input | DK2 | MW | 2025-11-09 | Mean | mean 526.2 | mean 1077 | mean +550.3 (+105 %) | mean: CUSUM 3.47, adj. p = 0.0015 |
| da_flow_dk1_export_mw | Input | DK2 | MW | 2025-05-13 | Variance | var 2.98e+04; within-day std 93.45 | var 3.155e+04; within-day std 104 | var x1.06; within-day std x1.11 | var: CUSUM 2.46, adj. p = 0.0020 |
| da_flow_dk1_import_mw | Input | DK2 | MW | 2025-08-26 | Mean | mean 141 | mean 249.4 | mean +108.4 (+77 %) | mean: CUSUM 3.55, adj. p = 0.0010 |
| da_flow_dk2_export_mw | Input | DK1 | MW | 2025-08-26 | Mean | mean 141 | mean 249.4 | mean +108.4 (+77 %) | mean: CUSUM 3.55, adj. p = 0.0010 |
| da_flow_dk2_import_mw | Input | DK1 | MW | 2025-05-13 | Variance | var 2.98e+04; within-day std 93.45 | var 3.155e+04; within-day std 104 | var x1.06; within-day std x1.11 | var: CUSUM 2.46, adj. p = 0.0020 |

### Regime classification (statistical)

| Column | Role | Zone | Mean | Variance | Range of regime means | Range of regime variances |
|---|---|---|---|---|---|---|
| x_da_id_spread | Endogenous | DK1 | stable | 3 breaks | 1.458 to 1.458 | 126.1 to 718.9 |
| x_da_id_spread | Endogenous | DK2 | stable | stable | -0.7538 to -0.7538 | 441.8 to 441.8 |
| x_id_bal_spread | Endogenous | DK1 | stable | 2 breaks | -4.916 to -4.916 | 3917 to 3.247e+04 |
| x_id_bal_spread | Endogenous | DK2 | stable | 2 breaks | 0.6017 to 0.6017 | 6374 to 3.442e+04 |
| x_da_bal_spread | Endogenous | DK1 | stable | 2 breaks | -3.458 to -3.458 | 4555 to 3.294e+04 |
| x_da_bal_spread | Endogenous | DK2 | stable | 2 breaks | -0.1521 to -0.1521 | 6729 to 3.509e+04 |
| c_wind_total_err | Endogenous | DK1 | 1 break | stable | -448 to -218.8 | 2.354e+05 to 2.354e+05 |
| c_wind_total_err | Endogenous | DK2 | 1 break | 1 break | -14.03 to 60.17 | 2.11e+04 to 3.679e+04 |
| c_load_err | Endogenous | DK1 | 1 break | 1 break | -57.02 to 8.512 | 6082 to 3.712e+04 |
| c_load_err | Endogenous | DK2 | 1 break | 3 breaks | -37.22 to 2.514 | 2938 to 5.559e+04 |
| c_wind_total_actual_mw_change_1_lag_1 | Exogenous | DK1 | stable | stable | -0.1415 to -0.1415 | 4.022e+04 to 4.022e+04 |
| c_wind_total_actual_mw_change_1_lag_1 | Exogenous | DK2 | stable | stable | -0.09445 to -0.09445 | 8088 to 8088 |
| c_reservoir_deviation_pct_no | Exogenous | DK1 | 1 break | not tested (no within-day variation) | 2.848 to 16.49 |  |
| c_reservoir_deviation_pct_no | Exogenous | DK2 | 1 break | not tested (no within-day variation) | 2.848 to 16.49 |  |
| c_reservoir_deviation_pct_se | Exogenous | DK1 | stable | not tested (no within-day variation) | 13.16 to 13.16 |  |
| c_reservoir_deviation_pct_se | Exogenous | DK2 | stable | not tested (no within-day variation) | 13.16 to 13.16 |  |
| c_reservoir_deviation_pct_fi | Exogenous | DK1 | stable | not tested (no within-day variation) | -3.181 to -3.181 |  |
| c_reservoir_deviation_pct_fi | Exogenous | DK2 | stable | not tested (no within-day variation) | -3.181 to -3.181 |  |
| da_flow_ger_net_export_mw | Exogenous | DK1 | stable | 2 breaks | 1349 to 1349 | 1.031e+06 to 2.579e+06 |
| da_flow_ger_net_export_mw | Exogenous | DK2 | 1 break | 2 breaks | 241.8 to 479.3 | 1.421e+05 to 3.118e+05 |
| da_flow_nl_net_export_mw | Exogenous | DK1 | stable | stable | -71.36 to -71.36 | 3.13e+05 to 3.13e+05 |
| da_flow_no2_net_export_mw | Exogenous | DK1 | stable | 1 break | -882.4 to -882.4 | 5.431e+05 to 8.332e+05 |
| da_flow_se3_net_export_mw | Exogenous | DK1 | 1 break | 1 break | -502.4 to -268.1 | 1.429e+05 to 1.48e+05 |
| da_flow_se4_net_export_mw | Exogenous | DK2 | 2 breaks | 1 break | -1033 to -434.5 | 2.182e+05 to 2.611e+05 |
| da_flow_dk1_net_export_mw | Exogenous | DK2 | 1 break | stable | -142.7 to -22.65 | 1.121e+05 to 1.121e+05 |
| da_flow_dk2_net_export_mw | Exogenous | DK1 | 1 break | stable | 22.65 to 142.7 | 1.121e+05 to 1.121e+05 |
| da_price | Input | DK1 | stable | 3 breaks | 81.11 to 81.11 | 1930 to 2775 |
| da_price | Input | DK2 | stable | 2 breaks | 82.5 to 82.5 | 2279 to 3060 |
| id_vwap | Input | DK1 | stable | 3 breaks | 79.65 to 79.65 | 1777 to 2957 |
| id_vwap | Input | DK2 | stable | stable | 83.26 to 83.26 | 2912 to 2912 |
| id_transaction_volume_mwh | Input | DK1 | stable | 1 break | 2083 to 2083 | 1.327e+06 to 1.528e+06 |
| id_transaction_volume_mwh | Input | DK2 | stable | stable | 562.7 to 562.7 | 8.802e+04 to 8.802e+04 |
| b_imbalance_price | Input | DK1 | stable | 2 breaks | 84.57 to 84.57 | 9593 to 3.2e+04 |
| b_imbalance_price | Input | DK2 | stable | 2 breaks | 82.65 to 82.65 | 9175 to 3.749e+04 |
| c_wind_total_forecast_mw | Input | DK1 | stable | stable | 1398 to 1398 | 7.371e+05 to 7.371e+05 |
| c_wind_total_forecast_mw | Input | DK2 | stable | stable | 577.2 to 577.2 | 1.365e+05 to 1.365e+05 |
| c_wind_onshore_forecast_mw | Input | DK1 | stable | stable | 834.1 to 834.1 | 3.747e+05 to 3.747e+05 |
| c_wind_onshore_forecast_mw | Input | DK2 | stable | 2 breaks | 152.3 to 152.3 | 1.223e+04 to 1.809e+04 |
| c_wind_offshore_forecast_mw | Input | DK1 | stable | stable | 562.4 to 562.4 | 7.489e+04 to 7.489e+04 |
| c_wind_offshore_forecast_mw | Input | DK2 | stable | stable | 424 to 424 | 6.455e+04 to 6.455e+04 |
| c_wind_total_actual_mw | Input | DK1 | stable | stable | 1669 to 1669 | 1.46e+06 to 1.46e+06 |
| c_wind_total_actual_mw | Input | DK2 | stable | stable | 530.1 to 530.1 | 1.841e+05 to 1.841e+05 |
| c_wind_onshore_actual_mw | Input | DK1 | stable | stable | 998.4 to 998.4 | 6.429e+05 to 6.429e+05 |
| c_wind_onshore_actual_mw | Input | DK2 | stable | stable | 160 to 160 | 1.81e+04 to 1.81e+04 |
| c_wind_offshore_actual_mw | Input | DK1 | 1 break | stable | 582.1 to 868.7 | 2.337e+05 to 2.337e+05 |
| c_wind_offshore_actual_mw | Input | DK2 | stable | stable | 370 to 370 | 9.688e+04 to 9.688e+04 |
| c_load_forecast_mw | Input | DK1 | stable | 1 break | 2695 to 2695 | 9.901e+04 to 1.761e+05 |
| c_load_forecast_mw | Input | DK2 | 2 breaks | 1 break | 1529 to 1850 | 5.584e+04 to 6.848e+04 |
| c_load_actual_mw | Input | DK1 | stable | 2 breaks | 2702 to 2702 | 1.365e+05 to 1.564e+05 |
| c_load_actual_mw | Input | DK2 | stable | 2 breaks | 1689 to 1689 | 6.224e+04 to 7.262e+04 |
| c_wind_total_actual_mw_change_1 | Input | DK1 | stable | stable | -0.07269 to -0.07269 | 4.026e+04 to 4.026e+04 |
| c_wind_total_actual_mw_change_1 | Input | DK2 | stable | stable | -0.06452 to -0.06452 | 8095 to 8095 |
| c_reservoir_fill_pct_no | Input | DK1 | stable | not tested (no within-day variation) | 67.04 to 67.04 |  |
| c_reservoir_fill_pct_no | Input | DK2 | stable | not tested (no within-day variation) | 67.04 to 67.04 |  |
| c_reservoir_fill_median_pct_no | Input | DK1 | stable | not tested (no within-day variation) | 58.78 to 58.78 |  |
| c_reservoir_fill_median_pct_no | Input | DK2 | stable | not tested (no within-day variation) | 58.78 to 58.78 |  |
| c_reservoir_fill_pct_se | Input | DK1 | 1 break | not tested (no within-day variation) | 59.46 to 79.56 |  |
| c_reservoir_fill_pct_se | Input | DK2 | 1 break | not tested (no within-day variation) | 59.46 to 79.56 |  |
| c_reservoir_fill_median_pct_se | Input | DK1 | stable | not tested (no within-day variation) | 57.65 to 57.65 |  |
| c_reservoir_fill_median_pct_se | Input | DK2 | stable | not tested (no within-day variation) | 57.65 to 57.65 |  |
| c_reservoir_fill_pct_fi | Input | DK1 | stable | not tested (no within-day variation) | 56.03 to 56.03 |  |
| c_reservoir_fill_pct_fi | Input | DK2 | stable | not tested (no within-day variation) | 56.03 to 56.03 |  |
| c_reservoir_fill_median_pct_fi | Input | DK1 | stable | not tested (no within-day variation) | 59.22 to 59.22 |  |
| c_reservoir_fill_median_pct_fi | Input | DK2 | stable | not tested (no within-day variation) | 59.22 to 59.22 |  |
| da_flow_ger_export_mw | Input | DK1 | stable | 2 breaks | 1599 to 1599 | 6.463e+05 to 9.688e+05 |
| da_flow_ger_export_mw | Input | DK2 | 1 break | 2 breaks | 371.2 to 533 | 7.34e+04 to 1.129e+05 |
| da_flow_ger_import_mw | Input | DK1 | stable | stable | 250.4 to 250.4 | 4.39e+05 to 4.39e+05 |
| da_flow_ger_import_mw | Input | DK2 | stable | stable | 109.1 to 109.1 | 6.228e+04 to 6.228e+04 |
| da_flow_nl_export_mw | Input | DK1 | stable | stable | 217.8 to 217.8 | 8.809e+04 to 8.809e+04 |
| da_flow_nl_import_mw | Input | DK1 | stable | stable | 289.2 to 289.2 | 9.927e+04 to 9.927e+04 |
| da_flow_no2_export_mw | Input | DK1 | stable | stable | 119.7 to 119.7 | 1.153e+05 to 1.153e+05 |
| da_flow_no2_import_mw | Input | DK1 | 1 break | 1 break | 896.2 to 1233 | 3.178e+05 to 4.316e+05 |
| da_flow_se3_export_mw | Input | DK1 | stable | stable | 48.32 to 48.32 | 2.091e+04 to 2.091e+04 |
| da_flow_se3_import_mw | Input | DK1 | 2 breaks | 2 breaks | 170.7 to 548 | 5.93e+04 to 8.931e+04 |
| da_flow_se4_export_mw | Input | DK2 | stable | stable | 32.03 to 32.03 | 1.644e+04 to 1.644e+04 |
| da_flow_se4_import_mw | Input | DK2 | 2 breaks | 1 break | 526.2 to 1077 | 1.625e+05 to 1.733e+05 |
| da_flow_dk1_export_mw | Input | DK2 | stable | 1 break | 114.3 to 114.3 | 2.98e+04 to 3.155e+04 |
| da_flow_dk1_import_mw | Input | DK2 | 1 break | stable | 141 to 249.4 | 4.042e+04 to 4.042e+04 |
| da_flow_dk2_export_mw | Input | DK1 | 1 break | stable | 141 to 249.4 | 4.042e+04 to 4.042e+04 |
| da_flow_dk2_import_mw | Input | DK1 | stable | 1 break | 114.3 to 114.3 | 2.98e+04 to 3.155e+04 |

### Reading this
- Statistical detection only: a break means the level or volatility differs between segments, not why.
- With a single year of data, breaks can reflect seasonality (e.g. solar-driven midday prices in spring/summer, the hydro cycle) as much as structural change.
- Candidate explanations to check before interpreting a break (not tested here): seasonal fuel and weather patterns; the Nordic mFRR energy-activation market go-live (March 2025); the day-ahead 15-minute MTU go-live (1 Oct 2025).
