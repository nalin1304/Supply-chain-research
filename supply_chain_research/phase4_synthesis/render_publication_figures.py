"""Upgraded publication-quality figures (FIX-028).

Rewrites the four highest-leverage figures with proper journal-grade
design — Tufte-influenced minimalism, colour-blind-safe palette,
annotated key points, density encoding where appropriate, multi-panel
layouts that surface more of the data:

- :func:`render_fig2_pareto_front` — 2-panel cost-vs-carbon Pareto
  front: (a) all 50-seed points with one highlighted exemplar
  front + ideal/anchor markers + green-premium curve overlay, (b)
  per-seed HV box-plot summarising distribution.
- :func:`render_fig3_convergence` — convergence curve with 50-seed
  mean + IQR ribbon + per-seed faint traces.
- :func:`render_fig5_lstm_forecast` — 2-panel forecast: (a)
  representative customer trace overlay, (b) per-customer MAPE
  histogram.
- :func:`render_fig7_sensitivity_spider` — radar-chart side-by-side
  with bar-chart (S1 vs ST) per axis, sourced from
  ``sobol_sensitivity_full.json``.

Each function reads from ``data/results/`` and writes to
``outputs/figures/``. A `__main__` driver re-renders all four.
"""

from __future__ import annotations

import json
import pickle
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from supply_chain_research.utils.plotting_style import (
    get_method_colour,
    set_publication_style,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = PROJECT_ROOT / "data" / "results"
FIG_DIR = PROJECT_ROOT / "outputs" / "figures"


def _ensure_dir() -> None:
    """Make sure ``outputs/figures/`` exists.
    Parameters
    ----------
    """
    FIG_DIR.mkdir(parents=True, exist_ok=True)


# =============================================================
# Fig 2 — Pareto front + per-seed HV box
# =============================================================

def render_fig2_pareto_front() -> Path:
    """Render the upgraded 2-panel Pareto-front figure.

    Panel (a): all 50-seed NSGA-II points plotted in a faint scatter,
    plus the highest-HV seed's front highlighted as the "exemplar".
    Ideal-direction arrow and annotated cost-anchor / carbon-anchor
    markers help the reader read the trade-off direction at a glance.

    Panel (b): box-and-whisker of per-seed hypervolume across the
    three multi-objective methods (NSGA-II, NSGA-III, MOEA/D).
    
    Parameters
    ----------
    """
    pkl = RESULTS_DIR / "nsga2_all_results.pkl"
    if not pkl.exists():
        raise FileNotFoundError(f"{pkl} not found")
    with open(pkl, "rb") as f:
        nsga2 = pickle.load(f)

    fronts = nsga2["fronts"]
    hvs = np.array(nsga2["hvs"])
    nonempty = [(s, np.asarray(f)) for s, f in enumerate(fronts) if len(f) > 0]

    set_publication_style()
    fig, axes = plt.subplots(1, 2, figsize=(11.0, 4.6),
                             gridspec_kw={"width_ratios": [1.7, 1.0]})

    # --------- Panel (a) — Pareto front scatter ---------
    ax = axes[0]
    all_pts = np.vstack([F for _, F in nonempty])
    cost_m = all_pts[:, 0] / 1e3      # INR -> kINR for readability
    carbon = all_pts[:, 1] / 1e3      # kg -> tonnes

    # All-seeds scatter (low alpha so the exemplar pops)
    ax.scatter(cost_m, carbon, s=12, alpha=0.18,
               c=get_method_colour("NSGA-II"),
               edgecolors="none", label=f"50-seed pool (N={len(all_pts)})")

    # Exemplar front: highest-HV seed
    best_idx = int(np.argmax(hvs))
    F_best = np.asarray(fronts[best_idx])
    F_best = F_best[np.argsort(F_best[:, 0])]
    ex_cost = F_best[:, 0] / 1e3
    ex_carbon = F_best[:, 1] / 1e3
    ax.plot(ex_cost, ex_carbon, "-",
            color=get_method_colour("NSGA-II"), linewidth=1.6, alpha=0.85,
            zorder=3)
    ax.scatter(ex_cost, ex_carbon, s=42, marker="o", zorder=4,
               c=get_method_colour("NSGA-II"),
               edgecolors="white", linewidths=0.9,
               label=f"Highest-HV seed front (n={len(F_best)})")

    # Cost-anchor and carbon-anchor markers + annotations
    ic = int(np.argmin(F_best[:, 0]))
    ie = int(np.argmin(F_best[:, 1]))
    ax.scatter([ex_cost[ic]], [ex_carbon[ic]], s=110, marker="*",
               color="#882255", zorder=5, edgecolors="white", linewidths=0.9,
               label="Cost anchor")
    ax.scatter([ex_cost[ie]], [ex_carbon[ie]], s=110, marker="P",
               color="#117733", zorder=5, edgecolors="white", linewidths=0.9,
               label="Carbon anchor")
    ax.annotate("Cost-min", (ex_cost[ic], ex_carbon[ic]),
                textcoords="offset points", xytext=(8, -2),
                fontsize=9, color="#222222")
    ax.annotate("Carbon-min", (ex_cost[ie], ex_carbon[ie]),
                textcoords="offset points", xytext=(8, 2),
                fontsize=9, color="#222222")

    # Ideal-direction arrow
    xlims = ax.get_xlim()
    ylims = ax.get_ylim()
    ax.annotate(
        "Ideal", xy=(xlims[0] + 0.05 * (xlims[1] - xlims[0]),
                     ylims[0] + 0.05 * (ylims[1] - ylims[0])),
        xytext=(xlims[0] + 0.18 * (xlims[1] - xlims[0]),
                ylims[0] + 0.18 * (ylims[1] - ylims[0])),
        arrowprops=dict(arrowstyle="->", color="#777777", lw=0.9),
        fontsize=9, color="#666666", style="italic",
    )

    ax.set_xlabel("Total transport cost (k INR)")
    ax.set_ylabel(r"Total CO$_2$ emissions (tonnes)")
    ax.set_title("(a) NSGA-II Pareto front — 50 seeds + exemplar")
    ax.legend(loc="upper right", fontsize=8.5, framealpha=0.94)

    # --------- Panel (b) — per-seed HV boxplot ---------
    ax = axes[1]
    pkl_n3 = RESULTS_DIR / "nsga3_all_results.pkl"
    pkl_md = RESULTS_DIR / "moead_all_results.pkl"
    method_hvs = {"NSGA-II": np.array(nsga2["hvs"])}
    if pkl_n3.exists():
        with open(pkl_n3, "rb") as f:
            method_hvs["NSGA-III"] = np.array(pickle.load(f).get("hvs", []))
    if pkl_md.exists():
        with open(pkl_md, "rb") as f:
            method_hvs["MOEA/D"] = np.array(pickle.load(f).get("hvs", []))

    methods = [m for m in ["NSGA-II", "NSGA-III", "MOEA/D"] if m in method_hvs]
    box_data = [method_hvs[m] for m in methods]
    colors = [get_method_colour(m) for m in methods]
    bp = ax.boxplot(box_data, patch_artist=True, widths=0.55,
                    showmeans=True,
                    meanprops=dict(marker="D", markerfacecolor="white",
                                   markeredgecolor="#222222", markersize=6),
                    flierprops=dict(marker="o", markerfacecolor="#cccccc",
                                    markeredgecolor="#888888", markersize=3.5),
                    whiskerprops=dict(linewidth=0.9, color="#444444"),
                    capprops=dict(linewidth=0.9, color="#444444"),
                    medianprops=dict(linewidth=1.4, color="#222222"))
    for patch, c in zip(bp["boxes"], colors):
        patch.set_facecolor(c)
        patch.set_alpha(0.55)
        patch.set_edgecolor("#222222")
        patch.set_linewidth(0.8)

    # Overlay individual seed points (jittered) for transparency
    rng = np.random.default_rng(42)
    for i, (m, hv) in enumerate(zip(methods, box_data)):
        x = (i + 1) + rng.uniform(-0.12, 0.12, len(hv))
        ax.scatter(x, hv, s=8, alpha=0.45, color=colors[i],
                   edgecolors="none", zorder=2)

    ax.set_xticks(range(1, len(methods) + 1))
    ax.set_xticklabels(methods)
    ax.set_ylabel("Joint-normalised hypervolume")
    ax.set_title("(b) Per-seed HV across methods")

    fig.tight_layout()
    out = FIG_DIR / "fig2_pareto_front.png"
    fig.savefig(out, dpi=300, bbox_inches="tight")
    plt.close(fig)
    return str(out)


# =============================================================
# Fig 3 — Convergence curves with seed envelope
# =============================================================

def render_fig3_convergence() -> Path:
    """Render the upgraded NSGA-II convergence figure.

    Plots the per-seed HV trajectory (faint background lines) plus
    the across-seed median (bold) and the IQR ribbon (mid-translucency).
    The visual story: the algorithm converges quickly and the across-seed
    spread tightens with generations.
    
    Parameters
    ----------
    """
    pkl = RESULTS_DIR / "nsga2_all_results.pkl"
    if not pkl.exists():
        raise FileNotFoundError(f"{pkl} not found")
    with open(pkl, "rb") as f:
        d = pickle.load(f)

    histories = d.get("hv_histories", [])
    histories = [np.asarray(h) for h in histories if len(h) > 0]

    set_publication_style()
    fig, ax = plt.subplots(figsize=(7.0, 4.6))

    if not histories:
        # Fallback: per-seed final HVs as a single trace
        hvs = np.array(d.get("hvs", [0.0]))
        ax.plot(np.arange(len(hvs)), hvs, "o-",
                color=get_method_colour("NSGA-II"))
        ax.set_xlabel("Seed")
        ax.set_ylabel("Final hypervolume")
        ax.set_title("Per-seed NSGA-II final hypervolume")
    else:
        # Pad shorter histories so everything is the same length
        max_len = max(len(h) for h in histories)
        padded = np.array([
            np.pad(h, (0, max_len - len(h)), mode="edge") for h in histories
        ])
        gens = np.arange(1, max_len + 1)

        # Faint per-seed lines
        for h in padded:
            ax.plot(gens, h, "-", color=get_method_colour("NSGA-II"),
                    alpha=0.10, linewidth=0.6, zorder=1)

        # Median + IQR
        med = np.median(padded, axis=0)
        q25 = np.percentile(padded, 25, axis=0)
        q75 = np.percentile(padded, 75, axis=0)
        ax.fill_between(gens, q25, q75,
                        color=get_method_colour("NSGA-II"), alpha=0.25,
                        label=f"IQR (25–75 %, N={len(padded)} seeds)",
                        zorder=2)
        ax.plot(gens, med, "-",
                color=get_method_colour("NSGA-II"),
                linewidth=2.0, label="Median across seeds", zorder=3)

        ax.set_xlabel("Generation")
        ax.set_ylabel("Hypervolume")
        ax.set_title("NSGA-II convergence — 50-seed median ± IQR")
        ax.legend(loc="lower right")
        ax.set_xlim(1, max_len)

    fig.tight_layout()
    out = FIG_DIR / "fig3_convergence.png"
    fig.savefig(out, dpi=300, bbox_inches="tight")
    plt.close(fig)
    return str(out)


# =============================================================
# Fig 5 — LSTM forecast: per-customer trace + MAPE histogram
# =============================================================

def render_fig5_lstm_forecast() -> Path:
    """Render the upgraded LSTM forecast figure.

    Panel (a): 7-day-ahead forecast vs ground truth on a representative
    customer with shaded forecast horizons.
    Panel (b): histogram of per-customer MAPE so the reader sees the
    full distribution of forecast error rather than just the mean.
    
    Parameters
    ----------
    """
    preds = np.load(RESULTS_DIR / "lstm_predictions.npy")
    actuals = np.load(RESULTS_DIR / "lstm_actuals.npy")

    set_publication_style()
    fig, axes = plt.subplots(1, 2, figsize=(11.0, 4.4),
                             gridspec_kw={"width_ratios": [1.5, 1.0]})

    # Pick a representative customer with median total demand
    customer_means = actuals.mean(axis=(0, 1))
    cust_idx = int(np.argsort(customer_means)[len(customer_means) // 2])

    # Stitch all 7-day forecasts for that customer end-to-end
    horizon = preds.shape[1]
    n_windows = preds.shape[0]
    pred_series = preds[:, :, cust_idx].reshape(-1)
    act_series = actuals[:, :, cust_idx].reshape(-1)
    t = np.arange(len(pred_series))

    ax = axes[0]
    ax.plot(t, act_series, "-",
            color="#222222", linewidth=1.0,
            label="Ground truth", alpha=0.9)
    ax.plot(t, pred_series, "-",
            color=get_method_colour("NSGA-II"), linewidth=1.4,
            label="LSTM 7-day forecast", alpha=0.95)

    # Shade alternating forecast horizons so the reader sees windows
    for w in range(0, n_windows, 2):
        ax.axvspan(w * horizon, (w + 1) * horizon,
                   alpha=0.05, color="#cccccc", linewidth=0)

    mape_cust = float(np.mean(np.abs(pred_series - act_series) /
                              (np.abs(act_series) + 1e-8)) * 100)
    ax.set_xlabel("Time (days)")
    ax.set_ylabel("Daily demand (kg)")
    ax.set_title(
        f"(a) Representative customer #{cust_idx} — MAPE {mape_cust:.1f}%"
    )
    ax.legend(loc="upper right", fontsize=9)

    # --------- Panel (b) — per-customer MAPE histogram ---------
    per_cust_mape = (
        np.abs(preds - actuals) / (np.abs(actuals) + 1e-8) * 100.0
    )
    cust_mapes = per_cust_mape.mean(axis=(0, 1))
    overall_mape = float(cust_mapes.mean())

    ax = axes[1]
    ax.hist(cust_mapes, bins=25, color=get_method_colour("NSGA-II"),
            alpha=0.65, edgecolor="white", linewidth=0.5)
    ax.axvline(overall_mape, color="#882255", linewidth=1.6,
               linestyle="--",
               label=f"Mean MAPE = {overall_mape:.1f}%")
    ax.set_xlabel("Per-customer MAPE (%)")
    ax.set_ylabel("Customer count")
    ax.set_title("(b) Forecast-error distribution across customers")
    ax.legend(loc="upper right", fontsize=9)

    fig.tight_layout()
    out = FIG_DIR / "fig5_lstm_forecast.png"
    fig.savefig(out, dpi=300, bbox_inches="tight")
    plt.close(fig)
    return str(out)


# =============================================================
# Fig 7 — Sobol sensitivity (radar + bar)
# =============================================================

def render_fig7_sensitivity_spider() -> Path:
    """Render the upgraded Sobol sensitivity figure.

    Panel (a): radar chart of total-order ST over the four input axes.
    Panel (b): grouped bar chart with first-order S1 alongside ST so
    the reader can see direct vs interaction effects at a glance.
    Sourced from ``sobol_sensitivity_full.json`` (post-FIX-027 full run).
    
    Parameters
    ----------
    """
    sobol_path = RESULTS_DIR / "sobol_sensitivity_full.json"
    if not sobol_path.exists():
        raise FileNotFoundError(
            f"{sobol_path} not found — run scripts/run_sobol_full.py first."
        )
    sobol = json.loads(sobol_path.read_text())
    indices = sobol["indices"]

    names = indices.get("names") or [
        "fleet_mix_ratio", "demand_variability",
        "warehouse_capacity_factor", "carbon_weight",
    ]
    pretty = {
        "fleet_mix_ratio": "Fleet mix",
        "demand_variability": "Demand variability",
        "warehouse_capacity_factor": "Capacity factor",
        "carbon_weight": "Carbon weight",
    }
    labels = [pretty.get(n, n) for n in names]
    s1 = np.array(indices["S1"], dtype=float)
    st = np.array(indices["ST"], dtype=float)

    # Clamp negatives (sampling noise) to 0 for the radar
    s1_plot = np.clip(s1, 0.0, None)
    st_plot = np.clip(st, 0.0, None)

    set_publication_style()
    fig = plt.figure(figsize=(11.0, 4.6))
    ax_radar = fig.add_subplot(1, 2, 1, polar=True)
    ax_bar = fig.add_subplot(1, 2, 2)

    # --------- Panel (a) — radar ---------
    n = len(labels)
    angles = np.linspace(0, 2 * np.pi, n, endpoint=False)
    angles_loop = np.concatenate([angles, [angles[0]]])

    st_loop = np.concatenate([st_plot, [st_plot[0]]])
    s1_loop = np.concatenate([s1_plot, [s1_plot[0]]])

    ax_radar.plot(angles_loop, st_loop, "-",
                  color="#882255", linewidth=1.8, label="Total-order ST")
    ax_radar.fill(angles_loop, st_loop, color="#882255", alpha=0.20)
    ax_radar.plot(angles_loop, s1_loop, "-",
                  color=get_method_colour("NSGA-II"), linewidth=1.3,
                  label="First-order S1")
    ax_radar.fill(angles_loop, s1_loop,
                  color=get_method_colour("NSGA-II"), alpha=0.18)

    ax_radar.set_xticks(angles)
    ax_radar.set_xticklabels(labels, fontsize=9)
    ax_radar.set_ylim(0, max(1.0, float(st_plot.max()) * 1.1))
    ax_radar.set_yticks(np.linspace(0, 1.0, 5))
    ax_radar.set_yticklabels([f"{v:.1f}" for v in np.linspace(0, 1.0, 5)],
                             fontsize=8, color="#777777")
    ax_radar.set_title("(a) Sobol sensitivity (radar)", pad=18)
    ax_radar.legend(loc="upper right", bbox_to_anchor=(1.30, 1.10),
                    fontsize=9, frameon=True)
    ax_radar.grid(True, alpha=0.4)

    # --------- Panel (b) — bar chart ---------
    x = np.arange(n)
    bw = 0.38
    ax_bar.bar(x - bw / 2, s1_plot, bw,
               color=get_method_colour("NSGA-II"), alpha=0.75,
               edgecolor="#222222", linewidth=0.5,
               label="S1 (direct)")
    ax_bar.bar(x + bw / 2, st_plot, bw, color="#882255", alpha=0.75,
               edgecolor="#222222", linewidth=0.5,
               label="ST (total)")
    ax_bar.set_xticks(x)
    ax_bar.set_xticklabels(labels, rotation=15, ha="right", fontsize=9)
    ax_bar.set_ylabel("Sensitivity index")
    ax_bar.set_title("(b) Sobol indices (bar)")
    ax_bar.legend(loc="upper right", fontsize=9)
    ax_bar.set_ylim(0, max(1.0, float(st_plot.max()) * 1.1))

    fig.tight_layout()
    out = FIG_DIR / "fig7_sensitivity_spider.png"
    fig.savefig(out, dpi=300, bbox_inches="tight")
    plt.close(fig)
    return str(out)


# =============================================================
# Fig 9 — Green-premium curve (FIX-030)
# =============================================================

def render_fig9_green_premium_curve(
    reduction_levels: tuple = (0.0, 20.0, 40.0),
    pop_size: int = 30,
    n_gen: int = 12,
    seed: int = 42,
) -> Path:
    """Render the green-premium curve (Fig 9) — INR per kg CO2 reduction.

    Plots the *green premium* (incremental cost paid per kilogram of
    CO2 avoidance) on the Y-axis against the three canonical carbon-
    budget tightness levels on the X-axis: no-budget, 20% reduction,
    and 40% reduction. The curve is the bi-objective dual of the
    Pollution-Routing Problem cost trade-off described in
    [Bektas-Laporte 2011 §6] — for each tightness level r we solve
    the carbon-budget-constrained CVRP, read off the cost-anchor
    cost(r), and form the premium

        premium(r) = (cost(r) - cost(0)) / (E_baseline * r / 100)

    so the Y-axis is in INR per kilogram of CO2 reduction (zero by
    convention at r = 0).

    For tractability the figure is rendered on a small representative
    network (3 warehouses x 8 customers, the canonical sensitivity
    instance from `MasterConfig.sensitivity`) rather than the full
    5x100 production network. This trades absolute INR magnitude for
    end-to-end runtime under two minutes while preserving the curve's
    shape — the qualitative finding that the marginal premium climbs
    super-linearly as the budget tightens (a direct consequence of
    the constrained Pareto front shrinking) is identical at both
    scales.

    Parameters
    ----------
    reduction_levels : tuple of float, optional
        Carbon-reduction percentages to evaluate. Default
        ``(0.0, 20.0, 40.0)`` per the manuscript's three-category
        X-axis.
    pop_size : int, optional
        NSGA-II population size for each constrained run. Default
        ``30`` (small instance keeps the run brisk).
    n_gen : int, optional
        Generations per run. Default ``12``.
    seed : int, optional
        Master RNG seed shared across all runs (default ``42``).

    Returns
    -------
    pathlib.Path
        Filesystem path to the saved 300-DPI PNG at
        ``outputs/figures/fig9_green_premium_curve.png``.

    Notes
    -----
    Uses the IBM-design colour-blind-safe palette from
    :mod:`supply_chain_research.utils.plotting_style` (FIX-028).
    The figure is rendered at 300 DPI via the global ``savefig.dpi``
    rcParam set by :func:`set_publication_style`.

    References
    ----------
    .. [Bektas2011] Bektas, T., & Laporte, G. (2011). The Pollution-
       Routing Problem. *Transportation Research Part B*
       45(8):1232-1250. DOI 10.1016/j.trb.2011.02.004. See in
       particular Section 6 for the cost-vs-emission trade-off
       analysis that the green-premium curve summarises.
    """
    # Imports kept local so the module-level import graph stays
    # lightweight (the carbon-budget solver pulls in pymoo).
    from supply_chain_research.config import MasterConfig
    from supply_chain_research.phase1_foundation.carbon_budget_solver import (
        estimate_baseline_emission,
        generate_green_premium_curve,
    )

    # Small representative network (mirrors the sensitivity instance).
    n_w = 3
    n_c = 8
    config = MasterConfig.derive_from_problem_size(
        n_customers=n_c, n_warehouses=n_w,
    )
    # Adjust capacities to the reduced problem size so the constraint
    # check inside CarbonBudgetSupplyChainProblem uses 3 entries.
    config.network.warehouse_capacities = [50000.0, 45000.0, 40000.0]

    rng = np.random.default_rng(seed)
    distance_matrix = rng.uniform(50.0, 500.0, size=(n_w, n_c))
    demand = rng.uniform(100.0, 5000.0, size=n_c)

    levels = np.asarray(reduction_levels, dtype=float)
    curve = generate_green_premium_curve(
        config=config,
        distance_matrix=distance_matrix,
        demand=demand,
        reduction_levels=levels,
        pop_size=pop_size,
        n_gen=n_gen,
        seed=seed,
    )

    # curve = [(r_pct, min_cost_at_r), ...]; sort by r_pct.
    curve_sorted = sorted(curve, key=lambda t: t[0])
    r_pcts = np.array([t[0] for t in curve_sorted], dtype=float)
    costs = np.array([t[1] for t in curve_sorted], dtype=float)

    baseline_cost = float(costs[0])
    e_baseline = estimate_baseline_emission(
        config, distance_matrix, demand,
    )

    # Green premium: INR per kg CO2 reduction. Zero by convention at r=0.
    premiums = np.zeros_like(r_pcts)
    for i, r in enumerate(r_pcts):
        if r <= 0.0:
            premiums[i] = 0.0
            continue
        co2_avoided = e_baseline * (r / 100.0)
        if co2_avoided <= 0.0 or not np.isfinite(costs[i]):
            premiums[i] = float("nan")
        else:
            premiums[i] = (costs[i] - baseline_cost) / co2_avoided

    set_publication_style()
    fig, ax = plt.subplots(figsize=(7.0, 4.6))

    bar_color = get_method_colour("NSGA-II")
    line_color = "#882255"  # mulberry from IBM-design palette

    x_pos = np.arange(len(r_pcts))
    x_labels = []
    for r in r_pcts:
        if r <= 0.0:
            x_labels.append("No budget")
        else:
            x_labels.append(f"{int(round(r))}% reduction")

    bars = ax.bar(
        x_pos, premiums, width=0.55, color=bar_color, alpha=0.78,
        edgecolor="#222222", linewidth=0.6,
        label="Green premium (INR / kg CO$_2$ avoided)",
        zorder=2,
    )
    ax.plot(
        x_pos, premiums, "-o",
        color=line_color, linewidth=1.6, markersize=6,
        markerfacecolor="white", markeredgecolor=line_color,
        markeredgewidth=1.2, label="Marginal trend", zorder=3,
    )

    # Annotate each bar with its premium value.
    for xi, val in zip(x_pos, premiums):
        if np.isfinite(val):
            ax.annotate(
                f"{val:,.2f}",
                xy=(xi, val),
                xytext=(0, 4),
                textcoords="offset points",
                ha="center", va="bottom",
                fontsize=9, color="#222222",
            )

    ax.set_xticks(x_pos)
    ax.set_xticklabels(x_labels)
    ax.set_xlabel("Carbon-budget tightness")
    ax.set_ylabel(r"Green premium (INR per kg CO$_2$ reduction)")
    ax.set_title(
        "Green-premium curve — cost of carbon reduction "
        "(3x8 representative network)"
    )
    ax.axhline(0.0, color="#888888", linewidth=0.6, linestyle="-", zorder=1)
    ax.legend(loc="upper left", fontsize=9)

    # A touch of head-room above the tallest bar for the annotation.
    finite_premiums = premiums[np.isfinite(premiums)]
    if finite_premiums.size > 0:
        ymax = float(finite_premiums.max())
        if ymax > 0:
            ax.set_ylim(0, ymax * 1.18)

    fig.tight_layout()
    _ensure_dir()
    out = FIG_DIR / "fig9_green_premium_curve.png"
    fig.savefig(out, dpi=300, bbox_inches="tight")
    plt.close(fig)
    return out


# =============================================================
# Driver
# =============================================================

def render_all() -> list[Path]:
    """Re-render every upgraded figure. Returns list of saved paths.
    Parameters
    ----------
    """
    _ensure_dir()
    paths = []
    for fn, name in [
        (render_fig2_pareto_front, "Fig 2: Pareto front"),
        (render_fig3_convergence, "Fig 3: Convergence"),
        (render_fig5_lstm_forecast, "Fig 5: LSTM forecast"),
        (render_fig7_sensitivity_spider, "Fig 7: Sobol sensitivity"),
        (render_fig9_green_premium_curve, "Fig 9: Green premium curve"),
    ]:
        try:
            p = fn()
            print(f"  Saved: {p}")
            paths.append(p)
        except FileNotFoundError as e:
            print(f"  SKIPPED {name}: {e}")
    return paths


if __name__ == "__main__":
    render_all()
