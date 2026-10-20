# Structural breaks — `baseline_2025`

Prices: Day-ahead = `da_price`, Intraday = `id_vwap`, Balancing = `b_imbalance_price`. Period 2025-01-01 to 2025-12-31. Per bidding zone.

**Method.** Daily series (Copenhagen local days). Mean breaks: CUSUM test on the daily mean price. Variance breaks: the same test on the log of the within-day variance. Both are standardised by a HAC long-run variance (Bartlett kernel, Andrews bandwidth), estimated around the candidate break, because prices are autocorrelated. For detection only, the daily series are capped at their 1st/99th percentiles. Multiple breaks are found by seeded binary segmentation (Kovács et al. 2023): about 30 overlapping windows, which also catches changes that later reverse. Significance: a parametric AR(1) bootstrap of the largest statistic over all windows, using the series' own persistence (estimated from first differences, so it is robust to level shifts). The cut-off is α = 0.01 on that adjusted p-value, with at least 30 days between breaks. In simulations this gives about 1 % false alarms at persistence 0 to 0.8. Before/after values are computed on the unmodified hourly prices of the adjacent segments. For variance breaks the typical within-day std is shown too: that is what the test compares. A mean break and a variance break within 14 days of each other are reported as 'Both'.

## Detected breaks

| Market | Zone | Break date | Break type | Before | After | Change | Statistical evidence |
|---|---|---|---|---|---|---|---|
| Day-ahead | DK1 | 2025-03-17 | Variance | var 2,775; within-day std 25.8 | var 2,560; within-day std 40.9 | var x0.92; within-day std x1.59 (tested) | var: CUSUM 3.47, adj. p = 0.0015 |
| Day-ahead | DK1 | 2025-07-05 | Variance | var 2,560; within-day std 40.9 | var 2,402; within-day std 34.0 | var x0.94; within-day std x0.83 (tested) | var: CUSUM 2.78, adj. p = 0.0050 |
| Day-ahead | DK1 | 2025-10-03 | Variance | var 2,402; within-day std 34.0 | var 1,930; within-day std 18.9 | var x0.80; within-day std x0.56 (tested) | var: CUSUM 3.76, adj. p = 0.0005 |
| Day-ahead | DK2 | 2025-07-05 | Variance | var 3,060; within-day std 34.3 | var 2,292; within-day std 35.6 | var x0.75; within-day std x1.04 (tested) | var: CUSUM 2.70, adj. p = 0.0100 |
| Day-ahead | DK2 | 2025-10-03 | Variance | var 2,292; within-day std 35.6 | var 2,279; within-day std 22.4 | var x0.99; within-day std x0.63 (tested) | var: CUSUM 3.22, adj. p = 0.0015 |
| Intraday | DK1 | 2025-03-16 | Variance | var 2,650; within-day std 25.4 | var 2,957; within-day std 40.7 | var x1.12; within-day std x1.60 (tested) | var: CUSUM 3.06, adj. p = 0.0015 |
| Intraday | DK1 | 2025-07-05 | Variance | var 2,957; within-day std 40.7 | var 2,573; within-day std 34.4 | var x0.87; within-day std x0.84 (tested) | var: CUSUM 2.82, adj. p = 0.0015 |
| Intraday | DK1 | 2025-10-04 | Variance | var 2,573; within-day std 34.4 | var 1,777; within-day std 19.8 | var x0.69; within-day std x0.57 (tested) | var: CUSUM 3.42, adj. p = 0.0005 |
| Balancing | DK1 | 2025-03-10 | Variance | var 20,361; within-day std 55.3 | var 31,996; within-day std 107.8 | var x1.57; within-day std x1.95 (tested) | var: CUSUM 4.02, adj. p = 0.0005 |
| Balancing | DK1 | 2025-10-31 | Variance | var 31,996; within-day std 107.8 | var 9,593; within-day std 50.3 | var x0.30; within-day std x0.47 (tested) | var: CUSUM 3.16, adj. p = 0.0005 |
| Balancing | DK2 | 2025-03-13 | Variance | var 13,074; within-day std 60.3 | var 37,487; within-day std 116.6 | var x2.87; within-day std x1.93 (tested) | var: CUSUM 3.69, adj. p = 0.0005 |
| Balancing | DK2 | 2025-11-08 | Variance | var 37,487; within-day std 116.6 | var 9,175; within-day std 62.6 | var x0.24; within-day std x0.54 (tested) | var: CUSUM 2.90, adj. p = 0.0010 |

## Regime classification (statistical)

| Market | Zone | Price column | Mean | Variance | Distinct regimes | Range of regime means | Range of regime variances |
|---|---|---|---|---|---|---|---|
| Day-ahead | DK1 | da_price | relatively stable mean | significant variance shifts (3 breaks) | yes — 1 mean regime(s), 4 variance regime(s) | 81.1 to 81.1 | 1,930 to 2,775 |
| Day-ahead | DK2 | da_price | relatively stable mean | significant variance shifts (2 breaks) | yes — 1 mean regime(s), 3 variance regime(s) | 82.5 to 82.5 | 2,279 to 3,060 |
| Intraday | DK1 | id_vwap | relatively stable mean | significant variance shifts (3 breaks) | yes — 1 mean regime(s), 4 variance regime(s) | 79.7 to 79.7 | 1,777 to 2,957 |
| Intraday | DK2 | id_vwap | relatively stable mean | relatively stable variance | no — one regime over the period | 83.3 to 83.3 | 2,912 to 2,912 |
| Balancing | DK1 | b_imbalance_price | relatively stable mean | significant variance shifts (2 breaks) | yes — 1 mean regime(s), 3 variance regime(s) | 84.6 to 84.6 | 9,593 to 31,996 |
| Balancing | DK2 | b_imbalance_price | relatively stable mean | significant variance shifts (2 breaks) | yes — 1 mean regime(s), 3 variance regime(s) | 82.7 to 82.7 | 9,175 to 37,487 |

## Reading this
- This is **statistical detection only**. A break means the level or volatility differs significantly between segments. It does not say why.
- With a single year of data, mean breaks can reflect seasonality (e.g. low midday solar-driven prices in spring/summer) as much as structural change.
- Candidate explanations to check before interpreting a break economically (not tested here): seasonal fuel and weather patterns; the Nordic mFRR energy-activation market go-live (March 2025), which changed balancing price formation; the day-ahead 15-minute MTU go-live (1 Oct 2025).
- Spikes are genuine market outcomes. No observations were removed and the dataframe is unchanged.
