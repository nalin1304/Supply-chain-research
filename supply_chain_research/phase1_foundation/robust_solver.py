"""Robust supply chain optimization under demand uncertainty.

Evaluates candidate solutions across ``n_scenarios`` stochastic
demand realisations sampled from a LogNormal noise model and uses
``mean + risk_lambda * std`` as the robust objective per scenario
ensemble.

When ``RobustConfig.enabled=False`` (default), :func:`run_robust_nsga2`
delegates to :func:`supply_chain_research.phase1_foundation.nsga2_solver.run_nsga2`
bit-for-bit so the deterministic Pareto front is preserved exactly
(preservation contract C3.6 of the supply-chain-research-audit
spec, ``bugfix.md``).

Demand-uncertainty model
------------------------
Each scenario ``s = 1..n_scenarios`` draws an i.i.d. LogNormal
multiplier per customer

    noise[c]      ~  LogNormal(mean=0, sigma=demand_noise_sigma)
    demand_s[c]   =  demand[c] * noise[c]

A LogNormal multiplier with ``mean=0`` of the underlying Normal is
strictly positive (no negative-demand artefacts), centred at the
baseline (``median = 1``), and recovers the deterministic demand as
``demand_noise_sigma -> 0``. This is the canonical multiplicative-noise
model used in stochastic / robust supply-chain optimisation
[BenTalNemirovski2002]_, [BertsimasSim2004]_, [MulveyVZ1995]_.

The robust objective per ensemble is

    f_robust(x)   =  mean_s f(x, demand_s) + risk_lambda * std_s f(x, demand_s)

evaluated independently for each of the two original objectives
(cost, carbon). ``risk_lambda = 0`` recovers the expected-value
formulation (Mulvey, Vanderbei & Zenios 1995 §2 "solution
robustness"); ``risk_lambda > 0`` penalises variability across
scenarios and biases the search toward solutions whose objective is
flatter under demand realisations (Bertsimas & Sim 2004 §3 "price of
robustness").

When ``enabled=False`` the deterministic
:class:`SupplyChainProblem` is solved instead — see preservation
clause C3.6 below.

References
----------
.. [BenTalNemirovski2002] Ben-Tal, A. & Nemirovski, A. (2002).
   "Robust optimization - methodology and applications."
   Mathematical Programming 92(3), 453-480.
   https://doi.org/10.1007/s101070100286
.. [BertsimasSim2004] Bertsimas, D. & Sim, M. (2004).
   "The Price of Robustness." Operations Research 52(1), 35-53.
   https://doi.org/10.1287/opre.1030.0065
.. [MulveyVZ1995] Mulvey, J. M., Vanderbei, R. J. & Zenios, S. A.
   (1995). "Robust optimization of large-scale systems."
   Operations Research 43(2), 264-281.
   https://doi.org/10.1287/opre.43.2.264
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
    DemandRepair,
    SupplyChainProblem,
    run_nsga2,
)


class RobustSupplyChainProblem(Problem):
    """Robust bi-objective supply chain optimization problem.

    Evaluates each candidate solution across n_scenarios demand draws
    and uses mean + lambda * std as the robust objectives.

    Parameters
    ----------
    config : MasterConfig
        Master configuration including robust settings.
    distance_matrix : np.ndarray
        Distance matrix in km, shape (n_warehouses, n_customers).
    demand : np.ndarray
        Baseline customer demand in kg, shape (n_customers,).

    Objectives
    ----------
    f1 : float
        Robust cost: mean(cost) + lambda * std(cost)
    f2 : float
        Robust emission: mean(emission) + lambda * std(emission)
    """

    def __init__(
        self,
        config: MasterConfig,
        distance_matrix: np.ndarray,
        demand: np.ndarray,
        scenario_seed: int = None,
    ):
        """Initialize the robust supply chain problem.

        Parameters
        ----------
        config : MasterConfig
            Master configuration.
        distance_matrix : np.ndarray
            Distance matrix in km, shape (n_warehouses, n_customers).
        demand : np.ndarray
            Baseline customer demand in kg, shape (n_customers,).
        scenario_seed : int, optional
            Seed for the demand-scenario sampler. When ``None``
            (default) ``config.random_seed`` is used so two
            ``run_robust_nsga2`` calls with identical inputs produce
            identical scenario ensembles (reproducibility, clause
            d of FIX-013).
        """
        self.config = config
        self.distance_matrix = distance_matrix
        self.demand = demand
        self.n_scenarios = config.robust.n_scenarios
        self.noise_sigma = config.robust.demand_noise_sigma
        self.risk_lambda = config.robust.risk_lambda

        n_w = config.network.n_warehouses
        n_c = config.network.n_customers
        self.n_vehicle_types = 2  # HCV, LCV

        self.vehicle_types = config.vehicle.build_vehicle_types()

        self.warehouse_capacities = np.array(
            config.network.warehouse_capacities[:n_w], dtype=np.float64
        )

        n_vars = n_w * n_c * self.n_vehicle_types
        n_constr = n_c + n_w
        max_demand = (
            float(np.max(demand))
            if len(demand) > 0
            else config.nsga.max_demand_default
        )

        # ----------------------------------------------------------------
        # Pre-generate stochastic demand scenarios from the LogNormal
        # noise model. Per [BenTalNemirovski2002]_ §2 / [BertsimasSim2004]_
        # §3 / [MulveyVZ1995]_ §2 we need a strictly-positive demand
        # multiplier with median 1 (so the deterministic case is
        # preserved as sigma -> 0). LogNormal(0, sigma) satisfies both:
        #   - support (0, +inf) -> no negative demand
        #   - median = exp(0) = 1 -> centred at the baseline
        #   - sigma -> 0 collapses to 1 (deterministic recovery)
        #
        # Pre-computing the ensemble with a fixed seed makes the
        # objective evaluation deterministic given the same inputs
        # (FIX-013 reproducibility clause d).
        # ----------------------------------------------------------------
        seed = (
            scenario_seed
            if scenario_seed is not None
            else config.random_seed
        )
        rng = np.random.default_rng(seed)
        # mean=0 (Normal mean) makes the LogNormal median = 1
        log_noise = rng.normal(
            loc=0.0, scale=self.noise_sigma, size=(self.n_scenarios, n_c)
        )
        noise = np.exp(log_noise)
        self.demand_scenarios = demand[None, :] * noise

        super().__init__(
            n_var=n_vars,
            n_obj=2,
            n_ieq_constr=n_constr,
            xl=np.zeros(n_vars),
            xu=np.full(n_vars, max_demand * 1.5),
        )

    def _evaluate_single_scenario(self, x, demand_scenario):
        """Evaluate cost and emission for a single demand scenario.

        Parameters
        ----------
        x : np.ndarray
            Decision variables reshaped to (n_w, n_c, n_v).
        demand_scenario : np.ndarray
            Demand vector for this scenario, shape (n_c,).

        Returns
        -------
        tuple
            (cost, emission) for this scenario.
        """
        n_w = self.config.network.n_warehouses
        n_c = self.config.network.n_customers
        n_v = self.n_vehicle_types

        cost = 0.0
        emission = 0.0

        for w in range(n_w):
            for c in range(n_c):
                dist = self.distance_matrix[w, c]
                for v in range(n_v):
                    vol = x[w, c, v]
                    if vol <= 0:
                        continue
                    vtype = self.vehicle_types[v]
                    cap_v = vtype["capacity"]
                    cost_km = vtype["cost_per_km"]
                    k_v = vtype["k"]
                    L_v = vtype["L"]

                    n_trips = np.ceil(vol / cap_v)
                    cost += 2 * cost_km * dist * n_trips
                    emission += (n_trips * k_v + L_v * vol) * dist
                    emission += k_v * dist * n_trips

        return cost, emission

    def _evaluate(self, X, out, *args, **kwargs):
        """Evaluate robust objectives and constraints for population.

        Parameters
        ----------
        X : np.ndarray
            Decision variables, shape (pop_size, n_vars).
        out : dict
            Output dictionary for objectives and constraints.
        """
        n_w = self.config.network.n_warehouses
        n_c = self.config.network.n_customers
        n_v = self.n_vehicle_types
        pop_size = X.shape[0]

        F = np.zeros((pop_size, 2))
        G = np.zeros((pop_size, n_c + n_w))

        for i in range(pop_size):
            x = X[i].reshape(n_w, n_c, n_v)

            # Evaluate across all scenarios
            costs = np.zeros(self.n_scenarios)
            emissions = np.zeros(self.n_scenarios)

            for s in range(self.n_scenarios):
                c_s, e_s = self._evaluate_single_scenario(
                    x, self.demand_scenarios[s]
                )
                costs[s] = c_s
                emissions[s] = e_s

            # Robust objectives: mean + lambda * std
            F[i, 0] = np.mean(costs) + self.risk_lambda * np.std(costs)
            F[i, 1] = (
                np.mean(emissions) + self.risk_lambda * np.std(emissions)
            )

            # Constraints use baseline demand
            for c in range(n_c):
                total_alloc = x[:, c, :].sum()
                G[i, c] = (
                    abs(total_alloc - self.demand[c])
                    - self.config.nsga.demand_constraint_eps
                )

            for w in range(n_w):
                wh_load = x[w, :, :].sum()
                G[i, n_c + w] = wh_load - self.warehouse_capacities[w]

        out["F"] = F
        out["G"] = G


def run_robust_nsga2(
    config: MasterConfig,
    distance_matrix: np.ndarray,
    demand: np.ndarray,
    pop_size: int = None,
    n_gen: int = None,
    seed: int = None,
) -> object:
    """Run robust NSGA-II optimization.

    When ``config.robust.enabled is False`` (default), this function
    delegates to
    :func:`supply_chain_research.phase1_foundation.nsga2_solver.run_nsga2`
    with byte-identical arguments so the deterministic Pareto front
    is preserved bit-for-bit at the same seed (preservation
    contract C3.6 of ``bugfix.md``).

    When ``config.robust.enabled is True`` the
    :class:`RobustSupplyChainProblem` is solved instead: each
    candidate solution is evaluated across
    ``config.robust.n_scenarios`` LogNormal-perturbed demand
    realisations and the bi-objective vector is replaced by

        f_robust = mean_s f(x, demand_s)
                   + config.robust.risk_lambda * std_s f(x, demand_s)

    The repair operator and the early-stopping policy are inherited
    from :func:`run_nsga2` so the only difference vs. the
    deterministic path is the ensemble inside ``Problem._evaluate``.

    Parameters
    ----------
    config : MasterConfig
        Master configuration. ``config.robust.enabled``,
        ``config.robust.n_scenarios``,
        ``config.robust.demand_noise_sigma``, and
        ``config.robust.risk_lambda`` parametrise the robust
        formulation; everything else mirrors :func:`run_nsga2`.
    distance_matrix : np.ndarray
        Distance matrix (n_warehouses, n_customers).
    demand : np.ndarray
        Baseline customer demand vector (n_customers,).
    pop_size, n_gen, seed : int, optional
        Optional overrides forwarded to NSGA-II; defaults pulled from
        ``config.nsga`` and ``config.random_seed``.

    Returns
    -------
    object
        pymoo ``Result`` object exposing ``F`` (Pareto front) and
        ``X`` (decision-variable archive).

    References
    ----------
    .. [BenTalNemirovski2002] Ben-Tal, A. & Nemirovski, A. (2002).
       Mathematical Programming 92(3), 453-480.
    .. [BertsimasSim2004] Bertsimas, D. & Sim, M. (2004).
       Operations Research 52(1), 35-53.
    .. [MulveyVZ1995] Mulvey, J. M., Vanderbei, R. J. & Zenios, S. A.
       (1995). Operations Research 43(2), 264-281.
    """
    # ------------------------------------------------------------------
    # PRESERVATION CONTRACT — clause C3.6 (bugfix.md):
    # "WHEN robust optimization is disabled
    # (MasterConfig.robust.enabled = False, the default) THEN the system
    # SHALL CONTINUE TO solve the deterministic formulation with
    # identical objective values for the same seed."
    #
    # This call MUST be byte-identical to a direct user-level
    # `run_nsga2(config, distance_matrix, demand, pop_size, n_gen, seed)`.
    # No code path in the robust module touches the random-number
    # schedule before this branch — therefore the bit-for-bit equality
    # required by C3.6 holds whether this delegation is reached lazily
    # at the start of execution or as part of an automated regression
    # sweep.
    # ------------------------------------------------------------------
    if not config.robust.enabled:
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

    # Use the caller-supplied `seed` for both the NSGA-II RNG (via
    # algorithm.setup) and the LogNormal scenario sampler so that two
    # `run_robust_nsga2(..., seed=42)` calls with identical inputs
    # produce identical fronts (FIX-013 reproducibility clause d).
    problem = RobustSupplyChainProblem(
        config, distance_matrix, demand, scenario_seed=seed,
    )

    algorithm = NSGA2(
        pop_size=pop_size,
        crossover=SBX(
            eta=config.nsga.crossover_eta,
            prob=config.nsga.crossover_prob,
        ),
        mutation=PM(eta=config.nsga.mutation_eta),
        repair=DemandRepair(
            n_w, n_c, problem.n_vehicle_types,
            demand, problem.warehouse_capacities, distance_matrix,
        ),
    )

    # Generation-by-generation execution with early stopping
    algorithm.setup(
        problem, seed=seed, verbose=False, termination=NoTermination()
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
                hv_indicator = HV(ref_point=ref_point, norm_ref_point=False)
                hv_val = hv_indicator(valid_F)
                hv_history.append(hv_val)

        if len(hv_history) >= early_stop_window:
            recent_variance = np.var(hv_history[-early_stop_window:])
            if recent_variance < early_stop_threshold:
                break

    return algorithm.result()
