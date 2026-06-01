"""Coverage tests for ``supply_chain_research.phase4_synthesis.managerial_insights``.

Validates the FIX-018 managerial-insights generator: artifact loaders,
section formatters, the public ``generate_managerial_insights`` entry
point, and the C3.12 preservation shims (``load_pareto_front``,
``load_des_results``, ``load_ppo_results``,
``compute_green_premium_curve``, ``compute_disruption_response``,
``identify_high_carbon_routes``, ``generate_insights_report``).

References
----------
[bugfix.md C2.12] Coverage clause for ``phase4_synthesis/managerial_insights.py``.
"""

from __future__ import annotations

import json
import pickle
from pathlib import Path
from typing import Any, Dict

import numpy as np
import pytest

from supply_chain_research.config import MasterConfig
from supply_chain_research.phase4_synthesis import managerial_insights as mi
from supply_chain_research.phase4_synthesis.managerial_insights import (
    MISSING_ARTIFACT_NOTE,
    _format_disruption_playbook,
    _format_executive_summary,
    _format_fleet_mix,
    _format_green_premium,
    _format_ppo_roi,
    _format_top_routes,
    _load_baseline_solution,
    _load_pareto_front,
    _load_ppo_eval,
    compute_disruption_response,
    compute_green_premium_curve,
    generate_insights_report,
    generate_managerial_insights,
    identify_high_carbon_routes,
    load_des_results,
    load_pareto_front,
    load_ppo_results,
)


# ---------------------------------------------------------------------------
# Synthetic-artifact builders
# ---------------------------------------------------------------------------


def _build_pareto_pkl(target: Path) -> np.ndarray:
    """Write a small synthetic Pareto-front pickle and return the array."""
    front = np.array(
        [[100.0, 5.0], [120.0, 4.0], [150.0, 3.0], [200.0, 2.0]],
        dtype=float,
    )
    target.write_bytes(pickle.dumps({"pareto_front": front}))
    return front


def _build_pareto_npy(target: Path) -> np.ndarray:
    """Write a small synthetic Pareto-front .npy file and return the array."""
    front = np.array([[100.0, 5.0], [200.0, 2.0]], dtype=float)
    np.save(target, front, allow_pickle=False)
    return front


def _build_baseline_pkl(target: Path) -> Dict[str, Any]:
    """Write a synthetic baseline-solution pickle."""
    payload = {"cost": 500.0, "carbon": 100.0, "routes": []}
    target.write_bytes(pickle.dumps(payload))
    return payload


def _build_ppo_summary_json(target: Path) -> Dict[str, Any]:
    """Write a synthetic PPO evaluation JSON file."""
    payload = {
        "cost": 450.0,
        "carbon": 90.0,
        "demand_surge": {
            "tts_baseline": 1.0,
            "tts_ppo": 2.5,
            "ttr_baseline": 7.0,
            "ttr_ppo": 4.0,
            "service_level_ppo": 0.95,
        },
    }
    target.write_text(json.dumps(payload), encoding="utf-8")
    return payload


def _build_monte_carlo_npy(target: Path) -> Dict[str, Any]:
    """Write a synthetic Monte-Carlo summary .npy (zero-D object array)."""
    summary = {
        "supply_shock": {
            "tts_mean": 2.0,
            "ttr_mean": 5.0,
            "max_drop_mean": 0.4,
            "mean_service_level_mean": 0.85,
            "n_runs": 20,
        },
    }
    np.save(target, np.array(summary, dtype=object), allow_pickle=True)
    return summary


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestPrivateLoaders:
    """Verify the private artifact loaders for the FIX-018 pipeline.

    Notes
    -----
    Each loader probes the canonical filename(s) for one artifact and
    falls back to ``None`` on missing / unreadable input. We exercise
    both branches.
    """

    def test_load_pareto_front_from_pickle(self, tmp_path: Path) -> None:
        # [bugfix.md C2.12] pickle path is preferred when present.
        front = _build_pareto_pkl(tmp_path / "nsga2_pareto.pkl")

        loaded = _load_pareto_front(tmp_path)

        assert loaded is not None
        np.testing.assert_array_equal(loaded, front)

    def test_load_pareto_front_from_npy(self, tmp_path: Path) -> None:
        # [bugfix.md C2.12] .npy fallback when no pickle is present.
        front = _build_pareto_npy(tmp_path / "nsga2_best_front.npy")

        loaded = _load_pareto_front(tmp_path)

        assert loaded is not None
        np.testing.assert_array_equal(loaded, front)

    def test_load_pareto_front_missing_returns_none(self, tmp_path: Path) -> None:
        # [bugfix.md C2.12] empty directory -> None (graceful degrade).
        assert _load_pareto_front(tmp_path) is None

    def test_load_baseline_solution(self, tmp_path: Path) -> None:
        # [bugfix.md C2.12] baseline pickle is parsed as a dict.
        payload = _build_baseline_pkl(tmp_path / "baseline_solution.pkl")

        loaded = _load_baseline_solution(tmp_path)
        assert loaded == payload

    def test_load_baseline_solution_missing_returns_none(
        self, tmp_path: Path,
    ) -> None:
        # [bugfix.md C2.12] absent file -> None.
        assert _load_baseline_solution(tmp_path) is None

    def test_load_ppo_eval_from_training_summary(self, tmp_path: Path) -> None:
        # [bugfix.md C2.12] legacy ``training_summary.json`` is supported.
        payload = _build_ppo_summary_json(tmp_path / "training_summary.json")

        loaded = _load_ppo_eval(tmp_path)
        assert loaded == payload

    def test_load_ppo_eval_missing_returns_none(self, tmp_path: Path) -> None:
        # [bugfix.md C2.12] absent file -> None.
        assert _load_ppo_eval(tmp_path) is None


class TestC3_12LoaderShims:
    """Verify the C3.12 preservation loader shims.

    Notes
    -----
    Each shim is a thin wrapper around a private loader; we verify
    the public signature accepts a ``str`` path and returns the
    documented type.
    """

    def test_load_pareto_front_shim(self, tmp_path: Path) -> None:
        # [bugfix.md C2.12] public shim accepts ``str`` and returns ndarray.
        front = _build_pareto_npy(tmp_path / "nsga2_best_front.npy")

        loaded = load_pareto_front(str(tmp_path))

        assert loaded is not None
        np.testing.assert_array_equal(loaded, front)
        # Absent dir -> None.
        assert load_pareto_front(str(tmp_path / "nope")) is None

    def test_load_des_results_from_monte_carlo_summary(
        self, tmp_path: Path,
    ) -> None:
        # [bugfix.md C2.12] DES shim parses the canonical npy artefact.
        summary = _build_monte_carlo_npy(tmp_path / "monte_carlo_summary.npy")

        loaded = load_des_results(str(tmp_path))
        assert loaded == summary

    def test_load_des_results_from_json_fallback(
        self, tmp_path: Path,
    ) -> None:
        # [bugfix.md C2.12] DES shim falls back to ``des_results.json``.
        payload = {"foo": "bar"}
        (tmp_path / "des_results.json").write_text(
            json.dumps(payload), encoding="utf-8",
        )

        assert load_des_results(str(tmp_path)) == payload

    def test_load_des_results_missing_returns_none(
        self, tmp_path: Path,
    ) -> None:
        # [bugfix.md C2.12] absent -> None.
        assert load_des_results(str(tmp_path)) is None

    def test_load_ppo_results_shim(self, tmp_path: Path) -> None:
        # [bugfix.md C2.12] PPO shim returns the parsed JSON dict.
        payload = _build_ppo_summary_json(tmp_path / "training_summary.json")

        assert load_ppo_results(str(tmp_path)) == payload


class TestSectionFormatters:
    """Verify each section formatter renders a markdown fragment.

    Notes
    -----
    Both the ``None`` (placeholder) and the synthetic-data branches
    are exercised so the missing-artefact note and the populated
    table paths both contribute to coverage.
    """

    def test_executive_summary_with_none_inputs(self) -> None:
        # [bugfix.md C2.12] formatter must not crash on all-None inputs.
        out = _format_executive_summary(None, None, None)
        assert "## Executive Summary" in out
        assert "0/3 sources populated" in out

    def test_executive_summary_with_data(self) -> None:
        # [bugfix.md C2.12] populated inputs are reflected in the summary.
        front = np.array([[1.0, 2.0]])
        out = _format_executive_summary(front, {"cost": 1.0}, {"reward": 0.5})
        assert "3/3 sources populated" in out

    def test_green_premium_with_none(self) -> None:
        # [bugfix.md C2.12] None front -> placeholder note.
        out = _format_green_premium(None)
        assert "## Green-Premium Curve" in out
        assert MISSING_ARTIFACT_NOTE in out

    def test_green_premium_with_data(self) -> None:
        # [bugfix.md C2.12] populated front -> tabular reduction levels.
        front = np.array(
            [[100.0, 5.0], [120.0, 4.0], [150.0, 3.0], [200.0, 2.0]],
        )
        out = _format_green_premium(front)
        assert "Reduction Target" in out
        assert " 10%" in out

    def test_fleet_mix_with_none(self) -> None:
        # [bugfix.md C2.12] None front -> placeholder note.
        cfg = MasterConfig()
        out = _format_fleet_mix(None, cfg)
        assert "## Fleet Mix Recommendation" in out
        assert MISSING_ARTIFACT_NOTE in out

    def test_fleet_mix_with_data(self) -> None:
        # [bugfix.md C2.12] populated front -> Pareto-anchored table.
        cfg = MasterConfig()
        front = np.array(
            [[100.0, 10.0], [200.0, 5.0], [400.0, 1.0]],
        )
        out = _format_fleet_mix(front, cfg)
        assert "Pareto-anchored fleet split" in out
        assert "Cost-optimal" in out

    def test_top_routes_with_none(self) -> None:
        # [bugfix.md C2.12] formatter ignores ``pareto_front`` and uses
        # ``config`` only; with default config the table is non-empty.
        cfg = MasterConfig()
        out = _format_top_routes(None, cfg)
        assert "## Top-5 Routes by Tonne-Km" in out
        assert "Tonne-Km" in out

    def test_disruption_playbook_with_none(self) -> None:
        # [bugfix.md C2.12] None ppo_eval -> placeholder note.
        out = _format_disruption_playbook(None)
        assert "## Disruption Playbook" in out
        assert MISSING_ARTIFACT_NOTE in out

    def test_disruption_playbook_with_data(self) -> None:
        # [bugfix.md C2.12] populated ppo_eval -> table rows.
        ppo = {
            "demand_surge": {
                "tts_baseline": 1.0,
                "tts_ppo": 2.5,
                "ttr_baseline": 7.0,
                "ttr_ppo": 4.0,
                "service_level_ppo": 0.95,
            },
        }
        out = _format_disruption_playbook(ppo)
        assert "Demand surge" in out
        assert "TTS baseline" in out

    def test_ppo_roi_with_none(self) -> None:
        # [bugfix.md C2.12] missing baseline -> placeholder note.
        out = _format_ppo_roi(None, None)
        assert "## PPO ROI" in out
        assert MISSING_ARTIFACT_NOTE in out

    def test_ppo_roi_with_data(self) -> None:
        # [bugfix.md C2.12] populated -> Δ % computed for cost / carbon.
        baseline = {"cost": 500.0, "carbon": 100.0}
        ppo = {"cost": 450.0, "carbon": 90.0}
        out = _format_ppo_roi(baseline, ppo)
        assert "## PPO ROI" in out
        assert "-10.0%" in out


class TestGenerateManagerialInsights:
    """Verify the public ``generate_managerial_insights`` orchestrator.

    Notes
    -----
    The output must contain all six section headers and must end with
    a single newline.
    """

    def test_produces_all_six_section_headers(self, tmp_path: Path) -> None:
        # [bugfix.md C2.12] all six documented sections must be present.
        # Build a fully-populated synthetic artifact directory.
        _build_pareto_pkl(tmp_path / "nsga2_pareto.pkl")
        _build_baseline_pkl(tmp_path / "baseline_solution.pkl")
        _build_ppo_summary_json(tmp_path / "training_summary.json")

        markdown = generate_managerial_insights(artifact_dir=tmp_path)

        for header in (
            "## Executive Summary",
            "## Green-Premium Curve",
            "## Fleet Mix Recommendation",
            "## Top-5 Routes by Tonne-Km",
            "## Disruption Playbook",
            "## PPO ROI",
        ):
            assert header in markdown, f"missing section: {header}"

        # Document title and trailing newline.
        assert markdown.startswith("# Managerial Insights")
        assert markdown.endswith("\n")

    def test_handles_missing_artifact_dir_gracefully(
        self, tmp_path: Path,
    ) -> None:
        # [bugfix.md C2.12] non-existent artifact dir falls back to the
        # documented placeholder for every section that needs data.
        markdown = generate_managerial_insights(
            artifact_dir=tmp_path / "nope",
        )

        assert "# Managerial Insights" in markdown
        assert MISSING_ARTIFACT_NOTE in markdown


class TestC3_12ComputeShims:
    """Verify ``compute_*`` C3.12 preservation shims.

    Notes
    -----
    The compute shims accept loaded artifacts and return the legacy
    list / dict shapes documented in the signature baseline.
    """

    def test_compute_green_premium_curve_with_none_returns_empty(self) -> None:
        # [bugfix.md C2.12] None / empty -> empty list.
        assert compute_green_premium_curve(None) == []
        assert compute_green_premium_curve(np.empty((0, 2))) == []

    def test_compute_green_premium_curve_returns_records(self) -> None:
        # [bugfix.md C2.12] populated front -> one record per reduction
        # band with the documented keys.
        front = np.array(
            [[100.0, 5.0], [200.0, 4.0], [400.0, 1.0]],
        )
        curve = compute_green_premium_curve(front)

        assert isinstance(curve, list)
        assert len(curve) == 6  # bands 0,10,20,30,40,50

        for record in curve:
            for key in (
                "reduction_pct", "min_cost",
                "delta_cost_vs_anchor", "premium_inr_per_kg_co2",
            ):
                assert key in record

    def test_compute_disruption_response_returns_summary(self) -> None:
        # [bugfix.md C2.12] disruption-response shim returns the
        # ``available / baseline / ppo`` shape.
        des = {"supply_shock": {"tts_mean": 1.0, "ttr_mean": 2.0,
                                "max_drop_mean": 0.5,
                                "mean_service_level_mean": 0.9,
                                "n_runs": 5}}
        ppo = {"demand_surge": {"tts_baseline": 1.0, "tts_ppo": 2.0,
                                 "ttr_baseline": 5.0, "ttr_ppo": 3.0,
                                 "service_level_ppo": 0.95}}

        out = compute_disruption_response(des, ppo)

        assert out["available"] == {"des": True, "ppo": True}
        assert "supply_shock" in out["baseline"]
        assert "demand_surge" in out["ppo"]

    def test_compute_disruption_response_with_none_inputs(self) -> None:
        # [bugfix.md C2.12] None inputs -> empty baseline / ppo dicts.
        out = compute_disruption_response(None, None)
        assert out["available"] == {"des": False, "ppo": False}
        assert out["baseline"] == {}
        assert out["ppo"] == {}

    def test_identify_high_carbon_routes_returns_top_k(self) -> None:
        # [bugfix.md C2.12] route ranking returns top-k records sorted
        # by carbon load (descending).
        cfg = MasterConfig()
        records = identify_high_carbon_routes(cfg, top_k=3)

        assert isinstance(records, list)
        assert len(records) == 3
        for r in records:
            for key in ("origin", "destination", "distance_km",
                        "tonne_km", "carbon_kg_per_route"):
                assert key in r
        # Descending order by carbon.
        carbons = [r["carbon_kg_per_route"] for r in records]
        assert carbons == sorted(carbons, reverse=True)

    def test_identify_high_carbon_routes_uses_distance_matrix(self) -> None:
        # [bugfix.md C2.12] explicit distance matrix overrides haversine.
        # The shim's shape check is ``(len(warehouses), len(cities))`` —
        # the city list (not the customer count) is the column axis.
        cfg = MasterConfig()
        n_w = len(cfg.network.warehouse_locations)
        n_cities = len(cfg.network.cities)
        dm = np.full((n_w, n_cities), 100.0)

        records = identify_high_carbon_routes(cfg, distance_matrix=dm, top_k=2)
        assert len(records) == 2
        for r in records:
            assert r["distance_km"] == pytest.approx(100.0)


class TestGenerateInsightsReportShim:
    """Verify the ``generate_insights_report`` C3.12 shim writes markdown.

    Notes
    -----
    The shim writes the rendered document to disk and also returns it
    in-band; we verify both surfaces.
    """

    def test_writes_markdown_to_disk_and_returns_summary(
        self, tmp_path: Path,
    ) -> None:
        # [bugfix.md C2.12] return dict carries the documented keys and
        # the file content matches.
        results_dir = tmp_path / "results"
        results_dir.mkdir()
        _build_pareto_pkl(results_dir / "nsga2_pareto.pkl")

        out_path = tmp_path / "out" / "insights.md"

        summary = generate_insights_report(
            output_path=str(out_path),
            results_dir=str(results_dir),
        )

        assert out_path.exists()
        for key in ("output_path", "results_dir", "length_chars", "markdown"):
            assert key in summary
        assert summary["length_chars"] == len(summary["markdown"])
        assert out_path.read_text(encoding="utf-8") == summary["markdown"]
