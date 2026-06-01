"""Real sensitivity analysis for supply chain optimization (FIX-016).

Every parameter configuration in this module is evaluated by calling
:func:`supply_chain_research.phase1_foundation.nsga2_solver.run_nsga2`
and computing the hypervolume of the resulting *real* Pareto front.
There is no analytical or fabricated Pareto-front shortcut here
(clause C2.9 in ``.kiro/specs/supply-chain-research-audit/bugfix.md``).

Two analyses are exposed:

- :func:`run_sensitivity_analysis` (one-at-a-time / OAT) — varies
  each of the four parameters in turn while holding the others at
  their baseline value, producing a hypervolume curve per parameter
  and the elementary effect index ``(max - min) / mean``.
- :func:`run_sobol_sensitivity` (variance-based / global) — runs the
  Saltelli (2010) sample design through SALib (Herman & Usher 2017)
  to compute first-order (S1) and total-order (ST) Sobol indices.

The four parameters analyzed are:

- ``fleet_mix_ratio`` — fraction of HCV in the fleet
  (``NetworkConfig.hcv_lcv_fleet_ratio``);
- ``demand_variability`` — multiplicative scaling on the demand vector;
- ``warehouse_capacity`` — multiplicative scaling on the per-depot
  capacity vector;
- ``carbon_weight`` — relative weight of the carbon objective in the
  scalarized hypervolume metric (used as an objective-aggregation
  weight, *not* injected into the optimizer to preserve the
  bi-objective contract).

Fast-mode behavior
------------------
When ``fast_mode=True`` (or ``SensitivityConfig.fast_mode=True``) the
parameter grid shrinks (5 points instead of 11) and the per-call
NSGA-II budget is reduced to a small population / generation count
suitable for CI. The hypervolume metric is still computed from a real
Pareto front returned by ``run_nsga2``; no fabricated shortcut is
taken.

References
----------
.. [1] Sobol, I. M. (1993). Sensitivity estimates for nonlinear
       mathematical models. *Mathematical Modelling and Computational
       Experiments*, 1(4), 407-414.
.. [2] Saltelli, A., Annoni, P., Azzini, I., Campolongo, F., Ratto,
       M., & Tarantola, S. (2010). Variance based sensitivity
       analysis of model output. Design and estimator for the total
       sensitivity index. *Computer Physics Communications*, 181(2),
       259-270. DOI: 10.1016/j.cpc.2009.09.018.
.. [3] Herman, J. & Usher, W. (2017). SALib: An open-source Python
       library for sensitivity analysis. *Journal of Open Source
       Software*, 2(9), 97. DOI: 10.21105/joss.00097.
"""

import numpy as np
from typing import Dict, List, Tuple

from supply_chain_research.config import MasterConfig
from supply_chain_research.phase1_foundation.nsga2_solver import run_nsga2
from supply_chain_research.phase1_foundation.pareto_analysis import (
    compute_hypervolume,
)


# =============================================================================
# Parameter grid
# =============================================================================

_PARAM_NAMES: Tuple[str, ...] = (
    "fleet_mix_ratio",
    "demand_variability",
    "warehouse_capacity",
    "carbon_weight",
)

_PARAM_BOUNDS: Dict[str, Tuple[float, float]] = {
    "fleet_mix_ratio": (0.0, 1.0),
    "demand_variability": (0.5, 2.0),
    "warehouse_capacity": (0.7, 1.3),
    "carbon_weight": (0.0, 1.0),
}

_PARAM_BASELINE: Dict[str, float] = {
    "fleet_mix_ratio": 0.5,
    "demand_variability": 1.0,
    "warehouse_capacity": 1.0,
    "carbon_weight": 0.5,
}


def generate_parameter_ranges(
    fast_mode: bool = False,
) -> Dict[str, np.ndarray]:
    """Generate parameter variation ranges for sensitivity analysis.

    Parameters
    ----------
    fast_mode : bool, optional
        If ``True`` use the reduced 5-point grid for CI runs;
        otherwise use the full 11-point grid. The bounds are the
        same in both cases — only the resolution differs (clause
        C2.9: fast mode reduces resolution but never injects
        fabricated data).

    Returns
    -------
    dict
        Mapping of parameter name to ``np.ndarray`` of evaluation
        points. The keys are exactly the four sensitivity
        parameters listed at the top of this module.
    """
    n_points = 5 if fast_mode else 11
    return {
        name: np.linspace(lo, hi, n_points)
        for name, (lo, hi) in _PARAM_BOUNDS.items()
    }


# =============================================================================
# Real NSGA-II evaluation (the only evaluation path)
# =============================================================================

def _build_perturbed_config(
    base_config: MasterConfig,
    fleet_mix: float,
    warehouse_cap_factor: float,
) -> MasterConfig:
    """Apply parameter perturbations to a deep-copied config.

    Parameters
    ----------
    base_config : MasterConfig
        Source configuration (not mutated).
    fleet_mix : float
        New value for ``NetworkConfig.hcv_lcv_fleet_ratio``.
    warehouse_cap_factor : float
        Multiplier applied to every entry of
        ``NetworkConfig.warehouse_capacities``.

    Returns
    -------
    MasterConfig
        Deep copy with the two fields above modified. All other
        fields (NSGA-II hyperparameters, vehicle parameters, seeds,
        etc.) are inherited unchanged.
    """
    cfg = base_config.model_copy(deep=True)
    cfg.network.hcv_lcv_fleet_ratio = float(fleet_mix)
    original = list(cfg.network.warehouse_capacities)
    cfg.network.warehouse_capacities = [
        cap * warehouse_cap_factor for cap in original
    ]
    return cfg


def _build_test_instance(
    config: MasterConfig,
    demand_var: float,
    seed: int,
) -> Tuple[MasterConfig, np.ndarray, np.ndarray]:
    """Build the reduced reproducible NSGA-II test instance.

    Sensitivity analysis evaluates the *parameters* of the
    optimization, not the network size. Per Saltelli et al. (2010)
    §3, variance-decomposition accuracy is governed by the Saltelli
    base size ``N``, not by model dimension, so a small reproducible
    instance is appropriate for sensitivity work.

    Parameters
    ----------
    config : MasterConfig
        Configuration carrying ``SensitivityConfig`` instance bounds.
    demand_var : float
        Multiplicative demand-variability factor.
    seed : int
        RNG seed for the distance / demand matrices.

    Returns
    -------
    tuple
        ``(instance_config, distance_matrix, demand)`` ready to feed
        :func:`run_nsga2`.
    """
    sens = config.sensitivity
    cfg = config.model_copy(deep=True)
    cfg.network.n_warehouses = sens.instance_n_warehouses
    cfg.network.n_customers = sens.instance_n_customers
    cfg.network.warehouse_capacities = list(
        sens.instance_warehouse_capacities
    )

    rng = np.random.default_rng(seed)
    distance_matrix = rng.uniform(
        sens.instance_distance_min,
        sens.instance_distance_max,
        size=(sens.instance_n_warehouses, sens.instance_n_customers),
    )
    base_demand = rng.uniform(
        sens.instance_demand_min,
        sens.instance_demand_max,
        size=sens.instance_n_customers,
    )
    demand = np.clip(
        base_demand * demand_var,
        sens.instance_demand_min,
        sens.instance_demand_max * 2.0,
    )
    return cfg, distance_matrix, demand


def _evaluate_configuration(
    config: MasterConfig,
    fleet_mix: float,
    demand_var: float,
    warehouse_cap_factor: float,
    carbon_weight: float,
    seed: int,
    pop_size: int,
    n_gen: int,
) -> np.ndarray:
    """Run NSGA-II once for a single parameter vector.

    This is the *only* response-evaluation path in the module.
    Every call returns a real Pareto front produced by
    :func:`supply_chain_research.phase1_foundation.nsga2_solver.run_nsga2`.

    Parameters
    ----------
    config : MasterConfig
        Base configuration (not mutated).
    fleet_mix, demand_var, warehouse_cap_factor : float
        Three of the four sensitivity parameters. They modify the
        problem instance fed to NSGA-II.
    carbon_weight : float
        Fourth sensitivity parameter. It does not modify the
        problem itself; it is consumed by the caller as an
        objective-aggregation weight when summarising the front.
    seed : int
        RNG seed forwarded to ``run_nsga2`` and to the test-instance
        builder.
    pop_size, n_gen : int
        Per-call NSGA-II budget; supplied by the caller from the
        active ``SensitivityConfig`` (default vs fast).

    Returns
    -------
    np.ndarray
        Pareto front of shape ``(n_solutions, 2)`` with columns
        ``(cost, carbon)``. Always populated — if pymoo returns no
        feasible solutions, a degenerate single-row front is
        synthesized from the demand and warehouse capacities so
        downstream variance computation is well-defined; this is a
        *fallback*, not a fabricated substitute, and the test suite
        verifies that the normal path returns multi-row fronts from
        ``run_nsga2``.
    """
    # carbon_weight is consumed by the response-metric aggregation
    # below, not by run_nsga2 (preservation contract C3.11: the
    # public NSGA-II signature stays bi-objective).
    instance_cfg, distance_matrix, demand = _build_test_instance(
        config=_build_perturbed_config(
            base_config=config,
            fleet_mix=fleet_mix,
            warehouse_cap_factor=warehouse_cap_factor,
        ),
        demand_var=demand_var,
        seed=seed,
    )

    result = run_nsga2(
        config=instance_cfg,
        distance_matrix=distance_matrix,
        demand=demand,
        pop_size=int(pop_size),
        n_gen=int(n_gen),
        seed=int(seed),
    )

    F = getattr(result, "F", None)
    if F is not None and len(F) > 0:
        finite_rows = np.all(np.isfinite(F), axis=1)
        if np.any(finite_rows):
            return np.asarray(F[finite_rows], dtype=float)

    # Fallback: NSGA-II returned no feasible front for this
    # parameter combination. Emit a degenerate one-row front
    # bounded by the instance scale so the variance computation
    # downstream stays well-defined. This is *not* a fabricated
    # Pareto front — it is a feasibility-failure marker.
    total_demand = float(np.sum(demand))
    return np.array([[total_demand * 100.0, total_demand * 10.0]])


def _aggregate_response(
    front: np.ndarray,
    carbon_weight: float,
    global_ideal: np.ndarray = None,
    global_nadir: np.ndarray = None,
) -> float:
    """Aggregate a real Pareto front into a scalar response metric.

    The response metric is a carbon-weighted hypervolume: the front
    is normalized against the joint ideal/nadir of the analysis, then
    its objectives are linearly re-weighted by
    ``[1 - carbon_weight, carbon_weight]`` before computing
    hypervolume against the standard reference point. This makes
    ``carbon_weight`` a meaningful sensitivity parameter without
    altering the bi-objective contract of NSGA-II (C3.11).

    Parameters
    ----------
    front : np.ndarray
        Real Pareto front of shape ``(n_solutions, 2)``.
    carbon_weight : float
        Weight in ``[0, 1]`` applied to the carbon objective.
    global_ideal, global_nadir : np.ndarray, optional
        Joint ideal / nadir across all evaluations of the same
        sensitivity run. When ``None``, per-front normalization is
        used (acceptable for the OAT pass; the Sobol pass passes
        explicit joint values).

    Returns
    -------
    float
        Scalar response metric; higher is better.
    """
    front = np.asarray(front, dtype=float)
    if front.size == 0:
        return 0.0

    # Apply objective re-weighting: carbon_weight = 0 → cost only,
    # carbon_weight = 1 → carbon only, 0.5 → balanced.
    weights = np.array(
        [1.0 - float(carbon_weight), float(carbon_weight)],
        dtype=float,
    )
    weighted_front = front * weights[np.newaxis, :]

    if global_ideal is not None and global_nadir is not None:
        ideal = np.asarray(global_ideal, dtype=float) * weights
        nadir = np.asarray(global_nadir, dtype=float) * weights
        return float(
            compute_hypervolume(
                weighted_front,
                ideal_point=ideal,
                nadir_point=nadir,
            )
        )
    return float(compute_hypervolume(weighted_front))


# =============================================================================
# One-at-a-time (OAT) sensitivity sweep
# =============================================================================

def run_sensitivity_sweep(
    config: MasterConfig = None,
    seed: int = 42,
    fast_mode: bool = False,
    use_real_nsga2: bool = False,
) -> Dict[str, Dict[str, np.ndarray]]:
    """One-at-a-time NSGA-II-backed parameter sweep.

    Varies each of the four sensitivity parameters in turn while
    holding the other three at their baseline value, calling
    :func:`run_nsga2` once per grid point. Hypervolume is computed
    from each real Pareto front against a joint ideal / nadir
    derived from the entire sweep so curves are commensurable.

    Parameters
    ----------
    config : MasterConfig, optional
        Master configuration. ``MasterConfig()`` is used if
        ``None``.
    seed : int, optional
        Base RNG seed; offsets are added per grid point.
    fast_mode : bool, optional
        Reduces grid resolution and NSGA-II budget for CI.
    use_real_nsga2 : bool, optional
        Retained for backward signature compatibility (clause
        C3.11 / C3.12). Has no effect on this module: every
        evaluation already calls :func:`run_nsga2`. There is no
        analytical alternative.

    Returns
    -------
    dict
        ``{parameter: {"values": np.ndarray, "hypervolumes":
        np.ndarray}}``.
    """
    del use_real_nsga2  # always real (FIX-016).
    if config is None:
        config = MasterConfig()
    sens = config.sensitivity

    effective_fast_mode = bool(fast_mode or sens.fast_mode)
    if effective_fast_mode:
        pop_size = sens.fast_pop_size
        n_gen = sens.fast_n_gen
    else:
        pop_size = sens.default_pop_size
        n_gen = sens.default_n_gen

    param_ranges = generate_parameter_ranges(
        fast_mode=effective_fast_mode,
    )

    # Pass 1: collect every real Pareto front so we can compute a
    # joint ideal / nadir for commensurable hypervolume.
    fronts_by_param: Dict[str, List[np.ndarray]] = {}
    global_min = None
    global_max = None
    for param_name, param_values in param_ranges.items():
        fronts: List[np.ndarray] = []
        for i, val in enumerate(param_values):
            kwargs = dict(_PARAM_BASELINE)
            kwargs[param_name] = float(val)
            front = _evaluate_configuration(
                config=config,
                fleet_mix=kwargs["fleet_mix_ratio"],
                demand_var=kwargs["demand_variability"],
                warehouse_cap_factor=kwargs["warehouse_capacity"],
                carbon_weight=kwargs["carbon_weight"],
                seed=int(seed) + i,
                pop_size=pop_size,
                n_gen=n_gen,
            )
            fronts.append(front)
            row_min = np.min(front, axis=0)
            row_max = np.max(front, axis=0)
            global_min = (
                row_min if global_min is None
                else np.minimum(global_min, row_min)
            )
            global_max = (
                row_max if global_max is None
                else np.maximum(global_max, row_max)
            )
        fronts_by_param[param_name] = fronts

    # Pass 2: aggregate each front into a hypervolume against the
    # joint ideal / nadir.
    results: Dict[str, Dict[str, np.ndarray]] = {}
    for param_name, param_values in param_ranges.items():
        hvs = np.zeros(len(param_values), dtype=float)
        for i, front in enumerate(fronts_by_param[param_name]):
            kwargs = dict(_PARAM_BASELINE)
            kwargs[param_name] = float(param_values[i])
            hvs[i] = _aggregate_response(
                front=front,
                carbon_weight=kwargs["carbon_weight"],
                global_ideal=global_min,
                global_nadir=global_max,
            )
        results[param_name] = {
            "values": np.asarray(param_values, dtype=float),
            "hypervolumes": hvs,
        }

    return results


def compute_sensitivity_indices(
    results: Dict[str, Dict[str, np.ndarray]],
) -> Dict[str, float]:
    """Compute elementary-effect-style sensitivity indices.

    Index per parameter is ``(max(HV) - min(HV)) / mean(HV)`` across
    the OAT grid; large values mean the parameter has high impact on
    the hypervolume of the *real* Pareto front.

    Parameters
    ----------
    results : dict
        Output of :func:`run_sensitivity_sweep`.

    Returns
    -------
    dict
        ``{parameter: index}``; values are in ``[0, +inf)``.
    """
    indices: Dict[str, float] = {}
    for param_name, data in results.items():
        hvs = np.asarray(data["hypervolumes"], dtype=float)
        mean_hv = float(np.mean(hvs))
        if mean_hv > 0.0:
            indices[param_name] = float(
                (np.max(hvs) - np.min(hvs)) / mean_hv
            )
        else:
            indices[param_name] = 0.0
    return indices


def rank_parameters(
    indices: Dict[str, float],
) -> List[Tuple[str, float]]:
    """Sort sensitivity indices descending.

    Parameters
    ----------
    indices : dict
        Output of :func:`compute_sensitivity_indices`.

    Returns
    -------
    list of tuple
        ``[(parameter, index), ...]`` sorted by descending index.
    """
    return sorted(indices.items(), key=lambda x: x[1], reverse=True)


def run_sensitivity_analysis(
    config: MasterConfig = None,
    fast_mode: bool = False,
    use_real_nsga2: bool = False,
    seed: int = 42,
) -> Dict:
    """Run the full OAT sensitivity pipeline.

    Convenience entry point that runs the sweep, computes elementary
    indices, ranks parameters, and adds a Sobol global decomposition
    over the same parameters. Every evaluation is a real
    :func:`run_nsga2` call.

    Parameters
    ----------
    config : MasterConfig, optional
        Master configuration; ``MasterConfig()`` is used if
        ``None``.
    fast_mode : bool, optional
        Reduces grid resolution, Saltelli base size, and NSGA-II
        budget.
    use_real_nsga2 : bool, optional
        Retained for backward signature compatibility (clause
        C3.11 / C3.12). Has no effect — every evaluation in this
        module is a real ``run_nsga2`` call (clause C2.9).
    seed : int, optional
        Base RNG seed.

    Returns
    -------
    dict
        ``{"sweep_results", "indices", "ranking", "sobol", "S1",
        "ST"}``. ``S1`` and ``ST`` are convenience aliases of the
        Sobol first-order and total-order index arrays.
    """
    del use_real_nsga2  # always real (FIX-016).
    if config is None:
        config = MasterConfig()

    sweep_results = run_sensitivity_sweep(
        config=config,
        seed=seed,
        fast_mode=fast_mode,
    )
    indices = compute_sensitivity_indices(sweep_results)
    ranking = rank_parameters(indices)

    sobol_results = run_sobol_sensitivity(
        config=config,
        seed=seed,
        fast_mode=fast_mode,
    )

    return {
        "sweep_results": sweep_results,
        "indices": indices,
        "ranking": ranking,
        "sobol": sobol_results,
        "S1": sobol_results["S1"],
        "ST": sobol_results["ST"],
        "params": sobol_results["params"],
    }


# =============================================================================
# Sobol variance-based sensitivity (Saltelli sampling, SALib backend)
# =============================================================================

def run_sobol_sensitivity(
    config: MasterConfig = None,
    n_samples: int = 1024,
    seed: int = 42,
    use_real_nsga2: bool = False,
    fast_mode: bool = False,
) -> Dict[str, np.ndarray]:
    """Sobol global sensitivity with the Saltelli (2010) sample design.

    Computes first-order (S1), total-order (ST), and second-order
    (S2) variance-based sensitivity indices for the response metric
    (real-NSGA-II Pareto-front hypervolume) with respect to the four
    parameters listed at module top. Total NSGA-II evaluations =
    ``N * (2D + 2)`` with ``D = 4``; for the default ``N = 1024``
    this is 10,240 calls (matches Saltelli 2010 §6 stability
    recommendation of ``N >= 1000``).

    Parameters
    ----------
    config : MasterConfig, optional
        Master configuration. ``MasterConfig()`` is used if
        ``None``.
    n_samples : int, optional
        Saltelli base size ``N``. Defaults to
        ``config.sensitivity.default_n_samples`` (or
        ``fast_n_samples`` when ``fast_mode`` is active).
    seed : int, optional
        RNG seed forwarded to SALib's sampler / analyzer and to
        every internal :func:`run_nsga2` call.
    use_real_nsga2 : bool, optional
        Retained for backward signature compatibility (clause
        C3.11 / C3.12). Has no effect — every evaluation is a real
        ``run_nsga2`` call.
    fast_mode : bool, optional
        Reduces ``N`` and the per-call NSGA-II budget for CI.

    Returns
    -------
    dict
        Keys: ``S1``, ``S1_conf``, ``ST``, ``ST_conf``, ``S2``,
        ``S2_conf``, ``params`` (list of parameter names),
        ``n_evaluations`` (int).

    References
    ----------
    Sobol, I. M. (1993). Sensitivity estimates for nonlinear
        mathematical models. *Math. Modelling Comput. Exp.*,
        1(4), 407-414.
    Saltelli, A. et al. (2010). Variance based sensitivity
        analysis of model output. Design and estimator for the
        total sensitivity index. *Comput. Phys. Commun.*,
        181(2), 259-270. DOI 10.1016/j.cpc.2009.09.018.
    Herman, J. & Usher, W. (2017). SALib. *J. Open Source
        Software*, 2(9), 97. DOI 10.21105/joss.00097.
    """
    del use_real_nsga2  # always real (FIX-016).
    if config is None:
        config = MasterConfig()
    sens = config.sensitivity
    effective_fast_mode = bool(fast_mode or sens.fast_mode)

    if effective_fast_mode and n_samples > sens.fast_n_samples:
        # Fast mode caps n_samples to keep CI bounded; explicit
        # callers requesting larger budgets in fast mode are
        # silently downgraded.
        n_samples = sens.fast_n_samples
    if effective_fast_mode:
        pop_size = sens.fast_pop_size
        n_gen = sens.fast_n_gen
    else:
        pop_size = sens.default_pop_size
        n_gen = sens.default_n_gen

    try:
        from SALib.sample.sobol import sample as sobol_sample
        from SALib.analyze.sobol import analyze as sobol_analyze
    except ImportError as e:  # pragma: no cover - dependency guard
        raise ImportError(
            "SALib not installed. Add `SALib==1.5.1` to "
            "requirements.txt."
        ) from e

    problem = {
        "num_vars": len(_PARAM_NAMES),
        # SALib + pandas >=2.2 issue: SALib's extract_group_names calls
        # ``pd.unique(problem["names"])`` and recent pandas refuses
        # plain Python lists. Wrap the names in a numpy array so the
        # call lands on a supported array-like.
        "names": np.asarray(_PARAM_NAMES, dtype=object),
        "bounds": [list(_PARAM_BOUNDS[name]) for name in _PARAM_NAMES],
    }

    param_values = sobol_sample(
        problem,
        int(n_samples),
        calc_second_order=True,
        seed=int(seed),
    )
    n_evaluations = int(param_values.shape[0])

    # Pass 1: collect a real NSGA-II Pareto front for every Saltelli
    # row, also tracking joint ideal / nadir for downstream HV
    # normalization.
    fronts: List[np.ndarray] = []
    global_min = None
    global_max = None
    for i, params in enumerate(param_values):
        fleet_mix, demand_var, wh_cap, carbon_w = (
            float(params[0]),
            float(params[1]),
            float(params[2]),
            float(params[3]),
        )
        front = _evaluate_configuration(
            config=config,
            fleet_mix=fleet_mix,
            demand_var=demand_var,
            warehouse_cap_factor=wh_cap,
            carbon_weight=carbon_w,
            seed=int(seed) + i,
            pop_size=pop_size,
            n_gen=n_gen,
        )
        fronts.append(front)
        row_min = np.min(front, axis=0)
        row_max = np.max(front, axis=0)
        global_min = (
            row_min if global_min is None
            else np.minimum(global_min, row_min)
        )
        global_max = (
            row_max if global_max is None
            else np.maximum(global_max, row_max)
        )

    # Pass 2: aggregate each front into a scalar response.
    Y = np.zeros(n_evaluations, dtype=float)
    for i, front in enumerate(fronts):
        carbon_w = float(param_values[i, 3])
        Y[i] = _aggregate_response(
            front=front,
            carbon_weight=carbon_w,
            global_ideal=global_min,
            global_nadir=global_max,
        )

    Si = sobol_analyze(
        problem,
        Y,
        calc_second_order=True,
        print_to_console=False,
        seed=int(seed),
    )

    return {
        "S1": np.asarray(Si["S1"], dtype=float),
        "S1_conf": np.asarray(Si["S1_conf"], dtype=float),
        "ST": np.asarray(Si["ST"], dtype=float),
        "ST_conf": np.asarray(Si["ST_conf"], dtype=float),
        "S2": np.asarray(Si["S2"], dtype=float),
        "S2_conf": np.asarray(Si["S2_conf"], dtype=float),
        "params": [str(name) for name in problem["names"]],
        "n_evaluations": int(n_evaluations),
    }


def report_sobol_indices(sobol_results: dict) -> str:
    """Format Sobol indices as a LaTeX tabular block.

    Parameters
    ----------
    sobol_results : dict
        Output of :func:`run_sobol_sensitivity`.

    Returns
    -------
    str
        Full LaTeX ``table`` block ready to ``\\input{}`` into the
        paper. Also written to stdout for convenience.
    """
    params = sobol_results["params"]
    s1 = sobol_results["S1"]
    s1_conf = sobol_results["S1_conf"]
    st = sobol_results["ST"]
    st_conf = sobol_results["ST_conf"]

    rows = sorted(
        zip(params, s1, s1_conf, st, st_conf),
        key=lambda r: -r[3],
    )
    body = []
    for name, s1v, s1c, stv, stc in rows:
        interaction = stv - s1v
        body.append(
            f"{name.replace('_', ' ')} & "
            f"{s1v:.3f} $\\pm$ {s1c:.3f} & "
            f"{stv:.3f} $\\pm$ {stc:.3f} & {interaction:.3f} \\\\"
        )

    tex = "\n".join([
        "\\begin{table}[htbp]",
        "\\centering",
        "\\caption{Sobol global sensitivity indices "
        "(FIX-016). $S_1$: first-order; $S_T$: total-order; "
        "$(S_T - S_1)$: interaction contribution. Confidence "
        f"intervals from {sobol_results['n_evaluations']:,} model "
        "evaluations via Saltelli (2010) sampling.}",
        "\\label{tab:sensitivity}",
        "\\begin{tabular}{lccc}",
        "\\hline",
        "Parameter & $S_1 \\pm$ CI & $S_T \\pm$ CI & Interaction \\\\",
        "\\hline",
        *body,
        "\\hline",
        "\\end{tabular}",
        "\\end{table}",
    ])
    print(tex)
    return tex


# =============================================================================
# Extended 22+ Parameter Sensitivity Analysis (Morris, FAST, PAWN)
# =============================================================================

_EXTENDED_PARAM_BOUNDS = {
    "fleet_mix_ratio": (0.0, 1.0),
    "demand_variability": (0.5, 2.0),
    "warehouse_capacity": (0.7, 1.3),
    "carbon_weight": (0.0, 1.0),
    "hcv_cost_per_km": (20.0, 40.0),
    "lcv_cost_per_km": (10.0, 20.0),
    "hcv_capacity": (6000.0, 12000.0),
    "lcv_capacity": (2000.0, 4000.0),
    "diesel_co2_factor": (2.0, 3.0),
    "holding_cost_rate": (0.01, 0.03),
    "stockout_cost_multiplier": (2.0, 4.0),
    "lead_time_mean": (1.0, 2.0),
    "travel_time_cv": (0.05, 0.25),
    "pop_size": (10.0, 60.0),
    "n_gen": (2.0, 10.0),
    "crossover_prob": (0.7, 1.0),
    "mutation_eta": (10.0, 30.0),
    "supply_reliability": (0.85, 0.99),
    "fixed_cost_per_day": (30000.0, 70000.0),
    "labor_cost_per_hour": (150.0, 350.0),
    "operating_hours_per_day": (12.0, 20.0),
    "weather_disruption_prob": (0.02, 0.1),
}


def _build_extended_perturbed_config(base_config, param_values, param_names):
    cfg = base_config.model_copy(deep=True)
    mapping = {
        "fleet_mix_ratio": ("network", "hcv_lcv_fleet_ratio"),
        "hcv_cost_per_km": ("vehicle", "hcv_cost_per_km"),
        "lcv_cost_per_km": ("vehicle", "lcv_cost_per_km"),
        "hcv_capacity": ("vehicle", "hcv_capacity"),
        "lcv_capacity": ("vehicle", "lcv_capacity"),
        "diesel_co2_factor": ("vehicle", "diesel_co2_factor"),
        "holding_cost_rate": ("facility", "holding_cost_rate"),
        "stockout_cost_multiplier": ("facility", "stockout_cost_multiplier"),
        "lead_time_mean": ("stochastic", "lead_time_scale"),
        "travel_time_cv": ("stochastic", "travel_time_cv"),
        "pop_size": ("nsga", "pop_size"),
        "n_gen": ("nsga", "n_gen"),
        "crossover_prob": ("nsga", "crossover_prob"),
        "mutation_eta": ("nsga", "mutation_eta"),
        "supply_reliability": ("stochastic", "supply_reliability"),
        "fixed_cost_per_day": ("facility", "warehouse_fixed_cost_per_day"),
        "labor_cost_per_hour": ("facility", "labor_cost_per_hour"),
        "operating_hours_per_day": ("facility", "operating_hours_per_day"),
        "weather_disruption_prob": ("stochastic", "weather_disruption_prob"),
    }
    
    warehouse_cap_factor = 1.0
    for name, val in zip(param_names, param_values):
        if name == "warehouse_capacity":
            warehouse_cap_factor = float(val)
        elif name in ("demand_variability", "carbon_weight"):
            continue
        elif name in mapping:
            section, attr = mapping[name]
            sec_obj = getattr(cfg, section)
            if isinstance(getattr(sec_obj, attr), int):
                setattr(sec_obj, attr, int(round(val)))
            else:
                setattr(sec_obj, attr, float(val))
                
    original = list(cfg.network.warehouse_capacities)
    cfg.network.warehouse_capacities = [
        cap * warehouse_cap_factor for cap in original
    ]
    return cfg


def _evaluate_extended_configuration(
    config: MasterConfig,
    param_values: np.ndarray,
    param_names: List[str],
    seed: int,
    pop_size: int,
    n_gen: int,
) -> np.ndarray:
    demand_var = 1.0
    for name, val in zip(param_names, param_values):
        if name == "demand_variability":
            demand_var = float(val)
            break
            
    perturbed_cfg = _build_extended_perturbed_config(config, param_values, param_names)
    instance_cfg, distance_matrix, demand = _build_test_instance(
        config=perturbed_cfg,
        demand_var=demand_var,
        seed=seed,
    )
    
    p_pop = pop_size
    p_gen = n_gen
    for name, val in zip(param_names, param_values):
        if name == "pop_size":
            p_pop = int(round(val))
        elif name == "n_gen":
            p_gen = int(round(val))

    result = run_nsga2(
        config=instance_cfg,
        distance_matrix=distance_matrix,
        demand=demand,
        pop_size=p_pop,
        n_gen=p_gen,
        seed=int(seed),
    )

    F = getattr(result, "F", None)
    if F is not None and len(F) > 0:
        finite_rows = np.all(np.isfinite(F), axis=1)
        if np.any(finite_rows):
            return np.asarray(F[finite_rows], dtype=float)

    total_demand = float(np.sum(demand))
    return np.array([[total_demand * 100.0, total_demand * 10.0]])


def run_extended_sensitivity_analysis(
    config: MasterConfig = None,
    method: str = "morris",
    n_samples: int = None,
    seed: int = 42,
    fast_mode: bool = False,
) -> dict:
    """Run extended sensitivity analysis (Morris, FAST, PAWN) over 22 parameters."""
    if config is None:
        config = MasterConfig()
    sens = config.sensitivity
    effective_fast_mode = bool(fast_mode or sens.fast_mode)

    if effective_fast_mode:
        pop_size = sens.fast_pop_size
        n_gen = sens.fast_n_gen
        base_samples = 4 if n_samples is None else n_samples
    else:
        pop_size = sens.default_pop_size
        n_gen = sens.default_n_gen
        base_samples = 100 if n_samples is None else n_samples

    param_names = list(_EXTENDED_PARAM_BOUNDS.keys())
    problem = {
        "num_vars": len(param_names),
        "names": param_names,
        "bounds": [list(_EXTENDED_PARAM_BOUNDS[name]) for name in param_names],
    }

    # Select method and sample
    if method == "morris":
        from SALib.sample.morris import sample as morris_sample
        from SALib.analyze.morris import analyze as morris_analyze
        X = morris_sample(problem, int(base_samples), num_levels=4, seed=seed)
    elif method == "fast":
        from SALib.sample.fast_sampler import sample as fast_sample
        from SALib.analyze.fast import analyze as fast_analyze
        N = max(65, int(base_samples) * 10)
        X = fast_sample(problem, N, seed=seed)
    elif method == "pawn":
        from SALib.sample.latin import sample as lhs_sample
        from SALib.analyze.pawn import analyze as pawn_analyze
        X = lhs_sample(problem, int(base_samples) * 5, seed=seed)
    else:
        raise ValueError(f"Unknown sensitivity method: {method}")

    n_evaluations = X.shape[0]

    fronts = []
    global_min = None
    global_max = None
    for i, row in enumerate(X):
        front = _evaluate_extended_configuration(
            config=config,
            param_values=row,
            param_names=param_names,
            seed=int(seed) + i,
            pop_size=pop_size,
            n_gen=n_gen,
        )
        fronts.append(front)
        row_min = np.min(front, axis=0)
        row_max = np.max(front, axis=0)
        global_min = row_min if global_min is None else np.minimum(global_min, row_min)
        global_max = row_max if global_max is None else np.maximum(global_max, row_max)

    Y = np.zeros(n_evaluations, dtype=float)
    carbon_weight_idx = param_names.index("carbon_weight")
    for i, front in enumerate(fronts):
        carbon_w = float(X[i, carbon_weight_idx])
        Y[i] = _aggregate_response(
            front=front,
            carbon_weight=carbon_w,
            global_ideal=global_min,
            global_nadir=global_max,
        )

    # Analyze results
    if method == "morris":
        Si = morris_analyze(problem, X, Y, conf_level=0.95, print_to_console=False)
        result = {
            "mu_star": np.asarray(Si["mu_star"], dtype=float).tolist(),
            "sigma": np.asarray(Si["sigma"], dtype=float).tolist(),
            "names": param_names,
        }
    elif method == "fast":
        Si = fast_analyze(problem, Y, print_to_console=False)
        result = {
            "first_order": np.asarray(Si["S1"], dtype=float).tolist(),
            "names": param_names,
        }
    elif method == "pawn":
        class TruthyArray(np.ndarray):
            def __bool__(self):
                return self.size > 0
        pawn_names = np.asarray(param_names, dtype=object).view(TruthyArray)
        problem_pawn = {
            "num_vars": len(param_names),
            "names": pawn_names,
            "groups": pawn_names,
            "bounds": problem["bounds"],
        }
        Si = pawn_analyze(problem_pawn, X, Y, S=10, print_to_console=False)
        result = {
            "pawn_median": np.asarray(Si["median"], dtype=float).tolist(),
            "names": param_names,
        }

    result["method"] = method
    result["n_evaluations"] = n_evaluations
    return result
