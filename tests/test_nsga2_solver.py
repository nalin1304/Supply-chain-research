"""Property-based and preservation tests for the NSGA-II solver.

This module covers task 4.3 of the supply-chain-research-audit spec.
It is deliberately separate from ``tests/test_nsga2.py`` (legacy unit
tests) and ``tests/test_nsga2_warmstart.py`` (FIX-011 warm-start
regression) so the four named ``Test*`` classes required by the task
land in one auditable file. Style and hypothesis configuration mirror
``tests/test_emission_model.py`` (task 4.1).

The four classes encode preservation contracts from
``.kiro/specs/supply-chain-research-audit/bugfix.md``:

* ``TestConstraintSatisfaction``  -- Pareto-front feasibility
  (capacity + demand within configured slack).
* ``TestParetoNonDominance``      -- non-domination of the returned
  front [Deb-2002 §III.A].
* ``TestRepairOperator``          -- ``MarginalTradeoffRepair`` is
  idempotent: ``repair(repair(x)) == repair(x)``.
* ``TestWarmStart``               -- bit-equivalence to the
  ``nsga2_pareto`` block of
  ``audit_workspace/NUMERIC_BASELINE.json`` under
  ``seed=42, warm_start=False`` [bugfix.md C3.2 / C3.4].

References
----------
.. [Deb-2002] Deb, K., Pratap, A., Agarwal, S. & Meyarivan, T.
   (2002). A fast and elitist multiobjective genetic algorithm:
   NSGA-II. IEEE Trans. Evol. Comput. 6(2):182-197.
   doi:10.1109/4235.996017.
"""
# [Deb-2002 §III] anchor citation; warm-start preservation per
# [bugfix.md C3.2 / C3.4]; mirrors hypothesis cadence in
# tests/test_emission_model.py (task 4.1).

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from hypothesis import HealthCheck, given, settings, strategies as st

from supply_chain_research.config import MasterConfig  # [config FIX-002]
from supply_chain_research.phase1_foundation.nsga2_solver import (  # [FIX-011/012/013]
    DemandRepair,
    MarginalTradeoffRepair,
    SupplyChainProblem,
    run_nsga2,
)


# Repository-relative path to the captured baseline produced by
# ``audit_workspace/capture_numeric_baseline.py`` (task 0.4).
_REPO_ROOT = Path(__file__).resolve().parent.parent  # [tests/.. → repo root]
_BASELINE_PATH = _REPO_ROOT / "audit_workspace" / "NUMERIC_BASELINE.json"

# Fixed seed mandated by clauses C3.2 and C3.4 — used across every
# preservation-flavoured test in this file.
_SEED = 42  # [bugfix.md C3.2 / C3.4]


# ---------------------------------------------------------------------
# Shared problem builder — mirrors capture_numeric_baseline._build_synthetic_problem
# so the regression test stays in lockstep with the captured baseline.
# ---------------------------------------------------------------------


def _build_synthetic_problem(cfg: MasterConfig, seed: int = _SEED):
    """Construct the deterministic synthetic instance used by the baseline.

    Mirrors ``audit_workspace/capture_numeric_baseline._build_synthetic_problem``
    byte-for-byte so the warm-start preservation test can recover the
    captured Pareto front under ``seed=42``.

    Parameters
    ----------
    cfg : MasterConfig
        Active master configuration. ``cfg.network.n_warehouses`` and
        ``cfg.network.n_customers`` set the matrix shape.
    seed : int, optional
        Seed for ``numpy.random.default_rng``. Defaults to ``42``
        (the project-wide preservation seed).

    Returns
    -------
    distance_matrix : numpy.ndarray, shape (n_warehouses, n_customers)
        Per-pair distances drawn from ``U[50, 500]`` km.
    demand : numpy.ndarray, shape (n_customers,)
        Per-customer demand drawn from ``U[100, 5000]`` kg.
    """
    n_w = cfg.network.n_warehouses  # [config FIX-002 — network sizing]
    n_c = cfg.network.n_customers  # [config FIX-002 — network sizing]
    rng = np.random.default_rng(seed)  # [seed=42 → bugfix.md C3.2]
    distance_matrix = rng.uniform(50.0, 500.0, size=(n_w, n_c))
    demand = rng.uniform(100.0, 5000.0, size=n_c)
    return distance_matrix, demand


def _build_small_instance(n_w: int, n_c: int, seed: int):
    """Build a tiny reproducible (distance, demand) pair for fast tests.

    Used by the property-based and idempotence tests where end-to-end
    NSGA-II runtime must stay under a couple of seconds per example.

    Parameters
    ----------
    n_w, n_c : int
        Warehouse and customer counts.
    seed : int
        Seed for the local ``numpy.random.default_rng`` instance.

    Returns
    -------
    distance_matrix : numpy.ndarray, shape (n_w, n_c)
    demand : numpy.ndarray, shape (n_c,)
    """
    rng = np.random.default_rng(seed)  # [hypothesis-driven seed]
    distance_matrix = rng.uniform(50.0, 500.0, size=(n_w, n_c))
    demand = rng.uniform(200.0, 2000.0, size=n_c)
    return distance_matrix, demand


def _make_small_config(n_w: int = 3, n_c: int = 8) -> MasterConfig:
    """Create a MasterConfig clone resized for fast property tests.

    Parameters
    ----------
    n_w : int, optional
        Warehouse count (default 3).
    n_c : int, optional
        Customer count (default 8).

    Returns
    -------
    MasterConfig
        A config whose ``network`` section is downsized; everything
        else (vehicle, NSGA, solver-internal epsilons) is left at the
        production defaults so we exercise the same numerical paths.
    """
    cfg = MasterConfig()  # [config FIX-002 — Pydantic central config]
    cfg.network.n_warehouses = n_w  # [shrink for hypothesis budget]
    cfg.network.n_customers = n_c
    return cfg


# =====================================================================
# 1. TestConstraintSatisfaction — feasibility of every front solution
# =====================================================================


class TestConstraintSatisfaction:
    """Every Pareto-front solution satisfies capacity + demand constraints.

    The ``MarginalTradeoffRepair`` operator [Audit 1.2] guarantees
    feasibility within ``NSGAConfig.demand_constraint_eps`` and
    ``NSGAConfig.repair_capacity_eps`` for every individual it
    processes. The Pareto front is the non-dominated subset of the
    final population, so the same guarantee must hold there.

    Validates: Requirements 1.12, 2.12 [bugfix.md C1.12 / C2.12]
    """

    @pytest.fixture(scope="class")
    def cfg(self):
        """Small-scale ``MasterConfig`` for tractable NSGA-II runs."""
        return _make_small_config(n_w=3, n_c=8)  # [small instance for CI budget]

    @pytest.fixture(scope="class")
    def problem_data(self, cfg):
        """Reproducible (distance_matrix, demand) at ``seed=_SEED``."""
        return _build_small_instance(  # [seed=42 reproducibility]
            cfg.network.n_warehouses, cfg.network.n_customers, _SEED,
        )

    def test_every_front_solution_is_feasible(self, cfg, problem_data):
        """Demand and capacity constraints hold for every front member.

        Runs NSGA-II at a small population/generation budget so the
        test fits inside the standard pytest timeout. The post-run
        feasibility check uses the SAME slacks the constraint
        evaluator uses inside ``SupplyChainProblem._evaluate``.

        Validates: Requirements 1.12, 2.12 [bugfix.md C1.12 / C2.12]
        """
        distance_matrix, demand = problem_data  # [_SEED=42]
        result = run_nsga2(  # [warm_start=False → cold-start path]
            cfg,
            distance_matrix,
            demand,
            pop_size=30,  # [small for CI]
            n_gen=8,  # [small for CI]
            seed=_SEED,
        )
        assert result.F is not None and len(result.F) > 0  # [non-empty front]

        X = np.atleast_2d(np.asarray(result.X))  # [(n_front, n_var)]
        n_w = cfg.network.n_warehouses
        n_c = cfg.network.n_customers
        n_v = 2  # [HCV + LCV vehicle slots]

        capacities = np.asarray(  # [per-warehouse cap, kg]
            cfg.network.warehouse_capacities[:n_w], dtype=float,
        )
        demand_eps = cfg.nsga.demand_constraint_eps  # [config FIX-002 default 1e-3]
        cap_eps = max(  # [match SupplyChainProblem._evaluate slack]
            cfg.nsga.repair_capacity_eps, 1.0,
        )

        for i, x_flat in enumerate(X):
            x = np.asarray(x_flat, dtype=float).reshape(n_w, n_c, n_v)
            assert (x >= -1e-9).all(), (  # [non-negativity from repair]
                f"Solution {i} contains a negative allocation"
            )
            per_customer = x.sum(axis=(0, 2))  # [demand satisfaction sum]
            assert np.max(np.abs(per_customer - demand)) <= demand_eps + 1e-6, (
                f"Solution {i} violates demand within slack {demand_eps}"
            )
            per_warehouse = x.sum(axis=(1, 2))  # [warehouse load sum]
            assert (per_warehouse - capacities).max() <= cap_eps, (
                f"Solution {i} overloads a warehouse beyond slack {cap_eps}"
            )

    @given(  # [hypothesis on seed only — instance varies, NSGA budget fixed]
        seed=st.integers(min_value=0, max_value=2**31 - 1),
    )
    @settings(  # [match tests/test_emission_model.py cadence]
        max_examples=8,
        deadline=None,
        suppress_health_check=[
            HealthCheck.function_scoped_fixture,
            HealthCheck.too_slow,
        ],
    )
    def test_property_feasibility_under_random_seeds(self, seed):
        """For any seed, the returned Pareto front is feasible.

        Property: ``forall seed in N. Pareto(NSGA-II(seed)) subseteq Feasible``.
        Drives ``run_nsga2`` with a varying numpy seed but fixed
        problem dimensions so each example runs in <2 s.

        Validates: Requirements 1.12, 2.12 [bugfix.md C1.12 / C2.12]
        """
        cfg = _make_small_config(n_w=3, n_c=6)  # [tiny instance for hypothesis]
        distance_matrix, demand = _build_small_instance(3, 6, seed)
        result = run_nsga2(
            cfg,
            distance_matrix,
            demand,
            pop_size=20,  # [hypothesis budget]
            n_gen=4,  # [hypothesis budget]
            seed=seed,  # [property under arbitrary seed]
        )
        assert result.F is not None and len(result.F) > 0

        X = np.atleast_2d(np.asarray(result.X))  # [decision vectors]
        n_w, n_c, n_v = 3, 6, 2  # [matches _make_small_config]
        capacities = np.asarray(
            cfg.network.warehouse_capacities[:n_w], dtype=float,
        )
        demand_eps = cfg.nsga.demand_constraint_eps  # [config FIX-002 slack]
        cap_eps = max(cfg.nsga.repair_capacity_eps, 1.0)  # [match _evaluate]
        for x_flat in X:
            x = np.asarray(x_flat, dtype=float).reshape(n_w, n_c, n_v)
            per_customer = x.sum(axis=(0, 2))
            per_warehouse = x.sum(axis=(1, 2))
            assert (x >= -1e-9).all()  # [non-negativity invariant]
            assert np.max(np.abs(per_customer - demand)) <= demand_eps + 1e-6
            assert (per_warehouse - capacities).max() <= cap_eps


# =====================================================================
# 2. TestParetoNonDominance — front contains no dominated solution
# =====================================================================


def _dominates(a: np.ndarray, b: np.ndarray) -> bool:
    """Return True iff ``a`` dominates ``b`` in the minimisation sense.

    ``a`` dominates ``b`` when ``a_k <= b_k`` for every objective
    ``k`` and ``a_k < b_k`` for at least one ``k``
    [Deb-2002 §III.A, Definition 1].

    Parameters
    ----------
    a, b : numpy.ndarray
        Objective vectors of identical shape (n_obj,).

    Returns
    -------
    bool
        ``True`` if ``a`` Pareto-dominates ``b``.
    """
    return bool(np.all(a <= b) and np.any(a < b))  # [Deb-2002 §III.A]


class TestParetoNonDominance:
    """No solution in the returned front dominates any other.

    By construction NSGA-II returns the first non-dominated rank
    [Deb-2002 §III.A]. We verify this empirically on the
    post-optimisation result so any future refactor that breaks the
    sorting invariant is caught here.

    Validates: Requirements 1.12, 2.12 [bugfix.md C1.12 / C2.12]
    """

    @pytest.fixture(scope="class")
    def cfg(self):
        """Small-scale config for fast NSGA-II runs."""
        return _make_small_config(n_w=3, n_c=8)  # [shared with class above]

    @pytest.fixture(scope="class")
    def front(self, cfg):
        """Run NSGA-II once and reuse the resulting front across tests."""
        distance_matrix, demand = _build_small_instance(3, 8, _SEED)
        result = run_nsga2(  # [seed=42 → cold-start preservation path]
            cfg,
            distance_matrix,
            demand,
            pop_size=40,  # [enough mass for non-trivial front]
            n_gen=10,  # [keeps wall time bounded]
            seed=_SEED,
        )
        assert result.F is not None and len(result.F) > 0
        return np.asarray(result.F, dtype=float)

    def test_front_is_non_dominated(self, front):
        """No pair (i, j) in the returned front has ``F_i`` dominating ``F_j``.

        Validates: Requirements 1.12, 2.12 [bugfix.md C1.12 / C2.12]
        """
        n = len(front)
        for i in range(n):
            for j in range(n):
                if i == j:
                    continue
                assert not _dominates(front[i], front[j]), (  # [Deb-2002 §III.A]
                    f"Solution {i}={front[i]} dominates {j}={front[j]} "
                    f"-- the returned front is not non-dominated."
                )

    def test_front_objectives_finite_and_non_negative(self, front):
        """Both objectives are finite and non-negative on the front.

        Cost (INR) and carbon (kg CO2) are physical quantities and must
        be ``>= 0``. Infeasible solutions should not survive into the
        first non-dominated rank.

        Validates: Requirements 1.12, 2.12 [bugfix.md C1.12 / C2.12]
        """
        assert np.all(np.isfinite(front)), "front contains nan/inf"  # [sanity]
        assert np.all(front >= 0.0), "front contains negative objective"

    @given(  # [hypothesis: vary seed, check non-domination invariant]
        seed=st.integers(min_value=0, max_value=2**31 - 1),
    )
    @settings(
        max_examples=8,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_property_non_domination_under_random_seeds(self, seed):
        """Property: front is always non-dominated regardless of seed.

        Validates: Requirements 1.12, 2.12 [bugfix.md C1.12 / C2.12]
        """
        cfg = _make_small_config(n_w=3, n_c=6)  # [tiny instance]
        distance_matrix, demand = _build_small_instance(3, 6, seed)
        result = run_nsga2(
            cfg, distance_matrix, demand,
            pop_size=20, n_gen=4, seed=seed,  # [hypothesis budget]
        )
        F = np.asarray(result.F, dtype=float)
        assert F.size > 0  # [non-empty front]
        for i in range(len(F)):
            for j in range(len(F)):
                if i == j:
                    continue
                assert not _dominates(F[i], F[j])  # [Deb-2002 §III.A]


# =====================================================================
# 3. TestRepairOperator — idempotence: repair(repair(x)) == repair(x)
# =====================================================================


def _make_repair_operator(cfg: MasterConfig, demand: np.ndarray,
                          distance_matrix: np.ndarray):
    """Construct a ``MarginalTradeoffRepair`` matching ``run_nsga2``.

    Mirrors the operator construction inside ``run_nsga2`` so the
    idempotence test exercises the exact same instance used by the
    optimiser.

    Parameters
    ----------
    cfg : MasterConfig
        Active master configuration providing vehicle parameters.
    demand : numpy.ndarray, shape (n_customers,)
    distance_matrix : numpy.ndarray, shape (n_warehouses, n_customers)

    Returns
    -------
    Tuple[MarginalTradeoffRepair, _ProblemStub]
        Operator instance and a minimal problem-shaped object exposing
        ``vehicle_types`` (the only attribute the operator inspects).
    """
    n_w = cfg.network.n_warehouses
    n_c = cfg.network.n_customers
    problem = SupplyChainProblem(cfg, distance_matrix, demand)  # [for vehicle_types]
    capacities = np.asarray(  # [per-warehouse capacity vector, kg]
        cfg.network.warehouse_capacities[:n_w], dtype=float,
    )
    repair = MarginalTradeoffRepair(  # [Audit 1.2 — diversity-preserving repair]
        n_warehouses=n_w,
        n_customers=n_c,
        n_vehicle_types=problem.n_vehicle_types,
        demand=demand,
        warehouse_capacities=capacities,
        distance_matrix=distance_matrix,
        vehicle_types=problem.vehicle_types,
        config=cfg,
    )
    return repair, problem


class TestRepairOperator:
    """``MarginalTradeoffRepair`` is idempotent within solver tolerance.

    Once a candidate has been brought into the feasible region, applying
    the repair operator again must be a no-op (modulo the configured
    epsilons). The post-fix capacity slack ``repair_capacity_eps``
    governs the allowable drift between the two passes.

    Validates: Requirements 1.12, 2.12 [bugfix.md C1.12 / C2.12]
    """

    @pytest.fixture(scope="class")
    def cfg(self):
        """Small config so each repair pass runs in <0.1 s."""
        return _make_small_config(n_w=3, n_c=8)  # [shared sizing]

    @pytest.fixture(scope="class")
    def problem_data(self, cfg):
        """Reproducible distance + demand at the project preservation seed."""
        return _build_small_instance(  # [_SEED=42]
            cfg.network.n_warehouses, cfg.network.n_customers, _SEED,
        )

    def test_repair_idempotence_on_random_population(self, cfg, problem_data):
        """``repair(repair(X))`` matches ``repair(X)`` element-wise.

        Validates: Requirements 1.12, 2.12 [bugfix.md C1.12 / C2.12]
        """
        distance_matrix, demand = problem_data  # [_SEED=42]
        repair, problem = _make_repair_operator(cfg, demand, distance_matrix)
        rng = np.random.default_rng(_SEED)
        n_w = cfg.network.n_warehouses
        n_c = cfg.network.n_customers
        n_v = 2
        # Random population spanning the bounds the problem advertises.
        X = rng.uniform(0.0, float(np.max(demand)),  # [matches problem.xu]
                        size=(8, n_w * n_c * n_v))
        once = repair._do(problem, X.copy())  # [first pass — projects to feasible]
        twice = repair._do(problem, once.copy())  # [second pass — should be no-op]
        # Capacity slack from the same config the operator uses internally.
        # The marginal-tradeoff repair is *deterministic* given an input
        # tensor (the internal RNG seeds itself off the byte-hash of X),
        # so the second pass is a true no-op modulo solver epsilons.
        np.testing.assert_allclose(  # [bit-equivalent within eps]
            twice, once,
            atol=cfg.nsga.repair_capacity_eps,
            rtol=1e-9,
        )

    @given(  # [hypothesis: vary scale + seed; assert idempotence]
        seed=st.integers(min_value=0, max_value=2**31 - 1),
        scale=st.floats(  # [shifts the random population's magnitude]
            min_value=0.5, max_value=5.0,
            allow_nan=False, allow_infinity=False,
        ),
    )
    @settings(
        max_examples=8,
        deadline=None,
        suppress_health_check=[
            HealthCheck.function_scoped_fixture,
            HealthCheck.too_slow,
        ],
    )
    def test_property_repair_idempotent(self, seed, scale):
        """Property: ``repair(repair(x)) == repair(x)`` for any input.

        Hypothesis varies the seed of the random pre-repair tensor and
        a scalar magnitude scale so we exercise both small and large
        violations of the demand and capacity constraints.

        Validates: Requirements 1.12, 2.12 [bugfix.md C1.12 / C2.12]
        """
        cfg = _make_small_config(n_w=3, n_c=6)  # [tiny instance for hypothesis]
        distance_matrix, demand = _build_small_instance(3, 6, seed)
        repair, problem = _make_repair_operator(cfg, demand, distance_matrix)
        rng = np.random.default_rng(seed)
        X = rng.uniform(  # [scaled by hypothesis magnitude]
            0.0, scale * float(np.max(demand)),
            size=(4, 3 * 6 * 2),
        )
        once = repair._do(problem, X.copy())  # [first pass]
        twice = repair._do(problem, once.copy())  # [second pass]
        np.testing.assert_allclose(  # [idempotence within solver eps]
            twice, once,
            atol=cfg.nsga.repair_capacity_eps,
            rtol=1e-9,
        )


# =====================================================================
# 4. TestWarmStart — preservation under fixed seed (clauses C3.2 / C3.4)
# =====================================================================


def _load_baseline() -> dict:
    """Load and return the parsed ``NUMERIC_BASELINE.json`` payload.

    Returns
    -------
    dict
        The full baseline payload, or raises ``FileNotFoundError`` if
        the captured file is missing. The TestWarmStart fixture
        converts that into a ``pytest.skip`` so CI skips cleanly when
        Group 0 has not been run yet.
    """
    if not _BASELINE_PATH.exists():  # [task 0.4 captures this file]
        raise FileNotFoundError(
            f"Numeric baseline not found at {_BASELINE_PATH}; "
            "run audit_workspace/capture_numeric_baseline.py."
        )
    with _BASELINE_PATH.open() as f:
        return json.load(f)


def _baseline_or_skip(field: str = "nsga2_pareto") -> dict:
    """Return ``baseline[field]`` or ``pytest.skip`` with a reason.

    Parameters
    ----------
    field : str, optional
        Top-level key inside ``NUMERIC_BASELINE.json`` (default
        ``"nsga2_pareto"``). Documents the expected schema in the
        skip message so a missing key is never silent.
    """
    try:
        baseline = _load_baseline()  # [task 0.4 baseline]
    except FileNotFoundError as exc:
        pytest.skip(str(exc))
    block = baseline.get(field)
    if block is None or "front" not in block:
        pytest.skip(  # [explicit, never silent]
            f"NUMERIC_BASELINE.json is missing the '{field}.front' key; "
            "re-run audit_workspace/capture_numeric_baseline.py."
        )
    return block


# pytest parametrization carries the warm-start regression: a single
# parametrized case today, but additional baseline keys can be added
# without altering the test body.
@pytest.mark.parametrize("baseline_field", ["nsga2_pareto"])
class TestWarmStart:
    """Cold-start (``warm_start=False``) reproduces the captured front.

    Per clauses C3.2 (NSGA-II Pareto front bit-equivalence under fixed
    seed) and C3.4 (warm-start preservation), running ``run_nsga2``
    with ``warm_start=False`` and ``seed=42`` at the recorded
    ``pop_size`` / ``n_gen`` MUST reproduce the Pareto front captured
    in ``audit_workspace/NUMERIC_BASELINE.json`` within the recorded
    relative tolerance (``rtol=1e-6`` plus ``atol=1e-9`` per the
    audit deliverable).

    Validates: Requirements 1.12, 2.12, 3.4
    [bugfix.md C1.12 / C1.14 / C2.12 / C2.14 / C3.2 / C3.4]
    """

    def test_reproduces_baseline_pareto_front(self, baseline_field):
        """Front under ``seed=42, warm_start=False`` matches baseline.

        Loads the captured front, runs NSGA-II with the same
        ``pop_size`` / ``n_gen`` / ``seed`` recorded in the baseline,
        and asserts element-wise closeness via
        ``numpy.isclose(rtol=1e-6, atol=1e-9)``. Falls back to
        ``pytest.skip`` if the baseline file lacks the expected key
        so we never silently mask a missing capture.

        Validates: Requirements 1.12, 2.12, 3.4
        [bugfix.md C3.2 / C3.4]
        """
        ref = _baseline_or_skip(baseline_field)  # [task 0.4 baseline]
        ref_front = np.asarray(ref["front"], dtype=float)  # [(n_ref, 2)]
        cfg_b = ref["config"]  # [pop_size / n_gen / seed / shape]

        cfg = MasterConfig()  # [config FIX-002 — same defaults as capture]
        # Sanity check: baseline must have been captured at the active
        # network shape, otherwise the comparison is meaningless.
        if (
            cfg.network.n_warehouses != cfg_b["n_warehouses"]  # [shape match]
            or cfg.network.n_customers != cfg_b["n_customers"]
        ):
            pytest.skip(  # [skip with reason — never silent pass]
                "Network shape changed since baseline capture: "
                f"baseline={cfg_b['n_warehouses']}x{cfg_b['n_customers']}, "
                f"current={cfg.network.n_warehouses}x"
                f"{cfg.network.n_customers}."
            )

        distance_matrix, demand = _build_synthetic_problem(  # [seed=42]
            cfg, seed=cfg_b["seed"],
        )
        result = run_nsga2(  # [warm_start=False default → C3.4 preservation]
            cfg,
            distance_matrix,
            demand,
            pop_size=cfg_b["pop_size"],  # [baseline pop_size=500]
            n_gen=cfg_b["n_gen"],  # [baseline n_gen=100]
            seed=cfg_b["seed"],  # [baseline seed=42]
        )
        cur_front = np.asarray(result.F, dtype=float)  # [(n_cur, 2)]
        assert cur_front.size > 0, "run_nsga2 returned an empty front"

        # Sort both fronts by (cost, carbon) so cardinality-preserving
        # comparison is invariant to internal ordering of the
        # non-dominated rank.
        ref_sorted = ref_front[np.lexsort((ref_front[:, 1],
                                           ref_front[:, 0]))]
        cur_sorted = cur_front[np.lexsort((cur_front[:, 1],
                                           cur_front[:, 0]))]
        assert cur_sorted.shape == ref_sorted.shape, (  # [size invariant]
            "Pareto-front cardinality regressed: "
            f"baseline={ref_sorted.shape}, current={cur_sorted.shape}"
        )
        # Element-wise closeness per the task's stated rtol/atol pair.
        # ``np.isclose`` checks ``|a - b| <= atol + rtol * |b|`` so this
        # is a strictly stronger guarantee than the baseline's recorded
        # ``tolerance=1e-6 (relative)`` field.
        assert np.all(  # [bugfix.md C3.2 / C3.4 within rtol=1e-6, atol=1e-9]
            np.isclose(cur_sorted, ref_sorted, rtol=1e-6, atol=1e-9)
        ), (
            "Pareto front diverged from NUMERIC_BASELINE.json beyond "
            "rtol=1e-6, atol=1e-9 -- preservation clauses C3.2/C3.4 "
            "violated."
        )

    def test_baseline_metadata_consistent(self, baseline_field):
        """Baseline metadata describes the cold-start cfg used here.

        Sanity-checks the captured ``config`` block records
        ``warm_start=False`` and ``seed=42``; otherwise the comparison
        in ``test_reproduces_baseline_pareto_front`` is meaningless.

        Validates: Requirements 1.12, 2.12, 3.4
        [bugfix.md C3.2 / C3.4]
        """
        ref = _baseline_or_skip(baseline_field)  # [task 0.4 baseline]
        cfg_b = ref["config"]
        assert cfg_b["seed"] == _SEED  # [seed=42 mandated]
        assert cfg_b["warm_start"] is False  # [cold-start path → C3.4]
        assert ref["objective_names"] == ["cost_inr", "carbon_kg_co2"]  # [order]


# --- Merged from test_nsga2.py ---


@pytest.fixture
def small_config():
    """Create small-scale configuration for testing."""
    config = MasterConfig()
    config.network.n_customers = 10
    config.network.n_warehouses = 3
    return config


@pytest.fixture
def small_distance_matrix(small_config):
    """Create a small distance matrix for testing."""
    n_w = small_config.network.n_warehouses
    n_c = small_config.network.n_customers
    rng = np.random.default_rng(42)
    return rng.uniform(50, 500, size=(n_w, n_c))


@pytest.fixture
def small_demand(small_config):
    """Create small demand array for testing."""
    rng = np.random.default_rng(42)
    return rng.uniform(200, 2000, size=small_config.network.n_customers)


class TestDemandRepair:
    """Test custom demand repair operator."""

    def test_repair_satisfies_demand(
        self, small_config, small_distance_matrix, small_demand
    ):
        """Repair should ensure allocations satisfy demand for each customer."""
        n_w = small_config.network.n_warehouses
        n_c = small_config.network.n_customers
        n_v = 2  # HCV, LCV
        warehouse_capacities = np.full(n_w, 50000.0)

        repair = DemandRepair(
            n_w, n_c, n_v, small_demand,
            warehouse_capacities, small_distance_matrix,
        )

        # Create random population
        rng = np.random.default_rng(42)
        X = rng.uniform(0, 1000, size=(5, n_w * n_c * n_v))

        repaired = repair._do(None, X.copy())

        # Check each customer's demand is satisfied
        for i in range(len(repaired)):
            x = repaired[i].reshape(n_w, n_c, n_v)
            for c in range(n_c):
                total = x[:, c, :].sum()
                assert total == pytest.approx(
                    small_demand[c], rel=1e-3
                )

    def test_repair_non_negative(
        self, small_config, small_distance_matrix, small_demand
    ):
        """Repair should ensure non-negative values."""
        n_w = small_config.network.n_warehouses
        n_c = small_config.network.n_customers
        n_v = 2
        warehouse_capacities = np.full(n_w, 50000.0)

        repair = DemandRepair(
            n_w, n_c, n_v, small_demand,
            warehouse_capacities, small_distance_matrix,
        )

        # Create population with negative values
        X = np.full((3, n_w * n_c * n_v), -0.5)

        repaired = repair._do(None, X.copy())

        # All values should be non-negative after repair
        for i in range(len(repaired)):
            assert np.all(repaired[i] >= 0)

    def test_repair_respects_capacity(
        self, small_config, small_distance_matrix, small_demand
    ):
        """Repair should respect warehouse capacity constraints."""
        n_w = small_config.network.n_warehouses
        n_c = small_config.network.n_customers
        n_v = 2
        # Set very tight capacity to test redistribution
        warehouse_capacities = np.full(n_w, 50000.0)

        repair = DemandRepair(
            n_w, n_c, n_v, small_demand,
            warehouse_capacities, small_distance_matrix,
        )

        # Create population that overloads warehouse 0
        rng = np.random.default_rng(42)
        X = rng.uniform(0, 2000, size=(3, n_w * n_c * n_v))

        repaired = repair._do(None, X.copy())

        # Check warehouse capacities are respected
        for i in range(len(repaired)):
            x = repaired[i].reshape(n_w, n_c, n_v)
            for w in range(n_w):
                wh_load = x[w, :, :].sum()
                # With generous capacity, should be within limits
                assert wh_load <= warehouse_capacities[w] + 1e-3


class TestSupplyChainProblem:
    """Test the optimization problem definition."""

    def test_problem_dimensions(
        self, small_config, small_distance_matrix, small_demand
    ):
        """Problem should have correct dimensions."""
        problem = SupplyChainProblem(
            small_config, small_distance_matrix, small_demand
        )

        n_w = small_config.network.n_warehouses
        n_c = small_config.network.n_customers
        n_v = 2  # HCV, LCV

        assert problem.n_var == n_w * n_c * n_v
        assert problem.n_obj == 2
        # Constraints: n_customers (demand) + n_warehouses (capacity)
        assert problem.n_ieq_constr == n_c + n_w

    def test_variable_bounds_volume_based(
        self, small_config, small_distance_matrix, small_demand
    ):
        """Variable bounds should be volume-based (0 to max_demand)."""
        problem = SupplyChainProblem(
            small_config, small_distance_matrix, small_demand
        )

        assert np.all(problem.xl == 0)
        max_demand = float(np.max(small_demand))
        assert np.all(problem.xu == max_demand)

    def test_evaluate_feasible(
        self, small_config, small_distance_matrix, small_demand
    ):
        """Evaluate a feasible solution."""
        n_w = small_config.network.n_warehouses
        n_c = small_config.network.n_customers
        n_v = 2
        problem = SupplyChainProblem(
            small_config, small_distance_matrix, small_demand
        )

        # Create feasible solution: all demand from warehouse 0, HCV
        X = np.zeros((1, n_w * n_c * n_v))
        x = X[0].reshape(n_w, n_c, n_v)
        for c in range(n_c):
            x[0, c, 0] = small_demand[c]
        X[0] = x.flatten()

        out = {}
        problem._evaluate(X, out)

        assert "F" in out
        assert "G" in out
        assert out["F"].shape == (1, 2)
        assert out["F"][0, 0] > 0  # Cost > 0
        assert out["F"][0, 1] > 0  # Emission > 0

    def test_evaluate_constraints(
        self, small_config, small_distance_matrix, small_demand
    ):
        """Feasible solution should satisfy constraints (G <= 0)."""
        n_w = small_config.network.n_warehouses
        n_c = small_config.network.n_customers
        n_v = 2
        problem = SupplyChainProblem(
            small_config, small_distance_matrix, small_demand
        )

        # Feasible: split demand evenly across warehouses using HCV
        X = np.zeros((1, n_w * n_c * n_v))
        x = X[0].reshape(n_w, n_c, n_v)
        for c in range(n_c):
            for w in range(n_w):
                x[w, c, 0] = small_demand[c] / n_w
        X[0] = x.flatten()

        out = {}
        problem._evaluate(X, out)

        # Demand constraints should be satisfied
        for c in range(n_c):
            assert out["G"][0, c] <= 0 + 1e-2

    def test_cost_uses_ceil(
        self, small_config, small_distance_matrix, small_demand
    ):
        """Cost objective should use ceil for discrete trip counting (round-trip)."""
        n_w = small_config.network.n_warehouses
        n_c = small_config.network.n_customers
        n_v = 2
        problem = SupplyChainProblem(
            small_config, small_distance_matrix, small_demand
        )

        # Ship slightly more than one vehicle capacity from w0 to c0
        X = np.zeros((1, n_w * n_c * n_v))
        x = X[0].reshape(n_w, n_c, n_v)
        # Put all demand on warehouse 0, HCV
        hcv_cap = small_config.vehicle.hcv_capacity
        # Set volume to 1.5 * capacity -> ceil gives 2 trips
        x[0, 0, 0] = 1.5 * hcv_cap
        # Put remaining demand elsewhere to satisfy constraint structure
        for c in range(1, n_c):
            x[0, c, 0] = small_demand[c]
        X[0] = x.flatten()

        out = {}
        problem._evaluate(X, out)

        # Cost for route (0,0) should reflect 2 round-trips
        dist = small_distance_matrix[0, 0]
        expected_cost_00 = 2 * small_config.vehicle.hcv_cost_per_km * dist * 2
        # Total cost includes all routes
        assert out["F"][0, 0] >= expected_cost_00


class TestNSGA2Run:
    """Test NSGA-II optimization execution."""

    def test_small_scale_run(
        self, small_config, small_distance_matrix, small_demand
    ):
        """Run NSGA-II with minimal settings."""
        result = run_nsga2(
            small_config,
            small_distance_matrix,
            small_demand,
            pop_size=20,
            n_gen=5,
            seed=42,
        )

        assert result is not None
        assert result.F is not None
        assert result.F.shape[1] == 2  # Two objectives
        assert len(result.F) > 0  # At least one solution

    def test_objectives_positive(
        self, small_config, small_distance_matrix, small_demand
    ):
        """All objective values should be positive."""
        result = run_nsga2(
            small_config,
            small_distance_matrix,
            small_demand,
            pop_size=20,
            n_gen=5,
            seed=42,
        )

        # Filter out infeasible solutions if any
        if result.F is not None and len(result.F) > 0:
            assert np.all(result.F >= 0)


class TestHypervolumeConvergence:
    """Test hypervolume-based early stopping in NSGA-II."""

    def test_hypervolume_reference_point(self):
        """Verify ref_point = front.max(axis=0) * 1.1 and HV is positive."""
        from pymoo.indicators.hv import HV

        # Create a simple 2D Pareto front
        front = np.array([
            [1.0, 4.0],
            [2.0, 3.0],
            [3.0, 2.0],
            [4.0, 1.0],
        ])

        ref_point = front.max(axis=0) * 1.1
        expected_ref = np.array([4.0 * 1.1, 4.0 * 1.1])
        np.testing.assert_allclose(ref_point, expected_ref)

        hv_indicator = HV(ref_point=ref_point, norm_ref_point=False)
        hv_val = hv_indicator(front)
        assert hv_val > 0

    def test_nsga2_returns_valid_result_with_convergence(
        self, small_config, small_distance_matrix, small_demand
    ):
        """Run run_nsga2 with convergence check and verify valid result."""
        result = run_nsga2(
            small_config,
            small_distance_matrix,
            small_demand,
            pop_size=20,
            n_gen=100,
            seed=42,
        )

        assert result is not None
        assert result.F is not None
        assert result.F.shape[1] == 2  # Two objectives
        assert len(result.F) > 0
        # All objectives should be positive (cost and emissions)
        assert np.all(result.F >= 0)

    def test_early_stopping_triggers(
        self, small_config, small_distance_matrix, small_demand
    ):
        """Verify that early stopping works without error on large n_gen."""
        # Run with a large n_gen - the function should complete
        # (either via early stopping or reaching the max)
        result = run_nsga2(
            small_config,
            small_distance_matrix,
            small_demand,
            pop_size=20,
            n_gen=200,
            seed=42,
        )

        assert result is not None
        assert result.F is not None
        assert len(result.F) > 0

