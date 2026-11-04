"""
latex_outputs.py — the figures and tables of the LaTeX thesis (the "latex"
step of main.py), written to latex_outputs/<name>/ so the folder can be
uploaded to Overleaf as it is:

    figures       the plots listed in LATEX_FIGURES (main.py), copied from
                  plots/<name>/; nothing is recomputed, so run this step after
                  the steps that make them
    descriptive   booktabs tables for the appendix, one for the endogenous and
                  one for the exogenous variables (calendar dummies left out),
                  per zone: observations, mean, median, standard deviation,
                  minimum, maximum, skewness and kurtosis (3 for a normal
                  distribution), the statistics of Table 3 in Spodniak et al.;
                  computed as in the documentation workbook. A variable that is
                  the same in every zone (e.g. a hydro deviation) gets one row,
                  zone "all"

    python main.py baseline_2025 --only latex

Files not on the list are removed, so a figure taken off the list does not stay.
"""

import shutil
from pathlib import Path

import pandas as pd

from common import column_units, name, zone_frame, zones_with_data
from dataframe.building import PROJECT_ROOT, Spec
from dataframe.documentation import _distribution_row

FOLDERS = []  # writes latex_outputs/<name>/, not plots/<name>/
LATEX_DIR = PROJECT_ROOT / "latex_outputs"
DESCRIPTIVE = {"n_obs": "Obs.", "mean": "Mean", "median": "Median", "std": "S.d.", "min": "Min", "max": "Max",
               "skewness": "Skew.", "kurtosis": "Kurt."}  # statistic: column header
DESCRIPTIVE_ROLES = ("Endogenous", "Exogenous")  # one table each
UNIT_SHORT = {"percentage points": "p.p."}  # shorter units in the tables


def _number(v: float) -> str:
    """A LaTeX number: no decimals from 100 on, one below, thousands separated, minus in maths mode."""
    text = f"{abs(v):,.0f}" if abs(v) >= 100 else f"{abs(v):.1f}"
    return ("$-$" if v < 0 and text.strip("0.,") else "") + text.replace(",", "{,}")


def _label_lines(col: str, unit: str) -> list:
    """The variable's label on two lines, so the table stays narrow: 'Hydro deviation (p.p.)' / 'Norway' for
    the name 'Hydro deviation, Norway', else the name / '(unit)'."""
    head, _, tail = name(col).partition(", ")
    unit = UNIT_SHORT.get(unit, unit)
    return [f"{head} ({unit})", tail] if tail else [head, f"({unit})"]


def descriptive_table(df: pd.DataFrame, spec: Spec, role: str = "Endogenous") -> str:
    """The descriptive-statistics table of the variables of one role (calendar dummies left out)."""
    cols = spec.by_role()[role]  # without the calendar dummies
    units = column_units(cols)
    years = sorted(df["datetime_utc"].dt.year.unique())
    period = str(years[0]) if len(years) == 1 else f"{years[0]}--{years[-1]}"
    rows, shared = [], False
    for n, col in enumerate(cols):
        if n:
            rows.append(r"\midrule")
        zone_names = zones_with_data(df, col)
        series = {z: zone_frame(df, z)[col].reset_index(drop=True) for z in zone_names}
        if len(series) > 1 and all(s.equals(series[zone_names[0]]) for s in series.values()):
            series, shared = {"all": series[zone_names[0]]}, True  # the same in every zone: one row
        labels = _label_lines(col, units[col])
        if len(series) == 1:  # one row: both lines in one cell
            labels = [r"\begin{tabular}[t]{@{}l@{}}" + r" \\ ".join(labels) + r"\end{tabular}"]
        for (zone, s), label in zip(series.items(), labels + [""] * len(series)):
            stats = _distribution_row(s)
            stats["kurtosis"] = stats["excess_kurtosis"] + 3
            cells = [f"{stats['n_obs']:,}".replace(",", "{,}")] + [_number(stats[k]) for k in list(DESCRIPTIVE)[1:]]
            rows.append(" & ".join([label, zone] + cells) + r" \\")
    notes = (" Calendar dummies are left out." if len(spec.by_role(calendar=True)[role]) > len(cols) else "") + \
            (" A variable that is the same in every zone is shown once (all)." if shared else "")
    label = "tab:descriptive" if role == "Endogenous" else f"tab:descriptive-{role.lower()}"
    lines = [r"\begin{table}[!htb]", r"\centering", r"\small", r"\renewcommand{\arraystretch}{1.15}",
             rf"\caption{{Descriptive statistics of the {role.lower()} variables, {period}, hourly values. Kurtosis "
             rf"is 3 for a normal distribution.{notes}}}", rf"\label{{{label}}}",
             r"\begin{tabular}{@{}ll" + "r" * len(DESCRIPTIVE) + "@{}}", r"\toprule",
             " & ".join([r"\textbf{Variable}", r"\textbf{Zone}"] + [rf"\textbf{{{h}}}" for h in DESCRIPTIVE.values()])
             + r" \\", r"\midrule"]
    return "\n".join(lines + rows + [r"\bottomrule", r"\end{tabular}", r"\end{table}", ""])


def run(df: pd.DataFrame, spec: Spec, plot_dir, figures: list = (), descriptive: str = "") -> Path:
    """figures: paths relative to plots/<name>/, each copied under its own file name; descriptive: the file name of
    the descriptive-statistics tables ("" = none)."""
    missing = [f for f in figures if not (plot_dir / f).exists()]
    if missing:
        raise FileNotFoundError(f"Not in {plot_dir}: {missing}. Run the steps that make them first.")
    names = [Path(f).name for f in figures]
    keep = names + ([descriptive] if descriptive else [])
    if len(set(keep)) < len(keep):
        raise ValueError(f"Two LaTeX outputs share a file name: {keep}")
    out = LATEX_DIR / plot_dir.name
    out.mkdir(parents=True, exist_ok=True)
    for old in out.iterdir():  # the folder is kept (OneDrive may hold it); files not on the list are removed
        if old.is_file() and old.name not in keep:
            old.unlink()
    for f, name in zip(figures, names):
        shutil.copy2(plot_dir / f, out / name)
        print(f"  latex_outputs/{plot_dir.name}/{name}")
    if descriptive:
        tables = [descriptive_table(df, spec, role) for role in DESCRIPTIVE_ROLES if spec.by_role()[role]]
        (out / descriptive).write_text("\n".join(tables), encoding="utf-8")
        print(f"  latex_outputs/{plot_dir.name}/{descriptive}")
    return out
