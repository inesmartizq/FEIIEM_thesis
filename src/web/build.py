"""
build.py — the dashboard for the supervisors (the "web" step of main.py): a
folder of static files, web/<name>/, opened in a browser (index.html) and
shared as a zip. Nothing is uploaded anywhere. It reads the dataframe and the
outputs of the other steps and recomputes nothing, so it rebuilds in seconds:

    python main.py baseline_2025 --only web

FILES (web/<name>/)
    index.html, assets/   the page, its style (style.css), its logic (app.js)
                          and the chart library (plotly.min.js, from the
                          plotly Python package, so the page works offline)
    data/site.js          everything but the hourly values: sections, pipeline,
                          variables with their metadata and statistics
    data/series/<col>.js  the hourly values of one variable, loaded when it is
                          opened
The data are .js files (window.SITE = ...), not .json: a browser opening a
local file may refuse to read a .json file next to it, but runs a script.

SECTIONS, in three parts
  1 Hypothesis         step 1: the forecast errors (forecast_errors step): their size,
                       sign and repetition, hour by hour and summarised; step 2: what
                       the forecast errors do to the price spreads: an error and a spread
                       on one time axis, large errors by sign and the spread's mean in
                       them (error_spreads step). The shocks_and_breaks data are in
                       SITE.hypothesis, not shown
  2 VARX model
    Overall pipeline   the steps and their key facts; each links to its section
    Data overview      the model variables and their inputs, in folders by
                       theme: hourly series per zone (every value on hover),
                       source, definition, statistics (no CSV download: the
                       page may go online, and Nord Pool limits redistribution)
    VARX tests         stationarity, lag selection and residual checks, from the
                       CSV files of those steps (plots/<name>/...), with their
                       formulas
    VARX results       what the hypothesis expects (expected_signs, from main.py),
                       the main results, the responses over time and the Granger
                       decisions that change with the lag structure; the rest
                       (models, method, comparisons, all robustness tables) folded
                       under Details; from the CSV files of the varx step
  3 Next steps         the open questions (flags.py) and the next stage
The formulas are drawn by matplotlib's mathtext into data/math/<key>.svg, so
the page needs no maths library and no internet.
The notes in flags.py are shown as coloured numbered circles: learnings (green),
questions (blue) and limitations (yellow); hovering one shows its text.
"""

import json
import math
import shutil
from datetime import datetime
from pathlib import Path

import matplotlib
import pandas as pd
from matplotlib.font_manager import FontProperties
from matplotlib.mathtext import math_to_image

from common import varies, zone_frame, zones
from dataframe.building import CALENDAR_PREFIX, DERIVED_FEATURES, PROJECT_ROOT, Spec
from dataframe.documentation import LITERATURE, _MetadataResolver
from web.flags import LIMITATIONS, POINTS

FOLDERS = []  # writes web/<name>/, not plots/<name>/
WEB_DIR = PROJECT_ROOT / "web"
ASSETS = Path(__file__).resolve().parent / "assets"

# folders of the data overview: the first theme whose rule matches a column
THEMES = [
    ("Price spreads", lambda c: c.startswith("x_")),
    ("Prices and volumes", lambda c: c.startswith(("da_price", "id_", "b_"))),
    ("Wind", lambda c: c.startswith("c_wind")),
    ("Demand", lambda c: c.startswith("c_load")),
    ("Hydro", lambda c: c.startswith("c_reservoir")),
    ("Cross-border flows", lambda c: c.startswith("da_flow")),
    ("Calendar dummies", lambda c: c.startswith(CALENDAR_PREFIX)),
]
DECIMALS = 3  # hourly values in the data files

# the formulas of the page (matplotlib mathtext, a subset of LaTeX)
EQUATIONS = {
    "varx": r"y_t = c + \sum_{i=1}^{p} A_i\, y_{t-i} + B\, x_t + D\, d_t + u_t",
    "adf": r"\Delta y_t = \alpha + \gamma\, y_{t-1} + \sum_{j=1}^{k} \delta_j\, \Delta y_{t-j} + \varepsilon_t"
           r"\qquad H_0:\ \gamma = 0\ \ \mathrm{(unit\ root)}",
    "kpss": r"\eta = \dfrac{1}{T^2\,\hat{\sigma}^2_{LR}} \sum_{t=1}^{T} S_t^2,\quad S_t = \sum_{s=1}^{t} \hat{e}_s"
            r"\qquad H_0:\ \mathrm{stationary}",
    "lrv": r"\hat{\sigma}^2_{LR}(\ell) = \hat{\gamma}_0 + 2\sum_{j=1}^{\ell}\left(1 - \dfrac{j}{\ell + 1}\right)\hat{\gamma}_j,"
           r"\qquad \hat{\gamma}_j = \dfrac{1}{T}\sum_{t=j+1}^{T}\hat{e}_t\,\hat{e}_{t-j}",
    "decision": r"\mathrm{ADF\ rejects:}\ p_{\mathrm{ADF}} < \alpha,\qquad \mathrm{KPSS\ rejects:}\ p_{\mathrm{KPSS}} < \alpha",
    "dummies": r"y_t = \beta_0 + \sum_{h} \beta_h\, d^{hour}_{h,t} + \sum_{m} \beta_m\, d^{month}_{m,t} + e_t",
    "ic": r"\mathrm{IC}(p) = \ln\,|\hat{\Sigma}_u(p)| + \dfrac{c_T}{T}\, p K^2",
    "penalty": r"c_T = 2\ \ \mathrm{(AIC)},\qquad 2 \ln \ln T\ \ \mathrm{(HQ)},\qquad \ln T\ \ \mathrm{(BIC)}",
    "lm": r"\hat{u}_t = \Pi\, z_t + D_1 \hat{u}_{t-1} + \cdots + D_h \hat{u}_{t-h} + v_t"
          r"\qquad H_0:\ D_1 = \cdots = D_h = 0",
    "lm_robust": r"\mathrm{LM} = \left(\sum_t g_t\right)^{\prime}\left(\sum_t g_t\, g_t^{\prime}\right)^{-1}"
                 r"\left(\sum_t g_t\right),\qquad g_t = \hat{u}_t \otimes q_t",
    "lm_standard": r"\mathrm{LM}_{\mathrm{standard}} = T\,\left(K - \mathrm{tr}\left(\hat{\Sigma}_u^{-1}\,"
                   r"\hat{\Sigma}_v\right)\right)",
    "lm_limit": r"\chi^2_n = Z_1^2 + \cdots + Z_n^2,\quad Z_i \sim N(0, 1);\qquad"
                r" \mathrm{P}\left(\chi^2_{hK^2} > c\right) = 0.05;\qquad p = \mathrm{P}\left(\chi^2_{hK^2} \geq \mathrm{LM}\right)",
    "stability": r"\mathrm{det}(I_K - A_1 z - \cdots - A_p z^p) = 0\quad \mathrm{only\ for}\quad |z| > 1",
    "ramp": r"e_t - e_{t-1} = \Delta F_t - r_t,\qquad e_t = F_t - W_t,\quad r_t = W_t - W_{t-1}",
    "granger": r"y_{b,t} = c_b + \sum_{i=1}^{p}\sum_{k=1}^{K} a_{bk,i}\, y_{k,t-i} + \beta_b^{\prime} x_t"
               r" + \delta_b^{\prime} d_t + u_{b,t}\qquad H_0:\ a_{ba,1} = \cdots = a_{ba,p} = 0",
    "wald": r"W = (R\hat{\theta}_b)^{\prime}\,[R\hat{V}R^{\prime}]^{-1}\,(R\hat{\theta}_b),\qquad"
            r" \hat{V} = (X^{\prime}X)^{-1}\left(\sum_t x_t x_t^{\prime}\,\hat{u}_{b,t}^2\right)(X^{\prime}X)^{-1}",
    "bootstrap": r"y^{*}_{b,t} = x_{0,t}^{\prime}\hat{\theta}_0 + \eta_{k(t)}\,\hat{u}_{0,t},\quad \eta_k = \pm 1,"
                 r"\qquad p = \dfrac{1 + \#\{W^{*} \geq W\}}{B + 1}",
    "ma": r"y_t = \mu_t + \sum_{h=0}^{\infty} \Phi_h\, u_{t-h},\qquad \Phi_0 = I_K,\quad"
          r" \Phi_h = \sum_{i=1}^{\mathrm{min}(h,p)} \Phi_{h-i} A_i",
    "cholesky": r"\Sigma_u = P P^{\prime},\qquad \varepsilon_t = P^{-1} u_t,\qquad \Theta_h = \Phi_h P",
    "error": r"e_t = F_t - A_t\qquad F_t:\ \mathrm{day\ ahead\ forecast},\quad A_t:\ \mathrm{actual}",
    "ram": r"\mathrm{RAM} = F_{\mathrm{max}} + F_{\mathrm{RA}} - F_{\mathrm{RM}} - F_0 - F_{\mathrm{AAC}},\qquad"
           r" F_0 = F_{\mathrm{ref}} - \mathrm{PTDF}\cdot NP_{\mathrm{ref}}",
    "spreads": r"S^{\mathrm{DA}-\mathrm{ID}}_t = P^{\mathrm{DA}}_t - P^{\mathrm{ID}}_t,\qquad"
               r" S^{\mathrm{ID}-\mathrm{BAL}}_t = P^{\mathrm{ID}}_t - P^{\mathrm{BAL}}_t,\qquad"
               r" S^{\mathrm{DA}-\mathrm{BAL}}_t = P^{\mathrm{DA}}_t - P^{\mathrm{BAL}}_t",
    "large_sign": r"\mathrm{large\ error:}\ |e_t| > Q_q(|e|)\qquad e_t > 0:\ \mathrm{over},\quad e_t < 0:\ \mathrm{under}",
    "around": r"\bar{s}_h = \dfrac{1}{n}\sum_{j=1}^{n} s_{t_j+h}\qquad"
              r" t_j:\ \mathrm{the\ first\ hour\ of\ run}\ j",
    "lag_corr": r"r_k = \mathrm{corr}\,(e_t,\ s_{t+k})",
    "tenths": r"\bar{s}_{g,k} = \mathrm{mean}\,\{\,s_{t+k}:\ e_t\ \mathrm{in\ decile}\ g\,\}",
    "normalised": r"\dfrac{e_t}{\bar{A}}\times 100\ \%,\qquad \bar{A} = \dfrac{1}{T}\sum_{t=1}^{T} A_t"
                  r"\ =\ \dfrac{\mathrm{total\ over\ the\ year}}{\mathrm{hours\ of\ the\ year}}",
    "robust_z": r"z_t =\dfrac{e_t - \mathrm{median}_r(e)}{1.4826\;\mathrm{MAD}_r(e)},\qquad"
                r" \mathrm{MAD}_r(e) = \mathrm{median}_r\,|e_t - \mathrm{median}_r(e)|,\qquad \mathrm{shock:}\ |z_t| > c",
    "cusum": r"\mathrm{CUSUM} = \max_k\ \dfrac{\left|\sum_{t=1}^{k}(x_t - \bar{x})\right|}{\sqrt{n\,\hat{\sigma}^2_{LR}}}",
    "event": r"D_h = \dfrac{1}{n}\sum_{k=1}^{n}\left(s_{t_k+h} - \bar{s}_{\mathrm{hour}(t_k+h)}\right)"
             r" \;\pm\; 1.96\,\dfrac{\mathrm{sd}_h}{\sqrt{n}}",
}
# the CSV files of the test steps, under plots/<name>/
TEST_FILES = {
    "levels": "stationarity_tests/levels.csv", "after": "stationarity_tests/after_dummies.csv",
    "robustness": "stationarity_tests/robustness.csv",
    "robustness_after": "stationarity_tests/robustness_after_dummies.csv", "criteria": "lag_selection/criteria.csv",
    "orders": "lag_selection/lag_orders.csv", "checks": "residual_checks/checks.csv",
    "variance": "residual_checks/variance.csv", "weekly": "residual_checks/weekly.csv",
    "quarters": "residual_checks/weekly_quarters.csv", "acf": "residual_checks/autocorrelation.csv",
}
# the CSV files of the varx step, under plots/<name>/
RESULT_FILES = {
    "models": "varx/models.csv", "equations": "varx/equations.csv", "correlations": "varx/correlations.csv",
    "granger": "varx/granger.csv", "structures": "varx/robustness_structures.csv",
    "irf_robustness": "varx/irf_robustness.csv", "irf": "varx/impulse_responses.csv",
}
# the CSV files of the forecast_errors step, under plots/<name>/
ERROR_FILES = {
    "summary": "forecast_errors/summary.csv", "hour_month": "forecast_errors/hour_month.csv",
    "runs": "forecast_errors/runs.csv", "large": "forecast_errors/large_by_month.csv",
}
# the CSV files of the error_spreads step, under plots/<name>/
SPREAD_FILES = {"means": "error_spreads/spreads.csv", "around": "error_spreads/around.csv",
                "correlation": "error_spreads/correlation.csv", "tenths": "error_spreads/tenths.csv"}
# the CSV files of the shocks_and_breaks step, under plots/<name>/
HYPOTHESIS_FILES = {
    "hypothesis": "shocks_and_breaks/hypothesis.csv", "shocks": "shocks_and_breaks/shocks.csv",
    "regimes": "shocks_and_breaks/regimes.csv", "events": "shocks_and_breaks/event_study.csv",
    "effects": "shocks_and_breaks/effects.csv", "breaks": "shocks_and_breaks/breaks.csv",
    "segments": "shocks_and_breaks/segments.csv",
}


def _theme(col: str) -> str:
    return next((name for name, rule in THEMES if rule(col)), "Other")


def _label(col: str, meta: dict, literature_name: str) -> str:
    """The name in the folders: the model variable's name, else the column's short label in
    the documentation, else its meaning up to the first ': '."""
    return literature_name or meta.get("label") or meta.get("meaning", "").split(": ")[0] or col


def _raw_sources(col: str, resolver) -> list[str]:
    """The data sources a column comes from: its own, or those of its inputs, followed down to the raw columns."""
    inputs = DERIVED_FEATURES.get(col, {}).get("inputs", [])
    if not inputs:
        return [resolver.describe(col).get("source", "")]
    return list(dict.fromkeys(s for c in inputs for s in _raw_sources(c, resolver)))


def _number(x: float, digits: int = 4):
    """A JSON-safe number with `digits` significant digits (None for NaN)."""
    if x is None or not math.isfinite(x):
        return None
    return float(f"{x:.{digits}g}")


def _js(variable: str, value) -> str:
    return f"{variable} = {json.dumps(value, ensure_ascii=False, separators=(',', ':'))};\n"


# ---------------------------------------------------------------------------
# CONTENT
# ---------------------------------------------------------------------------
def variables(df: pd.DataFrame, spec: Spec) -> list[dict]:
    """One record per model variable and input: metadata, zones and statistics."""
    resolver = _MetadataResolver()
    records = []
    for col in spec.columns:
        meta, lit = resolver.describe(col), LITERATURE.get(col, {})
        record = {
            "id": col, "label": _label(col, meta, lit.get("name", "")), "role": spec.role(col),
            "theme": _theme(col), "unit": meta.get("unit", ""), "meaning": meta.get("meaning", ""),
            "sources": _raw_sources(col, resolver), "availability": meta.get("availability", ""),
            "definition": lit.get("definition", ""), "transformation": meta.get("transformation", ""),
            "deviation": lit.get("deviation", ""), "inputs": DERIVED_FEATURES.get(col, {}).get("inputs", []),
            "calendar": col in spec.calendar, "zones": [], "stats": {},
        }
        if not record["calendar"]:
            for zone in zones(df):
                s = zone_frame(df, zone)[col]
                if varies(s):
                    record["zones"].append(zone)
                    record["stats"][zone] = {"mean": _number(s.mean()), "sd": _number(s.std()),
                                             "min": _number(s.min()), "max": _number(s.max()),
                                             "missing_pct": round(100 * s.isna().mean(), 2)}
        records.append(record)
    return records


def series(df: pd.DataFrame, col: str, zone_names: list) -> dict:
    """The hourly values of one variable per zone, on the complete hourly grid."""
    out = {"step_ms": 3_600_000, "values": {}}
    for zone in zone_names:
        dz = zone_frame(df, zone)
        out["t0_ms"] = int(dz["datetime_utc"].iloc[0].timestamp() * 1000)
        out["values"][zone] = [None if pd.isna(v) else round(float(v), DECIMALS) for v in dz[col]]
    return out


def _records(table: pd.DataFrame) -> list[dict]:
    """Rows as JSON-safe dicts (NaN -> None)."""
    return table.astype(object).where(pd.notna(table), None).to_dict("records")


def _series(values, digits: int = 4) -> list:
    return [round(float(v), digits) for v in values]


def _series_with_gaps(values, digits: int = 4) -> list:
    """As _series, with None where a value is missing (e.g. an event study with fewer than two shocks)."""
    return [None if pd.isna(v) else round(float(v), digits) for v in values]


def results(plot_dir: Path, files: dict) -> dict:
    """The results of pipeline steps, from their CSV files; a missing file gives None (step not run yet).
    The long tables become one array per series: residual autocorrelations per (zone, system, equation),
    impulse responses per (zone, system, response, shock), event studies per (zone, error, spread, sign)."""
    out = {}
    for key, rel in files.items():
        path = plot_dir / rel
        if not path.exists():
            out[key] = None
            continue
        table = pd.read_csv(path)
        if key == "acf":
            out[key] = [{"zone": z, "system": s, "equation": e, "r": _series(g["r"])}
                        for (z, s, e), g in table.groupby(["zone", "system", "equation"], sort=False)]
        elif key == "irf":
            # other Cholesky orders have their own band (lower_<order>); other lag structures only an estimate
            orders = [c.removeprefix("lower_") for c in table.columns if c.startswith("lower_")]
            robust = [c for c in table.columns if c.startswith("estimate_") and c.removeprefix("estimate_") not in orders]
            out[key] = [{"zone": z, "system": s, "response": r, "shock": k,
                         **{c: _series(g[c]) for c in ("estimate", "lower", "upper")},
                         "robust": {c.removeprefix("estimate_").replace("_", " "): _series(g[c]) for c in robust},
                         "orders": {o.replace("_", " "): {c: _series(g[f"{c}_{o}"]) for c in ("estimate", "lower", "upper")}
                                    for o in orders}}
                        for (z, s, r, k), g in table.groupby(["zone", "system", "response", "shock"], sort=False)]
        elif key in ("events", "around"):
            out[key] = [{"zone": z, "error": e, "spread": s, "sign": int(k), "h": g["h"].tolist(),
                         **{c: _series_with_gaps(g[c]) for c in ("mean", "lower", "upper")},
                         "n": g["n"].astype(int).tolist(), **({"runs": int(g["runs"].iloc[0])} if "runs" in g else {})}
                        for (z, e, s, k), g in table.groupby(["zone", "error", "spread", "sign"], sort=False)]
        else:
            out[key] = _records(table)
    return out


def tests(plot_dir: Path) -> dict:
    return results(plot_dir, TEST_FILES)


def hypothesis(plot_dir: Path) -> dict:
    """The shocks_and_breaks results; breaks and regime levels only of the forecast errors and spreads."""
    out = results(plot_dir, HYPOTHESIS_FILES)
    if out["hypothesis"]:
        shown = {r["error"] for r in out["hypothesis"]} | {r["spread"] for r in out["hypothesis"]}
        for key in ("breaks", "segments"):
            out[key] = [r for r in out[key] or [] if r["column"] in shown]
    return out


def write_equations(out: Path) -> dict:
    """data/math/<key>.svg for every formula; {key: path relative to index.html}."""
    (out / "data" / "math").mkdir(parents=True, exist_ok=True)
    paths = {}
    with matplotlib.rc_context({"mathtext.fontset": "cm", "svg.fonttype": "path", "savefig.transparent": True}):
        for key, tex in EQUATIONS.items():
            rel = f"data/math/{key}.svg"
            math_to_image(f"${tex}$", out / rel, prop=FontProperties(size=15), format="svg", color="#0b0b0b")
            paths[key] = rel
    return paths


def pipeline_facts(df: pd.DataFrame, records: list, plot_dir: Path) -> dict:
    """Key facts of the pipeline stages, shown on the overview."""
    hours = int(df["datetime_utc"].nunique())
    sources = sorted({s.split(" — ")[0] for r in records for s in r["sources"] if s and not s.startswith("Calendar")})
    facts = {
        "period": f"{df['datetime_utc'].min():%Y-%m-%d} to {df['datetime_utc'].max():%Y-%m-%d} (UTC)",
        "hours": hours, "zones": zones(df), "sources": sources,
        "counts": {role: sum(1 for r in records if r["role"] == role) for role in ("Endogenous", "Exogenous", "Input")},
    }
    orders_path = plot_dir / "lag_selection" / "lag_orders.csv"
    if orders_path.exists():
        orders = pd.read_csv(orders_path)
        facts["lag_orders"] = sorted(orders["p"].unique().tolist())
    return facts


# ---------------------------------------------------------------------------
# ENTRY POINT
# ---------------------------------------------------------------------------
def run(df: pd.DataFrame, spec: Spec, plot_dir, title: str = "Thesis dashboard",
        expected_signs: dict | None = None) -> Path:
    """expected_signs: {error: {spread: +1 / -1}}, the sign the hypothesis expects for each spread's response
    to a positive forecast error (main.py's EXPECTED_SIGNS)."""
    name = Path(plot_dir).name
    out = WEB_DIR / name
    series_dir = out / "data" / "series"
    series_dir.mkdir(parents=True, exist_ok=True)  # overwritten in place (OneDrive may hold the old files open)
    shutil.copytree(ASSETS, out / "assets", ignore=shutil.ignore_patterns("index.html"), dirs_exist_ok=True)
    shutil.copy(ASSETS / "index.html", out / "index.html")
    try:
        import plotly
    except ImportError:
        raise ImportError("The web step needs the plotly package (its chart library): pip install plotly") from None
    shutil.copy(Path(plotly.__file__).parent / "package_data" / "plotly.min.js", out / "assets" / "plotly.min.js")

    records = variables(df, spec)
    plotted = {r["id"] for r in records if r["zones"]}
    for col in plotted:
        (series_dir / f"{col}.js").write_text(
            "window.SITE_SERIES = window.SITE_SERIES || {};\n"
            + _js(f"SITE_SERIES[{json.dumps(col)}]", series(df, col, next(r["zones"] for r in records if r["id"] == col))),
            encoding="utf-8")
    for old in series_dir.glob("*.js"):  # variables no longer in the dataframe
        if old.stem not in plotted:
            old.unlink()
    site = {
        "title": title, "dataframe": name, "generated": f"{datetime.now():%Y-%m-%d %H:%M}",
        "zones": zones(df), "themes": [t for t, _ in THEMES] + ["Other"],
        "facts": pipeline_facts(df, records, Path(plot_dir)), "variables": records,
        "errors": results(Path(plot_dir), ERROR_FILES), "spreads": results(Path(plot_dir), SPREAD_FILES),
        "hypothesis": hypothesis(Path(plot_dir)),
        "tests": tests(Path(plot_dir)),
        "results": results(Path(plot_dir), RESULT_FILES), "expected": expected_signs or {}, "math": write_equations(out),
        "flags": {"points": POINTS, "limitations": LIMITATIONS},
    }
    (out / "data" / "site.js").write_text(_js("window.SITE", site), encoding="utf-8")
    size = sum(f.stat().st_size for f in out.rglob("*") if f.is_file()) / 1e6
    print(f"  wrote {out.relative_to(PROJECT_ROOT).as_posix()}/ ({size:.1f} MB): open index.html in a browser")
    return out
