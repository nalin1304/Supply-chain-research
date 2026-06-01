"""Coverage tests for ``supply_chain_research.phase4_synthesis.complexity_analysis``.

Validates the FIX-017 wall-clock complexity-benchmark suite plus the
C3.12 preservation shims (``profile_nsga2``, ``profile_ppo_rollout``,
``profile_lstm_forward``, ``profile_des_simulation``,
``profile_distance_matrix``, ``run_complexity_analysis``).

To keep the per-suite wall-clock budget under control, the heavy
``run_complexity_benchmarks`` call is issued once at module scope and
its result is reused; the C3.12 shims are exercised by monkeypatching
the underlying benchmark function so each shim test is essentially
free (~ms).

References
----------
[bugfix.md C2.12] Coverage clause for ``phase4_synthesis/complexity_analysis.py``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import numpy as np
import pytest

from supply_chain_research.config import MasterConfig
from supply_chain_research.phase4_synthesis import complexity_analysis as ca
from supply_chain_research.phase4_synthesis.complexity_analysis import (
    _THEORETICAL_BIG_O,
    _measure,
    _resolve_config,
    dump_complexity_report,
    profile_des_simulation,
    profile_distance_matrix,
    profile_lstm_forward,
    profile_nsga2,
    profile_ppo_rollout,
    run_complexity_analysis,
    run_complexity_benchmarks,
)


@pytest.fixture(scope="module")
def benchmark_results() -> Dict[str, Any]:
    """Run ``run_complexity_benchmarks`` once and reuse the result.

    Returns
    -------
    dict
        Output of ``run_complexity_benchmarks(fast_mode=True)``.
    """
    return run_complexity_benchmarks(fast_mode=True)


class TestTheoreticalBigOConstants:
    """Verify documented big-O strings are present.

    Notes
    -----
    Downstream consumers (LaTeX-table generator, CI complexity check)
    rely on the canonical algorithm keys.
    """

    def test_all_five_algorithms_have_big_o_string(self) -> None:
        # [bugfix.md C2.12] every algorithm has a documented big-O label.
        for key in ("nsga2", "moead", "des", "lstm_forward", "ppo_update"):
            assert key in _THEORETICAL_BIG_O
            assert isinstance(_THEORETICAL_BIG_O[key], str)
            assert _THEORETICAL_BIG_O[key]


class TestResolveConfig:
    """Verify ``_resolve_config`` returns a non-None MasterConfig.

    Notes
    -----
    The helper is the entry point that lets every benchmark accept an
    optional config; tests verify both the None-fallback and
    pass-through branches.
    """

    def test_none_input_returns_default_config(self) -> None:
        # [bugfix.md C2.12] None -> fresh MasterConfig instance.
        cfg = _resolve_config(None)
        assert isinstance(cfg, MasterConfig)

    def test_explicit_input_is_returned_unchanged(self) -> None:
        # [bugfix.md C2.12] explicit config is returned by reference.
        explicit = MasterConfig()
        result = _resolve_config(explicit)
        assert result is explicit


class TestMeasure:
    """Verify ``_measure`` produces the documented timing dictionary.

    Notes
    -----
    All timings come from ``time.perf_counter`` — a monotonic clock —
    so ``min <= mean`` always holds.
    """

    def test_measure_returns_documented_keys(self) -> None:
        # [bugfix.md C2.12] dict shape contract.
        timing = _measure(lambda: None, repetitions=3)

        for key in (
            "wall_seconds", "wall_seconds_min",
            "wall_seconds_mean", "wall_seconds_repetitions",
        ):
            assert key in timing

        assert timing["wall_seconds_repetitions"] == 3

    def test_measure_min_le_mean(self) -> None:
        # [bugfix.md C2.12] monotonic-clock invariant: min <= mean.
        timing = _measure(lambda: sum(range(100)), repetitions=4)
        assert timing["wall_seconds_min"] <= timing["wall_seconds_mean"]
        assert timing["wall_seconds"] == timing["wall_seconds_min"]

    def test_measure_zero_repetitions_raises(self) -> None:
        # [bugfix.md C2.12] guard clause requires repetitions >= 1.
        with pytest.raises(ValueError, match="repetitions must be >= 1"):
            _measure(lambda: None, repetitions=0)


class TestRunComplexityBenchmarks:
    """Verify ``run_complexity_benchmarks`` returns the documented schema.

    Notes
    -----
    Heavy benchmark; reuses the module-scoped fixture so it runs once.
    """

    def test_metadata_block_keys(
        self, benchmark_results: Dict[str, Any],
    ) -> None:
        # [bugfix.md C2.12] metadata block carries every documented field.
        meta = benchmark_results["metadata"]
        for key in (
            "fast_mode", "random_seed", "platform",
            "python_version", "numpy_version", "timestamp_iso",
        ):
            assert key in meta

        assert meta["fast_mode"] is True

    def test_each_algorithm_block_has_required_fields(
        self, benchmark_results: Dict[str, Any],
    ) -> None:
        # [bugfix.md C2.12] each algorithm block must carry wall-clock,
        # big-O label, and complexity-constant estimate; ``skipped=True``
        # is tolerated for any algorithm whose dependencies are missing.
        for algo in ("nsga2", "moead", "des", "lstm_forward", "ppo_update"):
            block = benchmark_results[algo]
            assert isinstance(block, dict)
            assert "wall_seconds" in block
            assert "theoretical_big_o" in block
            assert "complexity_constant_estimate" in block
            assert "wall_seconds_repetitions" in block
            # Either a real benchmark ran or it was skipped with a reason.
            if block.get("skipped"):
                assert "skip_reason" in block


class TestDumpComplexityReport:
    """Verify ``dump_complexity_report`` writes a parseable JSON file.

    Notes
    -----
    Uses tmp_path so the test is hermetic and never touches
    ``audit_workspace/`` on disk.
    """

    def test_dump_report_writes_valid_json(
        self, tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        benchmark_results: Dict[str, Any],
    ) -> None:
        # [bugfix.md C2.12] file is written + decoded JSON is identical
        # to the returned dict. We monkeypatch ``run_complexity_benchmarks``
        # so the test reuses the cached result without re-running the
        # full suite.
        monkeypatch.setattr(
            ca, "run_complexity_benchmarks",
            lambda config=None, fast_mode=True: benchmark_results,
        )
        out_path = tmp_path / "deep" / "report.json"

        result = dump_complexity_report(out_path=str(out_path), fast_mode=True)

        assert out_path.exists()
        decoded = json.loads(out_path.read_text(encoding="utf-8"))
        assert "metadata" in decoded
        assert decoded["metadata"]["fast_mode"] is True
        assert "nsga2" in decoded
        assert isinstance(result, dict)


class TestC3_12ProfileShims:
    """Verify the C3.12 profile_* shims expose ``Dict[str, float]`` shape.

    Notes
    -----
    The shims internally call ``run_complexity_benchmarks``; we
    monkeypatch the latter so each shim test is essentially free.
    """

    def _patch_with_cache(
        self,
        monkeypatch: pytest.MonkeyPatch,
        cached: Dict[str, Any],
    ) -> None:
        # Helper: route the shim's benchmark call to the cached result.
        monkeypatch.setattr(
            ca, "run_complexity_benchmarks",
            lambda config=None, fast_mode=True: cached,
        )

    def test_profile_nsga2_returns_dict_str_float(
        self,
        monkeypatch: pytest.MonkeyPatch,
        benchmark_results: Dict[str, Any],
    ) -> None:
        # [bugfix.md C2.12] legacy public shape: Dict[str, float].
        self._patch_with_cache(monkeypatch, benchmark_results)
        cfg = MasterConfig()

        out = profile_nsga2(cfg)

        assert isinstance(out, dict)
        for key, value in out.items():
            assert isinstance(key, str)
            assert isinstance(value, float)
        assert "wall_seconds" in out

    def test_profile_ppo_rollout_returns_dict_str_float(
        self,
        monkeypatch: pytest.MonkeyPatch,
        benchmark_results: Dict[str, Any],
    ) -> None:
        # [bugfix.md C2.12] PPO shim shape contract.
        self._patch_with_cache(monkeypatch, benchmark_results)
        out = profile_ppo_rollout(MasterConfig())

        assert isinstance(out, dict)
        for value in out.values():
            assert isinstance(value, float)

    def test_profile_lstm_forward_returns_dict_str_float(
        self,
        monkeypatch: pytest.MonkeyPatch,
        benchmark_results: Dict[str, Any],
    ) -> None:
        # [bugfix.md C2.12] LSTM shim shape contract.
        self._patch_with_cache(monkeypatch, benchmark_results)
        out = profile_lstm_forward(MasterConfig())

        assert isinstance(out, dict)
        for value in out.values():
            assert isinstance(value, float)

    def test_profile_des_simulation_returns_dict_str_float(
        self,
        monkeypatch: pytest.MonkeyPatch,
        benchmark_results: Dict[str, Any],
    ) -> None:
        # [bugfix.md C2.12] DES shim shape contract.
        self._patch_with_cache(monkeypatch, benchmark_results)
        out = profile_des_simulation(MasterConfig())

        assert isinstance(out, dict)
        for value in out.values():
            assert isinstance(value, float)

    def test_profile_distance_matrix_returns_skipped_stub(self) -> None:
        # [bugfix.md C2.12] distance-matrix shim is a documented stub
        # whose ``skipped`` flag is set to 1.0 (no benchmark performed).
        out = profile_distance_matrix(MasterConfig())

        assert isinstance(out, dict)
        assert out["skipped"] == 1.0
        assert np.isnan(out["wall_seconds"])
        for value in out.values():
            assert isinstance(value, float)


class TestRunComplexityAnalysisShim:
    """Verify ``run_complexity_analysis`` returns ``List[Dict[str, Any]]``.

    Notes
    -----
    ``run_complexity_analysis`` writes the JSON report and returns the
    legacy list-of-records shape. We monkeypatch ``dump_complexity_report``
    so the test only exercises the reshape logic.
    """

    def test_returns_one_record_per_algorithm(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        benchmark_results: Dict[str, Any],
    ) -> None:
        # [bugfix.md C2.12] legacy shape: List[Dict[str, Any]] with one
        # record per benchmarked algorithm and an ``algorithm`` key.
        out_path = tmp_path / "complexity.json"

        def fake_dump(out_path, config=None, fast_mode=True):
            # Mirror real behaviour: write the cached results, then return.
            Path(out_path).parent.mkdir(parents=True, exist_ok=True)
            Path(out_path).write_text(
                json.dumps(benchmark_results, default=str), encoding="utf-8",
            )
            return benchmark_results

        monkeypatch.setattr(ca, "dump_complexity_report", fake_dump)

        records = run_complexity_analysis(output_path=str(out_path))

        assert isinstance(records, list)
        algos = {rec["algorithm"] for rec in records}
        # All five algorithms produce a record (skipped or not).
        assert algos == {"nsga2", "moead", "des", "lstm_forward", "ppo_update"}

        for rec in records:
            assert isinstance(rec, dict)
            assert "algorithm" in rec
            # Every record carries the canonical keys from the inner block.
            assert "theoretical_big_o" in rec
            assert "wall_seconds" in rec
