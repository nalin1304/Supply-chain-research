"""Base solver interface for multi-objective optimization.

Provides a unified abstract base class (BaseSolver) and result container
(SolverResult) so every solver in the phase1_foundation package exposes
a consistent API. New solvers subclass BaseSolver and implement
``solve(config, seed) -> SolverResult``.

Design decisions
----------------
- SolverResult wraps numpy arrays rather than pymoo Result objects so
  solvers that do not use pymoo (e.g. MOPSO, AMOSA) return the same
  type.
- ``hypervolume`` is computed lazily by ``compute_hypervolume()`` when
  the caller does not supply it, using the same pymoo HV indicator
  that the NSGA-II pipeline uses.
- ``convergence_history`` stores per-generation hypervolume values to
  enable convergence-speed comparisons across algorithms.

References
----------
.. [1] Zitzler, E., Laumanns, M. & Thiele, L. (2001). SPEA2: Improving
       the Strength Pareto Evolutionary Algorithm. TIK Report 103, ETH
       Zurich.
.. [2] Coello Coello, C. A. & Lechuga, M. S. (2002). MOPSO: A Proposal
       for Multiple Objective Particle Swarm Optimization. CEC 2002.
.. [3] Deb, K. (2001). Multi-Objective Optimization Using Evolutionary
       Algorithms. Wiley.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from loguru import logger


@dataclass
class SolverResult:
    """Unified result container for all multi-objective solvers.

    Attributes
    ----------
    pareto_front : np.ndarray
        Objective values of the non-dominated solutions, shape
        ``(n_solutions, n_objectives)``.
    decision_variables : np.ndarray
        Decision variable values of the non-dominated solutions,
        shape ``(n_solutions, n_vars)``.
    hypervolume : float
        Hypervolume indicator value of the Pareto front
        approximation relative to a reference point.
    convergence_history : list of float
        Per-generation or per-iteration hypervolume values that
        trace how the algorithm converged over time.
    runtime_seconds : float
        Wall-clock time in seconds for the solver execution.
    n_function_evaluations : int
        Total number of objective function evaluations consumed.
    algorithm_name : str
        Human-readable algorithm name (e.g. "SPEA2", "MOPSO").
    metadata : dict
        Algorithm-specific extra data (e.g. archive size, final
        temperature for SA-based solvers).
    """

    pareto_front: np.ndarray  # (n_solutions, n_objectives)
    decision_variables: np.ndarray  # (n_solutions, n_vars)
    hypervolume: float = 0.0
    convergence_history: list = field(default_factory=list)
    runtime_seconds: float = 0.0
    n_function_evaluations: int = 0
    algorithm_name: str = ""
    metadata: dict = field(default_factory=dict)

    @property
    def n_solutions(self) -> int:
        """Number of non-dominated solutions found."""
        return self.pareto_front.shape[0] if self.pareto_front.size > 0 else 0

    @property
    def n_objectives(self) -> int:
        """Number of objectives."""
        if self.pareto_front.ndim == 2:
            return self.pareto_front.shape[1]
        return 0

    def compute_hypervolume(
        self,
        ref_point: np.ndarray | None = None,
        margin: float = 1.1,
    ) -> float:
        """(Re)compute the hypervolume indicator.

        Parameters
        ----------
        ref_point : np.ndarray, optional
            Explicit reference point. When ``None`` the reference
            point is set to ``margin * max(pareto_front, axis=0)``.
        margin : float
            Multiplicative margin applied to the nadir point when
            ``ref_point`` is None.

        Returns
        -------
        float
            Hypervolume indicator value (higher is better).
        """
        if self.n_solutions == 0:
            logger.warning("Empty Pareto front, hypervolume is 0.0")
            return 0.0

        try:
            from pymoo.indicators.hv import HV
        except ImportError:
            logger.error("pymoo is required for HV computation")
            return 0.0

        valid_F = self.pareto_front[
            np.all(np.isfinite(self.pareto_front), axis=1)
        ]
        if valid_F.shape[0] == 0:
            return 0.0

        if ref_point is None:
            ref_point = valid_F.max(axis=0) * margin

        hv_indicator = HV(ref_point=ref_point, norm_ref_point=False)
        self.hypervolume = float(hv_indicator(valid_F))
        return self.hypervolume

    def __repr__(self) -> str:
        return (
            f"SolverResult(algorithm={self.algorithm_name!r}, "
            f"n_solutions={self.n_solutions}, "
            f"hypervolume={self.hypervolume:.6g}, "
            f"runtime={self.runtime_seconds:.2f}s, "
            f"n_evals={self.n_function_evaluations})"
        )


class BaseSolver(ABC):
    """Abstract base for all multi-objective optimization solvers.

    Subclasses must implement:
    - ``solve(config, seed) -> SolverResult``
    - ``name`` property returning a short algorithm identifier.

    The base class provides convenience helpers for timing, logging,
    and hypervolume computation that all concrete solvers inherit.
    """

    @abstractmethod
    def solve(
        self,
        config: Any,
        distance_matrix: np.ndarray,
        demand: np.ndarray,
        seed: int = 42,
    ) -> SolverResult:
        """Run the optimization and return a SolverResult.

        Parameters
        ----------
        config : MasterConfig
            Master configuration providing vehicle, network, and
            algorithm sub-configs.
        distance_matrix : np.ndarray
            Distance matrix in km, shape
            ``(n_warehouses, n_customers)``.
        demand : np.ndarray
            Per-customer demand in kg, shape ``(n_customers,)``.
        seed : int
            Random seed for reproducibility.

        Returns
        -------
        SolverResult
            Unified result container with Pareto front, decision
            variables, hypervolume, and convergence history.
        """
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Short, human-readable algorithm name (e.g. 'SPEA2')."""
        ...

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name!r})"
