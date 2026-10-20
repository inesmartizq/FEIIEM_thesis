"""
structural_breaks.py

Structural-break analysis (mean and variance) of the price series of the
three markets — the representative price per market from
dataframe_building.MARKET_PRICES (day-ahead da_price, intraday id_vwap,
balancing b_imbalance_price) — per bidding zone. The "structural_breaks"
step of main.py. Read-only: the dataframe is never modified, no
observations are removed, no features are created.

METHOD
------
Detection runs on DAILY series (Copenhagen local days; a day needs >= 80 %
of its hours observed), not hourly: at hourly resolution a level test
mostly "detects" the day/night price cycle.

Series tested
    Mean breaks:     daily mean price.
    Variance breaks: log of each day's within-day variance of the hourly
                     prices (the daily variance measure of plots/<name>/
                     stats/) — a robust Inclán–Tiao-type test (Sansó, Aragó &
                     Carrion 2004) for a sustained multiplicative change in
                     volatility.
    Both are capped at their 1st/99th percentiles FOR DETECTION ONLY, so a
    single extreme day can't create a break (e.g. 2025-10-04 in DK1: almost
    constant DA prices, log variance 5 sd below normal).

Test statistic
    CUSUM: max_k |S_k| / sqrt(n * LRV), with LRV a HAC long-run variance
    (Bartlett kernel, Andrews (1991) AR(1) plug-in bandwidth) of the
    residuals around the candidate break (each side demeaned) — around the
    overall mean, a genuine shift would look like persistence and hide
    itself. At least MIN_SEGMENT_DAYS days on each side.

Multiple breaks: seeded binary segmentation (Kovács, Li, Bühlmann, Haubner
    & Munk 2023). The statistic is computed on ~30 overlapping windows
    (the full sample, halves, quarters, ...); the most significant window
    gives a break, then both sides are searched again. Unlike plain binary
    segmentation (whole sample only), a change that later reverses — e.g.
    volatility up in March and down again in November — is still found.

Significance
    Critical values / p-values come from a parametric bootstrap: the
    distribution of the LARGEST statistic over all windows, simulated
    (NULL_DRAWS times) on AR(1) series with the data's own persistence. rho
    is estimated from first differences (corr = -(1-rho)/2), which a level
    shift does not inflate. This accounts both for testing many windows and
    for persistence a short-window HAC estimate misses. Checked by
    simulation: ~1 % false alarms for rho = 0, 0.5, 0.8 at alpha = 0.01.
    p_value_adjusted (used for the decision) is this bootstrap p-value;
    p_value is the single-window Kolmogorov p, for reference only.

Reported numbers (mean / variance before and after) are computed on the
unmodified HOURLY prices of the two adjacent segments. For variance breaks
the typical within-day std (geometric mean of the daily variances, as a
std) is reported too — that is the quantity the test compares; total
hourly variance also contains day-to-day level swings.

STATISTICAL DETECTION != ECONOMIC MEANING. A detected break says the
level/volatility differs between segments; with one year of data this can
be seasonality, a market-design change, fuel prices or weather. The
output only flags candidate explanations, it doesn't test them.

OUTPUT (plots/<name>/structural_breaks/)
    STRUCTURAL_BREAKS.md                   -- break table (Market / Zone / Break date /
                                              Break type / Before / After / Change /
                                              Statistical evidence) + regime
                                              classification + method
    structural_breaks_<market>.png         -- price with breaks marked, plus daily/weekly
                                              volatility
"""

import math
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

_here = Path(__file__).resolve()
for _parent in [_here.parent, *_here.parents]:
    if (_parent / "analysis_utils.py").exists():
        if str(_parent) not in sys.path:
            sys.path.insert(0, str(_parent))
        break

from analysis_utils import PLOTS_DIR, load_dataframe
from dataframe_building import MARKET_PRICES

LOCAL_TZ = "Europe/Copenhagen"
MIN_DAY_COVERAGE = 0.8
BOTH_WINDOW_DAYS = 14          # a mean and a variance break this close -> "Both"
REL_CHANGE_MIN_LEVEL = 10.0    # EUR/MWh: below this, a % change of the mean is not meaningful
WINSOR_QUANTILE = 0.01         # detection series capped at the 1st / 99th percentile
NULL_DRAWS = 2000              # simulations for the max-over-intervals null distribution
MARKET_NAMES = {"da": "Day-ahead", "id": "Intraday", "bal": "Balancing"}

MEAN_COLOR = "#D55E00"
VAR_COLOR = "#6A3D9A"
PRICE_COLOR = "#0072B2"


# ---------------------------------------------------------------------------
# TEST
# ---------------------------------------------------------------------------
def _kolmogorov_sf(x: float) -> float:
    """P(sup |Brownian bridge| > x)."""
    if x <= 0:
        return 1.0
    k = np.arange(1, 101)
    return float(np.clip(2 * np.sum((-1.0) ** (k + 1) * np.exp(-2 * k ** 2 * x ** 2)), 0.0, 1.0))


def _long_run_variance(x: np.ndarray) -> float:
    """Bartlett-kernel HAC variance with the Andrews (1991) AR(1) plug-in
    bandwidth — adapts to how persistent the series is."""
    e = x - x.mean()
    n = len(e)
    denom = e[:-1] @ e[:-1]
    rho = float(np.clip((e[1:] @ e[:-1]) / denom, -0.97, 0.97)) if denom > 0 else 0.0
    alpha = 4 * rho ** 2 / ((1 - rho) ** 2 * (1 + rho) ** 2)
    bandwidth = min(int(1.1447 * (alpha * n) ** (1 / 3)), n - 1)
    lrv = e @ e / n
    for lag in range(1, bandwidth + 1):
        lrv += 2 * (1 - lag / (bandwidth + 1)) * (e[lag:] @ e[:-lag]) / n
    return max(lrv, 1e-12)


def _cusum_max(seg: np.ndarray, min_seg: int):
    """(statistic, k): the largest |CUSUM| over split points leaving
    >= min_seg observations on each side (k = observations left of the
    break), standardised by the long-run variance of the residuals AROUND
    THAT BREAK (each side demeaned separately). Estimating it around the
    overall mean instead would count a genuine shift as 'persistence',
    inflate the variance and hide the break."""
    n = len(seg)
    cusum = np.abs(np.cumsum(seg - seg.mean())[:-1])[min_seg - 1:n - min_seg]
    if cusum.size == 0:
        return None, None
    k = int(np.argmax(cusum)) + min_seg
    resid = np.concatenate([seg[:k] - seg[:k].mean(), seg[k:] - seg[k:].mean()])
    return float(cusum[k - min_seg] / math.sqrt(n * _long_run_variance(resid))), k


def _ar1_from_differences(x: np.ndarray) -> float:
    """AR(1) persistence estimated from FIRST DIFFERENCES: for an AR(1),
    corr(dx_t, dx_t-1) = -(1 - rho) / 2. Differencing removes level shifts,
    so — unlike the usual estimate — a genuine break does not inflate rho
    (which would make the test needlessly conservative)."""
    d = np.diff(x)
    d = d - d.mean()
    r1 = (d[1:] @ d[:-1]) / (d @ d)
    return float(np.clip(1 + 2 * r1, 0.0, 0.95))


_NULL_CACHE: dict = {}


def _null_max_statistics(n: int, min_seg: int, rho: float) -> np.ndarray:
    """Distribution, under 'no break', of the LARGEST statistic over all
    seeded intervals, simulated on AR(1) series with the data's own
    persistence (parametric bootstrap; rho rounded to 0.05 for caching).
    Its upper tail gives p-values that account both for testing ~30
    overlapping intervals and for persistence the short-window HAC
    estimate misses. Fixed seed, so results are reproducible."""
    rho = round(rho * 20) / 20
    key = (n, min_seg, rho)
    if key not in _NULL_CACHE:
        rng = np.random.default_rng(20250101)
        intervals = [(a, b) for a, b in _seeded_intervals(n, 2 * min_seg) if b - a >= 2 * min_seg]
        burn = 100
        draws = np.empty(NULL_DRAWS)
        for d in range(NULL_DRAWS):
            e = rng.standard_normal(n + burn)
            x = np.empty(n + burn)
            x[0] = e[0]
            for t in range(1, n + burn):
                x[t] = rho * x[t - 1] + e[t]
            x = x[burn:]
            draws[d] = max(_cusum_max(x[a:b], min_seg)[0] for a, b in intervals)
        _NULL_CACHE[key] = np.sort(draws)
    return _NULL_CACHE[key]


def _seeded_intervals(n: int, min_len: int, decay: float = 2 ** -0.5) -> list[tuple[int, int]]:
    """Seeded intervals (Kovács et al. 2023): the full sample, then layers of
    shorter, evenly spaced, overlapping windows (length shrinking by
    `decay` per layer) down to min_len."""
    intervals, layer = set(), 1
    while True:
        length = n * decay ** (layer - 1)
        if length < min_len:
            break
        count = 2 * math.ceil((1 / decay) ** (layer - 1)) - 1
        shift = (n - length) / (count - 1) if count > 1 else 0
        for i in range(count):
            start = int(round(i * shift))
            intervals.add((start, min(n, start + int(round(length)))))
        layer += 1
    return sorted(intervals)


def _seeded_segmentation(x: np.ndarray, min_seg: int, alpha: float) -> list[dict]:
    """Seeded binary segmentation. Unlike plain binary segmentation (which
    only ever tests the whole remaining sample), changes that later reverse
    (e.g. volatility up in March, down again in autumn) are found, because
    shorter windows that contain only one of them are tested too. Greedy:
    take the most significant interval, split there, repeat on both sides.
    p_value = per-interval Kolmogorov p; p_adjusted = p for the maximum over
    all intervals (simulated), which is what the alpha decision uses."""
    n = len(x)
    intervals = _seeded_intervals(n, 2 * min_seg)
    rho = _ar1_from_differences(x)
    null = _null_max_statistics(n, min_seg, rho)
    found = []

    def search(lo: int, hi: int):
        best = None
        for a, b in intervals:
            if a < lo or b > hi or b - a < 2 * min_seg:
                continue
            stat, k = _cusum_max(x[a:b], min_seg)
            if stat is None:
                continue
            p_adj = (1 + np.sum(null >= stat)) / (len(null) + 1)
            if p_adj < alpha and (best is None or stat > best["statistic"]):
                best = {"index": a + k, "statistic": stat, "p_value": _kolmogorov_sf(stat),
                        "p_adjusted": float(p_adj), "window": (a, b), "ar1_rho": rho}
        if best is None:
            return
        found.append(best)
        search(lo, best["index"])
        search(best["index"], hi)

    search(0, n)
    return sorted(found, key=lambda b: b["index"])


def _winsorize(x: np.ndarray, q: float = WINSOR_QUANTILE) -> np.ndarray:
    """Cap at the q / 1-q quantiles — for DETECTION only, so one extreme
    day (e.g. a day of almost constant prices, log variance ~5 sd below
    normal) cannot create a break on its own. Reported values use the
    unmodified hourly data."""
    lo, hi = np.quantile(x, [q, 1 - q])
    return np.clip(x, lo, hi)


# ---------------------------------------------------------------------------
# DATA
# ---------------------------------------------------------------------------
def _hourly_series(df, time_col, group_col, zone, col) -> pd.Series:
    """Hourly prices of one zone, indexed by Copenhagen local time."""
    g = df[df[group_col].astype(str) == zone]
    s = g.set_index(time_col)[col].sort_index()
    s.index = s.index.tz_convert(LOCAL_TZ)
    return s


def _daily(s: pd.Series) -> pd.DataFrame:
    day = s.index.tz_localize(None).normalize()
    grouped = s.groupby(day)
    daily = pd.DataFrame({"mean": grouped.mean(), "var": grouped.var(), "n": grouped.count(),
                          "hours": grouped.size()})
    daily = daily[daily["n"] >= MIN_DAY_COVERAGE * daily["hours"]]
    return daily


def _segment_rows(s: pd.Series, dates: list, stat_fn) -> list:
    """Statistic of the hourly series within each segment between break dates."""
    day = s.index.tz_localize(None).normalize()
    edges = [day.min()] + list(dates) + [day.max() + pd.Timedelta(days=1)]
    segments = []
    for start, end in zip(edges[:-1], edges[1:]):
        part = s[(day >= start) & (day < end)].dropna()
        segments.append({"start": start, "end": end - pd.Timedelta(days=1), "value": stat_fn(part),
                         "std": part.std(), "n_hours": len(part)})
    return segments


# ---------------------------------------------------------------------------
# ANALYSIS
# ---------------------------------------------------------------------------
def _analyse_series(s: pd.Series, alpha: float, min_seg: int):
    daily = _daily(s)
    mean_x = _winsorize(daily["mean"].to_numpy())
    mean_breaks = _seeded_segmentation(mean_x, min_seg, alpha)
    for b in mean_breaks:
        b["date"] = daily.index[b["index"]]

    var_daily = daily[daily["var"] > 0]
    var_breaks = _seeded_segmentation(_winsorize(np.log(var_daily["var"].to_numpy())), min_seg, alpha)
    for b in var_breaks:
        b["date"] = var_daily.index[b["index"]]

    mean_segs = _segment_rows(s, [b["date"] for b in mean_breaks], lambda p: p.mean())
    var_segs = _segment_rows(s, [b["date"] for b in var_breaks], lambda p: p.var())
    # What the variance test actually compares: the typical within-day std
    # (geometric mean of the daily within-day variances, as a std).
    for seg in var_segs:
        days = var_daily[(var_daily.index >= seg["start"]) & (var_daily.index <= seg["end"])]
        seg["within_day_std"] = float(np.sqrt(np.exp(np.log(days["var"]).mean())))
    return daily, mean_breaks, var_breaks, mean_segs, var_segs


def _fmt_seg(seg) -> str:
    return f"{seg['start']:%Y-%m-%d} to {seg['end']:%Y-%m-%d}"


def _break_tables(results):
    mean_rows, var_rows = [], []
    for (market, col, zone), (_, mb, vb, ms, vs) in results.items():
        for i, b in enumerate(mb):
            before, after = ms[i]["value"], ms[i + 1]["value"]
            rel = (100 * (after - before) / abs(before)) if abs(before) >= REL_CHANGE_MIN_LEVEL else None
            mean_rows.append({
                "market": market, "price_column": col, "zone": zone, "break_date": b["date"].date(),
                "segment_before": _fmt_seg(ms[i]), "segment_after": _fmt_seg(ms[i + 1]),
                "mean_before": before, "mean_after": after, "change": after - before,
                "relative_change_pct": rel, "cusum_statistic": b["statistic"], "p_value": b["p_value"],
                "p_value_adjusted": b["p_adjusted"],
            })
        for i, b in enumerate(vb):
            before, after = vs[i]["value"], vs[i + 1]["value"]
            var_rows.append({
                "market": market, "price_column": col, "zone": zone, "break_date": b["date"].date(),
                "segment_before": _fmt_seg(vs[i]), "segment_after": _fmt_seg(vs[i + 1]),
                "variance_before": before, "variance_after": after, "change": after - before,
                "variance_ratio": after / before if before > 0 else None,
                "std_before": vs[i]["std"], "std_after": vs[i + 1]["std"],
                "within_day_std_before": vs[i]["within_day_std"],
                "within_day_std_after": vs[i + 1]["within_day_std"],
                "within_day_std_ratio": vs[i + 1]["within_day_std"] / vs[i]["within_day_std"],
                "cusum_statistic": b["statistic"], "p_value": b["p_value"],
                "p_value_adjusted": b["p_adjusted"],
            })
    cols_m = ["market", "price_column", "zone", "break_date", "segment_before", "segment_after",
              "mean_before", "mean_after", "change", "relative_change_pct", "cusum_statistic", "p_value", "p_value_adjusted"]
    cols_v = ["market", "price_column", "zone", "break_date", "segment_before", "segment_after",
              "variance_before", "variance_after", "change", "variance_ratio", "std_before", "std_after",
              "within_day_std_before", "within_day_std_after", "within_day_std_ratio",
              "cusum_statistic", "p_value", "p_value_adjusted"]
    return (pd.DataFrame(mean_rows, columns=cols_m).round(4),
            pd.DataFrame(var_rows, columns=cols_v).round(4))


def _evidence(stat, p) -> str:
    return f"CUSUM {stat:.2f}, adj. p {'< 0.0001' if p < 1e-4 else f'= {p:.4f}'}"


def _var_text(v, side: str) -> str:
    return f"var {v[f'variance_{side}']:,.0f}; within-day std {v[f'within_day_std_{side}']:.1f}"


def _var_change_text(v) -> str:
    return (f"var x{v['variance_ratio']:.2f}; within-day std x{v['within_day_std_ratio']:.2f} "
            f"(tested)")


def _summary_table(mean_df: pd.DataFrame, var_df: pd.DataFrame) -> pd.DataFrame:
    """One row per break; a mean and a variance break within
    BOTH_WINDOW_DAYS of each other in the same market/zone become "Both"."""
    rows, used_var = [], set()
    for i, m in mean_df.iterrows():
        cands = var_df[(var_df["market"] == m["market"]) & (var_df["zone"] == m["zone"])]
        gap = (pd.to_datetime(cands["break_date"]) - pd.Timestamp(m["break_date"])).abs()
        close = cands[gap <= pd.Timedelta(days=BOTH_WINDOW_DAYS)]
        close = close[~close.index.isin(used_var)]
        rel = "" if pd.isna(m["relative_change_pct"]) else f" ({m['relative_change_pct']:+.0f} %)"
        before, after = f"mean {m['mean_before']:.1f}", f"mean {m['mean_after']:.1f}"
        change = f"mean {m['change']:+.1f}{rel}"
        evidence = f"mean: {_evidence(m['cusum_statistic'], m['p_value_adjusted'])}"
        kind, date = "Mean", str(m["break_date"])
        if len(close):
            v = close.iloc[(pd.to_datetime(close["break_date"]) - pd.Timestamp(m["break_date"])).abs().argmin()]
            used_var.add(v.name)
            kind = "Both"
            if str(v["break_date"]) != date:
                date = f"{date} / {v['break_date']} (var)"
            before += f"; {_var_text(v, 'before')}"
            after += f"; {_var_text(v, 'after')}"
            change += f"; {_var_change_text(v)}"
            evidence += f"; var: {_evidence(v['cusum_statistic'], v['p_value_adjusted'])}"
        rows.append({"Market": m["market"], "Zone": m["zone"], "Break date": date, "Break type": kind,
                     "Before": before, "After": after, "Change": change, "Statistical evidence": evidence})
    for i, v in var_df.iterrows():
        if i in used_var:
            continue
        rows.append({"Market": v["market"], "Zone": v["zone"], "Break date": str(v["break_date"]),
                     "Break type": "Variance", "Before": _var_text(v, "before"),
                     "After": _var_text(v, "after"), "Change": _var_change_text(v),
                     "Statistical evidence": f"var: {_evidence(v['cusum_statistic'], v['p_value_adjusted'])}"})
    out = pd.DataFrame(rows, columns=["Market", "Zone", "Break date", "Break type", "Before", "After",
                                      "Change", "Statistical evidence"])
    order = {name: i for i, name in enumerate(MARKET_NAMES.values())}
    out["_order"] = out["Market"].map(order)
    return out.sort_values(["_order", "Zone", "Break date"]).drop(columns="_order").reset_index(drop=True)


def _classification(results) -> pd.DataFrame:
    rows = []
    for (market, col, zone), (_, mb, vb, ms, vs) in results.items():
        rows.append({
            "Market": market, "Zone": zone, "Price column": col,
            "Mean": (f"significant mean shifts ({len(mb)} break{'s' if len(mb) > 1 else ''})"
                     if mb else "relatively stable mean"),
            "Variance": (f"significant variance shifts ({len(vb)} break{'s' if len(vb) > 1 else ''})"
                         if vb else "relatively stable variance"),
            "Distinct regimes": (f"yes — {len(ms)} mean regime(s), {len(vs)} variance regime(s)"
                                 if (mb or vb) else "no — one regime over the period"),
            "Range of regime means": (f"{min(s['value'] for s in ms):.1f} to {max(s['value'] for s in ms):.1f}"
                                      if ms else ""),
            "Range of regime variances": (f"{min(s['value'] for s in vs):,.0f} to "
                                          f"{max(s['value'] for s in vs):,.0f}" if vs else ""),
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# PLOT
# ---------------------------------------------------------------------------
def _weekly_std(s: pd.Series) -> pd.Series:
    """Std of the hourly prices within each Monday-Sunday week (Copenhagen
    local time); weeks with < 80 % of their hours observed are left out."""
    g = s.groupby(s.index.tz_localize(None).to_period("W-SUN"))  # s is in local time already
    std, n = g.std(), g.count()
    std = std[n >= 0.8 * 168]
    return pd.Series(std.to_numpy(), index=std.index.start_time)


def _vlines(ax, breaks, color, style, label):
    for i, b in enumerate(breaks):
        ax.axvline(b["date"], color=color, linestyle=style, linewidth=1.6,
                   label=label if i == 0 else None, zorder=3)


def _plot_market(name, market, col, zones, results, hourly, out_path):
    fig, axes = plt.subplots(2, len(zones), figsize=(8 * len(zones), 7.5), squeeze=False, sharex="col")
    for j, zone in enumerate(zones):
        daily, mb, vb, ms, vs = results[(market, col, zone)]
        ax = axes[0][j]
        ax.plot(daily.index, daily["mean"], color=PRICE_COLOR, linewidth=0.9, label="Daily mean price")
        for i, seg in enumerate(ms):
            ax.hlines(seg["value"], seg["start"], seg["end"] + pd.Timedelta(days=1), color=MEAN_COLOR,
                      linewidth=2.2, label="Regime mean (between mean breaks)" if i == 0 else None, zorder=4)
        _vlines(ax, mb, MEAN_COLOR, "-", "Mean break")
        _vlines(ax, vb, VAR_COLOR, "--", "Variance break")
        ax.set_title(f"{zone} — {col}", fontsize=11)
        ax.set_ylabel("Daily mean price [EUR/MWh]", fontsize=9)

        ax = axes[1][j]
        d_std = np.sqrt(daily["var"])
        w_std = _weekly_std(hourly[(market, col, zone)])
        ax.plot(d_std.index, d_std.values, color="0.6", linewidth=0.7, label="Daily std (within day)")
        if not w_std.empty:
            ax.step(w_std.index, w_std.values, where="post", color=PRICE_COLOR, linewidth=1.4,
                    label="Weekly std (within Mon–Sun week)")
        for i, seg in enumerate(vs):
            ax.hlines(seg["std"], seg["start"], seg["end"] + pd.Timedelta(days=1), color=VAR_COLOR,
                      linewidth=2.2, label="Regime std (between variance breaks)" if i == 0 else None, zorder=4)
        _vlines(ax, mb, MEAN_COLOR, "-", "Mean break")
        _vlines(ax, vb, VAR_COLOR, "--", "Variance break")
        ax.set_yscale("log")
        ax.set_ylabel("Std of hourly prices [EUR/MWh, log scale]", fontsize=9)
        ax.set_xlabel("Delivery date (Copenhagen local time)", fontsize=9)
        locator = mdates.AutoDateLocator()
        ax.xaxis.set_major_locator(locator)
        ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(locator))
        for a in (axes[0][j], ax):
            for spine in ("top", "right"):
                a.spines[spine].set_visible(False)
            a.tick_params(labelsize=8)

    handles = {}
    for a in axes.flat:
        for h, lbl in zip(*a.get_legend_handles_labels()):
            handles.setdefault(lbl, h)
    fig_h = fig.get_size_inches()[1]
    fig.suptitle(f"{market} price — structural breaks (CUSUM/HAC, seeded binary segmentation)",
                 fontsize=13, y=1 - 0.12 / fig_h, va="top")
    fig.legend(list(handles.values()), list(handles.keys()), loc="upper center",
               bbox_to_anchor=(0.5, 1 - 0.5 / fig_h), ncol=4, frameon=False, fontsize=9)
    fig.tight_layout(rect=(0, 0, 1, 1 - 1.15 / fig_h))
    fig.savefig(out_path, dpi=130)
    plt.close(fig)
    print(f"  wrote {out_path.name}")


# ---------------------------------------------------------------------------
# REPORT
# ---------------------------------------------------------------------------
def _md_table(df: pd.DataFrame) -> str:
    lines = ["| " + " | ".join(df.columns) + " |", "|" + "|".join("---" for _ in df.columns) + "|"]
    lines += ["| " + " | ".join(str(v) for v in r) + " |" for r in df.itertuples(index=False)]
    return "\n".join(lines)


def _write_report(name, summary, classification, alpha, min_seg, period, out_path):
    text = [
        f"# Structural breaks — `{name}`",
        "",
        f"Prices: {', '.join(f'{MARKET_NAMES.get(m, m)} = `{c}`' for m, c in MARKET_PRICES.items())}. "
        f"Period {period}. Per bidding zone.",
        "",
        "**Method.** Daily series (Copenhagen local days). Mean breaks: CUSUM test on the daily mean "
        "price. Variance breaks: the same test on the log of the within-day variance. Both are "
        "standardised by a HAC long-run variance (Bartlett kernel, Andrews bandwidth), estimated "
        "around the candidate break, because prices are autocorrelated. For detection only, the daily "
        "series are capped at their 1st/99th percentiles. Multiple breaks are found by seeded binary "
        "segmentation (Kovács et al. 2023): about 30 overlapping windows, which also catches changes "
        "that later reverse. Significance: a parametric AR(1) bootstrap of the largest statistic over "
        "all windows, using the series' own persistence (estimated from first differences, so it is "
        f"robust to level shifts). The cut-off is α = {alpha} on that adjusted p-value, with at least "
        f"{min_seg} days between breaks. In simulations this gives about 1 % false alarms at "
        "persistence 0 to 0.8. Before/after values are computed on the unmodified hourly prices of the "
        "adjacent segments. For variance breaks the typical within-day std is shown too: that is what "
        f"the test compares. A mean break and a variance break within {BOTH_WINDOW_DAYS} days of each "
        "other are reported as 'Both'.",
        "",
        "## Detected breaks",
        "",
        _md_table(summary) if len(summary) else "No breaks detected.",
        "",
        "## Regime classification (statistical)",
        "",
        _md_table(classification),
        "",
        "## Reading this",
        "- This is **statistical detection only**. A break means the level or volatility differs "
        "significantly between segments. It does not say why.",
        "- With a single year of data, mean breaks can reflect seasonality (e.g. low midday "
        "solar-driven prices in spring/summer) as much as structural change.",
        "- Candidate explanations to check before interpreting a break economically (not tested here): "
        "seasonal fuel and weather patterns; the Nordic mFRR energy-activation market go-live (March "
        "2025), which changed balancing price formation; the day-ahead 15-minute MTU go-live "
        "(1 Oct 2025).",
        "- Spikes are genuine market outcomes. No observations were removed and the dataframe is "
        "unchanged.",
        "",
    ]
    out_path.write_text("\n".join(text), encoding="utf-8")
    print(f"  wrote {out_path.name}")


# ---------------------------------------------------------------------------
# ENTRY POINT
# ---------------------------------------------------------------------------
def run_structural_breaks(input_arg: str, alpha: float = 0.01, min_segment_days: int = 30,
                          time_col: str | None = None, group_col: str | None = None):
    """The "structural_breaks" step of main.py."""
    df, time_col, group_col, _, stem = load_dataframe(input_arg, time_col, group_col)
    out_dir = PLOTS_DIR / stem / "structural_breaks"
    out_dir.mkdir(parents=True, exist_ok=True)
    zones = sorted(df[group_col].astype(str).unique())

    results, hourly = {}, {}
    for key, col in MARKET_PRICES.items():
        if col not in df.columns:
            print(f"  skipping {col} (not in this dataframe)")
            continue
        market = MARKET_NAMES.get(key, key)
        for zone in zones:
            s = _hourly_series(df, time_col, group_col, zone, col)
            hourly[(market, col, zone)] = s
            results[(market, col, zone)] = _analyse_series(s, alpha, min_segment_days)
            _, mb, vb, _, _ = results[(market, col, zone)]
            print(f"  {market:9s} {zone}: {len(mb)} mean break(s), {len(vb)} variance break(s)")
    if not results:
        print("  no market price columns present — nothing to do.")
        return

    mean_df, var_df = _break_tables(results)
    summary = _summary_table(mean_df, var_df)
    classification = _classification(results)

    for market, col in {(m, c) for (m, c, _) in results}:
        _plot_market(stem, market, col, zones, results, hourly,
                     out_dir / f"structural_breaks_{market.lower().replace('-', '_')}.png")

    period = f"{df[time_col].min():%Y-%m-%d} to {df[time_col].max():%Y-%m-%d}"
    _write_report(stem, summary, classification, alpha, min_segment_days, period,
                  out_dir / "STRUCTURAL_BREAKS.md")


if __name__ == "__main__":
    run_structural_breaks(sys.argv[1] if len(sys.argv) > 1 else "df_2025")
