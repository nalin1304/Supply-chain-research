"""Unit and integration tests for the expanded optimization solvers (Phase 2)."""

import pytest
import numpy as np

from supply_chain_research.config import MasterConfig
from supply_chain_research.phase1_foundation import (
    SPEA2Solver, run_spea2,
    MOPSOSolver, run_mopso,
    IBEASolver, run_ibea,
    EpsilonConstraintSolver, run_epsilon_constraint,
    WeightedSumSolver, run_weighted_sum,
    SingleObjectiveGASolver, run_single_objective_ga,
    AMOSASolver, run_amosa,
    ALNSSolver, run_alns,
    run_comparison, friedman_test, wilcoxon_pairwise
)


@pytest.fixture
def test_setup():
    config = MasterConfig()
    config.network.n_customers = 5
    config.network.n_warehouses = 2
    config.nsga.pop_size = 10
    config.nsga.n_gen = 2

    rng = np.random.default_rng(42)
    dist = rng.uniform(50, 200, size=(2, 5))
    demand = rng.uniform(100, 500, size=5)

    return config, dist, demand


def test_spea2_solver(test_setup):
    config, dist, demand = test_setup
    res = run_spea2(config, dist, demand, seed=42)
    assert res.algorithm_name == "SPEA2"
    assert res.pareto_front.shape[1] == 2
    assert len(res.pareto_front) > 0


def test_mopso_solver(test_setup):
    config, dist, demand = test_setup
    res = run_mopso(config, dist, demand, seed=42)
    assert res.algorithm_name == "MOPSO"
    assert res.pareto_front.shape[1] == 2
    assert len(res.pareto_front) > 0


def test_ibea_solver(test_setup):
    config, dist, demand = test_setup
    res = run_ibea(config, dist, demand, seed=42)
    assert res.algorithm_name == "IBEA"
    assert res.pareto_front.shape[1] == 2
    assert len(res.pareto_front) > 0


def test_epsilon_constraint_solver(test_setup):
    config, dist, demand = test_setup
    res = run_epsilon_constraint(config, dist, demand, seed=42)
    assert res.algorithm_name == "Epsilon-Constraint"
    assert res.pareto_front.shape[1] == 2
    assert len(res.pareto_front) > 0


def test_weighted_sum_solver(test_setup):
    config, dist, demand = test_setup
    res = run_weighted_sum(config, dist, demand, seed=42)
    assert res.algorithm_name == "Weighted Sum"
    assert res.pareto_front.shape[1] == 2
    assert len(res.pareto_front) > 0


def test_single_objective_ga_solver(test_setup):
    config, dist, demand = test_setup
    res = run_single_objective_ga(config, dist, demand, seed=42)
    assert res.algorithm_name == "Single-Objective GA"
    assert res.pareto_front.shape[1] == 2
    assert len(res.pareto_front) > 0


def test_amosa_solver(test_setup):
    config, dist, demand = test_setup
    res = run_amosa(config, dist, demand, seed=42)
    assert res.algorithm_name == "AMOSA"
    assert res.pareto_front.shape[1] == 2
    assert len(res.pareto_front) > 0


def test_alns_solver(test_setup):
    config, dist, demand = test_setup
    res = run_alns(config, dist, demand, seed=42)
    assert res.algorithm_name == "ALNS"
    assert res.pareto_front.shape[1] == 2
    assert len(res.pareto_front) > 0


def test_comparison_framework(test_setup):
    config, dist, demand = test_setup
    solvers = [SPEA2Solver(), MOPSOSolver(), ALNSSolver()]
    comp_res = run_comparison(config, dist, demand, solvers, n_seeds=3)

    assert comp_res.solvers == ["SPEA2", "MOPSO", "ALNS"]
    assert len(comp_res.seeds) == 3
    assert "SPEA2" in comp_res.hypervolumes

    f_test = friedman_test(comp_res)
    assert "SPEA2" in f_test.mean_ranks

    w_test = wilcoxon_pairwise(comp_res)
    assert len(w_test.p_values) > 0
