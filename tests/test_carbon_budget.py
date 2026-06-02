"""Tests for FIX-015 — Carbon-budget variants + green-premium curve.

Bug clauses C1.18 / C2.18 / C3.8 — see
``.kiro/specs/supply-chain-research-audit/bugfix.md``.

Validates:

a. **Preservation (clause C3.8).**
   ``CarbonBudgetConfig.mode == "none"`` makes
   :func:`run_carbon_budget_nsga2` delegate byte-for-byte to
   :func:`run_nsga2`, so the unconstrained Pareto front is reproduced
   bit-for-bit at the same seed.

b. **20% budget enforcement.**
   ``mode == "20pct"`` produces a Pareto front whose maximum carbon
   value is ``<= 0.80 * E_baseline`` (within a small numerical
   tolerance) — i.e. the Bektaş-Laporte (2011) carbon constraint
   bites.

c. **Monotonic tightness.**
   ``mode == "40pct"`` is strictly tighter than ``"20pct"`` — the
   max-carbon at 40 % reduction is ``<=`` the max-carbon at 20 %
   reduction (every solution at 40 % satisfies the 20 % budget).

d. **Green-premium curve shape.**
   :func:`generate_green_premium_curve` returns a list of
   ``(reduction_pct, min_cost_at_budget)`` points covering the
   canonical 0-60 % range; the cost is non-decreasing in the
   reduction percentage (tighter budget → cost can only rise).

e. **Reproducibility.**
   Two calls under the same seed (in any of the three modes) return
   identical Pareto fronts.

References
----------
- Bektaş, T. & Laporte, G. (2011). The Pollution-Routing Problem.
  *Transportation Research Part B* 45(8):1232-1250.
  DOI 10.1016/j.trb.2011.02.004.
- Sweeney, M., Zhang, J., & Klabjan, D. (2017). A Taxonomy and
  Review of Multi-Objective Vehicle Routing Problems.
"""

from __future__ import annotations

import numpy as np
import pytest

from supply_chain_research.config import MasterConfig
from supply_chain_research.phase1_foundation.carbon_budget_solver import (
    CarbonBudgetSupplyChainProblem,
    estimate_baseline_emission,
    generate_green_premium_curve,
    run_carbon_budget_nsga2,
)
from supply_chain_research.phase1_foundation.nsga2_solver import run_nsga2


SEED = 42


# ---------------------------------------------------------------------
# Shared fixtures — small synthetic problem so the suite finishes
# quickly; the scientific assertions are scale-invariant.
# ---------------------------------------------------------------------


@pytest.fixture(scope="module")
def small_config():
    """Small-scale MasterConfig (3 warehouses × 8 customers)."""
    cfg = MasterConfig()
    cfg.network.n_warehouses = 3
    cfg.network.n_customers = 8
    return cfg


@pytest.fixture(scope="module")
def small_problem(small_config):
    """Synthetic distance matrix + demand vector under SEED."""
    rng = np.random.default_rng(SEED)
    n_w = small_config.network.n_warehouses
    n_c = small_config.network.n_customers
    distance_matrix = rng.uniform(50.0, 500.0, size=(n_w, n_c))
    demand = rng.uniform(200.0, 2000.0, size=n_c)
    return distance_matrix, demand


# ---------------------------------------------------------------------
# (a) Preservation contract — clause C3.8
# ---------------------------------------------------------------------


@pytest.mark.timeout(300)
class TestPreservationModeNone:
    """``mode="none"`` delegates to ``run_nsga2`` bit-for-bit.

    Validates: Requirements 1.18, 2.18, 3.8
    """

    def test_mode_none_matches_run_nsga2_bit_for_bit(
        self, small_problem,
    ):
        """run_carbon_budget_nsga2(mode="none") and run_nsga2 produce
        identical Pareto fronts under the same seed.
        """
        cfg_a = MasterConfig()
        cfg_a.network.n_warehouses = 3
        cfg_a.network.n_customers = 8
        cfg_a.carbon_budget.mode = "none"

        cfg_b = MasterConfig()
        cfg_b.network.n_warehouses = 3
        cfg_b.network.n_customers = 8

        distance_matrix, demand = small_problem

        result_constrained = run_carbon_budget_nsga2(
            config=cfg_a,
            distance_matrix=distance_matrix,
            demand=demand,
            pop_size=40,
            n_gen=10,
            seed=SEED,
        )
        result_unconstrained = run_nsga2(
            config=cfg_b,
            distance_matrix=distance_matrix,
            demand=demand,
            pop_size=40,
            n_gen=10,
            seed=SEED,
        )

        assert result_constrained.F is not None
        assert result_unconstrained.F is not None

        # Pareto fronts must be identical (clause C3.8 — bit-for-bit)
        np.testing.assert_array_equal(
            result_constrained.F, result_unconstrained.F,
        )
        np.testing.assert_array_equal(
            np.asarray(result_constrained.X),
            np.asarray(result_unconstrained.X),
        )


# ---------------------------------------------------------------------
# (b) 20% budget enforcement
# ---------------------------------------------------------------------


@pytest.mark.timeout(300)
class TestTwentyPercentBudget:
    """``mode="20pct"`` Pareto front respects the carbon budget.

    Validates: Requirements 1.18, 2.18
    """

    def test_max_carbon_at_20pct_under_budget(
        self, small_config, small_problem,
    ):
        """Every solution in the 20 %-budget front has emission <=
        0.80 * E_baseline (within solver tolerance).
        """
        cfg = MasterConfig()
        cfg.network.n_warehouses = small_config.network.n_warehouses
        cfg.network.n_customers = small_config.network.n_customers
        cfg.carbon_budget.mode = "20pct"

        distance_matrix, demand = small_problem
        baseline = estimate_baseline_emission(cfg, distance_matrix, demand)
        budget = baseline * 0.80

        result = run_carbon_budget_nsga2(
            config=cfg,
            distance_matrix=distance_matrix,
            demand=demand,
            pop_size=60,
            n_gen=30,
            seed=SEED,
        )

        assert result.F is not None and len(result.F) > 0
        # Maximum carbon across the returned (feasible) front.
        # The repair operator may leave a tiny slack; allow 1% tolerance.
        max_carbon = float(np.max(result.F[:, 1]))
        assert max_carbon <= budget * 1.01, (
            f"max carbon {max_carbon} exceeds 20% budget {budget} "
            f"(baseline = {baseline})"
        )


# ---------------------------------------------------------------------
# (c) 40% strictly tighter than 20%
# ---------------------------------------------------------------------


@pytest.mark.timeout(600)
class TestFortyTighterThanTwenty:
    """``mode="40pct"`` is strictly tighter than ``"20pct"``.

    Validates: Requirements 1.18, 2.18
    """

    def test_max_carbon_40pct_le_max_carbon_20pct(
        self, small_config, small_problem,
    ):
        """The maximum carbon emission at 40 % reduction is <= the
        maximum carbon at 20 % reduction (modulo a small relative
        tolerance for stochastic EA noise).
        """
        cfg_20 = MasterConfig()
        cfg_20.network.n_warehouses = small_config.network.n_warehouses
        cfg_20.network.n_customers = small_config.network.n_customers
        cfg_20.carbon_budget.mode = "20pct"

        cfg_40 = MasterConfig()
        cfg_40.network.n_warehouses = small_config.network.n_warehouses
        cfg_40.network.n_customers = small_config.network.n_customers
        cfg_40.carbon_budget.mode = "40pct"

        distance_matrix, demand = small_problem

        result_20 = run_carbon_budget_nsga2(
            config=cfg_20,
            distance_matrix=distance_matrix,
            demand=demand,
            pop_size=60,
            n_gen=30,
            seed=SEED,
        )
        result_40 = run_carbon_budget_nsga2(
            config=cfg_40,
            distance_matrix=distance_matrix,
            demand=demand,
            pop_size=60,
            n_gen=30,
            seed=SEED,
        )

        assert result_20.F is not None and len(result_20.F) > 0
        assert result_40.F is not None and len(result_40.F) > 0

        max_carbon_20 = float(np.max(result_20.F[:, 1]))
        max_carbon_40 = float(np.max(result_40.F[:, 1]))

        # 40% budget is half of the 20% budget's slack, so max carbon
        # at 40% must be <= max carbon at 20% (allow 1% slack for EA noise).
        assert max_carbon_40 <= max_carbon_20 * 1.01, (
            f"40% max-carbon {max_carbon_40} not tighter than 20% "
            f"max-carbon {max_carbon_20}"
        )


# ---------------------------------------------------------------------
# (d) Green-premium curve shape
# ---------------------------------------------------------------------


@pytest.mark.timeout(900)
class TestGreenPremiumCurve:
    """generate_green_premium_curve returns a non-decreasing cost curve.

    Validates: Requirements 1.18, 2.18
    """

    def test_curve_covers_zero_to_sixty_percent(
        self, small_config, small_problem,
    ):
        """Default reduction_levels span 0-60% in 10% steps."""
        cfg = MasterConfig()
        cfg.network.n_warehouses = small_config.network.n_warehouses
        cfg.network.n_customers = small_config.network.n_customers

        distance_matrix, demand = small_problem
        # Use a tiny pop/gen for fast structural test.
        curve = generate_green_premium_curve(
            config=cfg,
            distance_matrix=distance_matrix,
            demand=demand,
            reduction_levels=[0, 30, 60],
            pop_size=20,
            n_gen=5,
            seed=SEED,
        )

        assert isinstance(curve, list)
        assert len(curve) == 3
        # First coord is reduction%, second is min cost
        for r, c in curve:
            assert isinstance(r, float)
            assert isinstance(c, float)
        # Reduction levels are in the expected order
        rs = [r for r, _ in curve]
        assert rs == [0.0, 30.0, 60.0]

    def test_cost_non_decreasing_with_reduction(
        self, small_config, small_problem,
    ):
        """Tighter carbon budgets cannot reduce cost (the canonical
        green premium): cost(0%) <= cost(20%) <= cost(40%) modulo
        a small relative tolerance for EA stochastic noise.
        """
        cfg = MasterConfig()
        cfg.network.n_warehouses = small_config.network.n_warehouses
        cfg.network.n_customers = small_config.network.n_customers

        distance_matrix, demand = small_problem
        curve = generate_green_premium_curve(
            config=cfg,
            distance_matrix=distance_matrix,
            demand=demand,
            reduction_levels=[0, 20, 40],
            pop_size=60,
            n_gen=30,
            seed=SEED,
        )

        costs = [c for _, c in curve]
        # Allow 5% relative slack — the EA at small pop/gen can
        # over-shoot the cost minimum at the unconstrained anchor.
        for i in range(1, len(costs)):
            prev = costs[i - 1]
            cur = costs[i]
            if not np.isfinite(prev) or not np.isfinite(cur):
                continue
            assert cur >= prev * 0.95, (
                f"green-premium curve decreased: cost({curve[i-1][0]}%) = "
                f"{prev} -> cost({curve[i][0]}%) = {cur}"
            )


# ---------------------------------------------------------------------
# (e) Reproducibility under fixed seed
# ---------------------------------------------------------------------


@pytest.mark.timeout(300)
class TestReproducibility:
    """Two runs under the same seed return the same Pareto front.

    Validates: Requirements 1.18, 2.18
    """

    def test_mode_none_reproducible(self, small_problem):
        """``mode="none"`` is deterministic under a fixed seed."""
        cfg = MasterConfig()
        cfg.network.n_warehouses = 3
        cfg.network.n_customers = 8
        cfg.carbon_budget.mode = "none"
        distance_matrix, demand = small_problem

        a = run_carbon_budget_nsga2(
            config=cfg,
            distance_matrix=distance_matrix,
            demand=demand,
            pop_size=30,
            n_gen=8,
            seed=SEED,
        )
        b = run_carbon_budget_nsga2(
            config=cfg,
            distance_matrix=distance_matrix,
            demand=demand,
            pop_size=30,
            n_gen=8,
            seed=SEED,
        )

        np.testing.assert_array_equal(a.F, b.F)

    def test_mode_20pct_reproducible(self, small_problem):
        """``mode="20pct"`` is deterministic under a fixed seed."""
        cfg = MasterConfig()
        cfg.network.n_warehouses = 3
        cfg.network.n_customers = 8
        cfg.carbon_budget.mode = "20pct"
        distance_matrix, demand = small_problem

        a = run_carbon_budget_nsga2(
            config=cfg,
            distance_matrix=distance_matrix,
            demand=demand,
            pop_size=30,
            n_gen=8,
            seed=SEED,
        )
        b = run_carbon_budget_nsga2(
            config=cfg,
            distance_matrix=distance_matrix,
            demand=demand,
            pop_size=30,
            n_gen=8,
            seed=SEED,
        )

        np.testing.assert_array_equal(a.F, b.F)


# ---------------------------------------------------------------------
# Auxiliary: baseline-emission estimator is deterministic
# ---------------------------------------------------------------------


class TestEstimateBaselineEmission:
    """estimate_baseline_emission is deterministic and positive.

    Validates: Requirements 1.18, 2.18
    """

    def test_baseline_emission_positive_and_deterministic(
        self, small_config, small_problem,
    ):
        cfg = MasterConfig()
        cfg.network.n_warehouses = small_config.network.n_warehouses
        cfg.network.n_customers = small_config.network.n_customers
        distance_matrix, demand = small_problem

        a = estimate_baseline_emission(cfg, distance_matrix, demand)
        b = estimate_baseline_emission(cfg, distance_matrix, demand)
        assert a > 0
        assert a == b


class TestCarbonBudgetProblemConstraintCount:
    """CarbonBudgetSupplyChainProblem reports n_c + n_w + 1 constraints.

    Validates: Requirements 1.18, 2.18
    """

    def test_constraint_count(self, small_config, small_problem):
        cfg = MasterConfig()
        cfg.network.n_warehouses = small_config.network.n_warehouses
        cfg.network.n_customers = small_config.network.n_customers
        distance_matrix, demand = small_problem

        baseline = estimate_baseline_emission(cfg, distance_matrix, demand)
        problem = CarbonBudgetSupplyChainProblem(
            cfg, distance_matrix, demand, baseline * 0.8,
        )
        n_w = cfg.network.n_warehouses
        n_c = cfg.network.n_customers
        assert problem.n_obj == 2
        assert problem.n_ieq_constr == n_c + n_w + 1
