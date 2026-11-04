# What the forecast errors do to the price spreads

Step 2 of the hypothesis, first look. A large error is |e| above its 95th percentile (as in step 1); over-forecast: e > 0 (e.g. less wind than planned), under-forecast: e < 0. The mean spread in those hours against its mean in all hours.

| Zone | Forecast error | Spread | Mean in large over-forecast hours (EUR/MWh) | Mean in large under-forecast hours (EUR/MWh) | Mean in all hours hours (EUR/MWh) | Large over-forecast hours | Large under-forecast hours |
|---|---|---|---|---|---|---|---|
| DK1 | Wind forecast error | DA-ID spread | +0.3 | +3.7 | +1.6 | 6 | 426 |
| DK1 | Wind forecast error | ID-BAL spread | +47.4 | +11.7 | -5.0 | 6 | 426 |
| DK1 | Wind forecast error | DA-BAL spread | +47.7 | +15.4 | -3.4 | 6 | 426 |
| DK1 | Demand forecast error | DA-ID spread | -0.9 | +1.0 | +1.5 | 209 | 229 |
| DK1 | Demand forecast error | ID-BAL spread | -9.7 | +5.7 | -5.0 | 209 | 229 |
| DK1 | Demand forecast error | DA-BAL spread | -10.5 | +6.7 | -3.5 | 209 | 229 |
| DK2 | Wind forecast error | DA-ID spread | -2.4 | +11.6 | -0.5 | 365 | 67 |
| DK2 | Wind forecast error | ID-BAL spread | -19.6 | +59.2 | -0.0 | 365 | 67 |
| DK2 | Wind forecast error | DA-BAL spread | -22.0 | +70.8 | -0.5 | 365 | 67 |
| DK2 | Demand forecast error | DA-ID spread | +0.9 | -3.8 | -0.8 | 174 | 264 |
| DK2 | Demand forecast error | ID-BAL spread | +16.4 | +10.0 | +0.6 | 174 | 264 |
| DK2 | Demand forecast error | DA-BAL spread | +17.2 | +6.2 | -0.2 | 174 | 264 |

## Lags: when, and how much

Plain spreads (EUR/MWh); 95 % block-bootstrap intervals (blocks of 336 h, 1000 draws, seed 2025). **Around a large error**: the mean spread h hours after the first hour of each run of large errors of one sign (around.csv, h from the first to the last lag, with the intervals).

| Zone | Forecast error | Spread | Runs of large | h = -1 | h = +0 | h = +1 | h = +2 | h = +3 | h = +6 |
|---|---|---|---|---|---|---|---|---|---|
| DK1 | Wind forecast error | DA-ID spread | over-forecasts (4) | -1 | +1 | +2 | -0 | -1 | -5 |
| DK1 | Wind forecast error | DA-ID spread | under-forecasts (124) | +3 | +2 | +2 | +2 | +2 | +4 |
| DK1 | Wind forecast error | ID-BAL spread | over-forecasts (4) | -15 | +86 | -17 | +1 | +49 | -144 |
| DK1 | Wind forecast error | ID-BAL spread | under-forecasts (124) | -7 | +18 | +13 | -11 | -12 | -9 |
| DK1 | Wind forecast error | DA-BAL spread | over-forecasts (4) | -16 | +87 | -16 | +1 | +49 | -149 |
| DK1 | Wind forecast error | DA-BAL spread | under-forecasts (124) | -3 | +20 | +15 | -9 | -10 | -5 |
| DK1 | Demand forecast error | DA-ID spread | over-forecasts (73) | -2 | -1 | -2 | -4 | -4 | +2 |
| DK1 | Demand forecast error | DA-ID spread | under-forecasts (67) | +1 | +0 | -0 | +2 | +1 | +4 |
| DK1 | Demand forecast error | ID-BAL spread | over-forecasts (73) | -4 | -82 | -4 | +21 | +24 | -13 |
| DK1 | Demand forecast error | ID-BAL spread | under-forecasts (67) | -29 | -4 | -4 | +8 | +3 | -7 |
| DK1 | Demand forecast error | DA-BAL spread | over-forecasts (73) | -5 | -83 | -7 | +17 | +19 | -11 |
| DK1 | Demand forecast error | DA-BAL spread | under-forecasts (67) | -28 | -4 | -4 | +10 | +3 | -3 |
| DK2 | Wind forecast error | DA-ID spread | over-forecasts (85) | -4 | -4 | -4 | -1 | -4 | -4 |
| DK2 | Wind forecast error | DA-ID spread | under-forecasts (34) | +5 | +9 | +11 | +11 | +8 | -0 |
| DK2 | Wind forecast error | ID-BAL spread | over-forecasts (85) | -38 | -86 | -41 | +6 | +29 | +30 |
| DK2 | Wind forecast error | ID-BAL spread | under-forecasts (34) | +54 | +37 | +74 | +48 | +19 | +46 |
| DK2 | Wind forecast error | DA-BAL spread | over-forecasts (85) | -42 | -90 | -45 | +5 | +25 | +26 |
| DK2 | Wind forecast error | DA-BAL spread | under-forecasts (34) | +59 | +46 | +85 | +59 | +27 | +46 |
| DK2 | Demand forecast error | DA-ID spread | over-forecasts (58) | -0 | +1 | +1 | -0 | +2 | -2 |
| DK2 | Demand forecast error | DA-ID spread | under-forecasts (69) | -1 | -2 | -2 | -2 | -2 | -5 |
| DK2 | Demand forecast error | ID-BAL spread | over-forecasts (58) | +6 | +12 | +18 | +18 | +4 | +10 |
| DK2 | Demand forecast error | ID-BAL spread | under-forecasts (69) | -14 | +3 | +13 | +11 | +25 | +5 |
| DK2 | Demand forecast error | DA-BAL spread | over-forecasts (58) | +6 | +13 | +20 | +17 | +6 | +8 |
| DK2 | Demand forecast error | DA-BAL spread | under-forecasts (69) | -15 | +1 | +11 | +9 | +24 | +0 |

**Correlation by lag**: r_k = corr(e_t, s_t+k) (correlation.csv, every lag). No interval: errors and spreads persist, so the band for independent hours would be too narrow.

| Zone | Forecast error | Spread | r at lag 0 | Strongest lag (h) | r there |
|---|---|---|---|---|---|
| DK1 | Wind forecast error | DA-ID spread | -0.07 | -3 | -0.07 |
| DK1 | Wind forecast error | ID-BAL spread | -0.04 | 0 | -0.04 |
| DK1 | Wind forecast error | DA-BAL spread | -0.05 | 0 | -0.05 |
| DK2 | Wind forecast error | DA-ID spread | -0.11 | 1 | -0.11 |
| DK2 | Wind forecast error | ID-BAL spread | -0.10 | 0 | -0.10 |
| DK2 | Wind forecast error | DA-BAL spread | -0.12 | 0 | -0.12 |
| DK1 | Demand forecast error | DA-ID spread | -0.00 | 48 | +0.03 |
| DK1 | Demand forecast error | ID-BAL spread | -0.03 | -17 | +0.03 |
| DK1 | Demand forecast error | DA-BAL spread | -0.03 | -17 | +0.03 |
| DK2 | Demand forecast error | DA-ID spread | +0.02 | -15 | +0.03 |
| DK2 | Demand forecast error | ID-BAL spread | -0.01 | 19 | -0.02 |
| DK2 | Demand forecast error | DA-BAL spread | -0.01 | 7 | +0.02 |

**Tenths**: the error in ten equal groups by value, and the mean spread in the same hour (tenths.csv: also later hours, with the intervals). The first and the last tenth:

| Zone | Forecast error | Spread | 1st tenth: mean error (MW) | mean spread | 10th tenth: mean error (MW) | mean spread  |
|---|---|---|---|---|---|---|
| DK1 | Wind forecast error | DA-ID spread | -1220 | +3.4 | +423 | +0.2 |
| DK1 | Wind forecast error | ID-BAL spread | -1220 | +7.0 | +423 | -16.6 |
| DK1 | Wind forecast error | DA-BAL spread | -1220 | +10.4 | +423 | -16.4 |
| DK1 | Demand forecast error | DA-ID spread | -333 | +1.3 | +329 | +0.8 |
| DK1 | Demand forecast error | ID-BAL spread | -333 | -2.7 | +329 | -13.7 |
| DK1 | Demand forecast error | DA-BAL spread | -333 | -1.4 | +329 | -12.9 |
| DK2 | Wind forecast error | DA-ID spread | -249 | +5.1 | +386 | -3.1 |
| DK2 | Wind forecast error | ID-BAL spread | -249 | +30.9 | +386 | -35.9 |
| DK2 | Wind forecast error | DA-BAL spread | -249 | +35.9 | +386 | -38.9 |
| DK2 | Demand forecast error | DA-ID spread | -301 | -2.5 | +234 | -1.0 |
| DK2 | Demand forecast error | ID-BAL spread | -301 | +6.7 | +234 | -6.5 |
| DK2 | Demand forecast error | DA-BAL spread | -301 | +4.1 | +234 | -7.5 |
