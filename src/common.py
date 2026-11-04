"""
common.py — helpers shared by the steps in src/dataframe, src/VAR_tests and
src/models: per-zone access, labels and units, colours, and the figure /
table helpers.
"""

import math
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # write PNG files, no display needed
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

from dataframe.building import PROJECT_ROOT
from dataframe.documentation import LITERATURE, column_units  # noqa: F401  (column_units: used by the steps)

PLOTS_DIR = PROJECT_ROOT / "plots"
ROLE_FOLDERS = {"Endogenous": "endogenous", "Exogenous": "exogenous", "Input": "inputs"}
FONT_SCALE = 2  # text size of the plots: the PNGs are shrunk to the text width in the thesis

# Colour-blind-safe (Okabe-Ito); DK1 / DK2 always get the same colour.
ZONE_COLORS = {"DK1": "#0072B2", "DK2": "#E69F00"}
_OTHER_ZONE_COLORS = ["#009E73", "#CC79A7", "#56B4E9", "#D55E00"]


# ---------------------------------------------------------------------------
# DATA
# ---------------------------------------------------------------------------
def zones(df: pd.DataFrame) -> list:
    return sorted(df["bidding_zone"].unique())


def zone_frame(df: pd.DataFrame, zone: str) -> pd.DataFrame:
    """One zone's rows in time order (on the complete hourly grid, 1 row = 1 hour)."""
    return df[df["bidding_zone"] == zone].sort_values("datetime_utc").reset_index(drop=True)


def varies(s: pd.Series) -> bool:
    """False for a column that is constant (or empty) in a zone — e.g. a
    cross-border flow to a counterpart the zone is not connected to, 0 in
    every hour. Such a column has nothing to plot, correlate or test there."""
    return s.nunique() > 1


def zones_with_data(df: pd.DataFrame, col: str) -> list:
    return [z for z in zones(df) if varies(df.loc[df["bidding_zone"] == z, col])]


# ---------------------------------------------------------------------------
# LABELS AND COLOURS
# ---------------------------------------------------------------------------
def label(col: str) -> str:
    """'DA-ID spread (x_da_id_spread)' for a documented model variable, else the column name."""
    name = LITERATURE.get(col, {}).get("name")
    return f"{name} ({col})" if name else col


def name(col: str) -> str:
    """'DA-ID spread' for a documented model variable, else the column name (as it is)."""
    return LITERATURE.get(col, {}).get("name", col)


def with_unit(text: str, unit: str) -> str:
    return f"{text} [{unit}]" if unit else text


def zone_color(zone: str) -> str:
    if zone not in ZONE_COLORS:
        ZONE_COLORS[zone] = _OTHER_ZONE_COLORS[(len(ZONE_COLORS) - 2) % len(_OTHER_ZONE_COLORS)]
    return ZONE_COLORS[zone]


# ---------------------------------------------------------------------------
# FIGURES AND TABLES
# ---------------------------------------------------------------------------
def style_axes(ax, title: str = "", xlabel: str = "", ylabel: str = ""):
    ax.set_title(title, fontsize=10 * FONT_SCALE)
    ax.set_xlabel(xlabel, fontsize=8 * FONT_SCALE)
    ax.set_ylabel(ylabel, fontsize=8 * FONT_SCALE)
    ax.tick_params(labelsize=8 * FONT_SCALE)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)


def time_axis(ax):
    locator = mdates.AutoDateLocator()
    ax.xaxis.set_major_locator(locator)
    ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(locator))


def _two_lines(text: str) -> str:
    """The text broken at the space nearest its middle (unchanged if it has no space, a line break or maths)."""
    spaces = [i for i, ch in enumerate(text) if ch == " "]
    if not spaces or "\n" in text or "$" in text:
        return text
    i = min(spaces, key=lambda k: abs(k - len(text) / 2))
    return text[:i] + "\n" + text[i + 1:]


def _fit_to_axes(fig, axes) -> bool:
    """A panel title or axis label longer than its panel goes on two lines, and is shrunk if it still does not
    fit; True if any changed."""
    renderer, changed = fig.canvas.get_renderer(), False
    for ax in axes:
        box = ax.get_window_extent(renderer)
        for text, room, along in ((ax.title, box.width, "width"), (ax.xaxis.label, box.width, "width"),
                                  (ax.yaxis.label, box.height, "height")):
            def length():
                return getattr(text.get_window_extent(renderer), along) if text.get_text() else 0
            if length() > room:
                text.set_text(_two_lines(text.get_text()))
                if length() > room:
                    text.set_fontsize(text.get_fontsize() * room / length())
                changed = True
    return changed


def save_figure(fig, axes, title: str, path: Path, legend_ncol: int | None = None, title_size: float = 13):
    """Title, a legend row under it (the labelled artists of all axes,
    deduplicated) and the panels below; the space is reserved in inches, so
    the layout is the same for any figure height."""
    handles = {}
    for ax in axes:
        for h, lbl in zip(*ax.get_legend_handles_labels()):
            handles.setdefault(lbl, h)
    fig_w, fig_h = fig.get_size_inches()
    suptitle = fig.suptitle(title, fontsize=title_size * FONT_SCALE, y=1 - 0.12 / fig_h, va="top")
    suptitle.set_in_layout(False)  # its space is reserved below (tight_layout would count it a second time)
    title_w = suptitle.get_window_extent(fig.canvas.get_renderer()).width / fig.dpi
    if title_w > 0.96 * fig_w:  # a title wider than the figure is shrunk to fit
        suptitle.set_fontsize(suptitle.get_fontsize() * 0.96 * fig_w / title_w)
    title_line, legend_line = suptitle.get_fontsize() * 1.25 / 72, 9 * FONT_SCALE * 1.6 / 72  # inches per line
    title_h = 0.12 + title_line * (1 + title.count("\n"))
    top = title_h + 0.1
    if handles:
        ncol = legend_ncol or len(handles)
        while True:  # fewer columns (more rows) until the legend fits the figure width
            legend = fig.legend(list(handles.values()), list(handles.keys()), loc="upper center", ncol=ncol,
                                bbox_to_anchor=(0.5, 1 - (title_h + 0.04) / fig_h), frameon=False,
                                fontsize=9 * FONT_SCALE)
            if ncol == 1 or legend.get_window_extent(fig.canvas.get_renderer()).width / fig.dpi <= 0.96 * fig_w:
                break
            legend.remove()
            ncol -= 1
        for line in legend.get_lines():  # thin hourly lines: readable legend sample
            if line.get_linewidth() < 1:
                line.set_linewidth(2)
                line.set_alpha(1)
        top = title_h + 0.14 + legend_line * math.ceil(len(handles) / ncol)
    fig.tight_layout(rect=(0, 0, 1, 1 - top / fig_h))
    if _fit_to_axes(fig, axes):
        fig.tight_layout(rect=(0, 0, 1, 1 - top / fig_h))
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=130)
    plt.close(fig)
    print(f"  wrote {path.relative_to(PLOTS_DIR).as_posix()}")


def md_table(df: pd.DataFrame) -> str:
    """A Markdown table (no tabulate dependency)."""
    lines = ["| " + " | ".join(map(str, df.columns)) + " |", "|" + "|".join("---" for _ in df.columns) + "|"]
    lines += ["| " + " | ".join(str(v) for v in row) + " |" for row in df.itertuples(index=False)]
    return "\n".join(lines)
