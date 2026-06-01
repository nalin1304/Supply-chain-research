"""Tests for Phase 4: Synthesis - statistics, figures, and tables."""

import os
import numpy as np

from supply_chain_research.phase4_synthesis.statistical_tests import (
    cliffs_delta,
    bootstrap_ci,
    wilcoxon_signed_rank,
    friedman_test,
    kruskal_wallis,
    mann_whitney_u,
    holm_bonferroni_correction,
    generate_synthetic_results,
    run_full_statistical_analysis,
)
from supply_chain_research.phase4_synthesis.sensitivity_analysis import (
    generate_parameter_ranges,
    run_sensitivity_sweep,
    compute_sensitivity_indices,
    rank_parameters,
)
from supply_chain_research.phase4_synthesis.ablation_study import (
    generate_ablation_results,
    compute_component_contribution,
    rank_components,
    run_ablation_study,
    VARIANTS,
    METRICS,
)
from supply_chain_research.phase4_synthesis.generate_all_figures import (
    generate_all_figures,
)
from supply_chain_research.phase4_synthesis.generate_latex_tables import (
    generate_all_tables,
    generate_table1_parameters,
    generate_table3_statistical_tests,
)


class TestStatisticalTests:
    """Tests for statistical validation module."""

    def test_cliffs_delta_identical(self):
        """Cliff's delta is zero for identical distributions."""
        x = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        delta, mag = cliffs_delta(x, x)
        assert delta == 0.0
        assert mag == "negligible"

    def test_cliffs_delta_dominated(self):
        """Cliff's delta is +1 when x always larger than y."""
        x = np.array([10.0, 11.0, 12.0, 13.0, 14.0])
        y = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        delta, mag = cliffs_delta(x, y)
        assert delta == 1.0
        assert mag == "large"

    def test_cliffs_delta_range(self):
        """Cliff's delta is in [-1, 1]."""
        rng = np.random.default_rng(42)
        x = rng.normal(10, 2, 30)
        y = rng.normal(8, 2, 30)
        delta, mag = cliffs_delta(x, y)
        assert -1.0 <= delta <= 1.0
        assert mag in ["negligible", "small", "medium", "large"]

    def test_bootstrap_ci_contains_median(self):
        """Bootstrap CI contains the sample median."""
        rng = np.random.default_rng(42)
        data = rng.normal(100, 10, 50)
        lower, upper = bootstrap_ci(data)
        median = np.median(data)
        assert lower <= median <= upper

    def test_bootstrap_ci_ordering(self):
        """Lower bound is less than upper bound."""
        data = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        lower, upper = bootstrap_ci(data)
        assert lower <= upper

    def test_wilcoxon_valid_pvalue(self):
        """Wilcoxon test returns valid p-value."""
        rng = np.random.default_rng(42)
        x = rng.normal(10, 2, 30)
        y = rng.normal(8, 2, 30)
        result = wilcoxon_signed_rank(x, y)
        assert 0.0 <= result["p_value"] <= 1.0
        assert result["statistic"] >= 0
        assert result["effect_magnitude"] in [
            "negligible", "small", "medium", "large"
        ]

    def test_wilcoxon_small_sample(self):
        """Wilcoxon handles small samples gracefully."""
        x = np.array([1.0, 2.0])
        y = np.array([3.0, 4.0])
        result = wilcoxon_signed_rank(x, y)
        assert result["p_value"] == 1.0

    def test_kruskal_wallis_valid_pvalue(self):
        """Kruskal-Wallis returns valid p-value."""
        rng = np.random.default_rng(42)
        g1 = rng.normal(10, 2, 30)
        g2 = rng.normal(12, 2, 30)
        g3 = rng.normal(14, 2, 30)
        result = kruskal_wallis(g1, g2, g3)
        assert 0.0 <= result["p_value"] <= 1.0
        assert result["effect_size_eta2"] >= 0.0

    def test_mann_whitney_valid_pvalue(self):
        """Mann-Whitney U returns valid p-value."""
        rng = np.random.default_rng(42)
        x = rng.normal(10, 2, 30)
        y = rng.normal(12, 2, 30)
        result = mann_whitney_u(x, y)
        assert 0.0 <= result["p_value"] <= 1.0
        assert result["statistic"] >= 0

    def test_generate_synthetic_results_shape(self):
        """Synthetic results have correct structure."""
        results = generate_synthetic_results(n_runs=20)
        assert "NSGA-II" in results
        assert "MOEA/D" in results
        assert "OR-Tools" in results
        for method in results:
            assert len(results[method]["cost"]) == 20
            assert len(results[method]["emissions"]) == 20
            assert len(results[method]["hypervolume"]) == 20

    def test_full_statistical_analysis(self):
        """Full analysis produces valid results for all metrics."""
        analysis = run_full_statistical_analysis()
        assert "cost" in analysis
        assert "emissions" in analysis
        assert "hypervolume" in analysis
        assert "service_level" in analysis

        for metric in analysis:
            assert "friedman" in analysis[metric]
            assert "kruskal_wallis" in analysis[metric]
            assert "mann_whitney_pairwise" in analysis[metric]
            assert "confidence_intervals" in analysis[metric]
            fr = analysis[metric]["friedman"]
            assert 0.0 <= fr["p_value"] <= 1.0
            kw = analysis[metric]["kruskal_wallis"]
            assert 0.0 <= kw["p_value"] <= 1.0

    def test_friedman_test_valid(self):
        """Friedman test returns valid p-value for paired samples."""
        rng = np.random.default_rng(42)
        g1 = rng.normal(10, 2, 30)
        g2 = rng.normal(12, 2, 30)
        g3 = rng.normal(14, 2, 30)
        result = friedman_test(g1, g2, g3)
        assert 0.0 <= result["p_value"] <= 1.0
        assert result["statistic"] >= 0.0
        assert "effect_size_w" in result

    def test_friedman_test_identical_groups(self):
        """Friedman test gives high p-value for identical groups."""
        rng = np.random.default_rng(42)
        data = rng.normal(10, 2, 30)
        result = friedman_test(data, data.copy(), data.copy())
        assert result["p_value"] >= 0.05

    def test_holm_bonferroni_correction(self):
        """Holm-Bonferroni correction adjusts p-values upward."""
        raw_p = [0.01, 0.04, 0.03]
        adjusted = holm_bonferroni_correction(raw_p)
        # Adjusted p-values should be >= raw p-values
        for adj, raw in zip(adjusted, raw_p):
            assert adj >= raw
        # All should be <= 1.0
        for adj in adjusted:
            assert adj <= 1.0

    def test_holm_bonferroni_single(self):
        """Holm-Bonferroni with single p-value is unchanged."""
        raw_p = [0.05]
        adjusted = holm_bonferroni_correction(raw_p)
        assert len(adjusted) == 1
        assert adjusted[0] == 0.05


class TestSensitivityAnalysis:
    """Tests for sensitivity analysis module."""

    def test_parameter_ranges(self):
        """Parameter ranges have expected keys and values."""
        ranges = generate_parameter_ranges()
        assert "fleet_mix_ratio" in ranges
        assert "demand_variability" in ranges
        assert "warehouse_capacity" in ranges
        assert "carbon_weight" in ranges
        # Each should have 11 values
        for key in ranges:
            assert len(ranges[key]) == 11

    def test_sensitivity_sweep(self):
        """Sensitivity sweep produces hypervolumes for all params."""
        results = run_sensitivity_sweep(seed=42)
        assert len(results) == 4
        for param_name, data in results.items():
            assert "values" in data
            assert "hypervolumes" in data
            assert len(data["values"]) == 11
            assert len(data["hypervolumes"]) == 11
            # Hypervolumes should be positive
            assert np.all(data["hypervolumes"] > 0)

    def test_sensitivity_indices(self):
        """Sensitivity indices are non-negative."""
        results = run_sensitivity_sweep(seed=42)
        indices = compute_sensitivity_indices(results)
        assert len(indices) == 4
        for val in indices.values():
            assert val >= 0.0

    def test_rank_parameters(self):
        """Ranking returns sorted list."""
        results = run_sensitivity_sweep(seed=42)
        indices = compute_sensitivity_indices(results)
        ranked = rank_parameters(indices)
        assert len(ranked) == 4
        # Should be sorted descending
        values = [r[1] for r in ranked]
        assert values == sorted(values, reverse=True)


class TestAblationStudy:
    """Tests for ablation study module."""

    def test_generate_ablation_results(self):
        """Ablation results have all variants and metrics."""
        results = generate_ablation_results()
        for variant in VARIANTS:
            assert variant in results
            for metric in METRICS:
                assert metric in results[variant]

    def test_full_system_best(self):
        """Full system generally outperforms ablated variants."""
        results = generate_ablation_results(seed=42)
        full = results["full_system"]
        # Service level should be highest for full system
        for variant in VARIANTS:
            if variant == "full_system":
                continue
            # Full system has better service (approximately)
            assert full["service_level"] > results[variant][
                "service_level"
            ] - 0.05

    def test_component_contribution(self):
        """Contribution percentages are computed for all variants."""
        results = generate_ablation_results()
        contributions = compute_component_contribution(results)
        # Should not include full_system
        assert "full_system" not in contributions
        assert len(contributions) == 4

    def test_rank_components_sorted(self):
        """Ranking returns sorted by aggregate impact."""
        results = generate_ablation_results()
        contributions = compute_component_contribution(results)
        rankings = rank_components(contributions)
        impacts = [r["aggregate_impact"] for r in rankings]
        assert impacts == sorted(impacts, reverse=True)

    def test_run_ablation_study(self):
        """Full ablation study returns expected structure."""
        study = run_ablation_study()
        assert "results" in study
        assert "contributions" in study
        assert "rankings" in study
        assert "variants" in study
        assert "metrics" in study


class TestFigureGeneration:
    """Tests for figure generation module."""

    def test_generate_all_figures(self):
        """Figures with available data are generated as PNG files."""
        filepaths = generate_all_figures(seed=42)
        # At minimum, fig1, fig7, supp1, supp2 always generate (no training data needed)
        assert len(filepaths) >= 4
        for fp in filepaths:
            assert os.path.exists(fp), f"Missing: {fp}"
            assert fp.endswith('.png')
            # Check file size > 0
            assert os.path.getsize(fp) > 0

    def test_figure_paths(self):
        """Figures are saved in correct directories."""
        filepaths = generate_all_figures(seed=42)
        main_figs = [f for f in filepaths if "supplementary" not in f]
        supp_figs = [f for f in filepaths if "supplementary" in f]
        # At minimum: fig1 + fig7 main, 2 supplementary
        assert len(main_figs) >= 2
        assert len(supp_figs) == 2


class TestLatexTables:
    """Tests for LaTeX table generation module."""

    def test_generate_all_tables(self):
        """All 6 tables are generated as .tex files."""
        filepaths = generate_all_tables(seed=42)
        assert len(filepaths) == 6
        for fp in filepaths:
            assert os.path.exists(fp), f"Missing: {fp}"
            assert fp.endswith('.tex')
            assert os.path.getsize(fp) > 0

    def test_table_contains_latex(self):
        """Generated tables contain valid LaTeX structure."""
        filepath = generate_table1_parameters()
        with open(filepath, 'r') as f:
            content = f.read()
        assert r'\begin{table}' in content
        assert r'\end{table}' in content
        assert r'\hline' in content
        assert r'\begin{tabular}' in content

    def test_table3_statistical_tests_content(self):
        """Table 3 contains statistical test content."""
        filepath = generate_table3_statistical_tests()
        with open(filepath, 'r') as f:
            content = f.read()
        assert "Friedman" in content
        assert "Kruskal-Wallis" in content
        assert "Wilcoxon" in content
        assert "p-value" in content or "pvalue" in content.lower()
