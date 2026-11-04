# Forecast errors

Step 1 of the hypothesis: what the forecast errors look like. Descriptive only. e_t = forecast − actual (positive = over-forecast). Normalised: as a % of the average hour of the variable itself (wind produced, electricity consumed), its total over the period divided by the hours, so zones of different size can be compared. A run is a stretch of consecutive hours in which the error keeps its sign; the run length of a typical hour is the median, over the hours, of the length of the run the hour belongs to. Monthly and hourly patterns: hour_month.csv; run lengths: runs.csv; large errors per month: large_by_month.csv.

| Zone | Forecast error | Total of the variable (TWh) | Average hour (MW) | Typical size, median abs. error (MW) | Typical size (% of the average hour) | Mean error (% of the average hour) | Large: abs. error above (MW, 95th pct.) | Largest over / under (MW) | Over-forecast hours | Mean error (MW) | Correlation with the actual value | Same sign as the hour before | Run length of a typical hour (h) | Longest run (h) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| DK1 | Wind forecast error | 14.61 | 1669 | 284 | 17.0 % | -17.1 % | 1189 | +1324 / -1855 | 33 % | -285 | -0.82 | 91 % | 20 | 152 |
| DK2 | Wind forecast error | 4.64 | 530 | 104 | 19.7 % | +8.0 % | 353 | +905 / -796 | 63 % | +42 | -0.52 | 88 % | 18 | 135 |
| DK1 | Demand forecast error | 23.65 | 2702 | 85 | 3.1 % | -0.3 % | 384 | +987 / -874 | 46 % | -8 | -0.34 | 79 % | 8 | 45 |
| DK2 | Demand forecast error | 14.78 | 1689 | 68 | 4.0 % | -1.5 % | 312 | +721 / -740 | 41 % | -26 | -0.31 | 83 % | 11 | 63 |

## Mean error by day-ahead price

Mean error (MW) in equal groups of hours sorted by the day-ahead price, 1 = the cheapest hours.

| zone | error | 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|---|
| DK1 | Demand forecast error | -46 | -14 | +2 | +19 | +1 |
| DK1 | Wind forecast error | -219 | -581 | -286 | -201 | -139 |
| DK2 | Demand forecast error | -70 | -40 | -17 | +9 | -9 |
| DK2 | Wind forecast error | +128 | -30 | +29 | +37 | +47 |
