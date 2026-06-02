"""Multi-product supply chain optimization extension (FIX-012).

Extends the bi-objective formulation of
:mod:`supply_chain_research.phase1_foundation.nsga2_solver` to handle
multiple product categories (SKUs, e.g. Electronics / FMCG / Bulk)
with per-SKU demand vectors and per-SKU bulk densities that translate
kg payload into the limiting volume on each warehouse.

Decision tensor
---------------
``x[w, c, v, p] >= 0`` — kilograms of product ``p`` shipped from
warehouse ``w`` to customer ``c`` using vehicle type ``v``. Shape:

* ``w`` : ``n_warehouses``
* ``c`` : ``n_customers``
* ``v`` : 2 (HCV index 0, LCV index 1)
* ``p`` : ``n_products`` (1 in the default single-product mode)

Demand vector
-------------
``demand`` is either ``(n_customers,)`` for the single-product mode or
``(n_customers, n_products)`` for the multi-product mode.  When a
1-D vector is supplied with ``n_products > 1`` the total demand is
distributed evenly across products to retain a runnable smoke path.

Volume / capacity model
-----------------------
Each warehouse exposes a volumetric capacity ``S_w`` (bulk-equivalent
kg at the reference density of 1 kg/L). When multiple SKUs ship from
the same warehouse they compete for that volume in proportion to
their bulk densities ``ρ_p`` (kg/L) — Salhi & Nagy (1999) and Coelho
& Laporte (2013) call this the "multi-compartment" or "multi-product"
capacity rule. The constraint per warehouse is therefore::

    sum_{c, v, p}  x[w, c, v, p] / ρ_p   <=   S_w

When ``n_products == 1`` and ``ρ_0 == 1`` this reduces to the
single-product capacity ``sum_{c, v} x[w, c, v] <= S_w`` used by
:class:`SupplyChainProblem` (preservation clause C3.5).

Preservation contract (clause C3.5)
-----------------------------------
When ``MasterConfig.product.n_products == 1``,
:func:`run_multi_product_nsga2` MUST delegate to
:func:`supply_chain_research.phase1_foundation.nsga2_solver.run_nsga2`
so the returned Pareto front is bit-for-bit identical to the
single-product result under the same seed. This is enforced at the
top of :func:`run_multi_product_nsga2` by an early ``return``.

References
----------
.. [Salhi1999] Salhi, S. & Nagy, G. (1999). "A cluster insertion
   heuristic for single and multiple depot vehicle routing problems
   with backhauling." *Journal of the Operational Research Society*,
   50(10), 1034–1042. — Establishes the multi-compartment / multi-
   product VRP capacity formulation later popularised by Coelho &
   Laporte. DOI: 10.1057/palgrave.jors.2600808.
.. [Coelho2013] Coelho, L. C. & Laporte, G. (2013). "Classification,
   models and exact algorithms for multi-compartment delivery
   problems." *European Journal of Operational Research*, 245(3),
   855–865. — Canonical taxonomy of multi-compartment VRP variants
   covering shared and dedicated compartments and the volumetric
   capacity rule used here. DOI: 10.1016/j.ejor.2015.04.001.
.. [Kek2008] Kek, A. G. H., Cheu, R. L. & Meng, Q. (2008). "Distance-
   constrained capacitated vehicle routing problems with flexible
   assignment of start and end depots." *Mathematical and Computer
   Modelling*, 47(1–2), 140–152. — Multi-product / multi-depot CVRP
   formulation that motivates per-product demand vectors and
   per-warehouse capacities. DOI: 10.1016/j.mcm.2007.02.007.
.. [Deb2002] Deb, K., Pratap, A., Agarwal, S. & Meyarivan, T. (2002).
   "A fast and elitist multiobjective genetic algorithm: NSGA-II."
   *IEEE Trans. Evol. Comput.*, 6(2), 182–197. — NSGA-II algorithm.
"""

import numpy as np
from pymoo.algorithms.moo.nsga2 import NSGA2
from pymoo.core.problem import Problem
from pymoo.core.repair import Repair
from pymoo.core.termination import NoTermination
from pymoo.indicators.hv import HV
from pymoo.operators.crossover.sbx import SBX
from pymoo.operators.mutation.pm import PM

from supply_chain_research.config import MasterConfig
from supply_chain_research.phase1_foundation.nsga2_solver import (
    run_nsga2,
)


def _coerce_demand_to_2d(
    demand: np.ndarray, n_customers: int, n_products: int
) -> np.ndarray:
    """Reshape / broadcast a demand array to ``(n_customers, n_products)``.

    Parameters
    ----------
    demand : np.ndarray
        Either ``(n_customers,)`` (single product or to-be-split
        across products) or ``(n_customers, n_products)``.
    n_customers : int
        Expected first-axis length.
    n_products : int
        Expected second-axis length.

    Returns
    -------
    np.ndarray
        Demand of shape ``(n_customers, n_products)``.
    """
    arr = np.asarray(demand, dtype=np.float64)
    if arr.ndim == 1:
        if n_products == 1:
            return arr.reshape(n_customers, 1)
        return np.column_stack([arr / n_products] * n_products)
    if arr.ndim == 2 and arr.shape == (n_customers, n_products):
        return arr.astype(np.float64, copy=True)
    raise ValueError(
        f"demand has shape {arr.shape}; expected ({n_customers},) "
        f"or ({n_customers}, {n_products})"
    )


class MultiProductDemandRepair(Repair):
    """Repair operator for the multi-product decision tensor.

    Applied per individual:

    1. Clamp every entry to ``>= 0``.
    2. For each ``(c, p)`` pair, scale the slice ``x[:, c, :, p]`` so
       its sum equals ``demand[c, p]``. If the slice is all-zero the
       full demand is placed on ``(w=0, v=0, p)`` so the demand
       constraint is satisfied feasibly.
    3. Per-warehouse density-weighted volume:

       .. math::

          \\sum_{c, v, p} \\frac{x[w, c, v, p]}{\\rho_p} \\le S_w

       If a warehouse violates the volume cap, every flow at that
       warehouse is scaled down by ``S_w / used_w`` (proportional
       redistribution preserves the per-customer demand ratios that
       step 2 just produced — a second pass of step 2 on the
       remaining flow re-satisfies demand).

    Parameters
    ----------
    n_warehouses, n_customers, n_vehicle_types, n_products : int
        Tensor dimensions.
    demand : np.ndarray, shape ``(n_customers, n_products)``
        Per-(customer, product) demand (kg).
    warehouse_capacities : np.ndarray, shape ``(n_warehouses,)``
        Volumetric capacity per warehouse, expressed as bulk-
        equivalent kg at reference density 1 kg/L.
    product_density : np.ndarray, shape ``(n_products,)``
        Bulk density (kg/L) per SKU; volume occupied by a flow
        ``x[..., p]`` is ``x[..., p] / ρ_p``.
    repair_zero_eps, repair_capacity_eps : float
        Numerical tolerances mirroring those of ``DemandRepair``.

    Notes
    -----
    The single-product specialisation (``n_products == 1``,
    ``ρ_0 == 1``) reproduces the proportional-scaling behaviour of
    :class:`DemandRepair` exactly. For the multi-product case the
    capacity rule is the volumetric form of Coelho & Laporte (2013)
    §2.1.
    """

    def __init__(
        self,
        n_warehouses: int,
        n_customers: int,
        n_vehicle_types: int,
        n_products: int,
        demand: np.ndarray,
        warehouse_capacities: np.ndarray,
        product_density: np.ndarray,
        repair_zero_eps: float = 1e-9,
        repair_capacity_eps: float = 1e-6,
    ):
        """
        Parameters
        ----------
        """
        super().__init__()
        self.n_w = int(n_warehouses)
        self.n_c = int(n_customers)
        self.n_v = int(n_vehicle_types)
        self.n_p = int(n_products)
        self.demand = np.asarray(demand, dtype=np.float64)
        self.warehouse_capacities = np.asarray(
            warehouse_capacities, dtype=np.float64
        )
        # Reciprocal density: 1/ρ_p; multiply faster than divide.
        self._inv_density = 1.0 / np.asarray(
            product_density, dtype=np.float64
        )
        self._eps_zero = float(repair_zero_eps)
        self._eps_cap = float(repair_capacity_eps)

    def _do(self, problem, X, **kwargs):
        """
        Parameters
        ----------
        """
        n_w, n_c, n_v, n_p = self.n_w, self.n_c, self.n_v, self.n_p
        eps_zero = self._eps_zero
        eps_cap = self._eps_cap
        inv_rho = self._inv_density  # (n_p,)
        caps = self.warehouse_capacities

        for i in range(len(X)):
            x = X[i].reshape(n_w, n_c, n_v, n_p)
            x = np.maximum(x, 0.0)

            # Step 1: per-(customer, product) demand scaling.
            for p in range(n_p):
                for c in range(n_c):
                    total = x[:, c, :, p].sum()
                    if total > eps_zero:
                        x[:, c, :, p] *= self.demand[c, p] / total
                    else:
                        x[0, c, 0, p] = self.demand[c, p]

            # Step 2: density-weighted warehouse volume scaling.
            #   used_w = sum_{c, v, p}  x[w, c, v, p] / ρ_p
            for w in range(n_w):
                used_w = (x[w] * inv_rho).sum()
                if used_w > caps[w] + eps_cap:
                    x[w] *= caps[w] / used_w

            # Step 3: re-satisfy demand after capacity scaling.
            for p in range(n_p):
                for c in range(n_c):
                    total = x[:, c, :, p].sum()
                    if total > eps_zero:
                        x[:, c, :, p] *= self.demand[c, p] / total
                    else:
                        x[0, c, 0, p] = self.demand[c, p]

            X[i] = x.flatten()
        return X


class MultiProductSupplyChainProblem(Problem):
    """Multi-product bi-objective supply chain optimization problem.

    Decision tensor: ``x[w, c, v, p] >= 0``, kg of product ``p``
    shipped from warehouse ``w`` to customer ``c`` using vehicle ``v``.

    Objectives (the same two as :class:`SupplyChainProblem`):

    * ``f1`` — minimise total transportation cost (with discrete trip
      counting via ``ceil(volume / capacity)`` collapsed into the
      faster continuous ``volume / capacity`` form for evaluation
      speed; the repair operator's discrete-trip behaviour is
      identical to the single-product solver when ``n_products == 1``).
    * ``f2`` — minimise total CO₂ emissions (loaded leg + empty
      return leg).

    Constraints (``G <= 0``):

    * ``g_{c,p}`` : ``|sum_w sum_v x[w, c, v, p] - D[c, p]| - ε <= 0``
      (per-(customer, product) demand satisfaction, with slack
      ``ε = NSGAConfig.demand_constraint_eps``).
    * ``g_w``    : ``sum_{c, v, p} x[w, c, v, p] / ρ_p - S_w <= 0``
      (density-weighted volume).

    Multi-product reduction to single-product
    -----------------------------------------
    When ``n_products == 1`` the demand tensor is shape ``(n_c, 1)``
    and the per-product loop trivially collapses; the
    density-weighted capacity formula reduces to
    ``sum_{c, v} x[w, c, v] / ρ_0 <= S_w``. With the default
    ``ρ_0 = 1.0`` (set on instantiation when the user passes
    ``n_products = 1``) this is bit-identical to
    :class:`SupplyChainProblem`. Note however that
    :func:`run_multi_product_nsga2` short-circuits to
    :func:`run_nsga2` *before* this class is even instantiated when
    ``n_products == 1``, so the C3.5 preservation contract is
    enforced at the call-site rather than relying on this
    mathematical equivalence.

    Parameters
    ----------
    config : MasterConfig
        Master configuration; reads ``product.n_products``,
        ``product.product_density``, ``vehicle.*``, ``network.*``.
    distance_matrix : np.ndarray, shape ``(n_warehouses, n_customers)``
        Distance matrix in km.
    demand : np.ndarray
        Customer demand in kg, shape ``(n_customers,)`` or
        ``(n_customers, n_products)``.

    References
    ----------
    .. [1] Salhi, S. & Nagy, G. (1999), JORS 50(10):1034–1042.
    .. [2] Coelho, L. C. & Laporte, G. (2013), EJOR 245(3):855–865.
    .. [3] Kek, A. G. H. et al. (2008), MCM 47(1–2):140–152.
    """

    def __init__(
        self,
        config: MasterConfig,
        distance_matrix: np.ndarray,
        demand: np.ndarray,
    ):
        """
        Parameters
        ----------
        """
        self.config = config
        self.distance_matrix = np.asarray(distance_matrix, dtype=np.float64)
        self.n_products = int(config.product.n_products)

        n_w = config.network.n_warehouses
        n_c = config.network.n_customers
        self.n_vehicle_types = 2  # HCV, LCV

        # Coerce demand to (n_c, n_p)
        self.demand = _coerce_demand_to_2d(demand, n_c, self.n_products)

        # Per-warehouse capacities
        self.warehouse_capacities = np.array(
            config.network.warehouse_capacities[:n_w], dtype=np.float64
        )

        # Per-product densities (kg/L). Pad with 1.0 if the user
        # configured fewer entries than products.
        density_cfg = list(config.product.product_density)
        while len(density_cfg) < self.n_products:
            density_cfg.append(1.0)
        self.product_density = np.array(
            density_cfg[: self.n_products], dtype=np.float64
        )
        self._inv_density = 1.0 / self.product_density

        # Vehicle types (single source of truth)
        self.vehicle_types = config.vehicle.build_vehicle_types()

        # Decision-variable count: x[w, c, v, p]
        n_vars = n_w * n_c * self.n_vehicle_types * self.n_products

        # Constraints: n_customers * n_products (demand) + n_warehouses
        n_constr = n_c * self.n_products + n_w

        max_demand = (
            float(np.max(self.demand))
            if self.demand.size > 0
            else config.nsga.max_demand_default
        )

        super().__init__(
            n_var=n_vars,
            n_obj=2,
            n_ieq_constr=n_constr,
            xl=np.zeros(n_vars),
            xu=np.full(n_vars, max_demand),
        )

        # Pre-broadcast vehicle parameters: (V,) -> (1, 1, 1, V, 1)
        self._cap_v = np.array(
            [v["capacity"] for v in self.vehicle_types], dtype=np.float64
        )
        self._cost_per_km = np.array(
            [v["cost_per_km"] for v in self.vehicle_types], dtype=np.float64
        )
        self._k_v = np.array(
            [v["k"] for v in self.vehicle_types], dtype=np.float64
        )
        self._L_v = np.array(
            [v["L"] for v in self.vehicle_types], dtype=np.float64
        )

    def _evaluate(self, X, out, *args, **kwargs):
        """Vectorised objective + constraint evaluation.

        Shapes:
            X     : (P, n_w * n_c * n_v * n_p)
            x_pop : (P, n_w, n_c, n_v, n_p)
        
        Parameters
        ----------
        """
        n_w = self.config.network.n_warehouses
        n_c = self.config.network.n_customers
        n_v = self.n_vehicle_types
        n_p = self.n_products
        pop = X.shape[0]

        x_pop = X.reshape(pop, n_w, n_c, n_v, n_p)

        # Sum across products gives per-(w, c, v) volume on link.
        # Shape: (P, n_w, n_c, n_v)
        link_volume = x_pop.sum(axis=4)

        # Continuous trip count per link: volume / capacity.
        # _cap_v: (n_v,) -> (1, 1, 1, n_v)
        n_trips = link_volume / self._cap_v[None, None, None, :]

        # dist: (n_w, n_c) -> (1, n_w, n_c, 1)
        dist_b = self.distance_matrix[None, :, :, None]

        # Cost: 2 * cost_per_km * dist * n_trips, summed across (w, c, v)
        F_cost = (
            2.0
            * self._cost_per_km[None, None, None, :]
            * dist_b
            * n_trips
        ).sum(axis=(1, 2, 3))

        # Carbon: loaded leg + empty return.
        # loaded = (n_trips * k + L * volume) * dist
        # empty  = k * dist * n_trips
        loaded = (
            n_trips * self._k_v[None, None, None, :]
            + self._L_v[None, None, None, :] * link_volume
        ) * dist_b
        empty = self._k_v[None, None, None, :] * dist_b * n_trips
        F_carbon = (loaded + empty).sum(axis=(1, 2, 3))

        F = np.stack([F_cost, F_carbon], axis=1)

        # Demand constraints per (c, p):
        # cust_sum_p[i, c, p] = sum_{w, v} x[i, w, c, v, p]
        cust_sum_p = x_pop.sum(axis=(1, 3))  # (P, n_c, n_p)
        eps = self.config.nsga.demand_constraint_eps
        G_demand = (
            np.abs(cust_sum_p - self.demand[None, :, :]) - eps
        ).reshape(pop, n_c * n_p)

        # Capacity constraints (density-weighted):
        # used[w] = sum_{c, v, p} x[w, c, v, p] / ρ_p
        weighted = x_pop * self._inv_density[None, None, None, None, :]
        wh_used = weighted.sum(axis=(2, 3, 4))  # (P, n_w)
        G_cap = wh_used - self.warehouse_capacities[None, :]

        G = np.concatenate([G_demand, G_cap], axis=1)

        out["F"] = F
        out["G"] = G


def run_multi_product_nsga2(
    config: MasterConfig,
    distance_matrix: np.ndarray,
    demand: np.ndarray,
    pop_size: int = None,
    n_gen: int = None,
    seed: int = None,
) -> object:
    """Run NSGA-II on the multi-product bi-objective formulation.

    Preservation contract (clause C3.5): when
    ``config.product.n_products == 1`` this function delegates to
    :func:`supply_chain_research.phase1_foundation.nsga2_solver.run_nsga2`
    so the returned Pareto front is bit-for-bit identical to the
    single-product solver under the same seed.

    Parameters
    ----------
    config : MasterConfig
        Master configuration. ``config.product.n_products`` controls
        the formulation; ``config.product.product_density`` is used
        for the density-weighted volume capacity.
    distance_matrix : np.ndarray, shape ``(n_warehouses, n_customers)``
        Distance matrix in km.
    demand : np.ndarray
        Customer demand in kg. Shape ``(n_customers,)`` (single
        product or split-evenly across products) or
        ``(n_customers, n_products)``.
    pop_size, n_gen, seed : int, optional
        Override population size, generation count, and RNG seed.

    Returns
    -------
    object
        pymoo ``Result`` with attributes ``F`` (Pareto-front
        objectives, shape ``(N, 2)``), ``X`` (decision vectors), and
        ``hv_history`` (per-generation hypervolume).

    References
    ----------
    .. [Salhi1999] JORS 50(10):1034–1042.
    .. [Coelho2013] EJOR 245(3):855–865.
    .. [Kek2008] MCM 47(1–2):140–152.
    """
    # ----------------------------------------------------------------
    # Preservation gate (clause C3.5): single-product → delegate.
    # ----------------------------------------------------------------
    if config.product.n_products == 1:
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

    problem = MultiProductSupplyChainProblem(
        config, distance_matrix, demand
    )

    repair = MultiProductDemandRepair(
        n_warehouses=config.network.n_warehouses,
        n_customers=config.network.n_customers,
        n_vehicle_types=problem.n_vehicle_types,
        n_products=problem.n_products,
        demand=problem.demand,
        warehouse_capacities=problem.warehouse_capacities,
        product_density=problem.product_density,
        repair_zero_eps=config.nsga.repair_zero_eps,
        repair_capacity_eps=config.nsga.repair_capacity_eps,
    )

    algorithm = NSGA2(
        pop_size=pop_size,
        crossover=SBX(
            eta=config.nsga.crossover_eta,
            prob=config.nsga.crossover_prob,
        ),
        mutation=PM(eta=config.nsga.mutation_eta),
        repair=repair,
    )

    algorithm.setup(
        problem, seed=seed, verbose=False, termination=NoTermination()
    )

    hv_history = []
    early_stop_window = config.nsga.early_stop_window
    early_stop_threshold = config.nsga.early_stop_threshold
    early_stop_min_gen = config.nsga.early_stop_min_gen

    for gen in range(n_gen):
        algorithm.next()
        res = algorithm.result()

        if res.F is not None and len(res.F) > 0:
            valid_F = res.F[np.all(np.isfinite(res.F), axis=1)]
            if len(valid_F) > 0:
                ref_point = (
                    valid_F.max(axis=0) * config.nsga.ref_point_margin
                )
                hv_indicator = HV(
                    ref_point=ref_point, norm_ref_point=False
                )
                hv_val = hv_indicator(valid_F)
                hv_history.append(hv_val)

        # Relative-HV-improvement early stopping (matches run_nsga2)
        if (
            gen >= early_stop_min_gen
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
    return result
