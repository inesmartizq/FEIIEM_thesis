# Stationarity tests and lag selection — `baseline_2025`

No VAR / VARX is estimated here: only the stationarity tests and the lag selection for a later model.

Lag selection: one system per (zone, spread); y = (c_wind_total_err, c_load_err, spread); exogenous per zone: DK1: c_wind_total_actual_mw_change_1, da_flow_ger_net_export_mw, da_flow_nl_net_export_mw, da_flow_no2_net_export_mw, da_flow_se3_net_export_mw, da_flow_dk2_net_export_mw; DK2: c_wind_total_actual_mw_change_1, da_flow_ger_net_export_mw, da_flow_se4_net_export_mw, da_flow_dk1_net_export_mw + dummies for fe_hour, fe_month_of_sample. Significance level 0.05.

## 1. Stationarity (ADF: H0 unit root; KPSS: H0 stationary; PP: H0 unit root, supporting)
STATIONARY: ADF rejects, KPSS does not. UNIT ROOT: the reverse. CONFLICT: both reject. INCONCLUSIVE: neither rejects. Nothing is differenced: the series stay in levels. KPSS p = exact asymptotic p-value (not truncated).

| zone | series | n | n_dropped | adf_stat | adf_p | adf_lags | adf_max_lag | kpss_stat | kpss_p | pp_p | decision |
|---|---|---|---|---|---|---|---|---|---|---|---|
| DK1 | c_wind_total_err | 8637 | 123 | -6.957 | < 0.0001 | 146 | 168 | 1.117 | 0.0013 | < 0.0001 | CONFLICT |
| DK1 | c_load_err | 8750 | 10 | -5.162 | < 0.0001 | 168 | 168 | 1.527 | 0.0002 | < 0.0001 | CONFLICT |
| DK1 | x_da_id_spread | 8760 | 0 | -14.383 | < 0.0001 | 36 | 48 | 0.231 | 0.2148 | < 0.0001 | STATIONARY |
| DK1 | x_da_bal_spread | 8760 | 0 | -38.87 | < 0.0001 | 4 | 48 | 0.06 | 0.8158 | < 0.0001 | STATIONARY |
| DK1 | x_id_bal_spread | 8760 | 0 | -39.651 | < 0.0001 | 4 | 48 | 0.122 | 0.4893 | < 0.0001 | STATIONARY |
| DK2 | c_wind_total_err | 8637 | 123 | -10.412 | < 0.0001 | 45 | 48 | 0.978 | 0.0028 | < 0.0001 | CONFLICT |
| DK2 | c_load_err | 8750 | 10 | -4.544 | 0.0002 | 168 | 168 | 1.987 | 1.37e-05 | < 0.0001 | CONFLICT |
| DK2 | x_da_id_spread | 8760 | 0 | -16.492 | < 0.0001 | 24 | 48 | 0.222 | 0.2287 | < 0.0001 | STATIONARY |
| DK2 | x_da_bal_spread | 8760 | 0 | -64.655 | < 0.0001 | 0 | 48 | 0.104 | 0.5647 | < 0.0001 | STATIONARY |
| DK2 | x_id_bal_spread | 8760 | 0 | -65.477 | < 0.0001 | 0 | 48 | 0.193 | 0.2817 | < 0.0001 | STATIONARY |

**Review needed: c_wind_total_err (DK1): CONFLICT; c_load_err (DK1): CONFLICT; c_wind_total_err (DK2): CONFLICT; c_load_err (DK2): CONFLICT**

Calendar controls: hour + month of sample (fixed in the stationarity step). The tests after these controls use simulated critical values; see 'Calendar check' and 'Final verdicts'.

ADF bound check for the series at the 168-lag limit, rerun with max 336: c_load_err DK1 lag 169, stat -5.25; c_load_err DK2 lag 336, stat -2.70 — ADF VERDICT CHANGES.

Robustness (S stationary, U unit root, C conflict, I inconclusive):

| zone | series | Baseline | KPSS bw 48 | KPSS bw 168 | alpha 1% | alpha 10% |
|---|---|---|---|---|---|---|
| DK1 | c_wind_total_err | C | C | C | C | C |
| DK1 | c_load_err | C | C | C | C | C |
| DK1 | x_da_id_spread | S | S | S | S | S |
| DK1 | x_da_bal_spread | S | S | S | S | S |
| DK1 | x_id_bal_spread | S | S | S | S | S |
| DK2 | c_wind_total_err | C | C | C | C | C |
| DK2 | c_load_err | C | C | C | C | C |
| DK2 | x_da_id_spread | S | S | S | S | S |
| DK2 | x_da_bal_spread | S | S | S | S | S |
| DK2 | x_id_bal_spread | S | S | S | S | S |

After the calendar controls (hour + month of sample) the standard critical values do not apply; see the sections 'Calendar check' (simulated critical values) and 'Final verdicts'.

## 2. Lag selection (same sample for every structure; lower = better)

| zone | spread | 1..1 | 1..2 | 1..3 | 1..4 | 1..6 | 1..12 | 1..24 | 1..48 | 1-24 + 48 |
|---|---|---|---|---|---|---|---|---|---|---|
| DK1 | x_da_id_spread | 22.6738 | 22.6304 | 22.6215 | 22.6266 | 22.6299 | 22.6515 | 22.7329 | 22.9129 | 22.7415 |
| DK1 | x_da_bal_spread | 27.9284 | 27.8912 | 27.8805 | 27.8871 | 27.8933 | 27.918 | 28.0038 | 28.1841 | 28.0128 |
| DK1 | x_id_bal_spread | 27.9151 | 27.8772 | 27.8668 | 27.8733 | 27.8795 | 27.9042 | 27.9897 | 28.1698 | 27.9986 |
| DK2 | x_da_id_spread | 20.7358 | 20.6519 | 20.6592 | 20.666 | 20.6776 | 20.7212 | 20.794 | 20.9713 | 20.8023 |
| DK2 | x_da_bal_spread | 25.7252 | 25.6482 | 25.6541 | 25.6623 | 25.6733 | 25.7184 | 25.7957 | 25.9776 | 25.8046 |
| DK2 | x_id_bal_spread | 25.7155 | 25.6383 | 25.6442 | 25.6524 | 25.6634 | 25.7082 | 25.7853 | 25.9675 | 25.7942 |

BIC-preferred contiguous order: DK1 x_da_id_spread: 1..3; DK1 x_da_bal_spread: 1..3; DK1 x_id_bal_spread: 1..3; DK2 x_da_id_spread: 1..2; DK2 x_da_bal_spread: 1..2; DK2 x_id_bal_spread: 1..2

<!-- dow-check start -->
## Day-of-week diagnostic (demand forecast errors; copies only, the controls are not changed)

Residuals after hour + month, and after hour + month + day of week (6 dummies, Copenhagen local time). ADF lag by AIC with bound 168 and 336; ADF critical value simulated (random walk, 168-h block steps, the same dummies, lag fixed at the selected lag, N = 1000); KPSS critical value simulated (AR(p) by BIC max 48, 168-h block bootstrap, N = 5000, automatic bandwidth); seed 2025. Autocorrelations on the residuals joined across missing hours.

DK1 demand forecast error: selected ADF lag 168 (bound 168), 169 (bound 336) with hour + month, 168 (bound 168), 169 (bound 336) with day of week added. ADF statistic vs simulated 5 % critical value — hour + month: bound 168: -7.65 vs -6.45; bound 336: -7.79 vs -6.40; + day of week: bound 168: -7.76 vs -6.38; bound 336: -7.90 vs -6.40. R² 0.133 -> 0.142; autocorrelation at 168 h 0.146 -> 0.137.
DK2 demand forecast error: selected ADF lag 168 (bound 168), 336 (bound 336) with hour + month, 168 (bound 168), 336 (bound 336) with day of week added. ADF statistic vs simulated 5 % critical value — hour + month: bound 168: -6.81 vs -6.38; bound 336: -6.16 vs -6.22; + day of week: bound 168: -6.82 vs -6.40; bound 336: -6.23 vs -6.34. R² 0.328 -> 0.341; autocorrelation at 168 h 0.182 -> 0.165.

| zone | series | controls | dummies | r2 | acf_24 | acf_168 | adf_bound | adf_lag | adf_stat | adf_crit_sim | adf_rejects | kpss_stat | kpss_crit_sim | kpss_p_sim |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| DK1 | c_load_err | hour + month | 34 | 0.1333 | 0.1397 | 0.1459 | 168 | 168 | -7.649 | -6.455 | True | 0.01339 | 0.02344 | 0.6658 |
| DK1 | c_load_err | hour + month | 34 | 0.1333 | 0.1397 | 0.1459 | 336 | 169 | -7.793 | -6.397 | True | 0.01339 | 0.02344 | 0.6658 |
| DK1 | c_load_err | hour + month + day of week | 40 | 0.1418 | 0.1433 | 0.1372 | 168 | 168 | -7.758 | -6.383 | True | 0.01347 | 0.02399 | 0.6886 |
| DK1 | c_load_err | hour + month + day of week | 40 | 0.1418 | 0.1433 | 0.1372 | 336 | 169 | -7.897 | -6.397 | True | 0.01347 | 0.02399 | 0.6886 |
| DK2 | c_load_err | hour + month | 34 | 0.3278 | 0.2503 | 0.1824 | 168 | 168 | -6.814 | -6.378 | True | 0.01294 | 0.02005 | 0.5422 |
| DK2 | c_load_err | hour + month | 34 | 0.3278 | 0.2503 | 0.1824 | 336 | 336 | -6.164 | -6.223 | False | 0.01294 | 0.02005 | 0.5422 |
| DK2 | c_load_err | hour + month + day of week | 40 | 0.3407 | 0.2595 | 0.1653 | 168 | 168 | -6.821 | -6.403 | True | 0.01345 | 0.02063 | 0.5314 |
| DK2 | c_load_err | hour + month + day of week | 40 | 0.3407 | 0.2595 | 0.1653 | 336 | 336 | -6.228 | -6.338 | False | 0.01345 | 0.02063 | 0.5314 |
<!-- dow-check end -->
<!-- calendar-check start -->
## Calendar check (2025): critical values after hour + month

**In plain words.** After removing the hour-of-day and monthly means (the VARX's calendar controls), the KPSS statistic is small by construction, because the running sums return to zero every month; the standard critical value 0.463 does not apply. The reference used instead is a simulated one: many stationary series with the same autocorrelation and the same (block-resampled) shocks as each residual, with exactly the same dummies removed; the 95th percentile of their KPSS statistics is the 5 % critical value. Share of variance the dummies absorb: DK1 wind forecast error 0.12 (hour alone 0.04); DK1 demand forecast error 0.13 (hour alone 0.09); DK2 wind forecast error 0.11 (hour alone 0.06); DK2 demand forecast error 0.33 (hour alone 0.30); spreads <= 1 %.

**A3 finding.** With a constant only, white noise gives a simulated 5 % KPSS critical value of 0.468 (standard 0.463), so the simulation reproduces the standard test. For the strongly autocorrelated raw forecast errors the simulated value is higher (KPSS over-rejects when the bandwidth is short relative to the persistence), but the raw statistics stay far above it: DK1 wind forecast error 1.117 vs 0.686 (p 0.0090, AR 25); DK1 demand forecast error 1.527 vs 0.759 (p 0.0030, AR 25); DK2 wind forecast error 0.978 vs 0.669 (p 0.0138, AR 2); DK2 demand forecast error 1.987 vs 0.683 (p 0.0004, AR 25). The raw rejections are not a finite-sample artefact.

Settings: AR(p) without constant, p by BIC (max 48 and max 168); innovations resampled in moving blocks of 168 h; N = 5000 (KPSS), 1000 (ADF); seed 2025; burn-in 500; KPSS with the automatic bandwidth and with 168 (verdict BANDWIDTH-SENSITIVE when the two disagree); ADF null = random walk with steps in 168-h blocks from the level-AR innovations, the same dummies, lag fixed at the data's lag. Decision (forecast errors, BIC max 48): ADF below its simulated critical value and KPSS below its simulated critical value at both bandwidths.

Decision changes between BIC max 48 and max 168: none.

| zone | series | raw_adf_stat | raw_adf_p | raw_adf_lags | raw_adf_max_lag | raw_kpss_stat | raw_kpss_p | raw_pp_stat | raw_pp_p | raw_decision | raw_n_dropped | n_dummies | r2_hour | r2_hour_month | adf_stat | adf_p | adf_lags | adf_max_lag | pp_stat | pp_p | kpss_stat | kpss_stat_168 | kpss_ar_order_ar48 | kpss_crit_auto_ar48 | kpss_p_auto_ar48 | kpss_crit_168_ar48 | kpss_p_168_ar48 | kpss_ar_order_ar168 | kpss_crit_auto_ar168 | kpss_p_auto_ar168 | kpss_crit_168_ar168 | kpss_p_168_ar168 | adf_crit_sim | decision_ar48 | decision_ar168 | decision |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| DK1 | c_wind_total_err | -6.957 | 9.395e-10 | 146 | 168 | 1.117 | 0.001312 | -16.13 | 4.75e-29 | CONFLICT | 123 | 34 | 0.04266 | 0.1247 | -9.652 | 1.428e-16 | 122 | 168 | -16.52 | 2.067e-29 | 0.01309 | 0.01547 | 3 | 0.02156 | 0.71 | 0.0224 | 0.6688 | 3 | 0.02185 | 0.7034 | 0.02256 | 0.666 | -6.501 | STATIONARY | STATIONARY | STATIONARY |
| DK1 | c_load_err | -5.162 | 1.053e-05 | 168 | 168 | 1.527 | 0.0001501 | -25.56 | 0 | CONFLICT | 10 | 34 | 0.09299 | 0.1333 | -16.05 | 5.766e-29 | 24 | 48 | -24.98 | 0 | 0.01339 | 0.01344 | 25 | 0.0235 | 0.6514 | 0.02304 | 0.8932 | 25 | 0.02352 | 0.6682 | 0.02317 | 0.8926 | -6.716 | STATIONARY | STATIONARY | STATIONARY |
| DK1 | x_da_id_spread | -14.38 | 9.095e-27 | 36 | 48 | 0.2309 | 0.2148 | -33.42 | 0 | STATIONARY | 0 | 34 | 0.002804 | 0.0114 | -14.65 | 3.546e-27 | 36 | 48 | -33.3 | 0 | 0.01097 | 0.01549 |  |  |  |  |  |  |  |  |  |  |  | nan | nan | nan |
| DK1 | x_da_bal_spread | -38.87 | 0 | 4 | 48 | 0.05971 | 0.8158 | -76.65 | 0 | STATIONARY | 0 | 34 | 0.002578 | 0.003745 | -38.97 | 0 | 4 | 48 | -76.49 | 0 | 0.01538 | 0.01774 |  |  |  |  |  |  |  |  |  |  |  | nan | nan | nan |
| DK1 | x_id_bal_spread | -39.65 | 0 | 4 | 48 | 0.1215 | 0.4893 | -77.26 | 0 | STATIONARY | 0 | 34 | 0.002535 | 0.003877 | -39.77 | 0 | 4 | 48 | -77.1 | 0 | 0.01609 | 0.01771 |  |  |  |  |  |  |  |  |  |  |  | nan | nan | nan |
| DK2 | c_wind_total_err | -10.41 | 1.794e-18 | 45 | 48 | 0.9783 | 0.002767 | -20.99 | 0 | CONFLICT | 123 | 34 | 0.05667 | 0.1053 | -14.22 | 1.653e-26 | 24 | 48 | -21.73 | 0 | 0.01621 | 0.01921 | 2 | 0.02035 | 0.2682 | 0.02239 | 0.238 | 2 | 0.02062 | 0.2602 | 0.0226 | 0.2374 | -7.068 | STATIONARY | STATIONARY | STATIONARY |
| DK2 | c_load_err | -4.544 | 0.0001639 | 168 | 168 | 1.987 | 1.37e-05 | -20.59 | 0 | CONFLICT | 10 | 34 | 0.2997 | 0.3278 | -6.814 | 2.083e-09 | 168 | 168 | -22.28 | 0 | 0.01294 | 0.01507 | 25 | 0.02003 | 0.5348 | 0.02326 | 0.7664 | 25 | 0.02017 | 0.5428 | 0.02346 | 0.7758 | -6.386 | STATIONARY | STATIONARY | STATIONARY |
| DK2 | x_da_id_spread | -16.49 | 2.19e-29 | 24 | 48 | 0.2219 | 0.2287 | -36.43 | 0 | STATIONARY | 0 | 34 | 0.002546 | 0.008861 | -16.69 | 1.49e-29 | 24 | 48 | -36.3 | 0 | 0.007745 | 0.01143 | 1 | 0.01797 | 0.979 | 0.02233 | 0.986 | 1 | 0.01787 | 0.9784 | 0.0223 | 0.9856 |  | STATIONARY | STATIONARY | STATIONARY |
| DK2 | x_da_bal_spread | -64.66 | 0 | 0 | 48 | 0.1042 | 0.5647 | -65.11 | 0 | STATIONARY | 0 | 34 | 0.002782 | 0.004954 | -64.77 | 0 | 0 | 48 | -64.9 | 0 | 0.01952 | 0.01978 | 1 | 0.02165 | 0.1052 | 0.02335 | 0.2306 | 1 | 0.02139 | 0.0932 | 0.02311 | 0.2222 |  | STATIONARY | STATIONARY | STATIONARY |
| DK2 | x_id_bal_spread | -65.48 | 0 | 0 | 48 | 0.1929 | 0.2817 | -65.73 | 0 | STATIONARY | 0 | 34 | 0.002493 | 0.004853 | -65.6 | 0 | 0 | 48 | -65.47 | 0 | 0.02205 | 0.02001 | 1 | 0.02351 | 0.0822 | 0.02338 | 0.2236 | 1 | 0.02356 | 0.0798 | 0.02345 | 0.2212 |  | STATIONARY | STATIONARY | STATIONARY |
<!-- calendar-check end -->
<!-- month-only start -->
## Month-only vs hour + month (forecast errors)

Same design as the calendar check (ADF lag by the baseline rule, critical values simulated with the same dummies; KPSS critical values simulated at both bandwidths, N = 5000, seed 2025; ADF N = 1000).

In plain words: no decision differs between month only and hour + month.

| zone | series | controls | dummies | r2 | adf_stat | adf_lags | adf_crit_sim | kpss_auto | kpss_crit_auto | kpss_168 | kpss_crit_168 | decision |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| DK1 | c_wind_total_err | month only | 11 | 0.08206 | -9.663 | 146 | -6.451 | 0.01312 | 0.02181 | 0.01552 | 0.02246 | STATIONARY |
| DK1 | c_wind_total_err | hour + month | 34 | 0.1247 | -9.652 | 122 | -6.568 | 0.01309 | 0.02169 | 0.01547 | 0.02249 | STATIONARY |
| DK1 | c_load_err | month only | 11 | 0.04024 | -7.64 | 168 | -6.53 | 0.01335 | 0.02353 | 0.01338 | 0.02312 | STATIONARY |
| DK1 | c_load_err | hour + month | 34 | 0.1333 | -16.05 | 24 | -6.704 | 0.01339 | 0.02352 | 0.01344 | 0.02305 | STATIONARY |
| DK2 | c_wind_total_err | month only | 11 | 0.04861 | -11.83 | 46 | -6.869 | 0.01634 | 0.02045 | 0.01932 | 0.02243 | STATIONARY |
| DK2 | c_wind_total_err | hour + month | 34 | 0.1053 | -14.22 | 24 | -7.062 | 0.01621 | 0.02038 | 0.01921 | 0.02241 | STATIONARY |
| DK2 | c_load_err | month only | 11 | 0.02795 | -6.87 | 168 | -6.354 | 0.01237 | 0.01812 | 0.01512 | 0.02311 | STATIONARY |
| DK2 | c_load_err | hour + month | 34 | 0.3278 | -6.814 | 168 | -6.385 | 0.01294 | 0.01989 | 0.01507 | 0.02334 | STATIONARY |
<!-- month-only end -->
<!-- lag-robustness start -->
## ADF lag-rule robustness (forecast errors)

The main tables use ONE rule everywhere: AIC up to 48, extended to 168 only if 48 is selected. Each cell: selected lag / ADF statistic vs 5 % critical value — verdict. Raw: standard -2.86. After hour + month: simulated at the same lag (random walk, 168-h block steps, same dummies, N = 1000, seed 2025).

| zone | series | rule | raw | after |
|---|---|---|---|---|
| DK1 | c_wind_total_err | baseline (AIC 48 -> 168) | 146 / -6.96 vs -2.86 — reject | 122 / -9.65 vs -6.57 — reject |
| DK1 | c_wind_total_err | AIC bound 168 | 146 / -6.96 vs -2.86 — reject | 122 / -9.65 vs -6.57 — reject |
| DK1 | c_wind_total_err | AIC bound 336 | 192 / -5.23 vs -2.86 — reject | 72 / -10.89 vs -6.96 — reject |
| DK1 | c_wind_total_err | BIC bound 168 | 24 / -12.55 vs -2.86 — reject | 2 / -21.58 vs -6.44 — reject |
| DK1 | c_load_err | baseline (AIC 48 -> 168) | 168 / -5.16 vs -2.86 — reject | 24 / -16.05 vs -6.70 — reject |
| DK1 | c_load_err | AIC bound 168 | 168 / -5.16 vs -2.86 — reject | 168 / -7.65 vs -6.54 — reject |
| DK1 | c_load_err | AIC bound 336 | 169 / -5.25 vs -2.86 — reject | 169 / -7.79 vs -6.50 — reject |
| DK1 | c_load_err | BIC bound 168 | 24 / -14.72 vs -2.86 — reject | 24 / -16.05 vs -6.70 — reject |
| DK2 | c_wind_total_err | baseline (AIC 48 -> 168) | 45 / -10.41 vs -2.86 — reject | 24 / -14.22 vs -7.06 — reject |
| DK2 | c_wind_total_err | AIC bound 168 | 122 / -6.91 vs -2.86 — reject | 24 / -14.22 vs -7.06 — reject |
| DK2 | c_wind_total_err | AIC bound 336 | 93 / -7.27 vs -2.86 — reject | 24 / -14.22 vs -7.06 — reject |
| DK2 | c_wind_total_err | BIC bound 168 | 1 / -29.11 vs -2.86 — reject | 1 / -29.65 vs -6.34 — reject |
| DK2 | c_load_err | baseline (AIC 48 -> 168) | 168 / -4.54 vs -2.86 — reject | 168 / -6.81 vs -6.38 — reject |
| DK2 | c_load_err | AIC bound 168 | 168 / -4.54 vs -2.86 — reject | 168 / -6.81 vs -6.38 — reject |
| DK2 | c_load_err | AIC bound 336 | 336 / -2.70 vs -2.86 — do not reject | 336 / -6.16 vs -6.24 — do not reject |
| DK2 | c_load_err | BIC bound 168 | 49 / -11.25 vs -2.86 — reject | 24 / -15.09 vs -7.22 — reject |
<!-- lag-robustness end -->
<!-- monte-carlo start -->
## Monte Carlo noise of the simulated critical values

ADF after hour + month (baseline lag rule): N = 2000 per seed, seeds 2025, 7, 42. Decision flips across seeds: none.

| zone | series | lag | adf_stat | crit_seed_2025 | crit_seed_7 | crit_seed_42 | crit_mean | crit_min | crit_max | rejects_all_seeds | rejects_any_seed |
|---|---|---|---|---|---|---|---|---|---|---|---|
| DK1 | c_wind_total_err | 122 | -9.652 | -6.536 | -6.517 | -6.55 | -6.534 | -6.55 | -6.517 | True | True |
| DK1 | c_load_err | 24 | -16.05 | -6.706 | -6.732 | -6.804 | -6.748 | -6.804 | -6.706 | True | True |
| DK2 | c_wind_total_err | 24 | -14.22 | -7.018 | -7.016 | -6.938 | -6.991 | -7.018 | -6.938 | True | True |
| DK2 | c_load_err | 168 | -6.814 | -6.365 | -6.355 | -6.349 | -6.356 | -6.365 | -6.349 | True | True |

Raw size-corrected KPSS (constant only, block bootstrap, automatic bandwidth): N = 5000 per seed, same seeds.

| zone | series | raw_kpss | crit_seed_2025 | crit_seed_7 | crit_seed_42 | crit_mean | crit_min | crit_max | p_min | p_max |
|---|---|---|---|---|---|---|---|---|---|---|
| DK1 | c_wind_total_err | 1.117 | 0.7046 | 0.6938 | 0.6601 | 0.6862 | 0.6601 | 0.7046 | 0.0068 | 0.0092 |
| DK1 | c_load_err | 1.527 | 0.748 | 0.7749 | 0.7551 | 0.7594 | 0.748 | 0.7749 | 0.0018 | 0.003 |
| DK2 | c_wind_total_err | 0.9783 | 0.6602 | 0.6617 | 0.6783 | 0.6667 | 0.6602 | 0.6783 | 0.0162 | 0.0172 |
| DK2 | c_load_err | 1.987 | 0.6759 | 0.6644 | 0.6844 | 0.6749 | 0.6644 | 0.6844 | 0.0002 | 0.0006 |
<!-- monte-carlo end -->
<!-- final-verdicts start -->
## Final verdicts (2025)

| Area | Series | Verdict | Depends on the ADF lag rule? |
|---|---|---|---|
| DK1 | Wind forecast error | stationary conditional on controls (hour + month) | no — every rule rejects, raw and after controls |
| DK1 | Demand forecast error | stationary conditional on controls (hour + month) | no — every rule rejects, raw and after controls |
| DK1 | DA-ID spread | stationary | — (raw test) |
| DK1 | DA-BAL spread | stationary | — (raw test) |
| DK1 | ID-BAL spread | stationary | — (raw test) |
| DK2 | Wind forecast error | stationary conditional on controls (hour + month) | no — every rule rejects, raw and after controls |
| DK2 | Demand forecast error | stationary conditional on controls (KPSS); ADF not robust | yes — AIC with bound 336 (lag 336) does not reject, raw (-2.70 vs -2.86) nor after controls (-6.16 vs -6.24); the baseline rule, AIC 168 and BIC 168 reject |
| DK2 | DA-ID spread | stationary | — (raw test) |
| DK2 | DA-BAL spread | stationary | — (raw test) |
| DK2 | ID-BAL spread | stationary | — (raw test) |

Raw tests are the main result. The forecast errors conflict raw (ADF rejects, KPSS rejects; the KPSS rejections
hold against size-corrected critical values); after hour + month effects KPSS finds no further level movement
against simulated critical values (both bandwidths, AR bound 48 and 168, month only and hour + month). The ADF after
the dummies is supporting evidence only (its simulated null is far stricter than -2.86). Weakest case: DK2 demand
forecast error. No decision flips across Monte Carlo seeds.
<!-- final-verdicts end -->
<!-- thesis-numbers start -->
## Numbers used in the thesis (where each one comes from)

| Number in the text | Value | Source |
|---|---|---|
| Raw ADF stat / lags, KPSS stat / p (10 series) | Table 1 | stationarity_baseline.png; section "Calendar check", columns raw_* |
| Dummy R² of the forecast errors | 0.11 to 0.33 (0.105 DK2 wind - 0.328 DK2 demand) | stationarity_after_calendar.png; Calendar check, r2_hour_month |
| KPSS after controls | 0.013 to 0.016 | stationarity_after_calendar.png; Calendar check, kpss_stat |
| Simulated KPSS 5 % critical value after controls | 0.020 to 0.024 (auto 0.020-0.024, bw 168 0.022-0.024) | stationarity_after_calendar.png; Calendar check, kpss_crit_*_ar48 |
| Simulated KPSS p after controls | 0.24 to 0.89 (auto 0.27-0.71, bw 168 0.24-0.89) | Calendar check, kpss_p_*_ar48 |
| Spreads: variance absorbed by the dummies | at most 1.1 % (DK1 DA-ID 0.011; all others <= 0.009) | Calendar check, r2_hour_month |
| Raw size-corrected KPSS 5 % critical value | 0.66 to 0.78 over three seeds (mean 0.67-0.76) | section "Monte Carlo noise", second table |
| Raw size-corrected KPSS p | 0.0002 to 0.017 over three seeds (DK2 wind 0.016-0.017, DK2 demand 0.0002-0.0006) | Monte Carlo noise, second table |
| ADF simulated 5 % critical value after controls | -6.35 to -7.02 (means -6.36 to -6.99 over three seeds, N = 2000) | Monte Carlo noise, first table |
| DK2 demand ADF after controls vs critical value | -6.81 vs -6.36 (mean; range -6.35 to -6.36) | Monte Carlo noise, first table |
| DK2 demand, raw ADF with AIC bound 336 | -2.70 (lag 336) | ADF lag-rule robustness |
| DK2 demand, after controls, AIC bound 336 | -6.16 vs -6.24 | ADF lag-rule robustness |
| DK2 demand, + day of week, AIC bound 336 | -6.23 vs -6.34 | Day-of-week diagnostic |
| DK2 demand, BIC, after controls | lag 24, -15.09 (BIC bound 168 and 336 give the same) | ADF lag-rule robustness; stationarity_adf_lag_check.png |
| DK1 demand, after controls, AIC bound 336 / 168 | -7.79 vs -6.50 (lag 169) / -7.65 vs -6.54 (lag 168) | ADF lag-rule robustness |
| Autocorrelation of the demand residuals at 168 h | 0.146 (DK1) / 0.182 (DK2); with day of week 0.137 / 0.165 | Day-of-week diagnostic |
| Autocorrelation at 24 h | 0.140 (DK1) / 0.250 (DK2) | Day-of-week diagnostic |
| Missing hours | 123 per zone (wind error), 10 per zone (demand error) | Table 1 footnote; Calendar check, raw_n_dropped |
| Controls | hour + month of sample, 34 dummies + constant | Table 2 footnote |
<!-- thesis-numbers end -->
<!-- changes start -->
## Changes outside the diagnostic (this step)

- `main.py`: `baseline_2022_2025` put on hold (commented out in DATAFRAMES, outputs kept);
  `VAR_TEST_SETTINGS["calendar_check"] = ["baseline_2025"]`.
- `src/model/VAR_tests.py` (stationarity code only; the VAR estimation code is unchanged):
  - calendar check: `_fit_ar_bic` (fast BIC AR order), `_block_indices`, `_simulate_ar` (168-h block
    resampling), `_dummy_basis`, `_project_out`, `kpss_critical_value_sim`, `_adf_tstat_fixed`,
    `adf_critical_value_sim` (random walk with 168-h block steps), `_clean_table` (figure style: coloured
    Decision, explicit widths, rules drawn separately, footnote under the table), `TABLE_WIDTHS`,
    `run_calendar_check`, `calendar_check_main`;
  - diagnostics: `day_of_week`, `run_dow_check`, `dow_check_main`; `LAG_RULES`, `_lag_by_rule`,
    `run_final_checks`, `_write_final_sections`, `final_checks_main`;
  - `_adf_aic_lag` gained an `ic` argument (BIC); `adf_lag_check` / `adf_lag_check_main`;
  - `run_var_tests` gained `calendar_check` (runs the calendar check for the listed dataframes) and keeps
    marked sections when it rewrites VAR_TESTS.md;
  - command-line options `--calendar-check`, `--dow-check`, `--final-checks`, `--adf-lag-check`;
  - default dataframe of the command line and of the tests: `baseline_2025`;
  - tests added: block indices, fast BIC AR order, KPSS bootstrap on white noise, random-walk ADF null
    (i.i.d. and block), day of week, BIC lag search; the full-window test uses the data's first year.
- Not changed: `model_specs.py`, the dataframe builder and the dataframes, the chosen controls, the raw
  decisions, the ADF lag rule of the main tables.
- Later: the file was renamed `src/model/VAR_tests.py` -> `src/model/stationarity_lag_selection.py`, and all VAR
  estimation code (full / short models, stability eigenvalues, portmanteau) was deleted; only the
  stationarity tests and the lag selection remain. Section 3 (estimated models) was removed from this file.
<!-- changes end -->
<!-- model-spec start -->
## Model specification (for the thesis)

Read from the code (`src/model_specs.py` SPODNIAK_BASELINE, `src/dataframe_building.py`, `src/model/VAR_tests.py`
run_var_tests). 2025, per zone (DK1, DK2). Units: every MW quantity is the hourly mean of MW, i.e. MWh per hour
(15-min data averaged to hourly in the import scripts).

### S1. Variables

One VARX per (zone, spread): y_t = (wind forecast error, demand forecast error, spread)', the errors ordered before
the spread. Three VARXs per zone (one per spread), because DA-BAL = DA-ID + ID-BAL holds exactly.

| Role | Column | Definition | Unit | Sign convention | Source / construction |
|---|---|---|---|---|---|
| Endogenous | `c_wind_total_err` | Wind forecast error WE_t = forecast - actual, total wind (onshore + offshore) | MWh/h | **forecast minus actual**; positive = over-forecast (less wind than planned) | Nord Pool Data Portal API (Power System): day-ahead production prognosis and actual production; `c_wind_total_forecast_mw - c_wind_total_actual_mw`, each = onshore + offshore |
| Endogenous | `c_load_err` | Demand forecast error LE_t = forecast - actual | MWh/h | **forecast minus actual**; positive = over-forecast (less demand than planned) | Nord Pool Power System: consumption prognosis and actual consumption; `c_load_forecast_mw - c_load_actual_mw` |
| Endogenous | `x_da_id_spread` | DA-ID spread = P_DA - P_ID | EUR/MWh | positive = day-ahead above intraday | `da_price - id_vwap`; hours with zero intraday volume take P_ID = P_DA (spread 0); an hour missing from the intraday data stays missing |
| Endogenous | `x_da_bal_spread` | DA-BAL spread = P_DA - P_BAL | EUR/MWh | positive = day-ahead above imbalance price | `da_price - b_imbalance_price` (Nord Pool imbalance price; from 2025 the hourly mean of the 15-min prices) |
| Endogenous | `x_id_bal_spread` | ID-BAL spread = P_ID - P_BAL | EUR/MWh | positive = intraday above imbalance price | `id_vwap` (same zero-volume rule) `- b_imbalance_price` |
| Exogenous | `c_wind_total_actual_mw_change_1` | Wind ramp R_t = W_t - W_(t-1): change from the previous hour of ACTUAL total wind production (onshore + offshore) | MWh/h | positive = ramping up | first difference per zone of `c_wind_total_actual_mw` (Nord Pool actual production); NaN if t or t-1 is missing |
| Exogenous | `da_flow_<counterpart>_net_export_mw` | Cross-border flow on one interconnection = export - import | MWh/h | **positive = export from the zone**, negative = import | Nord Pool Data Portal API DayAheadFlow (day-ahead **scheduled** exchange, not physical flows); `da_flow_<c>_export_mw - da_flow_<c>_import_mw` |
| Exogenous (fixed effects) | `fe_hour`, `fe_month_of_sample` | calendar dummies, see S2 | — | — | calendar |

Interconnections in the VARX (each with >= 5 % of the zone's total mean |flow|; none was dropped):
- **DK1:** Germany (`ger`), Netherlands (`nl`), Norway NO2 (`no2`), Sweden SE3 (`se3`), DK2 / Great Belt (`dk2`).
- **DK2:** Sweden SE4 (`se4`), Germany (`ger`), DK1 / Great Belt (`dk1`).
- **Missing Danish interconnection:** DK1 - Great Britain (Viking Link) is NOT in the data (the Nord Pool flow file
  has no GB column). No other is missing from the flow file: NL, DE, NO2, SE3, DK2 for DK1; DE, SE4, DK1 for DK2.

**Congestion indicator built or used in the estimation: NO.** It was removed from the builder, the spec and the
VARX; a test confirms no code reference remains (comments that explain the change only).
**Hydro variable used in the estimation: NO.** Reservoir filling columns (`c_reservoir_fill_pct_*`, NO / SE / FI and
sub-areas) ARE built in the dataframe as role "Input" (used in the correlation analysis only); the hydro deviation
of the literature has role "Not included" (no history before 2022 for its running median). Neither enters the VARX.

### S2. Calendar controls

- `fe_hour`: hour of day 0-23 in **Copenhagen local time** (24 categories; on the 23-hour DST day hour 2 has no hours,
  on the 25-hour day hour 2 occurs twice and both share the dummy). Dummies with `drop_first`: **hour 0 (00:00-01:00
  local) is the reference** -> 23 dummies.
- `fe_month_of_sample`: calendar month in **Copenhagen local time**, renumbered 1..N within the dataframe; 12
  categories for 2025. The final UTC hour (2025-12-31 23:00 UTC = 2026-01-01 00:00 local) would form a one-hour
  "month"; a first / last month with fewer than `MIN_EDGE_MONTH_HOURS = 24` hours is merged into its neighbour, so
  that hour belongs to **December** (745 hours). `drop_first`: **January 2025 is the reference** -> 11 dummies.
- **Constant: yes.** Total: 23 + 11 = **34 dummies + constant**. Dummies are built on the estimation rows of each
  model (first category present dropped there).
- **Weekly term in the VARX code path: NO for 2025.** `run_var_tests` uses `fe_cols = choice["columns"]`, the
  coarsest control set of `CONTROL_SETS` after which every endogenous series is stationary = hour + month. The weekly
  set (`fe_week_of_sample`) exists only as the fallback in `CONTROL_SETS` (`VAR_tests.py`), in the spec entry
  "Week fixed effects", and in the stationarity diagnostics (decomposition table); it is not used in the VARX.

### S3. Lag structures (lag selection only; no model is estimated)

- Compared on ONE common sample (the hours valid for the longest structure): contiguous orders 1..p for p in
  1, 2, 3, 4, 6, 12, 24, 48, and the literature structure lags 1-24 and 48 (25 lag matrices).
- BIC-preferred contiguous order: DK1 p = 3, DK2 p = 2 (all three spreads); see section 2.
- A row is used only when y_t, every lag of y and every exogenous variable are observed (listwise; no
  interpolation): wind error 123 missing hours, demand error 10, spreads 0.

### S4. Replication reference in the repository

- No paper (PDF), bibliography file or README content is in the repository (`readme.md` is empty; no `.bib`/`.tex`).
- The only description of the reference is in the code, written for this project and NOT verified against the paper
  here: `src/model_specs.py` SPODNIAK_BASELINE (title "Baseline VAR (Spodniak et al. 2019; also Nieminen et al.
  2023)", key `spodniak2019relevance`; per-variable `definition`, `literature_source` and `deviation`; notes: one VAR
  per zone, lags 1-24 and 48, fixed effects for hour and week, hydro deviation of reservoir filling vs its running
  median for NO/SE/FI), comments in `src/dataframe_building.py` (sign convention WE_t = W^_t - W_t, LE_t = L^_t - L_t;
  spread price definitions) and `FULL_LAGS` in `VAR_tests.py`. The literature's congestion indicator (zone price !=
  system price) is described only where it is replaced.
- The paper's own specification is therefore not available in the repo; check it against the paper itself.

### R1. Rolling figures

`rolling_<series>_2025.png` (5 files, this folder): rows = trailing rolling mean (top) and rolling standard deviation
(bottom), columns = DK1, DK2; window **720 hours (30 days)**, a value needs >= 80 % of the window observed (so the
lines start about 24 days into 2025); units in the titles and axis labels; DK1 blue, DK2 orange. They supersede the
per-zone `stationarity_plots/{zone}_{series}.png` (30-day rolling mean and std, one file per zone and series) for the
thesis; those files are left in place.
<!-- model-spec end -->
<!-- data-checks start -->
## Data checks (stationarity step)

Read-only checks; nothing was added to any dataframe or spec.

### T1. Exchange data in the raw folder

- **Viking Link ("DK1 - DK1_VL (MW)") is NOT in the raw data.** No raw file contains "DK1_VL", "VL" or "Viking"
  (searched all 23,109 JSON and 912 XML files under `data/raw`). Its unit and sign convention can therefore not be
  read from this repository.
- The only exchange data are the Nord Pool Data Portal **DayAheadFlow** responses,
  `data/raw/day_ahead/flows/<date>_<area>.json` (one file per delivery day, CET, and area; written by
  `src/imports/import_da_pipeline.py`). They are the **day-ahead scheduled exchange** (`"market": "DayAhead"`), not
  physical flows; unit **MW** per delivery period (15-min periods from 1 Oct 2025 averaged to hourly in the import).
  Sign in the raw file: `netPosition = import - export` (positive = import into the area).
- Exchange fields per delivery period: `totalImport`, `totalExport`, `totalNetPosition`, and per connection area
  `import`, `export`, `netPosition`. Connection areas found in every raw file:
  - **DK1:** DK2, GER, NL, NO2, SE3;
  - **DK2:** DK1, GER, SE4.
- Processed file `data/processed/day_ahead/flows_DK1_DK2_2021_2025_hourly.csv`: `Total{Import,Export,NetPosition}_MW`
  and `{NL,GER,DK2,NO2,SE3,DK1,SE4}_{Import,Export,NetPosition}_MW` (counterparts the area is not connected to are 0).
- Used by the dataframe builder (`SOURCES["da_nordpool_flows"]`): every `{counterpart}_Import_MW` / `_Export_MW`,
  as the inputs of `da_flow_<counterpart>_net_export_mw = export - import` (positive = export from the zone).
  Loaded but NOT kept in `baseline_2025`: `Total*_MW` (sum of the connections; would be collinear with them) and
  every `*_NetPosition_MW` (= import - export, the same information with the opposite sign).
- To add Viking Link, a download is needed: the Nord Pool report in which the user found "DK1 - DK1_VL (MW)"
  (delivery period CET; delivery area DK1, connection DK1_VL), period 2025-01-01 to 2025-12-31 (plus the warm-up
  week of 2024-12-25 to 2024-12-31), unit and sign convention to be read from that report's header. The current
  DayAheadFlow API responses do not return a DK1_VL connection.
- **Decision (user): Viking Link is not used.** It does not appear on Nord Pool's day-ahead flow page either, so the day-ahead flow data used here has no Viking Link exchange.

### T2. Intraday gaps (2025)

Hours without an intraday trade (`id_transaction_volume_mwh = 0`) take the day-ahead price as the intraday price, so
their DA-ID spread is exactly 0 and their DA-BAL and ID-BAL spreads are identical.

| Zone | Hours | Hours without an intraday trade | Share of 8,760 | DA-ID spread exactly 0 (all hours) | of which without a trade | DA-BAL = ID-BAL (exactly) |
|---|---|---|---|---|---|---|
| DK1 | 8,760 | 0 | 0.00 % | 7 | 0 | 7 |
| DK2 | 8,760 | 5 | 0.06 % | 9 | 5 | 9 |

- The remaining zero DA-ID hours (DK1 7, DK2 4) have intraday trades whose VWAP happens to equal the day-ahead price.
- DA-BAL = ID-BAL holds exactly in the same hours as DA-ID = 0 (the identity DA-BAL = DA-ID + ID-BAL); only 5 of
  them (DK2) are due to the no-trade rule. No hour has a missing intraday volume or VWAP apart from those 5 DK2
  hours (VWAP empty because there were no trades).

### T3. Text cleanup

Section 1 no longer claims "coarsest set" or "10 of 10 stationary", and its robustness table no longer has the
"Hour + month of sample removed" column (it used the standard KPSS critical value, which does not apply after
dummies); a pointer to 'Calendar check' and 'Final verdicts' replaces it. No result was recomputed.
<!-- data-checks end -->
