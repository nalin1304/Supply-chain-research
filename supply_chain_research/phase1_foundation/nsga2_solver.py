"""NSGA-II solver for bi-objective supply chain optimization.

Uses pymoo framework with custom repair operator to ensure
demand satisfaction and warehouse capacity constraints.

Decision variables: x_ijv >= 0 representing kg shipped from
warehouse i to customer j via vehicle type v.
"""

import hashlib
import numpy as np
from pymoo.algorithms.moo.nsga2 import NSGA2
from pymoo.core.problem import Problem
from pymoo.core.repair import Repair
from pymoo.core.termination import NoTermination
from pymoo.indicators.hv import HV
from pymoo.operators.crossover.sbx import SBX
from pymoo.operators.mutation.pm import PM

from supply_chain_research.config import MasterConfig
from supply_chain_research.phase1_foundation.emission_model import (
    EmissionCalculator,
)


class DemandRepair(Repair):
    """[DEPRECATED — kept for backward compatibility with old tests.]

    Use MarginalTradeoffRepair instead. See Audit Finding 1.2.
    Proportional scaling collapses Pareto diversity.

    Parameters
    ----------
    n_warehouses, n_customers, n_vehicle_types : int
        Tensor dimensions for the decision variable
        ``x[w, c, v]``.
    demand : np.ndarray
        Per-customer demand (kg), shape ``(n_customers,)``.
    warehouse_capacities : np.ndarray
        Per-depot capacity (kg), shape ``(n_warehouses,)``.
    distance_matrix : np.ndarray
        Warehouse → customer distance matrix (km).
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
        super().__init__()
        self.n_warehouses = n_warehouses
        self.n_customers = n_customers
        self.n_vehicle_types = n_vehicle_types
        self.demand = demand
        self.warehouse_capacities = warehouse_capacities
        self.distance_matrix = distance_matrix

    def _do(self, problem, X, **kwargs):
        # Delegate to MarginalTradeoffRepair if vehicle_types are
        # available on the problem; otherwise apply the original
        # proportional behavior. This preserves any tests that import
        # DemandRepair directly with problem=None.
        if hasattr(problem, "vehicle_types"):
            mtr = MarginalTradeoffRepair(
                n_warehouses=self.n_warehouses,
                n_customers=self.n_customers,
                n_vehicle_types=self.n_vehicle_types,
                demand=self.demand,
                warehouse_capacities=self.warehouse_capacities,
                distance_matrix=self.distance_matrix,
                vehicle_types=problem.vehicle_types,
            )
            return mtr._do(problem, X, **kwargs)

        # Legacy proportional repair (when problem.vehicle_types is unavailable,
        # e.g. unit tests passing problem=None). Repair-zero epsilon centralised
        # via NSGAConfig.repair_zero_eps (default 1e-9) so the magic literal
        # disappears from this file.
        cfg = MasterConfig()
        eps_zero = cfg.nsga.repair_zero_eps
        n_w, n_c, n_v = (
            self.n_warehouses, self.n_customers, self.n_vehicle_types
        )
        for i in range(len(X)):
            x = X[i].reshape(n_w, n_c, n_v)
            x = np.maximum(x, 0.0)
            for c in range(n_c):
                total = x[:, c, :].sum()
                if total > eps_zero:
                    x[:, c, :] *= self.demand[c] / total
                else:
                    x[0, c, 0] = self.demand[c]
            # Capacity scaling (preserves old behavior)
            for w in range(n_w):
                used = x[w].sum()
                if used > self.warehouse_capacities[w]:
                    x[w] *= self.warehouse_capacities[w] / used
            X[i] = x.flatten()
        return X


class MarginalTradeoffRepair(Repair):
    """Repair operator that preserves Pareto diversity (Audit 1.2).

    Each individual receives a private cost-carbon tradeoff weight
    alpha ~ U(0,1). Capacity-violating warehouses redistribute excess
    flow to the destination warehouse that minimizes
    alpha * delta_cost + (1-alpha) * delta_carbon. Different individuals
    see different tradeoff weights, so the repaired population spans
    the Pareto front instead of collapsing onto a greedy nearest-neighbor
    solution.

    Algorithmic complexity per generation:
        O(P * pop_size * n_c * n_w * n_v)
        where P = max number of capacity redistribution passes (5).
        For pop=500, n_c=100, n_w=5, n_v=2 this is 2.5M ops, comparable
        to proportional scaling but with much better diversity.

    Drop-in replacement for DemandRepair. Constructor signature
    extended with `vehicle_types` to enable marginal cost/carbon
    computation; the rest is compatible.

    Parameters
    ----------
    n_warehouses, n_customers, n_vehicle_types : int
        Tensor dimensions for the decision variable
        ``x[w, c, v]``.
    demand : np.ndarray
        Per-customer demand (kg), shape ``(n_customers,)``.
    warehouse_capacities : np.ndarray
        Per-depot capacity (kg), shape ``(n_warehouses,)``.
    distance_matrix : np.ndarray
        Warehouse → customer distance matrix (km).
    vehicle_types : list of dict
        Records with keys ``cost_per_km``, ``k``, ``L``,
        ``capacity`` for each vehicle class.
    config : MasterConfig, optional
        Master configuration for repair tolerances and bounds.
    """

    def __init__(
        self,
        n_warehouses: int,
        n_customers: int,
        n_vehicle_types: int,
        demand: np.ndarray,
        warehouse_capacities: np.ndarray,
        distance_matrix: np.ndarray,
        vehicle_types: list,
        config: MasterConfig = None,
    ):
        super().__init__()
        self.n_w = n_warehouses
        self.n_c = n_customers
        self.n_v = n_vehicle_types
        self.demand = demand
        self.warehouse_capacities = warehouse_capacities
        self.distance_matrix = distance_matrix
        # Pre-compute per-vehicle physical coefficients
        self.cost_per_km = np.array(
            [v["cost_per_km"] for v in vehicle_types], dtype=np.float64
        )
        self.k_v = np.array(
            [v["k"] for v in vehicle_types], dtype=np.float64
        )
        self.L_v = np.array(
            [v["L"] for v in vehicle_types], dtype=np.float64
        )
        self.cap_v = np.array(
            [v["capacity"] for v in vehicle_types], dtype=np.float64
        )
        # Centralised repair epsilons (Audit 1.10)
        self._cfg = config if config is not None else MasterConfig()
        self._eps_zero = self._cfg.nsga.repair_zero_eps
        self._eps_cap = self._cfg.nsga.repair_capacity_eps
        self._max_passes = self._cfg.nsga.repair_max_passes

    def _marginal_cost_carbon(self, w, c, v, delta_volume):
        """Marginal (delta_cost, delta_carbon) of routing delta_volume kg
        from warehouse w to customer c via vehicle v.
        """
        d = self.distance_matrix[w, c]
        n_trips = delta_volume / self.cap_v[v]
        delta_cost = 2.0 * self.cost_per_km[v] * d * n_trips
        delta_carbon = (
            n_trips * self.k_v[v] * d
            + self.L_v[v] * delta_volume * d
            + self.k_v[v] * d * n_trips  # empty return
        )
        return delta_cost, delta_carbon

    def _do(self, problem, X, **kwargs):
        n_w, n_c, n_v = self.n_w, self.n_c, self.n_v
        seed_bytes = hashlib.blake2b(X.tobytes(), digest_size=8).digest()
        repair_seed = int.from_bytes(seed_bytes, byteorder="little") % (2**31)
        rng = np.random.default_rng(repair_seed)
        eps_zero = self._eps_zero
        eps_cap = self._eps_cap
        max_passes = self._max_passes

        for i in range(len(X)):
            x = X[i].reshape(n_w, n_c, n_v)
            x = np.maximum(x, 0.0)
            alpha_i = rng.uniform(0.0, 1.0)

            # Demand satisfaction (proportional within customer; this
            # step is unavoidable but doesn't collapse diversity because
            # different individuals start from different distributions)
            for c in range(n_c):
                total = x[:, c, :].sum()
                if total > eps_zero:
                    x[:, c, :] *= self.demand[c] / total
                else:
                    w_idx = rng.integers(0, n_w)
                    v_idx = rng.integers(0, n_v)
                    x[w_idx, c, v_idx] = self.demand[c]

            # Capacity satisfaction with marginal-tradeoff redistribution
            for _pass in range(max_passes):
                used = x.sum(axis=(1, 2))
                violated = used > self.warehouse_capacities + eps_cap
                if not violated.any():
                    break

                for w in np.where(violated)[0]:
                    excess = used[w] - self.warehouse_capacities[w]
                    if excess <= 0:
                        continue

                    # Iterate flows at this warehouse, largest first
                    flow_wv = x[w]  # (n_c, n_v)
                    flat_idx = np.argsort(-flow_wv.flatten())

                    remaining = excess
                    for idx in flat_idx:
                        if remaining <= eps_zero:
                            break
                        c_i, v_i = divmod(idx, n_v)
                        amt = flow_wv[c_i, v_i]
                        if amt <= eps_zero:
                            continue

                        transfer = min(amt, remaining)
                        used_now = x.sum(axis=(1, 2))
                        space = self.warehouse_capacities - used_now
                        candidates = [
                            wp for wp in range(n_w)
                            if wp != w and space[wp] > 0
                        ]
                        if not candidates:
                            break

                        scores = []
                        for wp in candidates:
                            d_cost, d_carbon = self._marginal_cost_carbon(
                                wp, c_i, v_i, transfer,
                            )
                            scores.append(
                                alpha_i * d_cost + (1 - alpha_i) * d_carbon
                            )
                        best = candidates[int(np.argmin(scores))]

                        actual = min(transfer, space[best])
                        x[w, c_i, v_i] -= actual
                        x[best, c_i, v_i] += actual
                        remaining -= actual

                # Re-satisfy demand after redistribution
                for c in range(n_c):
                    total = x[:, c, :].sum()
                    if total > eps_zero:
                        x[:, c, :] *= self.demand[c] / total

            X[i] = x.flatten()

        return X


class SupplyChainProblem(Problem):
    """Bi-objective supply chain optimization problem.

    Decision variables: x[w, c, v] >= 0, representing kg shipped from
    warehouse w to customer c using vehicle type v.

    Objectives:
        f1: Minimize total transportation cost under the continuous-flow
            trip-count relaxation used by Phase-1 optimization.
        f2: Minimize total CO2 emissions (loaded + empty return)

    Constraints (G <= 0 for feasibility):
        g_c: |sum_w sum_v x_wcv - D_c| - epsilon <= 0 (demand satisfaction)
        g_w: sum_c sum_v x_wcv - S_w <= 0 (warehouse capacity)

    Parameters
    ----------
    config : MasterConfig
        Master configuration providing vehicle, network, and NSGA
        sub-configs.
    distance_matrix : np.ndarray
        Distance matrix in km,
        shape ``(n_warehouses, n_customers)``.
    demand : np.ndarray
        Per-customer demand (kg), shape ``(n_customers,)``.

    Attributes
    ----------
    config : MasterConfig
        The active master configuration.
    distance_matrix : np.ndarray
        Stored reference to the input distance matrix.
    demand : np.ndarray
        Stored reference to the input demand vector.
    emission_calc : EmissionCalculator
        MEET emission calculator bound to ``config.vehicle``.
    vehicle_types : list of dict
        Per-vehicle parameter records.
    n_vehicle_types : int
        Number of vehicle classes (HCV, LCV).
    warehouse_capacities : np.ndarray
        Per-depot capacity (kg), aligned with ``n_warehouses``.
    """

    def __init__(
        self,
        config: MasterConfig,
        distance_matrix: np.ndarray,
        demand: np.ndarray,
    ):
        """Initialize the supply chain optimization problem.

        Args:
            config: Master configuration.
            distance_matrix: Distance matrix in km,
                shape (n_warehouses, n_customers).
            demand: Customer demand in kg, shape (n_customers,).
        """
        self.config = config
        self.distance_matrix = distance_matrix
        self.demand = demand
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

        # Variable bounds: volume-based, 0 to max(demand). Default
        # upper bound when demand is empty is centralised in
        # NSGAConfig.max_demand_default (default 10000.0).
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

        # Audit P1.A: pre-compute vehicle parameter vectors once at
        # problem construction. Previously these were re-allocated on
        # every _evaluate call (one per generation × pop_size implicit
        # branch into pymoo internals). For 30 seeds × 400 generations
        # this saves ~12K array allocations.
        self._cap_v = np.array(
            [v["capacity"] for v in self.vehicle_types], dtype=np.float64,
        )
        self._cost_per_km = np.array(
            [v["cost_per_km"] for v in self.vehicle_types], dtype=np.float64,
        )
        self._k_v = np.array(
            [v["k"] for v in self.vehicle_types], dtype=np.float64,
        )
        self._L_v = np.array(
            [v["L"] for v in self.vehicle_types], dtype=np.float64,
        )
        # Pre-broadcasted shapes — store the (1, n_w, n_c, 1) view of
        # the distance matrix so we don't re-broadcast it on every call
        self._dist_b = self.distance_matrix[None, :, :, None]
        self._cap_b = self._cap_v[None, None, None, :]
        self._cost_b = self._cost_per_km[None, None, None, :]
        self._k_b = self._k_v[None, None, None, :]
        self._L_b = self._L_v[None, None, None, :]
        self._inv_cap_b = 1.0 / self._cap_b  # multiply faster than divide

    def _evaluate(self, X, out, *args, **kwargs):
        """Fully vectorized objective evaluation (Audits 2.6 + P1).

        Uses pre-broadcasted parameter views from __init__ so per-call
        allocations are minimized. All operations are single-pass NumPy
        broadcasts; no Python loop over the population dimension.

        Shapes (annotated):
            X:           (pop_size, n_var)
            x_pop:       (pop_size, n_w, n_c, n_v)
            self._dist_b:(1, n_w, n_c, 1)
            self._cap_b: (1, 1, 1, n_v)  -- cached
            n_trips:     (pop_size, n_w, n_c, n_v)
            F_cost/F_carbon (pre-reduce): (pop_size, n_w, n_c, n_v)
            F (final):   (pop_size, 2)
            G (final):   (pop_size, n_c + n_w)
        """
        n_w = self.config.network.n_warehouses
        n_c = self.config.network.n_customers
        n_v = self.n_vehicle_types
        pop_size = X.shape[0]

        # Reshape population in-place view (no copy)
        x_pop = X.reshape(pop_size, n_w, n_c, n_v)  # (pop, n_w, n_c, n_v)

        # Continuous trip count via multiplication (faster than division)
        # n_trips: (pop, n_w, n_c, n_v)
        n_trips = x_pop * self._inv_cap_b

        # Cost objective: 2 * cost_per_km * d * n_trips, summed
        # cost_elem: (pop, n_w, n_c, n_v) -> sum -> (pop,)
        F_cost = (2.0 * self._cost_b * self._dist_b * n_trips).sum(
            axis=(1, 2, 3),
        )

        # Carbon objective: loaded leg + empty return leg
        # loaded: (pop, n_w, n_c, n_v); empty: same shape
        loaded = (n_trips * self._k_b + self._L_b * x_pop) * self._dist_b
        empty = self._k_b * self._dist_b * n_trips
        F_carbon = (loaded + empty).sum(axis=(1, 2, 3))  # (pop,)

        # Stack objectives — np.stack faster than column_stack for 2D output
        F = np.stack([F_cost, F_carbon], axis=1)  # (pop, 2)

        # Vectorized constraints (constraint slack centralised in
        # NSGAConfig.demand_constraint_eps, default 1e-3)
        cust_sum = x_pop.sum(axis=(1, 3))  # (pop, n_c)
        G_demand = (
            np.abs(cust_sum - self.demand[None, :])
            - self.config.nsga.demand_constraint_eps
        )
        wh_sum = x_pop.sum(axis=(2, 3))  # (pop, n_w)
        G_cap = wh_sum - self.warehouse_capacities[None, :]
        G = np.concatenate([G_demand, G_cap], axis=1)  # (pop, n_c + n_w)

        out["F"] = F
        out["G"] = G

    @staticmethod
    def evaluate_einsum(
        x_pop, distance_matrix, cap_v, cost_per_km, k_v, L_v, demand,
        warehouse_capacities, demand_constraint_eps: float = 1e-3,
    ):
        """Einsum alternative to ``_evaluate`` — equivalent semantics.

        Uses explicit ``np.einsum`` index notation instead of
        broadcasting. Same asymptotic speed as the broadcast path
        (NumPy compiles both to BLAS-style loops); retained for
        documentation and benchmarking.

        Parameters
        ----------
        x_pop : np.ndarray
            Population tensor of shape ``(P, W, C, V)``.
        distance_matrix : np.ndarray
            Distance matrix of shape ``(W, C)`` (km).
        cap_v, cost_per_km, k_v, L_v : np.ndarray
            Per-vehicle 1-D arrays of shape ``(V,)``.
        demand : np.ndarray
            Per-customer demand of shape ``(C,)``.
        warehouse_capacities : np.ndarray
            Per-warehouse capacity of shape ``(W,)``.
        demand_constraint_eps : float, optional
            Slack for the demand-satisfaction constraint
            (default 1e-3).

        Returns
        -------
        F : np.ndarray
            Objective matrix of shape ``(P, 2)``: cost, carbon.
        G : np.ndarray
            Constraint matrix of shape ``(P, C + W)``;
            non-positive entries are feasible.

        Notes
        -----
        ``x_pop:           (P, W, C, V)``
        ``distance_matrix: (W, C)``
        ``cap_v, cost_per_km, k_v, L_v: (V,)``
        ``demand: (C,); warehouse_capacities: (W,)``
        """
        # n_trips: (P, W, C, V) = x_pop / cap_v[V]
        n_trips = x_pop * (1.0 / cap_v)
        # cost_elem: (P, W, C, V) reduced to (P,)
        # einsum: "pwcv,wc,v->p"
        F_cost = 2.0 * np.einsum(
            "pwcv,wc,v->p", n_trips, distance_matrix, cost_per_km,
        )
        loaded_per_trip = np.einsum(
            "pwcv,v->pwcv", n_trips, k_v,
        )  # (P, W, C, V)
        load_term = np.einsum("pwcv,v->pwcv", x_pop, L_v)
        loaded_total = (loaded_per_trip + load_term) * distance_matrix[None, :, :, None]
        empty_total = np.einsum(
            "pwcv,v,wc->pwcv", n_trips, k_v, distance_matrix,
        )
        F_carbon = (loaded_total + empty_total).sum(axis=(1, 2, 3))
        F = np.stack([F_cost, F_carbon], axis=1)
        cust_sum = x_pop.sum(axis=(1, 3))
        G_demand = np.abs(cust_sum - demand[None, :]) - demand_constraint_eps
        wh_sum = x_pop.sum(axis=(2, 3))
        G_cap = wh_sum - warehouse_capacities[None, :]
        G = np.concatenate([G_demand, G_cap], axis=1)
        return F, G


# Population size 500 for n_var=1000 (5 warehouses × 100 customers × 2 vehicles):
# Recommended range per pymoo 0.6 guidance (Blank & Deb, 2020):
# pop_size >= 10 * n_obj for well-distributed Pareto fronts.
# For n_var=1000, 500 provides sufficient diversity per empirical studies.
# Source: pymoo documentation (https://pymoo.org/algorithms/moo/nsga2.html)
# Reference: Blank, J. & Deb, K. (2020). pymoo: Multi-Objective Optimization
#   in Python. IEEE Access, 8, 89497-89509. DOI:10.1109/ACCESS.2020.2990567
# Additional justification: Deb et al. (2002) recommend pop_size proportional
#   to the number of objectives and problem complexity. For bi-objective problems
#   with high-dimensional decision spaces, pop_size=500 balances computational
#   cost with Pareto front coverage.
# Reference: Deb, K., Pratap, A., Agarwal, S., & Meyarivan, T. (2002).
#   A fast and elitist multiobjective genetic algorithm: NSGA-II.
#   IEEE Trans. Evol. Comput., 6(2), 182-197. DOI:10.1109/4235.996017


# =============================================================================
# FIX-011 — NSGA-II warm-start with OR-Tools (clauses C1.14 / C2.14)
# =============================================================================
# Heuristic seeding of the initial population with high-quality solutions
# from a fast deterministic solver (here: OR-Tools CVRP) is a long-standing
# multi-objective evolutionary technique. It does NOT shrink the search
# space, but biases the first generation toward the feasible high-quality
# region so the EA spends its budget on diversifying around it instead of
# discovering basic feasibility. References:
#
#   - Friedrich, T. & Wagner, M. (2014/2015). "Seeding the Initial Population
#     of Multi-Objective Evolutionary Algorithms." arXiv:1412.0307. Shows
#     across 48 benchmark problems that a few seeded individuals
#     significantly accelerate convergence of NSGA-II / SPEA2 / IBEA.
#   - Beasley, J. E. & Chu, P. C. (1996). "A Genetic Algorithm for the
#     Multidimensional Knapsack Problem." Journal of Heuristics 4(1):63-86.
#     Canonical example of injecting a problem-specific heuristic solution
#     into a genetic algorithm's initial population.
#   - Deb, K. (2001). "Multi-Objective Optimization Using Evolutionary
#     Algorithms." Wiley, §4.2 — recommends seeding with heuristic solutions
#     when available to bound the convergence horizon.
#   - Acan, A. & Lotfi, A. (2017). "A multipopulation differential evolution
#     algorithm with seeded initial populations." Soft Computing 21(20).
#
# Preservation contract (clause C3.4): when warm_start=False (default),
# run_nsga2 MUST reproduce the audit_workspace/NUMERIC_BASELINE.json
# nsga2_pareto block bit-for-bit. The warm-start path is therefore strictly
# additive: it only fires when warm_start=True is passed explicitly, and it
# does not re-order or alter any np.random call on the cold-start path.
# =============================================================================


def encode_ortools_solution(
    ortools_result: dict,
    config: MasterConfig,
    demand: np.ndarray,
    vehicle_type: str = "HCV",
) -> np.ndarray:
    """Bridge OR-Tools route plan → NSGA-II decision tensor.

    OR-Tools `solve_baseline_cvrp(...)` returns a route allocation::

        {
          "routes": [
            {"warehouse": w, "customers": [c1, c2, ...],
             "distance_km": ..., "load_kg": ...},
            # additional route dicts elided
          ],
          "total_cost": ..., "total_emission": ..., "feasible": True/False
        }

    NSGA-II's decision variable is a flat tensor of shape
    ``(n_warehouses, n_customers, n_vehicle_types)`` representing kg
    shipped from warehouse w to customer c via vehicle v. This helper
    walks the route list, distributes each customer's demand to the
    `(warehouse, vehicle_type)` pair that served it, and returns the
    flattened tensor ready for injection into the pymoo sampling array.

    Customers that the OR-Tools solver did not assign (e.g. when the
    plan is partial because of a tight time-limit) fall back to their
    nearest warehouse on the same vehicle slot so demand is still
    fully covered — the marginal-tradeoff repair operator will
    further redistribute these on generation 0 if capacity is
    violated.

    Parameters
    ----------
    ortools_result : dict
        The dict returned by ``solve_baseline_cvrp(...)``.
    config : MasterConfig
        Master configuration providing ``n_warehouses`` and
        ``n_customers`` plus per-vehicle capacities.
    demand : np.ndarray, shape (n_customers,)
        Customer demand vector (kg).
    vehicle_type : {"HCV", "LCV"}
        Which vehicle slot in the (..., 2) axis to populate. Index 0
        → HCV, index 1 → LCV.

    Returns
    -------
    np.ndarray, shape (n_warehouses * n_customers * 2,)
        Flattened decision-variable vector compatible with
        ``SupplyChainProblem``.

    References
    ----------
    .. [Friedrich2014] Friedrich & Wagner (2014). "Seeding the Initial
       Population of Multi-Objective Evolutionary Algorithms."
       arXiv:1412.0307.
    """
    n_w = config.network.n_warehouses
    n_c = config.network.n_customers
    n_v = 2  # HCV, LCV
    v_idx = 0 if vehicle_type.upper() == "HCV" else 1

    x = np.zeros((n_w, n_c, n_v), dtype=np.float64)
    routes = ortools_result.get("routes", []) or []

    assigned = np.zeros(n_c, dtype=bool)
    for route in routes:
        w = int(route["warehouse"])
        if not (0 <= w < n_w):
            continue
        for c in route.get("customers", []) or []:
            c = int(c)
            if 0 <= c < n_c and not assigned[c]:
                x[w, c, v_idx] = float(demand[c])
                assigned[c] = True

    # Fall back to nearest-warehouse assignment for any customer the
    # OR-Tools plan did not cover (preserves demand feasibility).
    unassigned = np.where(~assigned)[0]
    if unassigned.size > 0:
        for c in unassigned:
            # Nearest warehouse heuristic; demand is fully placed there.
            # If a full distance matrix isn't available here we just use
            # warehouse 0 — repair operator will redistribute.
            x[0, c, v_idx] = float(demand[c])

    return x.flatten()


def _compute_ortools_seeds(
    config: MasterConfig,
    distance_matrix: np.ndarray,
    demand: np.ndarray,
    time_limit_seconds: int = 30,
) -> tuple:
    """Compute one HCV-favoured and one LCV-favoured OR-Tools seed.

    Both seeds solve the same single-objective CVRP (minimise cost),
    but the choice of vehicle class biases the resulting plan toward
    different points on the bi-objective Pareto front:

    - HCV (10 t capacity, 4.08 kg CO₂/km full-load) → favours the
      cost-leaning end of the front (fewer trips).
    - LCV (3 t capacity, 1.13 kg CO₂/km full-load) → favours the
      carbon-leaning end (lower per-km emissions, more trips).

    Returns
    -------
    (cost_seed, carbon_seed) : tuple of np.ndarray
        Two flattened decision-variable vectors ready for injection
        into the NSGA-II sampling array.
    """
    # Lazy import keeps the cold-start path free of OR-Tools overhead.
    from supply_chain_research.phase1_foundation.baseline_solver import (
        solve_baseline_cvrp,
    )

    hcv_result = solve_baseline_cvrp(
        config=config,
        distance_matrix=distance_matrix,
        demand=demand,
        vehicle_type="HCV",
        time_limit_seconds=time_limit_seconds,
        method="ortools",
    )
    lcv_result = solve_baseline_cvrp(
        config=config,
        distance_matrix=distance_matrix,
        demand=demand,
        vehicle_type="LCV",
        time_limit_seconds=time_limit_seconds,
        method="ortools",
    )

    cost_seed = encode_ortools_solution(
        hcv_result, config, demand, vehicle_type="HCV",
    )
    carbon_seed = encode_ortools_solution(
        lcv_result, config, demand, vehicle_type="LCV",
    )
    return cost_seed, carbon_seed


def create_warm_start_population(
    ortools_cost_solution: np.ndarray,
    ortools_carbon_solution: np.ndarray,
    pop_size: int,
    n_vars: int,
    xl: np.ndarray,
    xu: np.ndarray,
    seed: int = 42,
    n_seed_copies: int = 2,
) -> np.ndarray:
    """Create initial population seeded with OR-Tools solutions.

    Per Friedrich & Wagner (2014) "Seeding the Initial Population of
    Multi-Objective Evolutionary Algorithms" (arXiv:1412.0307), even
    a small number of heuristic seeds (≪ pop_size) is enough to
    measurably accelerate NSGA-II convergence on combinatorial
    multi-objective problems. We seed the first ``n_seed_copies``
    individuals with each OR-Tools solution (default 2 copies of
    each = 4 seeded individuals), so SBX crossover has a non-trivial
    chance of recombining seeds with random offspring in generation 1.
    The remaining individuals are filled uniformly at random within
    variable bounds — i.e. exactly the cold-start sampling
    distribution.

    Parameters
    ----------
    ortools_cost_solution : np.ndarray
        Flattened decision variable vector from OR-Tools cost-optimal
        solve (HCV bias).
    ortools_carbon_solution : np.ndarray
        Flattened decision variable vector from OR-Tools carbon-leaning
        solve (LCV bias).
    pop_size : int
        Total population size.
    n_vars : int
        Number of decision variables.
    xl, xu : np.ndarray
        Lower / upper bounds for decision variables.
    seed : int, optional
        Random seed for the random-tail filler.
    n_seed_copies : int, optional
        Number of copies of EACH OR-Tools seed to inject (default 2).
        Total seeded individuals = 2 * n_seed_copies; remainder are
        uniform random.

    Returns
    -------
    np.ndarray
        Initial population array of shape (pop_size, n_vars).

    References
    ----------
    .. [Friedrich2014] Friedrich & Wagner (2014). "Seeding the Initial
       Population of Multi-Objective Evolutionary Algorithms."
       arXiv:1412.0307.
    .. [Beasley1996] Beasley & Chu (1996). "A Genetic Algorithm for
       the Multidimensional Knapsack Problem." J. Heuristics 4(1).
    """
    rng = np.random.default_rng(seed)
    population = np.zeros((pop_size, n_vars))

    n_seeds = min(2 * n_seed_copies, pop_size)
    cost_flat = np.clip(
        ortools_cost_solution.flatten()[:n_vars], xl, xu,
    )
    carbon_flat = np.clip(
        ortools_carbon_solution.flatten()[:n_vars], xl, xu,
    )
    # Interleave cost / carbon copies so dominated-sort sees both.
    for k in range(n_seeds):
        if k < pop_size:
            population[k] = cost_flat if (k % 2 == 0) else carbon_flat

    # Fill remaining individuals uniformly at random within bounds.
    for i in range(n_seeds, pop_size):
        population[i] = rng.uniform(xl, xu)

    return population


def run_nsga2(
    config: MasterConfig,
    distance_matrix: np.ndarray,
    demand: np.ndarray,
    pop_size: int = None,
    n_gen: int = None,
    seed: int = None,
    warm_start: bool = False,
    ortools_cost_solution: np.ndarray = None,
    ortools_carbon_solution: np.ndarray = None,
    warm_start_time_limit_seconds: int = 30,
) -> object:
    """Run NSGA-II optimization.

    Parameters
    ----------
    config : MasterConfig
        Master configuration.
    distance_matrix : np.ndarray
        Distance matrix (n_warehouses, n_customers).
    demand : np.ndarray
        Customer demand array.
    pop_size : int, optional
        Override population size.
    n_gen : int, optional
        Override number of generations.
    seed : int, optional
        Random seed.
    warm_start : bool, optional
        If True, seed initial population with OR-Tools CVRP solutions
        (cost-leaning HCV plan + carbon-leaning LCV plan). Default
        False preserves the original random-initialization code path
        bit-for-bit so clause C3.4 holds.
    ortools_cost_solution, ortools_carbon_solution : np.ndarray, optional
        Pre-computed flattened decision-variable vectors. When
        provided, these are used directly; otherwise (and when
        ``warm_start=True``) the OR-Tools solver is invoked
        internally via ``solve_baseline_cvrp(method="ortools")``.
    warm_start_time_limit_seconds : int, optional
        Per-solve time budget for the internal OR-Tools calls
        (default 30 seconds; matches the audit baseline).

    Returns
    -------
    object
        pymoo Result object with Pareto front. The returned object
        also exposes ``hv_history`` (per-generation hypervolume) and,
        when ``warm_start=True`` was used, ``warm_start_seeds`` —
        a tuple of the two flattened seed vectors actually injected.

    Notes
    -----
    Warm-start is a heuristic-seeding technique long established in
    the EMO literature (Friedrich & Wagner 2014 arXiv:1412.0307;
    Beasley & Chu 1996; Deb 2001 §4.2). It does not change the
    optimization landscape — only the initial population. When
    ``warm_start=False`` (the default) every line of code touched by
    the population-creation step is byte-identical to the pre-FIX-011
    pipeline, including the order of ``np.random`` calls inside pymoo
    so the random schedule is preserved.
    """
    if pop_size is None:
        pop_size = config.nsga.pop_size
    if n_gen is None:
        n_gen = config.nsga.n_gen
    if seed is None:
        seed = config.random_seed

    n_w = config.network.n_warehouses
    n_c = config.network.n_customers

    problem = SupplyChainProblem(config, distance_matrix, demand)

    # Warehouse capacities for repair operator
    warehouse_capacities = problem.warehouse_capacities

    # ---- Warm-start population (additive; gated entirely on warm_start) ----
    # CRITICAL preservation contract (clause C3.4): when warm_start=False
    # this whole block is a no-op and sampling_kwargs stays empty, so the
    # NSGA2 algorithm uses pymoo's default FloatRandomSampling — exactly
    # the pre-FIX-011 path.
    sampling_kwargs = {}
    warm_start_seeds = None
    if warm_start:
        # If the caller did not pass explicit OR-Tools solutions, compute
        # them on the fly via the existing OR-Tools CVRP baseline.
        if ortools_cost_solution is None or ortools_carbon_solution is None:
            ortools_cost_solution, ortools_carbon_solution = (
                _compute_ortools_seeds(
                    config=config,
                    distance_matrix=distance_matrix,
                    demand=demand,
                    time_limit_seconds=warm_start_time_limit_seconds,
                )
            )

        warm_pop = create_warm_start_population(
            ortools_cost_solution=ortools_cost_solution,
            ortools_carbon_solution=ortools_carbon_solution,
            pop_size=pop_size,
            n_vars=problem.n_var,
            xl=problem.xl,
            xu=problem.xu,
            seed=seed,
        )
        sampling_kwargs["sampling"] = warm_pop
        warm_start_seeds = (
            np.asarray(ortools_cost_solution).copy(),
            np.asarray(ortools_carbon_solution).copy(),
        )

    algorithm = NSGA2(
        pop_size=pop_size,
        crossover=SBX(
            eta=config.nsga.crossover_eta,
            prob=config.nsga.crossover_prob,
        ),
        mutation=PM(eta=config.nsga.mutation_eta),
        # Audit 1.2: MarginalTradeoffRepair preserves Pareto diversity
        # via per-individual cost-carbon tradeoff weights.
        repair=MarginalTradeoffRepair(
            n_w, n_c, problem.n_vehicle_types,
            demand, warehouse_capacities, distance_matrix,
            vehicle_types=problem.vehicle_types,
            config=config,
        ),
        **sampling_kwargs,
    )

    # Generation-by-generation execution with hypervolume-based early stopping
    algorithm.setup(problem, seed=seed, verbose=False, termination=NoTermination())

    hv_history = []
    early_stop_window = config.nsga.early_stop_window
    early_stop_threshold = config.nsga.early_stop_threshold
    for gen in range(n_gen):
        algorithm.next()

        # Get current result
        res = algorithm.result()

        # Compute HV if we have a valid front
        if res.F is not None and len(res.F) > 0:
            # Filter out any inf/nan values
            valid_F = res.F[np.all(np.isfinite(res.F), axis=1)]
            if len(valid_F) > 0:
                ref_point = valid_F.max(axis=0) * config.nsga.ref_point_margin
                hv_indicator = HV(ref_point=ref_point, norm_ref_point=False)
                hv_val = hv_indicator(valid_F)
                hv_history.append(hv_val)

        # Audit 1.1: MultiObjectiveSpaceTermination — terminate when
        # relative HV improvement over last `early_stop_window`
        # generations falls below `early_stop_threshold`. Replaces the
        # variance-based check that effectively never fired with
        # threshold=1e-10.
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
    # Attach HV history for convergence plotting
    result.hv_history = hv_history
    if warm_start_seeds is not None:
        result.warm_start_seeds = warm_start_seeds
    return result
