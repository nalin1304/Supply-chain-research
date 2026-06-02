"""MOEA/D solver for bi-objective supply chain optimization.

Uses pymoo framework with Tchebycheff decomposition and
neighborhood-based selection.
"""

import numpy as np
from pymoo.algorithms.moo.moead import MOEAD
from pymoo.core.problem import Problem
from pymoo.optimize import minimize
from pymoo.termination import get_termination
from pymoo.util.ref_dirs import get_reference_directions

from supply_chain_research.config import MasterConfig
from supply_chain_research.phase1_foundation.nsga2_solver import (
    MarginalTradeoffRepair,
    SupplyChainProblem,
)


class UnconstrainedSupplyChainProblem(Problem):
    """Wrapper that exposes a constrained Problem as an unconstrained one.

    This is necessary because pymoo's MOEA/D does not support constraints,
    but our custom repair operator (MarginalTradeoffRepair) handles feasibility,
    so we can safely hide constraints from pymoo.
    
    Parameters
    ----------
    """
    def __init__(self, problem):
        """
        Parameters
        ----------
        """
        super().__init__(
            n_var=problem.n_var,
            n_obj=problem.n_obj,
            n_ieq_constr=0,
            xl=problem.xl,
            xu=problem.xu,
        )
        self.problem = problem
        # Forward required attributes
        self.vehicle_types = getattr(problem, "vehicle_types", None)
        self.n_vehicle_types = getattr(problem, "n_vehicle_types", None)
        self.warehouse_capacities = getattr(problem, "warehouse_capacities", None)

    def _evaluate(self, X, out, *args, **kwargs):
        """
        Parameters
        ----------
        """
        sub_out = {}
        self.problem._evaluate(X, sub_out, *args, **kwargs)
        out["F"] = sub_out["F"]


def run_moead(
    config: MasterConfig,
    distance_matrix: np.ndarray,
    demand: np.ndarray,
    pop_size: int = None,
    n_gen: int = None,
    seed: int = None,
) -> object:
    """Run MOEA/D optimization.

    Args:
        config: Master configuration.
        distance_matrix: Distance matrix (n_warehouses, n_customers).
        demand: Customer demand array.
        pop_size: Override population size.
        n_gen: Override number of generations.
        seed: Random seed.

    Returns:
        pymoo Result object with Pareto front.
    
    Parameters
    ----------
    """
    if pop_size is None:
        pop_size = config.moead.pop_size
    if n_gen is None:
        n_gen = config.moead.n_gen
    if seed is None:
        seed = config.random_seed

    n_w = config.network.n_warehouses
    n_c = config.network.n_customers

    raw_problem = SupplyChainProblem(config, distance_matrix, demand)
    problem = UnconstrainedSupplyChainProblem(raw_problem)

    # Generate reference directions for 2 objectives
    ref_dirs = get_reference_directions(
        "uniform", 2, n_partitions=pop_size - 1
    )

    algorithm = MOEAD(
        ref_dirs=ref_dirs,
        n_neighbors=config.moead.n_neighbors,
        repair=MarginalTradeoffRepair(
            n_warehouses=n_w,
            n_customers=n_c,
            n_vehicle_types=len(config.vehicle.build_vehicle_types()),
            demand=demand,
            warehouse_capacities=np.array(config.network.warehouse_capacities[:n_w], dtype=np.float64),
            distance_matrix=distance_matrix,
            vehicle_types=config.vehicle.build_vehicle_types(),
            config=config,
        ),
    )

    termination = get_termination("n_gen", n_gen)

    result = minimize(
        problem,
        algorithm,
        termination,
        seed=seed,
        verbose=False,
    )

    return result
