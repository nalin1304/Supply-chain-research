"""Clarke-Wright Savings Algorithm for CVRP (FIX-014).

Implements the parallel savings algorithm for the Capacitated Vehicle
Routing Problem as an alternative baseline to OR-Tools, exposed via
``solve_baseline_cvrp(method="clarke_wright")`` in
``supply_chain_research/phase1_foundation/baseline_solver.py``.

The classic savings metric is

    s(i, j) = d(0, i) + d(0, j) - d(i, j)

where node ``0`` is the depot. The parallel variant scans the savings
list in decreasing order and merges the two routes containing customers
``i`` and ``j`` whenever (a) the merge does not violate vehicle
capacity, (b) ``i`` and ``j`` are at the ends of their respective
routes, and (c) they are not already on the same route.

Reference
---------
.. [Clarke1964] Clarke, G. & Wright, J. W. (1964). "Scheduling of
   Vehicles from a Central Depot to a Number of Delivery Points."
   Operations Research, 12(4), 568-581.
   DOI: 10.1287/opre.12.4.568
   BibTeX key: ``clarke1964savings`` in
   ``docs/VERIFIED_REFERENCES.bib`` under "FIX-014 — Clarke-Wright Savings
   baseline".
"""

from dataclasses import dataclass, field

import numpy as np

from supply_chain_research.config import MasterConfig
from supply_chain_research.phase1_foundation.emission_model import (
    EmissionCalculator,
)


@dataclass
class Route:
    """A vehicle route from depot through customers and back.

    Parameters
    ----------
    customers : List[int]
        Ordered list of customer indices in the route.
    load : float
        Total load (kg) carried on this route.
    distance : float
        Total route distance in km.
    """

    customers: list[int] = field(default_factory=list)
    load: float = 0.0
    distance: float = 0.0


def clarke_wright_savings(
    distance_matrix: np.ndarray,
    demand: np.ndarray,
    vehicle_capacity: float,
    depot_index: int = 0,
) -> list[Route]:
    """Solve CVRP using the parallel Clarke-Wright Savings Algorithm.

    Implements the classic Clarke & Wright (1964) savings algorithm
    [Clarke1964]_. The algorithm computes the savings metric

        s(i, j) = d(depot, i) + d(depot, j) - d(i, j)

    for every customer pair ``(i, j)``, sorts savings in decreasing
    order, and greedily merges the two routes containing customers
    ``i`` and ``j`` when (a) capacity is respected, (b) ``i`` and
    ``j`` are at the ends of their respective routes, and (c) the two
    routes are distinct.

    Parameters
    ----------
    distance_matrix : np.ndarray
        Full distance matrix including depot, shape (n_nodes, n_nodes).
        Node 0 is the depot (or use depot_index).
    demand : np.ndarray
        Customer demand in kg, shape (n_customers,).
        Index 0 corresponds to node 1 in distance_matrix.
    vehicle_capacity : float
        Maximum vehicle capacity in kg.
    depot_index : int, optional
        Index of the depot in the distance matrix. Default 0.

    Returns
    -------
    List[Route]
        List of routes, each containing customer indices (0-based,
        relative to the demand array).

    References
    ----------
    .. [Clarke1964] Clarke, G. & Wright, J. W. (1964). "Scheduling of
       Vehicles from a Central Depot to a Number of Delivery Points."
       Operations Research, 12(4), 568-581.
       DOI: 10.1287/opre.12.4.568
    """
    n_customers = len(demand)

    # Customer indices in the distance matrix
    customer_nodes = [
        i for i in range(distance_matrix.shape[0]) if i != depot_index
    ][:n_customers]

    # Initialize: one route per customer
    routes = []
    customer_to_route = {}

    for idx, node in enumerate(customer_nodes):
        route = Route(
            customers=[idx],
            load=demand[idx],
            distance=2.0 * distance_matrix[depot_index, node],
        )
        routes.append(route)
        customer_to_route[idx] = route

    # Compute savings: s(i,j) = d(0,i) + d(0,j) - d(i,j)
    # [Clarke & Wright 1964 §2 Eq. (1) — Operations Research 12(4):568–581;
    #  DOI 10.1287/opre.12.4.568]
    savings = []
    for i in range(n_customers):
        for j in range(i + 1, n_customers):
            node_i = customer_nodes[i]
            node_j = customer_nodes[j]
            s = (
                distance_matrix[depot_index, node_i]
                + distance_matrix[depot_index, node_j]
                - distance_matrix[node_i, node_j]
            )
            savings.append((s, i, j))

    # Sort savings in decreasing order
    savings.sort(key=lambda x: x[0], reverse=True)

    # Merge routes greedily
    for s_val, i, j in savings:
        if s_val <= 0:
            break

        route_i = customer_to_route.get(i)
        route_j = customer_to_route.get(j)

        # Skip if same route or either route was already merged away
        if route_i is None or route_j is None:
            continue
        if route_i is route_j:
            continue

        # Check capacity constraint
        if route_i.load + route_j.load > vehicle_capacity:
            continue

        # Check that i and j are at the ends of their respective routes
        i_is_end = (
            route_i.customers[0] == i or route_i.customers[-1] == i
        )
        j_is_end = (
            route_j.customers[0] == j or route_j.customers[-1] == j
        )

        if not (i_is_end and j_is_end):
            continue

        # Merge: orient routes so i is at the end of route_i
        # and j is at the start of route_j
        if route_i.customers[-1] != i:
            route_i.customers.reverse()
        if route_j.customers[0] != j:
            route_j.customers.reverse()

        # Compute new distance
        node_i = customer_nodes[i]
        node_j = customer_nodes[j]
        new_distance = (
            route_i.distance + route_j.distance
            - distance_matrix[depot_index, node_i]
            - distance_matrix[depot_index, node_j]
            + distance_matrix[node_i, node_j]
        )

        # Merge route_j into route_i
        route_i.customers.extend(route_j.customers)
        route_i.load += route_j.load
        route_i.distance = new_distance

        # Update customer-to-route mapping
        for c in route_j.customers:
            customer_to_route[c] = route_i

        # Remove route_j from routes list
        if route_j in routes:
            routes.remove(route_j)

    # Filter out empty routes
    active_routes = [r for r in routes if r.customers]

    # Run Local Search (2-opt, Or-opt, and Inter-route Relocate/Swap) to minimize total distance
    if active_routes:
        customer_nodes = [
            node_idx for node_idx in range(distance_matrix.shape[0]) if node_idx != depot_index
        ][:n_customers]

        def get_route_dist(custs: list[int]) -> float:
            """
            Parameters
            ----------
            """
            if not custs:
                return 0.0
            d = distance_matrix[depot_index, customer_nodes[custs[0]]]
            for idx in range(len(custs) - 1):
                d += distance_matrix[customer_nodes[custs[idx]], customer_nodes[custs[idx + 1]]]
            d += distance_matrix[customer_nodes[custs[-1]], depot_index]
            return d

        def run_intra_route_local_search(r: Route) -> bool:
            """
            Parameters
            ----------
            """
            n_r = len(r.customers)
            if n_r < 2:
                return False

            best_dist = r.distance
            # 1. Try 2-opt
            for i in range(n_r):
                for j in range(i + 1, n_r):
                    new_custs = r.customers[:i] + list(reversed(r.customers[i:j+1])) + r.customers[j+1:]
                    new_d = get_route_dist(new_custs)
                    if new_d < best_dist - 1e-6:
                        r.customers = new_custs
                        r.distance = new_d
                        return True

            # 2. Try Or-opt (L = 1, 2, 3)
            for L in [1, 2, 3]:
                if L >= n_r:
                    continue
                for i in range(n_r - L + 1):
                    subseg = r.customers[i:i+L]
                    remaining = r.customers[:i] + r.customers[i+L:]

                    for j in range(len(remaining) + 1):
                        # Try normal insertion
                        new_custs = remaining[:j] + subseg + remaining[j:]
                        new_d = get_route_dist(new_custs)
                        if new_d < best_dist - 1e-6:
                            r.customers = new_custs
                            r.distance = new_d
                            return True

                        # Try reversed insertion
                        new_custs = remaining[:j] + list(reversed(subseg)) + remaining[j:]
                        new_d = get_route_dist(new_custs)
                        if new_d < best_dist - 1e-6:
                            r.customers = new_custs
                            r.distance = new_d
                            return True
            return False

        def run_inter_route_local_search() -> bool:
            """
            Parameters
            ----------
            """
            if len(active_routes) < 2:
                return False

            for idx1 in range(len(active_routes)):
                for idx2 in range(len(active_routes)):
                    if idx1 == idx2:
                        continue

                    r1 = active_routes[idx1]
                    r2 = active_routes[idx2]

                    if not r1.customers or not r2.customers:
                        continue

                    # --- Relocate ---
                    for i in range(len(r1.customers)):
                        c = r1.customers[i]
                        c_demand = demand[c]
                        if r2.load + c_demand <= vehicle_capacity:
                            new_r1_custs = r1.customers[:i] + r1.customers[i+1:]
                            for j in range(len(r2.customers) + 1):
                                new_r2_custs = r2.customers[:j] + [c] + r2.customers[j:]
                                old_dist_sum = r1.distance + r2.distance
                                new_dist_sum = get_route_dist(new_r1_custs) + get_route_dist(new_r2_custs)

                                if new_dist_sum < old_dist_sum - 1e-6:
                                    r1.customers = new_r1_custs
                                    r1.distance = get_route_dist(new_r1_custs)
                                    r1.load -= c_demand

                                    r2.customers = new_r2_custs
                                    r2.distance = get_route_dist(new_r2_custs)
                                    r2.load += c_demand
                                    return True

                    # --- Swap ---
                    for i in range(len(r1.customers)):
                        c1 = r1.customers[i]
                        demand_c1 = demand[c1]
                        for j in range(len(r2.customers)):
                            c2 = r2.customers[j]
                            demand_c2 = demand[c2]

                            # Check capacity constraints
                            if (r1.load - demand_c1 + demand_c2 <= vehicle_capacity and
                                r2.load - demand_c2 + demand_c1 <= vehicle_capacity):

                                new_r1_custs = r1.customers[:i] + [c2] + r1.customers[i+1:]
                                new_r2_custs = r2.customers[:j] + [c1] + r2.customers[j+1:]

                                old_dist_sum = r1.distance + r2.distance
                                new_dist_sum = get_route_dist(new_r1_custs) + get_route_dist(new_r2_custs)

                                if new_dist_sum < old_dist_sum - 1e-6:
                                    r1.customers = new_r1_custs
                                    r1.distance = get_route_dist(new_r1_custs)
                                    r1.load = r1.load - demand_c1 + demand_c2

                                    r2.customers = new_r2_custs
                                    r2.distance = get_route_dist(new_r2_custs)
                                    r2.load = r2.load - demand_c2 + demand_c1
                                    return True

                    # --- 2-opt* (Suffix exchange) ---
                    for i in range(len(r1.customers) + 1):
                        for j in range(len(r2.customers) + 1):
                            if (i == 0 and j == 0) or (i == len(r1.customers) and j == len(r2.customers)):
                                continue

                            new_r1_custs = r1.customers[:i] + r2.customers[j:]
                            new_r2_custs = r2.customers[:j] + r1.customers[i:]

                            load_r1 = sum(demand[c] for c in new_r1_custs)
                            load_r2 = sum(demand[c] for c in new_r2_custs)

                            if load_r1 <= vehicle_capacity and load_r2 <= vehicle_capacity:
                                old_dist_sum = r1.distance + r2.distance
                                new_dist_sum = get_route_dist(new_r1_custs) + get_route_dist(new_r2_custs)

                                if new_dist_sum < old_dist_sum - 1e-6:
                                    r1.customers = new_r1_custs
                                    r1.distance = get_route_dist(new_r1_custs)
                                    r1.load = load_r1

                                    r2.customers = new_r2_custs
                                    r2.distance = get_route_dist(new_r2_custs)
                                    r2.load = load_r2
                                    return True
            return False

        # Update initial distances to be exact
        for r in active_routes:
            r.distance = get_route_dist(r.customers)

        improved = True
        while improved:
            improved = False

            # 1. Intra-route optimization
            for r in active_routes:
                while run_intra_route_local_search(r):
                    improved = True

            # 2. Inter-route optimization
            if run_inter_route_local_search():
                improved = True

        # Filter out empty routes
        active_routes = [r for r in active_routes if r.customers]

    return active_routes


def solve_cvrp_clarke_wright(
    config: MasterConfig,
    distance_matrix: np.ndarray,
    demand: np.ndarray,
    vehicle_type: str = "HCV",
) -> dict:
    """Solve CVRP using Clarke-Wright Savings Algorithm.

    Parameters
    ----------
    config : MasterConfig
        Master configuration.
    distance_matrix : np.ndarray
        Distance matrix in km, shape (n_warehouses, n_customers)
        or (n_nodes, n_nodes).
    demand : np.ndarray
        Customer demand in kg, shape (n_customers,).
    vehicle_type : str, optional
        Vehicle type to use ('HCV' or 'LCV'). Default 'HCV'.

    Returns
    -------
    dict
        Dictionary with:
            - total_cost: Total transportation cost (INR)
            - total_emission: Total emissions (kg CO2)
            - routes: List of route dictionaries
            - feasible: Whether a feasible solution was found
    """
    n_w = config.network.n_warehouses
    n_c = config.network.n_customers

    # Set vehicle parameters
    if vehicle_type.upper() == "HCV":
        capacity = config.vehicle.hcv_capacity
        cost_per_km = config.vehicle.hcv_cost_per_km
    else:
        capacity = config.vehicle.lcv_capacity
        cost_per_km = config.vehicle.lcv_cost_per_km

    emission_calc = EmissionCalculator(config)

    # Assign customers to nearest warehouse
    assignments = {}
    for c in range(n_c):
        if distance_matrix.shape[0] > n_w:
            dists = distance_matrix[:n_w, n_w + c]
        else:
            dists = distance_matrix[:, c]
        nearest_w = int(np.argmin(dists))
        if nearest_w not in assignments:
            assignments[nearest_w] = []
        assignments[nearest_w].append(c)

    total_cost = 0.0
    total_emission = 0.0
    all_routes = []

    for w, customers in assignments.items():
        if not customers:
            continue

        # Build local distance matrix: depot + customers
        n_local = len(customers) + 1
        local_dist = np.zeros((n_local, n_local))

        for i, ci in enumerate(customers):
            if distance_matrix.shape[0] > n_w:
                d = distance_matrix[w, n_w + ci]
            else:
                d = distance_matrix[w, ci]
            local_dist[0, i + 1] = d
            local_dist[i + 1, 0] = d

            for j, cj in enumerate(customers):
                if i != j:
                    if distance_matrix.shape[0] > n_w:
                        d_ij = distance_matrix[n_w + ci, n_w + cj]
                    else:
                        d_wi = distance_matrix[w, ci]
                        d_wj = distance_matrix[w, cj]
                        d_ij = max(
                            abs(d_wi - d_wj)
                            * config.nsga.inter_customer_distance_high_factor,
                            min(d_wi, d_wj)
                            * config.nsga.inter_customer_distance_low_factor,
                        )
                    local_dist[i + 1, j + 1] = d_ij

        # Local demand (customer indices are 0-based in local context)
        local_demand = np.array([demand[c] for c in customers])

        # Run Clarke-Wright
        cw_routes = clarke_wright_savings(
            distance_matrix=local_dist,
            demand=local_demand,
            vehicle_capacity=capacity,
            depot_index=0,
        )

        for route in cw_routes:
            dist_km = route.distance
            route_load = route.load

            total_cost += 2 * dist_km * cost_per_km
            total_emission += emission_calc.route_emission(
                vehicle_type, route_load, dist_km
            )
            total_emission += emission_calc.route_emission(
                vehicle_type, 0.0, dist_km
            )

            all_routes.append({
                "warehouse": w,
                "customers": [customers[c] for c in route.customers],
                "distance_km": dist_km,
                "load_kg": route_load,
            })

    return {
        "total_cost": total_cost,
        "total_emission": total_emission,
        "routes": all_routes,
        "feasible": len(all_routes) > 0,
    }
