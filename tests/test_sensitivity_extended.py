"""Unit tests for the extended sensitivity analysis layer (Phase 5)."""

import pytest
import numpy as np

from supply_chain_research.config import MasterConfig, SensitivityConfig
from supply_chain_research.phase4_synthesis import sensitivity_analysis as sa


@pytest.fixture
def test_setup():
    cfg = MasterConfig()
    cfg.sensitivity = SensitivityConfig(
        fast_mode=True,
        fast_n_samples=2,  # Keep base N very small for CI
        fast_pop_size=10,
        fast_n_gen=2,
        instance_n_warehouses=2,
        instance_n_customers=3,
    )
    return cfg


def test_extended_morris(test_setup):
    cfg = test_setup
    res = sa.run_extended_sensitivity_analysis(
        config=cfg,
        method="morris",
        n_samples=2,
        seed=42,
        fast_mode=True,
    )
    assert res["method"] == "morris"
    assert "mu_star" in res
    assert "sigma" in res
    assert len(res["names"]) == 22


def test_extended_fast(test_setup):
    cfg = test_setup
    res = sa.run_extended_sensitivity_analysis(
        config=cfg,
        method="fast",
        n_samples=2,
        seed=42,
        fast_mode=True,
    )
    assert res["method"] == "fast"
    assert "first_order" in res
    assert len(res["names"]) == 22


def test_extended_pawn(test_setup):
    cfg = test_setup
    res = sa.run_extended_sensitivity_analysis(
        config=cfg,
        method="pawn",
        n_samples=2,
        seed=42,
        fast_mode=True,
    )
    assert res["method"] == "pawn"
    assert "pawn_median" in res
    assert len(res["names"]) == 22
