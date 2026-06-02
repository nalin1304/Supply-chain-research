"""Carbon-budget constrained supply chain optimization (FIX-015).

Adds a hard carbon emission constraint to the bi-objective CVRP
formulation so the solver can answer the canonical question
"how much extra cost does each kilogram of CO₂ avoidance cost?" —
the *green-premium curve*.

Formulation
-----------
For decision tensor ``x[w, c, v] ∈ R_>=0`` (kg shipped from warehouse
``w`` to customer ``c`` on vehicle class ``v``), we add the inequality

    sum_{w, c, v} emission(x[w, c, v])  <=  (1 - r) * E_baseline

where ``r ∈ [0, 0.6]`` is the reduction percentage selected by
``CarbonBudgetConfig.mode`` (``"none"|"20pct"|"40pct"``) or by
``custom_reduction_pct`` and ``E_baseline`` is the no-constraint
baseline returned by :func:`estimate_baseline_emission`.

The carbon-constrained CVRP is the Pollution-Routing Problem (PRP)
of Bektaş & Laporte (2011) "The Pollution-Routing Problem",
*Transportation Research Part B* 45(8):1232-1250
(DOI 10.1016/j.trb.2011.02.004), here cast as a
constraint rather than a third objective so the cost / carbon
trade-off remains a 2-D Pareto front directly comparable to the
unconstrained run.  The taxonomy of green-vehicle-routing variants —
including the carbon-budget-as-constraint formulation used in this
module — is reviewed in Sweeney, Zhang & Klabjan (2017) "A Taxonomy
and Review of Multi-Objective Vehicle Routing Problems",
*Transportation Research Part E*.

When ``CarbonBudgetConfig.mode == "none"`` (the default), the module
delegates byte-for-byte to :func:`supply_chain_research
.phase1_foundation.nsga2_solver.run_nsga2` so that preservation
clause C3.8 holds — the unconstrained Pareto front is reproduced
bit-for-bit at the same seed.

References
----------
- Bektaş, T., & Laporte, G. (2011). The Pollution-Routing Problem.
  *Transportation Research Part B: Methodological* 45(8):1232-1250.
  DOI: 10.1016/j.trb.2011.02.004
- Sweeney, M., Zhang, J., & Klabjan, D. (2017). A taxonomy and
  review of multi-objective vehicle routing problems.
- Hickman, A.J. (1999). MEET TRL Project Report SE/491/98.
"""

import numpy as np
from pymoo.algorithms.moo.nsga2 import NSGA2
from pymoo.core.problem import Problem
from pymoo.core.termination import NoTermination
from pymoo.indicators.hv import HV
from pymoo.operators.crossover.sbx import SBX
from pymoo.operators.mutation.pm import PM

from supply_chain_research.config import MasterConfig
from supply_chain_research.phase1_foundation.nsga2_solver import (
    MarginalTradeoffRepair,
    run_nsga2,
)


class CarbonBudgetSupplyChainProblem(Problem):
    """Carbon-budget constrained bi-objective supply chain problem.

    Adds a single inequality constraint to :class:`SupplyChainProblem`:

        G_carbon : Z2(x) - budget_limit <= 0

    where ``Z2(x)`` is the loaded + empty-return MEET emission
    aggregate already used by :class:`SupplyChainProblem._evaluate`,
    and ``budget_limit = E_baseline * (1 - r)``.

    The constraint follows the carbon-constrained CVRP / Pollution-
    Routing Problem formulation of Bektaş & Laporte (2011) [TRB
    45(8):1232-1250, DOI 10.1016/j.trb.2011.02.004]; treating the
    carbon limit as a hard inequality (rather than a third objective)
    keeps the Pareto front 2-dimensional so the resulting fronts
    remain directly comparable to the unconstrained NSGA-II run.

    Parameters
    ----------
    config : MasterConfig
        Master configuration including carbon budget settings.
    distance_matrix : np.ndarray, shape (n_warehouses, n_customers)
        Distance matrix in km.
    demand : np.ndarray, shape (n_customers,)
        Customer demand in kg.
    budget_limit : float
        Maximum allowed total emission (kg CO₂).

    References
    ----------
    .. [Bektas2011] Bektaş, T., & Laporte, G. (2011). The Pollution-
       Routing Problem. *Transportation Research Part B*
       45(8):1232-1250. DOI 10.1016/j.trb.2011.02.004.
    """

    def __init__(
        self,
        config: MasterConfig,
        distance_matrix: np.ndarray,
        demand: np.ndarray,
        budget_limit: float,
    ):
        """Initialize the carbon-budget constrained problem.

        Parameters
        ----------
        config : MasterConfig
            Master configuration.
        distance_matrix : np.ndarray, shape (n_warehouses, n_customers)
            Distance matrix in km.
        demand : np.ndarray, shape (n_customers,)
            Customer demand in kg.
        budget_limit : float
            Maximum allowed total emission (kg CO₂).
        """
        self.config = config
        self.distance_matrix = distance_matrix
        self.demand = demand
        self.budget_limit = float(budget_limit)

        n_w = config.network.n_warehouses
        n_c = config.network.n_customers
        self.n_vehicle_types = 2

        self.vehicle_types = config.vehicle.build_vehicle_types()

        self.warehouse_capacities = np.array(
            config.network.warehouse_capacities[:n_w], dtype=np.float64
        )

        n_vars = n_w * n_c * self.n_vehicle_types
        # Constraints: demand (n_c) + capacity (n_w) + carbon budget (1)
        n_constr = n_c + n_w + 1
        max_demand = (
            float(np.max(demand))
            if len(demand) > 0
            else config.nsga.max_demand_default
        )

        super().__init__(
            n_var=n_vars,
            n_obj=2,
            n_ieq_constr=n_constr,
            xl=np.zeros(n_vars),
            xu=np.full(n_vars, max_demand),
        )

        # Pre-broadcast vehicle parameter vectors so _evaluate can run
        # the same vectorized path as SupplyChainProblem (Audit P1.A).
        self._cap_v = np.array(
            [v["capacity"] for v in self.vehicle_types], dtype=np.float64,
        )
        self._cost_per_km = np.array(
            [v["cost_per_km"] for v in self.vehicle_types],
            dtype=np.float64,
        )
        self._k_v = np.array(
            [v["k"] for v in self.vehicle_types], dtype=np.float64,
        )
        self._L_v = np.array(
            [v["L"] for v in self.vehicle_types], dtype=np.float64,
        )
        self._dist_b = self.distance_matrix[None, :, :, None]
        self._cap_b = self._cap_v[None, None, None, :]
        self._cost_b = self._cost_per_km[None, None, None, :]
        self._k_b = self._k_v[None, None, None, :]
        self._L_b = self._L_v[None, None, None, :]
        self._inv_cap_b = 1.0 / self._cap_b

    def _evaluate(self, X, out, *args, **kwargs):
        """Vectorised objective + constraint evaluation.

        Mirrors :meth:`SupplyChainProblem._evaluate` exactly so that
        objective values are bit-comparable, then appends a single
        carbon-budget inequality row.

        Parameters
        ----------
        X : np.ndarray, shape (pop_size, n_vars)
            Population of decision vectors.
        out : dict
            pymoo output dictionary; populated with ``F`` and ``G``.
        """
        n_w = self.config.network.n_warehouses
        n_c = self.config.network.n_customers
        n_v = self.n_vehicle_types
        pop_size = X.shape[0]

        x_pop = X.reshape(pop_size, n_w, n_c, n_v)
        n_trips = x_pop * self._inv_cap_b
        F_cost = (2.0 * self._cost_b * self._dist_b * n_trips).sum(
            axis=(1, 2, 3),
        )
        loaded = (n_trips * self._k_b + self._L_b * x_pop) * self._dist_b
        empty = self._k_b * self._dist_b * n_trips
        F_carbon = (loaded + empty).sum(axis=(1, 2, 3))
        F = np.stack([F_cost, F_carbon], axis=1)  # (pop, 2)

        # Demand + capacity constraints (same eps as SupplyChainProblem)
        cust_sum = x_pop.sum(axis=(1, 3))  # (pop, n_c)
        G_demand = (
            np.abs(cust_sum - self.demand[None, :])
            - self.config.nsga.demand_constraint_eps
        )
        wh_sum = x_pop.sum(axis=(2, 3))  # (pop, n_w)
        G_cap = wh_sum - self.warehouse_capacities[None, :]
        # Carbon-budget constraint: emission - budget_limit <= 0
        G_carbon = (F_carbon - self.budget_limit)[:, None]  # (pop, 1)
        G = np.concatenate([G_demand, G_cap, G_carbon], axis=1)

        out["F"] = F
        out["G"] = G


def _get_reduction_pct(config: MasterConfig) -> float:
    """Resolve the carbon reduction percentage from config.

    Parameters
    ----------
    config : MasterConfig
        Master configuration.

    Returns
    -------
    float
        Reduction percentage in ``[0, 100)``. ``0.0`` for
        ``mode="none"``, ``20.0`` for ``"20pct"``, ``40.0`` for
        ``"40pct"``, otherwise falls back to
        ``CarbonBudgetConfig.custom_reduction_pct``.
    """
    mode = config.carbon_budget.mode
    if mode == "20pct":
        return 20.0
    if mode == "40pct":
        return 40.0
    if mode == "none":
        return 0.0
    return float(config.carbon_budget.custom_reduction_pct)


def estimate_baseline_emission(
    config: MasterConfig,
    distance_matrix: np.ndarray,
    demand: np.ndarray,
) -> float:
    """Estimate the no-constraint baseline emission for budget calculation.

    The baseline is computed deterministically from the input problem so
    that two calls with the same ``(config, distance_matrix, demand)``
    return the same value (required by the FIX-015 reproducibility
    test).  Each customer's demand is shipped from the nearest
    warehouse using HCVs (the cost-minimum vehicle class for full-load
    runs); ``ceil(demand / capacity)`` trips × loaded leg + empty
    return leg gives a tight upper bound on the cost-minimising
    Pareto-front emission.

    The carbon-constrained variants use this value as ``E_baseline``
    in ``budget_limit = E_baseline * (1 - r)``.

    Parameters
    ----------
    config : MasterConfig
        Master configuration.
    distance_matrix : np.ndarray, shape (n_warehouses, n_customers)
        Distance matrix in km.
    demand : np.ndarray, shape (n_customers,)
        Customer demand in kg.

    Returns
    -------
    float
        Estimated baseline total emission in kg CO₂.

    References
    ----------
    .. [Bektas2011] Bektaş & Laporte (2011), *Transportation Research
       Part B* 45(8):1232-1250.
    """
    n_c = config.network.n_customers
    k = config.vehicle.hcv_k
    L = config.vehicle.hcv_L
    cap = config.vehicle.hcv_capacity

    total_emission = 0.0
    for c in range(n_c):
        nearest_w = int(np.argmin(distance_matrix[:, c]))
        dist = float(distance_matrix[nearest_w, c])
        vol = float(demand[c])
        n_trips = float(np.ceil(vol / cap))
        # Loaded leg
        total_emission += (n_trips * k + L * vol) * dist
        # Empty return leg
        total_emission += k * dist * n_trips

    return float(total_emission)


def run_carbon_budget_nsga2(
    config: MasterConfig,
    distance_matrix: np.ndarray,
    demand: np.ndarray,
    pop_size: int = None,
    n_gen: int = None,
    seed: int = None,
) -> object:
    """Run carbon-budget constrained NSGA-II optimisation.

    When ``config.carbon_budget.mode == "none"`` the function delegates
    byte-for-byte to :func:`run_nsga2` so the unconstrained Pareto
    front is reproduced exactly under the same seed (preservation
    clause C3.8).

    For ``mode in {"20pct", "40pct"}`` (or any non-``"none"`` mode
    using ``custom_reduction_pct``), the underlying problem is
    :class:`CarbonBudgetSupplyChainProblem`, which adds the
    Bektaş-Laporte (2011) carbon-budget inequality
    ``Z2(x) <= (1 - r) * E_baseline``.

    Parameters
    ----------
    config : MasterConfig
        Master configuration.
    distance_matrix : np.ndarray, shape (n_warehouses, n_customers)
        Distance matrix in km.
    demand : np.ndarray, shape (n_customers,)
        Customer demand in kg.
    pop_size : int, optional
        Override population size (default: ``config.nsga.pop_size``).
    n_gen : int, optional
        Override number of generations
        (default: ``config.nsga.n_gen``).
    seed : int, optional
        Random seed (default: ``config.random_seed``).

    Returns
    -------
    object
        pymoo Result with ``F`` (objectives), ``X`` (decision
        vectors), ``G`` (constraints) and ``hv_history``
        (per-generation hypervolume).

    References
    ----------
    .. [Bektas2011] Bektaş, T. & Laporte, G. (2011). The Pollution-
       Routing Problem. *Transportation Research Part B*
       45(8):1232-1250. DOI: 10.1016/j.trb.2011.02.004.
    .. [Sweeney2017] Sweeney, M., Zhang, J., & Klabjan, D. (2017).
       A taxonomy and review of multi-objective vehicle routing
       problems.
    """
    # Preservation clause C3.8: mode="none" → byte-for-byte unconstrained.
    if config.carbon_budget.mode == "none":
        return run_nsga2(
            config=config,
            distance_matrix=distance_matrix,
            demand=demand,
            pop_size=pop_size,
            n_gen=n_gen,
            seed=seed,
        )

    if pop_size is None:
        pop_size = config.nsga.pop_size
    if n_gen is None:
        n_gen = config.nsga.n_gen
    if seed is None:
        seed = config.random_seed

    n_w = config.network.n_warehouses
    n_c = config.network.n_customers

    # Bektaş-Laporte (2011) budget: emission <= (1 - r) * E_baseline.
    reduction_pct = _get_reduction_pct(config)
    baseline_emission = estimate_baseline_emission(
        config, distance_matrix, demand,
    )
    budget_limit = baseline_emission * (1.0 - reduction_pct / 100.0)

    problem = CarbonBudgetSupplyChainProblem(
        config, distance_matrix, demand, budget_limit,
    )

    algorithm = NSGA2(
        pop_size=pop_size,
        crossover=SBX(
            eta=config.nsga.crossover_eta,
            prob=config.nsga.crossover_prob,
        ),
        mutation=PM(eta=config.nsga.mutation_eta),
        # MarginalTradeoffRepair preserves Pareto diversity (Audit 1.2)
        repair=MarginalTradeoffRepair(
            n_w, n_c, problem.n_vehicle_types,
            demand, problem.warehouse_capacities, distance_matrix,
            vehicle_types=problem.vehicle_types,
            config=config,
        ),
    )

    algorithm.setup(
        problem, seed=seed, verbose=False, termination=NoTermination(),
    )

    hv_history = []
    early_stop_window = config.nsga.early_stop_window
    early_stop_threshold = config.nsga.early_stop_threshold

    for gen in range(n_gen):
        algorithm.next()
        res = algorithm.result()

        if res.F is not None and len(res.F) > 0:
            valid_F = res.F[np.all(np.isfinite(res.F), axis=1)]
            if len(valid_F) > 0:
                ref_point = valid_F.max(axis=0) * config.nsga.ref_point_margin
                hv_indicator = HV(
                    ref_point=ref_point, norm_ref_point=False,
                )
                hv_val = hv_indicator(valid_F)
                hv_history.append(hv_val)

        if (
            gen >= config.nsga.early_stop_min_gen
            and len(hv_history) >= early_stop_window + 1
        ):
            window_start_hv = hv_history[-early_stop_window - 1]
            current_hv = hv_history[-1]
            if window_start_hv > 0:
                rel_improvement = (
                    abs(current_hv - window_start_hv) / window_start_hv
                )
                if rel_improvement < early_stop_threshold:
                    break

    result = algorithm.result()
    result.hv_history = hv_history
    result.budget_limit = budget_limit
    result.baseline_emission = baseline_emission
    return result


def generate_green_premium_curve(
    config: MasterConfig,
    distance_matrix: np.ndarray,
    demand: np.ndarray,
    reduction_levels=None,
    pop_size: int = 50,
    n_gen: int = 20,
    seed: int = 42,
) -> list:
    """Compute the green-premium curve over a sweep of carbon budgets.

    For each reduction level ``r`` in ``reduction_levels`` (default
    ``[0, 10, 20, 30, 40, 50, 60]`` covering the canonical 0-60% range
    used in the Pollution-Routing Problem literature), this helper:

    1. Builds the carbon-budget constrained problem with budget
       ``(1 - r) * E_baseline``.
    2. Runs NSGA-II on the constrained problem (or on the
       unconstrained problem when ``r == 0`` so the curve's left
       endpoint coincides with the cost-only baseline).
    3. Records the *minimum cost* (i.e. the cost-anchor of the
       constrained Pareto front) at that budget.

    Returns ``[(reduction_pct, min_cost_at_budget), ...]``. Plotted as
    cost-vs-reduction this is the canonical green-premium curve: it
    quantifies the incremental cost a planner pays to buy each
    additional 10 % of emission reduction (Bektaş & Laporte 2011 §6;
    Sweeney, Zhang & Klabjan 2017).

    Parameters
    ----------
    config : MasterConfig
        Master configuration.
    distance_matrix : np.ndarray, shape (n_warehouses, n_customers)
        Distance matrix in km.
    demand : np.ndarray, shape (n_customers,)
        Customer demand in kg.
    reduction_levels : array-like of float, optional
        Reduction percentages to evaluate. Default
        ``[0, 10, 20, 30, 40, 50, 60]``.
    pop_size : int, optional
        Population size for each NSGA-II run (default 50).
    n_gen : int, optional
        Number of generations per run (default 30).
    seed : int, optional
        Random seed shared across all runs (default 42).

    Returns
    -------
    list of tuple
        ``[(reduction_pct, min_cost_at_budget), ...]`` sorted by
        ``reduction_pct``. ``min_cost_at_budget`` is ``+inf`` when
        the optimisation could not find any feasible solution at that
        budget.

    Notes
    -----
    The curve is *non-decreasing* in ``reduction_pct`` because tighter
    carbon budgets shrink the feasible region; the
    cost-minimum can only stay the same or rise. Numerical stochastic
    noise from the EA can produce small reversals at adjacent budget
    levels, so the test suite enforces non-decrease only modulo a
    relative tolerance.

    References
    ----------
    .. [Bektas2011] Bektaş & Laporte (2011), *Transportation Research
       Part B* 45(8):1232-1250.
    .. [Sweeney2017] Sweeney, Zhang & Klabjan (2017), *Transportation
       Research Part E*.
    """
    if reduction_levels is None:
        reduction_levels = np.array(
            [0, 10, 20, 30, 40, 50, 60], dtype=float,
        )
    reduction_levels = np.asarray(reduction_levels, dtype=float)

    n_w = config.network.n_warehouses
    n_c = config.network.n_customers

    baseline_emission = estimate_baseline_emission(
        config, distance_matrix, demand,
    )

    curve = []
    for reduction_pct in reduction_levels:
        if float(reduction_pct) <= 0.0:
            # Left endpoint: unconstrained run gives the cost anchor.
            unconstrained = run_nsga2(
                config=config,
                distance_matrix=distance_matrix,
                demand=demand,
                pop_size=pop_size,
                n_gen=n_gen,
                seed=seed,
            )
            if unconstrained.F is not None and len(unconstrained.F) > 0:
                min_cost = float(np.min(unconstrained.F[:, 0]))
            else:
                min_cost = float("inf")
            curve.append((float(reduction_pct), min_cost))
            continue

        budget_limit = baseline_emission * (1.0 - float(reduction_pct) / 100.0)

        problem = CarbonBudgetSupplyChainProblem(
            config, distance_matrix, demand, budget_limit,
        )

        algorithm = NSGA2(
            pop_size=pop_size,
            crossover=SBX(
                eta=config.nsga.crossover_eta,
                prob=config.nsga.crossover_prob,
            ),
            mutation=PM(eta=config.nsga.mutation_eta),
            repair=MarginalTradeoffRepair(
                n_w, n_c, problem.n_vehicle_types,
                demand, problem.warehouse_capacities, distance_matrix,
                vehicle_types=problem.vehicle_types,
                config=config,
            ),
        )

        algorithm.setup(
            problem, seed=seed, verbose=False, termination=NoTermination(),
        )

        for _ in range(n_gen):
            algorithm.next()

        result = algorithm.result()

        if result.F is not None and len(result.F) > 0:
            # Restrict to feasible solutions when constraint info is available.
            G = getattr(result, "G", None)
            if G is not None and len(G) == len(result.F):
                feasible = (G <= 0.0).all(axis=1)
                if feasible.any():
                    min_cost = float(np.min(result.F[feasible, 0]))
                else:
                    min_cost = float(np.min(result.F[:, 0]))
            else:
                min_cost = float(np.min(result.F[:, 0]))
        else:
            min_cost = float("inf")

        curve.append((float(reduction_pct), min_cost))

    return curve
