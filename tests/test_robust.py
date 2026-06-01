"""Tests for the robust supply chain solver (FIX-013).

Validates clauses C2.16 / C3.6 of the supply-chain-research-audit
spec:

a. **Preservation (C3.6)** — when
   ``MasterConfig.robust.enabled is False`` (the default)
   :func:`run_robust_nsga2` MUST delegate to
   :func:`supply_chain_research.phase1_foundation.nsga2_solver.run_nsga2`
   bit-for-bit at ``seed=42``.
b. **Robust path runs without errors** when ``enabled=True``.
c. **Mean+std objective** — a higher ``risk_lambda`` (0.9) produces
   a Pareto front whose worst-case scenario cost is lower than at
   ``risk_lambda=0.1``. This is the value-of-robust-optimisation
   property reported by [BertsimasSim2004]_ §3 ("price of
   robustness") and [BenTalNemirovski2002]_ §2.
d. **Reproducibility under fixed seed** — two runs of
   ``run_robust_nsga2(..., seed=42)`` with identical inputs return
   identical Pareto fronts.

References
----------
.. [BenTalNemirovski2002] Ben-Tal, A. & Nemirovski, A. (2002).
   Robust optimization - methodology and applications.
   Mathematical Programming 92(3), 453-480.
.. [BertsimasSim2004] Bertsimas, D. & Sim, M. (2004).
   The Price of Robustness. Operations Research 52(1), 35-53.
.. [MulveyVZ1995] Mulvey, J. M., Vanderbei, R. J. & Zenios, S. A.
   (1995). Robust optimization of large-scale systems.
   Operations Research 43(2), 264-281.
"""

import numpy as np
import pytest

from supply_chain_research.config import MasterConfig
from supply_chain_research.phase1_foundation.nsga2_solver import (
    SupplyChainProblem,
    run_nsga2,
)
from supply_chain_research.phase1_foundation.robust_solver import (
    RobustSupplyChainProblem,
    run_robust_nsga2,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def small_config():
    """Small-scale configuration that runs in a few seconds."""
    config = MasterConfig()
    config.network.n_customers = 8
    config.network.n_warehouses = 3
    config.network.warehouse_capacities = [60000.0, 55000.0, 50000.0]
    return config


@pytest.fixture
def small_distance_matrix(small_config):
    n_w = small_config.network.n_warehouses
    n_c = small_config.network.n_customers
    rng = np.random.default_rng(42)
    return rng.uniform(50, 500, size=(n_w, n_c))


@pytest.fixture
def small_demand(small_config):
    rng = np.random.default_rng(42)
    return rng.uniform(200, 2000, size=small_config.network.n_customers)


# ---------------------------------------------------------------------------
# (a) Preservation — enabled=False matches run_nsga2 bit-for-bit (C3.6)
# ---------------------------------------------------------------------------


class TestPreservation:
    """``run_robust_nsga2(enabled=False)`` ≡ ``run_nsga2`` bit-for-bit.

    Validates: Requirements 2.16, 3.6
    """

    def test_disabled_matches_run_nsga2_bit_for_bit_seed42(
        self, small_config, small_distance_matrix, small_demand
    ):
        """Default ``enabled=False`` MUST reproduce ``run_nsga2`` exactly."""
        # Default RobustConfig.enabled is False; assert explicitly so
        # the test fails loudly if the default is ever flipped.
        assert small_config.robust.enabled is False

        kwargs = dict(
            distance_matrix=small_distance_matrix,
            demand=small_demand,
            pop_size=20,
            n_gen=5,
            seed=42,
        )

        baseline = run_nsga2(config=small_config, **kwargs)
        candidate = run_robust_nsga2(config=small_config, **kwargs)

        assert baseline.F is not None and candidate.F is not None
        # Bit-for-bit equality (no tolerance) — both calls take the
        # exact same code path because run_robust_nsga2 forwards
        # directly to run_nsga2 when enabled=False.
        np.testing.assert_array_equal(candidate.F, baseline.F)
        np.testing.assert_array_equal(candidate.X, baseline.X)


# ---------------------------------------------------------------------------
# (b) Robust path runs without errors when enabled=True
# ---------------------------------------------------------------------------


class TestRobustPathRuns:
    """Robust path executes end-to-end and returns a well-formed front.

    Validates: Requirements 2.16
    """

    def test_enabled_true_runs_to_completion(
        self, small_config, small_distance_matrix, small_demand
    ):
        """``enabled=True`` returns a valid bi-objective Pareto front."""
        small_config.robust.enabled = True
        small_config.robust.n_scenarios = 5
        small_config.robust.demand_noise_sigma = 0.20
        small_config.robust.risk_lambda = 0.5

        result = run_robust_nsga2(
            config=small_config,
            distance_matrix=small_distance_matrix,
            demand=small_demand,
            pop_size=20,
            n_gen=5,
            seed=42,
        )

        assert result.F is not None
        assert result.F.ndim == 2
        assert result.F.shape[1] == 2  # cost + carbon
        assert len(result.F) > 0
        assert np.all(np.isfinite(result.F))
        # Robust mean+lambda*std is non-negative for non-negative
        # cost / carbon.
        assert np.all(result.F >= 0.0)


# ---------------------------------------------------------------------------
# (c) Value of robust optimisation — higher risk_lambda lowers worst-case
# ---------------------------------------------------------------------------


def _evaluate_worst_case_costs_on_scenarios(
    front_X, problem_eval, demand_scenarios
):
    """Evaluate every solution in `front_X` on `demand_scenarios`.

    Returns the per-solution worst-case (max over scenarios) cost
    vector. The carbon objective is computed alongside but only the
    cost worst case is returned because the FIX-013 task names cost as
    the metric of interest.
    """
    n_w = problem_eval.config.network.n_warehouses
    n_c = problem_eval.config.network.n_customers
    n_v = problem_eval.n_vehicle_types

    worst_costs = np.zeros(len(front_X))
    for i, sol in enumerate(front_X):
        x = sol.reshape(n_w, n_c, n_v)
        per_scenario_costs = []
        for s in range(demand_scenarios.shape[0]):
            c_s, _ = problem_eval._evaluate_single_scenario(
                x, demand_scenarios[s]
            )
            per_scenario_costs.append(c_s)
        worst_costs[i] = max(per_scenario_costs)
    return worst_costs


class TestRiskLambdaShrinksWorstCase:
    """Higher ``risk_lambda`` produces lower worst-case scenario cost.

    The robust objective penalises across-scenario variance, so the
    Pareto front at a high ``risk_lambda`` (0.9) should be biased
    toward solutions whose worst-case cost is lower than the front
    obtained at a low ``risk_lambda`` (0.1). This is the
    value-of-robust-optimisation property of [BertsimasSim2004]_
    §3 ("price of robustness").

    Validates: Requirements 2.16
    """

    def test_high_lambda_reduces_worst_case_cost(
        self, small_config, small_distance_matrix, small_demand
    ):
        # Common stochastic settings — only risk_lambda differs.
        small_config.robust.enabled = True
        small_config.robust.n_scenarios = 8
        small_config.robust.demand_noise_sigma = 0.30  # noticeable noise
        small_config.random_seed = 42

        kwargs = dict(
            config=small_config,
            distance_matrix=small_distance_matrix,
            demand=small_demand,
            pop_size=24,
            n_gen=10,
            seed=42,
        )

        # Low risk aversion — close to expected-value formulation.
        small_config.robust.risk_lambda = 0.1
        res_low = run_robust_nsga2(**kwargs)

        # High risk aversion — strongly penalises variance.
        small_config.robust.risk_lambda = 0.9
        res_high = run_robust_nsga2(**kwargs)

        assert res_low.F is not None and res_high.F is not None
        assert len(res_low.X) > 0 and len(res_high.X) > 0

        # Build a single ensemble of demand scenarios and re-evaluate
        # both fronts on the SAME scenarios so the comparison is
        # apples-to-apples (independent of the per-run sampler state
        # that drove the optimisation).
        scenario_eval_problem = RobustSupplyChainProblem(
            small_config,
            small_distance_matrix,
            small_demand,
            scenario_seed=12345,  # decoupled from optimisation seed
        )
        eval_scenarios = scenario_eval_problem.demand_scenarios

        low_worst = _evaluate_worst_case_costs_on_scenarios(
            res_low.X, scenario_eval_problem, eval_scenarios
        )
        high_worst = _evaluate_worst_case_costs_on_scenarios(
            res_high.X, scenario_eval_problem, eval_scenarios
        )

        # The most-conservative (best worst-case-cost) solution on
        # the high-lambda front should not be worse than the
        # most-conservative solution on the low-lambda front. This
        # is the canonical "value of robust optimisation" inequality:
        # increasing risk aversion does not hurt worst-case
        # performance.
        assert high_worst.min() <= low_worst.min() * 1.01, (
            "High risk_lambda should produce a solution whose "
            f"worst-case scenario cost ({high_worst.min():.4f}) "
            "is at most ~1% above the best worst-case cost on the "
            f"low-lambda front ({low_worst.min():.4f}). "
            "Violation suggests the mean+lambda*std objective is not "
            "actually penalising variance across scenarios."
        )


# ---------------------------------------------------------------------------
# (d) Reproducibility under fixed seed
# ---------------------------------------------------------------------------


class TestReproducibility:
    """Two ``seed=42`` runs return identical Pareto fronts.

    Validates: Requirements 2.16
    """

    def test_seed_42_reproducible_robust(
        self, small_config, small_distance_matrix, small_demand
    ):
        small_config.robust.enabled = True
        small_config.robust.n_scenarios = 5
        small_config.robust.demand_noise_sigma = 0.20
        small_config.robust.risk_lambda = 0.5

        kwargs = dict(
            config=small_config,
            distance_matrix=small_distance_matrix,
            demand=small_demand,
            pop_size=20,
            n_gen=5,
            seed=42,
        )
        a = run_robust_nsga2(**kwargs)
        b = run_robust_nsga2(**kwargs)

        assert a.F is not None and b.F is not None
        np.testing.assert_array_almost_equal(a.F, b.F)
        np.testing.assert_array_almost_equal(a.X, b.X)


# ---------------------------------------------------------------------------
# Sanity checks on the LogNormal demand sampler
# ---------------------------------------------------------------------------


class TestLogNormalSampler:
    """The pre-generated demand scenarios follow LogNormal(0, sigma).

    Validates: Requirements 2.16, 3.6
    """

    def test_scenarios_are_strictly_positive(
        self, small_config, small_distance_matrix, small_demand
    ):
        """LogNormal multiplier guarantees positive demand."""
        small_config.robust.enabled = True
        small_config.robust.n_scenarios = 50
        small_config.robust.demand_noise_sigma = 0.20

        problem = RobustSupplyChainProblem(
            small_config, small_distance_matrix, small_demand
        )
        assert np.all(problem.demand_scenarios > 0.0)

    def test_scenario_median_recovers_baseline(
        self, small_config, small_distance_matrix, small_demand
    ):
        """LogNormal(0, sigma) median = 1 → median demand ≈ baseline."""
        small_config.robust.enabled = True
        small_config.robust.n_scenarios = 500  # large for tight median
        small_config.robust.demand_noise_sigma = 0.20

        problem = RobustSupplyChainProblem(
            small_config, small_distance_matrix, small_demand
        )

        # Median across the scenario axis ≈ baseline demand within 8%
        # at 500 scenarios (median estimator variance scales as
        # O(sigma / sqrt(n))).
        median_demand = np.median(problem.demand_scenarios, axis=0)
        rel_err = np.abs(median_demand - small_demand) / small_demand
        assert rel_err.max() < 0.08, (
            f"Scenario median deviates from baseline by "
            f"{rel_err.max():.2%} (expected < 8% at n=500)."
        )

    def test_zero_sigma_recovers_deterministic(
        self, small_config, small_distance_matrix, small_demand
    ):
        """``demand_noise_sigma -> 0`` collapses scenarios to baseline."""
        small_config.robust.enabled = True
        small_config.robust.n_scenarios = 4
        small_config.robust.demand_noise_sigma = 0.0

        problem = RobustSupplyChainProblem(
            small_config, small_distance_matrix, small_demand
        )

        for s in range(problem.n_scenarios):
            np.testing.assert_array_almost_equal(
                problem.demand_scenarios[s], small_demand
            )
