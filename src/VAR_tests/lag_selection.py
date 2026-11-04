"""
lag_selection.py — the lag order p of the VARX, per bidding zone and system
(the "lag_selection" step of main.py). The model is a VARX(p, 0):

    y_t = c + A_1 y_(t-1) + ... + A_p y_(t-p) + B x_t + D d_t + u_t

y_t the K endogenous variables, x_t the exogenous variables (as listed in
main.py), d_t the calendar dummies. Only the endogenous variables get lags.

CRITERIA: every order p = 1..max_lag is fitted by least squares, equation by
equation (the same as multivariate least squares, and as maximum likelihood
with normal residuals), and scored by

    IC(p) = ln|S(p)| + (c_T / T) p K²        lower = better

    S(p) = U'U / T   the residual covariance of the fit with p lags
    T                hours, the SAME for every p: those valid for the longest
                     order. On other hours ln|S| of two orders would measure
                     different data and could not be compared.
    p K²             lag coefficients. The constant, exogenous and dummy
                     coefficients are the same for every p: they add the same
                     penalty to every order and cannot change the choice.
    c_T              ln T (BIC), 2 ln ln T (HQ), 2 (AIC): the gain in fit one
                     extra coefficient must bring to be worth it.

CHOICE: the order with the lowest `criterion` (AIC in main.py).
    For T >= 16 the penalties are ordered, ln T > 2 ln ln T > 2, so always
    p(BIC) <= p(HQ) <= p(AIC): the criteria differ only in how much fit an
    extra lag must add. BIC and HQ are consistent: when the data follow a VAR
    of finite order, they find it as T grows, but in a finite sample they can
    stop short of it. AIC does not stop short as T grows; it can only add lags
    (Lütkepohl 2005, ch. 4). Too few lags leave dynamics out of the model (and
    in the residuals); too many cost only precision. The penalty per hour of
    BIC and HQ, c_T / T, shrinks as T grows, so with a longer sample they move
    towards the AIC choice.
    BOUND: when the choice is max_lag itself, the lowest value may lie beyond
    it. The search is then repeated up to twice the bound (on the hours valid
    for it), until the choice is inside.

LITERATURE: the structure of the baseline paper (literature_lags) is scored on
the same hours for comparison; it is not a candidate.

SYSTEMS: endogenous variables that are exact linear combinations of each
other (e.g. DA-BAL = DA-ID + ID-BAL) cannot share one VAR — their lags would
be perfectly collinear. Found from the data: a variable whose removal leaves
the rank of the (centred) endogenous block unchanged is part of such a
dependency. Each system takes all the other endogenous variables plus ONE of
those; without a dependency there is one system with all of them.

REGRESSORS per equation: a constant, the lags, the exogenous variables that
vary in the zone (a flow to a counterpart the zone is not connected to is 0 in
every hour and is left out) and one dummy per calendar category (first
dropped). A column perfectly collinear with the others is dropped and named.

OUTPUT (plots/<name>/lag_selection/)
    lag_selection.png   per (zone, system): BIC, HQ and AIC by order, each
                        relative to its own lowest value, and the chosen order
    LAG_SELECTION.md    the setup, the choices, and how far each choice is from
                        the lowest value of every criterion
    lag_orders.csv      the order chosen by each criterion per (zone, system),
                        read by the residual_checks and varx steps
    criteria.csv        every criterion at every order (read by the web step)
"""

import math

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.ticker import MultipleLocator

from common import md_table, name, save_figure, style_axes, varies, zone_frame, zones
from dataframe.building import Spec

FOLDERS = ["lag_selection"]
ORDERS_FILE = "lag_orders.csv"

# penalty per coefficient c_T of each information criterion, strongest first
CRITERIA = {"bic": lambda T: math.log(T), "hq": lambda T: 2 * math.log(math.log(T)), "aic": lambda T: 2.0}
CRITERION_STYLE = {"bic": ("BIC", "#D55E00"), "hq": ("HQ", "#009E73"), "aic": ("AIC", "#0072B2")}
LITERATURE = "literature"


def endogenous_systems(dz: pd.DataFrame, endogenous: list) -> list[list[str]]:
    """The endogenous variables split into systems without exact linear
    dependencies (see the module docstring)."""
    Y = dz[endogenous].dropna().to_numpy(float)
    Y = Y - Y.mean(axis=0)
    rank = np.linalg.matrix_rank(Y)
    if rank == len(endogenous):
        return [list(endogenous)]
    dependent = [v for i, v in enumerate(endogenous) if np.linalg.matrix_rank(np.delete(Y, i, axis=1)) == rank]
    independent = [v for v in endogenous if v not in dependent]
    return [independent + [v] for v in dependent]


def _design(dz: pd.DataFrame, y_cols: list, lags: list, exog: list, calendar: list, sample=None):
    """Y (T x K), X (T x m), the regressor names and the mask of the hours
    used. dz is one zone's complete hourly grid in time order, so a shift of L
    rows = L hours. Only hours where everything is observed (and inside
    `sample`, if given) are kept; the dummies are built on THOSE hours, so the
    dropped reference category always has estimation hours."""
    parts = {"const": pd.Series(1.0, index=dz.index)}
    for lag in lags:
        for c in y_cols:
            parts[f"L{lag}.{c}"] = dz[c].shift(lag)
    for c in exog:
        parts[c] = dz[c]
    X = pd.DataFrame(parts)
    ok = X.notna().all(axis=1) & dz[y_cols].notna().all(axis=1)
    if sample is not None:
        ok &= sample
    X = X[ok]
    for c in calendar:
        X = X.join(pd.get_dummies(dz.loc[ok, c].astype("Int64"), prefix=c, drop_first=True, dtype=float))
    return dz.loc[ok, y_cols].to_numpy(float), X.to_numpy(float), list(X.columns), ok.to_numpy()


def check_exog(dz: pd.DataFrame, exog: list, calendar: list, zone: str) -> list:
    """Prints the shape and rank of [constant, exogenous, dummies]; a column
    perfectly collinear with the others is dropped (last one first) and named."""
    exog = list(exog)
    while True:
        X = _design(dz, [], [], exog, calendar)[1]
        rank = np.linalg.matrix_rank(X)
        print(f"  [{zone}] exogenous matrix: {X.shape[0]} hours x {X.shape[1]} columns (constant + {len(exog)} "
              f"exogenous + {X.shape[1] - 1 - len(exog)} dummies), rank {rank}")
        if rank == X.shape[1]:
            return exog
        for c in reversed(exog):
            rest = [e for e in exog if e != c]
            Xr = _design(dz, [], [], rest, calendar)[1]
            if np.linalg.matrix_rank(Xr) == Xr.shape[1]:
                print(f"  [{zone}] WARNING — {c} is perfectly collinear with the other exogenous columns: dropped")
                exog = rest
                break
        else:
            raise RuntimeError(f"{zone}: exogenous matrix rank deficient ({rank} < {X.shape[1]}) and no single "
                               f"column explains it")


def zone_inputs(df: pd.DataFrame, spec: Spec, zone: str) -> tuple:
    """(one zone's hourly frame, its exogenous columns, its systems): the
    exogenous variables that vary in the zone, checked for collinearity."""
    dz = zone_frame(df, zone)
    exog = [c for c in spec.exogenous if c not in spec.calendar and varies(dz[c])]
    return dz, check_exog(dz, exog, spec.calendar, zone), endogenous_systems(dz, list(spec.endogenous))


# ---------------------------------------------------------------------------
# FIT AND CRITERIA
# ---------------------------------------------------------------------------
def _fit_matrices(Y, X, names, ok, lags, y_cols) -> dict:
    coef, _, rank, _ = np.linalg.lstsq(X, Y, rcond=None)
    if rank < X.shape[1]:
        print(f"    WARNING — design matrix rank {rank} < {X.shape[1]} columns (collinear regressors)")
    resid = Y - X @ coef
    return {"X": X, "names": names, "ok": ok, "coef": coef, "resid": resid, "sigma": resid.T @ resid / len(Y),
            "lags": list(lags), "y_cols": list(y_cols)}


def fit(dz: pd.DataFrame, y_cols: list, lags: list, exog: list, calendar: list, sample=None) -> dict:
    """Equation-by-equation least squares of the VARX(p, 0) with the given lags."""
    Y, X, names, ok = _design(dz, y_cols, lags, exog, calendar, sample)
    return _fit_matrices(Y, X, names, ok, lags, y_cols)


def _lag_of(name: str) -> int | None:
    """The lag of a regressor named 'L<lag>.<column>', None for any other regressor."""
    head = name.split(".", 1)[0]
    return int(head[1:]) if "." in name and head.startswith("L") and head[1:].isdigit() else None


def fit_structure(full: tuple, lags: list, y_cols: list) -> dict:
    """The fit with `lags`, taken from the design built once with every lag up
    to the longest (same hours, same dummies): its columns for these lags, and
    every column that is not a lag."""
    Y, X, names, ok = full
    wanted = set(lags)
    keep = [i for i, n in enumerate(names) if _lag_of(n) is None or _lag_of(n) in wanted]
    return _fit_matrices(Y, X[:, keep], [names[i] for i in keep], ok, lags, y_cols)


def lag_matrices(model: dict, coef: np.ndarray | None = None) -> np.ndarray:
    """A[l - 1] = A_l (K x K; row = equation, column = lagged variable) for
    l = 1..longest lag; lags not in the structure stay 0. `coef` replaces the
    fitted coefficients (same regressors), e.g. a bootstrap draw."""
    coef = model["coef"] if coef is None else coef
    K, p = len(model["y_cols"]), max(model["lags"])
    A = np.zeros((p, K, K))
    for lag in model["lags"]:
        A[lag - 1] = coef[[model["names"].index(f"L{lag}.{c}") for c in model["y_cols"]]].T
    return A


def information_criteria(sigma: np.ndarray, T: int, n_lags: int, K: int) -> dict:
    """{'bic', 'hq', 'aic'}: ln|S| + (c_T / T) p K²."""
    logdet = np.linalg.slogdet(sigma)[1]
    return {ic: logdet + c_T(T) / T * n_lags * K ** 2 for ic, c_T in CRITERIA.items()}


def select_order(dz: pd.DataFrame, system: list, exog: list, calendar: list, criterion: str, max_lag: int,
                 literature_lags: list) -> dict:
    """The criteria of every order 1..bound and of the literature structure, all
    on the same hours, and each criterion's choice among the orders. The bound
    starts at max_lag and doubles while `criterion` chooses the bound itself.
    Returns {'ics': {order: {ic: value}}, 'best': {ic: order}, 'T', 'bound'}."""
    bound, K = max_lag, len(system)
    while True:
        structures = {p: list(range(1, p + 1)) for p in range(1, bound + 1)}
        structures[LITERATURE] = list(literature_lags)
        full = _design(dz, system, sorted(set().union(*structures.values())), exog, calendar)
        T = len(full[0])
        ics = {order: information_criteria(fit_structure(full, lags, system)["sigma"], T, len(lags), K)
               for order, lags in structures.items()}
        best = {ic: min(range(1, bound + 1), key=lambda p: ics[p][ic]) for ic in CRITERIA}
        if best[criterion] < bound:
            return {"ics": ics, "best": best, "T": T, "bound": bound}
        if 2 * bound * K >= T / 2:
            raise RuntimeError(f"{criterion.upper()} chooses the bound {bound}, and a longer search would leave too "
                               f"few hours per coefficient (T = {T})")
        print(f"    {criterion.upper()} chooses the bound {bound}: searching again up to {2 * bound}")
        bound *= 2


def read_orders(plot_dir) -> dict:
    """{(zone, (endogenous variables of the system)): {"p": chosen order, "BIC": .., "HQ": .., "AIC": ..}},
    as written by the lag_selection step."""
    path = plot_dir / "lag_selection" / ORDERS_FILE
    if not path.exists():
        raise FileNotFoundError(f"{path} not found: run the lag_selection step first")
    return {(r["zone"], tuple(r["variables"].split(", "))): {k: int(r[k]) for k in ("p", "BIC", "HQ", "AIC")}
            for r in pd.read_csv(path).to_dict("records")}


# ---------------------------------------------------------------------------
# OUTPUT
# ---------------------------------------------------------------------------
def system_label(system: list, systems: list) -> str:
    """The variable that tells the systems apart, or 'all endogenous'."""
    if len(systems) == 1:
        return "all endogenous"
    shared = set.intersection(*(set(s) for s in systems))
    return ", ".join(v for v in system if v not in shared)


def lag_ranges(lags) -> str:
    """'lags 1-24, 48' for [1, ..., 24, 48]."""
    lags, parts, start = sorted(lags), [], None
    for i, lag in enumerate(lags):
        start = lag if start is None else start
        if i + 1 == len(lags) or lags[i + 1] != lag + 1:
            parts.append(f"{start}-{lag}" if lag > start else f"{lag}")
            start = None
    return "lags " + ", ".join(parts)


def plot_selection(criteria: pd.DataFrame, choices: pd.DataFrame, criterion: str, literature_lags: list, path):
    zone_names = list(dict.fromkeys(choices["zone"]))
    ncols = int(choices.groupby("zone").size().max())
    fig, grid = plt.subplots(len(zone_names), ncols, figsize=(5 * ncols, 3.8 * len(zone_names)), squeeze=False)
    used = []
    for r, zone in enumerate(zone_names):
        zone_choices = choices[choices["zone"] == zone].to_dict("records")
        for c, choice in enumerate(zone_choices):
            ax = grid[r][c]
            used.append(ax)
            d = criteria[(criteria["zone"] == zone) & (criteria["system"] == choice["system"])]
            orders, lit = d[d["order"] != LITERATURE], d[d["order"] == LITERATURE]
            for ic, (criterion_name, color) in CRITERION_STYLE.items():
                low = orders[ic].min()
                ax.plot(orders["n_lag_matrices"], orders[ic] - low, color=color, linewidth=1.6, label=criterion_name)
                ax.scatter(choice[criterion_name], 0, marker="o", s=40, color=color, zorder=3)
                ax.scatter(lit["n_lag_matrices"], lit[ic] - low, marker="*", s=110, color=color, zorder=3)
            ax.scatter([], [], marker="o", color="0.3", label="lowest value of each criterion")
            ax.scatter([], [], marker="*", s=110, color="0.3", label=f"{lag_ranges(literature_lags)} (literature)")
            ax.axvline(choice["chosen"], color="0.35", linewidth=1, linestyle="--",
                       label=f"chosen order ({criterion.upper()})")
            bound = int(orders["n_lag_matrices"].max())
            ax.set_xlim(0, bound + 1)
            ax.xaxis.set_major_locator(MultipleLocator(6 * max(1, bound // 48)))
            style_axes(ax, f"{zone} — {', '.join(map(name, choice['system'].split(', ')))}", "Number of lag matrices p",
                       "IC(p) − lowest IC")
        for ax in grid[r][len(zone_choices):]:
            ax.axis("off")
    save_figure(fig, used, "VAR lag selection: information criteria by lag order (0 = the criterion's lowest value)",
                path)


def write_report(criteria: pd.DataFrame, choices: pd.DataFrame, setup: list, criterion: str, literature_lags: list,
                 path):
    names = [name for name, _ in CRITERION_STYLE.values()]
    distance = []
    for ch in choices.to_dict("records"):
        d = criteria[(criteria["zone"] == ch["zone"]) & (criteria["system"] == ch["system"])].set_index("order")
        lows = d.drop(index=LITERATURE)[list(CRITERIA)].min()
        lowest_of = {}
        for name in names:
            lowest_of.setdefault(ch[name], []).append(name)
        rows = [(order, ", ".join(of) + (" (chosen)" if order == ch["chosen"] else "")) for order, of in
                sorted(lowest_of.items())] + [(LITERATURE, "literature (comparison)")]
        for order, role in rows:
            distance.append({"zone": ch["zone"], "system": ch["system"],
                             "lags": lag_ranges(literature_lags if order == LITERATURE else range(1, order + 1)),
                             "lowest value of": role,
                             **{f"{CRITERION_STYLE[ic][0]} − lowest": round(d.loc[order, ic] - lows[ic], 4)
                                for ic in CRITERIA}})
    table = choices.drop(columns="variables").rename(columns={"chosen": f"chosen ({criterion.upper()})",
                                                              "searched": "orders searched"})
    text = [
        "# Lag selection", "",
        "VARX(p, 0): p lags of the endogenous variables; exogenous variables and calendar dummies as listed in "
        "main.py. Every order p is fitted by least squares on the same T hours and scored by "
        "IC(p) = ln|S(p)| + (c_T / T) p K², with c_T = ln T (BIC), 2 ln ln T (HQ), 2 (AIC); lower = better.", "",
        f"**Rule:** the order with the lowest {criterion.upper()}. For T ≥ 16 the penalties are ordered, so always "
        "p(BIC) ≤ p(HQ) ≤ p(AIC). If the choice is the largest order searched, the search is repeated up to twice "
        "that order.", "",
        "## Systems and regressors", "", md_table(pd.DataFrame(setup)), "",
        "## Choices", "", md_table(table), "",
        "## Distance from each criterion's lowest value", "",
        f"0 = the criterion's own choice. The literature structure ({lag_ranges(literature_lags)}) is scored on the "
        "same hours for comparison.", "", md_table(pd.DataFrame(distance)), "",
    ]
    path.write_text("\n".join(text), encoding="utf-8")
    print(f"  wrote {path.name}")


# ---------------------------------------------------------------------------
# ENTRY POINT
# ---------------------------------------------------------------------------
def run(df: pd.DataFrame, spec: Spec, plot_dir, criterion: str = "aic", max_lag: int = 48,
        literature_lags: list = (*range(1, 25), 48)) -> pd.DataFrame:
    if criterion not in CRITERIA:
        raise ValueError(f"criterion must be one of {list(CRITERIA)}, not {criterion!r}")
    out = plot_dir / "lag_selection"
    out.mkdir(parents=True, exist_ok=True)
    crit_rows, choice_rows, setup = [], [], []
    for zone in zones(df):
        dz, exog, systems = zone_inputs(df, spec, zone)
        setup.append({"zone": zone, "systems": "; ".join(f"({', '.join(s)})" for s in systems),
                      "exogenous": ", ".join(exog) or "none", "dummies": ", ".join(spec.calendar) or "none"})
        for system in systems:
            name = system_label(system, systems)
            print(f"  [{zone}] lag selection: {', '.join(system)} (orders 1..{max_lag})")
            sel = select_order(dz, system, exog, spec.calendar, criterion, max_lag, literature_lags)
            for order, ics in sel["ics"].items():
                crit_rows.append({"zone": zone, "system": name, "order": order,
                                  "n_lag_matrices": len(literature_lags) if order == LITERATURE else order, **ics})
            choice_rows.append({"zone": zone, "system": name, "variables": ", ".join(system), "T": sel["T"],
                                "searched": f"1-{sel['bound']}",
                                **{CRITERION_STYLE[ic][0]: sel["best"][ic] for ic in CRITERIA},
                                "chosen": sel["best"][criterion]})
    criteria, choices = pd.DataFrame(crit_rows), pd.DataFrame(choice_rows)
    plot_selection(criteria, choices, criterion, literature_lags, out / "lag_selection.png")
    write_report(criteria, choices, setup, criterion, literature_lags, out / "LAG_SELECTION.md")
    choices[["zone", "variables", "chosen", *(CRITERION_STYLE[ic][0] for ic in CRITERIA)]].rename(
        columns={"chosen": "p"}).to_csv(out / ORDERS_FILE, index=False)
    criteria.to_csv(out / "criteria.csv", index=False)
    print(f"  wrote {ORDERS_FILE}")
    for r in choices.to_dict("records"):
        print(f"  {r['zone']} {r['system']}: BIC {r['BIC']}, HQ {r['HQ']}, AIC {r['AIC']} -> chosen {r['chosen']}")
    return choices
