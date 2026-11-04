# Stationarity tests — endogenous variables

Per bidding zone; alpha = 0.05. ADF (H0 unit root; constant; AIC lag up to 48, searched again up to 168 where 48 was selected) and KPSS (H0 stationary; constant; automatic bandwidth; exact asymptotic p-value) decide; Phillips-Perron (H0 unit root) is supporting only. STATIONARY: ADF rejects, KPSS does not. UNIT ROOT: the reverse. CONFLICT: both reject. INCONCLUSIVE: neither rejects. Nothing is differenced or transformed.

## 1. Levels (the series as they are)

| zone | series | n_obs | n_dropped | adf_stat | adf_p | adf_lags | adf_max_lag | kpss_stat | kpss_p | kpss_lags | pp_stat | pp_p | decision |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| DK1 | x_da_id_spread | 8760 | 0 | -14.38 | 9.095e-27 | 36 | 48 | 0.2309 | 0.2148 | 46 | -33.42 | 0 | STATIONARY |
| DK1 | x_id_bal_spread | 8760 | 0 | -39.65 | 0 | 4 | 48 | 0.1215 | 0.4893 | 14 | -77.26 | 0 | STATIONARY |
| DK1 | x_da_bal_spread | 8760 | 0 | -38.87 | 0 | 4 | 48 | 0.05971 | 0.8158 | 18 | -76.65 | 0 | STATIONARY |
| DK1 | c_wind_total_err | 8637 | 123 | -6.957 | 9.395e-10 | 146 | 168 | 1.117 | 0.001312 | 50 | -16.13 | 4.75e-29 | CONFLICT |
| DK1 | c_load_err | 8750 | 10 | -5.162 | 1.053e-05 | 168 | 168 | 1.527 | 0.0001501 | 44 | -25.56 | 0 | CONFLICT |
| DK2 | x_da_id_spread | 8760 | 0 | -16.49 | 2.19e-29 | 24 | 48 | 0.2219 | 0.2287 | 45 | -36.43 | 0 | STATIONARY |
| DK2 | x_id_bal_spread | 8760 | 0 | -65.48 | 0 | 0 | 48 | 0.1929 | 0.2817 | 16 | -65.73 | 0 | STATIONARY |
| DK2 | x_da_bal_spread | 8760 | 0 | -64.66 | 0 | 0 | 48 | 0.1042 | 0.5647 | 20 | -65.11 | 0 | STATIONARY |
| DK2 | c_wind_total_err | 8637 | 123 | -10.41 | 1.794e-18 | 45 | 48 | 0.9783 | 0.002767 | 46 | -20.99 | 0 | CONFLICT |
| DK2 | c_load_err | 8750 | 10 | -4.544 | 0.0001639 | 168 | 168 | 1.987 | 1.37e-05 | 41 | -20.59 | 0 | CONFLICT |

**Not stationary: c_wind_total_err (DK1): CONFLICT; c_load_err (DK1): CONFLICT; c_wind_total_err (DK2): CONFLICT; c_load_err (DK2): CONFLICT** Missing hours dropped before testing (not interpolated): c_wind_total_err DK1 123; c_load_err DK1 10; c_wind_total_err DK2 123; c_load_err DK2 10.

## 2. After the calendar dummies (fe_hour, fe_month_of_sample)

Residuals of an OLS on a constant + the dummies; statistics compared with simulated 5 % critical values (KPSS: AR(p) by BIC max 48, 168-h block bootstrap, N = 5000; ADF: block random walks, lag fixed at the data's lag, N = 1000; seed 2025, one stream per zone and variable). BANDWIDTH-SENSITIVE: the KPSS verdict differs between the automatic bandwidth and 168.

| zone | series | n_obs | n_dummies | r2 | adf_stat | adf_lags | adf_max_lag | adf_crit_sim | adf_p_sim | ar_order | kpss_stat | kpss_crit_sim | kpss_p_sim | kpss_stat_48 | kpss_crit_48_sim | kpss_p_48_sim | kpss_stat_168 | kpss_crit_168_sim | kpss_p_168_sim | decision |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| DK1 | x_da_id_spread | 8760 | 34 | 0.0114 | -14.65 | 36 | 48 | -7.459 | 0 | 5 | 0.01097 | 0.01832 | 0.7036 | 0.01095 | 0.01822 | 0.7026 | 0.01549 | 0.02249 | 0.657 | STATIONARY |
| DK1 | x_id_bal_spread | 8760 | 34 | 0.003877 | -39.77 | 4 | 48 | -6.522 | 0 | 1 | 0.01609 | 0.01986 | 0.2096 | 0.01608 | 0.01982 | 0.234 | 0.01771 | 0.02279 | 0.4116 | STATIONARY |
| DK1 | x_da_bal_spread | 8760 | 34 | 0.003745 | -38.97 | 4 | 48 | -6.455 | 0 | 1 | 0.01538 | 0.01938 | 0.2544 | 0.01516 | 0.01894 | 0.28 | 0.01774 | 0.02245 | 0.4108 | STATIONARY |
| DK1 | c_wind_total_err | 8637 | 34 | 0.1247 | -9.652 | 122 | 168 | -6.518 | 0 | 3 | 0.01309 | 0.02134 | 0.709 | 0.01323 | 0.02155 | 0.706 | 0.01547 | 0.02221 | 0.6716 | STATIONARY |
| DK1 | c_load_err | 8750 | 34 | 0.1333 | -16.05 | 24 | 48 | -6.822 | 0 | 25 | 0.01339 | 0.0235 | 0.6604 | 0.01318 | 0.02317 | 0.673 | 0.01344 | 0.02309 | 0.8928 | STATIONARY |
| DK2 | x_da_id_spread | 8760 | 34 | 0.008861 | -16.69 | 24 | 48 | -7.538 | 0 | 1 | 0.007745 | 0.01765 | 0.9748 | 0.007748 | 0.01764 | 0.976 | 0.01143 | 0.022 | 0.9852 | STATIONARY |
| DK2 | x_id_bal_spread | 8760 | 34 | 0.004853 | -65.6 | 0 | 48 | -6.859 | 0 | 1 | 0.02205 | 0.02369 | 0.0784 | 0.02043 | 0.02174 | 0.0848 | 0.02001 | 0.02354 | 0.2234 | STATIONARY |
| DK2 | x_da_bal_spread | 8760 | 34 | 0.004954 | -64.77 | 0 | 48 | -6.83 | 0 | 1 | 0.01952 | 0.02168 | 0.1004 | 0.01874 | 0.02068 | 0.1044 | 0.01978 | 0.02324 | 0.2376 | STATIONARY |
| DK2 | c_wind_total_err | 8637 | 34 | 0.1053 | -14.22 | 24 | 48 | -6.939 | 0 | 2 | 0.01621 | 0.02035 | 0.2684 | 0.01604 | 0.02019 | 0.273 | 0.01921 | 0.02252 | 0.2394 | STATIONARY |
| DK2 | c_load_err | 8750 | 34 | 0.3278 | -6.814 | 168 | 168 | -6.392 | 0.011 | 25 | 0.01294 | 0.02025 | 0.538 | 0.01292 | 0.02006 | 0.5462 | 0.01507 | 0.02322 | 0.772 | STATIONARY |

**All stationary.**

## 3. Robustness (levels)

| zone | series | Levels | KPSS bw 48 | KPSS bw 168 | alpha 1% | alpha 10% |
|---|---|---|---|---|---|---|
| DK1 | x_da_id_spread | S | S | S | S | S |
| DK1 | x_id_bal_spread | S | S | S | S | S |
| DK1 | x_da_bal_spread | S | S | S | S | S |
| DK1 | c_wind_total_err | C | C | C | C | C |
| DK1 | c_load_err | C | C | C | C | C |
| DK2 | x_da_id_spread | S | S | S | S | S |
| DK2 | x_id_bal_spread | S | S | S | S | S |
| DK2 | x_da_bal_spread | S | S | S | S | S |
| DK2 | c_wind_total_err | C | C | C | C | C |
| DK2 | c_load_err | C | C | C | C | C |

S stationary, U unit root, C conflict, I inconclusive.

## 4. Robustness (after the calendar dummies)

The same checks on the tests after the dummies: KPSS with each fixed bandwidth against its own simulated critical value (ADF unchanged), and the simulated p-values at the other significance levels. No windows (each would need its own simulations).

| zone | series | After dummies | KPSS bw 48 | KPSS bw 168 | alpha 1% | alpha 10% |
|---|---|---|---|---|---|---|
| DK1 | x_da_id_spread | S | S | S | S | S |
| DK1 | x_id_bal_spread | S | S | S | S | S |
| DK1 | x_da_bal_spread | S | S | S | S | S |
| DK1 | c_wind_total_err | S | S | S | S | S |
| DK1 | c_load_err | S | S | S | S | S |
| DK2 | x_da_id_spread | S | S | S | S | S |
| DK2 | x_id_bal_spread | S | S | S | S | C |
| DK2 | x_da_bal_spread | S | S | S | S | S |
| DK2 | c_wind_total_err | S | S | S | S | S |
| DK2 | c_load_err | S | S | S | I | S |

S stationary, U unit root, C conflict, I inconclusive, B bandwidth-sensitive.
