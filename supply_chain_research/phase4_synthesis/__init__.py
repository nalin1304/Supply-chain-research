"""Phase 4: Synthesis - statistics, figures, tables.

Lazy imports: matplotlib (used by generate_all_figures) and pylatex
(used by generate_all_tables) are imported on demand to keep package
import time low. Test startup is faster.
"""

# Light modules — always imported
from supply_chain_research.phase4_synthesis.ablation_study import (
    run_ablation_study,
)
from supply_chain_research.phase4_synthesis.sensitivity_analysis import (
    compute_sensitivity_indices,
    rank_parameters,
    run_sensitivity_sweep,
)
from supply_chain_research.phase4_synthesis.statistical_tests import (
    bootstrap_ci,
    cliffs_delta,
    kruskal_wallis,
    mann_whitney_u,
    run_full_statistical_analysis,
    wilcoxon_signed_rank,
)


def __getattr__(name):
    """Lazy-load heavy figure/table modules.
    Parameters
    ----------
    """
    if name == "generate_all_figures":
        from supply_chain_research.phase4_synthesis.generate_all_figures import (
            generate_all_figures,
        )
        return generate_all_figures
    if name == "generate_all_tables":
        from supply_chain_research.phase4_synthesis.generate_latex_tables import (
            generate_all_tables,
        )
        return generate_all_tables
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "run_full_statistical_analysis",
    "wilcoxon_signed_rank",
    "kruskal_wallis",
    "mann_whitney_u",
    "cliffs_delta",
    "bootstrap_ci",
    "run_sensitivity_sweep",
    "compute_sensitivity_indices",
    "rank_parameters",
    "run_ablation_study",
    "generate_all_figures",
    "generate_all_tables",
]
