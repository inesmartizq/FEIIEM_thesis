"""
analysis_summary.py

Writes plots/<name>/ANALYSIS_SUMMARY.md — the "summary" step of main.py,
run last. A compact Markdown handoff meant to be pasted into (or read by)
another AI assistant, so it knows what has already been built, checked and
plotted for a dataframe and doesn't redo it.

Everything that can be is read from the code or from the outputs of the
earlier steps (dataframe CSV, documentation workbook, plots/stats/
correlation folders), so the summary can't drift from what was actually
produced. PROJECT_FACTS below is the exception: hand-written facts that
were investigated and settled during the project — keep it up to date.
"""

from datetime import datetime
from pathlib import Path

import pandas as pd

import dataframe_building as building
from analysis_utils import PLOTS_DIR

# Facts that were checked and settled. Written so another assistant does
# not re-investigate them. Update when something here changes.
PROJECT_FACTS = [
    "Timestamps: EVERY source is genuine UTC (all Nord Pool feeds and ENTSO-E/Energinet). Verified "
    "2026-10-07 from the raw responses (delivery day CET starts at 23:00Z the day before) and three data "
    "checks (imbalance = DA price in 99.7 % of no-regulation hours; ID VWAP tracks DA best unshifted; "
    "solar peaks at solar noon UTC). An earlier '-1 h Nord Pool CET fix' on mFRR/intraday/forecasts was "
    "WRONG (it put those columns one hour early) and was removed; any result produced before then "
    "(e.g. 'intraday leads DA by 1 h') is invalid.",
    "All sources are hourly in the dataframe; 15-min data was aggregated in the import scripts "
    "(MW values: hourly mean; intraday VWAPs: volume-weighted; intraday volumes: summed).",
    "Flow columns that are always 0 in one zone are STRUCTURAL, not a bug: a zone's own border "
    "(da_flow_dk1_* in DK1 rows) and borders it doesn't have (SE4 for DK1; NL/SE3/NO2 for DK2). "
    "Drop them per zone before a single-zone VAR (dataframe_building.filter_to_area).",
    "Flow net position sign: positive = row zone is a net IMPORTER (checked: corr = -1 with "
    "export - import; matches the Nord Pool 'Net Exchange' chart).",
    "b_dominating_direction: Up = +1, Down = -1, empty = 0 (no regulation: in 2022-2024 imbalance "
    "price = DA price and zero mFRR activation in 99-100 % of empty hours; 2025 less clean, 40 % / "
    "52 %). Hourly value = majority of the 15-min values in that hour; ties broken by that hour's net "
    "mFRR activation, not alphabetically.",
    "Imbalance price (P_BAL): equals the up price in up-regulation hours, the down price in down hours "
    "and the DA price without regulation (2022-2024: 100 / 100 / 99.7 %); from 2025 it is the hourly "
    "mean of 15-min prices and cannot be rebuilt from an hourly direction.",
    "Forecast errors (all c_*_err) are FORECAST - ACTUAL (positive = over-forecast), the baseline "
    "literature convention. Intraday hours with zero traded volume have no VWAP; for the spreads they "
    "take the DA price inside the spread calculation (no separate filled column), as in the "
    "literature.",
    "Derived lag/rolling features are computed per bidding zone, trailing windows ending at t "
    "(no look-ahead), no interpolation; the grid is built a week early (warm-up) and trimmed.",
    "One representative price per market is used for price-dynamics features (avoids near-duplicates); "
    "old id_da_spread / b_da_spread were removed as sign-flipped duplicates of the x_ spreads.",
    "No percentage changes for prices/spreads (can be 0 or negative); renewables totals are computed "
    "from components in DERIVED_FEATURES, not taken from the source's own totals.",
    "The literature's price-based bottleneck indicator (zone DA price != Nord Pool system price) was 1 in "
    "99.6-99.9 % of hours for DK1/DK2 in 2022-2025 and has been replaced by cross-border flows "
    "(da_flow_<counterpart>_net_export_mw, Nord Pool day-ahead scheduled exchange, positive = export); "
    "per zone only connections with >= 5 % of the zone's total mean |flow| enter the VAR.",
    "Reservoir filling (Nord Pool, weekly, % of capacity) for NO, SE, FI and NO1-NO5 / SE1-SE4: weekly "
    "value applied to every hour of its own Monday-Sunday week (look-ahead up to ~7 days, flagged); "
    "copied to both DK zones. NO differs from the sum of NO1-NO5 by up to 0.67 % in 19 of 300 weeks; SE "
    "matches its sub-areas exactly. Only 2022-2025: no historical median for the hydro deviation.",
    "Leakage/timing: each column's delivery time vs. availability time and a leakage flag are in the "
    "documentation workbook's metadata sheet. Forecast publication times are an ASSUMPTION (D-1; the "
    "data has no issue timestamp).",
]

NOT_YET_DONE = [
    "Correlation-break and autocorrelation-break analysis (planned separately; only mean and "
    "variance breaks of the three market prices are done).",
    "Stationarity tests (ADF / KPSS) and any differencing decisions.",
    "Granger causality tests, VAR lag-order selection and VAR estimation.",
    "Final feature selection (the correlation and duplicate outputs are inputs to it, not the decision).",
]

PLOT_DESCRIPTIONS = {
    "timeseries": "Model variables only, split into endogenous/ and exogenous/: hourly values, "
                  "one panel per zone (without a model spec: every feature, one figure per column family).",
    "distributions": "Histogram per variable, DK1 vs DK2 overlaid (endogenous/ and exogenous/).",
    "seasonals/hour_of_day": "24 h profile (Copenhagen local time), one panel per zone: min-max, 10-90 % and 25-75 % bands across days, mean (solid) and median (dashed).",
    "seasonals/hour_of_day_by_season": "24 h profile per meteorological season, one file per zone.",
    "seasonals/hour_of_week": "Average 7-day profile: 168 hourly means, Mon -> Sun.",
    "seasonals/month_of_year": "Mean per calendar month (years pooled).",
    "stats": "Per role (endogenous/, exogenous/): std & variance within each day / week / month, "
             "7-day rolling std, mean absolute hourly change.",
    "correlation": "Per zone + pooled: pair ranking (most to least correlated pair of different "
                   "columns, at its strongest lag; pair_ranking_clean: without forecast-vs-actual pairs, "
                   "reservoir-vs-reservoir pairs and |r| < 0.3), "
                   "model/: endogenous + exogenous correlation matrix per lag and cross-correlation "
                   "curves over all lags; all_columns/: matrix per lag without the reservoirs plus "
                   "reservoirs x other columns; per-zone numbers in tables/.",
    "structural_breaks": "Mean and variance breaks of the DA / ID / balancing prices per zone "
                         "(CUSUM + HAC, binary segmentation): STRUCTURAL_BREAKS.md (break table, "
                         "classification), plots.",
}


def _structural_breaks_section(name: str) -> list[str]:
    """The break table and regime classification, copied from
    structural_breaks/STRUCTURAL_BREAKS.md (the step writes no CSVs)."""
    report = PLOTS_DIR / name / "structural_breaks" / "STRUCTURAL_BREAKS.md"
    if not report.exists():
        return ["- Not run."]
    out = ["Statistical detection only (method and caveats: `structural_breaks/STRUCTURAL_BREAKS.md`). "
           "Daily series; mean = CUSUM on daily mean price, variance = CUSUM on log within-day "
           "variance; HAC long-run variance; binary segmentation.", ""]
    text = report.read_text(encoding="utf-8")
    start, end = text.find("## Detected breaks"), text.find("## Reading this")
    if start < 0:
        return out + ["- Report has no break table."]
    body = text[start:end if end > start else None].strip()
    return out + [body.replace("## ", "### "), ""]


def _fmt(x, digits=2):
    if pd.isna(x):
        return ""
    return f"{x:,.{digits}f}"


def _table(df: pd.DataFrame) -> str:
    """Plain Markdown table (no tabulate dependency)."""
    cols = list(df.columns)
    lines = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for _, row in df.iterrows():
        lines.append("| " + " | ".join(str(v) for v in row.values) + " |")
    return "\n".join(lines)


def _columns_section(df: pd.DataFrame) -> list[str]:
    derived = [c for c in df.columns if c in building.DERIVED_FEATURES]
    source = [c for c in df.columns if c not in building.KEY and c not in derived]
    groups = {"da_": "Day-ahead", "id_": "Intraday", "b_": "Balancing", "c_": "Fundamentals",
              "x_": "Cross-market", "fe_": "Calendar (fixed-effect identifiers)"}
    out = [f"- **{len(df.columns)} columns**: {len(building.KEY)} key ({', '.join(building.KEY)}), "
           f"{len(source)} from sources, {len(derived)} derived."]
    for prefix, name in groups.items():
        cols = [c for c in df.columns if c.startswith(prefix)]
        if cols:
            out.append(f"- **{name}** (`{prefix}*`, {len(cols)}): " + ", ".join(f"`{c}`" for c in cols))
    return out


def _derived_config_section() -> list[str]:
    phys = ", ".join(f"`{c}` ({'/'.join(ops)})" for c, ops in building.PHYSICAL_VARIABILITY.items())
    spreads = ", ".join(f"`x_{a}_{b}_spread`" for a, b in building.MARKET_SPREADS)
    return [
        "- Representative prices: " + ", ".join(f"{m}=`{c}`" for m, c in building.MARKET_PRICES.items())
        + f"; each gets {', '.join(building.PRICE_OPS)}.",
        f"- Cross-market spreads: {spreads}, each with `_abs` and `_std_24`.",
        f"- Physical ramp/variability: {phys}.",
        f"- Rolling windows need >= {building.ROLLING_MIN_FRACTION:.0%} of the window observed; "
        f"warm-up {building.WARMUP_HOURS} h before the start date.",
    ]


def _documentation_findings(name: str) -> list[str]:
    path = building.DOCUMENTATION_DIR / f"{name}_documentation.xlsx"
    if not path.exists():
        return ["- Documentation workbook not found (documentation step not run)."]
    meta = pd.read_excel(path, sheet_name="metadata")
    out = [f"- Workbook: `{path.relative_to(building.PROJECT_ROOT).as_posix()}` — sheets README, metadata "
           f"(meaning, unit, delivery vs availability time, leakage, source, ...), distribution "
           f"(mean/median/std/quantiles/skew/kurtosis/zero/negative/extreme %, per zone)."]
    leaky = meta.loc[meta["Potential leakage"] == "Yes", "Feature"].tolist()
    out.append(f"- Columns flagged potential leakage (not known before delivery): {len(leaky)} of "
               f"{len(meta) - len(building.KEY)}.")
    pairs = {}
    for _, r in meta[meta["Suspected duplicates"] == "Yes"].iterrows():
        for item in str(r["Suspected duplicates detail"]).split("; "):
            other, corr = item.split(" (")
            pairs.setdefault(frozenset([r["Feature"], other]), corr.rstrip(")"))
    if pairs:
        out.append("- Suspected duplicate pairs (|r| >= 0.99): " + "; ".join(
            f"`{a}` ~ `{b}` ({corr})" for (a, b), corr in
            ((sorted(p), c) for p, c in pairs.items())))
    miss = meta[meta["Missingness %"].fillna(0) > 1].sort_values("Missingness %", ascending=False)
    if len(miss):
        out.append("- Missingness > 1 %: " + ", ".join(
            f"`{r['Feature']}` {r['Missingness %']:.1f} %" for _, r in miss.iterrows()))
    return out


def _plots_section(name: str) -> list[str]:
    base = PLOTS_DIR / name
    if not base.exists():
        return ["- No plots folder yet."]
    out = []
    for rel, desc in PLOT_DESCRIPTIONS.items():
        folder = base / rel
        if folder.exists():
            n_png = len(list(folder.rglob("*.png")))
            n_csv = len(list(folder.rglob("*.csv")))
            out.append(f"- `plots/{name}/{rel}/` — {n_png} PNG, {n_csv} CSV. {desc}")
    return out


def _stats_section(df: pd.DataFrame, model_spec: dict | None) -> list[str]:
    """Mean / std / variance / mean absolute hourly change of the model's
    variables (or the default key features), computed here from the
    dataframe — the stats step writes no CSVs."""
    from dataframe_documentation import column_units
    from visualize_dataframe import DEFAULT_STATS_FEATURES, _stats_summary, model_variables

    if model_spec:
        features = [c for c, _, _ in model_variables(model_spec, df)]
    else:
        features = [c for c in DEFAULT_STATS_FEATURES if c in df.columns]
    if not features:
        return ["- No features."]
    units = column_units(features, building.SOURCES, building.DERIVED_FEATURES)
    s, _ = _stats_summary(df, "datetime_utc", "bidding_zone", features, units)
    s = s[s["scope"] == "all"]
    tbl = pd.DataFrame({
        "feature": s["feature"], "unit": s["unit"].fillna(""),
        "mean": s["mean"].map(_fmt), "std": s["std"].map(_fmt),
        "variance": s["variance"].map(lambda v: _fmt(v, 0)),
        "mean abs 1h change": s["mean_abs_change_1h"].map(_fmt),
    })
    return ["Both zones pooled, hourly values:", "", _table(tbl)]


def _leaf_inputs(col: str) -> frozenset:
    """The source columns a column is ultimately built from (itself, for a
    source column) — e.g. x_da_bal_spread_std_24 -> {da_price, b_imbalance_price}."""
    cfg = building.DERIVED_FEATURES.get(col)
    if cfg is None:
        return frozenset([col])
    return frozenset().union(*(_leaf_inputs(c) for c in cfg["inputs"]))


def _informative_pairs(best: pd.DataFrame, top_n: int) -> pd.DataFrame:
    """Drop mechanical pairs (the two columns share a source input, e.g. a
    spread's volatility vs. the price it contains) and list a lag-0 pair
    once instead of in both directions."""
    rows, seen = [], set()
    for _, r in best.iterrows():
        if _leaf_inputs(r["col_1"]) & _leaf_inputs(r["col_2"]):
            continue
        key = (frozenset([r["col_1"], r["col_2"]]), 0) if r["lag_hours"] == 0 else \
              ((r["col_1"], r["col_2"]), r["lag_hours"])
        if key in seen:
            continue
        seen.add(key)
        rows.append(r)
        if len(rows) == top_n:
            break
    return pd.DataFrame(rows)


def _correlation_section(name: str, top_n: int = 10) -> list[str]:
    base = PLOTS_DIR / name / "correlation"
    if not base.exists():
        return ["- Not run."]
    out = ["Pairs whose two columns share a source input (e.g. a spread's volatility vs. the price "
           "it contains) are left out as mechanical; a lag-0 pair is listed once.", ""]
    for zone_dir in sorted(p for p in base.iterdir() if p.is_dir()):
        ranking = zone_dir / "tables" / "pair_ranking.csv"
        if not ranking.exists():
            continue
        r = pd.read_csv(ranking)
        b = _informative_pairs(r[r["cross_market"]], top_n)
        out += [f"**{zone_dir.name}** — strongest cross-market pairs (col_1 at t -> col_2 at t + lag):", "",
                _table(pd.DataFrame({"col_1": b["col_1"], "col_2": b["col_2"],
                                     "lag (h)": b["lag_hours"], "r": b["corr"].map(lambda v: f"{v:+.3f}")})),
                ""]
        weak = zone_dir / "tables" / "weak_columns.txt"
        if weak.exists():
            names = [ln.split("\t")[0] for ln in weak.read_text(encoding="utf-8").splitlines()
                     if "\t" in ln]
            out += [f"Weakly related to everything (max |r| below threshold): "
                    f"{', '.join(f'`{n}`' for n in names) if names else 'none'}", ""]
    return out or ["- Not run."]


def _model_spec_section(spec: dict | None) -> list[str]:
    if spec is None:
        return ["- No model spec: exploratory dataframe with all columns of the selected markets."]
    rows = [{"role": v["role"], "market": v["market"], "variable": v["name"],
             "column": f"`{v['column']}`" if v["column"] else "—", "definition": v["definition"]}
            for v in spec["variables"]]
    inputs = "; ".join(f"{m}: " + ", ".join(f"`{c}`" for c in cols) for m, cols in spec["inputs"].items())
    return [f"**{spec['title']}** — full table incl. sources and deviations from the literature in the "
            f"documentation workbook's `model_variables` sheet (`src/model_specs.py`).", "",
            _table(pd.DataFrame(rows)), "",
            f"- Inputs (role 'Input': raw series the variables are built from, not model variables): {inputs}.",
            *[f"- {n}" for n in spec["notes"]], ""]


def write_analysis_summary(name: str, cfg: dict, model_spec: dict | None = None) -> Path:
    df = pd.read_csv(building.OUTPUT_DIR / f"{name}.csv", usecols=None)
    df["datetime_utc"] = pd.to_datetime(df["datetime_utc"], utc=True)
    markets = cfg.get("markets") or list(building.MARKETS)

    lines = [
        f"# Analysis summary — `{name}`",
        "",
        f"_Generated {datetime.now():%Y-%m-%d %H:%M} by `main.py` (step 6). Purpose: tell another "
        f"assistant what has already been built, verified and plotted, so it is not repeated._",
        "",
        "## 1. Dataframe",
        f"- File: `data/dataframes/{name}.csv` — panel, one row per (delivery hour UTC, bidding zone).",
        f"- Period: {df['datetime_utc'].min():%Y-%m-%d %H:%M} to {df['datetime_utc'].max():%Y-%m-%d %H:%M} UTC; "
        f"{len(df):,} rows; zones: {', '.join(sorted(df['bidding_zone'].unique()))}.",
        f"- Markets selected: {', '.join(markets)}.",
        *_columns_section(df),
        "",
        "### Model specification (endogenous / exogenous)",
        *_model_spec_section(model_spec),
        "",
        "## 2. Pipeline (code)",
        "- `main.py` (project root): configure DATAFRAMES / STEPS, then build -> documentation -> "
        "visualisation -> correlation -> structural breaks -> this summary.",
        "- `src/dataframe_building.py`: SOURCES, MARKETS, DERIVED_FEATURES (one registry each).",
        "- `src/dataframe_documentation.py`: metadata + distribution workbook.",
        "- `src/visualisation/visualize_dataframe.py`, `src/statsistics/correlation_analysis.py`.",
        "- `src/imports/*.py`: download + cache raw data -> `data/processed/` (not run by main.py).",
        "",
        "### Derived feature configuration",
        *_derived_config_section(),
        "",
        "## 3. Settled facts and decisions (do not re-investigate)",
        *[f"- {fact}" for fact in PROJECT_FACTS],
        "",
        "## 4. Documentation workbook findings",
        *_documentation_findings(name),
        "",
        "## 5. Plots and tables produced",
        *_plots_section(name),
        "",
        "## 6. Statistics of the model variables" if model_spec else "## 6. Key-feature statistics",
        *_stats_section(df, model_spec),
        "",
        "## 7. Correlation headline",
        *_correlation_section(name),
        "## 8. Structural breaks (prices)",
        *_structural_breaks_section(name),
        "## 9. Not done yet",
        *[f"- {item}" for item in NOT_YET_DONE],
        "",
    ]
    out_path = PLOTS_DIR / name / "ANALYSIS_SUMMARY.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"  Saved {out_path}")
    return out_path
