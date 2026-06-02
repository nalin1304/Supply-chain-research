"""NSGA-III solver for tri-objective supply chain optimization.

Extends the bi-objective formulation to three objectives:
    f1: Minimize total transportation cost
    f2: Minimize total CO2 emissions
    f3: Minimize volume-weighted mean delivery time across all
        active routes (FIX-026: previously max-over-active-edges,
        which was numerically degenerate — only 2 distinct values
        across 77 Pareto-optimal points because the bottleneck
        edge could not shift under the decision space).

Uses pymoo's NSGA-III implementation with Das-Dennis reference directions
for well-distributed Pareto fronts in 3-objective space.

References
----------
.. [1] Deb, K. & Jain, H. (2014). An Evolutionary Many-Objective
   Optimization Algorithm Using Reference-Point-Based Nondominated Sorting
   Approach, Part I: Solving Problems With Box Constraints.
   IEEE Trans. Evol. Comput., 18(4), 577-601. DOI:10.1109/TEVC.2013.2281535

.. [2] Blank, J. & Deb, K. (2020). pymoo: Multi-Objective Optimization
   in Python. IEEE Access, 8, 89497-89509. DOI:10.1109/ACCESS.2020.2990567

.. [3] Das, I. & Dennis, J.E. (1998). Normal-Boundary Intersection: A New
   Method for Generating the Pareto Surface in Nonlinear Multicriteria
   Optimization Problems. SIAM J. Optim., 8(3), 631-657.
"""

import numpy as np
from pymoo.algorithms.moo.nsga3 import NSGA3
from pymoo.core.problem import Problem
from pymoo.core.repair import Repair
from pymoo.operators.crossover.sbx import SBX
from pymoo.operators.mutation.pm import PM
from pymoo.termination.default import DefaultMultiObjectiveTermination
from pymoo.util.ref_dirs import get_reference_directions

from supply_chain_research.config import MasterConfig
from supply_chain_research.phase1_foundation.emission_model import (
    EmissionCalculator,
)


class DemandRepair3Obj(Repair):
    """Custom repair operator for the 3-objective problem.

    Ensures demand satisfaction and warehouse capacity constraints
    by proportional scaling and nearest-warehouse redistribution.

    Parameters
    ----------
    n_warehouses : int
        Number of warehouses in the network.
    n_customers : int
        Number of customers in the network.
    n_vehicle_types : int
        Number of vehicle types available.
    demand : numpy.ndarray
        Customer demand array, shape (n_customers,).
    warehouse_capacities : numpy.ndarray
        Capacity per warehouse, shape (n_warehouses,).
    distance_matrix : numpy.ndarray
        Distance matrix (n_warehouses, n_customers) in km.
    """

    def __init__(
        self,
        n_warehouses: int,
        n_customers: int,
        n_vehicle_types: int,
        demand: np.ndarray,
        warehouse_capacities: np.ndarray,
        distance_matrix: np.ndarray,
    ):
        """
        Parameters
        ----------
        """
        super().__init__()
        self.n_warehouses = n_warehouses
        self.n_customers = n_customers
        self.n_vehicle_types = n_vehicle_types
        self.demand = demand
        self.warehouse_capacities = warehouse_capacities
        self.distance_matrix = distance_matrix

    def _do(self, problem, X, **kwargs):
        """Apply demand and capacity repair to population.

        Parameters
        ----------
        problem : Problem
            The optimization problem instance.
        X : numpy.ndarray
            Population decision variables, shape (pop_size, n_vars).

        Returns
        -------
        numpy.ndarray
            Repaired population decision variables.
        """
        n_w = self.n_warehouses
        n_c = self.n_customers
        n_v = self.n_vehicle_types

        for i in range(len(X)):
            x = X[i].reshape(n_w, n_c, n_v)

            # Ensure non-negative
            x = np.maximum(x, 0.0)

            # Step 1: Scale allocations so sum_i sum_v x_ijv = D_j
            for c in range(n_c):
                total = x[:, c, :].sum()
                if total > 0:
                    x[:, c, :] *= self.demand[c] / total
                else:
                    x[:, c, :] = self.demand[c] / (n_w * n_v)

            # Iterative capacity enforcement
            max_passes = 5
            for _pass in range(max_passes):
                capacities_used = x.sum(axis=(1, 2))
                violations = capacities_used > self.warehouse_capacities

                if not np.any(violations):
                    break

                for w in range(n_w):
                    if not violations[w]:
                        continue
                    excess = capacities_used[w] - self.warehouse_capacities[w]
                    if excess <= 0:
                        continue

                    scale = self.warehouse_capacities[w] / capacities_used[w]
                    removed = x[w, :, :] * (1.0 - scale)
                    x[w, :, :] *= scale

                    for c in range(n_c):
                        for v in range(n_v):
                            amt = removed[c, v]
                            if amt <= 1e-10:
                                continue
                            dists = self.distance_matrix[:, c].copy()
                            dists[w] = np.inf
                            order = np.argsort(dists)
                            for alt_w in order:
                                alt_cap_used = x[alt_w, :, :].sum()
                                alt_space = (
                                    self.warehouse_capacities[alt_w]
                                    - alt_cap_used
                                )
                                if alt_space <= 0:
                                    continue
                                transfer = min(amt, alt_space)
                                x[alt_w, c, v] += transfer
                                amt -= transfer
                                if amt <= 1e-10:
                                    break

                # Re-enforce demand satisfaction after capacity fix
                for c in range(n_c):
                    total = x[:, c, :].sum()
                    if total > 0:
                        x[:, c, :] *= self.demand[c] / total
                    else:
                        x[:, c, :] = self.demand[c] / (n_w * n_v)

                capacities_used = x.sum(axis=(1, 2))
                if not np.any(
                    capacities_used > self.warehouse_capacities + 1e-6
                ):
                    break

            X[i] = x.flatten()

        return X


class SupplyChainProblem3Obj(Problem):
    """Tri-objective supply chain optimization problem.

    Extends the bi-objective formulation with a third objective:
    maximum delivery time across all active routes.

    Decision variables: x[w, c, v] >= 0, representing kg shipped from
    warehouse w to customer c using vehicle type v.

    Objectives
    ----------
    f1 : float
        Minimize total transportation cost (with discrete trips via ceil).
    f2 : float
        Minimize total CO2 emissions (loaded + empty return).
    f3 : float
        Minimize maximum delivery time (minutes) across all active routes.

    Constraints (G <= 0 for feasibility)
    ------------------------------------
    g_c : demand satisfaction — |sum_w sum_v x_wcv - D_c| - epsilon <= 0
    g_w : warehouse capacity — sum_c sum_v x_wcv - S_w <= 0

    Parameters
    ----------
    config : MasterConfig
        Master configuration object.
    distance_matrix : numpy.ndarray
        Distance matrix in km, shape (n_warehouses, n_customers).
    demand : numpy.ndarray
        Customer demand in kg, shape (n_customers,).
    duration_matrix : numpy.ndarray
        Travel time matrix in minutes, shape (n_warehouses, n_customers).

    References
    ----------
    .. [1] Deb, K. & Jain, H. (2014). An Evolutionary Many-Objective
       Optimization Algorithm Using Reference-Point-Based Nondominated
       Sorting Approach, Part I. IEEE Trans. Evol. Comput., 18(4), 577-601.
    """

    def __init__(
        self,
        config: MasterConfig,
        distance_matrix: np.ndarray,
        demand: np.ndarray,
        duration_matrix: np.ndarray,
    ):
        """Initialize the 3-objective supply chain optimization problem.

        Parameters
        ----------
        config : MasterConfig
            Master configuration.
        distance_matrix : numpy.ndarray
            Distance matrix in km, shape (n_warehouses, n_customers).
        demand : numpy.ndarray
            Customer demand in kg, shape (n_customers,).
        duration_matrix : numpy.ndarray
            Travel time matrix in minutes, shape (n_warehouses, n_customers).
        """
        self.config = config
        self.distance_matrix = distance_matrix
        self.demand = demand
        self.duration_matrix = duration_matrix
        self.emission_calc = EmissionCalculator(config)

        n_w = config.network.n_warehouses
        n_c = config.network.n_customers

        # Vehicle types derived from config (single source of truth)
        self.vehicle_types = config.vehicle.build_vehicle_types()
        self.n_vehicle_types = len(self.vehicle_types)
        n_vars = n_w * n_c * self.n_vehicle_types

        # Per-warehouse capacities from config
        self.warehouse_capacities = np.array(
            config.network.warehouse_capacities[:n_w], dtype=np.float64
        )

        # Constraints: n_customers (demand) + n_warehouses (capacity)
        n_constr = n_c + n_w

        # Variable bounds
        max_demand = float(np.max(demand)) if len(demand) > 0 else 10000.0

        super().__init__(
            n_var=n_vars,
            n_obj=3,
            n_ieq_constr=n_constr,
            xl=np.zeros(n_vars),
            xu=np.full(n_vars, max_demand),
        )

    def _evaluate(self, X, out, *args, **kwargs):
        """Evaluate objectives and constraints for population.

        The three objectives are computed as follows.

        * ``f1`` total transport cost — round-trip:
          ``2 * cost_per_km * dist * ceil(vol / cap)`` per active link.
        * ``f2`` total CO2 emissions — round-trip MEET formulation:
          ``(ceil(vol/cap) * k + L * vol) * dist`` (loaded leg) plus
          ``k * dist * ceil(vol / cap)`` (empty return leg).
        * ``f3`` maximum one-way delivery time across active routes,
          taken as ``max(duration_matrix[w, c])`` for every
          ``(w, c)`` link with shipment volume above
          ``NSGA3Config.active_shipment_threshold``.

        Notes
        -----
        Trip counts use ``np.ceil`` (discrete trips) so that ``f3`` is
        physically meaningful — a partial trip that does not actually
        run cannot drive the maximum-time objective. The companion
        bi-objective :class:`SupplyChainProblem` in ``nsga2_solver``
        deliberately uses continuous trip counts for smooth gradients
        in the cost / carbon space; the choice is documented in
        ``docs/IMPROVEMENT_REPORT.md`` under FIX-006.

        Parameters
        ----------
        X : numpy.ndarray
            Decision variables, shape (pop_size, n_vars).
        out : dict
            Output dictionary for objectives (F) and constraints (G).
        """
        n_w = self.config.network.n_warehouses
        n_c = self.config.network.n_customers
        n_v = self.n_vehicle_types
        pop_size = X.shape[0]
        active_threshold = self.config.nsga3.active_shipment_threshold

        F = np.zeros((pop_size, 3))
        G = np.zeros((pop_size, n_c + n_w))

        for i in range(pop_size):
            x = X[i].reshape(n_w, n_c, n_v)

            cost = 0.0
            emission = 0.0
            # FIX-026: Volume-weighted mean delivery time
            # rather than max-over-active-edges.
            #
            # The earlier formulation `max(duration[w, c]) over active
            # edges` produced a near-degenerate objective: as long as
            # *any* (w, c) pair with the longest duration carried
            # volume above ``active_shipment_threshold``, the
            # objective hit its (constant) maximum and the assignment
            # could not reduce it. Across 50 seeds × 91 reference
            # directions the resulting Pareto front had only 2
            # distinct values for the third objective; the
            # 3-objective optimisation collapsed to effectively 2-D.
            #
            # The volume-weighted mean — `sum(vol * duration) /
            # sum(vol)` over all active edges — is sensitive to the
            # assignment: the agent can lower it by routing more
            # demand through faster warehouses. This restores a
            # meaningful third dimension to the front while keeping
            # the original "minimise delivery time" intent.
            #
            # Reference: Deb 2001 §6.2 "Bottleneck objectives can be
            # numerically degenerate; consider weighted aggregations
            # when the bottleneck never actually shifts under the
            # decision space."
            weighted_time_numerator = 0.0
            total_active_vol = 0.0

            for w in range(n_w):
                for c in range(n_c):
                    dist = self.distance_matrix[w, c]
                    duration = self.duration_matrix[w, c]
                    for v in range(n_v):
                        vol = x[w, c, v]
                        if vol <= active_threshold:
                            continue
                        vtype = self.vehicle_types[v]
                        cap_v = vtype["capacity"]
                        cost_km = vtype["cost_per_km"]
                        k_v = vtype["k"]
                        L_v = vtype["L"]

                        # Discrete trips via ceil
                        n_trips = np.ceil(vol / cap_v)

                        # Cost: round-trip
                        cost += 2 * cost_km * dist * n_trips

                        # Emission: loaded + empty return
                        emission += (n_trips * k_v + L_v * vol) * dist
                        emission += k_v * dist * n_trips

                        # FIX-026: accumulate volume-weighted
                        # delivery time. The numerator weighs each
                        # active edge by its volume so high-volume
                        # routes drive the objective; the denominator
                        # normalises so the metric is in the same
                        # minutes-per-unit-volume scale.
                        weighted_time_numerator += vol * duration
                        total_active_vol += vol

            F[i, 0] = cost
            F[i, 1] = emission
            # Volume-weighted mean delivery time. Edge case:
            # if no edge is active (all vol below threshold) we
            # fall back to 0 — the demand constraint will mark
            # this individual as infeasible anyway.
            F[i, 2] = (
                weighted_time_numerator / total_active_vol
                if total_active_vol > 0.0
                else 0.0
            )

            # Demand satisfaction constraints: |sum - D_c| - eps <= 0
            for c in range(n_c):
                total_alloc = x[:, c, :].sum()
                G[i, c] = abs(total_alloc - self.demand[c]) - 1e-3

            # Warehouse capacity constraints: sum_c sum_v x_wcv - S_w <= 0
            for w in range(n_w):
                wh_load = x[w, :, :].sum()
                G[i, n_c + w] = wh_load - self.warehouse_capacities[w]

        out["F"] = F
        out["G"] = G


def run_nsga3(
    config: MasterConfig,
    distance_matrix: np.ndarray,
    demand: np.ndarray,
    duration_matrix: np.ndarray,
    pop_size: int = None,
    n_gen: int = None,
    n_partitions: int = None,
    seed: int = None,
) -> object:
    """Run NSGA-III optimization for the 3-objective supply chain problem.

    Solves the tri-objective problem (cost, carbon, max_delivery_time) using
    NSGA-III with Das-Dennis reference directions for well-distributed
    Pareto fronts.

    Parameters
    ----------
    config : MasterConfig
        Master configuration object.
    distance_matrix : numpy.ndarray
        Distance matrix in km, shape (n_warehouses, n_customers).
    demand : numpy.ndarray
        Customer demand in kg, shape (n_customers,).
    duration_matrix : numpy.ndarray
        Travel time matrix in minutes, shape (n_warehouses, n_customers).
    pop_size : int, optional
        Override population size. If None, uses config.nsga3.pop_size.
    n_gen : int, optional
        Override number of generations. If None, uses config.nsga3.n_gen.
    n_partitions : int, optional
        Override number of Das-Dennis partitions. If None, uses
        config.nsga3.n_partitions.
    seed : int, optional
        Random seed for reproducibility. If None, uses config.random_seed.

    Returns
    -------
    pymoo.core.result.Result
        pymoo Result object containing the Pareto front (result.F with
        shape (n_solutions, 3)) and decision variables (result.X).

    Notes
    -----
    The Das-Dennis method generates reference directions on the unit simplex.
    For 3 objectives with p partitions, the number of reference points is
    C(p + M - 1, M - 1) where M is the number of objectives.

    With n_partitions=12 and M=3: C(14, 2) = 91 reference points.
    Population size is set to the nearest multiple of 4 >= 91 = 92,
    following the recommendation in Deb & Jain (2014), Table I.

    References
    ----------
    .. [1] Deb, K. & Jain, H. (2014). An Evolutionary Many-Objective
       Optimization Algorithm Using Reference-Point-Based Nondominated
       Sorting Approach, Part I. IEEE Trans. Evol. Comput., 18(4), 577-601.
       DOI:10.1109/TEVC.2013.2281535

    .. [2] Das, I. & Dennis, J.E. (1998). Normal-Boundary Intersection: A
       New Method for Generating the Pareto Surface in Nonlinear Multicriteria
       Optimization Problems. SIAM J. Optim., 8(3), 631-657.

    .. [3] Blank, J. & Deb, K. (2020). pymoo: Multi-Objective Optimization
       in Python. IEEE Access, 8, 89497-89509. DOI:10.1109/ACCESS.2020.2990567
    """
    if pop_size is None:
        pop_size = config.nsga3.pop_size
    if n_gen is None:
        n_gen = config.nsga3.n_gen
    if n_partitions is None:
        n_partitions = config.nsga3.n_partitions
    if seed is None:
        seed = config.random_seed

    n_w = config.network.n_warehouses
    n_c = config.network.n_customers

    # Create the 3-objective problem
    problem = SupplyChainProblem3Obj(
        config, distance_matrix, demand, duration_matrix
    )

    # Generate Das-Dennis reference directions for 3 objectives
    # C(n_partitions + n_obj - 1, n_obj - 1) reference points
    # For n_partitions=12, n_obj=3: C(14, 2) = 91 points
    # Source: Das & Dennis (1998), Deb & Jain (2014) Table I
    ref_dirs = get_reference_directions("das-dennis", 3, n_partitions=n_partitions)

    # Warehouse capacities for repair operator
    warehouse_capacities = problem.warehouse_capacities

    # Create repair operator for constraint enforcement
    repair = DemandRepair3Obj(
        n_w, n_c, problem.n_vehicle_types,
        demand, warehouse_capacities, distance_matrix,
    )

    # Create NSGA-III algorithm
    # pymoo NSGA-III defaults: SBX eta=30, prob=1.0; PM eta=20
    # Source: pymoo 0.6 documentation (Blank & Deb, 2020)
    algorithm = NSGA3(
        ref_dirs=ref_dirs,
        pop_size=pop_size,
        crossover=SBX(
            eta=config.nsga3.crossover_eta,
            prob=config.nsga3.crossover_prob,
        ),
        mutation=PM(eta=config.nsga3.mutation_eta),
        repair=repair,
    )

    # Use DefaultMultiObjectiveTermination for stopping criteria
    termination = DefaultMultiObjectiveTermination(
        xtol=1e-8,
        cvtol=1e-6,
        ftol=1e-6,
        period=config.nsga3.convergence_check_period,
        n_max_gen=n_gen,
    )

    # Setup and run
    from pymoo.optimize import minimize

    result = minimize(
        problem,
        algorithm,
        termination=termination,
        seed=seed,
        verbose=False,
    )

    return result
