"""Unit tests for the expanded resilience and disruption layer (Phase 4)."""

import pytest
import numpy as np

from supply_chain_research.config import MasterConfig
from supply_chain_research.phase2_resilience.des_environment import DESEnvironment
from supply_chain_research.phase2_resilience.shock_models import (
    Cyberattack,
    LaborStrike,
    RawMaterialShortage,
    TransportInfrastructure,
    RegulatoryChange,
    PowerOutage,
)
from supply_chain_research.phase2_resilience.compound_disruption import CompoundDisruption
from supply_chain_research.phase2_resilience.recovery_strategies import (
    CapacitySharing,
    BackupSupplier,
)
from supply_chain_research.phase2_resilience.resilience_metrics import ResilienceMetrics
from supply_chain_research.phase2_resilience.monte_carlo_runner import MonteCarloRunner


@pytest.fixture
def base_setup():
    config = MasterConfig()
    config.network.n_customers = 5
    config.network.n_warehouses = 2
    config.simulation.sim_days = 20
    config.simulation.warmup_days = 2
    return config


def test_cyberattack(base_setup):
    config = base_setup
    des = DESEnvironment(config=config, seed=42)
    shock = Cyberattack(warehouse_ids=[0], severity=0.8, detection_time=2, recovery_time=4, start_day=5, seed=42)
    des.add_shock(shock)
    res = des.run()
    assert res["mean_service_level"] > 0
    
    # Compute resilience metrics explicitly
    calc = ResilienceMetrics()
    metrics = calc.compute_all(res, shock.shock_start, shock.shock_end)
    assert "network_resilience_index" in metrics
    assert "economic_resilience" in metrics
    assert "adaptive_capacity" in metrics
    assert "vulnerability_index" in metrics
    assert "robustness_coefficient" in metrics
    assert "recovery_cost_ratio" in metrics


def test_labor_strike(base_setup):
    config = base_setup
    des = DESEnvironment(config=config, seed=42)
    shock = LaborStrike(warehouse_ids=[0], severity=0.7, duration_range=(5, 10), start_day=5, seed=42)
    des.add_shock(shock)
    res = des.run()
    assert res["mean_service_level"] > 0


def test_raw_material_shortage(base_setup):
    config = base_setup
    des = DESEnvironment(config=config, seed=42)
    shock = RawMaterialShortage(shortage_severity=0.6, price_multiplier=1.5, start_day=5, seed=42)
    des.add_shock(shock)
    res = des.run()
    assert res["mean_service_level"] > 0


def test_transport_infrastructure(base_setup):
    config = base_setup
    des = DESEnvironment(config=config, seed=42)
    shock = TransportInfrastructure(detour_factor=1.3, repair_time=5, start_day=5, seed=42)
    des.add_shock(shock)
    res = des.run()
    assert res["mean_service_level"] > 0


def test_regulatory_change(base_setup):
    config = base_setup
    des = DESEnvironment(config=config, seed=42)
    shock = RegulatoryChange(compliance_cost=2000.0, implementation_lead_time=2, duration_range=(5, 10), start_day=5, seed=42)
    des.add_shock(shock)
    res = des.run()
    assert res["mean_service_level"] > 0


def test_power_outage(base_setup):
    config = base_setup
    des = DESEnvironment(config=config, seed=42)
    shock = PowerOutage(outage_duration=3, spoilage_rate=0.1, backup_power_prob=0.0, start_day=5, seed=42)
    des.add_shock(shock)
    res = des.run()
    assert res["mean_service_level"] > 0


def test_compound_disruption(base_setup):
    config = base_setup
    des = DESEnvironment(config=config, seed=42)
    s1 = Cyberattack(warehouse_ids=[0], severity=0.8, detection_time=2, recovery_time=4, start_day=5, seed=42)
    s2 = PowerOutage(outage_duration=3, spoilage_rate=0.1, backup_power_prob=0.0, start_day=7, seed=42)
    
    comp = CompoundDisruption(shocks=[s1, s2], simultaneous=True, seed=42)
    des.add_shock(comp)
    res = des.run()
    assert res["mean_service_level"] > 0


def test_recovery_strategies(base_setup):
    config = base_setup
    
    # 1. Capacity Sharing
    des = DESEnvironment(config=config, seed=42)
    shock = Cyberattack(warehouse_ids=[0], severity=0.8, detection_time=2, recovery_time=4, start_day=5, seed=42)
    des.add_shock(shock)
    strategy = CapacitySharing(transfer_threshold_pct=0.3, transfer_amount=1000.0)
    des.env = des.env if hasattr(des, "env") else None  # run will set env
    # In run(), we can't easily register a recovery strategy SimPy process, but we can register it as an active_shocks item!
    # Because RecoveryStrategy implements apply(des_env) which yields timeouts, it is structurally equivalent to a shock!
    des.add_shock(strategy)
    res = des.run()
    assert res["mean_service_level"] > 0

    # 2. Backup Supplier
    des = DESEnvironment(config=config, seed=42)
    shock = Cyberattack(warehouse_ids=[0], severity=0.8, detection_time=2, recovery_time=4, start_day=5, seed=42)
    des.add_shock(shock)
    backup = BackupSupplier(trigger_level_pct=0.2, backup_boost_factor=1.5)
    des.add_shock(backup)
    res = des.run()
    assert res["mean_service_level"] > 0


def test_monte_carlo_lhs_and_stress_testing(base_setup):
    config = base_setup
    runner = MonteCarloRunner(config=config, n_runs=5, n_jobs=1, base_seed=42)
    
    # Run Monte Carlo supply shock with LHS
    supply_res = runner.run_supply_shock_analysis(lhs=True)
    assert supply_res["n_runs"] == 5
    assert "convergence_diagnostics" in supply_res
    assert "network_resilience_index" in supply_res["raw_results"][0]

    # Run Stress Testing sweep
    stress_res = runner.run_stress_testing_framework(severities=[0.2, 0.5, 0.8], n_runs=2)
    assert len(stress_res) == 3
    assert 0.5 in stress_res
    assert "nri_mean" in stress_res[0.5]
