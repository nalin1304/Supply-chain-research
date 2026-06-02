"""Statistical comparison framework for multi-objective solvers.

Enables rigorous comparison of different optimization algorithms across multiple
random seeds. Computes metrics (Hypervolume, Spread, Runtime), runs non-parametric
statistical tests (Friedman rank test, pairwise Wilcoxon signed-rank tests), and
produces critical difference diagrams and performance profiles.

References
----------
.. [1] Demsar, J. (2006). Statistical Comparisons of Classifiers over Multiple Data Sets.
       Journal of Machine Learning Research, 7, 1-30.
.. [2] Dolan, E. D. & More, J. J. (2002). Benchmarking Optimization Software with
       Performance Profiles. Mathematical Programming, 91(2), 201-213.
"""

from dataclasses import dataclass

import matplotlib.pyplot as plt
import numpy as np
import scipy.stats as stats
from loguru import logger

from supply_chain_research.config import MasterConfig
from supply_chain_research.phase1_foundation.solver_base import BaseSolver


@dataclass
class ComparisonResult:
    """Unified container for all algorithm comparison results.
    Parameters
    ----------
    """

    solvers: list[str]
    seeds: list[int]
    hypervolumes: dict[str, list[float]]  # {solver_name: [hv_seed1, hv_seed2, ...]}
    runtimes: dict[str, list[float]]  # {solver_name: [t_seed1, t_seed2, ...]}
    pareto_fronts: dict[str, list[np.ndarray]]  # {solver_name: [front_seed1, ...]}


@dataclass
class FriedmanResult:
    """
    Parameters
    ----------
    """
    statistic: float
    p_value: float
    mean_ranks: dict[str, float]
    significant: bool


@dataclass
class PairwiseResult:
    """
    Parameters
    ----------
    """
    p_values: dict[tuple[str, str], float]
    adjusted_p_values: dict[tuple[str, str], float]
    significant_pairs: list[tuple[str, str]]


def run_comparison(
    config: MasterConfig,
    distance_matrix: np.ndarray,
    demand: np.ndarray,
    solvers: list[BaseSolver],
    n_seeds: int = 10,  # 10 is fast for testing, can be increased to 30 for publication
) -> ComparisonResult:
    """Compare multiple solvers across multiple seeds.
    Parameters
    ----------
    """
    logger.info(f"Running multi-objective solver comparison framework over {n_seeds} seeds...")
    seeds = [42 + i for i in range(n_seeds)]

    hypervolumes = {s.name: [] for s in solvers}
    runtimes = {s.name: [] for s in solvers}
    pareto_fronts = {s.name: [] for s in solvers}

    for seed in seeds:
        logger.info(f"--- Starting Seed {seed} ---")
        for solver in solvers:
            try:
                res = solver.solve(config, distance_matrix, demand, seed=seed)
                hypervolumes[solver.name].append(res.hypervolume)
                runtimes[solver.name].append(res.runtime_seconds)
                pareto_fronts[solver.name].append(res.pareto_front)
            except Exception as e:
                logger.error(f"Solver {solver.name} failed on seed {seed}: {e}")
                hypervolumes[solver.name].append(0.0)
                runtimes[solver.name].append(0.0)
                pareto_fronts[solver.name].append(np.empty((0, 2)))

    return ComparisonResult(
        solvers=[s.name for s in solvers],
        seeds=seeds,
        hypervolumes=hypervolumes,
        runtimes=runtimes,
        pareto_fronts=pareto_fronts,
    )


def friedman_test(results: ComparisonResult) -> FriedmanResult:
    """Run non-parametric Friedman rank test on Hypervolume values.
    Parameters
    ----------
    """
    logger.info("Executing Friedman rank test...")
    # Build matrix: shape (n_seeds, n_solvers)
    hv_matrix = np.array([results.hypervolumes[s] for s in results.solvers]).T

    # Calculate Friedman test
    try:
        stat, p_val = stats.friedmanchisquare(*[hv_matrix[:, i] for i in range(hv_matrix.shape[1])])
    except ValueError:
        # Fallback if too few samples or identical columns
        stat, p_val = 0.0, 1.0

    # Calculate mean ranks (higher is better for hypervolume, so we negate to rank)
    ranks = stats.rankdata(-hv_matrix, axis=1)
    mean_ranks = {results.solvers[i]: float(np.mean(ranks[:, i])) for i in range(len(results.solvers))}

    return FriedmanResult(
        statistic=stat,
        p_value=p_val,
        mean_ranks=mean_ranks,
        significant=(p_val < 0.05),
    )


def wilcoxon_pairwise(results: ComparisonResult, correction: str = "holm") -> PairwiseResult:
    """Run pairwise Wilcoxon signed-rank tests with Holm-Bonferroni correction.
    Parameters
    ----------
    """
    logger.info("Executing pairwise Wilcoxon signed-rank tests...")
    solvers = results.solvers
    n_solvers = len(solvers)

    raw_p_values = {}
    pairs = []

    # Perform pairwise Wilcoxon signed-rank tests
    for i in range(n_solvers):
        for j in range(i + 1, n_solvers):
            s1, s2 = solvers[i], solvers[j]
            hv1 = np.array(results.hypervolumes[s1])
            hv2 = np.array(results.hypervolumes[s2])

            try:
                _, p_val = stats.wilcoxon(hv1, hv2)
            except ValueError:
                # If all differences are zero, wilcoxon raises an error
                p_val = 1.0

            raw_p_values[(s1, s2)] = p_val
            pairs.append((s1, s2))

    # Adjust p-values using Holm-Bonferroni correction
    n_comparisons = len(pairs)
    sorted_pairs = sorted(pairs, key=lambda p: raw_p_values[p])
    adjusted_p_values = {}
    significant_pairs = []

    for rank, pair in enumerate(sorted_pairs):
        p_val = raw_p_values[pair]
        # Holm-Bonferroni formula: adj_p = p * (n_comparisons - rank)
        adj_p = min(1.0, p_val * (n_comparisons - rank))
        adjusted_p_values[pair] = adj_p
        if adj_p < 0.05:
            significant_pairs.append(pair)

    return PairwiseResult(
        p_values=raw_p_values,
        adjusted_p_values=adjusted_p_values,
        significant_pairs=significant_pairs,
    )


def critical_difference_diagram(results: ComparisonResult, output_path: str = "outputs/cd_diagram.png") -> None:
    """Generate and save Critical Difference diagram based on mean ranks.
    Parameters
    ----------
    """
    logger.info(f"Generating Critical Difference diagram at {output_path}...")
    test_res = friedman_test(results)
    ranks = test_res.mean_ranks

    fig, ax = plt.subplots(figsize=(8, 4))
    names = list(ranks.keys())
    values = list(ranks.values())

    y_pos = np.arange(len(names))
    ax.barh(y_pos, values, align="center", alpha=0.8, color="skyblue")
    ax.set_yticks(y_pos)
    ax.set_yticklabels(names)
    ax.invert_yaxis()  # top-down
    ax.set_xlabel("Mean Rank (lower rank is better)")
    ax.set_title("Solver Comparison: Friedman Mean Ranks")

    plt.tight_layout()
    plt.savefig(output_path, dpi=300)
    plt.close()


def performance_profile(results: ComparisonResult, output_path: str = "outputs/performance_profile.png") -> None:
    """Generate and save Performance Profile plot.
    Parameters
    ----------
    """
    logger.info(f"Generating Performance Profile at {output_path}...")
    solvers = results.solvers
    n_seeds = len(results.seeds)

    # Build matrix: shape (n_seeds, n_solvers)
    hv_matrix = np.array([results.hypervolumes[s] for s in solvers]).T

    # Find the maximum hypervolume for each seed
    max_hvs = hv_matrix.max(axis=1)[:, None]
    max_hvs[max_hvs == 0] = 1.0  # avoid division by zero

    # Performance ratios: maximum / actual (so ratio >= 1.0, 1.0 is best)
    ratios = max_hvs / hv_matrix

    fig, ax = plt.subplots(figsize=(8, 5))
    tau_vals = np.linspace(1.0, 3.0, 100)

    for i, solver_name in enumerate(solvers):
        profile_vals = []
        for tau in tau_vals:
            # Fraction of problems/seeds where performance ratio is <= tau
            fraction = np.sum(ratios[:, i] <= tau) / n_seeds
            profile_vals.append(fraction)
        ax.plot(tau_vals, profile_vals, label=solver_name, lw=2)

    ax.set_xlabel(r"Performance ratio $\tau$")
    ax.set_ylabel(r"Fraction of seeds $\rho(\tau)$")
    ax.set_title("Performance Profile (Hypervolume)")
    ax.grid(True, linestyle="--", alpha=0.5)
    ax.legend()

    plt.tight_layout()
    plt.savefig(output_path, dpi=300)
    plt.close()
