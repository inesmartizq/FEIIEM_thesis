"""
correlation_analysis.py

Correlation diagnostics for any of the analysis-ready dataframes produced
by dataframe_building.py (full_2022_2025.csv, df_2025.csv, or anything
else added to ANALYSES later). Purpose: help decide which columns are
worth keeping before feeding a dataframe into the VAR -- a column that's
weakly related to everything else, at every lag checked, is either not
adding information, or its relationship shows up at a lag outside what
was checked.

Produces, for DK1, DK2, AND a pooled "combined" pass (see "WHY BOTH
PER-ZONE AND COMBINED" below):
  1. One correlation matrix PER LAG, for every lag in --lags (hours;
     default 0 1 4 24 168 -- i.e. "does this feature now relate to that
     feature 0/1/4/24/168 hours later"). lag=0 is the ordinary
     (symmetric) contemporaneous matrix. For lag > 0 the matrix is NOT
     symmetric: matrix.loc[c1, c2] means "c1 now vs c2 `lag` hours
     later" -- the direction that actually matters for a VAR (does c1
     help predict c2's future, not the reverse).
  2. Numeric summaries meant to be handed back for further analysis
     (see OUTPUT below) rather than just eyeballed as heatmaps:
     a tidy all-pairs-all-lags table, a best-lag-per-pair table, and a
     per-column "how related is this to anything" summary.

USAGE
    Normally run as the "correlation" step of main.py (project root),
    which calls run_correlation_analysis(). Standalone, on an already-built
    dataframe:
    python correlation_analysis.py df_2025
    python correlation_analysis.py full_2022_2025 --lags 0 1 2 3 6 12 24
    python correlation_analysis.py df_2025 --method spearman

    Optional flags:
      --lags L [L ...]   Space-separated list of lags in HOURS to check
                          (default: 0 1 4 24 168). Each becomes its own
                          matrix -- see point 1 above.
      --method            "pearson" (default) or "spearman".
      --min-abs-corr F    Threshold used only to flag "weakly correlated
                           with everything, at every lag checked" columns
                           (default 0.10) -- informational, nothing is
                           dropped automatically.
      --time-col / --group-col   Override auto-detected columns.

WHY BOTH PER-ZONE AND COMBINED:
  DK1 and DK2 have different sets of always-zero flow columns (see
  dataframe_building.py's report_zero_variance_by_area() -- e.g.
  da_flow_se4_* is real data for DK2 but constant 0 for DK1), and the
  VAR itself will be fit per zone (see dataframe_building.py's
  filter_to_area()) -- so the per-zone matrices are what actually
  screens columns for each area's model. The "combined" pass pools both
  zones' rows into one matrix, which you asked for directly -- useful
  for a first overall look, but keep in mind it can blend two genuinely
  different relationships (DK1's and DK2's) into one number, or make a
  correlation look stronger/weaker than it is in either zone alone
  simply because the areas differ on average (a Simpson's-paradox-style
  effect). Treat "combined" as a quick overview, and the per-zone
  matrices as the ones that actually matter for modeling.

OUTPUT (plots/<dataframe_name>/correlation/<zone>/, one folder per zone
plus one for "combined")
    pair_ranking.png                 -- every pair of DIFFERENT columns (a
                                        column with itself excluded), from the
                                        most to the least correlated, at the
                                        pair's strongest lag; colour = sign
    pair_ranking_clean.png           -- the same, without pairs of a forecast
                                        and its own actual (e.g.
                                        c_load_forecast_mw / c_load_actual_mw),
                                        without reservoir-vs-reservoir pairs,
                                        and without pairs with |r| < 0.3
                                        (CLEAN_MIN_ABS_CORR); a reservoir paired
                                        with a non-reservoir column is kept when
                                        |r| >= 0.3
    model/                           -- only with a model spec: the model's
                                        variables (endogenous, then exogenous)
        model_correlation_lag{L}.png -- endogenous + exogenous matrix per lag L,
                                        values written in the cells; black lines
                                        separate the two groups
        cross_correlation.png        -- per endogenous variable: its correlation
                                        with every other model variable at every
                                        lag from -max(lags) to +max(lags) hours
    all_columns/
        correlation_matrix_lag{L}.png   -- every column except the reservoirs
        reservoirs_lag{L}.png           -- reservoirs (rows, at t) x every other
                                           column (at t + L); the reservoir vs
                                           reservoir block (all ~1) is not shown
    tables/                          -- per zone only (not for "combined")
        pair_ranking.csv            -- every pair at its strongest lag, ranked
                                        (+ markets, cross_market flag); the
                                        clean chart is this table minus
                                        forecast-vs-actual pairs and |r| < 0.3
        weak_columns.txt             -- columns whose strongest |corr| is below
                                        --min-abs-corr
    (Only these two are written: they are what the analysis summary reads.
    Every other number is shown in the charts.)
"""

import argparse
import math
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# analysis_utils.py may not be sitting next to this script -- e.g. this
# file can live in src/statsistics/ while analysis_utils.py stays in
# src/. Search upward from this file for the folder that has it, and add
# THAT to sys.path, rather than assuming a fixed relative depth. Works
# no matter how these scripts get reorganized into subfolders later.
_here = Path(__file__).resolve()
for _parent in [_here.parent, *_here.parents]:
    if (_parent / "analysis_utils.py").exists():
        if str(_parent) not in sys.path:
            sys.path.insert(0, str(_parent))
        break
else:
    raise ImportError(
        f"Could not find analysis_utils.py anywhere above {_here} -- "
        f"make sure it's still somewhere in this project's src/ tree."
    )

from analysis_utils import PLOTS_DIR, load_dataframe, drop_constant_columns


# ---------------------------------------------------------------------------
# LAGGED CORRELATION MATRIX (the core computation)
# ---------------------------------------------------------------------------

def lagged_correlation_matrix(df: pd.DataFrame, cols: list, lag: int, method: str = "pearson",
                              group_col: str | None = None) -> pd.DataFrame:
    """matrix.loc[c1, c2] = correlation between col c1 at time t and col
    c2 at time t + lag (lag counted in ROWS of the already-sorted hourly
    grid, so lag=L means L hours later). The shift is done WITHIN each
    group_col value (bidding zone): in the pooled "combined" pass the rows
    of DK1 and DK2 interleave, and a plain row shift would pair DK1 with
    DK2 instead of with DK1 L hours later. lag=0 gives the ordinary,
    symmetric contemporaneous matrix. For lag > 0 the matrix is NOT
    symmetric -- matrix.loc[c1, c2] means "c1 now vs c2 L hours later",
    which is a different (and, for choosing VAR predictors, more useful)
    question than "c2 now vs c1 L hours later" (that's matrix.loc[c2, c1]
    instead).

    Uses LISTWISE deletion: rows where ANY column (at either t or t+lag)
    is NaN are dropped once for the whole lag, rather than a separate
    pairwise dropna per column pair. This trades a small amount of
    precision (a handful of extra dropped rows for pairs that don't
    actually overlap in missingness) for computing every pair in one
    vectorized matrix multiply instead of ~n^2 separate correlation
    calls. Reasonable here since missingness is low (well under 2%) for
    almost every feature -- see the coverage report -- so revisit this
    if a future dataframe has much higher missingness.
    """
    x = df[cols]
    y = df.groupby(group_col)[cols].shift(-lag) if group_col else df[cols].shift(-lag)
    y.columns = [f"{c}__shift" for c in cols]
    combined = pd.concat([x, y], axis=1).dropna()
    n = len(combined)
    if n < 10:
        return pd.DataFrame(np.nan, index=cols, columns=cols)

    X = combined[cols].to_numpy(dtype=float)
    Y = combined[[f"{c}__shift" for c in cols]].to_numpy(dtype=float)
    if method == "spearman":
        X = pd.DataFrame(X).rank().to_numpy()
        Y = pd.DataFrame(Y).rank().to_numpy()

    x_std = X.std(axis=0)
    y_std = Y.std(axis=0)
    x_std[x_std == 0] = np.nan  # a column constant WITHIN this lag's dropna subset -> NaN, not div-by-zero
    y_std[y_std == 0] = np.nan
    Xz = (X - X.mean(axis=0)) / x_std
    Yz = (Y - Y.mean(axis=0)) / y_std
    corr = (Xz.T @ Yz) / n
    return pd.DataFrame(corr, index=cols, columns=cols)


# ---------------------------------------------------------------------------
# NUMERIC SUMMARIES (the "send this back for analysis" outputs)
# ---------------------------------------------------------------------------

# The project's own naming convention (see dataframe_building.py's
# SOURCES comments) already tags every column with which market it
# belongs to -- no separate filter list to maintain by hand. "other" is
# the fallback for a future column that doesn't follow the convention.
#
# c_ (load/wind/solar forecasts & actuals, and the derived forecast-
# error columns) isn't its own market -- it's not a venue you trade on,
# it's the calculated system data that FEEDS the day-ahead market. So it
# maps to "day_ahead" here, same as da_, rather than getting its own
# "forecasts_actuals" bucket.
# x_ = cross-market spreads (x_da_id_spread etc.) — they belong to no
# single market, so they get their own bucket.
MARKET_LABELS = {"b": "balancing", "c": "day_ahead", "da": "day_ahead", "id": "intraday", "x": "cross_market"}


def market_of(col: str) -> str:
    return MARKET_LABELS.get(col.split("_")[0], "other")


def tidy_all_pairs_all_lags(lag_matrices: dict) -> pd.DataFrame:
    """Every (col_1, col_2, lag) combination as one flat table -- easiest
    format to hand back for further analysis (filter/sort/pivot however
    needed) rather than reading off N separate heatmaps. Includes both
    directions (col_1->col_2 and col_2->col_1) since they differ for
    lag > 0, and the diagonal (a column against itself = its own
    autocorrelation at that lag), which is informative in its own right."""
    rows = []
    for lag, mat in lag_matrices.items():
        for c1 in mat.index:
            for c2 in mat.columns:
                val = mat.loc[c1, c2]
                if pd.notna(val):
                    rows.append({"col_1": c1, "col_2": c2, "lag_hours": lag, "corr": round(float(val), 4)})
    return pd.DataFrame(rows)


def pair_ranking(tidy: pd.DataFrame) -> pd.DataFrame:
    """One row per UNORDERED pair of different columns (a column against
    itself — its autocorrelation — is excluded), at the lag where the pair
    is most strongly related, in either direction. Sorted from the most to
    the least correlated (by |corr|). col_1 / col_2 / lag_hours read as
    "col_1 at t vs col_2 at t + lag" (direction irrelevant at lag 0)."""
    pairs = tidy[tidy["col_1"] != tidy["col_2"]].copy()
    pairs["abs_corr"] = pairs["corr"].abs()
    pairs["pair"] = [frozenset(p) for p in zip(pairs["col_1"], pairs["col_2"])]
    best = pairs.loc[pairs.groupby("pair")["abs_corr"].idxmax()].drop(columns="pair")
    best["cross_market"] = best["market_1"] != best["market_2"]
    best = best.sort_values("abs_corr", ascending=False).reset_index(drop=True)
    best.insert(0, "rank", range(1, len(best) + 1))
    return best[["rank", "col_1", "col_2", "lag_hours", "corr", "abs_corr",
                 "market_1", "market_2", "cross_market"]]


MAX_RANKED_PAIRS = 200  # more pairs than this: show the top and bottom 100
CLEAN_MIN_ABS_CORR = 0.3  # pair_ranking_clean keeps only pairs with |r| >= this


def is_reservoir(col: str) -> bool:
    return "reservoir" in col


def is_forecast_actual_pair(a: str, b: str) -> bool:
    """True for a forecast and the actual of the SAME quantity: the names
    differ only by 'forecast' <-> 'actual' (e.g. c_load_forecast_mw /
    c_load_actual_mw). Forecast errors, ramps etc. are not such pairs."""
    def base(name):
        return name.replace("_forecast", "_<fa>").replace("_actual", "_<fa>")
    return a != b and base(a) == base(b) and "<fa>" in base(a)


def without_forecast_actual(ranking: pd.DataFrame) -> pd.DataFrame:
    keep = ~pd.Series([is_forecast_actual_pair(a, b) for a, b in zip(ranking["col_1"], ranking["col_2"])],
                      index=ranking.index)
    out = ranking[keep].reset_index(drop=True)
    out["rank"] = range(1, len(out) + 1)
    return out


def plot_pair_ranking(ranking: pd.DataFrame, zone, method: str, lags: list, out_path,
                      excluded_note: str = "a column with itself excluded", max_pairs: int | None = MAX_RANKED_PAIRS):
    """Horizontal bars, one per pair, from the most correlated (top) to the
    least correlated (bottom). Bar length = |corr| at the pair's strongest
    lag; colour = sign; label = pair and lag."""
    shown, n_omitted = ranking, 0
    if max_pairs and len(ranking) > max_pairs:
        half = max_pairs // 2
        shown = pd.concat([ranking.head(half), ranking.tail(half)])
        n_omitted = len(ranking) - max_pairs

    def label(r):
        if r["lag_hours"] == 0:
            return f"{r['col_1']}  ↔  {r['col_2']}"
        return f"{r['col_1']}  →  {r['col_2']}  (+{r['lag_hours']} h)"

    labels = [label(r) for _, r in shown.iterrows()]
    values = shown["abs_corr"].to_numpy()
    colors = np.where(shown["corr"].to_numpy() >= 0, "#C0392B", "#2471A3")
    y = np.arange(len(shown))
    if n_omitted:  # leave a visible gap between the top and the bottom block
        y = np.where(y >= max_pairs // 2, y + 2, y)

    fig, ax = plt.subplots(figsize=(11, max(4, 0.19 * (len(shown) + 3))))
    ax.barh(y, values, color=colors, height=0.75)
    for yi, v, r in zip(y, values, shown["corr"]):
        ax.text(v + 0.005, yi, f"{r:+.2f}", va="center", fontsize=6.5)
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=6.5)
    if n_omitted:
        ax.text(0.5, max_pairs // 2 + 0.5, f"… {n_omitted} pairs in between not shown (see "
                f"tables/pair_ranking.csv) …", ha="center", va="center", fontsize=8, style="italic")
    ax.set_ylim(y.max() + 0.6, -0.6)  # most correlated on top, no empty margin
    ax.set_xlim(0, 1.06)
    ax.set_xlabel(f"|{method.capitalize()} correlation| at the pair's strongest lag (lags checked: "
                  f"{', '.join(str(l) for l in lags)} h)", fontsize=9)
    ax.set_ylabel("Pair of columns (→ = left column leads by the lag shown)", fontsize=9)
    ax.set_title(f"{zone} — pairs ranked from most to least correlated "
                 f"({len(ranking)} pairs)\n{excluded_note}", fontsize=11)
    from matplotlib.patches import Patch
    ax.legend(handles=[Patch(color="#C0392B", label="positive correlation"),
                       Patch(color="#2471A3", label="negative correlation")],
              loc="lower right", fontsize=8, frameon=False)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    fig.tight_layout()
    fig.savefig(out_path, dpi=130)
    plt.close(fig)
    print(f"  wrote {out_path.name}")


def column_summary(tidy: pd.DataFrame, cols: list) -> pd.DataFrame:
    """One row per column: the single strongest |correlation| it has
    with ANY other column, in EITHER direction (col_1 or col_2), at ANY
    checked lag -- plus which column and lag that was. This is the
    number that actually decides "does this feature carry any linear
    relationship worth keeping, at all, within the lags checked"."""
    others = tidy[tidy["col_1"] != tidy["col_2"]].copy()
    others["abs_corr"] = others["corr"].abs()
    rows = []
    for col in cols:
        as_c1 = others[others["col_1"] == col].rename(columns={"col_2": "other"})
        as_c2 = others[others["col_2"] == col].rename(columns={"col_1": "other"})
        both = pd.concat([as_c1[["other", "lag_hours", "corr", "abs_corr"]],
                           as_c2[["other", "lag_hours", "corr", "abs_corr"]]])
        if both.empty:
            rows.append({"feature": col, "strongest_abs_corr": 0.0, "with_feature": None, "at_lag_hours": None})
            continue
        best = both.loc[both["abs_corr"].idxmax()]
        rows.append({"feature": col, "strongest_abs_corr": round(float(best["abs_corr"]), 4),
                     "with_feature": best["other"], "at_lag_hours": int(best["lag_hours"])})
    return pd.DataFrame(rows).sort_values("strongest_abs_corr").reset_index(drop=True)


# ---------------------------------------------------------------------------
# PLOTTING
# ---------------------------------------------------------------------------

def plot_heatmap(matrix: pd.DataFrame, title: str, out_path, xlabel: str, ylabel: str, cbar_label: str,
                 vmin=-1, vmax=1, cmap="RdBu_r", split: int | None = None, annotate: bool = False):
    """Heatmap of a (possibly rectangular) matrix. split: number of leading
    rows/columns in the first group (e.g. endogenous) — a black line is drawn
    after them and the second group's labels are grey. annotate: write r in
    every cell (for small matrices)."""
    nr, nc = matrix.shape
    size = max(6, 0.35 * max(nr, nc))
    fig_w, fig_h = (max(8.5, 0.9 * nc + 3.5), max(7, 0.9 * nr + 3)) if annotate else \
                   (max(7, 0.35 * nc + 3), max(5, 0.35 * nr + 3))
    fig, ax = plt.subplots(figsize=(fig_w, fig_h))
    im = ax.imshow(matrix.values, vmin=vmin, vmax=vmax, cmap=cmap, aspect="auto" if not annotate else "equal")
    ax.set_xticks(range(nc))
    ax.set_yticks(range(nr))
    tick = 9 if annotate else 7
    ax.set_xticklabels(matrix.columns, rotation=90, fontsize=tick)
    ax.set_yticklabels(matrix.index, fontsize=tick)
    if split:
        ax.axhline(split - 0.5, color="black", linewidth=1.8)
        ax.axvline(split - 0.5, color="black", linewidth=1.8)
        for lbl in ax.get_xticklabels()[split:] + ax.get_yticklabels()[split:]:
            lbl.set_color("0.4")
            lbl.set_style("italic")
    if annotate:
        for i in range(nr):
            for j in range(nc):
                v = matrix.values[i, j]
                if np.isfinite(v):
                    ax.text(j, i, f"{v:+.2f}", ha="center", va="center", fontsize=8.5,
                            color="white" if abs(v) > 0.6 else "black")
    # Big matrices get a big figure, so scale the text with it — fixed
    # 10-12 pt labels are unreadably small on a ~40-inch, 100+ feature plot.
    label_size = max(10, 0.5 * size) if not annotate else 10
    ax.set_xlabel(xlabel, fontsize=label_size)
    ax.set_ylabel(ylabel, fontsize=label_size)
    ax.set_title(title, fontsize=label_size * 1.2)
    cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cbar.set_label(cbar_label, fontsize=label_size)
    cbar.ax.tick_params(labelsize=label_size * 0.8)
    fig.tight_layout()
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=130)
    plt.close(fig)
    print(f"  wrote {Path(out_path).parent.name}/{Path(out_path).name}")


def _lag_axis_labels(lag: int, row_word: str = "Feature", col_word: str = "Feature"):
    if lag == 0:
        return f"{col_word} (same delivery hour t)", f"{row_word} (delivery hour t)"
    return f"{col_word} at hour t + {lag} h (later)", f"{row_word} at hour t (earlier)"


def plot_all_columns(lag_matrices: dict, zone, method: str, cols: list, out_dir):
    """all_columns/: every column except the reservoirs (square), and the
    reservoirs (rows, at t) against every other column (at t + lag)."""
    res = [c for c in cols if is_reservoir(c)]
    other = [c for c in cols if not is_reservoir(c)]
    cbar = f"{method.capitalize()} correlation coefficient [-1, 1]"
    for lag, mat in lag_matrices.items():
        xl, yl = _lag_axis_labels(lag)
        plot_heatmap(mat.loc[other, other],
                     f"{zone} — {method.capitalize()} correlation, lag = {lag} h"
                     + (" (reservoirs: see reservoirs_lag{}.png)".format(lag) if res else ""),
                     out_dir / f"correlation_matrix_lag{lag}.png", xlabel=xl, ylabel=yl, cbar_label=cbar)
        if res and other:
            xl, yl = _lag_axis_labels(lag, row_word="Reservoir filling")
            plot_heatmap(mat.loc[res, other],
                         f"{zone} — reservoirs vs the other columns, lag = {lag} h",
                         out_dir / f"reservoirs_lag{lag}.png", xlabel=xl, ylabel=yl, cbar_label=cbar)


OFF_SCALE_R = 0.9  # cross-correlation lines peaking above this are drawn off scale (named in the panel)
# Colours for the cross-correlation lines (one per model variable).
_CCF_COLORS = ["#0072B2", "#E69F00", "#009E73", "#CC79A7", "#56B4E9", "#D55E00", "#000000", "#999999",
               "#8C564B", "#BCBD22", "#17BECF", "#7F3C8D"]


def plot_model_correlation(df: pd.DataFrame, zone, method: str, group_col: str, model_cols: dict,
                           lags: list, out_dir):
    """model/: correlation of the model's variables (endogenous first, then
    exogenous) per lag, and the cross-correlation of every endogenous
    variable with every other model variable over all lags up to max(lags)."""
    endo, exo = model_cols["Endogenous"], model_cols["Exogenous"]
    mcols = endo + exo
    if len(mcols) < 2:
        return
    cbar = f"{method.capitalize()} correlation coefficient [-1, 1]"
    for lag in lags:
        mat = lagged_correlation_matrix(df, mcols, lag, method=method, group_col=group_col)
        xl, yl = _lag_axis_labels(lag, "Variable", "Variable")
        plot_heatmap(mat, f"{zone} — model variables, {method.capitalize()} correlation, lag = {lag} h\n"
                          f"endogenous (black labels) | exogenous (grey, italic)",
                     out_dir / f"model_correlation_lag{lag}.png", xlabel=xl, ylabel=yl, cbar_label=cbar,
                     split=len(endo), annotate=True)

    # Cross-correlation: M_k[v, e] = corr(v at t, e at t + k), so for k >= 0
    # v leads e by k hours; for k < 0 the value is M_|k|[e, v] (e leads).
    max_lag = max(lags)
    mats = {k: lagged_correlation_matrix(df, mcols, k, method=method, group_col=group_col)
            for k in range(max_lag + 1)}
    n = len(df[mcols].dropna())
    band = 1.96 / math.sqrt(n) if n else 0
    ks = np.arange(-max_lag, max_lag + 1)
    colors = {c: _CCF_COLORS[i % len(_CCF_COLORS)] for i, c in enumerate(mcols)}
    fig, axes = plt.subplots(len(endo), 1, figsize=(13, 3.1 * len(endo)), sharex=True, squeeze=False)
    handles = {}
    for ax, e in zip(axes[:, 0], endo):
        scale, off_scale = 0.0, []
        for v in mcols:
            if v == e:
                continue
            r = np.array([mats[k].loc[v, e] if k >= 0 else mats[-k].loc[e, v] for k in ks])
            (line,) = ax.plot(ks, r, color=colors[v], linewidth=1.1,
                              linestyle="-" if v in endo else "--")
            handles.setdefault(v + ("" if v in endo else "  (exogenous)"), line)
            # Near-identities (e.g. DA-BAL = DA-ID + ID-BAL, so the two balancing
            # spreads correlate ~0.99) would squash every other line: scale the
            # y-axis to the rest and name the off-scale peak instead.
            peak = int(np.nanargmax(np.abs(r)))
            if abs(r[peak]) > OFF_SCALE_R:
                off_scale.append(f"{v}: r = {r[peak]:+.2f} at k = {ks[peak]} h")
                r = np.where(np.abs(r) > OFF_SCALE_R, np.nan, r)
            scale = max(scale, float(np.nanmax(np.abs(r))))
        if scale:
            ax.set_ylim(-1.15 * scale, 1.15 * scale)
        if off_scale:
            ax.text(0.01, 0.97, "off scale: " + "; ".join(off_scale), transform=ax.transAxes,
                    fontsize=8, va="top", style="italic", color="0.3")
        ax.axhline(0, color="black", linewidth=0.6)
        ax.axvline(0, color="black", linewidth=0.6)
        if band:
            ax.axhspan(-band, band, color="0.88", zorder=0)
        for d in range(-max_lag, max_lag + 1, 24):
            if d:
                ax.axvline(d, color="0.85", linewidth=0.6, zorder=0)
        ax.set_title(f"{e}", fontsize=10)
        ax.set_ylabel("r", fontsize=9)
        ax.tick_params(labelsize=8)
        for spine in ("top", "right"):
            ax.spines[spine].set_visible(False)
    step = 24 if max_lag <= 168 else 168
    axes[-1, 0].set_xticks(np.arange(-max_lag - (-max_lag % step), max_lag + 1, step))
    axes[-1, 0].set_xlim(-max_lag, max_lag)
    axes[-1, 0].set_xlabel("Lag k [hours]:  k > 0 = the line's variable at t vs the panel's variable at t + k "
                           "(line leads);  k < 0 = the panel's variable leads", fontsize=9)
    fig_h = fig.get_size_inches()[1]
    fig.suptitle(f"{zone} — cross-correlation of each endogenous variable with the other model variables "
                 f"({method.capitalize()}; grey band = ±1.96/√n)", fontsize=12, y=1 - 0.12 / fig_h, va="top")
    fig.legend(list(handles.values()), list(handles.keys()), loc="upper center",
               bbox_to_anchor=(0.5, 1 - 0.45 / fig_h), ncol=4, frameon=False, fontsize=9)
    fig.tight_layout(rect=(0, 0, 1, 1 - 1.2 / fig_h))
    out_path = out_dir / "cross_correlation.png"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=130)
    plt.close(fig)
    print(f"  wrote {out_dir.name}/{out_path.name}")


def model_columns(model_spec: dict | None, cols: list) -> dict | None:
    """{"Endogenous": [...], "Exogenous": [...]} — the spec's variables that
    are among cols, calendar fixed effects (hour / week identifiers) left out."""
    if not model_spec:
        return None
    out = {"Endogenous": [], "Exogenous": []}
    for v in model_spec["variables"]:
        if v["role"] in out and v["column"] in cols and v.get("market") != "Calendar":
            out[v["role"]].append(v["column"])
    return out if out["Endogenous"] else None


# ---------------------------------------------------------------------------
# PER-ZONE DRIVER
# ---------------------------------------------------------------------------

def analyze_zone(df: pd.DataFrame, zone, feature_cols: list, method: str, group_col: str,
                  lags: list, min_abs_corr: float, out_dir, write_tables: bool = True,
                  model_spec: dict | None = None):
    """Writes, for one zone (or the pooled 'combined' pass):
        out_dir/pair_ranking.png          pairs from most to least correlated
        out_dir/model/                    model variables: matrix per lag + cross-correlation
        out_dir/all_columns/              matrix per lag without reservoirs + reservoirs x rest
        out_dir/tables/                   pair_ranking.csv + weak_columns.txt
                                          (only if write_tables — not for 'combined')"""
    print(f"\n--- {zone} ---")
    tables_dir = out_dir / "tables"
    out_dir.mkdir(parents=True, exist_ok=True)
    if write_tables:
        tables_dir.mkdir(parents=True, exist_ok=True)

    cols = drop_constant_columns(df, feature_cols, label=str(zone))
    if len(cols) < 2:
        print(f"  fewer than 2 usable columns for {zone} -- skipping.")
        return

    lag_matrices = {}
    for lag in lags:
        print(f"  computing lag={lag}h correlation matrix ({len(cols)} columns)...")
        lag_matrices[lag] = lagged_correlation_matrix(df, cols, lag, method=method, group_col=group_col)
    plot_all_columns(lag_matrices, zone, method, cols, out_dir / "all_columns")
    model_cols = model_columns(model_spec, cols)
    if model_cols:
        plot_model_correlation(df, zone, method, group_col, model_cols, lags, out_dir / "model")

    tidy = tidy_all_pairs_all_lags(lag_matrices)
    tidy["market_1"] = tidy["col_1"].map(market_of)
    tidy["market_2"] = tidy["col_2"].map(market_of)

    ranking = pair_ranking(tidy)
    if write_tables:
        ranking.to_csv(tables_dir / "pair_ranking.csv", index=False)
    plot_pair_ranking(ranking, zone, method, lags, out_dir / "pair_ranking.png")
    # Clean ranking: without "forecast vs its own actual" pairs (near-identical
    # by nature, they crowd the top), without reservoir-vs-reservoir pairs (the
    # reservoirs move together) and without weak pairs (|r| < CLEAN_MIN_ABS_CORR).
    # A reservoir paired with a non-reservoir column stays if it is strong enough.
    no_fa = without_forecast_actual(ranking)
    res_res = no_fa["col_1"].map(is_reservoir) & no_fa["col_2"].map(is_reservoir)
    strong = no_fa["abs_corr"] >= CLEAN_MIN_ABS_CORR
    clean = no_fa[~res_res & strong].reset_index(drop=True)
    clean["rank"] = range(1, len(clean) + 1)
    n_weak = int((~res_res & ~strong).sum())
    plot_pair_ranking(clean, zone, method, lags, out_dir / "pair_ranking_clean.png",
                      excluded_note=f"self-pairs, {len(ranking) - len(no_fa)} forecast vs actual pair(s), "
                                    f"{int(res_res.sum())} reservoir vs reservoir pairs\n"
                                    f"and {n_weak} pairs with |r| < {CLEAN_MIN_ABS_CORR} excluded")

    col_summary = column_summary(tidy, cols)
    weak = col_summary[col_summary["strongest_abs_corr"] < min_abs_corr]
    if write_tables:
        with open(tables_dir / "weak_columns.txt", "w") as f:
            f.write(f"Columns whose strongest |correlation| with any other column, in either\n"
                    f"direction, at any of lags {lags}, is below {min_abs_corr}.\n")
            f.write("This is informational only -- nothing was dropped from the dataframe.\n\n")
            for _, row in weak.iterrows():
                f.write(f"{row['feature']}\t(best |corr| = {row['strongest_abs_corr']} "
                        f"with {row['with_feature']} at lag {row['at_lag_hours']}h)\n")
        print(f"  wrote tables/pair_ranking.csv and tables/weak_columns.txt ({len(weak)} flagged)")
    print("  top 5 pairs:")
    print(ranking.head(5)[["col_1", "col_2", "lag_hours", "corr"]].to_string(index=False))


# ---------------------------------------------------------------------------
# ENTRY POINT
# ---------------------------------------------------------------------------

def run_correlation_analysis(input_arg: str, lags: list = (0, 1, 4, 24, 168), method: str = "pearson",
                             min_abs_corr: float = 0.10, time_col: str | None = None,
                             model_spec: dict | None = None,
                             group_col: str | None = None):
    """The "correlation" step of main.py (also what the CLI below runs).
    input_arg: dataframe name (e.g. df_2025), filename, or path."""
    lags = list(lags)
    df, time_col, group_col, feature_cols, stem = load_dataframe(
        input_arg, time_col, group_col)
    df = df.sort_values(time_col).reset_index(drop=True)  # lag = rows only makes sense on a sorted, uniform grid

    base_out = PLOTS_DIR / stem / "correlation"
    print(f"Writing correlation output to {base_out}")
    print(f"Lags (hours): {lags}")

    zones = sorted(df[group_col].astype(str).unique())
    for zone in zones:
        zone_df = df[df[group_col].astype(str) == zone].sort_values(time_col).reset_index(drop=True)
        analyze_zone(zone_df, zone, feature_cols, method, group_col, lags,
                     min_abs_corr, base_out / zone, model_spec=model_spec)

    # "Combined" pass: both zones pooled into one matrix, on top of the
    # per-zone ones above -- see the WHY BOTH PER-ZONE AND COMBINED note
    # in the module docstring for the caveat on how to read this one.
    analyze_zone(df, "combined", feature_cols, method, group_col, lags,
                 min_abs_corr, base_out / "combined", write_tables=False, model_spec=model_spec)

    print(f"\nDone. See {base_out} for one subfolder per zone plus 'combined'.")


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("input", help="Dataframe name (e.g. df_2025), filename, or full path to a dataframe CSV.")
    parser.add_argument("--lags", type=int, nargs="+", default=[0, 1, 4, 24, 168],
                         help="Lags in hours to compute a correlation matrix for (default: 0 1 4 24 168).")
    parser.add_argument("--method", choices=["pearson", "spearman"], default="pearson")
    parser.add_argument("--min-abs-corr", type=float, default=0.10,
                         help="Threshold for flagging weakly-correlated columns (default 0.10).")
    parser.add_argument("--time-col", default=None)
    parser.add_argument("--group-col", default=None)
    args = parser.parse_args()
    run_correlation_analysis(args.input, args.lags, args.method, args.min_abs_corr,
                             args.time_col, args.group_col)


if __name__ == "__main__":
    main()