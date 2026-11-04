"""
correlation.py — correlations of a dataframe's columns, per bidding zone (the
"correlation" step of main.py):

    correlation/<zone>_matrix.png             correlation of every column (endogenous,
                                              exogenous, inputs; calendar dummies left
                                              out) at the same hour; lines separate the roles
    correlation/<zone>_cross_correlation.png  per endogenous variable: its correlation with
                                              every other model variable at lags
                                              -max_lag .. +max_lag hours

Per zone only: the VAR is estimated per zone, and pooling the zones can blend
two different relationships into one number. A column that does not vary in
a zone (e.g. a flow to a counterpart the zone is not connected to) is left
out for that zone. Every correlation uses the hours where both columns are
observed (pairwise).
"""

import math

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from common import FONT_SCALE, label, save_figure, style_axes, varies, zone_frame, zones
from dataframe.building import Spec

FOLDERS = ["correlation"]
ANNOTATE_MAX_COLUMNS = 20  # write r in the cells of matrices up to this size
OFF_SCALE_R = 0.9          # cross-correlation lines peaking above this are drawn off scale (named in the panel)
ROLE_STYLE = {"Endogenous": ("black", "normal", "bold"), "Exogenous": ("0.35", "italic", "normal"),
              "Input": ("0.55", "normal", "normal")}


def plot_matrix(dz: pd.DataFrame, groups: dict, zone: str, method: str, path):
    cols = [c for cs in groups.values() for c in cs]
    matrix = dz[cols].corr(method=method).to_numpy()
    n = len(cols)
    annotate = n <= ANNOTATE_MAX_COLUMNS
    size = max(8.0, 0.32 * n + 3) if not annotate else max(8.5, 0.75 * n + 3)
    fig, ax = plt.subplots(figsize=(size + 1.5, size))
    im = ax.imshow(matrix, vmin=-1, vmax=1, cmap="RdBu_r")
    ax.set_xticks(range(n), cols, rotation=90, fontsize=8 * FONT_SCALE)
    ax.set_yticks(range(n), cols, fontsize=8 * FONT_SCALE)
    roles = [role for role, cs in groups.items() for _ in cs]
    for tick_labels in (ax.get_xticklabels(), ax.get_yticklabels()):
        for text, role in zip(tick_labels, roles):
            color, style, weight = ROLE_STYLE[role]
            text.set(color=color, style=style, weight=weight)
    edge = 0
    for cs in list(groups.values())[:-1]:
        edge += len(cs)
        if 0 < edge < n:
            ax.axhline(edge - 0.5, color="black", linewidth=1.6)
            ax.axvline(edge - 0.5, color="black", linewidth=1.6)
    if annotate:
        for i in range(n):
            for j in range(n):
                if np.isfinite(matrix[i, j]):
                    ax.text(j, i, f"{matrix[i, j]:+.2f}", ha="center", va="center", fontsize=8 * FONT_SCALE,
                            color="white" if abs(matrix[i, j]) > 0.6 else "black")
    bar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    bar.set_label(f"{method.capitalize()} correlation", fontsize=9 * FONT_SCALE)
    bar.ax.tick_params(labelsize=8 * FONT_SCALE)
    counts = ", ".join(f"{len(cs)} {role.lower()}" for role, cs in groups.items() if cs)
    save_figure(fig, [ax], f"{zone} — {method.capitalize()} correlation at the same hour ({counts})\n"
                           f"endogenous: bold | exogenous: italic | inputs: grey", path)


def plot_cross_correlation(dz: pd.DataFrame, groups: dict, zone: str, method: str, max_lag: int, path):
    """Panel per endogenous variable e; one line per other model variable v:
    r_k = corr(v at t, e at t + k). k > 0: v leads e by k hours; k < 0: e leads."""
    endo, exo = groups["Endogenous"], groups["Exogenous"]
    variables = endo + exo
    if not endo or len(variables) < 2:
        return
    ks = np.arange(-max_lag, max_lag + 1)
    colors = {v: plt.get_cmap("tab20")(i % 20) for i, v in enumerate(variables)}
    n_hours = int(dz[variables].notna().all(axis=1).sum())
    band = 1.96 / math.sqrt(n_hours) if n_hours else 0
    fig, axes = plt.subplots(len(endo), 1, figsize=(14, 3.1 * len(endo)), sharex=True, squeeze=False)
    axes = list(axes[:, 0])
    style = {v: "-" if v in endo else "--" for v in variables}
    for v in variables:  # legend entries in variable order (every variable is missing from its own panel)
        axes[0].plot([], [], color=colors[v], linestyle=style[v], label=v + ("" if v in endo else "  (exogenous)"))
    for ax, e in zip(axes, endo):
        scale, off_scale = 0.0, []
        shifted = {k: dz[e].shift(-k) for k in ks}
        for v in variables:
            if v == e:
                continue
            r = np.array([dz[v].corr(shifted[k], method=method) for k in ks])
            peak = int(np.nanargmax(np.abs(r)))
            # near-identities (e.g. DA-BAL = DA-ID + ID-BAL) would squash every other line:
            # scale the axis to the rest and name the off-scale peak instead
            if abs(r[peak]) > OFF_SCALE_R:
                off_scale.append(f"{v}: r = {r[peak]:+.2f} at k = {ks[peak]} h")
                r = np.where(np.abs(r) > OFF_SCALE_R, np.nan, r)
            ax.plot(ks, r, color=colors[v], linewidth=1.1, linestyle=style[v])
            if np.isfinite(r).any():
                scale = max(scale, float(np.nanmax(np.abs(r))))
        if scale:
            ax.set_ylim(-1.15 * scale, 1.15 * scale)
        if off_scale:
            ax.text(0.01, 0.97, "off scale: " + "; ".join(off_scale), transform=ax.transAxes, fontsize=8 * FONT_SCALE,
                    va="top", style="italic", color="0.3")
        ax.axhline(0, color="black", linewidth=0.6)
        ax.axvline(0, color="black", linewidth=0.6)
        ax.axhspan(-band, band, color="0.88", zorder=0)
        for d in range(-max_lag, max_lag + 1, 24):
            if d:
                ax.axvline(d, color="0.85", linewidth=0.6, zorder=0)
        style_axes(ax, label(e), "", "r")
    step = 24 if max_lag <= 168 else 168
    axes[-1].set_xticks(np.arange(-max_lag - (-max_lag % step), max_lag + 1, step))
    axes[-1].set_xlim(-max_lag, max_lag)
    axes[-1].set_xlabel("Lag k [hours]: k > 0 = the line's variable at t vs the panel's variable at t + k "
                        "(line leads); k < 0 = the panel's variable leads", fontsize=9 * FONT_SCALE)
    save_figure(fig, axes, f"{zone} — cross-correlation of each endogenous variable with the other model "
                           f"variables ({method.capitalize()}; grey band = ±1.96/√n)", path, legend_ncol=4)


def run(df: pd.DataFrame, spec: Spec, plot_dir, method: str = "pearson", max_lag: int = 168):
    out = plot_dir / "correlation"
    for zone in zones(df):
        dz = zone_frame(df, zone)
        groups = {role: [c for c in cols if varies(dz[c])] for role, cols in spec.by_role().items()}
        print(f"  {zone}: " + ", ".join(f"{len(cs)} {role.lower()}" for role, cs in groups.items()))
        plot_matrix(dz, groups, zone, method, out / f"{zone}_matrix.png")
        plot_cross_correlation(dz, groups, zone, method, max_lag, out / f"{zone}_cross_correlation.png")
