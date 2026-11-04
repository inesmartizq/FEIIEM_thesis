# VARX

VARX(p, 0) per zone and system with the lag order of the lag_selection step, fitted by least squares on every hour valid for p. Variables in Cholesky order (first = not moved by the others within the hour).

**Granger causality:** H0 = the p lags of the cause add nothing to the equation of the effect. Wald test with heteroskedasticity-robust covariance; p-value from 1000 block wild bootstrap draws under H0 (blocks of 336 hours); p < 0.05 = rejects.

**Impulse responses:** one-s.d. orthogonalised (Cholesky) shocks, 48 hours; 95% band from 1000 block wild bootstrap draws (blocks of 336 hours). Figures irf_<zone>.png; every response in impulse_responses.csv.

## Models

| zone | system | variables (Cholesky order) | p | T | regressors per equation | R² | residual correlation | 1 s.d. shock |
|---|---|---|---|---|---|---|---|---|
| DK1 | x_da_id_spread | c_wind_total_err, c_load_err, x_da_id_spread | 25 | 8404 | 119 | 0.91, 0.77, 0.66 | Wind forecast error / Demand forecast error +0.07, Wind forecast error / DA-ID spread -0.01, Demand forecast error / DA-ID spread +0.01 | Wind forecast error 147 MW, Demand forecast error 86.6 MW, DA-ID spread 10.5 EUR/MWh |
| DK1 | x_id_bal_spread | c_wind_total_err, c_load_err, x_id_bal_spread | 25 | 8404 | 119 | 0.91, 0.77, 0.06 | Wind forecast error / Demand forecast error +0.06, Wind forecast error / ID-BAL spread -0.10, Demand forecast error / ID-BAL spread -0.08 | Wind forecast error 147 MW, Demand forecast error 86.3 MW, ID-BAL spread 143 EUR/MWh |
| DK1 | x_da_bal_spread | c_wind_total_err, c_load_err, x_da_bal_spread | 25 | 8404 | 119 | 0.91, 0.77, 0.07 | Wind forecast error / Demand forecast error +0.06, Wind forecast error / DA-BAL spread -0.10, Demand forecast error / DA-BAL spread -0.08 | Wind forecast error 147 MW, Demand forecast error 86.3 MW, DA-BAL spread 144 EUR/MWh |
| DK2 | x_da_id_spread | c_wind_total_err, c_load_err, x_da_id_spread | 25 | 8404 | 117 | 0.82, 0.85, 0.62 | Wind forecast error / Demand forecast error +0.04, Wind forecast error / DA-ID spread -0.04, Demand forecast error / DA-ID spread +0.04 | Wind forecast error 74.6 MW, Demand forecast error 56.6 MW, DA-ID spread 12.3 EUR/MWh |
| DK2 | x_id_bal_spread | c_wind_total_err, c_load_err, x_id_bal_spread | 25 | 8404 | 117 | 0.82, 0.85, 0.14 | Wind forecast error / Demand forecast error +0.03, Wind forecast error / ID-BAL spread -0.13, Demand forecast error / ID-BAL spread -0.06 | Wind forecast error 74.5 MW, Demand forecast error 56.5 MW, ID-BAL spread 149 EUR/MWh |
| DK2 | x_da_bal_spread | c_wind_total_err, c_load_err, x_da_bal_spread | 25 | 8404 | 117 | 0.82, 0.85, 0.15 | Wind forecast error / Demand forecast error +0.04, Wind forecast error / DA-BAL spread -0.13, Demand forecast error / DA-BAL spread -0.06 | Wind forecast error 74.5 MW, Demand forecast error 56.5 MW, DA-BAL spread 149 EUR/MWh |

## Robustness structures

Each model is refitted with these lag structures; the Granger tests are repeated (all lags of the cause) and the responses recomputed.

| zone | system | chosen | BIC order | HQ order | literature | weekly lags |
|---|---|---|---|---|---|---|
| DK1 | x_da_id_spread | lags 1-25 | lags 1-2 | lags 1-3 | lags 1-24, 48 | lags 1-25, 167-169, 335-337 |
| DK1 | x_id_bal_spread | lags 1-25 | lags 1-2 | lags 1-3 | lags 1-24, 48 | lags 1-25, 167-169, 335-337 |
| DK1 | x_da_bal_spread | lags 1-25 | lags 1-2 | lags 1-3 | lags 1-24, 48 | lags 1-25, 167-169, 335-337 |
| DK2 | x_da_id_spread | lags 1-25 | lags 1-2 | lags 1-2 | lags 1-24, 48 | lags 1-25, 167-169, 335-337 |
| DK2 | x_id_bal_spread | lags 1-25 | lags 1-2 | lags 1-2 | lags 1-24, 48 | lags 1-25, 167-169, 335-337 |
| DK2 | x_da_bal_spread | lags 1-25 | lags 1-2 | lags 1-2 | lags 1-24, 48 | lags 1-25, 167-169, 335-337 |

## Granger causality

p = the chosen model; 'p, <structure>' = the same test in a robustness model; 'decision differs in' = the structures where p < 0.05 does not agree with the chosen model.

| zone | system | cause | effect | W | df | p | rejects | p, BIC order | p, HQ order | p, literature | p, weekly lags | decision differs in |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| DK1 | x_da_id_spread | Demand forecast error | Wind forecast error | 31.2 | 25 | 0.3626 | no | 0.3267 | 0.1159 | 0.4146 | 0.4116 | - |
| DK1 | x_da_id_spread | DA-ID spread | Wind forecast error | 37.3 | 25 | 0.1479 | no | 0.3976 | 0.1499 | 0.2567 | 0.1708 | - |
| DK1 | x_da_id_spread | Wind forecast error | Demand forecast error | 68.8 | 25 | 0.0010 | yes | 0.0320 | 0.0110 | 0.0010 | 0.0010 | - |
| DK1 | x_da_id_spread | DA-ID spread | Demand forecast error | 23.2 | 25 | 0.4595 | no | 0.5564 | 0.5794 | 0.3317 | 0.1099 | - |
| DK1 | x_da_id_spread | Wind forecast error | DA-ID spread | 25.4 | 25 | 0.5604 | no | 0.6673 | 0.6863 | 0.8891 | 0.6703 | - |
| DK1 | x_da_id_spread | Demand forecast error | DA-ID spread | 34.2 | 25 | 0.0899 | no | 0.0200 | 0.0150 | 0.0989 | 0.2987 | BIC order, HQ order |
| DK1 | x_id_bal_spread | Demand forecast error | Wind forecast error | 29.8 | 25 | 0.4436 | no | 0.3736 | 0.1489 | 0.5265 | 0.3766 | - |
| DK1 | x_id_bal_spread | ID-BAL spread | Wind forecast error | 37.7 | 25 | 0.0789 | no | 0.0020 | 0.0190 | 0.0470 | 0.0649 | BIC order, HQ order, literature |
| DK1 | x_id_bal_spread | Wind forecast error | Demand forecast error | 69.7 | 25 | 0.0010 | yes | 0.0280 | 0.0240 | 0.0010 | 0.0010 | - |
| DK1 | x_id_bal_spread | ID-BAL spread | Demand forecast error | 63.9 | 25 | 0.0010 | yes | 0.0010 | 0.0010 | 0.0010 | 0.0030 | - |
| DK1 | x_id_bal_spread | Wind forecast error | ID-BAL spread | 41.8 | 25 | 0.0230 | yes | 0.0010 | 0.0010 | 0.0140 | 0.2208 | weekly lags |
| DK1 | x_id_bal_spread | Demand forecast error | ID-BAL spread | 37.0 | 25 | 0.1279 | no | 0.3097 | 0.0260 | 0.1169 | 0.2308 | HQ order |
| DK1 | x_da_bal_spread | Demand forecast error | Wind forecast error | 29.8 | 25 | 0.4346 | no | 0.3407 | 0.1339 | 0.5275 | 0.3796 | - |
| DK1 | x_da_bal_spread | DA-BAL spread | Wind forecast error | 37.1 | 25 | 0.0799 | no | 0.0030 | 0.0250 | 0.0480 | 0.1049 | BIC order, HQ order, literature |
| DK1 | x_da_bal_spread | Wind forecast error | Demand forecast error | 69.2 | 25 | 0.0010 | yes | 0.0380 | 0.0320 | 0.0010 | 0.0010 | - |
| DK1 | x_da_bal_spread | DA-BAL spread | Demand forecast error | 62.7 | 25 | 0.0010 | yes | 0.0010 | 0.0010 | 0.0040 | 0.0020 | - |
| DK1 | x_da_bal_spread | Wind forecast error | DA-BAL spread | 42.1 | 25 | 0.0180 | yes | 0.0030 | 0.0010 | 0.0200 | 0.2018 | weekly lags |
| DK1 | x_da_bal_spread | Demand forecast error | DA-BAL spread | 35.0 | 25 | 0.1748 | no | 0.3177 | 0.0400 | 0.1558 | 0.2637 | HQ order |
| DK2 | x_da_id_spread | Demand forecast error | Wind forecast error | 22.7 | 25 | 0.6464 | no | 0.7233 | 0.7233 | 0.7023 | 0.6543 | - |
| DK2 | x_da_id_spread | DA-ID spread | Wind forecast error | 24.0 | 25 | 0.4835 | no | 0.0989 | 0.0989 | 0.3706 | 0.1229 | - |
| DK2 | x_da_id_spread | Wind forecast error | Demand forecast error | 48.9 | 25 | 0.0050 | yes | 0.0020 | 0.0020 | 0.0280 | 0.0200 | - |
| DK2 | x_da_id_spread | DA-ID spread | Demand forecast error | 23.8 | 25 | 0.6703 | no | 0.3127 | 0.3127 | 0.7063 | 0.7612 | - |
| DK2 | x_da_id_spread | Wind forecast error | DA-ID spread | 42.5 | 25 | 0.0100 | yes | 0.0030 | 0.0030 | 0.0080 | 0.0230 | - |
| DK2 | x_da_id_spread | Demand forecast error | DA-ID spread | 25.4 | 25 | 0.3147 | no | 0.7033 | 0.7033 | 0.5325 | 0.2168 | - |
| DK2 | x_id_bal_spread | Demand forecast error | Wind forecast error | 23.6 | 25 | 0.6144 | no | 0.6783 | 0.6783 | 0.6753 | 0.5385 | - |
| DK2 | x_id_bal_spread | ID-BAL spread | Wind forecast error | 34.5 | 25 | 0.3257 | no | 0.2268 | 0.2268 | 0.2927 | 0.2178 | - |
| DK2 | x_id_bal_spread | Wind forecast error | Demand forecast error | 47.8 | 25 | 0.0110 | yes | 0.0010 | 0.0010 | 0.0270 | 0.0300 | - |
| DK2 | x_id_bal_spread | ID-BAL spread | Demand forecast error | 52.4 | 25 | 0.0100 | yes | 0.0010 | 0.0010 | 0.0040 | 0.0030 | - |
| DK2 | x_id_bal_spread | Wind forecast error | ID-BAL spread | 27.9 | 25 | 0.4086 | no | 0.4446 | 0.4446 | 0.4346 | 0.5634 | - |
| DK2 | x_id_bal_spread | Demand forecast error | ID-BAL spread | 31.8 | 25 | 0.0979 | no | 0.1988 | 0.1988 | 0.0859 | 0.0140 | weekly lags |
| DK2 | x_da_bal_spread | Demand forecast error | Wind forecast error | 23.7 | 25 | 0.6064 | no | 0.6573 | 0.6573 | 0.6464 | 0.5564 | - |
| DK2 | x_da_bal_spread | DA-BAL spread | Wind forecast error | 31.4 | 25 | 0.4595 | no | 0.2647 | 0.2647 | 0.4246 | 0.3237 | - |
| DK2 | x_da_bal_spread | Wind forecast error | Demand forecast error | 47.7 | 25 | 0.0100 | yes | 0.0010 | 0.0010 | 0.0310 | 0.0260 | - |
| DK2 | x_da_bal_spread | DA-BAL spread | Demand forecast error | 50.7 | 25 | 0.0210 | yes | 0.0010 | 0.0010 | 0.0050 | 0.0110 | - |
| DK2 | x_da_bal_spread | Wind forecast error | DA-BAL spread | 30.8 | 25 | 0.2507 | no | 0.2068 | 0.2068 | 0.2877 | 0.3976 | - |
| DK2 | x_da_bal_spread | Demand forecast error | DA-BAL spread | 32.2 | 25 | 0.1009 | no | 0.1079 | 0.1079 | 0.0759 | 0.0190 | weekly lags |

## Robustness: impulse responses

Hours (of 49) in which the response of a robustness model lies inside the 95% band of the chosen model.

| zone | system | response | shock | BIC order | HQ order | literature | weekly lags |
|---|---|---|---|---|---|---|---|
| DK1 | x_da_id_spread | DA-ID spread | Wind forecast error | 48 of 49 | 47 of 49 | 49 of 49 | 49 of 49 |
| DK1 | x_da_id_spread | DA-ID spread | Demand forecast error | 49 of 49 | 49 of 49 | 49 of 49 | 49 of 49 |
| DK1 | x_da_id_spread | DA-ID spread | DA-ID spread | 35 of 49 | 36 of 49 | 44 of 49 | 49 of 49 |
| DK1 | x_id_bal_spread | ID-BAL spread | Wind forecast error | 48 of 49 | 48 of 49 | 48 of 49 | 49 of 49 |
| DK1 | x_id_bal_spread | ID-BAL spread | Demand forecast error | 49 of 49 | 48 of 49 | 48 of 49 | 49 of 49 |
| DK1 | x_id_bal_spread | ID-BAL spread | ID-BAL spread | 47 of 49 | 47 of 49 | 49 of 49 | 49 of 49 |
| DK1 | x_da_bal_spread | DA-BAL spread | Wind forecast error | 47 of 49 | 48 of 49 | 49 of 49 | 49 of 49 |
| DK1 | x_da_bal_spread | DA-BAL spread | Demand forecast error | 48 of 49 | 48 of 49 | 49 of 49 | 49 of 49 |
| DK1 | x_da_bal_spread | DA-BAL spread | DA-BAL spread | 48 of 49 | 48 of 49 | 49 of 49 | 49 of 49 |
| DK2 | x_da_id_spread | DA-ID spread | Wind forecast error | 45 of 49 | 45 of 49 | 48 of 49 | 49 of 49 |
| DK2 | x_da_id_spread | DA-ID spread | Demand forecast error | 48 of 49 | 48 of 49 | 49 of 49 | 49 of 49 |
| DK2 | x_da_id_spread | DA-ID spread | DA-ID spread | 32 of 49 | 32 of 49 | 33 of 49 | 49 of 49 |
| DK2 | x_id_bal_spread | ID-BAL spread | Wind forecast error | 44 of 49 | 44 of 49 | 48 of 49 | 49 of 49 |
| DK2 | x_id_bal_spread | ID-BAL spread | Demand forecast error | 48 of 49 | 48 of 49 | 49 of 49 | 49 of 49 |
| DK2 | x_id_bal_spread | ID-BAL spread | ID-BAL spread | 45 of 49 | 45 of 49 | 48 of 49 | 49 of 49 |
| DK2 | x_da_bal_spread | DA-BAL spread | Wind forecast error | 43 of 49 | 43 of 49 | 49 of 49 | 49 of 49 |
| DK2 | x_da_bal_spread | DA-BAL spread | Demand forecast error | 48 of 49 | 48 of 49 | 48 of 49 | 49 of 49 |
| DK2 | x_da_bal_spread | DA-BAL spread | DA-BAL spread | 47 of 49 | 47 of 49 | 48 of 49 | 49 of 49 |

## Robustness: Cholesky order

The chosen model with other Cholesky orders: the same-hour response of the spread (hour 0), the response one hour later with the 95% band of each order (from the same bootstrap draws), and the hours (of 49) in which the response lies inside the band of the chosen order.

| zone | system | response | shock | same hour, chosen | hour 1, chosen | same hour, spread first | hour 1, spread first | inside the band, spread first |
|---|---|---|---|---|---|---|---|---|
| DK1 | x_da_id_spread | DA-ID spread | Wind forecast error | -0.09 | +0.20 [-0.33, +0.76] | 0.0 | +0.27 [-0.13, +0.71] | 49 of 49 |
| DK1 | x_da_id_spread | DA-ID spread | Demand forecast error | 0.1 | +0.22 [-0.03, +0.48] | 0.0 | +0.14 [-0.02, +0.29] | 49 of 49 |
| DK1 | x_da_id_spread | DA-ID spread | DA-ID spread | 10.49 | +9.06 [+7.83, +10.20] | 10.49 | +9.06 [+7.83, +10.20] | 49 of 49 |
| DK1 | x_id_bal_spread | ID-BAL spread | Wind forecast error | -14.6 | -11.44 [-15.34, -7.68] | 0.0 | -8.56 [-11.96, -5.11] | 48 of 49 |
| DK1 | x_id_bal_spread | ID-BAL spread | Demand forecast error | -11.27 | +0.62 [-2.43, +3.57] | 0.0 | +2.82 [-0.27, +5.91] | 48 of 49 |
| DK1 | x_id_bal_spread | ID-BAL spread | ID-BAL spread | 143.04 | +28.01 [+17.91, +38.45] | 144.22 | +28.89 [+18.48, +39.60] | 49 of 49 |
| DK1 | x_da_bal_spread | DA-BAL spread | Wind forecast error | -14.75 | -10.84 [-14.75, -7.05] | 0.0 | -7.69 [-11.37, -4.06] | 48 of 49 |
| DK1 | x_da_bal_spread | DA-BAL spread | Demand forecast error | -11.37 | +0.69 [-2.23, +3.70] | 0.0 | +3.09 [+0.19, +6.10] | 48 of 49 |
| DK1 | x_da_bal_spread | DA-BAL spread | DA-BAL spread | 144.15 | +30.63 [+21.06, +40.57] | 145.35 | +31.43 [+21.62, +41.66] | 49 of 49 |
| DK2 | x_da_id_spread | DA-ID spread | Wind forecast error | -0.52 | -0.30 [-0.66, +0.08] | 0.0 | +0.14 [-0.25, +0.58] | 47 of 49 |
| DK2 | x_da_id_spread | DA-ID spread | Demand forecast error | 0.49 | +0.39 [+0.04, +0.72] | 0.0 | -0.02 [-0.27, +0.20] | 47 of 49 |
| DK2 | x_da_id_spread | DA-ID spread | DA-ID spread | 12.31 | +10.42 [+9.19, +11.69] | 12.33 | +10.43 [+9.21, +11.69] | 49 of 49 |
| DK2 | x_id_bal_spread | ID-BAL spread | Wind forecast error | -19.06 | -11.64 [-20.75, -2.30] | 0.0 | -5.20 [-13.64, +3.10] | 48 of 49 |
| DK2 | x_id_bal_spread | ID-BAL spread | Demand forecast error | -8.39 | -0.38 [-3.12, +2.21] | 0.0 | +2.44 [-0.27, +4.95] | 47 of 49 |
| DK2 | x_id_bal_spread | ID-BAL spread | ID-BAL spread | 148.61 | +50.02 [+34.11, +66.53] | 150.06 | +51.03 [+34.76, +67.98] | 49 of 49 |
| DK2 | x_da_bal_spread | DA-BAL spread | Wind forecast error | -19.75 | -11.73 [-20.90, -2.60] | 0.0 | -4.89 [-13.13, +3.58] | 48 of 49 |
| DK2 | x_da_bal_spread | DA-BAL spread | Demand forecast error | -8.04 | -0.17 [-3.09, +2.68] | 0.0 | +2.60 [-0.18, +5.50] | 48 of 49 |
| DK2 | x_da_bal_spread | DA-BAL spread | DA-BAL spread | 149.36 | +51.57 [+36.07, +68.17] | 150.87 | +52.60 [+36.79, +69.63] | 49 of 49 |
