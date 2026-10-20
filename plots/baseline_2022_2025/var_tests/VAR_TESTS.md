# VAR tests — `baseline_2022_2025`

One VAR per (zone, spread); y = (c_wind_total_err, c_load_err, spread); exogenous per zone: DK1: c_wind_total_actual_mw_change_1, da_flow_ger_net_export_mw, da_flow_nl_net_export_mw, da_flow_no2_net_export_mw, da_flow_se3_net_export_mw, da_flow_dk2_net_export_mw; DK2: c_wind_total_actual_mw_change_1, da_flow_ger_net_export_mw, da_flow_se4_net_export_mw, da_flow_dk1_net_export_mw + dummies for fe_hour, fe_month_of_sample. Significance level 0.05.

## 1. Stationarity (ADF: H0 unit root; KPSS: H0 stationary; PP: H0 unit root, supporting)
STATIONARY: ADF rejects, KPSS does not. UNIT ROOT: the reverse. CONFLICT: both reject. INCONCLUSIVE: neither rejects. Nothing is differenced: the VAR below uses levels. KPSS p = exact asymptotic p-value (not truncated).

| zone | series | n | n_dropped | adf_stat | adf_p | adf_lags | adf_max_lag | kpss_stat | kpss_p | pp_p | decision |
|---|---|---|---|---|---|---|---|---|---|---|---|
| DK1 | c_wind_total_err | 34749 | 315 | -8.989 | < 0.0001 | 168 | 168 | 7.897 | 1.51e-18 | < 0.0001 | CONFLICT |
| DK1 | c_load_err | 35054 | 10 | -10.129 | < 0.0001 | 168 | 168 | 1.025 | 0.0021 | < 0.0001 | CONFLICT |
| DK1 | x_da_id_spread | 35064 | 0 | -29.465 | < 0.0001 | 25 | 48 | 1.977 | 1.44e-05 | < 0.0001 | CONFLICT |
| DK1 | x_da_bal_spread | 35064 | 0 | -26.185 | < 0.0001 | 46 | 48 | 1.614 | 9.50e-05 | < 0.0001 | CONFLICT |
| DK1 | x_id_bal_spread | 35064 | 0 | -26.607 | < 0.0001 | 46 | 48 | 0.575 | 0.0258 | < 0.0001 | CONFLICT |
| DK2 | c_wind_total_err | 34749 | 315 | -11.529 | < 0.0001 | 46 | 48 | 16.737 | 1.18e-37 | < 0.0001 | CONFLICT |
| DK2 | c_load_err | 35054 | 10 | -5.729 | < 0.0001 | 168 | 168 | 9.262 | 1.65e-21 | < 0.0001 | CONFLICT |
| DK2 | x_da_id_spread | 35064 | 0 | -30.635 | < 0.0001 | 25 | 48 | 1.031 | 0.0021 | < 0.0001 | CONFLICT |
| DK2 | x_da_bal_spread | 35064 | 0 | -29.368 | < 0.0001 | 37 | 48 | 0.26 | 0.1759 | < 0.0001 | STATIONARY |
| DK2 | x_id_bal_spread | 35064 | 0 | -28.977 | < 0.0001 | 37 | 48 | 0.059 | 0.8214 | < 0.0001 | STATIONARY |

**Review needed: c_wind_total_err (DK1): CONFLICT; c_load_err (DK1): CONFLICT; x_da_id_spread (DK1): CONFLICT; x_da_bal_spread (DK1): CONFLICT; x_id_bal_spread (DK1): CONFLICT; c_wind_total_err (DK2): CONFLICT; c_load_err (DK2): CONFLICT; x_da_id_spread (DK2): CONFLICT**

Calendar controls for the VARX: hour + month of sample (the coarsest set after which every series is stationary; hour + month of sample: 10 of 10 stationary; hour + week of sample: 10 of 10 stationary).

ADF bound check for the series at the 168-lag limit, rerun with max 336: c_wind_total_err DK1 lag 313, stat -5.04; c_load_err DK1 lag 336, stat -5.25; c_load_err DK2 lag 336, stat -3.49 — same ADF verdict.

Robustness (S stationary, U unit root, C conflict, I inconclusive):

| zone | series | Baseline | 2025 | 2024-25 | 2023-25 | KPSS bw 48 | KPSS bw 168 | Hour + month of sample removed | alpha 1% | alpha 10% |
|---|---|---|---|---|---|---|---|---|---|---|
| DK1 | c_wind_total_err | C | C | C | C | C | C | S | C | C |
| DK1 | c_load_err | C | C | C | C | C | C | S | C | C |
| DK1 | x_da_id_spread | C | S | S | S | C | C | S | C | C |
| DK1 | x_da_bal_spread | C | S | S | S | C | C | S | C | C |
| DK1 | x_id_bal_spread | C | S | S | S | C | C | S | S | C |
| DK2 | c_wind_total_err | C | C | C | C | C | C | S | C | C |
| DK2 | c_load_err | C | C | C | C | C | C | S | C | C |
| DK2 | x_da_id_spread | C | S | S | S | C | C | S | C | C |
| DK2 | x_da_bal_spread | S | S | S | S | S | S | S | S | S |
| DK2 | x_id_bal_spread | S | S | S | S | S | S | S | S | S |

## 2. Lag selection (same sample for every structure; lower = better)

| zone | spread | 1..1 | 1..2 | 1..3 | 1..4 | 1..6 | 1..12 | 1..24 | 1..48 | 1-24 + 48 |
|---|---|---|---|---|---|---|---|---|---|---|
| DK1 | x_da_id_spread | 22.6778 | 22.6631 | 22.6515 | 22.6523 | 22.6501 | 22.6413 | 22.6389 | 22.6634 | 22.6398 |
| DK1 | x_da_bal_spread | 26.7246 | 26.7083 | 26.6958 | 26.6966 | 26.6936 | 26.6858 | 26.6867 | 26.7119 | 26.6877 |
| DK1 | x_id_bal_spread | 26.696 | 26.679 | 26.667 | 26.6679 | 26.6653 | 26.6577 | 26.6585 | 26.6839 | 26.6596 |
| DK2 | x_da_id_spread | 20.7172 | 20.7081 | 20.706 | 20.7073 | 20.7054 | 20.7 | 20.667 | 20.6958 | 20.668 |
| DK2 | x_da_bal_spread | 24.4408 | 24.4304 | 24.428 | 24.4293 | 24.4274 | 24.4229 | 24.3911 | 24.4201 | 24.3922 |
| DK2 | x_id_bal_spread | 24.414 | 24.4031 | 24.4008 | 24.4023 | 24.4006 | 24.3962 | 24.3644 | 24.3934 | 24.3655 |

BIC-preferred contiguous order (used for the 'short' model): DK1 x_da_id_spread: 1..24; DK1 x_da_bal_spread: 1..12; DK1 x_id_bal_spread: 1..12; DK2 x_da_id_spread: 1..24; DK2 x_da_bal_spread: 1..24; DK2 x_id_bal_spread: 1..24

## 3. Estimated models: stability and residual autocorrelation

| zone | spread | version | T | max_eigen_modulus | stable | portmanteau_h | portmanteau_Q | portmanteau_df | portmanteau_p | residuals_white_noise |
|---|---|---|---|---|---|---|---|---|---|---|
| DK1 | x_da_id_spread | full | 34206 | 0.99391 | True | 72 | 8963.4 | 423 | < 0.0001 | False |
| DK1 | x_da_id_spread | short | 34429 | 0.99196 | True | 48 | 8007.0 | 216 | < 0.0001 | False |
| DK1 | x_da_bal_spread | full | 34206 | 0.9935 | True | 72 | 8926.6 | 423 | < 0.0001 | False |
| DK1 | x_da_bal_spread | short | 34585 | 0.98068 | True | 36 | 8382.1 | 216 | < 0.0001 | False |
| DK1 | x_id_bal_spread | full | 34206 | 0.9934 | True | 72 | 8911.5 | 423 | < 0.0001 | False |
| DK1 | x_id_bal_spread | short | 34585 | 0.98067 | True | 36 | 8376.3 | 216 | < 0.0001 | False |
| DK2 | x_da_id_spread | full | 34206 | 0.98711 | True | 72 | 14241.7 | 423 | < 0.0001 | False |
| DK2 | x_da_id_spread | short | 34429 | 0.98607 | True | 48 | 13663.6 | 216 | < 0.0001 | False |
| DK2 | x_da_bal_spread | full | 34206 | 0.98712 | True | 72 | 14139.3 | 423 | < 0.0001 | False |
| DK2 | x_da_bal_spread | short | 34429 | 0.98589 | True | 48 | 13601.1 | 216 | < 0.0001 | False |
| DK2 | x_id_bal_spread | full | 34206 | 0.98716 | True | 72 | 14149.4 | 423 | < 0.0001 | False |
| DK2 | x_id_bal_spread | short | 34429 | 0.98595 | True | 48 | 13601.5 | 216 | < 0.0001 | False |
