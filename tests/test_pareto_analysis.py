"""Unit tests for pareto_analysis module — Audit 3.3."""

import numpy as np
import pytest

from supply_chain_research.phase1_foundation.pareto_analysis import (
    compute_hypervolume,
    compute_normalized_hypervolume,
)


class TestHVScaleSensitivity:
    """Catch the scale-sensitivity bug in raw HV computation (Audit 3.3)."""

    def test_normalized_hv_reflects_actual_quality(self):
        """Normalized HV correctly reflects per-objective changes."""
        front_a = np.array([
            [4.5e6, 50000.0],
            [5.0e6, 45000.0],
            [5.5e6, 40000.0],
        ])
        front_b = front_a * np.array([1.0, 1.05])  # 5% worse on carbon

        joint = np.vstack([front_a, front_b])
        ideal = joint.min(axis=0)
        nadir = joint.max(axis=0)

        hv_a = compute_normalized_hypervolume(
            front_a, ideal_point=ideal, nadir_point=nadir,
        )
        hv_b = compute_normalized_hypervolume(
            front_b, ideal_point=ideal, nadir_point=nadir,
        )

        # Front A is dominated by Front B on cost (equal) but better on carbon
        # so HV_a > HV_b
        assert hv_a > hv_b, f"HV_a={hv_a:.6f} should exceed HV_b={hv_b:.6f}"
        # Difference should be measurable
        assert (hv_a - hv_b) / hv_a > 0.01

    def test_normalized_hv_invariant_to_unit_change(self):
        """Multiplying an objective by a positive constant should not
        change the normalized HV (when ideal/nadir scale together).
        """
        front = np.array([
            [4.5e6, 50000.0],
            [5.0e6, 45000.0],
            [5.5e6, 40000.0],
        ])
        front_scaled = front * np.array([1.0, 1000.0])  # Carbon in grams

        # When ideal/nadir are derived from the same front, HV is invariant
        # because the front normalizes to identical [0,1] coordinates.
        hv1 = compute_normalized_hypervolume(front)
        hv2 = compute_normalized_hypervolume(front_scaled)

        assert abs(hv1 - hv2) < 1e-9, (
            f"Unit change broke normalization: hv1={hv1}, hv2={hv2}"
        )

    def test_compute_hypervolume_alias_uses_normalization(self):
        """compute_hypervolume() must produce the same result as
        compute_normalized_hypervolume() (Audit 3.3 fix wires the alias).
        """
        front = np.array([
            [4.5e6, 50000.0],
            [5.0e6, 45000.0],
            [5.5e6, 40000.0],
        ])
        hv_alias = compute_hypervolume(front)
        hv_norm = compute_normalized_hypervolume(front)
        assert abs(hv_alias - hv_norm) < 1e-9

    def test_hv_zero_for_empty_front(self):
        """Empty front returns 0.0."""
        assert compute_normalized_hypervolume(np.array([])) == 0.0
        assert compute_normalized_hypervolume(None) == 0.0

    def test_hv_handles_degenerate_objective(self):
        """Objective with zero range does not divide by zero."""
        front = np.array([
            [4.5e6, 100.0],
            [5.0e6, 100.0],
            [5.5e6, 100.0],
        ])
        hv = compute_normalized_hypervolume(front)
        assert np.isfinite(hv)
