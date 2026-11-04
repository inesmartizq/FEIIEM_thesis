# Lag selection

VARX(p, 0): p lags of the endogenous variables; exogenous variables and calendar dummies as listed in main.py. Every order p is fitted by least squares on the same T hours and scored by IC(p) = ln|S(p)| + (c_T / T) p K², with c_T = ln T (BIC), 2 ln ln T (HQ), 2 (AIC); lower = better.

**Rule:** the order with the lowest AIC. For T ≥ 16 the penalties are ordered, so always p(BIC) ≤ p(HQ) ≤ p(AIC). If the choice is the largest order searched, the search is repeated up to twice that order.

## Systems and regressors

| zone | systems | exogenous | dummies |
|---|---|---|---|
| DK1 | (c_wind_total_err, c_load_err, x_da_id_spread); (c_wind_total_err, c_load_err, x_id_bal_spread); (c_wind_total_err, c_load_err, x_da_bal_spread) | c_wind_total_actual_mw_change_1_lag_1, c_reservoir_deviation_pct_no, c_reservoir_deviation_pct_se, c_reservoir_deviation_pct_fi, da_flow_ger_net_export_mw, da_flow_nl_net_export_mw, da_flow_no2_net_export_mw, da_flow_se3_net_export_mw, da_flow_dk2_net_export_mw | fe_hour, fe_month_of_sample |
| DK2 | (c_wind_total_err, c_load_err, x_da_id_spread); (c_wind_total_err, c_load_err, x_id_bal_spread); (c_wind_total_err, c_load_err, x_da_bal_spread) | c_wind_total_actual_mw_change_1_lag_1, c_reservoir_deviation_pct_no, c_reservoir_deviation_pct_se, c_reservoir_deviation_pct_fi, da_flow_ger_net_export_mw, da_flow_se4_net_export_mw, da_flow_dk1_net_export_mw | fe_hour, fe_month_of_sample |

## Choices

| zone | system | T | orders searched | BIC | HQ | AIC | chosen (AIC) |
|---|---|---|---|---|---|---|---|
| DK1 | x_da_id_spread | 8200 | 1-48 | 2 | 3 | 25 | 25 |
| DK1 | x_id_bal_spread | 8200 | 1-48 | 2 | 3 | 25 | 25 |
| DK1 | x_da_bal_spread | 8200 | 1-48 | 2 | 3 | 25 | 25 |
| DK2 | x_da_id_spread | 8200 | 1-48 | 2 | 2 | 25 | 25 |
| DK2 | x_id_bal_spread | 8200 | 1-48 | 2 | 2 | 25 | 25 |
| DK2 | x_da_bal_spread | 8200 | 1-48 | 2 | 2 | 25 | 25 |

## Distance from each criterion's lowest value

0 = the criterion's own choice. The literature structure (lags 1-24, 48) is scored on the same hours for comparison.

| zone | system | lags | lowest value of | BIC − lowest | HQ − lowest | AIC − lowest |
|---|---|---|---|---|---|---|
| DK1 | x_da_id_spread | lags 1-2 | BIC | 0.0 | 0.0029 | 0.0473 |
| DK1 | x_da_id_spread | lags 1-3 | HQ | 0.0022 | 0.0 | 0.0417 |
| DK1 | x_da_id_spread | lags 1-25 | AIC (chosen) | 0.1297 | 0.0161 | 0.0 |
| DK1 | x_da_id_spread | lags 1-24, 48 | literature (comparison) | 0.1608 | 0.0472 | 0.0311 |
| DK1 | x_id_bal_spread | lags 1-2 | BIC | 0.0 | 0.0038 | 0.0333 |
| DK1 | x_id_bal_spread | lags 1-3 | HQ | 0.0012 | 0.0 | 0.0268 |
| DK1 | x_id_bal_spread | lags 1-25 | AIC (chosen) | 0.1437 | 0.0311 | 0.0 |
| DK1 | x_id_bal_spread | lags 1-24, 48 | literature (comparison) | 0.1706 | 0.0579 | 0.0268 |
| DK1 | x_da_bal_spread | lags 1-2 | BIC | 0.0 | 0.0041 | 0.0331 |
| DK1 | x_da_bal_spread | lags 1-3 | HQ | 0.001 | 0.0 | 0.0264 |
| DK1 | x_da_bal_spread | lags 1-25 | AIC (chosen) | 0.1439 | 0.0315 | 0.0 |
| DK1 | x_da_bal_spread | lags 1-24, 48 | literature (comparison) | 0.1706 | 0.0582 | 0.0267 |
| DK2 | x_da_id_spread | lags 1-2 | BIC, HQ | 0.0 | 0.0 | 0.0485 |
| DK2 | x_da_id_spread | lags 1-25 | AIC (chosen) | 0.1285 | 0.012 | 0.0 |
| DK2 | x_da_id_spread | lags 1-24, 48 | literature (comparison) | 0.1556 | 0.0391 | 0.0271 |
| DK2 | x_id_bal_spread | lags 1-2 | BIC, HQ | 0.0 | 0.0 | 0.0415 |
| DK2 | x_id_bal_spread | lags 1-25 | AIC (chosen) | 0.1355 | 0.019 | 0.0 |
| DK2 | x_id_bal_spread | lags 1-24, 48 | literature (comparison) | 0.1572 | 0.0407 | 0.0217 |
| DK2 | x_da_bal_spread | lags 1-2 | BIC, HQ | 0.0 | 0.0 | 0.0411 |
| DK2 | x_da_bal_spread | lags 1-25 | AIC (chosen) | 0.1359 | 0.0194 | 0.0 |
| DK2 | x_da_bal_spread | lags 1-24, 48 | literature (comparison) | 0.1576 | 0.0411 | 0.0217 |
