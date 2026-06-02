"""IBEA (Indicator-Based Evolutionary Algorithm) solver for supply chain optimization.

Uses a custom indicator-based survival selection with additive epsilon indicator,
integrated into the pymoo GeneticAlgorithm framework.
"""

import time

import numpy as np
from loguru import logger
from pymoo.algorithms.base.genetic import GeneticAlgorithm
from pymoo.core.survival import Survival
from pymoo.operators.crossover.sbx import SBX
from pymoo.operators.mutation.pm import PM
from pymoo.operators.sampling.rnd import FloatRandomSampling
from pymoo.operators.selection.tournament import TournamentSelection
from pymoo.optimize import minimize
from pymoo.termination import get_termination
from pymoo.util.dominator import Dominator


def ibea_binary_tournament(pop, P, algorithm, **kwargs):
    """
    Parameters
    ----------
    """
    n_tournaments, n_parents = P.shape
    if n_parents != 2:
        raise ValueError("Only implemented for binary tournament!")
    S = np.full(n_tournaments, -1, dtype=int)
    for i in range(n_tournaments):
        a, b = P[i, 0], P[i, 1]
        a_cv, b_cv = pop[a].CV[0], pop[b].CV[0]
        if a_cv > 0.0 or b_cv > 0.0:
            if a_cv < b_cv:
                S[i] = a
            elif b_cv < a_cv:
                S[i] = b
            else:
                S[i] = a if algorithm.random_state.random() < 0.5 else b
        else:
            a_f, b_f = pop[a].F, pop[b].F
            rel = Dominator.get_relation(a_f, b_f)
            if rel == 1:
                S[i] = a
            elif rel == -1:
                S[i] = b
            else:
                S[i] = a if algorithm.random_state.random() < 0.5 else b
    return S[:, None]

from supply_chain_research.config import MasterConfig
from supply_chain_research.phase1_foundation.nsga2_solver import (
    MarginalTradeoffRepair,
    SupplyChainProblem,
)
from supply_chain_research.phase1_foundation.solver_base import BaseSolver, SolverResult


class IBEASurvival(Survival):
    """Environmental selection based on additive epsilon indicator (Zitzler & Kunzli 2004).
    Parameters
    ----------
    """

    def __init__(self, kappa: float = 0.05):
        """
        Parameters
        ----------
        """
        super().__init__(filter_infeasible=True)
        self.kappa = kappa

    def _do(self, problem, pop, n_survive, **kwargs):
        """
        Parameters
        ----------
        """
        F = pop.get("F")
        N = len(F)
        if N <= n_survive:
            return pop

        # Normalize objectives to [0, 1] for balanced indicator comparison
        F_min = F.min(axis=0)
        F_max = F.max(axis=0)
        F_range = F_max - F_min
        F_range[F_range == 0] = 1.0
        F_norm = (F - F_min) / F_range

        active = list(range(N))
        while len(active) > n_survive:
            F_active = F_norm[active]
            # Additive epsilon indicator matrix: I(y, x) = max_m (y_m - x_m)
            # Row index is y, Col index is x
            diff = F_active[:, None, :] - F_active[None, :, :]
            I = diff.max(axis=2)

            # Compute fitness: F(x) = sum_{y != x} -exp(-I(y, x) / kappa)
            matrix = -np.exp(-I / self.kappa)
            np.fill_diagonal(matrix, 0.0)
            fitness = matrix.sum(axis=0)

            # Remove worst (the one with smallest/most-negative fitness)
            worst_idx = np.argmin(fitness)
            active.pop(worst_idx)

        return pop[active]


class IBEASolver(BaseSolver):
    """Indicator-Based Evolutionary Algorithm (IBEA) solver.
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
        """Run IBEA optimization.
        Parameters
        ----------
        """
        logger.info("Initializing IBEA solver...")
        start_time = time.time()

        n_w = config.network.n_warehouses
        n_c = config.network.n_customers
        n_v = 2

        problem = SupplyChainProblem(config, distance_matrix, demand)

        # Build custom IBEA algorithm
        algorithm = GeneticAlgorithm(
            pop_size=config.nsga.pop_size,
            sampling=FloatRandomSampling(),
            crossover=SBX(prob=config.nsga.crossover_prob, eta=config.nsga.crossover_eta),
            mutation=PM(eta=config.nsga.mutation_eta),
            selection=TournamentSelection(func_comp=ibea_binary_tournament),
            survival=IBEASurvival(kappa=0.05),
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
        logger.info(f"IBEA execution finished in {runtime:.2f}s")

        # Extract convergence history
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
            algorithm_name="IBEA",
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
        return "IBEA"


def run_ibea(
    config: MasterConfig,
    distance_matrix: np.ndarray,
    demand: np.ndarray,
    seed: int = 42,
) -> SolverResult:
    """Wrapper function to execute IBEA solver.
    Parameters
    ----------
    """
    solver = IBEASolver()
    return solver.solve(config, distance_matrix, demand, seed)
