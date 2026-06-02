"""Epsilon-Constraint Method solver for supply chain optimization.

Classical mathematical programming approach: optimizes one objective (cost)
while constraining the other (carbon) to be below a set of epsilon values.
"""

import time

import numpy as np
from loguru import logger
from scipy.optimize import minimize as scipy_minimize

from supply_chain_research.config import MasterConfig
from supply_chain_research.phase1_foundation.nsga2_solver import (
    MarginalTradeoffRepair,
    SupplyChainProblem,
)
from supply_chain_research.phase1_foundation.solver_base import BaseSolver, SolverResult


class EpsilonConstraintSolver(BaseSolver):
    """Epsilon-Constraint Method solver.
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
        """Run Epsilon-Constraint solver.
        Parameters
        ----------
        """
        logger.info("Initializing Epsilon-Constraint solver...")
        start_time = time.time()

        n_w = config.network.n_warehouses
        n_c = config.network.n_customers
        n_v = 2

        problem = SupplyChainProblem(config, distance_matrix, demand)
        repair = MarginalTradeoffRepair(
            n_warehouses=n_w,
            n_customers=n_c,
            n_vehicle_types=n_v,
            demand=demand,
            warehouse_capacities=problem.warehouse_capacities,
            distance_matrix=distance_matrix,
            vehicle_types=problem.vehicle_types,
            config=config,
        )

        # Generate a starting point using a quick random repair
        rng = np.random.default_rng(seed)
        x0 = rng.uniform(problem.xl, problem.xu, size=(1, problem.n_var))
        x0 = repair._do(problem, x0)[0]

        # Helper to compute objective and constraints
        def get_objectives(x):
            """
            Parameters
            ----------
            """
            X = x[None, :]
            out = {}
            problem._evaluate(X, out)
            return out["F"][0], out["G"][0]

        # First, find the extreme points (anchor points) to get the carbon range
        # 1. Minimize Carbon emissions to find carbon_min
        logger.info("Finding carbon minimum anchor point...")
        res_carbon = scipy_minimize(
            lambda x: get_objectives(x)[0][1],
            x0,
            bounds=list(zip(problem.xl, problem.xu)),
            method="SLSQP",
            options={"maxiter": 30},
        )
        carbon_min_sol = repair._do(problem, res_carbon.x[None, :])[0]
        carbon_min = get_objectives(carbon_min_sol)[0][1]

        # 2. Minimize Cost to find carbon_max
        logger.info("Finding cost minimum anchor point...")
        res_cost = scipy_minimize(
            lambda x: get_objectives(x)[0][0],
            x0,
            bounds=list(zip(problem.xl, problem.xu)),
            method="SLSQP",
            options={"maxiter": 30},
        )
        cost_min_sol = repair._do(problem, res_cost.x[None, :])[0]
        carbon_max = get_objectives(cost_min_sol)[0][1]

        # Sweep 15 epsilon values between carbon_min and carbon_max
        if carbon_max <= carbon_min:
            carbon_max = carbon_min * 1.5

        epsilons = np.linspace(carbon_min, carbon_max, 15)
        pareto_front = []
        decision_variables = []
        n_evals = 0

        logger.info(f"Sweeping {len(epsilons)} epsilon values for constraint optimization...")
        # Use SLSQP to solve the constrained subproblems
        for eps in epsilons:
            # Objective: minimize cost
            # Constraints: -G >= 0 and eps - carbon >= 0
            cons = [
                {"type": "ineq", "fun": lambda x, e=eps: e - get_objectives(x)[0][1]},
            ]
            for idx in range(problem.n_ieq_constr):
                cons.append({"type": "ineq", "fun": lambda x, i=idx: -get_objectives(x)[1][i]})

            # Start from the cost_min_sol if it satisfies the constraint, otherwise x0
            start_x = cost_min_sol if get_objectives(cost_min_sol)[0][1] <= eps else x0

            res = scipy_minimize(
                lambda x: get_objectives(x)[0][0],
                start_x,
                bounds=list(zip(problem.xl, problem.xu)),
                constraints=cons,
                method="SLSQP",
                options={"maxiter": 20},
            )
            n_evals += res.nfev

            sol = repair._do(problem, res.x[None, :])[0]
            f_vals, g_vals = get_objectives(sol)

            # Check feasibility
            if np.all(g_vals <= config.nsga.demand_constraint_eps) and f_vals[1] <= eps + 10.0:
                pareto_front.append(f_vals)
                decision_variables.append(sol)

        runtime = time.time() - start_time
        logger.info(f"Epsilon-Constraint sweep finished in {runtime:.2f}s")

        # Fallback to anchor points if no feasible solutions found
        if not pareto_front:
            pareto_front = [get_objectives(carbon_min_sol)[0], get_objectives(cost_min_sol)[0]]
            decision_variables = [carbon_min_sol, cost_min_sol]

        pareto_front = np.array(pareto_front)
        decision_variables = np.array(decision_variables)

        # Remove dominated points from the sweep result to yield true Pareto front
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
            algorithm_name="Epsilon-Constraint",
            metadata={"epsilons": epsilons},
        )
        result.compute_hypervolume()
        return result

    @property
    def name(self) -> str:
        """
        Parameters
        ----------
        """
        return "Epsilon-Constraint"


def run_epsilon_constraint(
    config: MasterConfig,
    distance_matrix: np.ndarray,
    demand: np.ndarray,
    seed: int = 42,
) -> SolverResult:
    """Wrapper function to execute Epsilon-Constraint solver.
    Parameters
    ----------
    """
    solver = EpsilonConstraintSolver()
    return solver.solve(config, distance_matrix, demand, seed)
