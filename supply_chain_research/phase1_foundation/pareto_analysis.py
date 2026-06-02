"""Pareto front analysis and quality metrics.

Computes hypervolume, generational distance, inverted generational
distance, spread indicator, and green premium metrics.

Audit 3.3: compute_hypervolume now normalizes objectives to [0,1]
before computing HV so the indicator is scale-invariant. Previous
behavior (raw HV in INR x kg CO2) was dominated by whichever objective
had the larger numerical range.
"""

import numpy as np
from pymoo.indicators.gd import GD
from pymoo.indicators.hv import HV
from pymoo.indicators.igd import IGD


def compute_normalized_hypervolume(
    pareto_front: np.ndarray,
    ideal_point: np.ndarray = None,
    nadir_point: np.ndarray = None,
    margin: float = 1.1,
) -> float:
    """Compute scale-invariant hypervolume.

    Normalizes objectives to [0,1] before HV computation so the
    indicator is comparable across algorithms regardless of
    objective scales.

    Parameters
    ----------
    pareto_front : np.ndarray
        Shape (n_solutions, n_objectives).
    ideal_point : np.ndarray, optional
        Per-objective minimum across all fronts being compared.
        If None, uses the per-objective min of the input front.
    nadir_point : np.ndarray, optional
        Per-objective maximum across all fronts being compared.
        If None, uses the per-objective max of the input front.
    margin : float
        Multiplier on the nadir for the reference point. Default 1.1
        gives a 10% margin.

    Returns
    -------
    float
        Hypervolume in [0, margin^n_obj]. Higher is better.
    """
    if pareto_front is None or len(pareto_front) == 0:
        return 0.0

    front = np.asarray(pareto_front, dtype=float)

    if ideal_point is None:
        ideal_point = np.min(front, axis=0)
    if nadir_point is None:
        nadir_point = np.max(front, axis=0)

    # Guard against degenerate range
    range_vec = nadir_point - ideal_point
    range_vec = np.where(range_vec < 1e-12, 1.0, range_vec)

    # Normalize to [0, 1] (clip in case external ideal/nadir are tighter)
    normalized = (front - ideal_point) / range_vec
    normalized = np.clip(normalized, 0.0, margin)

    # Reference point at margin in normalized space
    ref = np.full(front.shape[1], margin)
    hv = HV(ref_point=ref)(normalized)
    return float(hv)


def compute_hypervolume(
    pareto_front: np.ndarray,
    reference_point: np.ndarray = None,
    ideal_point: np.ndarray = None,
    nadir_point: np.ndarray = None,
    margin: float = 1.1,
) -> float:
    """Compute hypervolume indicator (scale-invariant).

    Audit 3.3 fix: normalizes objectives before HV computation.
    The old `reference_point` parameter is kept for backward
    compatibility but ignored; users should pass `ideal_point` and
    `nadir_point` for cross-front comparisons. When both are None,
    per-front normalization is used.

    Parameters
    ----------
    pareto_front : np.ndarray
        Shape (n_solutions, n_objectives).
    reference_point : np.ndarray, optional
        DEPRECATED — kept for back-compat; ignored if provided.
        Use ideal_point/nadir_point instead.
    ideal_point : np.ndarray, optional
        Joint minimum across all fronts being compared. Pass this when
        comparing multiple algorithms so HV values are commensurable.
    nadir_point : np.ndarray, optional
        Joint maximum across all fronts being compared.
    margin : float
        Reference-point margin in normalized space (default 1.1).

    Returns
    -------
    float
        Normalized hypervolume.
    """
    return compute_normalized_hypervolume(
        pareto_front=pareto_front,
        ideal_point=ideal_point,
        nadir_point=nadir_point,
        margin=margin,
    )


def compute_hypervolume_with_history(
    pareto_front: np.ndarray,
    historical_populations: list,
    margin: float = 1.1,
) -> float:
    """Compute hypervolume using global nadir from optimization history.

    Computes a consistent reference point from the global maximum
    (nadir) across ALL historical populations, not just the current
    front. This ensures hypervolume values are comparable across
    generations.

    Args:
        pareto_front: Current Pareto front, shape (n_solutions, n_obj).
        historical_populations: List of arrays representing all
            populations evaluated across all generations. Each entry
            should be shape (pop_size, n_objectives).
        margin: Multiplier for the reference point (default 1.1 =
            110% of global nadir, matching config.nsga.ref_point_margin).

    Returns:
        Hypervolume value computed with global reference point.
    
    Parameters
    ----------
    """
    if pareto_front is None or len(pareto_front) == 0:
        return 0.0

    # Compute global nadir across all historical populations
    all_points = [pareto_front]
    for pop in historical_populations:
        if pop is not None and len(pop) > 0:
            all_points.append(np.asarray(pop))

    combined = np.vstack(all_points)
    global_nadir = np.max(combined, axis=0)
    reference_point = global_nadir * margin

    hv_indicator = HV(ref_point=reference_point)
    return float(hv_indicator(pareto_front))


def compute_generational_distance(
    obtained_front: np.ndarray,
    true_front: np.ndarray,
) -> float:
    """Compute Generational Distance (GD).

    Measures convergence: average distance from obtained front
    to the true Pareto front.

    Args:
        obtained_front: Obtained Pareto front.
        true_front: True/reference Pareto front.

    Returns:
        GD value (lower is better).
    
    Parameters
    ----------
    """
    if obtained_front is None or len(obtained_front) == 0:
        return float("inf")

    gd_indicator = GD(true_front)
    return float(gd_indicator(obtained_front))


def compute_igd(
    obtained_front: np.ndarray,
    true_front: np.ndarray,
) -> float:
    """Compute Inverted Generational Distance (IGD).

    Measures both convergence and diversity.

    Args:
        obtained_front: Obtained Pareto front.
        true_front: True/reference Pareto front.

    Returns:
        IGD value (lower is better).
    
    Parameters
    ----------
    """
    if obtained_front is None or len(obtained_front) == 0:
        return float("inf")

    igd_indicator = IGD(true_front)
    return float(igd_indicator(obtained_front))


def compute_spread(pareto_front: np.ndarray) -> float:
    """Compute Spread (Delta) indicator.

    Measures the extent of spread along the Pareto front.

    Args:
        pareto_front: Array of shape (n_solutions, n_objectives).

    Returns:
        Spread value.
    
    Parameters
    ----------
    """
    if pareto_front is None or len(pareto_front) < 2:
        return 0.0

    # Sort by first objective
    sorted_front = pareto_front[pareto_front[:, 0].argsort()]

    # Compute consecutive distances
    n = len(sorted_front)
    distances = np.zeros(n - 1)
    for i in range(n - 1):
        distances[i] = np.linalg.norm(
            sorted_front[i + 1] - sorted_front[i]
        )

    if np.sum(distances) == 0:
        return 0.0

    mean_dist = np.mean(distances)

    # Spread = sum of |di - d_mean| / ((n-1) * d_mean)
    spread = np.sum(np.abs(distances - mean_dist))
    spread /= (n - 1) * mean_dist

    return float(spread)


def compute_green_premium(
    pareto_front: np.ndarray,
) -> dict:
    """Compute Green Premium: cost increase for emission reduction.

    Identifies the minimum cost and minimum emission solutions
    on the Pareto front and computes the trade-off.

    Args:
        pareto_front: Array of shape (n_solutions, 2) where
            column 0 is cost and column 1 is emissions.

    Returns:
        Dictionary with green premium metrics.
    
    Parameters
    ----------
    """
    if pareto_front is None or len(pareto_front) < 2:
        return {
            "green_premium_pct": 0.0,
            "emission_reduction_pct": 0.0,
            "min_cost_solution": None,
            "min_emission_solution": None,
        }

    # Find extreme solutions
    min_cost_idx = np.argmin(pareto_front[:, 0])
    min_emission_idx = np.argmin(pareto_front[:, 1])

    min_cost_sol = pareto_front[min_cost_idx]
    min_emission_sol = pareto_front[min_emission_idx]

    # Green premium: how much more does the greenest solution cost?
    cost_increase = min_emission_sol[0] - min_cost_sol[0]
    cost_increase_pct = (cost_increase / min_cost_sol[0]) * 100

    # Emission reduction from cheapest to greenest
    emission_reduction = min_cost_sol[1] - min_emission_sol[1]
    emission_reduction_pct = (
        (emission_reduction / min_cost_sol[1]) * 100
    )

    return {
        "green_premium_pct": float(cost_increase_pct),
        "emission_reduction_pct": float(emission_reduction_pct),
        "min_cost_solution": min_cost_sol.tolist(),
        "min_emission_solution": min_emission_sol.tolist(),
    }


def full_pareto_analysis(
    pareto_front: np.ndarray,
    reference_front: np.ndarray = None,
) -> dict:
    """Run complete Pareto front analysis.

    Args:
        pareto_front: Obtained Pareto front.
        reference_front: True/reference front for GD/IGD.
            If None, uses the obtained front as reference.

    Returns:
        Dictionary with all Pareto quality metrics.
    
    Parameters
    ----------
    """
    if reference_front is None:
        reference_front = pareto_front

    hv = compute_hypervolume(pareto_front)
    gd = compute_generational_distance(pareto_front, reference_front)
    igd = compute_igd(pareto_front, reference_front)
    spread = compute_spread(pareto_front)
    green_premium = compute_green_premium(pareto_front)

    return {
        "hypervolume": hv,
        "generational_distance": gd,
        "inverted_generational_distance": igd,
        "spread": spread,
        "green_premium": green_premium,
        "n_solutions": len(pareto_front),
        "nadir_point": np.max(pareto_front, axis=0).tolist(),
        "ideal_point": np.min(pareto_front, axis=0).tolist(),
    }


def compute_delta_spread(pareto_front: np.ndarray) -> float:
    """Deb's Δ spread metric (Deb 2001, eq. 3.16).

    Δ = (d_f + d_l + sum_i |d_i - d_bar|) / (d_f + d_l + (n-1) * d_bar)

    where d_i is the Euclidean distance between consecutive sorted
    points, d_f and d_l are distances from extreme points to ideal
    boundary points (here approximated as the front's min/max corners),
    and d_bar is the mean d_i.

    Lower is better (uniform spread).

    Parameters
    ----------
    pareto_front : np.ndarray
        Two-dimensional array of objective vectors, shape
        ``(n_solutions, n_objectives)``.

    Returns
    -------
    float
        Spread Δ in ``[0, +inf)``; ``0.0`` is returned for fronts
        with fewer than three points or numerically degenerate
        spacing.
    """
    if pareto_front is None or len(pareto_front) < 3:
        return 0.0
    front = np.asarray(pareto_front, dtype=float)
    n = len(front)
    sorted_front = front[front[:, 0].argsort()]

    # Consecutive distances
    deltas = np.linalg.norm(np.diff(sorted_front, axis=0), axis=1)
    d_bar = float(np.mean(deltas)) if len(deltas) > 0 else 0.0
    if d_bar < 1e-12:
        return 0.0

    # Boundary distances: distance from extremes to the ideal corner
    ideal = front.min(axis=0)
    nadir = front.max(axis=0)
    d_f = float(np.linalg.norm(sorted_front[0] - ideal))
    d_l = float(np.linalg.norm(sorted_front[-1] - nadir))

    numerator = d_f + d_l + float(np.sum(np.abs(deltas - d_bar)))
    denominator = d_f + d_l + (n - 1) * d_bar
    if denominator < 1e-12:
        return 0.0
    return numerator / denominator


def compute_additive_epsilon(
    obtained_front: np.ndarray,
    reference_front: np.ndarray,
) -> float:
    """Additive epsilon indicator (Zitzler et al. 2003).

    eps_a(A, R) = max_{r in R} min_{a in A} max_{i} (a_i - r_i)

    For minimization. Lower is better; eps_a = 0 means A weakly
    dominates R.

    Parameters
    ----------
    obtained_front : np.ndarray
        Front returned by the algorithm under test, shape
        ``(|A|, n_objectives)``.
    reference_front : np.ndarray
        Reference (ground-truth or best-known) front, shape
        ``(|R|, n_objectives)``.

    Returns
    -------
    float
        The additive epsilon indicator. Returns ``inf`` when either
        front is empty or ``None``.
    """
    if (
        obtained_front is None
        or reference_front is None
        or len(obtained_front) == 0
        or len(reference_front) == 0
    ):
        return float("inf")
    A = np.asarray(obtained_front, dtype=float)
    R = np.asarray(reference_front, dtype=float)
    # For each r in R, find min over A of max over i of (a_i - r_i)
    diffs = A[:, None, :] - R[None, :, :]   # (|A|, |R|, m)
    per_pair = diffs.max(axis=2)            # (|A|, |R|): max over objectives
    per_r = per_pair.min(axis=0)            # (|R|,): min over A
    return float(per_r.max())
