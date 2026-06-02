"""Phase 1: Foundation - data engineering, emission model, optimization.

Exposes multi-objective optimization solvers and statistical comparison tools.
"""

from supply_chain_research.phase1_foundation.alns_solver import ALNSSolver, run_alns
from supply_chain_research.phase1_foundation.amosa_solver import AMOSASolver, run_amosa
from supply_chain_research.phase1_foundation.epsilon_constraint_solver import (
    EpsilonConstraintSolver,
    run_epsilon_constraint,
)
from supply_chain_research.phase1_foundation.ibea_solver import IBEASolver, run_ibea
from supply_chain_research.phase1_foundation.moead_solver import run_moead
from supply_chain_research.phase1_foundation.mopso_solver import MOPSOSolver, run_mopso
from supply_chain_research.phase1_foundation.nsga2_solver import run_nsga2
from supply_chain_research.phase1_foundation.single_objective_ga import (
    SingleObjectiveGASolver,
    run_single_objective_ga,
)
from supply_chain_research.phase1_foundation.solver_base import BaseSolver, SolverResult
from supply_chain_research.phase1_foundation.solver_comparison import (
    friedman_test,
    run_comparison,
    wilcoxon_pairwise,
)
from supply_chain_research.phase1_foundation.spea2_solver import SPEA2Solver, run_spea2
from supply_chain_research.phase1_foundation.weighted_sum_solver import (
    WeightedSumSolver,
    run_weighted_sum,
)
