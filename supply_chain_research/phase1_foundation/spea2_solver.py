"""SPEA2 solver for multi-objective supply chain optimization.

Uses pymoo's SPEA2 algorithm implementation with MarginalTradeoffRepair.
"""

import time

import numpy as np
from loguru import logger
from pymoo.algorithms.moo.spea2 import SPEA2
from pymoo.optimize import minimize
from pymoo.termination import get_termination

from supply_chain_research.config import MasterConfig
from supply_chain_research.phase1_foundation.nsga2_solver import (
    MarginalTradeoffRepair,
    SupplyChainProblem,
)
from supply_chain_research.phase1_foundation.solver_base import BaseSolver, SolverResult


class SPEA2Solver(BaseSolver):
    """Strength Pareto Evolutionary Algorithm 2 (SPEA2) solver.
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
        """Run SPEA2 optimization.
        Parameters
        ----------
        """
        logger.info("Initializing SPEA2 solver...")
        start_time = time.time()

        n_w = config.network.n_warehouses
        n_c = config.network.n_customers
        n_v = 2

        problem = SupplyChainProblem(config, distance_matrix, demand)

        # Define SPEA2 algorithm
        algorithm = SPEA2(
            pop_size=config.nsga.pop_size,
            repair=MarginalTradeoffRepair(
                n_warehouses=n_w,
                n_customers=n_c,
                n_vehicle_types=n_v,
                demand=demand,
                warehouse_capacities=problem.warehouse_capacities,
                distance_matrix=distance_matrix,
                vehicle_types=problem.vehicle_types,
                config=config,
            ),
        )

        termination = get_termination("n_gen", config.nsga.n_gen)

        res = minimize(
            problem,
            algorithm,
            termination,
            seed=seed,
            verbose=False,
            save_history=True,
        )

        runtime = time.time() - start_time
        logger.info(f"SPEA2 execution finished in {runtime:.2f}s")

        # Extract convergence history (hypervolume)
        convergence_history = []
        if res.history:
            for algo in res.history:
                opt = algo.opt
                if opt is not None and len(opt) > 0:
                    F_gen = opt.get("F")
                    try:
                        from pymoo.indicators.hv import HV
                        ref = F_gen.max(axis=0) * 1.1 if len(F_gen) > 0 else np.array([1e6, 1e6])
                        hv_indicator = HV(ref_point=ref, norm_ref_point=False)
                        val = float(hv_indicator(F_gen))
                        convergence_history.append(val)
                    except Exception:
                        convergence_history.append(0.0)

        # Build SolverResult
        result = SolverResult(
            pareto_front=res.F if res.F is not None else np.empty((0, 2)),
            decision_variables=res.X if res.X is not None else np.empty((0, problem.n_var)),
            convergence_history=convergence_history,
            runtime_seconds=runtime,
            n_function_evaluations=res.algorithm.evaluator.n_eval,
            algorithm_name="SPEA2",
            metadata={"res": res},
        )
        result.compute_hypervolume()
        return result

    @property
    def name(self) -> str:
        """
        Parameters
        ----------
        """
        return "SPEA2"


def run_spea2(
    config: MasterConfig,
    distance_matrix: np.ndarray,
    demand: np.ndarray,
    seed: int = 42,
) -> SolverResult:
    """Wrapper function to execute SPEA2 solver.
    Parameters
    ----------
    """
    solver = SPEA2Solver()
    return solver.solve(config, distance_matrix, demand, seed)
