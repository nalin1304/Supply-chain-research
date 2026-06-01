"""Cross-asset consistency tests for the manuscript.

After FIX-024 every quantitative claim in the paper should trace
back to a single source-of-truth file in ``data/results/``. This test
suite asserts that:

  1. The headline numbers in ``training_summary.json`` are present
     and finite (not the post-skip ``0.0`` placeholder regression).
  2. The 3-method method-comparison numbers in
     ``outputs/tables/table2_algorithm_comparison.tex`` match the
     hypervolumes in ``training_summary.json``.
  3. The Friedman / Wilcoxon p-values in
     ``outputs/tables/table3_statistical_tests.tex`` match
     ``statistical_tests.json`` to four decimal places.
  4. The (R, s, S) and random baseline rewards in
     ``ppo_baselines.json`` match those quoted in
     ``docs/MANAGERIAL_INSIGHTS.md`` and
     ``docs/MENTOR_REPORT.md``.
  5. The Friedman / Wilcoxon p-values in
     ``statistical_tests.json`` are actually below 0.05
     (the threshold the manuscript discussion relies on).

The intent is to catch any future regression where one asset is
regenerated and another is forgotten — the kind of silent drift the
FIX-024 fix-class was originally introduced to prevent.

These tests SKIP gracefully when the result files are absent so that
a fresh CI checkout without ``data/results/`` does not fail; they
only enforce consistency when the artefacts exist.
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path

import pytest


_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_RESULTS_DIR = _PROJECT_ROOT / "data" / "results"
_TABLES_DIR = _PROJECT_ROOT / "outputs" / "tables"
_DOCS_DIR = _PROJECT_ROOT / "docs"

_TRAINING_SUMMARY = _RESULTS_DIR / "training_summary.json"
_STATS_TESTS = _RESULTS_DIR / "statistical_tests.json"
_PPO_BASELINES = _RESULTS_DIR / "ppo_baselines.json"

_TABLE2_TEX = _TABLES_DIR / "table2_algorithm_comparison.tex"
_TABLE3_TEX = _TABLES_DIR / "table3_statistical_tests.tex"

_MANAGERIAL_MD = _DOCS_DIR / "MANAGERIAL_INSIGHTS.md"
_MENTOR_MD = _DOCS_DIR / "MENTOR_REPORT.md"

_FIG9_GREEN_PREMIUM = (
    _PROJECT_ROOT / "outputs" / "figures" / "fig9_green_premium_curve.png"
)

_TABLE1_LITERATURE = _TABLES_DIR / "table1_literature_comparison.tex"


def _skip_if_missing(*paths: Path) -> None:
    """pytest.skip if any required artefact is absent."""
    missing = [str(p.relative_to(_PROJECT_ROOT)) for p in paths if not p.exists()]
    if missing:
        pytest.skip(
            "Required artefact(s) absent (run training + paper-assets first): "
            + ", ".join(missing)
        )


def _approx_in_text(value: float, text: str, tolerance: float = 0.001) -> bool:
    """True if a number close to ``value`` appears anywhere in ``text``.

    Looks for both bare-decimal, comma-thousands, and space-thousands
    variants (the docs use space-separators per typographic convention).
    Used for cross-checking against narrative markdown which sometimes
    rounds to an extra decimal place vs the JSON.
    """
    if not math.isfinite(value):
        return False
    candidates = [
        f"{value:.3f}",
        f"{value:.4f}",
        f"{value:,.0f}",
        f"{value:.0f}",
        f"{value:.2%}",
        # Space-thousands separator variants (docs typography).
        f"{value:,.0f}".replace(",", " "),
        f"{value:,.0f}".replace(",", "\u202f"),  # narrow no-break space
    ]
    if any(c in text for c in candidates):
        return True
    # Float-tolerance scan over every numeric token in the text,
    # including space-separated ones like "-63 908".
    nums = re.findall(
        r"-?\d{1,3}(?:[,\u202f ]\d{3})*(?:\.\d+)?|-?\d+(?:\.\d+)?", text
    )
    for token in nums:
        cleaned = token.replace(",", "").replace(" ", "").replace("\u202f", "")
        try:
            v = float(cleaned)
        except ValueError:
            continue
        if value != 0:
            if abs(v - value) / max(abs(value), 1e-9) <= tolerance:
                return True
        else:
            if abs(v) <= tolerance:
                return True
    return False


# --------------------------------------------------------------
# 1. training_summary.json finite-and-present
# --------------------------------------------------------------

def test_training_summary_lstm_metrics_are_finite() -> None:
    """LSTM MAPE and RMSE in training_summary.json must be > 0 (FIX-024)."""
    _skip_if_missing(_TRAINING_SUMMARY)
    summary = json.loads(_TRAINING_SUMMARY.read_text())
    lstm = summary.get("lstm", {})
    mape = lstm.get("mape", 0.0)
    rmse = lstm.get("rmse", 0.0)
    assert mape > 0.0, (
        "training_summary.json LSTM MAPE is 0.0 — the FIX-024 cache-recompute "
        "regressed. Run `python -m supply_chain_research.phase4_synthesis."
        "generate_all_figures` or fix the skip-branch in modal_train.py."
    )
    assert rmse > 0.0, "training_summary.json LSTM RMSE is 0.0 (same as MAPE issue)."


def test_training_summary_required_keys() -> None:
    """training_summary.json carries every key the manuscript cites."""
    _skip_if_missing(_TRAINING_SUMMARY)
    summary = json.loads(_TRAINING_SUMMARY.read_text())
    for key in ["nsga2", "nsga3", "moead", "lstm", "ppo_small", "ppo_full",
                "baselines", "des"]:
        assert key in summary, f"training_summary.json missing key: {key}"


# --------------------------------------------------------------
# 2. Table 2 numbers match training_summary.json
# --------------------------------------------------------------

def test_table2_hypervolumes_match_training_summary() -> None:
    """Table 2 HV cells must match training_summary.json mean_hv."""
    _skip_if_missing(_TRAINING_SUMMARY, _TABLE2_TEX)
    summary = json.loads(_TRAINING_SUMMARY.read_text())
    tex = _TABLE2_TEX.read_text()

    nsga2_hv = summary["nsga2"]["mean_hv"]
    moead_hv = summary["moead"]["mean_hv"]
    nsga3_hv = summary["nsga3"]["mean_hv"]

    # Tables format to 3 decimal places; JSON values may be longer
    assert _approx_in_text(nsga2_hv, tex, 0.005), (
        f"Table 2 does not contain NSGA-II HV ≈ {nsga2_hv:.3f}"
    )
    assert _approx_in_text(moead_hv, tex, 0.005), (
        f"Table 2 does not contain MOEA/D HV ≈ {moead_hv:.3f}"
    )
    assert _approx_in_text(nsga3_hv, tex, 0.005), (
        f"Table 2 does not contain NSGA-III HV ≈ {nsga3_hv:.3f}"
    )


# --------------------------------------------------------------
# 3. Table 3 stat tests match statistical_tests.json
# --------------------------------------------------------------

def test_table3_friedman_p_matches_stats_json() -> None:
    """Table 3 Friedman p-value is the same as statistical_tests.json."""
    _skip_if_missing(_STATS_TESTS, _TABLE3_TEX)
    stats = json.loads(_STATS_TESTS.read_text())
    tex = _TABLE3_TEX.read_text()
    friedman_p = stats["friedman"]["p"]
    # Tables format to 4 decimal places.
    expected = f"{friedman_p:.4f}"
    assert expected in tex, (
        f"Table 3 missing Friedman p={expected} (JSON has p={friedman_p}). "
        "Either Table 3 is stale or statistical_tests.json is stale."
    )


def test_table3_wilcoxon_p_matches_stats_json() -> None:
    """Table 3 Wilcoxon p-value is the same as statistical_tests.json."""
    _skip_if_missing(_STATS_TESTS, _TABLE3_TEX)
    stats = json.loads(_STATS_TESTS.read_text())
    tex = _TABLE3_TEX.read_text()
    wp = stats["wilcoxon_nsga2_moead"]["p"]
    expected = f"{wp:.4f}"
    assert expected in tex, (
        f"Table 3 missing Wilcoxon p={expected} (JSON has p={wp}). "
        "Either Table 3 is stale or statistical_tests.json is stale."
    )


# --------------------------------------------------------------
# 4. Baselines in ppo_baselines.json appear in narrative docs
# --------------------------------------------------------------

def test_managerial_md_quotes_ppo_baselines() -> None:
    """MANAGERIAL_INSIGHTS.md references the (R, s, S) and random rewards.

    A loose check — values that round to the same major significant
    figures must appear in the doc. Catches the FIX-024-class issue
    where a doc is regenerated against stale numbers.
    """
    _skip_if_missing(_PPO_BASELINES, _MANAGERIAL_MD)
    baselines = json.loads(_PPO_BASELINES.read_text())
    md = _MANAGERIAL_MD.read_text()

    ss_mean = baselines["ss_policy"]["mean"]
    rnd_mean = baselines["random"]["mean"]
    assert _approx_in_text(ss_mean, md, 0.01), (
        f"MANAGERIAL_INSIGHTS.md missing (R, s, S) reward ≈ {ss_mean:.0f}"
    )
    assert _approx_in_text(rnd_mean, md, 0.01), (
        f"MANAGERIAL_INSIGHTS.md missing random reward ≈ {rnd_mean:.0f}"
    )


def test_mentor_report_quotes_ppo_baselines() -> None:
    """MENTOR_REPORT.md likewise quotes the baselines from the JSON."""
    _skip_if_missing(_PPO_BASELINES, _MENTOR_MD)
    baselines = json.loads(_PPO_BASELINES.read_text())
    md = _MENTOR_MD.read_text()

    ss_mean = baselines["ss_policy"]["mean"]
    ppo_full = baselines["ppo_full"]["mean"]
    assert _approx_in_text(ss_mean, md, 0.01), (
        f"MENTOR_REPORT.md missing (R, s, S) reward ≈ {ss_mean:.0f}"
    )
    assert _approx_in_text(ppo_full, md, 0.01), (
        f"MENTOR_REPORT.md missing PPO-100 reward ≈ {ppo_full:.0f}"
    )


# --------------------------------------------------------------
# 5. Significance thresholds the manuscript discussion relies on
# --------------------------------------------------------------

def test_significance_thresholds_hold() -> None:
    """Friedman and Wilcoxon p-values must be < 0.05.

    The manuscript's §6 discussion claims significance at α=0.05.
    A regression pulling these p-values above 0.05 would invalidate
    the headline narrative. This test pins it.
    """
    _skip_if_missing(_STATS_TESTS)
    stats = json.loads(_STATS_TESTS.read_text())
    friedman_p = stats["friedman"]["p"]
    wilcoxon_p = stats["wilcoxon_nsga2_moead"]["p"]
    assert friedman_p < 0.05, (
        f"Friedman p={friedman_p:.4f} is no longer < 0.05; the "
        "manuscript significance claim has regressed."
    )
    assert wilcoxon_p < 0.05, (
        f"Wilcoxon p={wilcoxon_p:.4f} is no longer < 0.05; the "
        "post-hoc significance claim has regressed."
    )


def test_des_service_level_above_threshold() -> None:
    """DES no-shock SL must remain ≥ 95 %.

    Pinned to catch any regression in the DES env that would drop
    the headline service level the resilience section depends on.
    """
    _skip_if_missing(_TRAINING_SUMMARY)
    summary = json.loads(_TRAINING_SUMMARY.read_text())
    sl_mean = summary["des"]["mean_sl"]
    assert sl_mean >= 0.95, (
        f"DES service level {sl_mean:.2%} below the 95 % threshold "
        "the manuscript Phase 2 section claims."
    )


# --------------------------------------------------------------
# 6. Fig 9 — green-premium curve existence (FIX-030)
# --------------------------------------------------------------

def test_fig9_green_premium_curve_exists() -> None:
    """outputs/figures/fig9_green_premium_curve.png must exist (FIX-030).

    The 9-main-figure set (fig1...fig9) is what the manuscript and
    docs/HEADLINE_NUMBERS.md commit to. Skip-gracefully if the file
    is absent in a fresh checkout (matching the pattern used by the
    other consistency tests); when present, the file must be a non-
    empty PNG of at least 50 KB so we catch silent regenerations
    that produce a blank or truncated figure.
    """
    _skip_if_missing(_FIG9_GREEN_PREMIUM)
    size_bytes = _FIG9_GREEN_PREMIUM.stat().st_size
    assert size_bytes >= 50 * 1024, (
        f"fig9_green_premium_curve.png is {size_bytes} bytes "
        "(< 50 KB) — likely a blank or truncated render."
    )


# --------------------------------------------------------------
# 7. Table 1 — literature comparison matrix existence (Task 9.2)
# --------------------------------------------------------------

def test_table1_literature_comparison_has_ten_rows() -> None:
    """outputs/tables/table1_literature_comparison.tex must exist (Task 9.2).

    The literature-comparison matrix is the asset cited inline by §2.5
    of ``docs/PAPER_OUTLINE.md``. The file must be a syntactically
    valid LaTeX table fragment with at least 10 distinct paper rows
    in the body (the "This paper" summary row is excluded from the
    count; the 10-row threshold matches the 10 representative
    references the literature review surveys). Skip-gracefully if
    the file is absent in a fresh checkout, matching the pattern
    used by the other consistency checks.
    """
    _skip_if_missing(_TABLE1_LITERATURE)
    tex = _TABLE1_LITERATURE.read_text()

    # Validate basic LaTeX table structure.
    assert "\\begin{table}" in tex, (
        "table1_literature_comparison.tex missing \\begin{table} environment."
    )
    assert "\\end{table}" in tex, (
        "table1_literature_comparison.tex missing \\end{table} closure."
    )
    assert "\\begin{tabular}" in tex and "\\end{tabular}" in tex, (
        "table1_literature_comparison.tex missing tabular block."
    )
    assert "\\caption{" in tex, (
        "table1_literature_comparison.tex missing \\caption{...}."
    )
    assert "\\label{tab:literature_comparison}" in tex, (
        "table1_literature_comparison.tex missing the expected label "
        "\\label{tab:literature_comparison}."
    )

    # Count distinct paper rows (lines containing a \citep{...} key).
    # This excludes the header row (no \citep) and the "This paper"
    # summary row (no \citep), giving a clean 10-row floor.
    paper_rows = [
        line for line in tex.splitlines() if "\\citep{" in line
    ]
    assert len(paper_rows) >= 10, (
        f"table1_literature_comparison.tex has only {len(paper_rows)} "
        "paper rows (lines containing \\citep{...}); the §2 literature "
        "review commits to at least 10 representative references."
    )
