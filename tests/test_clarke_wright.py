"""Tests for FIX-014 — Clarke-Wright Savings baseline.

Validates the four contracts named in task 3.4 of the
``supply-chain-research-audit`` spec:

(a) **Preservation (clause C3.7):**
    ``solve_baseline_cvrp(method="ortools")`` at ``seed=42`` matches
    the ``cvrp_baseline`` block of
    ``audit_workspace/NUMERIC_BASELINE.json`` within 1e-6 relative
    tolerance.

(b) **Feasibility:** Clarke-Wright produces a valid solution covering
    every customer with no capacity violation.

(c) **Quality bound:** Clarke-Wright route cost is within 50% of the
    OR-Tools optimum on the same instance — the documented gap for
    the savings heuristic
    (Clarke & Wright 1964; Laporte 1992 OR-Spektrum review).

(d) **Reproducibility:** two ``solve_baseline_cvrp(method="clarke_wright")``
    calls under the same seed return bit-identical objectives and
    routes (the savings algorithm is deterministic given a
    deterministic distance matrix).

Reference
---------
.. [Clarke1964] Clarke, G. & Wright, J. W. (1964). "Scheduling of
   Vehicles from a Central Depot to a Number of Delivery Points."
   Operations Research, 12(4), 568-581.
   DOI: 10.1287/opre.12.4.568
   BibTeX key: ``clarke1964savings`` in
   ``docs/VERIFIED_REFERENCES.bib`` under "FIX-014 — Clarke-Wright Savings
   baseline".
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from supply_chain_research.config import MasterConfig
from supply_chain_research.phase1_foundation.baseline_solver import (
    solve_baseline_cvrp,
)
from supply_chain_research.phase1_foundation.clarke_wright import (
    Route,
    clarke_wright_savings,
    solve_cvrp_clarke_wright,
)


REPO_ROOT = Path(__file__).resolve().parent.parent
BASELINE_PATH = REPO_ROOT / "audit_workspace" / "NUMERIC_BASELINE.json"

SEED = 42


# ---------------------------------------------------------------------
# Shared fixtures (mirror audit_workspace/capture_numeric_baseline.py)
# ---------------------------------------------------------------------


def _build_synthetic_problem(cfg: MasterConfig, seed: int):
    """Build the same synthetic problem used by the baseline capture.

    Parameters
    ----------
    cfg : MasterConfig
        Master config providing ``n_warehouses`` and ``n_customers``.
    seed : int
        Seed for ``numpy.random.default_rng``.

    Returns
    -------
    distance_matrix : np.ndarray, shape (n_w, n_c)
    demand : np.ndarray, shape (n_c,)
    """
    n_w = cfg.network.n_warehouses
    n_c = cfg.network.n_customers
    rng = np.random.default_rng(seed)
    distance_matrix = rng.uniform(50.0, 500.0, size=(n_w, n_c))
    demand = rng.uniform(100.0, 5000.0, size=n_c)
    return distance_matrix, demand


@pytest.fixture(scope="module")
def cfg() -> MasterConfig:
    """Default ``MasterConfig`` instance shared by every test."""
    return MasterConfig()


@pytest.fixture(scope="module")
def synthetic_problem(cfg: MasterConfig):
    """Synthetic 5-warehouse × 100-customer problem at ``seed=42``."""
    return _build_synthetic_problem(cfg, SEED)


@pytest.fixture(scope="module")
def numeric_baseline():
    """Load ``NUMERIC_BASELINE.json`` once for the module."""
    if not BASELINE_PATH.exists():
        pytest.skip(f"NUMERIC_BASELINE.json not found at {BASELINE_PATH}")
    with open(BASELINE_PATH) as f:
        return json.load(f)


# ---------------------------------------------------------------------
# (a) Preservation: OR-Tools default path matches NUMERIC_BASELINE.json
# ---------------------------------------------------------------------


class TestOrtoolsPreservation:
    """Default ``method="ortools"`` reproduces the cvrp_baseline block.

    Validates: Requirements 3.7 (preservation clause C3.7).
    """

    def test_ortools_default_matches_numeric_baseline_within_tolerance(
        self, cfg, synthetic_problem, numeric_baseline
    ):
        """OR-Tools default path matches captured cost / emission."""
        if "cvrp_baseline" not in numeric_baseline:
            pytest.skip("No cvrp_baseline key in NUMERIC_BASELINE.json")

        ref = numeric_baseline["cvrp_baseline"]
        tol = float(ref.get("tolerance", 1.0e-6))  # relative

        distance_matrix, demand = synthetic_problem

        # Default method (no method kwarg) MUST be ortools per C3.7.
        result = solve_baseline_cvrp(
            config=cfg,
            distance_matrix=distance_matrix,
            demand=demand,
            vehicle_type="HCV",
            time_limit_seconds=30,
        )

        assert result["feasible"], "OR-Tools baseline must be feasible"

        cur_cost = float(result["total_cost"])
        cur_emis = float(result["total_emission"])

        ref_cost = float(ref["total_cost_inr"])
        ref_emis = float(ref["total_emission_kgco2"])

        rel_cost = abs(cur_cost - ref_cost) / max(abs(ref_cost), 1.0)
        rel_emis = abs(cur_emis - ref_emis) / max(abs(ref_emis), 1.0)

        assert rel_cost < tol, (
            f"Cost regression: current={cur_cost} vs "
            f"baseline={ref_cost} (rel diff {rel_cost:.2e} > {tol:.2e})"
        )
        assert rel_emis < tol, (
            f"Emission regression: current={cur_emis} vs "
            f"baseline={ref_emis} (rel diff {rel_emis:.2e} > {tol:.2e})"
        )

    def test_explicit_ortools_method_matches_default(
        self, cfg, synthetic_problem
    ):
        """``method="ortools"`` and the default produce identical results."""
        distance_matrix, demand = synthetic_problem

        default_result = solve_baseline_cvrp(
            config=cfg,
            distance_matrix=distance_matrix,
            demand=demand,
            vehicle_type="HCV",
            time_limit_seconds=30,
        )
        explicit_result = solve_baseline_cvrp(
            config=cfg,
            distance_matrix=distance_matrix,
            demand=demand,
            vehicle_type="HCV",
            time_limit_seconds=30,
            method="ortools",
        )

        assert default_result["total_cost"] == pytest.approx(
            explicit_result["total_cost"], rel=1.0e-9
        )
        assert default_result["total_emission"] == pytest.approx(
            explicit_result["total_emission"], rel=1.0e-9
        )


# ---------------------------------------------------------------------
# (b) Clarke-Wright produces a valid solution
# ---------------------------------------------------------------------


class TestClarkeWrightFeasibility:
    """All customers covered, no capacity violation, no double-coverage.

    Validates: Requirements 2.17.
    """

    def test_all_customers_covered(self, cfg, synthetic_problem):
        """Every customer appears in exactly one route."""
        distance_matrix, demand = synthetic_problem
        n_c = cfg.network.n_customers

        result = solve_baseline_cvrp(
            config=cfg,
            distance_matrix=distance_matrix,
            demand=demand,
            vehicle_type="HCV",
            method="clarke_wright",
        )

        assert result["feasible"], "Clarke-Wright must produce a feasible plan"

        covered: list[int] = []
        for route in result["routes"]:
            covered.extend(route["customers"])

        # No customer is visited twice
        assert len(covered) == len(set(covered)), (
            "Clarke-Wright must not double-cover any customer"
        )
        # Every customer is visited
        assert set(covered) == set(range(n_c)), (
            f"Clarke-Wright missed customers: "
            f"{set(range(n_c)) - set(covered)}"
        )

    def test_no_capacity_violation(self, cfg, synthetic_problem):
        """Every route load is within HCV capacity."""
        distance_matrix, demand = synthetic_problem
        capacity = cfg.vehicle.hcv_capacity

        result = solve_baseline_cvrp(
            config=cfg,
            distance_matrix=distance_matrix,
            demand=demand,
            vehicle_type="HCV",
            method="clarke_wright",
        )

        for r_idx, route in enumerate(result["routes"]):
            assert route["load_kg"] <= capacity + 1e-6, (
                f"Route {r_idx} load {route['load_kg']:.2f} exceeds "
                f"capacity {capacity}"
            )

    def test_total_route_load_equals_total_demand(
        self, cfg, synthetic_problem
    ):
        """Sum of route loads equals sum of customer demands."""
        distance_matrix, demand = synthetic_problem

        result = solve_baseline_cvrp(
            config=cfg,
            distance_matrix=distance_matrix,
            demand=demand,
            vehicle_type="HCV",
            method="clarke_wright",
        )

        total_route_load = sum(r["load_kg"] for r in result["routes"])
        total_demand = float(np.sum(demand))
        assert total_route_load == pytest.approx(total_demand, rel=1.0e-9)


# ---------------------------------------------------------------------
# (c) Cost gap vs OR-Tools is within the documented 50% envelope
# ---------------------------------------------------------------------


class TestClarkeWrightCostBound:
    """Clarke-Wright route cost is within 50% of OR-Tools.

    The savings heuristic is documented to land within ~5–25% of the
    optimum on classical CVRP benchmarks; the 50% envelope used here
    is generous to account for the approximate inter-customer distance
    matrix used in this codebase (see ``baseline_solver.py``).

    Validates: Requirements 2.17.
    """

    def test_cw_cost_within_50pct_of_ortools(
        self, cfg, synthetic_problem
    ):
        """``cw_cost <= 1.5 × ortools_cost``."""
        distance_matrix, demand = synthetic_problem

        ortools_result = solve_baseline_cvrp(
            config=cfg,
            distance_matrix=distance_matrix,
            demand=demand,
            vehicle_type="HCV",
            time_limit_seconds=30,
            method="ortools",
        )
        cw_result = solve_baseline_cvrp(
            config=cfg,
            distance_matrix=distance_matrix,
            demand=demand,
            vehicle_type="HCV",
            method="clarke_wright",
        )

        assert ortools_result["feasible"]
        assert cw_result["feasible"]

        ot_cost = float(ortools_result["total_cost"])
        cw_cost = float(cw_result["total_cost"])

        assert cw_cost > 0.0, "Clarke-Wright cost must be positive"
        assert ot_cost > 0.0, "OR-Tools cost must be positive"

        # 50% envelope (cw / ot - 1 ≤ 0.5)
        ratio = cw_cost / ot_cost
        assert ratio <= 1.5, (
            f"Clarke-Wright cost {cw_cost:.2f} INR exceeds 1.5x "
            f"OR-Tools cost {ot_cost:.2f} INR (ratio {ratio:.3f})"
        )


# ---------------------------------------------------------------------
# (d) Reproducibility under fixed seed
# ---------------------------------------------------------------------


class TestClarkeWrightReproducibility:
    """Two runs on the same instance yield bit-identical results.

    The Clarke-Wright savings algorithm is deterministic given a
    deterministic distance matrix and a deterministic tie-breaking
    rule (Python's stable ``list.sort``).

    Validates: Requirements 2.17.
    """

    def test_two_runs_produce_identical_objectives(
        self, cfg, synthetic_problem
    ):
        """Total cost and emission are bit-identical across two runs."""
        distance_matrix, demand = synthetic_problem

        r1 = solve_baseline_cvrp(
            config=cfg,
            distance_matrix=distance_matrix,
            demand=demand,
            vehicle_type="HCV",
            method="clarke_wright",
        )
        r2 = solve_baseline_cvrp(
            config=cfg,
            distance_matrix=distance_matrix,
            demand=demand,
            vehicle_type="HCV",
            method="clarke_wright",
        )

        assert r1["total_cost"] == r2["total_cost"]
        assert r1["total_emission"] == r2["total_emission"]
        assert len(r1["routes"]) == len(r2["routes"])

    def test_two_runs_produce_identical_routes(
        self, cfg, synthetic_problem
    ):
        """Route compositions match across two runs."""
        distance_matrix, demand = synthetic_problem

        r1 = solve_baseline_cvrp(
            config=cfg,
            distance_matrix=distance_matrix,
            demand=demand,
            vehicle_type="HCV",
            method="clarke_wright",
        )
        r2 = solve_baseline_cvrp(
            config=cfg,
            distance_matrix=distance_matrix,
            demand=demand,
            vehicle_type="HCV",
            method="clarke_wright",
        )

        # Compare route sets (order-independent on the route list,
        # order-preserving within each route)
        sets_1 = sorted(tuple(r["customers"]) for r in r1["routes"])
        sets_2 = sorted(tuple(r["customers"]) for r in r2["routes"])
        assert sets_1 == sets_2


# ---------------------------------------------------------------------
# Unit tests for the underlying ``clarke_wright_savings`` primitive
# ---------------------------------------------------------------------


class TestClarkeWrightSavingsPrimitive:
    """Direct exercise of ``clarke_wright_savings`` on small instances.

    Validates: Requirements 2.17.
    """

    def test_savings_metric_two_customers_one_truck(self):
        """Two customers within capacity merge into a single route."""
        # depot at index 0, two customers at indices 1 and 2.
        # Customers are close together so savings > 0.
        # d(0,1) = d(0,2) = 10, d(1,2) = 5. s(1,2) = 10 + 10 - 5 = 15.
        distance_matrix = np.array(
            [[0.0, 10.0, 10.0], [10.0, 0.0, 5.0], [10.0, 5.0, 0.0]]
        )
        demand = np.array([100.0, 100.0])

        routes = clarke_wright_savings(
            distance_matrix=distance_matrix,
            demand=demand,
            vehicle_capacity=300.0,
            depot_index=0,
        )

        assert len(routes) == 1, "Both customers should fit on one route"
        assert sorted(routes[0].customers) == [0, 1]
        assert routes[0].load == pytest.approx(200.0, rel=1.0e-9)

    def test_capacity_constraint_forces_split(self):
        """Customers exceeding capacity stay on separate routes."""
        distance_matrix = np.array(
            [[0.0, 10.0, 10.0], [10.0, 0.0, 5.0], [10.0, 5.0, 0.0]]
        )
        demand = np.array([200.0, 200.0])

        routes = clarke_wright_savings(
            distance_matrix=distance_matrix,
            demand=demand,
            vehicle_capacity=300.0,  # too small for the merged 400 kg
            depot_index=0,
        )

        assert len(routes) == 2, "Capacity must force two routes"
        for r in routes:
            assert r.load <= 300.0

    def test_negative_savings_keeps_routes_separate(self):
        """When d(i,j) > d(0,i) + d(0,j) the merge is not made."""
        # Customers 1 and 2 far apart relative to depot
        distance_matrix = np.array(
            [[0.0, 5.0, 5.0], [5.0, 0.0, 100.0], [5.0, 100.0, 0.0]]
        )
        demand = np.array([100.0, 100.0])

        routes = clarke_wright_savings(
            distance_matrix=distance_matrix,
            demand=demand,
            vehicle_capacity=1000.0,
            depot_index=0,
        )

        # s(1,2) = 5 + 5 - 100 = -90 < 0, so no merge
        assert len(routes) == 2

    def test_route_dataclass_defaults(self):
        """A freshly-constructed Route has empty customers and zeros."""
        r = Route()
        assert r.customers == []
        assert r.load == 0.0
        assert r.distance == 0.0


# ---------------------------------------------------------------------
# Sanity check on ``solve_cvrp_clarke_wright`` direct entry point
# ---------------------------------------------------------------------


class TestSolveCvrpClarkeWrightEntryPoint:
    """``solve_cvrp_clarke_wright`` matches ``solve_baseline_cvrp(method=cw)``.

    Validates: Requirements 2.17.
    """

    def test_direct_and_dispatched_results_agree(
        self, cfg, synthetic_problem
    ):
        """Direct call and dispatched call return identical objectives."""
        distance_matrix, demand = synthetic_problem

        direct = solve_cvrp_clarke_wright(
            config=cfg,
            distance_matrix=distance_matrix,
            demand=demand,
            vehicle_type="HCV",
        )
        dispatched = solve_baseline_cvrp(
            config=cfg,
            distance_matrix=distance_matrix,
            demand=demand,
            vehicle_type="HCV",
            method="clarke_wright",
        )

        assert direct["total_cost"] == dispatched["total_cost"]
        assert direct["total_emission"] == dispatched["total_emission"]
        assert len(direct["routes"]) == len(dispatched["routes"])
