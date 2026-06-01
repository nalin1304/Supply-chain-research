"""OR-Tools baseline solver for single-objective CVRP comparison.

Solves a Capacitated Vehicle Routing Problem minimizing total
transportation cost only, then computes emissions for the solution.
"""

import numpy as np
from ortools.constraint_solver import pywrapcp, routing_enums_pb2

from supply_chain_research.config import MasterConfig
from supply_chain_research.phase1_foundation.emission_model import (
    EmissionCalculator,
)


def solve_baseline_cvrp(
    config: MasterConfig,
    distance_matrix: np.ndarray,
    demand: np.ndarray,
    vehicle_type: str = "HCV",
    time_limit_seconds: int = 30,
    method: str = "ortools",
) -> dict:
    """Solve CVRP using OR-Tools or Clarke-Wright for single-objective baseline.

    Solves minimum-cost routing with capacity constraints using
    a single vehicle type. This provides a comparison point for
    the multi-objective Pareto front.

    Args:
        config: Master configuration.
        distance_matrix: Distance matrix in km,
            shape (n_warehouses, n_customers) or
            shape (n_nodes, n_nodes).
        demand: Customer demand in kg, shape (n_customers,).
        vehicle_type: Vehicle type to use ('HCV' or 'LCV').
        time_limit_seconds: Time limit for solver.
        method: Solver method, either "ortools" (default, preserves C3.7)
            or "clarke_wright" for the Clarke-Wright Savings heuristic.

    Returns:
        Dictionary with:
            - total_cost: Total transportation cost (INR)
            - total_emission: Total emissions (g CO2)
            - routes: List of routes per warehouse
            - feasible: Whether a feasible solution was found
    """
    # When method="clarke_wright", delegate to Clarke-Wright solver
    # [Clarke & Wright 1964, "Scheduling of Vehicles from a Central Depot to
    #  a Number of Delivery Points", Operations Research 12(4):568–581;
    #  DOI 10.1287/opre.12.4.568. BibTeX key clarke1964savings in
    #  docs/VERIFIED_REFERENCES.bib under FIX-014.]
    if method == "clarke_wright":
        from supply_chain_research.phase1_foundation.clarke_wright import (
            solve_cvrp_clarke_wright,
        )
        return solve_cvrp_clarke_wright(
            config=config,
            distance_matrix=distance_matrix,
            demand=demand,
            vehicle_type=vehicle_type,
        )

    # Default: method="ortools" — original behavior preserved (C3.7)
    n_w = config.network.n_warehouses
    n_c = config.network.n_customers

    # Set vehicle parameters
    if vehicle_type.upper() == "HCV":
        capacity = int(config.vehicle.hcv_capacity)
        cost_per_km = config.vehicle.hcv_cost_per_km
    else:
        capacity = int(config.vehicle.lcv_capacity)
        cost_per_km = config.vehicle.lcv_cost_per_km

    # Assign customers to nearest warehouse
    assignments = {}
    for c in range(n_c):
        if distance_matrix.shape[0] > n_w:
            # Full matrix format
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
    emission_calc = EmissionCalculator(config)

    for w, customers in assignments.items():
        if not customers:
            continue

        # Build sub-distance matrix: depot (warehouse) + customers
        n_local = len(customers) + 1  # +1 for depot
        local_dist = np.zeros((n_local, n_local), dtype=int)

        for i, ci in enumerate(customers):
            # Depot to customer
            if distance_matrix.shape[0] > n_w:
                d = distance_matrix[w, n_w + ci]
            else:
                d = distance_matrix[w, ci]
            local_dist[0, i + 1] = int(d * 1000)  # Convert to meters
            local_dist[i + 1, 0] = int(d * 1000)

            for j, cj in enumerate(customers):
                if i != j:
                    if distance_matrix.shape[0] > n_w:
                        d = distance_matrix[n_w + ci, n_w + cj]
                    else:
                        # Approximate inter-customer distance.
                        # NOTE: This is a known approximation
                        # limitation. The triangle inequality is
                        # not preserved -- customers equidistant
                        # from the depot but in opposite directions
                        # could get near-zero distance. We apply a
                        # floor of max(abs(d_wi-d_wj)*high_factor,
                        # min(d_wi,d_wj)*low_factor) to avoid
                        # degenerate zero-distance cases. Factors
                        # centralised in NSGAConfig (default 0.8 / 0.3).
                        d_wi = distance_matrix[w, ci]
                        d_wj = distance_matrix[w, cj]
                        d = max(
                            abs(d_wi - d_wj)
                            * config.nsga.inter_customer_distance_high_factor,
                            min(d_wi, d_wj)
                            * config.nsga.inter_customer_distance_low_factor,
                        )
                    local_dist[i + 1, j + 1] = int(d * 1000)

        # Setup OR-Tools routing model
        local_demand = [0] + [int(demand[c]) for c in customers]
        n_vehicles = max(
            1, int(np.ceil(sum(local_demand) / capacity))
        )

        manager = pywrapcp.RoutingIndexManager(
            n_local, n_vehicles, 0
        )
        routing = pywrapcp.RoutingModel(manager)

        def distance_callback(from_index, to_index):
            """Return distance between two nodes for OR-Tools routing.

            Parameters
            ----------
            from_index : int
                Internal OR-Tools index of the origin node.
            to_index : int
                Internal OR-Tools index of the destination node.

            Returns
            -------
            int
                Distance in meters between the two nodes.
            """
            from_node = manager.IndexToNode(from_index)
            to_node = manager.IndexToNode(to_index)
            return local_dist[from_node][to_node]

        transit_callback_index = routing.RegisterTransitCallback(
            distance_callback
        )
        routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

        # Capacity constraint
        def demand_callback(from_index):
            """Return demand at a node for OR-Tools capacity dimension.

            Parameters
            ----------
            from_index : int
                Internal OR-Tools index of the node.

            Returns
            -------
            int
                Demand in kg at the specified node (0 for the depot).
            """
            from_node = manager.IndexToNode(from_index)
            return local_demand[from_node]

        demand_callback_index = routing.RegisterUnaryTransitCallback(
            demand_callback
        )
        routing.AddDimensionWithVehicleCapacity(
            demand_callback_index,
            0,  # no slack
            [capacity] * n_vehicles,
            True,  # start cumul to zero
            "Capacity",
        )

        # Search parameters
        search_params = pywrapcp.DefaultRoutingSearchParameters()
        search_params.first_solution_strategy = (
            routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
        )
        search_params.time_limit.seconds = time_limit_seconds

        solution = routing.SolveWithParameters(search_params)

        if solution:
            for v in range(n_vehicles):
                route = []
                index = routing.Start(v)
                route_distance = 0

                while not routing.IsEnd(index):
                    node = manager.IndexToNode(index)
                    route.append(node)
                    next_index = solution.Value(
                        routing.NextVar(index)
                    )
                    route_distance += routing.GetArcCostForVehicle(
                        index, next_index, v
                    )
                    index = next_index

                if len(route) > 1:  # Non-empty route
                    dist_km = route_distance / 1000.0
                    route_load = sum(
                        local_demand[n] for n in route if n > 0
                    )
                    total_cost += 2 * dist_km * cost_per_km
                    total_emission += emission_calc.route_emission(
                        vehicle_type, route_load, dist_km
                    )
                    total_emission += emission_calc.route_emission(
                        vehicle_type, 0.0, dist_km
                    )
                    all_routes.append({
                        "warehouse": w,
                        "customers": [
                            customers[n - 1]
                            for n in route if n > 0
                        ],
                        "distance_km": dist_km,
                        "load_kg": route_load,
                    })

    return {
        "total_cost": total_cost,
        "total_emission": total_emission,
        "routes": all_routes,
        "feasible": len(all_routes) > 0,
    }
