"""MOPSO (Multi-Objective Particle Swarm Optimization) solver.

Custom NumPy implementation of MOPSO with an external Pareto archive,
crowding distance leader selection, and custom MarginalTradeoffRepair.
"""

import time

import numpy as np
from loguru import logger

from supply_chain_research.config import MasterConfig
from supply_chain_research.phase1_foundation.nsga2_solver import (
    MarginalTradeoffRepair,
    SupplyChainProblem,
)
from supply_chain_research.phase1_foundation.solver_base import BaseSolver, SolverResult


def compute_crowding_distances(F: np.ndarray) -> np.ndarray:
    """Compute crowding distances for points in objective space.
    Parameters
    ----------
    """
    n = len(F)
    if n <= 2:
        return np.full(n, np.inf)

    cd = np.zeros(n)
    for m in range(F.shape[1]):
        idx = np.argsort(F[:, m])
        cd[idx[0]] = np.inf
        cd[idx[-1]] = np.inf

        f_min = F[idx[0], m]
        f_max = F[idx[-1], m]
        scale = f_max - f_min
        if scale == 0:
            scale = 1.0

        for i in range(1, n - 1):
            cd[idx[i]] += (F[idx[i + 1], m] - F[idx[i - 1], m]) / scale
    return cd


def update_archive(archive_X: list, archive_F: list, candidate_X: np.ndarray, candidate_F: np.ndarray, max_size: int = 100):
    """Update Pareto archive with new non-dominated solutions.
    Parameters
    ----------
    """
    # Check if candidate is dominated by any archive member
    for f in archive_F:
        if np.all(f <= candidate_F) and np.any(f < candidate_F):
            return  # Dominated, do not add

    # Remove any archive members dominated by the candidate
    keep_indices = []
    for idx, f in enumerate(archive_F):
        if not (np.all(candidate_F <= f) and np.any(candidate_F < f)):
            keep_indices.append(idx)

    new_X = [archive_X[i] for i in keep_indices] + [candidate_X.copy()]
    new_F = [archive_F[i] for i in keep_indices] + [candidate_F.copy()]

    # Prune archive if it exceeds size limit
    if len(new_X) > max_size:
        F_arr = np.array(new_F)
        cd = compute_crowding_distances(F_arr)
        # Remove the one with the smallest crowding distance (densest region)
        worst_idx = np.argmin(cd)
        new_X.pop(worst_idx)
        new_F.pop(worst_idx)

    archive_X.clear()
    archive_F.clear()
    archive_X.extend(new_X)
    archive_F.extend(new_F)


class MOPSOSolver(BaseSolver):
    """Multi-Objective Particle Swarm Optimization (MOPSO) solver.
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
        """Run MOPSO optimization.
        Parameters
        ----------
        """
        logger.info("Initializing MOPSO solver...")
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

        rng = np.random.default_rng(seed)

        # PSO parameters
        pop_size = config.nsga.pop_size
        n_gen = config.nsga.n_gen
        w = 0.5  # Inertia weight
        c1 = 1.5  # Cognitive coefficient
        c2 = 1.5  # Social coefficient

        # Initialize particles
        X = rng.uniform(problem.xl, problem.xu, size=(pop_size, problem.n_var))
        X = repair._do(problem, X)

        out = {}
        problem._evaluate(X, out)
        F = out["F"]

        # Velocities
        V = np.zeros_like(X)

        # Personal bests
        PBest_X = X.copy()
        PBest_F = F.copy()

        # External archive
        archive_X = []
        archive_F = []
        for i in range(pop_size):
            update_archive(archive_X, archive_F, X[i], F[i], max_size=pop_size)

        convergence_history = []
        n_evals = pop_size

        for gen in range(n_gen):
            # Leader selection: tournament on crowding distance in archive
            arch_F = np.array(archive_F)
            arch_X = np.array(archive_X)
            cd = compute_crowding_distances(arch_F)

            for i in range(pop_size):
                # Pick leader
                idx1, idx2 = rng.integers(0, len(arch_X), size=2)
                leader_idx = idx1 if cd[idx1] > cd[idx2] else idx2
                gbest = arch_X[leader_idx]

                # Update velocity and position
                r1, r2 = rng.uniform(0.0, 1.0, size=2)
                V[i] = w * V[i] + c1 * r1 * (PBest_X[i] - X[i]) + c2 * r2 * (gbest - X[i])
                X[i] += V[i]

            # Project particles back to bounds and repair constraints
            X = np.clip(X, problem.xl, problem.xu)
            X = repair._do(problem, X)

            # Evaluate
            problem._evaluate(X, out)
            F = out["F"]
            n_evals += pop_size

            # Update personal bests and archive
            for i in range(pop_size):
                # Personal best update (minimization):
                # If candidate dominates old pbest, update. If neither dominates, pick randomly.
                cand_F = F[i]
                old_F = PBest_F[i]
                cand_dom = np.all(cand_F <= old_F) and np.any(cand_F < old_F)
                old_dom = np.all(old_F <= cand_F) and np.any(old_F < cand_F)

                if cand_dom or (not old_dom and rng.uniform() < 0.5):
                    PBest_X[i] = X[i].copy()
                    PBest_F[i] = F[i].copy()

                update_archive(archive_X, archive_F, X[i], F[i], max_size=pop_size)

            # Compute current hypervolume of archive
            try:
                from pymoo.indicators.hv import HV
                current_arch_F = np.array(archive_F)
                ref = current_arch_F.max(axis=0) * 1.1 if len(current_arch_F) > 0 else np.array([1e6, 1e6])
                hv_indicator = HV(ref_point=ref, norm_ref_point=False)
                val = float(hv_indicator(current_arch_F))
                convergence_history.append(val)
            except Exception:
                convergence_history.append(0.0)

        runtime = time.time() - start_time
        logger.info(f"MOPSO execution finished in {runtime:.2f}s")

        result = SolverResult(
            pareto_front=np.array(archive_F),
            decision_variables=np.array(archive_X),
            convergence_history=convergence_history,
            runtime_seconds=runtime,
            n_function_evaluations=n_evals,
            algorithm_name="MOPSO",
            metadata={"archive_size": len(archive_X)},
        )
        result.compute_hypervolume()
        return result

    @property
    def name(self) -> str:
        """
        Parameters
        ----------
        """
        return "MOPSO"


def run_mopso(
    config: MasterConfig,
    distance_matrix: np.ndarray,
    demand: np.ndarray,
    seed: int = 42,
) -> SolverResult:
    """Wrapper function to execute MOPSO solver.
    Parameters
    ----------
    """
    solver = MOPSOSolver()
    return solver.solve(config, distance_matrix, demand, seed)
