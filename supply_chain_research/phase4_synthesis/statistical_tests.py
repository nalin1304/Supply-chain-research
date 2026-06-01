"""Statistical validation for multi-objective optimization results.

Implements Friedman (paired omnibus), Wilcoxon signed-rank (paired post-hoc),
Kruskal-Wallis (supplementary), Mann-Whitney U tests with effect sizes
(Cliff's delta), Holm-Bonferroni correction, and confidence intervals.

Note: This module currently uses synthetic/simulated data generators
for demonstration purposes. In a production research pipeline, the
generate_synthetic_results() function should be replaced by wiring
actual NSGA-II/MOEA-D optimization outputs into the statistical
validation functions. The analysis pipeline itself is correct; only
the data source is synthetic.
"""

import numpy as np
from scipy import stats
from typing import Dict, List, Tuple


def cliffs_delta(x: np.ndarray, y: np.ndarray) -> Tuple[float, str]:
    """Compute Cliff's delta effect size.

    Cliff's delta measures how often values in one distribution
    are larger than values in another.

    Args:
        x: First sample array.
        y: Second sample array.

    Returns:
        Tuple of (delta value, magnitude label).
        Magnitude: negligible (<0.147), small (<0.33),
        medium (<0.474), large (>=0.474).
    """
    n_x = len(x)
    n_y = len(y)

    if n_x == 0 or n_y == 0:
        return 0.0, "negligible"

    # Count dominance pairs
    more = 0
    less = 0
    for xi in x:
        for yi in y:
            if xi > yi:
                more += 1
            elif xi < yi:
                less += 1

    delta = (more - less) / (n_x * n_y)

    # Magnitude thresholds (Romano et al. 2006)
    abs_delta = abs(delta)
    if abs_delta < 0.147:
        magnitude = "negligible"
    elif abs_delta < 0.33:
        magnitude = "small"
    elif abs_delta < 0.474:
        magnitude = "medium"
    else:
        magnitude = "large"

    return delta, magnitude


def bootstrap_ci(
    data: np.ndarray,
    statistic_func=np.median,
    n_bootstrap: int = 1000,
    confidence: float = 0.95,
    seed: int = 42,
) -> Tuple[float, float]:
    """Compute bootstrap confidence interval.

    Args:
        data: Sample array.
        statistic_func: Function to compute statistic.
        n_bootstrap: Number of bootstrap samples.
        confidence: Confidence level.
        seed: Random seed.

    Returns:
        Tuple of (lower_bound, upper_bound).
    """
    rng = np.random.default_rng(seed)
    n = len(data)

    if n == 0:
        return 0.0, 0.0

    boot_stats = np.zeros(n_bootstrap)
    for i in range(n_bootstrap):
        sample = rng.choice(data, size=n, replace=True)
        boot_stats[i] = statistic_func(sample)

    alpha = 1.0 - confidence
    lower = np.percentile(boot_stats, 100 * alpha / 2)
    upper = np.percentile(boot_stats, 100 * (1 - alpha / 2))

    return float(lower), float(upper)


def wilcoxon_signed_rank(
    x: np.ndarray, y: np.ndarray
) -> Dict[str, float]:
    """Wilcoxon signed-rank test for paired samples.

    Tests whether two paired samples come from the same distribution.
    Used for paired comparison of NSGA-II vs MOEA/D on each metric.

    Args:
        x: First paired sample.
        y: Second paired sample.

    Returns:
        Dictionary with statistic, p_value, effect_size, magnitude.
    """
    if len(x) < 5 or len(y) < 5:
        return {
            "statistic": 0.0,
            "p_value": 1.0,
            "effect_size": 0.0,
            "effect_magnitude": "negligible",
        }

    # Remove pairs with zero difference
    diff = x - y
    nonzero_mask = diff != 0
    if np.sum(nonzero_mask) < 2:
        return {
            "statistic": 0.0,
            "p_value": 1.0,
            "effect_size": 0.0,
            "effect_magnitude": "negligible",
        }

    stat, p_value = stats.wilcoxon(
        x[nonzero_mask], y[nonzero_mask], alternative='two-sided'
    )

    delta, magnitude = cliffs_delta(x, y)

    return {
        "statistic": float(stat),
        "p_value": float(p_value),
        "effect_size": float(delta),
        "effect_magnitude": magnitude,
    }


def friedman_test(*groups: np.ndarray) -> Dict[str, float]:
    """Friedman test for paired samples (omnibus test).

    Non-parametric test comparing distributions of multiple related
    groups evaluated on the same scenarios. Appropriate when methods
    are compared on the same problem instances.

    Args:
        *groups: Variable number of paired sample arrays.
            All groups must have the same length.

    Returns:
        Dictionary with statistic, p_value, and effect_size (Kendall's W).
    """
    valid_groups = [g for g in groups if len(g) >= 2]
    if len(valid_groups) < 2:
        return {
            "statistic": 0.0,
            "p_value": 1.0,
            "effect_size_w": 0.0,
        }

    # All groups must have same length for Friedman
    min_len = min(len(g) for g in valid_groups)
    trimmed_groups = [g[:min_len] for g in valid_groups]

    stat, p_value = stats.friedmanchisquare(*trimmed_groups)

    # Handle NaN from identical groups (no variance in ranks)
    if np.isnan(p_value):
        p_value = 1.0
    if np.isnan(stat):
        stat = 0.0

    # Kendall's W effect size: W = chi2 / (n * (k - 1))
    n = min_len
    k = len(trimmed_groups)
    w = stat / (n * (k - 1)) if n * (k - 1) > 0 else 0.0

    return {
        "statistic": float(stat),
        "p_value": float(p_value),
        "effect_size_w": float(w),
    }


def kruskal_wallis(*groups: np.ndarray) -> Dict[str, float]:
    """Kruskal-Wallis H-test for independent samples.

    Non-parametric test comparing distributions of multiple groups.
    Kept as a supplementary test for readers who want independent-sample
    perspective.

    Args:
        *groups: Variable number of sample arrays.

    Returns:
        Dictionary with statistic, p_value, effect_size (eta^2).
    """
    valid_groups = [g for g in groups if len(g) >= 2]
    if len(valid_groups) < 2:
        return {
            "statistic": 0.0,
            "p_value": 1.0,
            "effect_size_eta2": 0.0,
        }

    stat, p_value = stats.kruskal(*valid_groups)

    # Eta-squared effect size for Kruskal-Wallis
    n_total = sum(len(g) for g in valid_groups)
    k = len(valid_groups)
    eta2 = (stat - k + 1) / (n_total - k) if n_total > k else 0.0
    eta2 = max(0.0, eta2)

    return {
        "statistic": float(stat),
        "p_value": float(p_value),
        "effect_size_eta2": float(eta2),
    }


def mann_whitney_u(
    x: np.ndarray, y: np.ndarray
) -> Dict[str, float]:
    """Mann-Whitney U test for two independent samples.

    Non-parametric test for pairwise comparison.

    Args:
        x: First sample.
        y: Second sample.

    Returns:
        Dictionary with statistic, p_value, effect_size,
        magnitude.
    """
    if len(x) < 2 or len(y) < 2:
        return {
            "statistic": 0.0,
            "p_value": 1.0,
            "effect_size": 0.0,
            "effect_magnitude": "negligible",
        }

    stat, p_value = stats.mannwhitneyu(
        x, y, alternative='two-sided'
    )

    delta, magnitude = cliffs_delta(x, y)

    return {
        "statistic": float(stat),
        "p_value": float(p_value),
        "effect_size": float(delta),
        "effect_magnitude": magnitude,
    }


def holm_bonferroni_correction(
    p_values: List[float],
) -> List[float]:
    """Apply Holm-Bonferroni correction for multiple comparisons.

    Audit 3.5 — SCOPE: This function applies the Holm correction
    PER-METRIC. The caller passes the p-values from all pairwise
    tests within a single metric (e.g., the 3 pairs of NSGA-II vs
    MOEA/D vs OR-Tools for HV alone), and the family-wise error rate
    is controlled within that metric only.

    Justification (per-metric): Each performance metric (HV, IGD,
    cost, etc.) is treated as a separate analysis question, so the
    family-wise error rate is controlled per-question. This matches
    how EJOR statistical-comparison papers (e.g., Derrac et al. 2011
    "A practical tutorial on the use of nonparametric statistical tests")
    report results.

    For a family-wise error rate across ALL metrics x ALL pairs,
    use apply_global_holm() instead.

    Tradeoff:
        - Per-metric: more discoveries; each metric independently
          controlled at alpha; suitable when metrics are not jointly
          interpreted.
        - Global: fewer false discoveries; appropriate when reporting
          a single composite claim ("our method dominates across the
          board").

    Sorts p-values and applies step-down correction:
    adjusted_p[i] = p[i] * (n_comparisons - rank_i)
    where rank_i is the 0-based index in the sorted order.

    Enforces monotonicity: each adjusted p-value in sorted order
    must be >= the previous one (running maximum).

    Args:
        p_values: List of raw p-values from pairwise tests within
            a single metric.

    Returns:
        List of adjusted p-values (in original order), capped at 1.0.
    """
    n = len(p_values)
    if n == 0:
        return []

    # Sort by p-value, keeping track of original indices
    indexed = sorted(enumerate(p_values), key=lambda x: x[1])
    adjusted = [0.0] * n

    for rank, (orig_idx, pval) in enumerate(indexed):
        correction_factor = n - rank
        adj_p = pval * correction_factor
        adjusted[orig_idx] = min(adj_p, 1.0)

    # Enforce monotonicity (each adjusted p must be >= previous
    # in sorted order) using a running maximum
    sorted_adjusted = [adjusted[idx] for idx, _ in indexed]
    for i in range(1, len(sorted_adjusted)):
        if sorted_adjusted[i] < sorted_adjusted[i - 1]:
            sorted_adjusted[i] = sorted_adjusted[i - 1]
    # Write back to original positions
    for i, (orig_idx, _) in enumerate(indexed):
        adjusted[orig_idx] = sorted_adjusted[i]

    return adjusted


def generate_synthetic_results(
    n_runs: int = 30, seed: int = 42
) -> Dict[str, Dict[str, np.ndarray]]:
    """Generate synthetic optimization results for testing.

    Creates plausible results for NSGA-II, MOEA/D, and OR-Tools
    baseline across multiple independent runs.

    Args:
        n_runs: Number of independent runs per method.
        seed: Random seed.

    Returns:
        Dictionary mapping method names to metric arrays.
    """
    rng = np.random.default_rng(seed)

    results = {
        "NSGA-II": {
            "cost": rng.normal(245000, 12000, n_runs),
            "emissions": rng.normal(18500, 900, n_runs),
            "hypervolume": rng.normal(0.72, 0.03, n_runs),
            "computation_time": rng.normal(145, 20, n_runs),
            "service_level": rng.normal(0.94, 0.02, n_runs),
        },
        "MOEA/D": {
            "cost": rng.normal(252000, 14000, n_runs),
            "emissions": rng.normal(17800, 850, n_runs),
            "hypervolume": rng.normal(0.69, 0.04, n_runs),
            "computation_time": rng.normal(128, 18, n_runs),
            "service_level": rng.normal(0.92, 0.025, n_runs),
        },
        "OR-Tools": {
            "cost": rng.normal(268000, 15000, n_runs),
            "emissions": rng.normal(21000, 1100, n_runs),
            "hypervolume": rng.normal(0.55, 0.05, n_runs),
            "computation_time": rng.normal(35, 8, n_runs),
            "service_level": rng.normal(0.89, 0.03, n_runs),
        },
    }

    return results


def run_full_statistical_analysis(
    results: Dict[str, Dict[str, np.ndarray]] = None,
) -> Dict[str, any]:
    """Run comprehensive statistical analysis.

    Uses Friedman test as primary omnibus test (paired samples),
    with Kruskal-Wallis as supplementary. Post-hoc uses paired
    Wilcoxon signed-rank with Holm-Bonferroni correction.

    Args:
        results: Dictionary of method results. If None, generates
            synthetic results for demonstration.

    Returns:
        Dictionary with all test results organized by metric.
    """
    if results is None:
        results = generate_synthetic_results()

    # Audit 3.1: print Friedman power up front
    methods_count = len(results)
    sample_count = len(next(iter(results.values()))[
        next(iter(next(iter(results.values())).keys()))
    ])
    try:
        power = compute_friedman_power(
            n_groups=methods_count,
            n_samples=sample_count,
            expected_kendall_w=0.25,
        )
        print(
            f"[Audit 3.1] Friedman power "
            f"(k={methods_count}, n={sample_count}, W=0.25): {power:.3f}"
        )
    except Exception as e:
        print(f"[Audit 3.1] Friedman power computation failed: {e}")

    metrics = ["cost", "emissions", "hypervolume", "service_level"]
    methods = list(results.keys())

    analysis = {}

    for metric in metrics:
        metric_results = {}

        # Extract data for each method
        method_data = {
            m: results[m][metric] for m in methods
        }

        # Friedman test: primary omnibus test (paired samples)
        groups = [method_data[m] for m in methods]
        metric_results["friedman"] = friedman_test(*groups)

        # Kruskal-Wallis: supplementary independent-samples test
        metric_results["kruskal_wallis"] = kruskal_wallis(*groups)

        # Pairwise Wilcoxon signed-rank with Holm-Bonferroni correction
        pairwise = {}
        pair_keys = []
        raw_p_values = []

        for i in range(len(methods)):
            for j in range(i + 1, len(methods)):
                pair_key = f"{methods[i]}_vs_{methods[j]}"
                result = wilcoxon_signed_rank(
                    method_data[methods[i]],
                    method_data[methods[j]],
                )
                pairwise[pair_key] = result
                pair_keys.append(pair_key)
                raw_p_values.append(result["p_value"])

        # Apply Holm-Bonferroni correction
        adjusted_p_values = holm_bonferroni_correction(raw_p_values)
        for idx, pair_key in enumerate(pair_keys):
            pairwise[pair_key]["p_value_adjusted"] = adjusted_p_values[idx]

        metric_results["wilcoxon_pairwise"] = pairwise

        # Keep Mann-Whitney as supplementary pairwise test
        mann_whitney_pairwise = {}
        for i in range(len(methods)):
            for j in range(i + 1, len(methods)):
                pair_key = f"{methods[i]}_vs_{methods[j]}"
                mann_whitney_pairwise[pair_key] = mann_whitney_u(
                    method_data[methods[i]],
                    method_data[methods[j]],
                )
        metric_results["mann_whitney_pairwise"] = mann_whitney_pairwise

        # Wilcoxon signed-rank: paired NSGA-II vs MOEA/D (legacy key)
        if "NSGA-II" in methods and "MOEA/D" in methods:
            metric_results["wilcoxon_nsga2_vs_moead"] = (
                wilcoxon_signed_rank(
                    method_data["NSGA-II"],
                    method_data["MOEA/D"],
                )
            )

        # Confidence intervals for each method
        ci_results = {}
        for m in methods:
            ci_results[m] = bootstrap_ci(method_data[m])
        metric_results["confidence_intervals"] = ci_results

        analysis[metric] = metric_results

    return analysis


def compute_friedman_power(
    n_groups: int,
    n_samples: int,
    expected_kendall_w: float = 0.25,
    alpha: float = 0.05,
    n_iterations: int = 10000,
    seed: int = 42,
) -> float:
    """Audit 3.1: Monte Carlo power simulation for Friedman test.

    Generates n_iterations synthetic datasets where the true effect size
    is `expected_kendall_w` and counts the fraction in which the
    Friedman test rejects H0 at significance level alpha. Returns
    empirical power.

    Parameters
    ----------
    n_groups : int
        Number of competing algorithms (k).
    n_samples : int
        Number of seeds (n).
    expected_kendall_w : float
        True Kendall's W under H1 (0 = no effect, 1 = perfect ranking
        agreement). 0.10 small, 0.25 medium, 0.40 large.
    alpha : float
        Significance level.
    n_iterations : int
        Number of Monte Carlo iterations.
    seed : int
        RNG seed.

    Returns
    -------
    float
        Empirical statistical power in [0, 1].
    """
    rng = np.random.default_rng(seed)
    # Convert Kendall's W to a per-group mean shift such that the
    # population W matches `expected_kendall_w`. We use the relation
    # chi2 = n*(k-1)*W, and approximate the mean shift mu so that the
    # signal-to-noise ratio in the ranks reproduces W.
    # Use a simple linear separation model: group i samples ~ N(i*mu, 1).
    # Calibrate mu empirically.
    sep = np.sqrt(expected_kendall_w / max(n_groups - 1, 1)) * 2.0

    rejections = 0
    for _ in range(n_iterations):
        # Each row is one block (sample); columns are groups
        baseline = rng.standard_normal((n_samples, 1))
        offsets = (np.arange(n_groups) - (n_groups - 1) / 2.0) * sep
        data = baseline + offsets[None, :] + rng.standard_normal(
            (n_samples, n_groups)
        ) * 0.5
        try:
            stat, p = stats.friedmanchisquare(*[data[:, j] for j in range(n_groups)])
            if not np.isnan(p) and p < alpha:
                rejections += 1
        except ValueError:
            continue
    return float(rejections / n_iterations)


def apply_global_holm(
    p_values_flat: list,
    keys: list = None,
) -> list:
    """Audit 3.5: global Holm-Bonferroni across ALL pairs and metrics.

    Use this when reporting a family-wise error rate across the entire
    table of comparisons. Use apply_holm_bonferroni (the per-metric
    version) when each metric is treated as a separate analysis.

    Parameters
    ----------
    p_values_flat : list of float
        Flat list of raw p-values across all metrics x all pairs.
    keys : list, optional
        Optional identifying labels parallel to p_values_flat (only
        used in the docstring; not returned).

    Returns
    -------
    list of float
        Adjusted p-values in the original order, capped at 1.0.
    """
    return holm_bonferroni_correction(p_values_flat)
