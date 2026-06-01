#!/usr/bin/env python3
"""Render Figure 8: 3-panel NSGA-III Pareto-front projections (FIX-028 upgraded).

Projects the 3-objective NSGA-III front (cost, carbon, mean
delivery time) onto each pair of objectives. Density-encoded scatter
with hex-bin background, an alpha-shaded all-seed pool, and the
highest-HV seed's front overlaid as a sorted curve so the trade-off
shape is immediately visible.

Reads ``data/results/nsga3_all_results.pkl`` and writes
``outputs/figures/fig8_nsga3_projections.png``.
"""

from __future__ import annotations

import pickle
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from supply_chain_research.utils.plotting_style import (  # noqa: E402
    set_publication_style,
    get_method_colour,
)


RESULTS_PKL = PROJECT_ROOT / "data" / "results" / "nsga3_all_results.pkl"
FIG_OUT = PROJECT_ROOT / "outputs" / "figures" / "fig8_nsga3_projections.png"


def _projection_panel(ax, x, y, x_best, y_best, xlabel, ylabel, title):
    """Render one (x, y) projection panel with density encoding."""
    # Density background — hex-bin
    hb = ax.hexbin(x, y, gridsize=24, cmap="Blues",
                   linewidths=0.0, mincnt=1, alpha=0.90)
    # All-seed scatter (low alpha so the exemplar pops)
    ax.scatter(x, y, s=10, alpha=0.30,
               c=get_method_colour("NSGA-III"),
               edgecolors="none", zorder=2)
    # Exemplar (highest-HV seed) connected curve
    order = np.argsort(x_best)
    ax.plot(x_best[order], y_best[order], "-",
            color="#882255", linewidth=1.5, alpha=0.85, zorder=3)
    ax.scatter(x_best, y_best, s=36, marker="o",
               c="#882255", edgecolors="white", linewidths=0.8,
               zorder=4, label="Highest-HV seed front")
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    return hb


def main() -> None:
    """Render the 3-panel projection figure."""
    if not RESULTS_PKL.exists():
        print(f"ERROR: {RESULTS_PKL} not found.")
        sys.exit(1)
    with open(RESULTS_PKL, "rb") as f:
        data = pickle.load(f)

    fronts = data.get("fronts", [])
    nonempty = [(s, np.asarray(f)) for s, f in enumerate(fronts) if len(f) > 0]
    if not nonempty:
        print("ERROR: every NSGA-III front is empty.")
        sys.exit(1)

    P = np.vstack([F for _, F in nonempty])
    cost_m = P[:, 0] / 1e6                 # INR -> M-INR
    carbon_kt = P[:, 1] / 1e3              # kg -> tonnes
    time_h = P[:, 2] / 60.0                # min -> h

    # Highest-HV seed
    hvs = np.array(data.get("hvs", []), dtype=float)
    if len(hvs) == len(fronts) and len(hvs) > 0:
        best = int(np.argmax(hvs))
    else:
        # Fall back to seed with most points
        sizes = [len(F) for F in fronts]
        best = int(np.argmax(sizes))
    F_best = np.asarray(fronts[best])
    bx_cost = F_best[:, 0] / 1e6
    bx_carbon = F_best[:, 1] / 1e3
    bx_time = F_best[:, 2] / 60.0

    set_publication_style()
    fig, axes = plt.subplots(1, 3, figsize=(15.0, 4.6))

    h0 = _projection_panel(
        axes[0], cost_m, carbon_kt, bx_cost, bx_carbon,
        "Total cost (M INR)", r"Total carbon (tonnes CO$_2$)",
        "(a) Cost vs Carbon",
    )
    h1 = _projection_panel(
        axes[1], cost_m, time_h, bx_cost, bx_time,
        "Total cost (M INR)", "Mean delivery time (h)",
        "(b) Cost vs Time",
    )
    _projection_panel(
        axes[2], carbon_kt, time_h, bx_carbon, bx_time,
        r"Total carbon (tonnes CO$_2$)", "Mean delivery time (h)",
        "(c) Carbon vs Time",
    )

    # Single shared colorbar reading from panel (a)
    cbar = fig.colorbar(h0, ax=axes, orientation="vertical",
                        fraction=0.025, pad=0.02, shrink=0.85)
    cbar.set_label("Density (points / hex)", fontsize=9)

    axes[0].legend(loc="upper right", fontsize=8.5, framealpha=0.92)

    fig.suptitle(
        f"NSGA-III 3-objective Pareto front — pairwise projections "
        f"({len(nonempty)} seeds, {len(P)} total points; "
        f"highlighted = highest-HV seed, {len(F_best)} pts)",
        fontsize=11, y=1.02,
    )
    fig.savefig(FIG_OUT, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {FIG_OUT} ({FIG_OUT.stat().st_size/1024:.0f} KB)")
    print(f"  Points: {len(P)} across {len(nonempty)} seeds; "
          f"exemplar seed {best} with {len(F_best)} pts")


if __name__ == "__main__":
    main()
