"""Publication-ready matplotlib style configuration.

Two callable themes:

- :func:`set_publication_style` — tight, journal-grade. Times New
  Roman serif body, slightly thicker axis spines, axis grid below
  data, restrained palette designed to read clearly in greyscale
  print. The default for every figure module in
  ``phase4_synthesis``.
- :func:`apply_modern_palette` — additive helper for figures that
  benefit from a tableau-influenced palette (sequential / divergent
  hues). Returns the chosen palette so callers can colour multiple
  artists consistently.

The palette names map to IBM-design / ColorBrewer-2 colour-blind-
safe sequences so the figures remain interpretable in both colour
and greyscale prints.
"""

from __future__ import annotations

import matplotlib.pyplot as plt
from cycler import cycler

# IBM-design colour-blind-safe sequence
# (ColorBrewer-2 verified, deuteranopia + protanopia + tritanopia safe)
COLOUR_BLIND_SAFE = [
    "#332288",  # indigo
    "#117733",  # teal-green
    "#882255",  # mulberry
    "#DDCC77",  # ochre
    "#88CCEE",  # cyan
    "#CC6677",  # rose
    "#44AA99",  # aqua
    "#999933",  # olive
]

# Sequential single-hue (for ordinal data like seeds)
SEQUENTIAL_VIRIDIS = "viridis"

# Three-method palette used in §5 algorithm-comparison plots
METHOD_PALETTE = {
    "NSGA-II": "#332288",   # indigo (primary method)
    "NSGA-III": "#882255",  # mulberry
    "MOEA/D": "#117733",    # teal-green
    "Random": "#999933",    # olive
    "(R, s, S)": "#CC6677", # rose
    "PPO": "#332288",       # indigo (matches NSGA-II for cohesion)
}


def set_publication_style() -> None:
    """Apply publication-quality matplotlib rcParams.

    Designed for Elsevier ``elsarticle`` / IEEE ``IEEEtran``
    final-submission column widths (single column ≈ 3.5 in,
    full width ≈ 7.0 in). Calls update on ``rcParams`` in place.

    Returns
    -------
    None
        ``matplotlib.pyplot.rcParams`` mutated globally.
    
    Parameters
    ----------
    """
    plt.rcParams.update({
        # Typography — serif body to match journal templates
        "font.family": "serif",
        "font.serif": ["Times New Roman", "Times", "DejaVu Serif"],
        "mathtext.fontset": "stix",
        "font.size": 11,
        "axes.titlesize": 12,
        "axes.titleweight": "bold",
        "axes.labelsize": 11,
        "axes.labelweight": "regular",
        "xtick.labelsize": 10,
        "ytick.labelsize": 10,
        "legend.fontsize": 10,
        "legend.title_fontsize": 10,

        # Figure size and DPI
        "figure.figsize": (7.0, 4.3),  # full-width default; per-fig override
        "figure.dpi": 100,             # screen preview
        "savefig.dpi": 300,            # publication
        "savefig.bbox": "tight",
        "savefig.pad_inches": 0.05,

        # Axes — visible spines on bottom + left only (Tufte-style)
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.spines.left": True,
        "axes.spines.bottom": True,
        "axes.linewidth": 0.8,
        "axes.edgecolor": "#222222",
        "axes.labelcolor": "#222222",
        "axes.titlecolor": "#222222",
        "axes.titlepad": 10,
        "axes.labelpad": 6,

        # Grid — minor, behind the data
        "axes.grid": True,
        "axes.grid.axis": "both",
        "axes.axisbelow": True,
        "grid.color": "#cccccc",
        "grid.alpha": 0.6,
        "grid.linestyle": "-",
        "grid.linewidth": 0.4,

        # Ticks
        "xtick.color": "#444444",
        "ytick.color": "#444444",
        "xtick.direction": "out",
        "ytick.direction": "out",
        "xtick.major.width": 0.8,
        "ytick.major.width": 0.8,
        "xtick.major.size": 3,
        "ytick.major.size": 3,
        "xtick.minor.size": 1.5,
        "ytick.minor.size": 1.5,

        # Lines + markers
        "lines.linewidth": 1.6,
        "lines.markersize": 5,
        "lines.markeredgewidth": 0.8,

        # Colour cycle: colour-blind-safe sequence
        "axes.prop_cycle": cycler(color=COLOUR_BLIND_SAFE),

        # Legend — clean, frameless on white background
        "legend.frameon": True,
        "legend.framealpha": 0.92,
        "legend.edgecolor": "#cccccc",
        "legend.fancybox": False,
        "legend.borderpad": 0.6,
        "legend.borderaxespad": 0.8,
        "legend.handlelength": 1.8,
        "legend.handletextpad": 0.6,
        "legend.columnspacing": 1.4,

        # Boxplot / bar / scatter defaults
        "patch.linewidth": 0.6,
        "patch.edgecolor": "#222222",
        "boxplot.medianprops.color": "#222222",
        "boxplot.medianprops.linewidth": 1.2,
        "boxplot.boxprops.linewidth": 0.8,
        "boxplot.whiskerprops.linewidth": 0.8,
        "boxplot.capprops.linewidth": 0.8,

        # Error-bar caps
        "errorbar.capsize": 3,
    })


def apply_modern_palette() -> list[str]:
    """Return the colour-blind-safe palette tuple.

    Provided as an additive helper for callers that want to colour
    artists explicitly rather than relying on the default cycle.

    Returns
    -------
    list of str
        Hex colour codes in the canonical order used by
        :func:`set_publication_style`.
    
    Parameters
    ----------
    """
    return list(COLOUR_BLIND_SAFE)


def get_method_colour(method: str) -> str:
    """Return the canonical colour for a multi-objective method.

    Parameters
    ----------
    method : str
        One of ``"NSGA-II"``, ``"NSGA-III"``, ``"MOEA/D"``,
        ``"Random"``, ``"(R, s, S)"``, ``"PPO"``.

    Returns
    -------
    str
        Hex colour code; falls back to indigo for unknown methods.
    """
    return METHOD_PALETTE.get(method, "#332288")
