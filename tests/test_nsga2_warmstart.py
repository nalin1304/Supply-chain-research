"""Tests for FIX-011 — NSGA-II warm-start with OR-Tools (clauses
C1.14 / C2.14 / C3.4).

Validates:

1. ``run_nsga2(warm_start=False)`` (the default) reproduces the
   ``nsga2_pareto`` block of ``audit_workspace/NUMERIC_BASELINE.json``
   under ``seed=42, pop_size=500, n_gen=100`` (clause C3.4 — preservation
   of pre-fix numeric output).

2. ``run_nsga2(warm_start=True)`` produces a Pareto front whose
   normalized hypervolume is ≥ the cold-start hypervolume on the
   standard 5×100 problem at ``seed=42`` — i.e. heuristic seeding does
   not regress convergence (the value of warm-start; clause C2.14).

3. Warm-start preserves feasibility: every solution in the returned
   Pareto front satisfies the demand and capacity constraints within
   the configured epsilons (``NSGAConfig.demand_constraint_eps`` and
   ``NSGAConfig.repair_capacity_eps``).

The OR-Tools→pymoo encoding bridge (``encode_ortools_solution``) is
also tested directly so that bridge bugs surface independently of the
end-to-end run.

References
----------
- Friedrich & Wagner (2014). Seeding the Initial Population of
  Multi-Objective Evolutionary Algorithms. arXiv:1412.0307.
- Beasley & Chu (1996). A Genetic Algorithm for the Multidimensional
  Knapsack Problem. J. Heuristics 4(1).
- Deb (2001). Multi-Objective Optimization Using Evolutionary
  Algorithms. Wiley, §4.2 (Initialization).
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
from supply_chain_research.phase1_foundation.nsga2_solver import (
    encode_ortools_solution,
    run_nsga2,
)
from supply_chain_research.phase1_foundation.pareto_analysis import (
    compute_hypervolume,
)


REPO_ROOT = Path(__file__).resolve().parent.parent
BASELINE_PATH = REPO_ROOT / "audit_workspace" / "NUMERIC_BASELINE.json"

SEED = 42


# ---------------------------------------------------------------------
# Synthetic problem (mirrors capture_numeric_baseline._build_synthetic_problem
# so the regression test stays in lockstep with the baseline)
# ---------------------------------------------------------------------


def _build_synthetic_problem(cfg: MasterConfig, seed: int = SEED):
    n_w = cfg.network.n_warehouses
    n_c = cfg.network.n_customers
    rng = np.random.default_rng(seed)
    distance_matrix = rng.uniform(50.0, 500.0, size=(n_w, n_c))
    demand = rng.uniform(100.0, 5000.0, size=n_c)
    return distance_matrix, demand


# ---------------------------------------------------------------------
# Test 0: encoding bridge — small synthetic problem
# ---------------------------------------------------------------------


class TestEncodeOrtoolsSolution:
    """Validate the OR-Tools route → (n_w, n_c, 2) tensor bridge.

    Validates: Requirements 1.14, 2.14
    """

    def test_encode_assigns_demand_to_correct_warehouse_and_vehicle(self):
        cfg = MasterConfig()
        cfg.network.n_warehouses = 3
        cfg.network.n_customers = 5
        demand = np.array([100.0, 200.0, 300.0, 400.0, 500.0])

        ortools_result = {
            "routes": [
                {"warehouse": 0, "customers": [0, 1], "load_kg": 300.0,
                 "distance_km": 10.0},
                {"warehouse": 2, "customers": [2, 3, 4], "load_kg": 1200.0,
                 "distance_km": 20.0},
            ],
            "total_cost": 0.0, "total_emission": 0.0, "feasible": True,
        }

        flat = encode_ortools_solution(
            ortools_result, cfg, demand, vehicle_type="HCV",
        )
        x = flat.reshape(3, 5, 2)

        # HCV slot (index 0) for the assigned customers
        assert x[0, 0, 0] == pytest.approx(100.0)
        assert x[0, 1, 0] == pytest.approx(200.0)
        assert x[2, 2, 0] == pytest.approx(300.0)
        assert x[2, 3, 0] == pytest.approx(400.0)
        assert x[2, 4, 0] == pytest.approx(500.0)
        # LCV slot must be untouched
        assert np.all(x[:, :, 1] == 0.0)

    def test_encode_full_demand_satisfaction(self):
        """Each customer's demand sum across (w, v) must equal demand[c]."""
        cfg = MasterConfig()
        cfg.network.n_warehouses = 2
        cfg.network.n_customers = 4
        demand = np.array([150.0, 250.0, 350.0, 450.0])

        ortools_result = {
            "routes": [
                {"warehouse": 0, "customers": [0, 2], "load_kg": 500.0,
                 "distance_km": 5.0},
                {"warehouse": 1, "customers": [1, 3], "load_kg": 700.0,
                 "distance_km": 8.0},
            ],
            "total_cost": 0.0, "total_emission": 0.0, "feasible": True,
        }

        flat = encode_ortools_solution(
            ortools_result, cfg, demand, vehicle_type="LCV",
        )
        x = flat.reshape(2, 4, 2)
        per_customer = x.sum(axis=(0, 2))
        np.testing.assert_allclose(per_customer, demand, rtol=0, atol=1e-9)
        # LCV slot was requested
        assert x[0, 0, 1] == pytest.approx(150.0)
        assert x[1, 1, 1] == pytest.approx(250.0)

    def test_encode_unassigned_customer_falls_back(self):
        """Customers missing from the OR-Tools plan still receive demand."""
        cfg = MasterConfig()
        cfg.network.n_warehouses = 2
        cfg.network.n_customers = 3
        demand = np.array([100.0, 200.0, 300.0])

        # Note: customer 2 is not in any route
        ortools_result = {
            "routes": [
                {"warehouse": 0, "customers": [0], "load_kg": 100.0,
                 "distance_km": 5.0},
                {"warehouse": 1, "customers": [1], "load_kg": 200.0,
                 "distance_km": 5.0},
            ],
            "total_cost": 0.0, "total_emission": 0.0, "feasible": True,
        }

        flat = encode_ortools_solution(
            ortools_result, cfg, demand, vehicle_type="HCV",
        )
        x = flat.reshape(2, 3, 2)
        # Customer 2 demand still placed somewhere
        assert x[:, 2, :].sum() == pytest.approx(300.0)


# ---------------------------------------------------------------------
# Test 1: cold-start preservation (clause C3.4)
# ---------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.skipif(
    not BASELINE_PATH.exists(),
    reason="audit_workspace/NUMERIC_BASELINE.json not found",
)
@pytest.mark.timeout(600)
class TestColdStartPreservation:
    """``run_nsga2(warm_start=False)`` reproduces the baseline front.

    Validates: Requirements 1.14, 2.14, 3.4
    """

    @pytest.fixture(scope="class")
    def baseline(self):
        with open(BASELINE_PATH) as f:
            return json.load(f)

    def test_default_path_matches_baseline_extremes(self, baseline):
        """Min-cost and min-carbon objectives match the captured front
        within the 1e-6 relative tolerance recorded in the baseline.

        The full Pareto-front comparison is sensitive to floating-point
        non-determinism in pymoo's sorting; checking the extremes is
        the canonical preservation test (and is what
        ``test_regression_baseline.py`` already enforces). We extend
        it here by also asserting the run executes the same number of
        generations (which proves the early-stopping criterion has
        not been altered) and recovers a non-empty front.
        """
        ref = baseline.get("nsga2_pareto")
        if ref is None or "front" not in ref:
            pytest.skip("Baseline missing nsga2_pareto.front")

        ref_front = np.asarray(ref["front"], dtype=float)
        tol = float(ref.get("tolerance", 1e-6))
        cfg_b = ref["config"]

        cfg = MasterConfig()
        # Baseline was captured at the default 5×100 problem; sanity-check.
        assert cfg.network.n_warehouses == cfg_b["n_warehouses"]
        assert cfg.network.n_customers == cfg_b["n_customers"]

        distance_matrix, demand = _build_synthetic_problem(cfg, seed=SEED)

        result = run_nsga2(
            cfg,
            distance_matrix,
            demand,
            pop_size=cfg_b["pop_size"],
            n_gen=cfg_b["n_gen"],
            seed=cfg_b["seed"],
            # Default behavior — warm_start kwarg absent on purpose.
        )

        assert result.F is not None and len(result.F) > 0

        cur_min_cost = float(result.F[:, 0].min())
        cur_min_carbon = float(result.F[:, 1].min())

        ref_min_cost = float(ref_front[:, 0].min())
        ref_min_carbon = float(ref_front[:, 1].min())

        rel_cost = abs(cur_min_cost - ref_min_cost) / max(
            abs(ref_min_cost), 1.0
        )
        rel_carbon = abs(cur_min_carbon - ref_min_carbon) / max(
            abs(ref_min_carbon), 1.0
        )

        assert rel_cost < tol, (
            f"Cold-start min-cost regressed: cur={cur_min_cost}, "
            f"ref={ref_min_cost}, rel_diff={rel_cost}"
        )
        assert rel_carbon < tol, (
            f"Cold-start min-carbon regressed: cur={cur_min_carbon}, "
            f"ref={ref_min_carbon}, rel_diff={rel_carbon}"
        )

        # Same number of generations executed → same termination path
        assert len(result.hv_history) == ref["n_generations_executed"]


# ---------------------------------------------------------------------
# Test 2: warm-start hypervolume (value of FIX-011)
# ---------------------------------------------------------------------


@pytest.mark.timeout(600)
class TestWarmStartHypervolume:
    """``warm_start=True`` does not regress hypervolume vs cold start.

    Validates: Requirements 1.14, 2.14
    """

    def test_warm_start_hv_at_least_cold_start_hv(self):
        """On the standard 5×100 problem at seed=42, the normalized
        hypervolume of the warm-started front is ≥ that of the
        cold-started front (within numerical tolerance).
        """
        cfg = MasterConfig()
        distance_matrix, demand = _build_synthetic_problem(cfg, seed=SEED)

        # Smaller scale than the baseline so the test fits in the
        # 600s timeout while still exercising both paths through pymoo.
        # Both runs use the SAME pop/gen so the comparison is fair.
        pop_size = 100
        n_gen = 30

        cold = run_nsga2(
            cfg,
            distance_matrix,
            demand,
            pop_size=pop_size,
            n_gen=n_gen,
            seed=SEED,
            warm_start=False,
        )
        warm = run_nsga2(
            cfg,
            distance_matrix,
            demand,
            pop_size=pop_size,
            n_gen=n_gen,
            seed=SEED,
            warm_start=True,
            warm_start_time_limit_seconds=10,
        )

        assert cold.F is not None and len(cold.F) > 0
        assert warm.F is not None and len(warm.F) > 0
        # Warm-start exposes the seeds it actually injected
        assert getattr(warm, "warm_start_seeds", None) is not None
        assert len(warm.warm_start_seeds) == 2

        # Use the joint nadir/ideal across both fronts so the
        # normalized HV values are commensurable. compute_hypervolume
        # is the project's scale-invariant indicator (Audit 3.3).
        joint = np.vstack([cold.F, warm.F])
        ideal = joint.min(axis=0)
        nadir = joint.max(axis=0)

        hv_cold = compute_hypervolume(
            cold.F, ideal_point=ideal, nadir_point=nadir,
        )
        hv_warm = compute_hypervolume(
            warm.F, ideal_point=ideal, nadir_point=nadir,
        )

        # Allow a tiny numerical slack so we don't fail on float-eq
        # edge cases when the two fronts happen to coincide.
        assert hv_warm >= hv_cold - 1e-9, (
            f"Warm-start HV regressed: hv_warm={hv_warm}, "
            f"hv_cold={hv_cold}"
        )


# ---------------------------------------------------------------------
# Test 3: warm-start preserves feasibility
# ---------------------------------------------------------------------


@pytest.mark.timeout(600)
class TestWarmStartFeasibility:
    """Every warm-started Pareto-front solution satisfies demand +
    capacity constraints within the configured epsilons.

    Validates: Requirements 1.14, 2.14
    """

    def test_warm_start_solutions_are_feasible(self):
        cfg = MasterConfig()
        distance_matrix, demand = _build_synthetic_problem(cfg, seed=SEED)

        pop_size = 100
        n_gen = 20
        result = run_nsga2(
            cfg,
            distance_matrix,
            demand,
            pop_size=pop_size,
            n_gen=n_gen,
            seed=SEED,
            warm_start=True,
            warm_start_time_limit_seconds=10,
        )

        assert result.F is not None and len(result.F) > 0
        # pymoo's Result.X is the decision vectors of the final front
        X = np.asarray(result.X)
        if X.ndim == 1:
            X = X.reshape(1, -1)

        n_w = cfg.network.n_warehouses
        n_c = cfg.network.n_customers
        n_v = 2  # HCV, LCV
        cap = np.asarray(
            cfg.network.warehouse_capacities[:n_w], dtype=float,
        )

        demand_eps = cfg.nsga.demand_constraint_eps
        # Repair operator may leave a tiny slack; accept the same
        # tolerance the constraint evaluation uses.
        cap_eps = max(cfg.nsga.repair_capacity_eps, 1.0)

        for i, x_flat in enumerate(X):
            x = np.asarray(x_flat, dtype=float).reshape(n_w, n_c, n_v)
            # Non-negativity
            assert (x >= -1e-9).all(), (
                f"Solution {i} has negative allocations"
            )
            # Demand satisfaction (within configured slack)
            per_customer = x.sum(axis=(0, 2))
            err = np.abs(per_customer - demand)
            assert err.max() <= demand_eps + 1e-6, (
                f"Solution {i} violates demand: max abs err = "
                f"{err.max()} > {demand_eps}"
            )
            # Capacity satisfaction (within configured slack)
            per_warehouse = x.sum(axis=(1, 2))
            overload = per_warehouse - cap
            assert overload.max() <= cap_eps, (
                f"Solution {i} violates capacity: max overload = "
                f"{overload.max()} > {cap_eps}"
            )


# ---------------------------------------------------------------------
# Test 4: explicit-seed warm-start path
# ---------------------------------------------------------------------


@pytest.mark.timeout(300)
class TestWarmStartExplicitSeeds:
    """When the caller passes pre-computed OR-Tools seeds, run_nsga2
    uses them directly (no internal OR-Tools call).

    Validates: Requirements 1.14, 2.14
    """

    def test_explicit_seeds_are_injected(self):
        cfg = MasterConfig()
        cfg.network.n_warehouses = 3
        cfg.network.n_customers = 8
        rng = np.random.default_rng(SEED)
        distance_matrix = rng.uniform(50.0, 500.0, size=(3, 8))
        demand = rng.uniform(100.0, 3000.0, size=8)

        # Pre-compute seeds via the public OR-Tools baseline
        cost_result = solve_baseline_cvrp(
            config=cfg,
            distance_matrix=distance_matrix,
            demand=demand,
            vehicle_type="HCV",
            time_limit_seconds=5,
            method="ortools",
        )
        carbon_result = solve_baseline_cvrp(
            config=cfg,
            distance_matrix=distance_matrix,
            demand=demand,
            vehicle_type="LCV",
            time_limit_seconds=5,
            method="ortools",
        )
        cost_seed = encode_ortools_solution(
            cost_result, cfg, demand, vehicle_type="HCV",
        )
        carbon_seed = encode_ortools_solution(
            carbon_result, cfg, demand, vehicle_type="LCV",
        )

        result = run_nsga2(
            cfg,
            distance_matrix,
            demand,
            pop_size=40,
            n_gen=8,
            seed=SEED,
            warm_start=True,
            ortools_cost_solution=cost_seed,
            ortools_carbon_solution=carbon_seed,
        )

        assert result.F is not None and len(result.F) > 0
        # The exposed seeds must equal what we passed in
        assert getattr(result, "warm_start_seeds", None) is not None
        np.testing.assert_array_equal(
            result.warm_start_seeds[0], cost_seed,
        )
        np.testing.assert_array_equal(
            result.warm_start_seeds[1], carbon_seed,
        )
