"""
VARX.py — the VARX(p, 0) of each bidding zone and system, its Granger causality
tests and its impulse responses (the "varx" step of main.py). p is the lag
order chosen by the lag_selection step (lag_orders.csv); the regressors are
those of lag_selection.py, fitted by least squares, equation by equation, on
every hour valid for p:

    y_t = c + A_1 y_(t-1) + ... + A_p y_(t-p) + B x_t + D d_t + u_t

The variables of each system are ordered `shock_order` first (the forecast
errors), then the rest (the spread): the order of the Cholesky factorisation.

UNCERTAINTY: the residual checks found a residual variance that changes over
time and a weekly pattern in the demand-error equation. Both tools below allow
for such dependence within `window_hours` (336 = two weeks).

GRANGER CAUSALITY: does variable a help predict variable b, given the rest of
the model? H0: the p lag coefficients of a in the equation of b are all 0.
    W = (Rβ)' V⁻¹ (Rβ),   V = Σ_t h_t h_t',   h_t = R (X'X)⁻¹ x_t u_t
(heteroskedasticity-robust). The p-value comes from the block wild bootstrap
below, run under H0: y* = X_0 β_0 + η_b u_0,t with the model without a's lags
(β_0, u_0), W* recomputed for every draw, p = (1 + #{W* >= W}) / (draws + 1).
So the test allows for the changing variance and for residual correlation
within blocks of window_hours. Not a chi² critical value with a Newey-West
window of window_hours: with p = 25 restrictions, one year holds only ~26
two-week blocks, too few to estimate their long-run covariance; in a
simulation without causality that test rejected in 93% of samples at the 5%
level, the bootstrap test in 3-6%.

IMPULSE RESPONSES: orthogonalised by the Cholesky factor of the residual
covariance, Σ_u = P P' (P lower triangular): a shock to one variable can move
the variables after it in the order within the hour, but not those before it.
The response at horizon h to a one-standard-deviation shock is
    Θ_h = Φ_h P,   Φ_0 = I,   Φ_h = Σ_(i = 1..min(h, p)) Φ_(h-i) A_i.
BANDS: block wild bootstrap, fixed design (Shao 2010, "dependent wild
bootstrap"). The hourly grid is cut into blocks of window_hours; in each draw,
every block gets one random sign η_b = ±1, applied to the two estimating
equations of the model:
    coefficients  β* = β + (X'X)⁻¹ X'u*,  u*_t = η_b u_t   (y* = X β + u*)
    covariance    Σ* = Σ + (1/T) Σ_t η_b (u_t u_t' - Σ)
Each residual stays in its own hour, so the changing variance is kept, and so
is the correlation within a block; gaps in the data need no special
treatment. Σ* is bootstrapped as the mean it is: re-estimating it from the
residuals of u* would give the same Σ in every draw (η² = 1), and the band of
the responses in the hour of the shock (Θ_0 = P) would miss its uncertainty.
The responses are recomputed from (β*, Σ*); the band is the percentile band
of the draws.

ROBUSTNESS: each model is refitted with other lag structures (ROBUSTNESS):
    BIC order, HQ order   lags 1..p of the order chosen by BIC / HQ (lag_selection)
    literature            literature_lags (Spodniak et al.: lags 1-24 and 48)
    weekly lags           the chosen lags plus weekly_lags (the weekly residual
                          pattern of the demand error, residual_checks)
The Granger tests are repeated (all lags of the cause) and the responses
recomputed. Reported: every p-value and the structures under which a
decision changes; in how many hours each spread response stays inside the
band of the chosen model. Structures with the same lags are fitted once.
OTHER ORDERS: the responses of the chosen model with the Cholesky factor of
other_orders (e.g. the spread first: a forecast-error shock then cannot move
the spread within the hour). The model and its Granger tests do not depend
on the order; only the split of the same-hour residual correlation does.
Each order gets its own band from the same bootstrap draws. Reported: the
same-hour response, the response one hour later with the band of each order,
and the hours inside the band of the chosen order.
Every Granger test and the bands draw from their own random stream (seeded
by seed and what is tested), so a result does not depend on the others.

OUTPUT (plots/<name>/varx/)
    VARX.md                  the models (order, fit, residual correlation,
                             shock sizes), the Granger tests, the robustness
    irf_<zone>.png           response of each spread to one-s.d. shocks of
                             every variable of its model, with the band and
                             the responses of the robustness structures
    impulse_responses.csv    every response: zone, system, response, shock,
                             horizon, estimate, band, robustness estimates,
                             other orders with their bands
    models.csv, equations.csv, correlations.csv, granger.csv,
    robustness_structures.csv, irf_robustness.csv
                             the same results as data (read by the web step)
"""

import zlib

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.ticker import MultipleLocator

from common import column_units, md_table, save_figure, style_axes, zone_color, zones
from dataframe.building import Spec
from dataframe.documentation import LITERATURE
from VAR_tests import lag_selection as ls

FOLDERS = ["varx"]
ROBUSTNESS = {"BIC order": ":", "HQ order": "-.", "literature": (0, (5, 1)), "weekly lags": "--"}  # line styles
ORDER_COLOR, ORDER_STYLES = "#009E73", ["-", "--", ":"]  # the other Cholesky orders


def _rng(seed: int, *parts):
    """A random stream of its own for what `parts` name (zone, system, test, ...)."""
    return np.random.default_rng([seed, zlib.crc32("|".join(map(str, parts)).encode())])


def robustness_structures(order: dict, literature_lags: list, weekly_lags: list) -> dict[str, list]:
    """The lag structure of every robustness model; order = read_orders() row."""
    return {"BIC order": list(range(1, order["BIC"] + 1)), "HQ order": list(range(1, order["HQ"] + 1)),
            "literature": list(literature_lags), "weekly lags": list(range(1, order["p"] + 1)) + list(weekly_lags)}


def _name(col: str) -> str:
    return LITERATURE.get(col, {}).get("name", col)


def _size(value: float) -> str:
    return f"{value:,.0f}" if abs(value) >= 100 else f"{value:.1f}"


def _with_band(estimate: float, lower: float, upper: float) -> str:
    return f"{estimate:+.2f} [{lower:+.2f}, {upper:+.2f}]"


def _fmt_p(p: float) -> str:
    return "< 0.0001" if p < 1e-4 else f"{p:.4f}"


def cholesky_order(system: list, shock_order: list) -> list:
    """The system's variables in Cholesky order: those in shock_order first
    (in that order), then the others (in system order)."""
    return [v for v in shock_order if v in system] + [v for v in system if v not in shock_order]


# ---------------------------------------------------------------------------
# GRANGER CAUSALITY
# ---------------------------------------------------------------------------
def block_signs(model: dict, window: int, draws: int, rng) -> np.ndarray:
    """(T, draws) random signs, one per block of `window` hours of the hourly
    grid, for the hours used by the model."""
    block = np.flatnonzero(model["ok"]) // window
    return rng.choice([-1.0, 1.0], (block[-1] + 1, draws))[block]


def granger_test(model: dict, XtX_inv: np.ndarray, cause: str, effect: str, window: int, draws: int,
                 rng) -> tuple[float, int, float]:
    """(W, degrees of freedom, bootstrap p-value) of H0: the lags of `cause`
    in the equation of `effect` are all 0 (see the module docstring)."""
    X, e = model["X"], model["y_cols"].index(effect)
    idx = [model["names"].index(f"L{lag}.{cause}") for lag in model["lags"]]
    G = X @ XtX_inv[:, idx]  # row t: (R (X'X)⁻¹ x_t)'
    proj = XtX_inv @ X.T

    def wald(Y: np.ndarray) -> np.ndarray:  # one statistic per column of Y
        B = proj @ Y
        U = Y - X @ B
        return np.array([B[idx, d] @ np.linalg.solve((G * U[:, [d]]).T @ (G * U[:, [d]]), B[idx, d])
                         for d in range(Y.shape[1])])

    y = model["resid"][:, e] + X @ model["coef"][:, e]
    W = float(wald(y[:, None])[0])
    keep = np.setdiff1d(np.arange(X.shape[1]), idx)
    fitted = X[:, keep] @ np.linalg.lstsq(X[:, keep], y, rcond=None)[0]  # the model under H0
    W_star = wald(fitted[:, None] + (y - fitted)[:, None] * block_signs(model, window, draws, rng))
    return W, len(idx), float((1 + np.sum(W_star >= W)) / (draws + 1))


# ---------------------------------------------------------------------------
# IMPULSE RESPONSES
# ---------------------------------------------------------------------------
def ma_coefficients(A: np.ndarray, horizon: int) -> np.ndarray:
    """Φ_0..Φ_horizon from the lag matrices A (..., p, K, K); leading
    dimensions (e.g. bootstrap draws) are kept."""
    *batch, p, K, _ = A.shape
    Phi = np.zeros((*batch, horizon + 1, K, K))
    Phi[..., 0, :, :] = np.eye(K)
    for h in range(1, horizon + 1):
        for i in range(1, min(h, p) + 1):
            Phi[..., h, :, :] += Phi[..., h - i, :, :] @ A[..., i - 1, :, :]
    return Phi


def impulse_responses(A: np.ndarray, sigma: np.ndarray, horizon: int, order: list | None = None) -> np.ndarray:
    """Θ[..., h, i, j]: response of variable i at horizon h to a
    one-standard-deviation orthogonalised shock to variable j; order: the
    positions of the variables in the Cholesky order (default: as they are)."""
    sigma = np.asarray(sigma)
    k = np.arange(sigma.shape[-1]) if order is None else np.asarray(order)
    P = np.zeros_like(sigma)
    P[..., k[:, None], k] = np.linalg.cholesky(sigma[..., k[:, None], k])
    return ma_coefficients(A, horizon) @ P[..., None, :, :]


def response_band(A_draws: np.ndarray, sigmas: np.ndarray, horizon: int, band: float,
                  order: list | None = None) -> np.ndarray:
    """(lower, upper)[h, i, j]: the percentile band of the responses over the bootstrap draws (A_draws: draws, p,
    K, K; sigmas: draws, K, K), in the given Cholesky order."""
    return np.quantile(impulse_responses(A_draws, sigmas, horizon, order), [(1 - band) / 2, (1 + band) / 2], axis=0)


def bootstrap_draws(model: dict, window: int, draws: int, rng) -> tuple[np.ndarray, np.ndarray]:
    """Coefficients (draws, m, K) and residual covariances (draws, K, K) of
    the block wild bootstrap (see the module docstring)."""
    X, U, sigma = model["X"], model["resid"], model["sigma"]
    T, K = U.shape
    proj = np.linalg.solve(X.T @ X, X.T)                # (X'X)⁻¹ X'
    signs = block_signs(model, window, draws, rng)
    coefs = np.array([model["coef"] + proj @ (U * signs[:, [d]]) for d in range(draws)])
    deviations = (U[:, :, None] * U[:, None, :] - sigma).reshape(T, K * K)   # u_t u_t' - Σ
    sigmas = sigma + (signs.T @ deviations).reshape(draws, K, K) / T
    lowest = np.linalg.eigvalsh(sigmas)[:, 0]
    if (lowest <= 0).any():
        raise RuntimeError(f"{(lowest <= 0).sum()} bootstrap residual covariances are not positive definite")
    return coefs, sigmas


# ---------------------------------------------------------------------------
# OUTPUT
# ---------------------------------------------------------------------------
def plot_responses(zone: str, panels: list, units: dict, band: float, path):
    """panels: [(y_cols, Θ, lower, upper, P, response index, {robustness label: Θ}, {order label: Θ})], one row
    each."""
    K = max(len(p[0]) for p in panels)
    fig, grid = plt.subplots(len(panels), K, figsize=(4.6 * K, 3.6 * len(panels)), squeeze=False)
    used = []
    for r, (y_cols, theta, lower, upper, P, i, theta_robust, theta_orders) in enumerate(panels):
        hours = np.arange(theta.shape[0])
        for j, shock in enumerate(y_cols):
            ax = grid[r][j]
            used.append(ax)
            ax.fill_between(hours, lower[:, i, j], upper[:, i, j], color=zone_color(zone), alpha=0.25, linewidth=0,
                            label=f"{band:.0%} bootstrap band")
            for label, th in theta_robust.items():
                ax.plot(hours, th[:, i, j], color="0.25", linewidth=0.9, linestyle=ROBUSTNESS[label],
                        label=f"robustness: {label}")
            for n, (label, th) in enumerate(theta_orders.items()):
                ax.plot(hours, th[:, i, j], color=ORDER_COLOR, linewidth=1.3,
                        linestyle=ORDER_STYLES[n % len(ORDER_STYLES)], label=f"order: {label}")
            ax.plot(hours, theta[:, i, j], color=zone_color(zone), linewidth=1.6, label="response (chosen model)")
            ax.axhline(0, color="0.5", linewidth=0.8)
            ax.set_xlim(0, hours[-1])
            ax.xaxis.set_major_locator(MultipleLocator(6 * max(1, hours[-1] // 48)))
            style_axes(ax, f"{_name(shock)} shock (1 s.d. = {_size(P[j, j])} {units[shock]})",
                       "Hours after the shock" if r == len(panels) - 1 else "",
                       f"{_name(y_cols[i])} [{units[y_cols[i]]}]" if j == 0 else "")
        for ax in grid[r][len(y_cols):]:
            ax.axis("off")
    common = [c for c in panels[0][0] if all(c in p[0] for p in panels)]  # the variables every row shares
    order = " → ".join([_name(c) for c in common] + (["spread"] if len(common) < len(panels[0][0]) else []))
    save_figure(fig, used, f"Impulse responses, {zone}: one-s.d. Cholesky shocks\norder: {order}", path,
                legend_ncol=4)


def write_report(models: pd.DataFrame, granger: pd.DataFrame, structures: pd.DataFrame, inside: pd.DataFrame,
                 orders: pd.DataFrame, settings: dict, path):
    text = [
        "# VARX", "",
        "VARX(p, 0) per zone and system with the lag order of the lag_selection step, fitted by least squares on every "
        "hour valid for p. Variables in Cholesky order (first = not moved by the others within the hour).", "",
        f"**Granger causality:** H0 = the p lags of the cause add nothing to the equation of the effect. Wald test "
        f"with heteroskedasticity-robust covariance; p-value from {settings['draws']} block wild bootstrap draws "
        f"under H0 (blocks of {settings['window_hours']} hours); p < {settings['alpha']} = rejects.", "",
        f"**Impulse responses:** one-s.d. orthogonalised (Cholesky) shocks, {settings['horizon']} hours; "
        f"{settings['band']:.0%} band from {settings['draws']} block wild bootstrap draws (blocks of "
        f"{settings['window_hours']} hours). Figures irf_<zone>.png; every response in impulse_responses.csv.", "",
        "## Models", "", md_table(models), "",
        "## Robustness structures", "",
        "Each model is refitted with these lag structures; the Granger tests are repeated (all lags of the cause) and "
        "the responses recomputed.", "", md_table(structures), "",
        "## Granger causality", "",
        "p = the chosen model; 'p, <structure>' = the same test in a robustness model; 'decision differs in' = the "
        f"structures where p < {settings['alpha']} does not agree with the chosen model.", "", md_table(granger), "",
        "## Robustness: impulse responses", "",
        f"Hours (of {settings['horizon'] + 1}) in which the response of a robustness model lies inside the "
        f"{settings['band']:.0%} band of the chosen model.", "", md_table(inside), "",
        "## Robustness: Cholesky order", "",
        "The chosen model with other Cholesky orders: the same-hour response of the spread (hour 0), the response one "
        f"hour later with the {settings['band']:.0%} band of each order (from the same bootstrap draws), and the hours "
        f"(of {settings['horizon'] + 1}) in which the response lies inside the band of the chosen order.", "",
        md_table(orders) if len(orders) else "No other orders.", "",
    ]
    path.write_text("\n".join(text), encoding="utf-8")
    print(f"  wrote {path.name}")


# ---------------------------------------------------------------------------
# ENTRY POINT
# ---------------------------------------------------------------------------
def run(df: pd.DataFrame, spec: Spec, plot_dir, shock_order: list = (), other_orders: dict = {}, horizon: int = 48,
        window_hours: int = 336, draws: int = 1000, band: float = 0.95, alpha: float = 0.05, seed: int = 2025,
        literature_lags: list = (), weekly_lags: list = ()) -> pd.DataFrame:
    out = plot_dir / "varx"
    out.mkdir(parents=True, exist_ok=True)
    orders = ls.read_orders(plot_dir)
    units = column_units(list(spec.endogenous))
    models, granger, structure_rows, responses, inside, order_rows = [], [], [], [], [], []
    data = {"models": [], "equations": [], "correlations": [], "granger": [], "irf_robustness": []}  # as CSV files
    for zone in zones(df):
        dz, exog, systems = ls.zone_inputs(df, spec, zone)
        panels = []
        for system in systems:
            if (zone, tuple(system)) not in orders:
                raise KeyError(f"{zone} ({', '.join(system)}) has no lag order in {ls.ORDERS_FILE}: run the "
                               f"lag_selection step first")
            order, name = orders[(zone, tuple(system))], ls.system_label(system, systems)
            p, y_cols = order["p"], cholesky_order(system, shock_order)
            print(f"  [{zone}] VARX({p}): {', '.join(y_cols)}")
            m = ls.fit(dz, y_cols, list(range(1, p + 1)), exog, spec.calendar)
            T, K = m["resid"].shape
            Y = m["resid"] + m["X"] @ m["coef"]
            r2 = 1 - (m["resid"] ** 2).sum(axis=0) / ((Y - Y.mean(axis=0)) ** 2).sum(axis=0)
            sd = np.sqrt(np.diag(m["sigma"]))
            corr = m["sigma"] / np.outer(sd, sd)
            P = np.linalg.cholesky(m["sigma"])
            models.append({
                "zone": zone, "system": name, "variables (Cholesky order)": ", ".join(y_cols), "p": p, "T": T,
                "regressors per equation": m["X"].shape[1],
                "R²": ", ".join(f"{v:.2f}" for v in r2),
                "residual correlation": ", ".join(f"{_name(y_cols[a])} / {_name(y_cols[b])} {corr[a, b]:+.2f}"
                                                  for a in range(K) for b in range(a + 1, K)),
                "1 s.d. shock": ", ".join(f"{_name(c)} {_size(P[j, j])} {units[c]}" for j, c in enumerate(y_cols)),
            })
            data["models"].append({"zone": zone, "system": name, "p": p, "T": T, "regressors": m["X"].shape[1]})
            data["equations"] += [{"zone": zone, "system": name, "position": j, "variable": c, "r2": r2[j],
                                   "shock_sd": P[j, j], "unit": units[c]} for j, c in enumerate(y_cols)]
            data["correlations"] += [{"zone": zone, "system": name, "a": y_cols[a], "b": y_cols[b], "corr": corr[a, b]}
                                     for a in range(K) for b in range(a + 1, K)]
            structures = {"chosen": list(range(1, p + 1)),
                          **robustness_structures(order, literature_lags, weekly_lags)}
            structure_rows.append({"zone": zone, "system": name,
                                   **{label: ls.lag_ranges(lags) for label, lags in structures.items()}})
            fits = {}  # lags -> (model, (X'X)⁻¹), fitted once
            for lags in map(tuple, structures.values()):
                if lags not in fits:
                    f = m if lags == tuple(structures["chosen"]) else ls.fit(dz, y_cols, list(lags), exog,
                                                                              spec.calendar)
                    fits[lags] = (f, np.linalg.inv(f["X"].T @ f["X"]))
            for effect in y_cols:
                for cause in y_cols:
                    if cause == effect:
                        continue
                    tests = {lags: granger_test(*fits[lags], cause, effect, window_hours, draws,
                                                _rng(seed, zone, name, lags, cause, effect)) for lags in fits}
                    W, dof, pval = tests[tuple(structures["chosen"])]
                    p_robust = {label: tests[tuple(lags)][2] for label, lags in structures.items() if label != "chosen"}
                    differs = [label for label, pr in p_robust.items() if (pr < alpha) != (pval < alpha)]
                    granger.append({"zone": zone, "system": name, "cause": _name(cause), "effect": _name(effect),
                                    "W": round(W, 1), "df": dof, "p": _fmt_p(pval),
                                    "rejects": "yes" if pval < alpha else "no",
                                    **{f"p, {label}": _fmt_p(pr) for label, pr in p_robust.items()},
                                    "decision differs in": ", ".join(differs) or "-"})
                    data["granger"].append({"zone": zone, "system": name, "cause": cause, "effect": effect, "W": W,
                                            "df": dof, "p": pval, **{f"p_{label}": pr for label, pr in p_robust.items()}})
            theta = impulse_responses(ls.lag_matrices(m), m["sigma"], horizon)
            theta_robust = {label: impulse_responses(ls.lag_matrices(fits[tuple(lags)][0]),
                                                     fits[tuple(lags)][0]["sigma"], horizon)
                            for label, lags in structures.items() if label != "chosen"}
            positions = {label: [y_cols.index(v) for v in cholesky_order(system, o)] for label, o in other_orders.items()}
            theta_orders = {label: impulse_responses(ls.lag_matrices(m), m["sigma"], horizon, k)
                            for label, k in positions.items()}
            coefs, sigmas = bootstrap_draws(m, window_hours, draws, _rng(seed, zone, name, "bands"))
            A_draws = np.array([ls.lag_matrices(m, c) for c in coefs])
            lower, upper = response_band(A_draws, sigmas, horizon, band)
            order_bands = {label: response_band(A_draws, sigmas, horizon, band, k) for label, k in positions.items()}
            for i, resp in enumerate(y_cols):
                for j, shock in enumerate(y_cols):
                    responses.append(pd.DataFrame({
                        "zone": zone, "system": name, "response": resp, "shock": shock,
                        "horizon": np.arange(horizon + 1), "estimate": theta[:, i, j],
                        "lower": lower[:, i, j], "upper": upper[:, i, j],
                        **{f"estimate_{label.replace(' ', '_')}": th[:, i, j]
                           for label, th in {**theta_robust, **theta_orders}.items()},
                        **{f"{side}_{label.replace(' ', '_')}": b[s][:, i, j]
                           for label, b in order_bands.items() for s, side in enumerate(("lower", "upper"))}}))
                    if resp not in shock_order:
                        hours_in = {label: int(((lower[:, i, j] <= th[:, i, j]) & (th[:, i, j] <= upper[:, i, j])).sum())
                                    for label, th in {**theta_robust, **theta_orders}.items()}
                        key = {"zone": zone, "system": name, "response": _name(resp), "shock": _name(shock)}
                        inside.append({**key, **{label: f"{hours_in[label]} of {horizon + 1}" for label in theta_robust}})
                        row = {**key, "same hour, chosen": round(theta[0, i, j], 2),
                               "hour 1, chosen": _with_band(theta[1, i, j], lower[1, i, j], upper[1, i, j])}
                        for label, th in theta_orders.items():
                            lo, hi = order_bands[label]
                            row[f"same hour, {label}"] = round(th[0, i, j], 2)
                            row[f"hour 1, {label}"] = _with_band(th[1, i, j], lo[1, i, j], hi[1, i, j])
                            row[f"inside the band, {label}"] = f"{hours_in[label]} of {horizon + 1}"
                        order_rows.append(row)
                        data["irf_robustness"] += [{"zone": zone, "system": name, "response": resp, "shock": shock,
                                                    "structure": label, "hours_inside": n, "hours": horizon + 1}
                                                   for label, n in hours_in.items()]
            panels += [(y_cols, theta, lower, upper, P, i, theta_robust, theta_orders) for i, c in enumerate(y_cols)
                       if c not in shock_order]
        plot_responses(zone, panels, units, band, out / f"irf_{zone}.png")
    models, granger = pd.DataFrame(models), pd.DataFrame(granger)
    write_report(models, granger, pd.DataFrame(structure_rows), pd.DataFrame(inside), pd.DataFrame(order_rows),
                 {"window_hours": window_hours, "alpha": alpha, "horizon": horizon, "band": band, "draws": draws},
                 out / "VARX.md")
    pd.concat(responses, ignore_index=True).to_csv(out / "impulse_responses.csv", index=False)
    pd.DataFrame(structure_rows).to_csv(out / "robustness_structures.csv", index=False)
    for file, rows in data.items():  # the results as data (read by the web step)
        pd.DataFrame(rows).to_csv(out / f"{file}.csv", index=False)
    print("  wrote impulse_responses.csv and the result tables (.csv)")
    return granger
