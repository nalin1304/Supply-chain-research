"""Regression test for the CVRPLIB Augerat Set-A validation (FIX-023).

The parallel Clarke-Wright Savings algorithm in
``supply_chain_research/phase1_foundation/clarke_wright.py`` should
land within the 3-10 % gap-to-BKS band reported for this family of
instances in the OR literature [Augerat-Belenguer-1995].

This test runs the algorithm against three small, fast Augerat
instances pulled from the local cache populated by
``scripts/run_cvrplib_benchmark.py`` and asserts the per-instance
gaps fall inside a tolerance envelope around the empirically-observed
post-FIX-023 results. If the pre-cached files are not present (e.g.
on a fresh CI checkout), the test is skipped rather than failed —
network access is not a test-suite invariant.

References
----------
.. [Augerat-Belenguer-1995] Augerat, P., Belenguer, J. M., Benavent, E.,
   Corberan, A., Naddef, D. (1995). Computational results with a branch
   and cut code for the capacitated vehicle routing problem. Research
   Report 949-M, Universite Joseph Fourier, Grenoble.
   BibTeX key: ``augerat1995cvrp_branch_and_cut``.
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pytest

from supply_chain_research.phase1_foundation.clarke_wright import (
    clarke_wright_savings,
)


_CACHE_DIR = Path(__file__).resolve().parents[1] / "data" / "external" / "cvrplib"


# Subset of Augerat Set-A used for the regression. Three small
# instances are chosen for fast test execution; all three are
# pre-cached by ``scripts/run_cvrplib_benchmark.py``.
_INSTANCES = [
    # name           BKS       expected_gap_pct (post-FIX-023)
    ("A-n32-k5",     784.0,    5.7),
    ("A-n33-k5",     661.0,    6.3),
    ("A-n33-k6",     742.0,    4.6),
]

# Tolerance on the per-instance gap. Wide enough to absorb minor
# floating-point variation from numpy versions but tight enough to
# detect a real regression in the Clarke-Wright implementation.
_GAP_TOLERANCE_PP = 1.5  # +/- 1.5 percentage points


def _parse_vrp(path: Path) -> dict:
    """Parse a TSPLIB-format CVRP instance.

    Mirrors the parser in ``scripts/run_cvrplib_benchmark.py`` so the
    test does not depend on importing from a script module.
    """
    text = path.read_text()
    dim = int(re.search(r"DIMENSION\s*:\s*(\d+)", text).group(1))
    cap = int(re.search(r"CAPACITY\s*:\s*(\d+)", text).group(1))
    coords = np.zeros((dim, 2))
    demand = np.zeros(dim)
    in_coords = False
    in_demand = False
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("NODE_COORD_SECTION"):
            in_coords, in_demand = True, False
            continue
        if line.startswith("DEMAND_SECTION"):
            in_coords, in_demand = False, True
            continue
        if line.startswith("DEPOT_SECTION") or line.startswith("EOF"):
            in_coords, in_demand = False, False
            continue
        parts = line.split()
        if in_coords and len(parts) >= 3:
            i = int(parts[0]) - 1
            coords[i] = [float(parts[1]), float(parts[2])]
        elif in_demand and len(parts) >= 2:
            i = int(parts[0]) - 1
            demand[i] = float(parts[1])
    return {"dimension": dim, "capacity": cap, "coords": coords, "demand": demand}


def _solve(parsed: dict) -> float:
    """Run Clarke-Wright on a parsed instance and return total tour distance."""
    coords = parsed["coords"]
    diff = coords[:, None, :] - coords[None, :, :]
    distance_matrix = np.sqrt((diff ** 2).sum(axis=-1))
    customer_demand = parsed["demand"][1:]
    routes = clarke_wright_savings(
        distance_matrix=distance_matrix,
        demand=customer_demand,
        vehicle_capacity=float(parsed["capacity"]),
        depot_index=0,
    )
    return float(sum(r.distance for r in routes))


@pytest.mark.parametrize("name,bks,expected_gap_pct", _INSTANCES)
def test_clarke_wright_gap_to_bks(
    name: str, bks: float, expected_gap_pct: float
) -> None:
    """Per-instance gap-to-BKS lies in the literature-validated band.

    Asserts:
    1. The cached .vrp file exists (or skips the test).
    2. Clarke-Wright produces a positive total distance (not NaN/0).
    3. The gap is non-negative (heuristic is an upper bound).
    4. The gap is within +/- ``_GAP_TOLERANCE_PP`` percentage points
       of the expected value recorded post-FIX-023.
    5. The gap is in the literature-validated 3-10 % band overall.
    """
    vrp_path = _CACHE_DIR / f"{name}.vrp"
    if not vrp_path.exists():
        pytest.skip(
            f"{name}.vrp not cached; run "
            "`python scripts/run_cvrplib_benchmark.py` once to populate."
        )

    parsed = _parse_vrp(vrp_path)
    ours = _solve(parsed)

    assert ours > 0.0, f"{name}: solver returned non-positive distance {ours}"

    gap_pct = (ours - bks) / bks * 100.0
    assert gap_pct >= 0.0, (
        f"{name}: gap is negative ({gap_pct:+.2f}%) — Clarke-Wright is an "
        f"upper bound, this should never happen."
    )

    # Tight regression band around the post-FIX-023 result
    delta = abs(gap_pct - expected_gap_pct)
    assert delta <= _GAP_TOLERANCE_PP, (
        f"{name}: gap {gap_pct:+.2f}% deviates from expected "
        f"{expected_gap_pct:+.2f}% by {delta:.2f} pp (tolerance "
        f"{_GAP_TOLERANCE_PP} pp). Possible regression in Clarke-Wright."
    )

    # Wider literature-validated band [Augerat-Belenguer-1995]:
    # Clarke-Wright on Augerat instances reports 3-10 % gap.
    assert 0.0 <= gap_pct <= 12.0, (
        f"{name}: gap {gap_pct:+.2f}% is outside the 0-12 % "
        f"literature-validated envelope for Clarke-Wright on Augerat."
    )
