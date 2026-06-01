"""Tests for the NSGA-III solver.

Validates the 3-objective supply chain optimization using NSGA-III
with Das-Dennis reference directions.
"""

import numpy as np
import pytest

from supply_chain_research.config import MasterConfig
from supply_chain_research.phase1_foundation.nsga3_solver import (
    DemandRepair3Obj,
    SupplyChainProblem3Obj,
    run_nsga3,
)


@pytest.fixture
def small_config():
    """Create small-scale configuration for testing."""
    config = MasterConfig()
    config.network.n_customers = 10
    config.network.n_warehouses = 3
    config.network.warehouse_capacities = [60000.0, 55000.0, 50000.0]
    return config


@pytest.fixture
def small_distance_matrix(small_config):
    """Create a small distance matrix for testing."""
    n_w = small_config.network.n_warehouses
    n_c = small_config.network.n_customers
    rng = np.random.default_rng(42)
    return rng.uniform(50, 500, size=(n_w, n_c))


@pytest.fixture
def small_duration_matrix(small_config):
    """Create a small duration matrix (minutes) for testing."""
    n_w = small_config.network.n_warehouses
    n_c = small_config.network.n_customers
    rng = np.random.default_rng(43)
    # Travel times: 60-600 minutes (1-10 hours)
    return rng.uniform(60, 600, size=(n_w, n_c))


@pytest.fixture
def small_demand(small_config):
    """Create small demand array for testing."""
    rng = np.random.default_rng(42)
    return rng.uniform(200, 2000, size=small_config.network.n_customers)


class TestSupplyChainProblem3Obj:
    """Test the 3-objective optimization problem definition."""

    def test_problem_has_3_objectives(
        self, small_config, small_distance_matrix, small_demand,
        small_duration_matrix
    ):
        """Problem should have 3 objectives."""
        problem = SupplyChainProblem3Obj(
            small_config, small_distance_matrix, small_demand,
            small_duration_matrix
        )
        assert problem.n_obj == 3

    def test_problem_dimensions(
        self, small_config, small_distance_matrix, small_demand,
        small_duration_matrix
    ):
        """Problem should have correct dimensions."""
        problem = SupplyChainProblem3Obj(
            small_config, small_distance_matrix, small_demand,
            small_duration_matrix
        )
        n_w = small_config.network.n_warehouses
        n_c = small_config.network.n_customers
        n_v = 2  # HCV, LCV

        assert problem.n_var == n_w * n_c * n_v
        assert problem.n_obj == 3
        assert problem.n_ieq_constr == n_c + n_w

    def test_evaluate_returns_3_objectives(
        self, small_config, small_distance_matrix, small_demand,
        small_duration_matrix
    ):
        """Evaluation should return F with shape (pop_size, 3)."""
        n_w = small_config.network.n_warehouses
        n_c = small_config.network.n_customers
        n_v = 2
        problem = SupplyChainProblem3Obj(
            small_config, small_distance_matrix, small_demand,
            small_duration_matrix
        )

        # Create a feasible solution
        X = np.zeros((1, n_w * n_c * n_v))
        x = X[0].reshape(n_w, n_c, n_v)
        for c in range(n_c):
            x[0, c, 0] = small_demand[c]
        X[0] = x.flatten()

        out = {}
        problem._evaluate(X, out)

        assert out["F"].shape == (1, 3)
        assert out["F"][0, 0] > 0  # Cost > 0
        assert out["F"][0, 1] > 0  # Emission > 0
        assert out["F"][0, 2] > 0  # Delivery time > 0


class TestNSGA3Run:
    """Test NSGA-III optimization execution."""

    def test_returns_3_objective_pareto_front(
        self, small_config, small_distance_matrix, small_demand,
        small_duration_matrix
    ):
        """run_nsga3 should return a result with F.shape[1] == 3."""
        result = run_nsga3(
            small_config,
            small_distance_matrix,
            small_demand,
            small_duration_matrix,
            pop_size=50,
            n_gen=10,
            n_partitions=4,
            seed=42,
        )

        assert result is not None
        assert result.F is not None
        assert result.F.shape[1] == 3

    def test_all_objectives_non_negative(
        self, small_config, small_distance_matrix, small_demand,
        small_duration_matrix
    ):
        """All objective values should be non-negative."""
        result = run_nsga3(
            small_config,
            small_distance_matrix,
            small_demand,
            small_duration_matrix,
            pop_size=50,
            n_gen=10,
            n_partitions=4,
            seed=42,
        )

        assert result.F is not None
        assert len(result.F) > 0
        assert np.all(result.F >= 0)

    def test_reproducibility_under_fixed_seed(
        self, small_config, small_distance_matrix, small_demand,
        small_duration_matrix
    ):
        """Results should be reproducible under the same seed."""
        kwargs = dict(
            config=small_config,
            distance_matrix=small_distance_matrix,
            demand=small_demand,
            duration_matrix=small_duration_matrix,
            pop_size=50,
            n_gen=10,
            n_partitions=4,
            seed=42,
        )

        result1 = run_nsga3(**kwargs)
        result2 = run_nsga3(**kwargs)

        np.testing.assert_array_almost_equal(result1.F, result2.F)

    def test_pareto_non_dominance(
        self, small_config, small_distance_matrix, small_demand,
        small_duration_matrix
    ):
        """No solution in the Pareto front should dominate another."""
        result = run_nsga3(
            small_config,
            small_distance_matrix,
            small_demand,
            small_duration_matrix,
            pop_size=50,
            n_gen=10,
            n_partitions=4,
            seed=42,
        )

        F = result.F
        n = len(F)
        for i in range(n):
            for j in range(n):
                if i == j:
                    continue
                # Solution i should NOT dominate solution j
                # (domination: all objectives <=, at least one <)
                all_leq = np.all(F[i] <= F[j])
                any_lt = np.any(F[i] < F[j])
                dominates = all_leq and any_lt
                assert not dominates, (
                    f"Solution {i} dominates solution {j}: "
                    f"F[{i}]={F[i]}, F[{j}]={F[j]}"
                )
