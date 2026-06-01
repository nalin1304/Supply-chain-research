"""Run Clarke-Wright Savings on CVRPLIB Augerat instances (Audit 3.6).

Validates the implementation against published Best-Known Solutions
(BKS) from CVRPLIB. We use the Clarke-Wright Savings algorithm
[Clarke1964] rather than NSGA-II for this benchmark because:

1. CVRPLIB BKS values are reported as a single tour-distance number
   (sum of Euclidean edge lengths including return-to-depot). Clarke-
   Wright returns total tour distance directly in the same units, so
   the gap calculation is unit-clean.
2. NSGA-II in this codebase returns a Pareto front of (cost, carbon)
   points where cost is in INR (route-distance × cost_per_km × n_trips
   × round-trip factor). Converting INR back to raw distance requires
   inverting all those multipliers, which is brittle.
3. Clarke-Wright on Augerat Set A typically achieves a 3-8% gap to BKS
   in the OR literature [Augerat-Belenguer-1995], so this is a well-
   established sanity check for whether the implementation converges
   to a sensible neighbourhood of the optimum.

Reference
---------
.. [Augerat-Belenguer-1995] Augerat, P., Belenguer, J. M., Benavent, E.,
   Corberan, A., Naddef, D. (1995). Computational results with a branch
   and cut code for the capacitated vehicle routing problem. Research
   Report 949-M, Universite Joseph Fourier, Grenoble.
.. [Clarke1964] Clarke, G. & Wright, J. W. (1964). Scheduling of
   Vehicles from a Central Depot to a Number of Delivery Points.
   Operations Research 12(4): 568-581. DOI: 10.1287/opre.12.4.568
"""

import os
import re
import sys
import urllib.request
from pathlib import Path

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from supply_chain_research.phase1_foundation.clarke_wright import (
    clarke_wright_savings,
)

# CVRPLIB hosts a few standard mirrors. We try them in order and fall
# back gracefully if any one is down. As of 2026 the canonical
# vrp.atd-lab.inf.puc-rio.br endpoints have been reorganised and the
# old direct-file URLs no longer resolve, so the github mirror by
# @zhu-he is now the primary source.
CVRPLIB_MIRRORS = [
    "https://raw.githubusercontent.com/zhu-he/cvrp-data/master/A/",
]

# CVRPLIB Augerat Set-A — published BKS values from
# [Augerat-Belenguer-1995] §5 Table 2 and the CVRPLIB website
# (vrp.atd-lab.inf.puc-rio.br).
INSTANCES = [
    {"name": "A-n32-k5",  "bks": 784},
    {"name": "A-n33-k5",  "bks": 661},
    {"name": "A-n33-k6",  "bks": 742},
    {"name": "A-n34-k5",  "bks": 778},
    {"name": "A-n36-k5",  "bks": 799},
    {"name": "A-n37-k5",  "bks": 669},
    {"name": "A-n37-k6",  "bks": 949},
    {"name": "A-n38-k5",  "bks": 730},
    {"name": "A-n39-k5",  "bks": 822},
    {"name": "A-n39-k6",  "bks": 831},
    {"name": "A-n44-k6",  "bks": 937},
    {"name": "A-n45-k6",  "bks": 944},
    {"name": "A-n45-k7",  "bks": 1146},
    {"name": "A-n46-k7",  "bks": 914},
    {"name": "A-n48-k7",  "bks": 1073},
    {"name": "A-n53-k7",  "bks": 1010},
    {"name": "A-n54-k7",  "bks": 1167},
    {"name": "A-n55-k9",  "bks": 1073},
    {"name": "A-n60-k9",  "bks": 1354},
    {"name": "A-n61-k9",  "bks": 1034},
    {"name": "A-n62-k8",  "bks": 1288},
    {"name": "A-n63-k9",  "bks": 1616},
    {"name": "A-n63-k10", "bks": 1314},
    {"name": "A-n64-k9",  "bks": 1401},
    {"name": "A-n65-k9",  "bks": 1174},
    {"name": "A-n69-k9",  "bks": 1159},
    {"name": "A-n80-k10", "bks": 1763},
]

CACHE_DIR = Path("data/external/cvrplib")


def download(name: str, dest: Path, timeout_sec: float = 10.0) -> bool:
    """Fetch a CVRPLIB .vrp file from any working mirror.

    Parameters
    ----------
    name : str
        Instance name without extension, e.g. ``"A-n32-k5"``.
    dest : Path
        Local cache path. Skipped if already present.
    timeout_sec : float, optional
        Per-mirror connect/read timeout in seconds (default 10.0).

    Returns
    -------
    bool
        ``True`` if the file is on disk after the call (whether
        cached or freshly downloaded), ``False`` if every mirror
        failed.
    """
    if dest.exists():
        return True
    dest.parent.mkdir(parents=True, exist_ok=True)
    for mirror in CVRPLIB_MIRRORS:
        url = mirror + name + ".vrp"
        try:
            with urllib.request.urlopen(url, timeout=timeout_sec) as r:
                data = r.read()
            dest.write_bytes(data)
            return True
        except Exception:
            continue
    return False


def parse_vrp(path: Path) -> dict:
    """Parse a TSPLIB-format CVRP instance.

    Parameters
    ----------
    path : Path
        Path to a ``.vrp`` file in standard TSPLIB format (``DIMENSION``,
        ``CAPACITY``, ``NODE_COORD_SECTION``, ``DEMAND_SECTION``,
        ``DEPOT_SECTION``).

    Returns
    -------
    dict with keys ``dimension``, ``capacity``, ``coords``
    ``(n, 2)``, ``demand`` ``(n,)``, ``depot`` (0-indexed).
    """
    text = path.read_text()
    m_dim = re.search(r"DIMENSION\s*:\s*(\d+)", text)
    m_cap = re.search(r"CAPACITY\s*:\s*(\d+)", text)
    dim = int(m_dim.group(1))
    cap = int(m_cap.group(1))

    coords = np.zeros((dim, 2))
    in_coords = False
    in_demand = False
    demand = np.zeros(dim)
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("NODE_COORD_SECTION"):
            in_coords = True
            continue
        if line.startswith("DEMAND_SECTION"):
            in_coords = False
            in_demand = True
            continue
        if line.startswith("DEPOT_SECTION") or line.startswith("EOF"):
            in_demand = False
            continue
        parts = line.split()
        if in_coords and len(parts) >= 3:
            i = int(parts[0]) - 1
            coords[i] = [float(parts[1]), float(parts[2])]
        elif in_demand and len(parts) >= 2:
            i = int(parts[0]) - 1
            demand[i] = float(parts[1])
    return {
        "dimension": dim, "capacity": cap, "coords": coords,
        "demand": demand, "depot": 0,
    }


def solve_with_clarke_wright(parsed: dict) -> float:
    """Solve a CVRPLIB instance with parallel Clarke-Wright Savings.

    Parameters
    ----------
    parsed : dict
        Output of :func:`parse_vrp`.

    Returns
    -------
    float
        Total tour distance summed over all routes (kept in the same
        Euclidean-edge-length units as the CVRPLIB BKS).
    """
    dim = parsed["dimension"]
    coords = parsed["coords"]
    demand_full = parsed["demand"]  # length n_nodes (incl depot at 0)
    capacity = float(parsed["capacity"])

    # Pairwise Euclidean distance matrix on the full node set
    diff = coords[:, None, :] - coords[None, :, :]
    distance_matrix = np.sqrt((diff ** 2).sum(axis=-1))

    # Customer demand only (drop depot at index 0)
    customer_demand = demand_full[1:]

    routes = clarke_wright_savings(
        distance_matrix=distance_matrix,
        demand=customer_demand,
        vehicle_capacity=capacity,
        depot_index=0,
    )

    # Total tour distance is the sum of route distances; clarke-wright
    # already includes the depot-to-first-customer and last-customer-to-
    # depot legs (round-trip).
    total_distance = float(sum(r.distance for r in routes))
    return total_distance


def main() -> None:
    """Run Clarke-Wright on every Augerat instance and write a LaTeX table.

    Skips any instance whose .vrp file fails to download from every
    mirror (the LaTeX output simply omits that row, with a console
    warning).
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    rows = []

    for inst in INSTANCES:
        name = inst["name"]
        bks = float(inst["bks"])
        local = CACHE_DIR / f"{name}.vrp"
        if not download(name, local):
            print(f"SKIPPING {name} (every mirror failed)")
            continue
        parsed = parse_vrp(local)
        ours = solve_with_clarke_wright(parsed)
        gap_pct = (ours - bks) / bks * 100.0 if bks > 0 else float("nan")
        rows.append({
            "name": name, "bks": bks, "ours": ours, "gap_pct": gap_pct,
        })
        print(
            f"{name}: BKS={bks:.0f}, ours={ours:.0f}, gap={gap_pct:+.1f}%"
        )

    if not rows:
        print("\nNo instances completed; LaTeX table not written.")
        return

    # Summary
    gaps = np.array([r["gap_pct"] for r in rows])
    print(
        f"\nSummary across {len(rows)} instances: "
        f"mean gap = {gaps.mean():+.1f}% | "
        f"median = {np.median(gaps):+.1f}% | "
        f"min = {gaps.min():+.1f}% | max = {gaps.max():+.1f}%"
    )

    # Write LaTeX
    out_path = Path("outputs/tables/cvrplib_validation.tex")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    body_rows = "\n".join(
        f"{r['name']} & {r['bks']:.0f} & {r['ours']:.0f} & "
        f"{r['gap_pct']:+.1f}\\% \\\\"
        for r in rows
    )
    summary_row = (
        f"\\textbf{{Mean}} & -- & -- & "
        f"\\textbf{{{gaps.mean():+.1f}\\%}} \\\\"
    )
    tex = (
        "\\begin{table}[htbp]\n"
        "\\centering\n"
        "\\caption{CVRPLIB Augerat Set-A validation. Total tour "
        "distance under the parallel Clarke-Wright Savings "
        "implementation in \\texttt{supply\\_chain\\_research/phase1"
        "\\_foundation/clarke\\_wright.py} versus the published "
        "best-known solution (BKS) from \\citet{Augerat-Belenguer-1995}. "
        "Positive gap means our solution is longer than BKS; the "
        "Clarke-Wright savings heuristic is an upper bound, so "
        "every gap must be non-negative.}\n"
        "\\label{tab:cvrplib_validation}\n"
        "\\begin{tabular}{lccc}\n"
        "\\hline\n"
        "Instance & BKS & Clarke-Wright & Gap \\\\\n"
        "\\hline\n"
        f"{body_rows}\n"
        "\\hline\n"
        f"{summary_row}\n"
        "\\hline\n"
        "\\end{tabular}\n"
        "\\end{table}\n"
    )
    out_path.write_text(tex)
    print(f"\nSaved: {out_path}")


if __name__ == "__main__":
    main()
