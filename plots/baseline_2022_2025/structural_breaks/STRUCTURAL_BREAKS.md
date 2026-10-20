# Structural breaks — `baseline_2022_2025`

Prices: Day-ahead = `da_price`, Intraday = `id_vwap`, Balancing = `b_imbalance_price`. Period 2022-01-01 to 2025-12-31. Per bidding zone.

**Method.** Daily series (Copenhagen local days). Mean breaks: CUSUM test on the daily mean price. Variance breaks: the same test on the log of the within-day variance. Both are standardised by a HAC long-run variance (Bartlett kernel, Andrews bandwidth), estimated around the candidate break, because prices are autocorrelated. For detection only, the daily series are capped at their 1st/99th percentiles. Multiple breaks are found by seeded binary segmentation (Kovács et al. 2023): about 30 overlapping windows, which also catches changes that later reverse. Significance: a parametric AR(1) bootstrap of the largest statistic over all windows, using the series' own persistence (estimated from first differences, so it is robust to level shifts). The cut-off is α = 0.01 on that adjusted p-value, with at least 30 days between breaks. In simulations this gives about 1 % false alarms at persistence 0 to 0.8. Before/after values are computed on the unmodified hourly prices of the adjacent segments. For variance breaks the typical within-day std is shown too: that is what the test compares. A mean break and a variance break within 14 days of each other are reported as 'Both'.

## Detected breaks

| Market | Zone | Break date | Break type | Before | After | Change | Statistical evidence |
|---|---|---|---|---|---|---|---|
| Day-ahead | DK1 | 2022-06-18 | Variance | var 7,460; within-day std 36.0 | var 24,639; within-day std 77.0 | var x3.30; within-day std x2.14 (tested) | var: CUSUM 5.56, adj. p = 0.0005 |
| Day-ahead | DK1 | 2022-10-05 | Variance | var 24,639; within-day std 77.0 | var 16,653; within-day std 39.2 | var x0.68; within-day std x0.51 (tested) | var: CUSUM 4.38, adj. p = 0.0005 |
| Day-ahead | DK1 | 2022-12-25 | Variance | var 16,653; within-day std 39.2 | var 2,377; within-day std 24.6 | var x0.14; within-day std x0.63 (tested) | var: CUSUM 4.51, adj. p = 0.0005 |
| Day-ahead | DK1 | 2023-12-15 | Variance | var 2,377; within-day std 24.6 | var 744; within-day std 13.4 | var x0.31; within-day std x0.54 (tested) | var: CUSUM 2.97, adj. p = 0.0045 |
| Day-ahead | DK1 | 2024-04-08 | Variance | var 744; within-day std 13.4 | var 3,218; within-day std 29.0 | var x4.33; within-day std x2.17 (tested) | var: CUSUM 5.91, adj. p = 0.0005 |
| Day-ahead | DK1 | 2025-03-17 | Variance | var 3,218; within-day std 29.0 | var 2,503; within-day std 37.7 | var x0.78; within-day std x1.30 (tested) | var: CUSUM 3.37, adj. p = 0.0005 |
| Day-ahead | DK1 | 2025-10-03 | Variance | var 2,503; within-day std 37.7 | var 1,930; within-day std 18.9 | var x0.77; within-day std x0.50 (tested) | var: CUSUM 3.74, adj. p = 0.0005 |
| Day-ahead | DK2 | 2022-06-18 | Variance | var 9,074; within-day std 41.9 | var 29,519; within-day std 80.6 | var x3.25; within-day std x1.93 (tested) | var: CUSUM 4.38, adj. p = 0.0005 |
| Day-ahead | DK2 | 2022-10-05 | Variance | var 29,519; within-day std 80.6 | var 16,756; within-day std 42.5 | var x0.57; within-day std x0.53 (tested) | var: CUSUM 3.92, adj. p = 0.0005 |
| Day-ahead | DK2 | 2022-12-25 | Variance | var 16,756; within-day std 42.5 | var 2,504; within-day std 25.5 | var x0.15; within-day std x0.60 (tested) | var: CUSUM 5.39, adj. p = 0.0005 |
| Day-ahead | DK2 | 2023-12-15 | Variance | var 2,504; within-day std 25.5 | var 1,171; within-day std 14.8 | var x0.47; within-day std x0.58 (tested) | var: CUSUM 3.04, adj. p = 0.0015 |
| Day-ahead | DK2 | 2024-04-07 | Variance | var 1,171; within-day std 14.8 | var 3,058; within-day std 32.6 | var x2.61; within-day std x2.21 (tested) | var: CUSUM 5.87, adj. p = 0.0005 |
| Day-ahead | DK2 | 2025-10-03 | Variance | var 3,058; within-day std 32.6 | var 2,279; within-day std 22.4 | var x0.75; within-day std x0.69 (tested) | var: CUSUM 3.21, adj. p = 0.0010 |
| Intraday | DK1 | 2022-06-16 | Variance | var 7,414; within-day std 36.7 | var 26,149; within-day std 78.6 | var x3.53; within-day std x2.14 (tested) | var: CUSUM 5.57, adj. p = 0.0005 |
| Intraday | DK1 | 2022-10-05 | Variance | var 26,149; within-day std 78.6 | var 17,919; within-day std 40.0 | var x0.69; within-day std x0.51 (tested) | var: CUSUM 3.43, adj. p = 0.0005 |
| Intraday | DK1 | 2022-12-21 | Variance | var 17,919; within-day std 40.0 | var 2,450; within-day std 22.1 | var x0.14; within-day std x0.55 (tested) | var: CUSUM 3.93, adj. p = 0.0005 |
| Intraday | DK1 | 2024-04-07 | Variance | var 2,450; within-day std 22.1 | var 3,971; within-day std 28.6 | var x1.62; within-day std x1.30 (tested) | var: CUSUM 5.67, adj. p = 0.0005 |
| Intraday | DK1 | 2025-03-16 | Variance | var 3,971; within-day std 28.6 | var 2,807; within-day std 37.8 | var x0.71; within-day std x1.32 (tested) | var: CUSUM 3.05, adj. p = 0.0030 |
| Intraday | DK1 | 2025-10-04 | Variance | var 2,807; within-day std 37.8 | var 1,777; within-day std 19.8 | var x0.63; within-day std x0.52 (tested) | var: CUSUM 3.41, adj. p = 0.0005 |
| Intraday | DK2 | 2022-06-11 | Variance | var 8,688; within-day std 39.8 | var 30,164; within-day std 75.8 | var x3.47; within-day std x1.90 (tested) | var: CUSUM 4.70, adj. p = 0.0005 |
| Intraday | DK2 | 2022-10-15 | Variance | var 30,164; within-day std 75.8 | var 17,007; within-day std 42.8 | var x0.56; within-day std x0.57 (tested) | var: CUSUM 3.60, adj. p = 0.0005 |
| Intraday | DK2 | 2022-12-25 | Variance | var 17,007; within-day std 42.8 | var 2,767; within-day std 27.1 | var x0.16; within-day std x0.63 (tested) | var: CUSUM 4.83, adj. p = 0.0005 |
| Intraday | DK2 | 2023-12-08 | Variance | var 2,767; within-day std 27.1 | var 1,221; within-day std 15.5 | var x0.44; within-day std x0.57 (tested) | var: CUSUM 2.77, adj. p = 0.0090 |
| Intraday | DK2 | 2024-04-07 | Variance | var 1,221; within-day std 15.5 | var 3,531; within-day std 31.3 | var x2.89; within-day std x2.02 (tested) | var: CUSUM 5.05, adj. p = 0.0005 |
| Balancing | DK1 | 2022-02-28 | Variance | var 5,019; within-day std 37.6 | var 12,912; within-day std 67.7 | var x2.57; within-day std x1.80 (tested) | var: CUSUM 3.15, adj. p = 0.0005 |
| Balancing | DK1 | 2022-06-16 | Variance | var 12,912; within-day std 67.7 | var 51,779; within-day std 117.2 | var x4.01; within-day std x1.73 (tested) | var: CUSUM 4.08, adj. p = 0.0005 |
| Balancing | DK1 | 2022-10-22 | Variance | var 51,779; within-day std 117.2 | var 14,672; within-day std 46.3 | var x0.28; within-day std x0.40 (tested) | var: CUSUM 4.58, adj. p = 0.0005 |
| Balancing | DK1 | 2022-12-25 | Mean | mean 214.5 | mean 81.2 | mean -133.3 (-62 %) | mean: CUSUM 3.93, adj. p = 0.0020 |
| Balancing | DK1 | 2023-10-03 | Variance | var 14,672; within-day std 46.3 | var 3,530; within-day std 25.6 | var x0.24; within-day std x0.55 (tested) | var: CUSUM 2.70, adj. p = 0.0050 |
| Balancing | DK1 | 2024-05-03 | Variance | var 3,530; within-day std 25.6 | var 7,397; within-day std 50.7 | var x2.10; within-day std x1.98 (tested) | var: CUSUM 4.72, adj. p = 0.0005 |
| Balancing | DK1 | 2025-02-22 | Variance | var 7,397; within-day std 50.7 | var 34,424; within-day std 106.0 | var x4.65; within-day std x2.09 (tested) | var: CUSUM 4.70, adj. p = 0.0005 |
| Balancing | DK1 | 2025-10-30 | Variance | var 34,424; within-day std 106.0 | var 9,550; within-day std 50.7 | var x0.28; within-day std x0.48 (tested) | var: CUSUM 3.26, adj. p = 0.0005 |
| Balancing | DK2 | 2022-02-28 | Variance | var 6,142; within-day std 44.6 | var 15,319; within-day std 68.7 | var x2.49; within-day std x1.54 (tested) | var: CUSUM 3.04, adj. p = 0.0010 |
| Balancing | DK2 | 2022-06-03 | Variance | var 15,319; within-day std 68.7 | var 42,931; within-day std 115.0 | var x2.80; within-day std x1.67 (tested) | var: CUSUM 3.94, adj. p = 0.0005 |
| Balancing | DK2 | 2022-10-16 | Variance | var 42,931; within-day std 115.0 | var 23,250; within-day std 62.3 | var x0.54; within-day std x0.54 (tested) | var: CUSUM 2.96, adj. p = 0.0020 |
| Balancing | DK2 | 2022-12-25 / 2022-12-20 (var) | Both | mean 209.6; var 23,250; within-day std 62.3 | mean 79.2; var 7,441; within-day std 43.2 | mean -130.4 (-62 %); var x0.32; within-day std x0.69 (tested) | mean: CUSUM 4.11, adj. p = 0.0015; var: CUSUM 4.68, adj. p = 0.0005 |
| Balancing | DK2 | 2023-10-03 | Variance | var 7,441; within-day std 43.2 | var 4,511; within-day std 27.4 | var x0.61; within-day std x0.64 (tested) | var: CUSUM 2.57, adj. p = 0.0095 |
| Balancing | DK2 | 2024-05-03 | Variance | var 4,511; within-day std 27.4 | var 8,151; within-day std 52.0 | var x1.81; within-day std x1.90 (tested) | var: CUSUM 4.61, adj. p = 0.0005 |
| Balancing | DK2 | 2025-01-09 | Variance | var 8,151; within-day std 52.0 | var 32,755; within-day std 104.2 | var x4.02; within-day std x2.00 (tested) | var: CUSUM 5.30, adj. p = 0.0005 |
| Balancing | DK2 | 2025-11-08 | Variance | var 32,755; within-day std 104.2 | var 9,175; within-day std 62.6 | var x0.28; within-day std x0.60 (tested) | var: CUSUM 2.94, adj. p = 0.0020 |

## Regime classification (statistical)

| Market | Zone | Price column | Mean | Variance | Distinct regimes | Range of regime means | Range of regime variances |
|---|---|---|---|---|---|---|---|
| Day-ahead | DK1 | da_price | relatively stable mean | significant variance shifts (7 breaks) | yes — 1 mean regime(s), 8 variance regime(s) | 114.4 to 114.4 | 744 to 24,639 |
| Day-ahead | DK2 | da_price | relatively stable mean | significant variance shifts (6 breaks) | yes — 1 mean regime(s), 7 variance regime(s) | 111.2 to 111.2 | 1,171 to 29,519 |
| Intraday | DK1 | id_vwap | relatively stable mean | significant variance shifts (6 breaks) | yes — 1 mean regime(s), 7 variance regime(s) | 112.0 to 112.0 | 1,777 to 26,149 |
| Intraday | DK2 | id_vwap | relatively stable mean | significant variance shifts (5 breaks) | yes — 1 mean regime(s), 6 variance regime(s) | 111.2 to 111.2 | 1,221 to 30,164 |
| Balancing | DK1 | b_imbalance_price | significant mean shifts (1 break) | significant variance shifts (7 breaks) | yes — 2 mean regime(s), 8 variance regime(s) | 81.2 to 214.5 | 3,530 to 51,779 |
| Balancing | DK2 | b_imbalance_price | significant mean shifts (1 break) | significant variance shifts (8 breaks) | yes — 2 mean regime(s), 9 variance regime(s) | 79.2 to 209.6 | 4,511 to 42,931 |

## Reading this
- This is **statistical detection only**. A break means the level or volatility differs significantly between segments. It does not say why.
- With a single year of data, mean breaks can reflect seasonality (e.g. low midday solar-driven prices in spring/summer) as much as structural change.
- Candidate explanations to check before interpreting a break economically (not tested here): seasonal fuel and weather patterns; the Nordic mFRR energy-activation market go-live (March 2025), which changed balancing price formation; the day-ahead 15-minute MTU go-live (1 Oct 2025).
- Spikes are genuine market outcomes. No observations were removed and the dataframe is unchanged.
