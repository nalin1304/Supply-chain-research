"""Weighted Sum Method solver for multi-objective supply chain optimization.

Scalarizes the cost and carbon objectives into a single weighted objective:
    F(X) = alpha * Cost + (1 - alpha) * Carbon.
Sweeps alpha from 1.0 to 0.0 in 21 steps to approximate the Pareto front.

Note: As a limitation of convex scalarization, the Weighted Sum method
cannot find solutions in non-convex regions of the true Pareto front.
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


class WeightedSumProblem(Problem):
    """Scalarized single-objective version of the SupplyChainProblem.
    Parameters
    ----------
    
            Parameters
            ----------
            bi_problem : type
                Description of bi_problem.
            alpha : type
                Description of alpha.
        """

    def __init__(self, bi_problem: Problem, alpha: float):
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
        self.alpha = alpha

    def _evaluate(self, X, out, *args, **kwargs):
        """
        Parameters
        ----------
        """
        bi_out = {}
        self.bi_problem._evaluate(X, bi_out, *args, **kwargs)
        # Scalarize: alpha * cost + (1 - alpha) * carbon
        out["F"] = self.alpha * bi_out["F"][:, 0] + (1.0 - self.alpha) * bi_out["F"][:, 1]
        out["G"] = bi_out["G"]


class WeightedSumSolver(BaseSolver):
    """Weighted Sum Method solver.
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
        """Run Weighted Sum solver by sweeping alpha weights.
        Parameters
        ----------
        
                Parameters
                ----------
                config : type
                    Description of config.
                distance_matrix : type
                    Description of distance_matrix.
                demand : type
                    Description of demand.
                seed : type
                    Description of seed.
            """
        logger.info("Initializing Weighted Sum solver...")
        start_time = time.time()

        n_w = config.network.n_warehouses
        n_c = config.network.n_customers
        n_v = 2

        bi_problem = SupplyChainProblem(config, distance_matrix, demand)

        # 21 steps from alpha=1.0 (pure cost) to alpha=0.0 (pure carbon)
        alphas = np.linspace(1.0, 0.0, 21)
        pareto_front = []
        decision_variables = []
        n_evals = 0

        # Create the repair operator
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

        logger.info("Sweeping weights for single-objective GA scalarizations...")
        for alpha in alphas:
            scalar_problem = WeightedSumProblem(bi_problem, alpha)

            # Single-objective GA
            algorithm = GA(
                pop_size=30,  # smaller pop for speed per subproblem
                repair=repair,
            )

            # Run a quick GA optimization (50 generations is enough for each weight)
            termination = get_termination("n_gen", 50)

            res = minimize(
                scalar_problem,
                algorithm,
                termination,
                seed=seed,
                verbose=False,
            )

            n_evals += res.algorithm.evaluator.n_eval

            if res.X is not None:
                sol = np.atleast_2d(res.X)[0]
                # Evaluate on bi-objective problem to get cost/carbon objectives
                bi_out = {}
                bi_problem._evaluate(sol[None, :], bi_out)
                f_vals = bi_out["F"][0]
                g_vals = bi_out["G"][0]

                # Ensure feasibility
                if np.all(g_vals <= config.nsga.demand_constraint_eps):
                    pareto_front.append(f_vals)
                    decision_variables.append(sol)

        runtime = time.time() - start_time
        logger.info(f"Weighted Sum sweep finished in {runtime:.2f}s")

        # Handle empty results edge case
        if not pareto_front:
            # Fallback to a random repaired solution
            rng = np.random.default_rng(seed)
            x_rand = rng.uniform(bi_problem.xl, bi_problem.xu, size=(1, bi_problem.n_var))
            x_rand = repair._do(bi_problem, x_rand)[0]
            bi_out = {}
            bi_problem._evaluate(x_rand[None, :], bi_out)
            pareto_front.append(bi_out["F"][0])
            decision_variables.append(x_rand)

        pareto_front = np.array(pareto_front)
        decision_variables = np.array(decision_variables)

        # Filter dominated points to yield the non-dominated Pareto front
        non_dominated = []
        for i in range(len(pareto_front)):
            dominated = False
            for j in range(len(pareto_front)):
                if i != j:
                    if np.all(pareto_front[j] <= pareto_front[i]) and np.any(pareto_front[j] < pareto_front[i]):
                        dominated = True
                        break
            if not dominated:
                non_dominated.append(i)

        pareto_front = pareto_front[non_dominated]
        decision_variables = decision_variables[non_dominated]

        result = SolverResult(
            pareto_front=pareto_front,
            decision_variables=decision_variables,
            convergence_history=[],
            runtime_seconds=runtime,
            n_function_evaluations=n_evals,
            algorithm_name="Weighted Sum",
            metadata={"alphas": alphas},
        )
        result.compute_hypervolume()
        return result

    @property
    def name(self) -> str:
        """
        Parameters
        ----------
        """
        return "Weighted Sum"


def run_weighted_sum(
    config: MasterConfig,
    distance_matrix: np.ndarray,
    demand: np.ndarray,
    seed: int = 42,
) -> SolverResult:
    """Wrapper function to execute Weighted Sum solver.
    Parameters
    ----------
    
            Parameters
            ----------
            config : type
                Description of config.
            distance_matrix : type
                Description of distance_matrix.
            demand : type
                Description of demand.
            seed : type
                Description of seed.
        """
    solver = WeightedSumSolver()
    return solver.solve(config, distance_matrix, demand, seed)
