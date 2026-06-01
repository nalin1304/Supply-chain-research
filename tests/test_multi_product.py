"""Tests for the multi-product supply chain solver (FIX-012).

Validates clauses C2.15 / C3.5 of the supply-chain-research-audit
spec:

* When ``MasterConfig.product.n_products == 1`` the multi-product
  solver MUST delegate to the single-product
  :func:`supply_chain_research.phase1_foundation.nsga2_solver.run_nsga2`
  and return a Pareto front bit-for-bit identical to that solver
  (preservation contract C3.5).
* When ``n_products >= 2`` the decision tensor is
  ``x[w, c, v, p]`` of shape
  ``(n_warehouses, n_customers, 2, n_products)`` and per-product
  demand satisfaction plus density-weighted warehouse capacity must
  hold for every solution returned by NSGA-II.

References
----------
.. [Salhi1999] Salhi & Nagy (1999), JORS 50(10):1034--1042.
.. [Coelho2013] Coelho & Laporte (2013), EJOR 245(3):855--865.
.. [Kek2008]    Kek, Cheu & Meng (2008), MCM 47(1--2):140--152.
"""

import numpy as np
import pytest

from supply_chain_research.config import MasterConfig
from supply_chain_research.phase1_foundation.multi_product_solver import (
    MultiProductDemandRepair,
    MultiProductSupplyChainProblem,
    run_multi_product_nsga2,
)
from supply_chain_research.phase1_foundation.nsga2_solver import run_nsga2


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def small_config():
    """Small-scale configuration that runs in <30s under default budget."""
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
def small_demand_1d(small_config):
    rng = np.random.default_rng(42)
    return rng.uniform(200, 2000, size=small_config.network.n_customers)


# ---------------------------------------------------------------------------
# 4(a) Single-product preservation (C3.5)
# ---------------------------------------------------------------------------


class TestSingleProductPreservation:
    """``n_products == 1`` MUST delegate to ``run_nsga2`` bit-for-bit.

    Validates: Requirements 2.15, 3.5
    """

    def test_n_products_one_matches_run_nsga2_bit_for_bit(
        self, small_config, small_distance_matrix, small_demand_1d
    ):
        """run_multi_product_nsga2(n_products=1) ≡ run_nsga2 at seed=42."""
        # Default ProductConfig.n_products is already 1, but assert
        # explicitly so the test fails loudly if the default changes.
        assert small_config.product.n_products == 1

        kwargs = dict(
            distance_matrix=small_distance_matrix,
            demand=small_demand_1d,
            pop_size=20,
            n_gen=5,
            seed=42,
        )

        baseline = run_nsga2(config=small_config, **kwargs)
        candidate = run_multi_product_nsga2(
            config=small_config, **kwargs
        )

        assert baseline.F is not None and candidate.F is not None
        # Bit-for-bit equality (no tolerance) — both calls take the
        # exact same code path.
        np.testing.assert_array_equal(candidate.F, baseline.F)
        np.testing.assert_array_equal(candidate.X, baseline.X)


# ---------------------------------------------------------------------------
# 4(b) Multi-product feasibility — demand satisfaction
# ---------------------------------------------------------------------------


class TestMultiProductFeasibility:
    """Per-(customer, product) demand satisfaction across the Pareto front.

    Validates: Requirements 2.15
    """

    def test_per_product_demand_is_satisfied(
        self, small_config, small_distance_matrix
    ):
        """sum_w sum_v x[w, c, v, p] == demand[c, p] for every (c, p)."""
        n_c = small_config.network.n_customers
        small_config.product.n_products = 3
        small_config.product.product_names = ["Electronics", "FMCG", "Bulk"]
        small_config.product.product_value_per_kg = [500.0, 80.0, 20.0]
        small_config.product.product_density = [1.2, 0.8, 0.4]

        rng = np.random.default_rng(123)
        demand = rng.uniform(50, 600, size=(n_c, 3))

        result = run_multi_product_nsga2(
            config=small_config,
            distance_matrix=small_distance_matrix,
            demand=demand,
            pop_size=20,
            n_gen=5,
            seed=42,
        )

        assert result.F is not None and len(result.F) > 0

        n_w = small_config.network.n_warehouses
        n_v = 2
        n_p = small_config.product.n_products
        eps = small_config.nsga.demand_constraint_eps
        # Allow 1% relative tolerance per (c, p) on top of the
        # absolute slack the repair operator targets.
        rel_tol = 1e-2

        for sol in result.X:
            x = sol.reshape(n_w, n_c, n_v, n_p)
            # sum over (w, v) -> (n_c, n_p)
            cust_sum = x.sum(axis=(0, 2))
            for c in range(n_c):
                for p in range(n_p):
                    diff = abs(cust_sum[c, p] - demand[c, p])
                    assert diff <= max(
                        eps, rel_tol * demand[c, p]
                    ), (
                        f"Demand violation: customer={c}, product={p}, "
                        f"got {cust_sum[c, p]:.4f}, "
                        f"expected {demand[c, p]:.4f}"
                    )


# ---------------------------------------------------------------------------
# 4(c) Multi-product capacity — density-weighted volume
# ---------------------------------------------------------------------------


class TestMultiProductCapacity:
    """Density-weighted warehouse volume must respect ``warehouse_capacities``.

    Validates: Requirements 2.15
    """

    def test_density_weighted_capacity_holds(
        self, small_config, small_distance_matrix
    ):
        """sum_{c, v, p} x[w, c, v, p] / density_p <= warehouse_capacity[w]."""
        n_c = small_config.network.n_customers
        small_config.product.n_products = 3
        small_config.product.product_density = [1.2, 0.8, 0.4]

        rng = np.random.default_rng(7)
        demand = rng.uniform(50, 400, size=(n_c, 3))

        result = run_multi_product_nsga2(
            config=small_config,
            distance_matrix=small_distance_matrix,
            demand=demand,
            pop_size=20,
            n_gen=5,
            seed=42,
        )

        assert result.F is not None and len(result.F) > 0

        n_w = small_config.network.n_warehouses
        n_v = 2
        n_p = small_config.product.n_products
        density = np.asarray(small_config.product.product_density)
        caps = np.asarray(
            small_config.network.warehouse_capacities[:n_w]
        )
        # Allow a 1% relative slack to accommodate float scaling
        # rounding inside the repair operator.
        rel_tol = 1e-2

        for sol in result.X:
            x = sol.reshape(n_w, n_c, n_v, n_p)
            for w in range(n_w):
                weighted = (x[w] / density[None, None, :]).sum()
                limit = caps[w] * (1.0 + rel_tol)
                assert weighted <= limit, (
                    f"Capacity violation at warehouse {w}: "
                    f"weighted_used={weighted:.2f}, "
                    f"capacity={caps[w]:.2f}"
                )


# ---------------------------------------------------------------------------
# 4(d) Pareto-front shape — same bi-objective format as single-product
# ---------------------------------------------------------------------------


class TestParetoFrontShape:
    """``result.F`` is ``(n_solutions, 2)`` for n_products in {1, 3}.

    Validates: Requirements 2.15, 3.5
    """

    def test_single_product_front_has_two_columns(
        self, small_config, small_distance_matrix, small_demand_1d
    ):
        result = run_multi_product_nsga2(
            config=small_config,
            distance_matrix=small_distance_matrix,
            demand=small_demand_1d,
            pop_size=20,
            n_gen=5,
            seed=42,
        )
        assert result.F is not None and result.F.ndim == 2
        assert result.F.shape[1] == 2

    def test_multi_product_front_has_two_columns(
        self, small_config, small_distance_matrix
    ):
        n_c = small_config.network.n_customers
        small_config.product.n_products = 3
        small_config.product.product_density = [1.2, 0.8, 0.4]
        rng = np.random.default_rng(99)
        demand = rng.uniform(50, 600, size=(n_c, 3))

        result = run_multi_product_nsga2(
            config=small_config,
            distance_matrix=small_distance_matrix,
            demand=demand,
            pop_size=20,
            n_gen=5,
            seed=42,
        )
        assert result.F is not None and result.F.ndim == 2
        assert result.F.shape[1] == 2


# ---------------------------------------------------------------------------
# 4(e) Reproducibility under fixed seed
# ---------------------------------------------------------------------------


class TestReproducibility:
    """Two runs with the same seed must return identical fronts.

    Validates: Requirements 2.15
    """

    def test_seed_42_reproducible_multi_product(
        self, small_config, small_distance_matrix
    ):
        n_c = small_config.network.n_customers
        small_config.product.n_products = 3
        small_config.product.product_density = [1.2, 0.8, 0.4]
        rng = np.random.default_rng(2024)
        demand = rng.uniform(50, 600, size=(n_c, 3))

        kwargs = dict(
            config=small_config,
            distance_matrix=small_distance_matrix,
            demand=demand,
            pop_size=20,
            n_gen=5,
            seed=42,
        )
        a = run_multi_product_nsga2(**kwargs)
        b = run_multi_product_nsga2(**kwargs)

        assert a.F is not None and b.F is not None
        np.testing.assert_array_almost_equal(a.F, b.F)
        np.testing.assert_array_almost_equal(a.X, b.X)


# ---------------------------------------------------------------------------
# Problem-class sanity checks (decision-tensor shape, dimensions)
# ---------------------------------------------------------------------------


class TestProblemDimensions:
    """The decision tensor is x[w, c, v, p]."""

    def test_decision_tensor_has_four_axes(
        self, small_config, small_distance_matrix
    ):
        n_c = small_config.network.n_customers
        small_config.product.n_products = 3
        rng = np.random.default_rng(0)
        demand = rng.uniform(100, 500, size=(n_c, 3))

        problem = MultiProductSupplyChainProblem(
            small_config, small_distance_matrix, demand
        )

        n_w = small_config.network.n_warehouses
        n_v = 2
        n_p = 3
        assert problem.n_var == n_w * n_c * n_v * n_p
        assert problem.n_obj == 2
        # Per-(c, p) demand + per-w capacity.
        assert problem.n_ieq_constr == n_c * n_p + n_w


class TestRepairOperator:
    """MultiProductDemandRepair satisfies its post-conditions."""

    def test_repair_satisfies_demand_per_product(
        self, small_config, small_distance_matrix
    ):
        n_w = small_config.network.n_warehouses
        n_c = small_config.network.n_customers
        n_v = 2
        n_p = 3
        small_config.product.n_products = n_p
        small_config.product.product_density = [1.2, 0.8, 0.4]

        rng = np.random.default_rng(11)
        demand = rng.uniform(50, 400, size=(n_c, n_p))

        repair = MultiProductDemandRepair(
            n_warehouses=n_w,
            n_customers=n_c,
            n_vehicle_types=n_v,
            n_products=n_p,
            demand=demand,
            warehouse_capacities=np.asarray(
                small_config.network.warehouse_capacities[:n_w]
            ),
            product_density=np.asarray(
                small_config.product.product_density
            ),
        )

        # Random initial population.
        X = rng.uniform(0, 200, size=(4, n_w * n_c * n_v * n_p))
        repaired = repair._do(None, X.copy())

        rel_tol = 1e-2
        for i in range(len(repaired)):
            x = repaired[i].reshape(n_w, n_c, n_v, n_p)
            assert np.all(x >= 0.0)
            cust_sum = x.sum(axis=(0, 2))  # (n_c, n_p)
            for c in range(n_c):
                for p in range(n_p):
                    if demand[c, p] > 0:
                        rel_diff = abs(
                            cust_sum[c, p] - demand[c, p]
                        ) / demand[c, p]
                        assert rel_diff <= rel_tol
