# Residual checks

The VARX(p, 0) with the lag order chosen by the lag_selection step, fitted by least squares on every hour valid for it. p < 0.05 = the test rejects.

**Autocorrelation:** LM(24) tests no residual autocorrelation up to lag 24 (chi²(24 K²)). The robust form is valid also when the residual variance changes over time; the standard form assumes it does not. Size: the largest residual autocorrelation (any pair of variables; 'a on b' = a at t, b at t - lag) within a day and at whole weeks; white noise stays within the band ±1.96/√T.

**Variance:** ARCH-LM(24) per equation tests a constant residual variance (chi²(24)); kurtosis is 3 for normal residuals.

**Stability:** every model is stable (largest eigenvalue modulus of the companion matrix below 1).

## Autocorrelation and stability

| zone | system | p | T | robust LM(24) | robust p | standard LM(24) | standard p | largest autocorr., lags 1-24 | largest autocorr., whole weeks | white-noise band | max eigenvalue modulus |
|---|---|---|---|---|---|---|---|---|---|---|---|
| DK1 | x_da_id_spread | 25 | 8404 | 408.5 | < 0.0001 | 636.6 | < 0.0001 | +0.018 (lag 1, c_wind_total_err on c_wind_total_err) | +0.086 (lag 168, c_load_err on c_load_err) | ±0.021 | 0.9414 |
| DK1 | x_id_bal_spread | 25 | 8404 | 439.9 | < 0.0001 | 743.8 | < 0.0001 | +0.016 (lag 1, c_wind_total_err on c_wind_total_err) | +0.085 (lag 336, c_load_err on c_load_err) | ±0.021 | 0.943 |
| DK1 | x_da_bal_spread | 25 | 8404 | 438.9 | < 0.0001 | 708.7 | < 0.0001 | +0.017 (lag 1, c_wind_total_err on c_wind_total_err) | +0.085 (lag 336, c_load_err on c_load_err) | ±0.021 | 0.943 |
| DK2 | x_da_id_spread | 25 | 8404 | 388.9 | < 0.0001 | 760.6 | < 0.0001 | -0.018 (lag 24, c_load_err on c_load_err) | +0.177 (lag 336, c_load_err on c_load_err) | ±0.021 | 0.9591 |
| DK2 | x_id_bal_spread | 25 | 8404 | 387.1 | < 0.0001 | 746.5 | < 0.0001 | -0.018 (lag 24, c_load_err on c_load_err) | +0.177 (lag 336, c_load_err on c_load_err) | ±0.021 | 0.959 |
| DK2 | x_da_bal_spread | 25 | 8404 | 384.1 | < 0.0001 | 763.9 | < 0.0001 | -0.018 (lag 24, c_load_err on c_load_err) | +0.177 (lag 336, c_load_err on c_load_err) | ±0.021 | 0.959 |

## Variance

| zone | system | equation | ARCH-LM(24) | p | kurtosis |
|---|---|---|---|---|---|
| DK1 | x_da_id_spread | c_wind_total_err | 561.6 | < 0.0001 | 9.5 |
| DK1 | x_da_id_spread | c_load_err | 418.1 | < 0.0001 | 11.3 |
| DK1 | x_da_id_spread | x_da_id_spread | 1287.7 | < 0.0001 | 37.3 |
| DK1 | x_id_bal_spread | c_wind_total_err | 572.3 | < 0.0001 | 9.4 |
| DK1 | x_id_bal_spread | c_load_err | 427.8 | < 0.0001 | 11.3 |
| DK1 | x_id_bal_spread | x_id_bal_spread | 30.2 | 0.1791 | 217.6 |
| DK1 | x_da_bal_spread | c_wind_total_err | 570.9 | < 0.0001 | 9.4 |
| DK1 | x_da_bal_spread | c_load_err | 427.1 | < 0.0001 | 11.4 |
| DK1 | x_da_bal_spread | x_da_bal_spread | 35.2 | 0.0654 | 211.7 |
| DK2 | x_da_id_spread | c_wind_total_err | 517.6 | < 0.0001 | 10.4 |
| DK2 | x_da_id_spread | c_load_err | 873.4 | < 0.0001 | 13.1 |
| DK2 | x_da_id_spread | x_da_id_spread | 1522.9 | < 0.0001 | 26.1 |
| DK2 | x_id_bal_spread | c_wind_total_err | 514.9 | < 0.0001 | 10.4 |
| DK2 | x_id_bal_spread | c_load_err | 878.5 | < 0.0001 | 13.2 |
| DK2 | x_id_bal_spread | x_id_bal_spread | 267.8 | < 0.0001 | 119.0 |
| DK2 | x_da_bal_spread | c_wind_total_err | 515.6 | < 0.0001 | 10.4 |
| DK2 | x_da_bal_spread | c_load_err | 879.5 | < 0.0001 | 13.2 |
| DK2 | x_da_bal_spread | x_da_bal_spread | 269.1 | < 0.0001 | 116.9 |

## Weekly pattern

Each equation's residual autocorrelation at whole weeks, for three models fitted on the same hours: the chosen model (baseline), the chosen model plus lags 167, 168, 169, 335, 336, 337 (weekly lags), and the chosen model with the calendar dummies fe_hour_of_week, fe_month_of_sample (weekly dummies).

| zone | system | equation | 168 h, baseline | 168 h, weekly lags | 168 h, weekly dummies | 336 h, baseline | 336 h, weekly lags | 336 h, weekly dummies |
|---|---|---|---|---|---|---|---|---|
| DK1 | x_da_id_spread | c_wind_total_err | 0.042 | -0.004 | 0.02 | 0.025 | -0.019 | 0.002 |
| DK1 | x_da_id_spread | c_load_err | 0.087 | -0.011 | 0.048 | 0.085 | -0.01 | 0.046 |
| DK1 | x_da_id_spread | x_da_id_spread | 0.025 | 0.004 | 0.004 | 0.005 | -0.0 | -0.016 |
| DK1 | x_id_bal_spread | c_wind_total_err | 0.04 | -0.006 | 0.019 | 0.025 | -0.018 | 0.002 |
| DK1 | x_id_bal_spread | c_load_err | 0.085 | -0.011 | 0.047 | 0.083 | -0.011 | 0.045 |
| DK1 | x_id_bal_spread | x_id_bal_spread | -0.003 | 0.002 | -0.02 | -0.02 | 0.003 | -0.039 |
| DK1 | x_da_bal_spread | c_wind_total_err | 0.04 | -0.006 | 0.018 | 0.025 | -0.018 | 0.003 |
| DK1 | x_da_bal_spread | c_load_err | 0.085 | -0.011 | 0.047 | 0.084 | -0.011 | 0.045 |
| DK1 | x_da_bal_spread | x_da_bal_spread | 0.001 | 0.003 | -0.016 | -0.019 | 0.003 | -0.038 |
| DK2 | x_da_id_spread | c_wind_total_err | 0.033 | 0.004 | 0.006 | 0.03 | 0.001 | 0.003 |
| DK2 | x_da_id_spread | c_load_err | 0.102 | -0.02 | 0.036 | 0.173 | -0.033 | 0.113 |
| DK2 | x_da_id_spread | x_da_id_spread | 0.038 | 0.004 | 0.014 | -0.008 | -0.01 | -0.033 |
| DK2 | x_id_bal_spread | c_wind_total_err | 0.03 | 0.002 | 0.004 | 0.029 | -0.002 | 0.002 |
| DK2 | x_id_bal_spread | c_load_err | 0.104 | -0.021 | 0.038 | 0.174 | -0.034 | 0.114 |
| DK2 | x_id_bal_spread | x_id_bal_spread | -0.036 | -0.002 | -0.051 | -0.014 | -0.002 | -0.028 |
| DK2 | x_da_bal_spread | c_wind_total_err | 0.03 | 0.002 | 0.004 | 0.028 | -0.002 | 0.001 |
| DK2 | x_da_bal_spread | c_load_err | 0.104 | -0.021 | 0.038 | 0.174 | -0.034 | 0.114 |
| DK2 | x_da_bal_spread | x_da_bal_spread | -0.036 | -0.003 | -0.051 | -0.013 | -0.002 | -0.026 |

Baseline, per quarter (Copenhagen local time): the correlation within the quarter's hours.

| zone | system | equation | lag | Q1 | Q2 | Q3 | Q4 |
|---|---|---|---|---|---|---|---|
| DK1 | x_da_id_spread | c_wind_total_err | 168 h | 0.033 | 0.068 | 0.02 | 0.033 |
| DK1 | x_da_id_spread | c_wind_total_err | 336 h | 0.047 | 0.027 | 0.005 | 0.038 |
| DK1 | x_da_id_spread | c_load_err | 168 h | 0.031 | 0.066 | 0.132 | 0.095 |
| DK1 | x_da_id_spread | c_load_err | 336 h | 0.038 | 0.05 | 0.082 | 0.133 |
| DK1 | x_da_id_spread | x_da_id_spread | 168 h | 0.023 | 0.035 | 0.045 | -0.048 |
| DK1 | x_da_id_spread | x_da_id_spread | 336 h | 0.002 | 0.031 | -0.001 | -0.036 |
| DK1 | x_id_bal_spread | c_wind_total_err | 168 h | 0.037 | 0.064 | 0.017 | 0.036 |
| DK1 | x_id_bal_spread | c_wind_total_err | 336 h | 0.047 | 0.03 | 0.0 | 0.04 |
| DK1 | x_id_bal_spread | c_load_err | 168 h | 0.03 | 0.063 | 0.134 | 0.089 |
| DK1 | x_id_bal_spread | c_load_err | 336 h | 0.037 | 0.052 | 0.079 | 0.128 |
| DK1 | x_id_bal_spread | x_id_bal_spread | 168 h | -0.03 | -0.013 | 0.04 | -0.03 |
| DK1 | x_id_bal_spread | x_id_bal_spread | 336 h | -0.024 | -0.043 | 0.001 | -0.008 |
| DK1 | x_da_bal_spread | c_wind_total_err | 168 h | 0.037 | 0.064 | 0.017 | 0.035 |
| DK1 | x_da_bal_spread | c_wind_total_err | 336 h | 0.047 | 0.029 | 0.001 | 0.041 |
| DK1 | x_da_bal_spread | c_load_err | 168 h | 0.03 | 0.063 | 0.134 | 0.089 |
| DK1 | x_da_bal_spread | c_load_err | 336 h | 0.038 | 0.052 | 0.079 | 0.128 |
| DK1 | x_da_bal_spread | x_da_bal_spread | 168 h | -0.028 | -0.003 | 0.043 | -0.036 |
| DK1 | x_da_bal_spread | x_da_bal_spread | 336 h | -0.02 | -0.047 | 0.006 | -0.008 |
| DK2 | x_da_id_spread | c_wind_total_err | 168 h | 0.012 | 0.032 | 0.048 | 0.028 |
| DK2 | x_da_id_spread | c_wind_total_err | 336 h | 0.046 | 0.04 | 0.005 | 0.034 |
| DK2 | x_da_id_spread | c_load_err | 168 h | 0.197 | 0.053 | 0.084 | 0.106 |
| DK2 | x_da_id_spread | c_load_err | 336 h | 0.192 | 0.09 | 0.107 | 0.212 |
| DK2 | x_da_id_spread | x_da_id_spread | 168 h | 0.027 | 0.042 | 0.04 | 0.042 |
| DK2 | x_da_id_spread | x_da_id_spread | 336 h | -0.04 | 0.014 | 0.012 | -0.044 |
| DK2 | x_id_bal_spread | c_wind_total_err | 168 h | 0.007 | 0.028 | 0.051 | 0.021 |
| DK2 | x_id_bal_spread | c_wind_total_err | 336 h | 0.048 | 0.039 | 0.005 | 0.03 |
| DK2 | x_id_bal_spread | c_load_err | 168 h | 0.193 | 0.057 | 0.088 | 0.108 |
| DK2 | x_id_bal_spread | c_load_err | 336 h | 0.198 | 0.088 | 0.107 | 0.213 |
| DK2 | x_id_bal_spread | x_id_bal_spread | 168 h | -0.003 | -0.04 | -0.065 | -0.016 |
| DK2 | x_id_bal_spread | x_id_bal_spread | 336 h | -0.013 | -0.023 | -0.011 | 0.005 |
| DK2 | x_da_bal_spread | c_wind_total_err | 168 h | 0.007 | 0.029 | 0.051 | 0.021 |
| DK2 | x_da_bal_spread | c_wind_total_err | 336 h | 0.047 | 0.039 | 0.005 | 0.03 |
| DK2 | x_da_bal_spread | c_load_err | 168 h | 0.193 | 0.056 | 0.088 | 0.108 |
| DK2 | x_da_bal_spread | c_load_err | 336 h | 0.197 | 0.087 | 0.107 | 0.213 |
| DK2 | x_da_bal_spread | x_da_bal_spread | 168 h | -0.006 | -0.038 | -0.065 | -0.013 |
| DK2 | x_da_bal_spread | x_da_bal_spread | 336 h | -0.01 | -0.027 | -0.002 | -0.006 |

## Ramp timing

Correlation of the hourly change of c_wind_total_err with c_wind_total_actual_mw_change_1 in the same and in the previous hour (ramp_timing.png). In the same hour the two share the actual value, so the points follow a slope of -1.

| zone | r, same hour | r, previous hour |
|---|---|---|
| DK1 | -0.825 | -0.32 |
| DK2 | -0.854 | -0.201 |
