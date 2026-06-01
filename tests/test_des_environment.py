"""Property-based and preservation tests for the DES environment.

This module covers task 4.4 of the supply-chain-research-audit spec.
It is deliberately separate from ``tests/test_des.py`` (legacy unit
tests) so the four named ``Test*`` classes required by the task land
in one auditable file. Style and hypothesis cadence mirror
``tests/test_emission_model.py`` (task 4.1) and
``tests/test_nsga2_solver.py`` (task 4.3).

The four classes encode invariants from
``.kiro/specs/supply-chain-research-audit/bugfix.md``:

* ``TestProcessRegistration``     -- the DES wires three SimPy
  processes (customer-order, replenishment, daily-metrics) plus one
  ``shock.apply`` process per registered shock
  [Banks-2010 §3] [Mueller-2017 §SimPy].
* ``TestContainerLevelGuard``     -- ``simpy.Container.level`` never
  goes negative across the simulated horizon [bugfix.md C1.4 / C2.4
  no-stockout invariant].
* ``TestTimeUnitConsistency``     -- ``env.now`` advances one
  simulated day per ``env.timeout(1)`` and finishes at exactly
  ``sim_days + warmup_days`` [Mueller-2017 §SimPy time-unit
  invariant].
* ``TestNoShockServiceLevel``     -- mean service level under
  ``seed=42, n_replications=30`` matches the captured baseline within
  ``+/-0.005`` [bugfix.md C3.9].

References
----------
.. [Banks-2010] Banks, J., Carson, J. S., Nelson, B. L., & Nicol,
   D. M. (2010). Discrete-Event System Simulation (5th ed.).
   Pearson Prentice Hall. ISBN 978-0-13-606212-7.
.. [Mueller-2017] Mueller, S. (2017). SimPy: Discrete-Event Simulation
   for Python. SimPy 3/4 documentation.
   https://simpy.readthedocs.io/en/stable/
"""
# [Banks-2010 §3] discrete-event semantics anchor; [Mueller-2017 §SimPy]
# time-unit / process-registration anchor; preservation per
# [bugfix.md C3.9]; mirrors hypothesis cadence in
# tests/test_emission_model.py (task 4.1) and tests/test_nsga2_solver.py
# (task 4.3).

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import simpy  # [Mueller-2017 §SimPy] core DES library
from hypothesis import HealthCheck, given, settings, strategies as st

from supply_chain_research.config import (  # [config FIX-002]
    MasterConfig,
    SimulationConfig,
)
from supply_chain_research.phase2_resilience.des_environment import (  # [SUT]
    DESEnvironment,
    Warehouse,
)


# Repository-relative path to the captured baseline produced by
# ``audit_workspace/capture_numeric_baseline.py`` (task 0.4).
_REPO_ROOT = Path(__file__).resolve().parent.parent  # [tests/.. → repo root]
_BASELINE_PATH = _REPO_ROOT / "audit_workspace" / "NUMERIC_BASELINE.json"

# Project-wide preservation seed mandated by clause C3.9.
_SEED = 42  # [bugfix.md C3.9]

# Replication count mandated by clause C3.9 / task 4.4.
_N_REPLICATIONS = 30  # [bugfix.md C3.9, task 4.4]

# Top-level baseline key + nested mean-service-level field. The audit
# captured it under ``des_service_level.mean_service_level`` per
# ``audit_workspace/capture_numeric_baseline.capture_des_no_shock``.
_BASELINE_FIELD = "des_service_level"  # [task 0.4 NUMERIC_BASELINE.json]
_BASELINE_VALUE_KEY = "mean_service_level"  # [task 0.4 captured field]


# ---------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------


def _make_small_config(
    sim_days: int = 20,
    warmup_days: int = 5,
    n_warehouses: int = 2,
    n_customers: int = 6,
) -> MasterConfig:
    """Construct a small ``MasterConfig`` for fast property tests.

    Parameters
    ----------
    sim_days : int, optional
        Post-warmup simulated days. Default 20 keeps each run under
        a couple of seconds.
    warmup_days : int, optional
        Warmup days discarded from the metrics tail.
    n_warehouses, n_customers : int, optional
        Network sizing; the production default is 5 warehouses and
        100 customers, but the property tests use a tiny instance to
        stay inside the hypothesis budget.

    Returns
    -------
    MasterConfig
        A config whose ``simulation`` and ``network`` sections are
        downsized; everything else is left at the production
        defaults so we exercise the same numerical paths.
    """
    cfg = MasterConfig(  # [config FIX-002 — central Pydantic config]
        simulation=SimulationConfig(  # [override sim/warmup horizon only]
            sim_days=sim_days,
            warmup_days=warmup_days,
        ),
    )
    cfg.network.n_warehouses = n_warehouses  # [shrink for hypothesis budget]
    cfg.network.n_customers = n_customers
    return cfg


def _load_baseline_block() -> dict | None:
    """Return the ``des_service_level`` block from the captured JSON.

    Returns
    -------
    dict or None
        The full ``des_service_level`` block, or ``None`` if either
        the file is missing or the expected key is absent.
        ``TestNoShockServiceLevel`` converts ``None`` into a
        ``pytest.skip`` with a documented reason so we never silently
        pass.
    """
    if not _BASELINE_PATH.exists():  # [task 0.4 captures this file]
        return None
    try:
        payload = json.loads(_BASELINE_PATH.read_text())  # [JSON load]
    except (OSError, json.JSONDecodeError):  # [defensive — never silent]
        return None
    block = payload.get(_BASELINE_FIELD)
    if not isinstance(block, dict):  # [missing top-level key]
        return None
    if _BASELINE_VALUE_KEY not in block:  # [missing nested mean]
        return None
    return block


# =====================================================================
# 1. TestProcessRegistration -- DES wires every SimPy process correctly
# =====================================================================


class TestProcessRegistration:
    """``DESEnvironment.run()`` registers every required SimPy process.

    [Banks-2010 §3] frames a discrete-event simulation as a set of
    cooperating event-generating processes; the DES under test wires
    three by default (``_customer_order_process``,
    ``_replenishment_process``, ``_daily_metrics_process``) and one
    extra ``shock.apply(...)`` process per registered shock. Missing
    any of those processes silently breaks service-level tracking,
    which is why we pin the contract here.

    Validates: Requirements 1.12, 2.12 [bugfix.md C1.12 / C2.12]
    """

    def test_run_populates_metrics_and_warehouses(self):
        """After ``run()`` the env, warehouses, and metrics are wired.

        [Banks-2010 §3] discrete-event simulation contract: by the
        time control returns from ``env.run(until=T)`` every process
        registered before the run-call must have produced its share
        of state mutations.

        Validates: Requirements 1.12, 2.12 [bugfix.md C1.12 / C2.12]
        """
        cfg = _make_small_config()  # [small instance — fast]
        des = DESEnvironment(config=cfg, seed=_SEED)  # [seed=42]
        results = des.run()
        assert isinstance(des.env, simpy.Environment)  # [SimPy env wired]
        assert len(des.warehouses) == cfg.network.n_warehouses  # [WH count]
        # Daily-metrics buffer length matches sim_days exactly because
        # the customer-order process appends only after warmup.
        assert len(des.daily_service_level) == cfg.simulation.sim_days
        assert results["sim_days"] == cfg.simulation.sim_days
        assert results["warmup_days"] == cfg.simulation.warmup_days

    def test_run_records_one_metrics_row_per_simulated_day(self):
        """Customer + metrics processes append exactly ``sim_days`` rows.

        Verifies the customer-order process and the daily-metrics
        process both yield one ``env.timeout(1)`` per simulated day
        [Mueller-2017 §SimPy]: per-day buffers ``daily_orders``,
        ``daily_fulfilled``, ``daily_costs``, and ``daily_emissions``
        each have length ``sim_days``.

        Validates: Requirements 1.12, 2.12 [bugfix.md C1.12 / C2.12]
        """
        cfg = _make_small_config()  # [shared sizing]
        des = DESEnvironment(config=cfg, seed=_SEED)
        des.run()
        assert len(des.daily_orders) == cfg.simulation.sim_days
        assert len(des.daily_fulfilled) == cfg.simulation.sim_days
        assert len(des.daily_costs) == cfg.simulation.sim_days
        assert len(des.daily_emissions) == cfg.simulation.sim_days
        assert len(des.daily_sla_met) == cfg.simulation.sim_days

    def test_replenishment_process_advances_inventory(self):
        """Replenishment process is wired -- WH levels stay at-or-below cap.

        The daily replenishment process fires every simulated day; if
        it fails to register the warehouses would drift toward zero
        in seconds and the no-shock service level would collapse.
        Sampling final levels confirms the process runs and respects
        the per-warehouse capacity cap [Mueller-2017 §SimPy.Container].

        Validates: Requirements 1.12, 2.12 [bugfix.md C1.12 / C2.12]
        """
        cfg = _make_small_config()  # [small instance]
        des = DESEnvironment(config=cfg, seed=_SEED)
        des.run()
        for wh in des.warehouses:  # [Banks-2010 §3 process invariant]
            assert wh.level >= 0.0  # [container guard]
            assert wh.level <= wh.capacity + 1e-9  # [cap respected]

    def test_shock_apply_process_registered_per_shock(self):
        """Each ``add_shock`` survives the next ``run()`` invocation.

        The SUT lazily wires ``shock.apply(self)`` as a SimPy process
        inside ``run()``; confirming the shock objects survive the
        run (with their internal start markers populated) proves the
        registration path executed [Banks-2010 §3 process composition].

        Validates: Requirements 1.12, 2.12 [bugfix.md C1.12 / C2.12]
        """
        from supply_chain_research.phase2_resilience.shock_models import (
            DemandShock,  # [shock contract]
        )

        cfg = _make_small_config()  # [shared sizing]
        des = DESEnvironment(config=cfg, seed=_SEED)
        shock = DemandShock(  # [demand shock — non-default behaviour]
            customer_ids=[0, 1, 2],
            multiplier=1.5,
            duration_range=(3, 3),
            start_day=2,
            seed=_SEED,
        )
        des.add_shock(shock)
        assert shock in des.active_shocks  # [registration recorded]
        des.run()
        # ``apply`` records ``shock_start`` once it actually fires;
        # if the process were never registered this would still be
        # ``None`` and the check would fail.
        assert shock.shock_start == 2  # [process actually executed]


# =====================================================================
# 2. TestContainerLevelGuard -- WH inventory never goes negative
# =====================================================================


class TestContainerLevelGuard:
    """SimPy ``Container.level`` for every warehouse stays non-negative.

    The DES design note in ``des_environment.py`` documents a
    time-stepped, race-free fulfilment loop; the property here is the
    operational invariant that follows from that design
    [Mueller-2017 §SimPy.Container]. We sample the invariant across
    replications to catch any future refactor that re-introduces a
    yield between the level-check and the ``container.get`` call.

    Validates: Requirements 1.12, 2.12 [bugfix.md C1.12 / C2.12]
    """

    def test_warehouse_fulfill_never_negative(self):
        """``Warehouse.fulfill`` returns no more than the current level.

        Pure unit-style probe of the fulfilment guard inside a
        single-process SimPy environment so the invariant is visible
        even if the surrounding DES changes.

        Validates: Requirements 1.12, 2.12 [bugfix.md C1.12 / C2.12]
        """
        env = simpy.Environment()  # [Mueller-2017 §SimPy Environment]
        wh = Warehouse(env, 0, capacity=1000.0, initial_level=10.0)
        for request in (5.0, 5.0, 5.0):  # [drain to empty + over-request]
            qty, _ok = wh.fulfill(request)
            assert qty <= request + 1e-9  # [no over-fulfilment]
            assert wh.level >= -1e-12  # [non-negative invariant]

    def test_levels_non_negative_post_run_default_seed(self):
        """All warehouse levels are non-negative after a no-shock run.

        Validates: Requirements 1.12, 2.12 [bugfix.md C1.12 / C2.12]
        """
        cfg = _make_small_config()  # [small instance]
        des = DESEnvironment(config=cfg, seed=_SEED)
        des.run()
        for wh in des.warehouses:  # [Container guard]
            assert wh.level >= -1e-12  # [non-negative]

    @given(  # [vary seed to exercise stochastic order arrivals]
        seed=st.integers(min_value=0, max_value=2**31 - 1),
    )
    @settings(  # [match tests/test_emission_model.py cadence]
        max_examples=8,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_property_levels_non_negative_under_random_seeds(self, seed):
        """Property: ``forall seed. min(wh.level) >= 0`` after ``run()``.

        Drives the DES with a varying numpy seed but tiny problem
        dimensions so each example finishes in well under a second.

        Validates: Requirements 1.12, 2.12 [bugfix.md C1.12 / C2.12]
        """
        cfg = _make_small_config(  # [tiny instance for hypothesis]
            sim_days=10, warmup_days=2, n_warehouses=2, n_customers=4,
        )
        des = DESEnvironment(config=cfg, seed=seed)
        des.run()
        for wh in des.warehouses:  # [Container guard under any seed]
            assert wh.level >= -1e-12

    def test_property_levels_non_negative_during_simulation(self):
        """Snapshot every warehouse level on every simulated day.

        Registers an extra SimPy process that records the per-warehouse
        level at every ``env.timeout(1)`` and asserts the running
        minimum is non-negative at every step. This catches a level
        going briefly negative between the daily aggregations even if
        the post-run snapshot looks healthy.

        Validates: Requirements 1.12, 2.12 [bugfix.md C1.12 / C2.12]
        """
        cfg = _make_small_config(  # [small instance — recorder is cheap]
            sim_days=15, warmup_days=3, n_warehouses=2, n_customers=4,
        )
        des = DESEnvironment(config=cfg, seed=_SEED)
        levels: list[float] = []  # [per-(day, warehouse) flattened snapshots]

        # Build the env manually so we can inject a level-recorder
        # process before ``env.run(until=T)`` fires. Mirrors the
        # SUT's own process-wiring pattern [Banks-2010 §3].
        des.env = simpy.Environment()  # [fresh env]
        capacities = cfg.network.warehouse_capacities
        des.warehouses = [  # [matches DESEnvironment.run construction]
            Warehouse(
                des.env, w_id,
                capacities[w_id]
                if w_id < len(capacities)
                else cfg.simulation.fallback_warehouse_capacity,
                initial_level=(
                    capacities[w_id]
                    if w_id < len(capacities)
                    else cfg.simulation.fallback_warehouse_capacity
                ) * cfg.simulation.initial_inventory_fraction,
                replenishment_rate_multiplier=(
                    cfg.simulation.replenishment_rate_multiplier
                ),
            )
            for w_id in range(des.n_warehouses)
        ]
        des.daily_orders = []
        des.daily_fulfilled = []
        des.daily_service_level = []
        des.daily_costs = []
        des.daily_emissions = []
        des.daily_sla_met = []
        des.daily_travel_times = []

        des.env.process(des._customer_order_process())  # [SUT process]
        des.env.process(des._replenishment_process())  # [SUT process]
        des.env.process(des._daily_metrics_process())  # [SUT process]

        def _level_recorder(env, warehouses, sink):
            """Snapshot every warehouse level at every simulated day.

            Yields ``env.timeout(1)`` so it advances in lockstep with
            the customer-order and replenishment processes
            [Banks-2010 §3].
            """
            total = cfg.simulation.sim_days + cfg.simulation.warmup_days
            while env.now < total:
                for wh in warehouses:
                    sink.append(float(wh.level))  # [per-day snapshot]
                yield env.timeout(1)  # [advance one simulated day]

        des.env.process(_level_recorder(  # [extra observer process]
            des.env, des.warehouses, levels,
        ))
        des.env.run(  # [match sim_days + warmup_days horizon]
            until=cfg.simulation.sim_days + cfg.simulation.warmup_days,
        )
        assert min(levels) >= -1e-9  # [in-flight non-negativity]
        assert len(levels) > 0  # [recorder actually ran]


# =====================================================================
# 3. TestTimeUnitConsistency -- env.now advances in days
# =====================================================================


class TestTimeUnitConsistency:
    """``env.now`` advances one *day* per ``env.timeout(1)``.

    The DES module docstring documents a day-stepped time model; this
    is the [Mueller-2017 §SimPy] convention that ``env.run(until=T)``
    advances ``env.now`` to exactly ``T`` units. Encoding that as a
    property here means any future refactor (e.g. switching to hours
    via a ``yield env.timeout(24)``) fails CI immediately.

    Validates: Requirements 1.12, 2.12 [bugfix.md C1.12 / C2.12]
    """

    def test_env_now_matches_total_horizon(self):
        """``env.now == sim_days + warmup_days`` after ``run()``.

        [Mueller-2017 §SimPy] specifies that ``env.run(until=T)``
        runs the simulation forward until the next event is at or
        beyond ``T``; under the DES day-step convention that means
        ``env.now`` lands exactly on the integer ``T``.

        Validates: Requirements 1.12, 2.12 [bugfix.md C1.12 / C2.12]
        """
        cfg = _make_small_config(sim_days=12, warmup_days=4)  # [small]
        des = DESEnvironment(config=cfg, seed=_SEED)
        des.run()
        expected = cfg.simulation.sim_days + cfg.simulation.warmup_days
        assert des.env.now == pytest.approx(expected, abs=1e-12)

    def test_post_warmup_buffer_length_equals_sim_days(self):
        """Number of metric rows == ``sim_days`` (warmup discarded).

        The customer-order process appends to the metric buffers only
        once ``day >= warmup_days`` so the surviving length equals
        ``sim_days`` exactly [bugfix.md C3.9 service-level horizon].

        Validates: Requirements 1.12, 2.12 [bugfix.md C1.12 / C2.12]
        """
        cfg = _make_small_config(sim_days=15, warmup_days=5)  # [shared sizing]
        des = DESEnvironment(config=cfg, seed=_SEED)
        des.run()
        # Float epsilon: counts are exact integers, so eq is fine.
        assert len(des.daily_service_level) == cfg.simulation.sim_days
        assert des.total_days_simulated == cfg.simulation.sim_days

    @given(  # [vary horizon to confirm the day-step invariant scales]
        sim_days=st.integers(min_value=5, max_value=25),  # [budget cap]
        warmup_days=st.integers(min_value=0, max_value=5),  # [budget cap]
    )
    @settings(
        max_examples=8,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_property_env_now_equals_horizon(self, sim_days, warmup_days):
        """Property: ``env.now`` lands on ``sim_days + warmup_days``.

        Validates: Requirements 1.12, 2.12 [bugfix.md C1.12 / C2.12]
        """
        cfg = _make_small_config(  # [tiny instance for hypothesis]
            sim_days=sim_days,
            warmup_days=warmup_days,
            n_warehouses=2,
            n_customers=4,
        )
        des = DESEnvironment(config=cfg, seed=_SEED)
        des.run()
        expected = sim_days + warmup_days
        # SimPy advances by integer day-step yields, so equality is
        # exact (float-epsilon tolerance is purely belt-and-braces).
        assert des.env.now == pytest.approx(expected, abs=1e-12)
        assert len(des.daily_service_level) == sim_days


# =====================================================================
# 4. TestNoShockServiceLevel -- preservation against NUMERIC_BASELINE.json
# =====================================================================


class TestNoShockServiceLevel:
    """No-shock mean service level matches the captured baseline.

    Per clause C3.9, running the DES under ``seed=42,
    n_replications=30`` with **no** shocks active MUST produce a
    mean service level within ``+/-0.005`` of the value recorded in
    ``audit_workspace/NUMERIC_BASELINE.json``. Replication seeds
    follow the same scheme used by the capture script
    (``base_seed + i``) so the comparison is bit-for-bit faithful.

    Validates: Requirements 1.12, 2.12, 3.9
    [bugfix.md C1.12 / C2.12 / C3.9]
    """

    def test_mean_service_level_matches_baseline(self):
        """30 replications at ``seed=42`` reproduce the captured mean.

        Loads the baseline value, runs ``DESEnvironment`` 30 times
        without registering any shocks, and asserts the absolute
        difference of the per-replication mean is at most ``0.005``.
        Skips with a documented reason if the baseline file or key is
        missing -- never silently passes.

        Validates: Requirements 1.12, 2.12, 3.9 [bugfix.md C3.9]
        """
        block = _load_baseline_block()  # [task 0.4 NUMERIC_BASELINE.json]
        if block is None:  # [explicit skip — never silent]
            pytest.skip(
                f"NUMERIC_BASELINE.json missing or lacks "
                f"'{_BASELINE_FIELD}.{_BASELINE_VALUE_KEY}'; run "
                "audit_workspace/capture_numeric_baseline.py."
            )

        baseline_mean = float(block[_BASELINE_VALUE_KEY])  # [captured]
        baseline_cfg = block.get("config", {})  # [seed/horizon/shape]
        n_replications = int(  # [task 4.4 mandates 30]
            baseline_cfg.get("n_replications", _N_REPLICATIONS),
        )
        base_seed = int(baseline_cfg.get("base_seed", _SEED))  # [seed=42]

        cfg = MasterConfig()  # [config FIX-002 — production defaults]
        # Sanity check: baseline must have been captured at the active
        # network/horizon shape, otherwise comparison is meaningless.
        if (
            cfg.network.n_warehouses
            != baseline_cfg.get("n_warehouses", cfg.network.n_warehouses)
            or cfg.network.n_customers
            != baseline_cfg.get("n_customers", cfg.network.n_customers)
            or cfg.simulation.sim_days
            != baseline_cfg.get("sim_days", cfg.simulation.sim_days)
            or cfg.simulation.warmup_days
            != baseline_cfg.get(
                "warmup_days", cfg.simulation.warmup_days,
            )
        ):
            pytest.skip(  # [skip with reason — never silent]
                "DES baseline shape changed since capture: "
                f"baseline={baseline_cfg}, current network="
                f"{cfg.network.n_warehouses}x{cfg.network.n_customers}, "
                f"sim_days={cfg.simulation.sim_days}, "
                f"warmup_days={cfg.simulation.warmup_days}.",
            )

        # Re-run the no-shock baseline. Per-replication seeds match
        # ``capture_numeric_baseline.capture_des_no_shock`` exactly.
        service_levels: list[float] = []
        for i in range(n_replications):  # [bugfix.md C3.9 -- 30 reps]
            des = DESEnvironment(config=cfg, seed=base_seed + i)
            assert des.active_shocks == []  # [no-shock invariant]
            results = des.run()
            service_levels.append(  # [per-replication mean]
                float(results["mean_service_level"]),
            )

        sl_arr = np.asarray(service_levels)  # [n_replications,]
        current_mean = float(sl_arr.mean())  # [aggregate]
        delta = abs(current_mean - baseline_mean)  # [task 4.4: ±0.005]
        assert delta <= 0.005, (
            "DES no-shock mean service level diverged from "
            f"NUMERIC_BASELINE.json: current={current_mean:.6f}, "
            f"baseline={baseline_mean:.6f}, |delta|={delta:.6f} > 0.005 "
            "-- preservation clause C3.9 violated."
        )

    def test_baseline_metadata_consistent(self):
        """Captured config records ``n_replications=30`` and ``seed=42``.

        Sanity-checks the captured ``config`` block so the comparison
        in ``test_mean_service_level_matches_baseline`` reflects the
        exact contract clause C3.9 spells out.

        Validates: Requirements 1.12, 2.12, 3.9 [bugfix.md C3.9]
        """
        block = _load_baseline_block()  # [task 0.4 baseline]
        if block is None:  # [skip with reason]
            pytest.skip(
                f"NUMERIC_BASELINE.json missing or lacks "
                f"'{_BASELINE_FIELD}.{_BASELINE_VALUE_KEY}'.",
            )
        cfg_b = block.get("config", {})  # [captured config]
        # Tolerance matches clause C3.9 / task 4.4 exactly.
        assert block.get("tolerance") == pytest.approx(0.005, abs=1e-12)
        assert cfg_b.get("base_seed") == _SEED  # [seed=42]
        assert cfg_b.get("n_replications") == _N_REPLICATIONS  # [30 reps]
        assert cfg_b.get("shocks") == []  # [no-shock baseline]


# --- Merged from test_des.py ---

from supply_chain_research.phase2_resilience.monte_carlo_runner import (
    MonteCarloRunner,
)
from supply_chain_research.phase2_resilience.resilience_metrics import (
    ResilienceMetrics,
)
from supply_chain_research.phase2_resilience.shock_models import (
    DemandShock as DemandShockModel,
    SupplyShock,
)


def _small_config_legacy():
    """Create a small config for fast testing (from test_des.py)."""
    config = MasterConfig(
        simulation=SimulationConfig(
            sim_days=60,
            warmup_days=10,
            lambda_orders=2.0,
            order_size_mu=1.5,
            order_size_sigma=0.3,
            des_order_size_mu=4.0,
            des_order_size_sigma=0.3,
        ),
    )
    # Override network size for speed
    config.network.n_customers = 10
    config.network.n_warehouses = 2
    return config


class TestWarehouse:
    """Tests for Warehouse class."""

    def test_warehouse_creation(self):
        """Warehouse initializes with correct capacity and level."""
        env = simpy.Environment()
        wh = Warehouse(env, 0, capacity=1000, initial_level=800)
        assert wh.level == 800
        assert wh.capacity == 1000
        assert wh.warehouse_id == 0

    def test_warehouse_fulfill_success(self):
        """Warehouse fulfills order when sufficient inventory."""
        env = simpy.Environment()
        wh = Warehouse(env, 0, capacity=1000, initial_level=800)
        qty, success = wh.fulfill(100)
        assert success is True
        assert qty == 100
        assert wh.level == 700

    def test_warehouse_fulfill_partial(self):
        """Warehouse fulfills partial order when limited stock."""
        env = simpy.Environment()
        wh = Warehouse(env, 0, capacity=1000, initial_level=50)
        qty, success = wh.fulfill(100)
        assert success is True
        assert qty == 50
        assert wh.level == 0

    def test_warehouse_fulfill_empty(self):
        """Warehouse rejects order when empty."""
        env = simpy.Environment()
        wh = Warehouse(env, 0, capacity=1000, initial_level=0)
        qty, success = wh.fulfill(100)
        assert success is False
        assert qty == 0.0

    def test_warehouse_no_negative_inventory(self):
        """Container level never goes negative."""
        env = simpy.Environment()
        wh = Warehouse(env, 0, capacity=1000, initial_level=10)
        # Fulfill multiple times
        wh.fulfill(5)
        wh.fulfill(5)
        qty, success = wh.fulfill(5)
        assert wh.level >= 0
        assert success is False


class TestDESEnvironment:
    """Tests for DES environment."""

    def test_des_runs_without_errors(self):
        """DES completes a simulation without raising errors."""
        config = _small_config_legacy()
        des = DESEnvironment(config=config, seed=42)
        results = des.run()
        assert results is not None
        assert "daily_service_level" in results
        assert "daily_orders" in results

    def test_des_correct_simulation_length(self):
        """DES produces correct number of days of data."""
        config = _small_config_legacy()
        des = DESEnvironment(config=config, seed=42)
        results = des.run()
        # Should have sim_days worth of data (warmup excluded)
        assert len(results["daily_service_level"]) == config.simulation.sim_days

    def test_des_service_level_range(self):
        """Service levels are between 0 and 1."""
        config = _small_config_legacy()
        des = DESEnvironment(config=config, seed=42)
        results = des.run()
        sl = results["daily_service_level"]
        assert all(0.0 <= s <= 1.0 for s in sl)

    def test_des_with_distance_matrix(self):
        """DES accepts and uses provided distance matrix."""
        config = _small_config_legacy()
        dist = np.random.default_rng(42).uniform(
            50, 500, size=(2, 10)
        )
        des = DESEnvironment(
            config=config, distance_matrix=dist, seed=42
        )
        results = des.run()
        assert results["sim_days"] == 60

    def test_des_reproducibility(self):
        """Same seed produces same results."""
        config = _small_config_legacy()
        des1 = DESEnvironment(config=config, seed=123)
        results1 = des1.run()

        des2 = DESEnvironment(config=config, seed=123)
        results2 = des2.run()

        np.testing.assert_array_equal(
            results1["daily_service_level"],
            results2["daily_service_level"],
        )

    def test_des_full_matrix_format(self):
        """DES handles full (n_warehouses+n_customers) matrix."""
        config = _small_config_legacy()
        n_total = config.network.n_warehouses + config.network.n_customers
        dist = np.random.default_rng(42).uniform(
            50, 500, size=(n_total, n_total)
        )
        des = DESEnvironment(
            config=config, distance_matrix=dist, seed=42
        )
        results = des.run()
        assert len(results["daily_service_level"]) == 60

    def test_des_cascade_to_second_warehouse(self):
        """When nearest warehouse is empty, DES fulfills from next nearest."""
        config = _small_config_legacy()
        # Use 2 warehouses with specific distances
        dist = np.array([
            [100.0, 200.0, 300.0, 400.0, 500.0, 600.0, 700.0, 800.0, 900.0, 1000.0],
            [500.0, 400.0, 300.0, 200.0, 100.0, 600.0, 700.0, 800.0, 900.0, 1000.0],
        ])
        des = DESEnvironment(config=config, distance_matrix=dist, seed=42)
        results = des.run()
        # With reasonable order sizes and 2 warehouses, should have some fulfillment
        # even if one warehouse runs low
        assert results["mean_service_level"] > 0.0

    def test_des_service_level_reasonable(self):
        """DES service level should be realistic, not degenerate."""
        config = _small_config_legacy()
        # Use very small warehouse capacities to create resource pressure
        # Daily replenishment = total_cap * 2.4 / 7 must be below demand
        config.network.warehouse_capacities = [1500.0, 1200.0]
        des = DESEnvironment(config=config, seed=42)
        results = des.run()
        sl = results["mean_service_level"]
        assert 0.3 < sl < 0.99, f"Service level {sl} is degenerate"

    def test_des_service_level_not_degenerate(self):
        """DES with default params gives non-degenerate service level."""
        config = _small_config_legacy()
        des = DESEnvironment(config=config, seed=42)
        results = des.run()
        sl = results["mean_service_level"]
        # Should not be 0% (system totally broken) or 100% always (trivial)
        assert sl > 0.0, f"Service level is 0 - system is broken"

    def test_des_baseline_service_level_healthy(self):
        """Full-scale DES with no shocks achieves ~95% service level."""
        config = MasterConfig(
            simulation=SimulationConfig(
                sim_days=60,
                warmup_days=10,
            ),
        )
        des = DESEnvironment(config=config, seed=42)
        results = des.run()
        sl = results["mean_service_level"]
        assert 0.92 <= sl <= 0.98, (
            f"Service level {sl:.4f} outside expected [0.92, 0.98] range"
        )


class TestSupplyShock:
    """Tests for SupplyShock class."""

    def test_supply_shock_applies(self):
        """Supply shock reduces warehouse capacity."""
        config = _small_config_legacy()
        des = DESEnvironment(config=config, seed=42)
        shock = SupplyShock(
            warehouse_id=0,
            severity=0.5,
            duration_range=(10, 10),
            start_day=5,
            seed=42,
        )
        des.add_shock(shock)
        results = des.run()
        # Shock should have been applied (simulation ran)
        assert results is not None
        assert shock.shock_start == 5

    def test_supply_shock_demand_multiplier(self):
        """Supply shock does not affect demand."""
        shock = SupplyShock(seed=42)
        assert shock.get_demand_multiplier(0, 50) == 1.0
        assert shock.get_demand_multiplier(5, 100) == 1.0

    def test_supply_shock_random_warehouse(self):
        """Supply shock selects random warehouse when not specified."""
        config = _small_config_legacy()
        des = DESEnvironment(config=config, seed=42)
        shock = SupplyShock(
            warehouse_id=None,
            severity=0.5,
            duration_range=(10, 20),
            start_day=5,
            seed=42,
        )
        des.add_shock(shock)
        des.run()
        assert shock._actual_warehouse is not None
        assert 0 <= shock._actual_warehouse < config.network.n_warehouses

    def test_supply_shock_drains_excess_inventory(self):
        """Supply shock drains inventory above effective capacity."""
        config = _small_config_legacy()
        des = DESEnvironment(config=config, seed=42)
        # Setup environment manually to test drain
        des.env = simpy.Environment()
        cap = config.network.warehouse_capacities[0]
        des.warehouses = [Warehouse(des.env, 0, cap, initial_level=cap * 0.9)]
        des.n_warehouses = 1
        des.warmup_days = 0
        des.sim_days = 10
        des.active_shocks = []

        # Create shock with severity 0.5 (50% capacity reduction)
        shock = SupplyShock(
            warehouse_id=0, severity=0.5,
            duration_range=(5, 5), start_day=1, seed=42,
        )
        des.add_shock(shock)

        # Run simulation
        des.env.process(shock.apply(des))
        des.env.run(until=3)  # Run past shock start

        # After shock, inventory should be <= effective capacity
        effective_cap = cap * 0.5
        assert des.warehouses[0].level <= effective_cap + 1.0


class TestDemandShockUnit:
    """Tests for DemandShock class (unit-level)."""

    def test_demand_shock_applies(self):
        """Demand shock increases demand for affected customers."""
        config = _small_config_legacy()
        des = DESEnvironment(config=config, seed=42)
        shock = DemandShockModel(
            customer_ids=[0, 1, 2],
            multiplier=3.0,
            duration_range=(10, 10),
            start_day=5,
            seed=42,
        )
        des.add_shock(shock)
        results = des.run()
        assert results is not None

    def test_demand_shock_multiplier_when_active(self):
        """Demand shock returns correct multiplier when active."""
        config = _small_config_legacy()
        des = DESEnvironment(config=config, seed=42)
        shock = DemandShockModel(
            customer_ids=[0, 1, 2],
            multiplier=3.0,
            duration_range=(10, 10),
            start_day=5,
            seed=42,
        )
        des.add_shock(shock)
        des.run()
        # After run, shock was active at some point
        assert shock.shock_start == 5

    def test_demand_shock_no_effect_unaffected_customer(self):
        """Demand shock does not affect unlisted customers."""
        shock = DemandShockModel(
            customer_ids=[0, 1, 2],
            multiplier=3.0,
            seed=42,
        )
        # Before activation, multiplier is 1.0
        assert shock.get_demand_multiplier(5, 100) == 1.0


class TestResilienceMetrics:
    """Tests for resilience metrics computation."""

    def test_tts_computation(self):
        """TTS correctly counts days above threshold."""
        metrics = ResilienceMetrics(service_level_threshold=0.90)
        # Service level drops below 0.9 on day 5 (index 5)
        sl = [0.95, 0.95, 0.94, 0.93, 0.92, 0.88, 0.85, 0.90, 0.95]
        tts = metrics.compute_tts(sl, shock_start_day=2)
        # Days 2,3,4 are above 0.9 -> TTS = 3
        assert tts == 3

    def test_tts_immediate_drop(self):
        """TTS is 0 when service drops immediately."""
        metrics = ResilienceMetrics(service_level_threshold=0.90)
        sl = [0.95, 0.95, 0.80, 0.85, 0.90]
        tts = metrics.compute_tts(sl, shock_start_day=2)
        assert tts == 0

    def test_tts_never_drops(self):
        """TTS equals remaining days when service never drops."""
        metrics = ResilienceMetrics(service_level_threshold=0.90)
        sl = [0.95, 0.95, 0.95, 0.95, 0.95]
        tts = metrics.compute_tts(sl, shock_start_day=1)
        assert tts == 4

    def test_ttr_computation(self):
        """TTR correctly measures recovery time."""
        metrics = ResilienceMetrics(recovery_threshold=0.95)
        # Pre-shock baseline ~0.95, recovers on day 7
        sl = [0.95, 0.95, 0.95, 0.80, 0.82, 0.85, 0.88, 0.92, 0.95]
        ttr = metrics.compute_ttr(
            sl, shock_end_day=5, pre_shock_baseline=0.95
        )
        # Recovery target = 0.95 * 0.95 = 0.9025
        # Day 5: 0.85 < target, Day 6: 0.88 < target,
        # Day 7: 0.92 >= target -> TTR = 2
        assert ttr == 2

    def test_ttr_never_recovers(self):
        """TTR returns -1 when system never recovers."""
        metrics = ResilienceMetrics(recovery_threshold=0.95)
        sl = [0.95, 0.95, 0.80, 0.80, 0.80, 0.80]
        ttr = metrics.compute_ttr(
            sl, shock_end_day=3, pre_shock_baseline=0.95
        )
        assert ttr == -1

    def test_ttr_normalized_basic(self):
        """TTR_normalized = TTR / shock_magnitude (Hosseini 2019 Sec. 4)."""
        metrics = ResilienceMetrics()
        # 10-day TTR under a 50% supply shock => 20 days/unit
        assert metrics.compute_ttr_normalized(10.0, 0.5) == 20.0
        # 6-day TTR under a 2.0x demand shock => 3 days/unit
        assert metrics.compute_ttr_normalized(6.0, 2.0) == 3.0

    def test_ttr_normalized_invalid_magnitude(self):
        """compute_ttr_normalized rejects non-positive shock magnitudes."""
        metrics = ResilienceMetrics()
        with pytest.raises(ValueError):
            metrics.compute_ttr_normalized(5.0, 0.0)
        with pytest.raises(ValueError):
            metrics.compute_ttr_normalized(5.0, -0.1)

    def test_max_drop_computation(self):
        """Max drop correctly identifies deepest decline."""
        metrics = ResilienceMetrics()
        sl = [0.95, 0.95, 0.90, 0.70, 0.75, 0.95]
        drop = metrics.compute_max_drop(
            sl, shock_start_day=2, shock_end_day=4
        )
        # Baseline = mean(0.95, 0.95) = 0.95
        # Min during shock = 0.70
        # Drop = 0.95 - 0.70 = 0.25
        assert abs(drop - 0.25) < 1e-10

    def test_cumulative_lost_demand(self):
        """Lost demand correctly sums unfulfilled orders."""
        metrics = ResilienceMetrics()
        orders = [100, 100, 100, 100, 100]
        fulfilled = [95, 95, 80, 70, 90]
        lost = metrics.compute_cumulative_lost_demand(
            orders, fulfilled, shock_start_day=2, shock_end_day=4
        )
        # Days 2-4: orders=300, fulfilled=80+70+90=240, lost=60
        assert lost == 60

    def test_recovery_trajectory(self):
        """Recovery trajectory extracts correct post-shock data."""
        metrics = ResilienceMetrics()
        sl = [0.95, 0.95, 0.80, 0.85, 0.90, 0.95, 0.96]
        trajectory = metrics.compute_recovery_trajectory(
            sl, shock_end_day=3, window=3
        )
        np.testing.assert_array_almost_equal(
            trajectory, [0.85, 0.90, 0.95]
        )

    def test_compute_all(self):
        """compute_all returns all expected metrics."""
        metrics = ResilienceMetrics()
        results = {
            "daily_service_level": np.array(
                [0.95] * 10 + [0.80, 0.75, 0.85] + [0.95] * 7
            ),
            "daily_orders": np.array([100] * 20),
            "daily_fulfilled": np.array(
                [95] * 10 + [80, 75, 85] + [95] * 7
            ),
        }
        out = metrics.compute_all(
            results, shock_start_day=10, shock_end_day=13
        )
        assert "tts" in out
        assert "ttr" in out
        assert "max_service_level_drop" in out
        assert "cumulative_lost_demand" in out
        assert "pre_shock_service_level" in out


class TestMonteCarloRunner:
    """Tests for Monte Carlo runner."""

    def test_monte_carlo_runs(self):
        """Monte Carlo runner completes without errors."""
        config = _small_config_legacy()
        runner = MonteCarloRunner(
            config=config,
            n_runs=3,
            n_jobs=1,
            base_seed=42,
        )
        results = runner.run_supply_shock_analysis()
        assert results["n_runs"] == 3
        assert "tts_mean" in results
        assert "ttr_mean" in results

    def test_monte_carlo_reproducibility(self):
        """Same seed produces same Monte Carlo results."""
        config = _small_config_legacy()
        runner1 = MonteCarloRunner(
            config=config, n_runs=3, n_jobs=1, base_seed=42
        )
        results1 = runner1.run_supply_shock_analysis()

        runner2 = MonteCarloRunner(
            config=config, n_runs=3, n_jobs=1, base_seed=42
        )
        results2 = runner2.run_supply_shock_analysis()

        assert results1["tts_mean"] == results2["tts_mean"]
        assert results1["ttr_mean"] == results2["ttr_mean"]

    def test_monte_carlo_demand_shock(self):
        """Monte Carlo demand shock analysis completes."""
        config = _small_config_legacy()
        runner = MonteCarloRunner(
            config=config, n_runs=3, n_jobs=1, base_seed=42
        )
        results = runner.run_demand_shock_analysis()
        assert results["n_runs"] == 3
        assert results["shock_type"] == "demand_shock"

    def test_monte_carlo_run_all(self):
        """run_all produces results for both shock types."""
        config = _small_config_legacy()
        runner = MonteCarloRunner(
            config=config, n_runs=2, n_jobs=1, base_seed=42
        )
        results = runner.run_all()
        assert "supply_shock" in results
        assert "demand_shock" in results
        assert results["supply_shock"]["n_runs"] == 2
        assert results["demand_shock"]["n_runs"] == 2

