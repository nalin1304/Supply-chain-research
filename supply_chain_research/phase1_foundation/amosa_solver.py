"""AMOSA (Archived Multi-Objective Simulated Annealing) solver.

Custom NumPy implementation of AMOSA (Bandyopadhyay et al. 2008)
with temperature-based dominated state acceptance, Pareto archive,
geometric cooling schedule, and custom MarginalTradeoffRepair.
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


def dominates(a: np.ndarray, b: np.ndarray) -> bool:
    """Return True if a dominates b (minimization).
    Parameters
    ----------
    
            Parameters
            ----------
            a : type
                Description of a.
            b : type
                Description of b.
        """
    return np.all(a <= b) and np.any(a < b)


def domination_amount(a: np.ndarray, b: np.ndarray) -> float:
    """Calculate the amount of domination of a over b.
    Parameters
    ----------
    
            Parameters
            ----------
            a : type
                Description of a.
            b : type
                Description of b.
        """
    # Domination difference: product of positive differences
    diff = np.maximum(0.0, a - b)
    return float(np.prod(diff[diff > 0])) if np.any(diff > 0) else 0.0


class AMOSASolver(BaseSolver):
    """Archived Multi-Objective Simulated Annealing (AMOSA) solver.
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
        """Run AMOSA optimization.
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
        logger.info("Initializing AMOSA solver...")
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

        # AMOSA parameters
        t_max = 100.0  # Max temperature
        t_min = 0.01  # Min temperature
        alpha = 0.90  # Geometric cooling rate
        max_iter = 10  # Iterations per temperature step
        archive_limit = config.nsga.pop_size  # Limit archive size

        # Initialize archive and current state
        # Create a few initial solutions to populate the archive
        pop_size = 20
        X_init = rng.uniform(problem.xl, problem.xu, size=(pop_size, problem.n_var))
        X_init = repair._do(problem, X_init)

        out = {}
        problem._evaluate(X_init, out)
        F_init = out["F"]

        archive_X = []
        archive_F = []
        for i in range(pop_size):
            # Update archive manually
            is_dom = False
            for f in archive_F:
                if dominates(f, F_init[i]):
                    is_dom = True
                    break
            if not is_dom:
                keep = [k for k, f in enumerate(archive_F) if not dominates(F_init[i], f)]
                archive_X = [archive_X[k] for k in keep] + [X_init[i].copy()]
                archive_F = [archive_F[k] for k in keep] + [F_init[i].copy()]

        # Set current state to a random non-dominated solution from archive
        curr_idx = rng.integers(0, len(archive_X))
        x_curr = archive_X[curr_idx].copy()
        f_curr = archive_F[curr_idx].copy()

        t = t_max
        n_evals = pop_size
        convergence_history = []

        logger.info("Executing Simulated Annealing cooling schedule...")
        while t > t_min:
            for _ in range(max_iter):
                # 1. Generate neighbor via perturbation (5% of variables)
                perturb_mask = rng.random(problem.n_var) < 0.05
                if not np.any(perturb_mask):
                    perturb_mask[rng.integers(0, problem.n_var)] = True

                x_cand = x_curr.copy()
                std = (problem.xu - problem.xl) * 0.1
                x_cand[perturb_mask] += rng.normal(0.0, std[perturb_mask])
                x_cand = np.clip(x_cand, problem.xl, problem.xu)
                x_cand = repair._do(problem, x_cand[None, :])[0]

                # 2. Evaluate candidate
                problem._evaluate(x_cand[None, :], out)
                f_cand = out["F"][0]
                n_evals += 1

                # 3. Check domination status between candidate and current
                cand_dom = dominates(f_cand, f_curr)
                curr_dom = dominates(f_curr, f_cand)

                if cand_dom:
                    # Candidate dominates current
                    # Check domination with archive
                    dominated_by_arch = False
                    dominates_arch_members = []
                    for k, f in enumerate(archive_F):
                        if dominates(f, f_cand):
                            dominated_by_arch = True
                            break
                        if dominates(f_cand, f):
                            dominates_arch_members.append(k)

                    if dominated_by_arch:
                        # Case 1: Dominated by some archive member, accept with prob
                        # Calculate avg domination difference
                        delta = np.mean([domination_amount(f, f_cand) for f in archive_F if dominates(f, f_cand)])
                        p = 1.0 / (1.0 + np.exp(delta / t))
                        if rng.uniform() < p:
                            x_curr = x_cand.copy()
                            f_curr = f_cand.copy()
                    else:
                        # Case 2: Candidate dominates current and is not dominated by archive
                        x_curr = x_cand.copy()
                        f_curr = f_cand.copy()
                        # Update archive
                        if dominates_arch_members:
                            keep = [k for k in range(len(archive_F)) if k not in dominates_arch_members]
                            archive_X = [archive_X[k] for k in keep]
                            archive_F = [archive_F[k] for k in keep]
                        archive_X.append(x_cand.copy())
                        archive_F.append(f_cand.copy())
                elif curr_dom:
                    # Current dominates candidate
                    # Acceptance probability based on domination amount
                    delta = domination_amount(f_curr, f_cand)
                    p = 1.0 / (1.0 + np.exp(delta / t))
                    if rng.uniform() < p:
                        x_curr = x_cand.copy()
                        f_curr = f_cand.copy()
                else:
                    # Current and candidate are incomparable
                    # Check dominance with archive
                    dominated_by_arch = False
                    for f in archive_F:
                        if dominates(f, f_cand):
                            dominated_by_arch = True
                            break

                    if not dominated_by_arch:
                        # Add to archive and accept as current
                        keep = [k for k, f in enumerate(archive_F) if not dominates(f_cand, f)]
                        archive_X = [archive_X[k] for k in keep] + [x_cand.copy()]
                        archive_F = [archive_F[k] for k in keep] + [f_cand.copy()]
                        x_curr = x_cand.copy()
                        f_curr = f_cand.copy()
                    else:
                        # Dominated by archive, accept with prob
                        delta = np.mean([domination_amount(f, f_cand) for f in archive_F if dominates(f, f_cand)])
                        p = 1.0 / (1.0 + np.exp(delta / t))
                        if rng.uniform() < p:
                            x_curr = x_cand.copy()
                            f_curr = f_cand.copy()

                # Limit archive size
                if len(archive_X) > archive_limit:
                    # Prune using crowding distance
                    from supply_chain_research.phase1_foundation.mopso_solver import (
                        compute_crowding_distances,
                    )
                    F_arr = np.array(archive_F)
                    cd = compute_crowding_distances(F_arr)
                    worst = np.argmin(cd)
                    archive_X.pop(worst)
                    archive_F.pop(worst)

            # Record current hypervolume
            try:
                from pymoo.indicators.hv import HV
                current_arch_F = np.array(archive_F)
                ref = current_arch_F.max(axis=0) * 1.1 if len(current_arch_F) > 0 else np.array([1e6, 1e6])
                hv_indicator = HV(ref_point=ref, norm_ref_point=False)
                val = float(hv_indicator(current_arch_F))
                convergence_history.append(val)
            except Exception:
                convergence_history.append(0.0)

            t *= alpha  # Geometric cooling

        runtime = time.time() - start_time
        logger.info(f"AMOSA execution finished in {runtime:.2f}s")

        result = SolverResult(
            pareto_front=np.array(archive_F),
            decision_variables=np.array(archive_X),
            convergence_history=convergence_history,
            runtime_seconds=runtime,
            n_function_evaluations=n_evals,
            algorithm_name="AMOSA",
            metadata={"final_temp": t},
        )
        result.compute_hypervolume()
        return result

    @property
    def name(self) -> str:
        """
        Parameters
        ----------
        """
        return "AMOSA"


def run_amosa(
    config: MasterConfig,
    distance_matrix: np.ndarray,
    demand: np.ndarray,
    seed: int = 42,
) -> SolverResult:
    """Wrapper function to execute AMOSA solver.
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
    solver = AMOSASolver()
    return solver.solve(config, distance_matrix, demand, seed)
