"""Single-Objective GA solver for supply chain optimization.

Optimizes each objective (cost and carbon) independently using pymoo's single-objective GA.
Finds the absolute anchor points (extremes) of the Pareto front.
"""

import time

import numpy as np
from loguru import logger
from pymoo.algorithms.soo.nonconvex.ga import GA
from pymoo.core.problem import Problem
from pymoo.optimize import minimize
from pymoo.termination import get_termination

from supply_chain_research.config import MasterConfig
from supply_chain_research.phase1_foundation.nsga2_solver import (
    MarginalTradeoffRepair,
    SupplyChainProblem,
)
from supply_chain_research.phase1_foundation.solver_base import BaseSolver, SolverResult


class ScalarProblem(Problem):
    """Wraps bi-objective SupplyChainProblem as a single-objective problem.
    Parameters
    ----------
    """

    def __init__(self, bi_problem: Problem, obj_index: int):
        """
        Parameters
        ----------
        """
        super().__init__(
            n_var=bi_problem.n_var,
            n_obj=1,
            n_ieq_constr=bi_problem.n_ieq_constr,
            xl=bi_problem.xl,
            xu=bi_problem.xu,
        )
        self.bi_problem = bi_problem
        self.obj_index = obj_index

    def _evaluate(self, X, out, *args, **kwargs):
        """
        Parameters
        ----------
        """
        bi_out = {}
        self.bi_problem._evaluate(X, bi_out, *args, **kwargs)
        out["F"] = bi_out["F"][:, self.obj_index]
        out["G"] = bi_out["G"]


class SingleObjectiveGASolver(BaseSolver):
    """Single-Objective GA solver for anchor points computation.
    Parameters
    ----------
    """

    def solve(
        self,
        config: MasterConfig,
        distance_matrix: np.ndarray,
        demand: np.ndarray,
        seed: int = 42,
    ) -> SolverResult:
        """Run two independent single-objective GA optimizations.
        Parameters
        ----------
        """
        logger.info("Initializing Single-Objective GA solver...")
        start_time = time.time()

        n_w = config.network.n_warehouses
        n_c = config.network.n_customers
        n_v = 2

        bi_problem = SupplyChainProblem(config, distance_matrix, demand)
        repair = MarginalTradeoffRepair(
            n_warehouses=n_w,
            n_customers=n_c,
            n_vehicle_types=n_v,
            demand=demand,
            warehouse_capacities=bi_problem.warehouse_capacities,
            distance_matrix=distance_matrix,
            vehicle_types=bi_problem.vehicle_types,
            config=config,
        )

        n_evals = 0
        pareto_front = []
        decision_variables = []

        # Run optimization 1: Minimize Cost (index 0)
        logger.info("Optimizing objective 1 (Cost)...")
        prob_cost = ScalarProblem(bi_problem, obj_index=0)
        algorithm_cost = GA(
            pop_size=config.nsga.pop_size,
            repair=repair,
        )
        termination = get_termination("n_gen", config.nsga.n_gen)
        res_cost = minimize(
            prob_cost,
            algorithm_cost,
            termination,
            seed=seed,
            verbose=False,
        )
        n_evals += res_cost.algorithm.evaluator.n_eval

        # Run optimization 2: Minimize Carbon (index 1)
        logger.info("Optimizing objective 2 (Carbon)...")
        prob_carbon = ScalarProblem(bi_problem, obj_index=1)
        algorithm_carbon = GA(
            pop_size=config.nsga.pop_size,
            repair=repair,
        )
        res_carbon = minimize(
            prob_carbon,
            algorithm_carbon,
            termination,
            seed=seed,
            verbose=False,
        )
        n_evals += res_carbon.algorithm.evaluator.n_eval

        # Evaluate both solutions on the original bi-objective problem
        for sol in [res_cost.X, res_carbon.X]:
            if sol is not None:
                sol_flat = np.atleast_2d(sol)[0]
                bi_out = {}
                bi_problem._evaluate(sol_flat[None, :], bi_out)
                pareto_front.append(bi_out["F"][0])
                decision_variables.append(sol_flat)

        runtime = time.time() - start_time
        logger.info(f"Single-Objective GA runs finished in {runtime:.2f}s")

        pareto_front = np.array(pareto_front)
        decision_variables = np.array(decision_variables)

        result = SolverResult(
            pareto_front=pareto_front,
            decision_variables=decision_variables,
            convergence_history=[],
            runtime_seconds=runtime,
            n_function_evaluations=n_evals,
            algorithm_name="Single-Objective GA",
            metadata={"res_cost": res_cost, "res_carbon": res_carbon},
        )
        result.compute_hypervolume()
        return result

    @property
    def name(self) -> str:
        """
        Parameters
        ----------
        """
        return "Single-Objective GA"


def run_single_objective_ga(
    config: MasterConfig,
    distance_matrix: np.ndarray,
    demand: np.ndarray,
    seed: int = 42,
) -> SolverResult:
    """Wrapper function to execute Single-Objective GA solver.
    Parameters
    ----------
    """
    solver = SingleObjectiveGASolver()
    return solver.solve(config, distance_matrix, demand, seed)
