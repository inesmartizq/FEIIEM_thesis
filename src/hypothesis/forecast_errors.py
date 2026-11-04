"""
forecast_errors.py — step 1 of the hypothesis: what the forecast errors look
like (the "forecast_errors" step of main.py). Descriptive only: no model, no
test. For every forecast error among the endogenous variables (the error
columns of building.FORECAST_ERRORS), per zone, with e_t = forecast - actual
(positive = over-forecast):

    magnitude    the typical error (median |e|), the large ones (|e| above its
                 large_quantile) and the largest over- and under-forecast
    sign         the share of over-forecast hours and the mean error
    same hours   the mean error by hour of the day and month (Copenhagen time)
    persistence  runs: consecutive hours in which the error keeps its sign
    recurrence   the hours with a large error, per month and sign
    normalised   the size of the variable itself (wind produced, electricity consumed): its total over the
                 period and its average hour (total / hours), so an error can be read as a % of the
                 average hour and compared between zones of different size
    level link   the correlation of the error with the actual value: strongly negative when the error
                 mostly tracks the level of the variable (a forecast that is too low in windy hours)
                 rather than surprises
    price link   the mean error in each of price_groups equal groups of hours sorted by the day-ahead
                 price (1 = cheapest): an error that changes with the price is not a pure surprise,
                 e.g. consumption that rises above its forecast when power is cheap

OUTPUT (plots/<name>/forecast_errors/)
    summary.csv         one row per zone and error: the key numbers above
    by_price.csv        mean error per group of hours sorted by the day-ahead price
    hour_month.csv      mean error and share of over-forecast hours per month and hour
    runs.csv            number of runs per sign and length
    large_by_month.csv  hours with a large error per month and sign
    FORECAST_ERRORS.md  the key numbers as a table
"""

import numpy as np
import pandas as pd

from common import label, md_table, zone_frame, zones_with_data
from dataframe.building import FORECAST_ERRORS, LOCAL_TZ, MARKET_PRICES, Spec
from hypothesis.shocks_and_breaks import shock_runs

FOLDERS = ["forecast_errors"]


def error_columns(spec: Spec) -> list:
    """The forecast errors among the endogenous variables."""
    return [c for c in spec.by_role()["Endogenous"] if c in FORECAST_ERRORS]


def hourly(df: pd.DataFrame, zone: str, col: str) -> pd.Series:
    """One zone's hourly values on the complete hourly grid, indexed by Copenhagen local time."""
    dz = zone_frame(df, zone)
    return pd.Series(dz[col].to_numpy(float), index=pd.DatetimeIndex(dz["datetime_utc"]).tz_convert(LOCAL_TZ))


def sign_runs(e: pd.Series) -> pd.DataFrame:
    """Runs of consecutive hours with the same sign (a missing hour or an exact 0 ends a run): sign, start, length."""
    runs = shock_runs(e.to_numpy(), 0.0)  # runs with |e| > 0: every run of one sign
    return pd.DataFrame({"sign": [s for _, _, s in runs], "start": [e.index[a] for a, _, _ in runs],
                         "length": [b - a + 1 for a, b, _ in runs]})


def describe(e: pd.Series, large_quantile: float) -> dict:
    """The key numbers of one error series."""
    v = e.dropna()
    s = np.sign(e.to_numpy())
    pairs = ~np.isnan(s[1:]) & ~np.isnan(s[:-1])
    runs = sign_runs(e)
    longest = runs.loc[runs["length"].idxmax()]
    hours_in = np.repeat(runs["length"].to_numpy(), runs["length"].to_numpy())  # each hour: the length of its run
    return {
        "hours": len(v), "mean": v.mean(), "median_abs": v.abs().median(),
        "large_threshold": v.abs().quantile(large_quantile), "max_over": v.max(), "max_under": v.min(),
        "over_share": (v > 0).mean(), "under_share": (v < 0).mean(),
        "same_sign_share": float(np.sum((s[1:] == s[:-1])[pairs]) / np.sum(pairs)),
        "median_run_of_hour": float(np.median(hours_in)), "runs": len(runs),
        "longest_run": int(longest["length"]), "longest_run_sign": int(longest["sign"]),
        "longest_run_start": f"{longest['start']:%Y-%m-%d %H:%M}",
    }


def by_price(e: pd.Series, price: pd.Series, groups: int) -> pd.DataFrame:
    """The mean error per group of hours sorted by price (1 = cheapest), with each group's price range."""
    frame = pd.DataFrame({"e": e.to_numpy(), "price": price.to_numpy()}).dropna()
    frame["group"] = pd.qcut(frame["price"], groups, labels=range(1, groups + 1)).astype(int)
    return frame.groupby("group").agg(price_min=("price", "min"), price_max=("price", "max"),
                                      mean_error=("e", "mean"), hours=("e", "size")).reset_index()


def run(df: pd.DataFrame, spec: Spec, plot_dir, large_quantile: float = 0.95, price_groups: int = 5):
    out = plot_dir / "forecast_errors"
    out.mkdir(parents=True, exist_ok=True)
    rows = {k: [] for k in ("summary", "by_price", "hour_month", "runs", "large_by_month")}
    for col in error_columns(spec):
        for zone in zones_with_data(df, col):
            e = hourly(df, zone, col)
            key = {"zone": zone, "error": col}
            actual = hourly(df, zone, FORECAST_ERRORS[col][1])  # what the forecast is of: its size, for normalising
            numbers = {**describe(e, large_quantile), "actual": FORECAST_ERRORS[col][1],
                       "actual_mean": actual.mean(), "actual_total_twh": actual.sum() / 1e6,
                       "corr_actual": e.corr(actual)}
            rows["summary"].append({**key, **numbers})
            price = hourly(df, zone, MARKET_PRICES["da"])
            rows["by_price"] += [{**key, **r} for r in by_price(e, price, price_groups).to_dict("records")]
            frame = pd.DataFrame({"e": e.to_numpy(), "month": e.index.month, "hour": e.index.hour}).dropna()
            cells = frame.groupby(["month", "hour"])["e"].agg(mean="mean", over_share=lambda x: (x > 0).mean(),
                                                              hours="size").reset_index()
            rows["hour_month"] += [{**key, **r} for r in cells.to_dict("records")]
            counts = sign_runs(e).groupby(["sign", "length"]).size()
            rows["runs"] += [{**key, "sign": s, "length": n, "runs": c} for (s, n), c in counts.items()]
            large = frame[frame["e"].abs() > numbers["large_threshold"]]
            per_month = large.groupby(["month", np.sign(large["e"]).astype(int)]).size()
            rows["large_by_month"] += [{**key, "month": m, "sign": s, "hours": c} for (m, s), c in per_month.items()]
            print(f"  {zone} {col}: median |e| {numbers['median_abs']:.0f}, over-forecast "
                  f"{100 * numbers['over_share']:.0f} % of hours, same sign as the hour before "
                  f"{100 * numbers['same_sign_share']:.0f} %, longest run {numbers['longest_run']} h")
    for key, table in rows.items():
        pd.DataFrame(table).to_csv(out / f"{key}.csv", index=False)
    _write_report(pd.DataFrame(rows["summary"]), pd.DataFrame(rows["by_price"]), large_quantile,
                  out / "FORECAST_ERRORS.md")


def _write_report(summary: pd.DataFrame, prices: pd.DataFrame, large_quantile: float, path):
    name = lambda c: label(c).split(" (")[0]  # noqa: E731
    share = lambda col: (100 * summary[col] / summary["actual_mean"]).map(lambda v: f"{v:+.1f} %")  # noqa: E731
    table = pd.DataFrame({
        "Zone": summary["zone"], "Forecast error": summary["error"].map(name),
        "Total of the variable (TWh)": summary["actual_total_twh"].map(lambda v: f"{v:.2f}"),
        "Average hour (MW)": summary["actual_mean"].round(0).astype(int),
        "Typical size, median abs. error (MW)": summary["median_abs"].round(0).astype(int),
        "Typical size (% of the average hour)": share("median_abs").str.lstrip("+"),
        "Mean error (% of the average hour)": share("mean"),
        f"Large: abs. error above (MW, {100 * large_quantile:g}th pct.)": summary["large_threshold"].round(0).astype(int),
        "Largest over / under (MW)": [f"{a:+.0f} / {b:+.0f}" for a, b in zip(summary["max_over"], summary["max_under"])],
        "Over-forecast hours": (100 * summary["over_share"]).round(0).astype(int).astype(str) + " %",
        "Mean error (MW)": summary["mean"].map(lambda v: f"{v:+.0f}"),
        "Correlation with the actual value": summary["corr_actual"].map(lambda v: f"{v:+.2f}"),
        "Same sign as the hour before": (100 * summary["same_sign_share"]).round(0).astype(int).astype(str) + " %",
        "Run length of a typical hour (h)": summary["median_run_of_hour"].map(lambda v: f"{v:g}"),
        "Longest run (h)": summary["longest_run"],
    })
    text = [
        "# Forecast errors",
        "",
        "Step 1 of the hypothesis: what the forecast errors look like. Descriptive only. e_t = forecast − actual "
        "(positive = over-forecast). Normalised: as a % of the average hour of the variable itself (wind produced, "
        "electricity consumed), its total over the period divided by the hours, so zones of different size can be "
        "compared. A run is a stretch of consecutive hours in which the error keeps its sign; the "
        "run length of a typical hour is the median, over the hours, of the length of the run the hour belongs to. "
        "Monthly and hourly patterns: hour_month.csv; run lengths: runs.csv; large errors per month: large_by_month.csv.",
        "",
        md_table(table),
        "",
        "## Mean error by day-ahead price",
        "",
        "Mean error (MW) in equal groups of hours sorted by the day-ahead price, 1 = the cheapest hours.",
        "",
        md_table(prices.assign(error=prices["error"].map(name))
                 .pivot_table(index=["zone", "error"], columns="group", values="mean_error")
                 .map(lambda v: f"{v:+.0f}").reset_index()),
        "",
    ]
    path.write_text("\n".join(text), encoding="utf-8")
    print(f"  wrote {path.name}")
