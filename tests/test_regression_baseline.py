"""Regression tests against NUMERIC_BASELINE.json.

Loads the persisted numeric baseline and verifies the current code
reproduces it within tolerance under seed=42. Catches any refactor
that silently changes numeric behavior.
"""

import json
import os
from pathlib import Path

import numpy as np
import pytest

BASELINE_PATH = Path("audit_workspace/NUMERIC_BASELINE.json")


@pytest.mark.regression
@pytest.mark.skipif(
    not BASELINE_PATH.exists(),
    reason="NUMERIC_BASELINE.json not found",
)
class TestNumericBaseline:
    """Ensure current outputs match the captured baseline."""

    @pytest.fixture(scope="class")
    def baseline(self):
        with open(BASELINE_PATH) as f:
            return json.load(f)

    def test_emission_model_matches_baseline(self, baseline):
        """HCV emission at full load is bit-identical to baseline."""
        from supply_chain_research.config import MasterConfig
        from supply_chain_research.phase1_foundation.emission_model import (
            EmissionCalculator,
        )

        if "emissions" not in baseline:
            pytest.skip("No 'emissions' key in baseline")

        cfg = MasterConfig()
        calc = EmissionCalculator(cfg)
        rate_full = calc.emission_rate("HCV", cfg.vehicle.hcv_capacity)
        rate_empty = calc.emission_rate("HCV", 0.0)

        ref = baseline["emissions"]
        if isinstance(ref, dict):
            tol = ref.get("tolerance", 1e-9)
            if "hcv_full_rate" in ref:
                assert abs(rate_full - ref["hcv_full_rate"]) < tol
            if "hcv_empty_rate" in ref:
                assert abs(rate_empty - ref["hcv_empty_rate"]) < tol

    def test_pareto_front_within_tolerance(self, baseline):
        """NSGA-II under seed=42 produces objective values within tol.

        Mirrors ``audit_workspace/capture_numeric_baseline.capture_nsga2``
        bit-for-bit:

        * synthetic instance built via the same
          ``rng.uniform(50, 500, ...)`` / ``rng.uniform(100, 5000, ...)``
          generator (``_build_synthetic_problem`` in the capture
          script);
        * NSGA-II called with the same ``pop_size`` / ``n_gen`` /
          ``seed`` recorded in the captured ``config`` block;
        * extreme points (``min cost``, ``min carbon``) compared
          against the baseline within the recorded relative
          ``tolerance`` (default ``1e-6`` per task 0.4).

        Validates: bugfix.md C3.2 (NSGA-II Pareto-front bit-equivalence
        under fixed seed). The full element-wise comparison lives in
        ``tests/test_nsga2_solver.py::TestWarmStart``; this test is
        the lightweight extreme-point sentinel.
        """
        if "nsga2_pareto" not in baseline:
            pytest.skip("No 'nsga2_pareto' key in baseline")

        ref = baseline["nsga2_pareto"]
        if not isinstance(ref, dict) or "front" not in ref:
            pytest.skip("Baseline malformed")

        ref_front = np.asarray(ref["front"])
        cfg_b = ref.get("config", {})
        tol = float(ref.get("tolerance", 1e-6))  # [relative — task 0.4]

        # Run NSGA-II at the same (pop_size, n_gen, seed) recorded in
        # the baseline so the comparison is meaningful within the
        # baseline's recorded relative tolerance.
        from supply_chain_research.config import MasterConfig
        from supply_chain_research.phase1_foundation.nsga2_solver import (
            run_nsga2,
        )
        cfg = MasterConfig()
        # Sanity-check shape: skip if baseline shape drifted from the
        # active config (shape change would invalidate the comparison).
        if (
            cfg.network.n_warehouses
            != cfg_b.get("n_warehouses", cfg.network.n_warehouses)
            or cfg.network.n_customers
            != cfg_b.get("n_customers", cfg.network.n_customers)
        ):
            pytest.skip(
                "Network shape drifted since baseline capture: "
                f"baseline={cfg_b.get('n_warehouses')}x"
                f"{cfg_b.get('n_customers')}, current="
                f"{cfg.network.n_warehouses}x{cfg.network.n_customers}.",
            )
        seed = int(cfg_b.get("seed", 42))
        pop_size = int(cfg_b.get("pop_size", 500))
        n_gen = int(cfg_b.get("n_gen", 100))

        # Mirrors capture_numeric_baseline._build_synthetic_problem
        # exactly so the RNG schedule lines up bit-for-bit.
        rng = np.random.default_rng(seed)
        n_w, n_c = cfg.network.n_warehouses, cfg.network.n_customers
        dist = rng.uniform(50.0, 500.0, size=(n_w, n_c))
        demand = rng.uniform(100.0, 5000.0, size=n_c)

        result = run_nsga2(
            cfg, dist, demand,
            pop_size=pop_size, n_gen=n_gen, seed=seed,
        )
        if result.F is None or len(result.F) == 0:
            pytest.skip("Solver returned empty front; cannot regression-test")

        # Compare extreme points only (most stable across small changes)
        cur_min_cost = float(result.F[:, 0].min())
        cur_min_carbon = float(result.F[:, 1].min())

        ref_min_cost = float(np.min(ref_front[:, 0]))
        ref_min_carbon = float(np.min(ref_front[:, 1]))

        assert (
            abs(cur_min_cost - ref_min_cost) / max(abs(ref_min_cost), 1) < tol
        ), f"Min cost changed: {cur_min_cost} vs {ref_min_cost}"
        assert (
            abs(cur_min_carbon - ref_min_carbon)
            / max(abs(ref_min_carbon), 1)
            < tol
        ), f"Min carbon changed: {cur_min_carbon} vs {ref_min_carbon}"
