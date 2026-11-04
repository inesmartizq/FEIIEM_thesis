"""
flags.py — notes shown on the dashboard as coloured, numbered circles; hovering one shows its text.

Written from Thesis Control Report 1 (2026-11-02, baseline_2025). The numbers in the texts are fixed
text: they do not update when the data change.

POINTS        what the first estimation taught (a green "learning" circle) and the question it raises
              (a blue "question" circle at the same place; all questions are also listed on the
              "Questions and next steps" page)
LIMITATIONS   the limitations of the data and the model (yellow circles)

at: where the circles go: [selector, enclosing element to mark or None] pairs; the same note can sit in
several places. The elements must be static (not re-rendered), so the circles stay.
"""

POINTS = [
    {
        "title": "The spreads",
        "learning": "In 2025 the DA-BAL spread is almost the ID-BAL spread (correlation 0.99). The ID-BAL spread "
                    "varies about eight times more than the DA-ID spread, so DA-BAL, their sum, is driven almost "
                    "entirely by its balancing part, and the scarcity of balancing resources cannot be told apart "
                    "from the incentive to close an imbalance. Spodniak et al. (2021) met the same in a weaker form "
                    "and report only DA-ID and ID-RP.",
        "question": "Should we drop the separate DA-BAL models and instead estimate one model per zone with both "
                    "steps, DA-ID and ID-BAL, so that the full-path response is their sum?",
        "at": [["#results-answer h2", None]],
    },
    {
        "title": "Extreme hours",
        "learning": "Since March 2025 the balancing price reaches extreme values far more often than in the periods "
                    "studied by Spodniak et al. and Nieminen, so neither a fixed price window nor a short list of "
                    "known events fits 2025 directly. The window of Spodniak et al. (2021), −150 to 400 EUR/MWh, "
                    "would remove 3.5 % of all hours. Checking the 110 hours above 800 or below −900 EUR/MWh (60 in "
                    "DK1, 50 in DK2) against recorded outages and market incidents would show how many are events "
                    "rather than normal market behaviour.",
        "question": "How should the extreme balancing prices enter the model: as they are, removed with the fixed "
                    "window of Spodniak et al., or capped at a high percentile, so that a few hours cannot dominate "
                    "the least-squares estimates?",
        "at": [["#tests-variance", None]],
    },
    {
        "title": "The ordering",
        "learning": "The same-hour results, and in DK2 the wind effect one hour later, rest on the Cholesky ordering. "
                    "It is easy to defend for the wind error but less so for the demand error, since total load may "
                    "include consumption that reacts to prices. Ordering the demand error after the spread, or "
                    "splitting the forecast error by when the market learns it, would make the same-hour effect "
                    "depend less on this choice.",
        "question": "Which ordering should carry the main results: ours (wind error, demand error, spread), the "
                    "spread first as in the reference studies, or the demand error after the spread (wind error, "
                    "spread, demand error), which lets consumption react to prices within the hour? The other two "
                    "would then serve as checks.",
        "at": [["#answer-irf", ".card"]],
    },
    {
        "title": "The demand error",
        "learning": "The demand error is not a clean forecast surprise: actual demand is computed total load and may "
                    "include consumption that reacts to prices. It also keeps a weekly pattern that the 25 lags miss, "
                    "and adding lags at one and two weeks changes two Granger decisions.",
        "question": "Should the main model include the lags at one and two weeks, even though they lie outside the "
                    "contiguous lag orders that AIC compares? Or just take it as it is?",
        "at": [["#tests-weekly", None]],
    },
    {
        "title": "The wind error",
        "learning": "In DK1 the day-ahead wind forecast is on average 17 % below actual production, and the error "
                    "correlates −0.82 with production, so a large DK1 error is mostly a windy hour. Keeping only the "
                    "part of the error that the forecast cannot predict would separate the surprise from this bias.",
        "question": "Should the DK1 wind forecast be corrected for its bias before the error is computed, as "
                    "Spodniak et al. (2021) do for Finland with a 30-day rolling regression of actual on forecast "
                    "production, so that the error measures surprises rather than the bias?",
        "at": [["#results-irf h2", None]],
    },
    {
        "title": "The wind ramp",
        "learning": "The actual ramp of the previous hour brings part of the wind error's past back into the model, so "
                    "the Granger test may understate a delayed wind effect. The forecast ramp, known the day before, "
                    "measures the expected change in output without containing actual production, and could "
                    "replace it.",
        "question": "Should the forecast ramp of the same hour replace the actual ramp of the previous hour as the "
                    "ramping control?",
        "at": [["#tests-ramp", None]],
    },
    {
        "title": "The market redesigns",
        "learning": "The balancing price changed character after the mFRR energy activation market started in March "
                    "2025. Estimating the model before and after the redesign, and with the 15-minute balancing "
                    "price, would show whether the effects changed with the new market.",
        "question": "Should the sample be split at March 2025, even though only two months come before the redesign, "
                    "or should a single model allow the links to change after March?",
        "at": [["#results-h", ".intro"]],
    },
    {
        "title": "The intraday price",
        "learning": "The full-session intraday price may dilute the link with the forecast errors, since many trades "
                    "happen long before delivery. The price of the last three hours of trading (VWAP3H) is a natural "
                    "robustness check.",
        "question": "Should we switch to VWAP3H or VWAP1H? Should we model the auctions instead (since we now have "
                    "the auction data)? The previous studies do not do it with the auctions.",
        "at": [["#data-h", ".intro"]],
    },
    {
        "title": "The daily profile",
        "learning": "The model assumes the same daily profile in every month. Checking the model residuals for a "
                    "daily profile that changes with the season would show whether this assumption matters.",
        "question": "What do you think about the dummies and their application? Would you change the process of "
                    "figure them out? Do you think they are well applied dummies?",
        "at": [["img[data-math='dummies']", "figure"]],
    },
    {
        "title": "Linearity",
        "learning": "A linear model shows where the effect lies but cannot size it for large errors or extreme "
                    "spreads. The generalized additive model and quantile regression are designed for this.",
        "question": "Should the next stage first correct the VARX along the points above, or move on to the "
                    "generalized additive model and quantile regression with the current specification?",
        "at": [["img[data-math='varx']", "figure"]],
    },
]

LIMITATIONS = [
    {
        "title": "Linearity",
        "text": "The VARX is linear and symmetric: a surprise of 1,000 MW has ten times the effect of one of 100 MW, "
                "and a shortfall mirrors an equal surplus. Balancing prices probably do not behave this way, since "
                "bids are activated in price order, so large imbalances reach expensive bids, and up- and "
                "down-regulation are priced separately.",
        "at": [["img[data-math='varx']", "figure"]],
    },
    {
        "title": "Constant coefficients",
        "text": "One set of coefficients covers a year with two market redesigns, the mFRR energy activation market "
                "in March and 15-minute day-ahead products in October. The month dummies shift the level of each "
                "series, not the strength of the links between them.",
        "at": [["#results-h", ".intro"]],
    },
    {
        "title": "Changing variance",
        "text": "The bootstrap allows the residual variance to change, but the one-standard-deviation shocks are "
                "averages over the year. The demand error changes most: its standard deviation jumps on 5 March 2025 "
                "in both zones, the day after the mFRR energy activation market started, and rises again in "
                "November and December. Neither the forecast nor the actual demand becomes more variable; they agree "
                "less. The cause is still open.",
        "at": [["#tests-variance", None]],
    },
    {
        "title": "Leftover autocorrelation",
        "text": "The LM test rejects no residual autocorrelation in every model, in both its forms. Most of the pattern "
                "sits at lag 1 in the wind-error equation, and more lags do not remove it. The bootstrap keeps it in the "
                "Granger p-values and response bands, but the coefficients may still be biased.",
        "at": [["#tests-lm", None]],
    },
    {
        "title": "Sample length",
        "text": "The model uses one year of hourly data, against five years in Spodniak et al. A year holds only "
                "about 26 two-week blocks, which limits how precisely the bootstrap can measure uncertainty, and BIC "
                "and HQ would need one to three years of data to settle on the order AIC picks.",
        "at": [["#tests-lags h2", None]],
    },
    {
        "title": "Many tests",
        "text": "The Granger evidence comes from many tests at once: without any link, about 1 test in 20 is "
                "significant by chance, and no significant link survives a Bonferroni correction.",
        "at": [["#answer-granger", ".card"]],
    },
    {
        "title": "Solar left out",
        "text": "The model leaves out the solar forecast error, as the reference studies do, which keeps the results "
                "comparable. Adding it as a fourth endogenous variable would also double the Granger tests in each "
                "model, from six to twelve.",
        "at": [["#varx-roles", None]],
    },
    {
        "title": "The controls",
        "text": "The cross-border flows are scheduled in the same day-ahead auction that sets the day-ahead price in "
                "the DA-ID and DA-BAL spreads, so they are not fully independent of the spreads, and Viking Link (DK1 "
                "to Great Britain) is missing from the flow data. The weekly reservoir value is used for every hour "
                "of its week, so early hours see a value published later. Wind curtailment at very low prices is "
                "assumed small.",
        "at": [["#varx-roles", None]],
    },
    {
        "title": "Wind forecast timing",
        "text": "The wind forecast is the one published at 18:00 on the day before delivery, six hours after the "
                "day-ahead auction closes. The wind error therefore picks up only surprises after 18:00, which may "
                "understate its link with the DA-ID and DA-BAL spreads.",
        "at": [["#data-h", ".intro"]],
    },
    {
        "title": "Demand data",
        "text": "Actual demand is the TSO's total load (net generation minus exports plus imports minus storage), "
                "not metered consumption, so errors in measured generation, wind included, end up in the demand "
                "error. The stored forecast is assumed to be the day-ahead version, and any later update to be "
                "small.",
        "at": [["#data-h", ".intro"]],
    },
    {
        "title": "Whose forecast",
        "text": "The forecast errors are the TSOs' misses, not those of the market participants, who bid with their own "
                "forecasts. The TSO forecasts are closer to the inputs of the flow-based capacity calculation, but "
                "not the exact inputs: the domain is published by 11:00 on the day before delivery, while the wind "
                "forecast used here is published at 18:00 that day. The results describe how the TSOs' misses "
                "relate to the spreads, not how each participant's own misses do.",
        "at": [["img[data-math='error']", "figure"]],
    },
    {
        "title": "Hourly balancing price",
        "text": "Since March 2025 the balancing price is set for every quarter-hour. The hourly mean mixes "
                "quarter-hours with different regulation states in 68 % of the hours after March, which makes the "
                "balancing spreads noisy and hard to explain with any model of hourly averages.",
        "at": [["#data-h", ".intro"]],
    },
]
