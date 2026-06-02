"""Contracts for the advanced research modules (Phases 7-10)."""

from pathlib import Path

import numpy as np
import pytest

from supply_chain_research.config import MasterConfig, PPOConfig
from supply_chain_research.phase3_ai.dr_env_wrapper import DomainRandomizationWrapper
from supply_chain_research.phase3_ai.gnn_forecaster import GNNForecaster
from supply_chain_research.phase3_ai.gym_environment import SupplyChainEnv
from supply_chain_research.phase3_ai.m5_data_loader import M5DataLoader
from supply_chain_research.phase3_ai.mappo_agent import MAPPOAgent
from supply_chain_research.phase3_ai.marl_env import MultiAgentSupplyChainEnv
from supply_chain_research.phase3_ai.sim2real_evaluator import evaluate_sim2real


def _small_config() -> MasterConfig:
    cfg = MasterConfig.derive_from_problem_size(4, 2)
    cfg.gym_env.episode_length = 5
    cfg.simulation.sim_days = 5
    cfg.network.warehouse_capacities = [2000.0, 2000.0]
    cfg.ppo.hidden_size = 16
    cfg.ppo.steps_per_rollout = 8
    cfg.ppo.minibatch_size_min = 4
    cfg.ppo.minibatch_count = 2
    cfg.ppo.n_epochs = 1
    return cfg


def test_m5_synthetic_fallback_is_deterministic(tmp_path: Path):
    a = M5DataLoader(tmp_path / "missing", n_customers=6, seed=123).load_or_simulate()
    b = M5DataLoader(tmp_path / "missing", n_customers=6, seed=123).load_or_simulate()

    assert a.shape == (1913, 6)
    assert a.dtype == np.float32
    np.testing.assert_allclose(a, b)


def test_domain_randomization_records_episode_parameters():
    cfg = _small_config()
    env = SupplyChainEnv(
        n_customers=4,
        n_warehouses=2,
        episode_length=5,
        config=cfg,
        stress_mode=True,
    )
    wrapped = DomainRandomizationWrapper(env, randomization_scale=0.1, seed=7)
    obs, info = wrapped.reset(seed=7)

    assert obs.shape == env.observation_space.shape
    assert "lead_time_days" in wrapped.last_randomization
    assert 1 <= wrapped.base_env._lead_time_days <= 4
    assert np.all(wrapped.base_env.warehouse_capacities > 0)


def test_mappo_checkpoint_roundtrip(tmp_path: Path):
    cfg = _small_config()
    ppo_cfg = PPOConfig(hidden_size=16, steps_per_rollout=8, n_epochs=1)
    env = MultiAgentSupplyChainEnv(
        n_customers=4,
        n_warehouses=2,
        episode_length=5,
        config=cfg,
    )
    agent = MAPPOAgent(
        env.local_obs_dim,
        env.global_obs_dim,
        env.action_dim,
        env.n_agents,
        config=ppo_cfg,
        device="cpu",
    )
    path = tmp_path / "mappo.pt"
    agent.save(str(path))

    loaded = MAPPOAgent(
        env.local_obs_dim,
        env.global_obs_dim,
        env.action_dim,
        env.n_agents,
        config=ppo_cfg,
        device="cpu",
    )
    loaded.load(str(path))

    for p1, p2 in zip(agent.actor.parameters(), loaded.actor.parameters()):
        assert np.allclose(p1.detach().numpy(), p2.detach().numpy())


def test_gnn_forecaster_smoke():
    rng = np.random.default_rng(42)
    data = rng.uniform(0, 10, size=(24, 3)).astype(np.float32)
    forecaster = GNNForecaster(
        seq_length=8,
        batch_size=4,
        epochs=1,
        gcn_hidden=4,
        rnn_hidden=8,
        device="cpu",
        seed=42,
    )
    forecaster.fit(data)
    pred = forecaster.predict(5)

    assert pred.shape == (5, 3)
    assert np.all(pred >= 0.0)


def test_sim2real_evaluator_returns_metrics(tmp_path: Path):
    metrics = evaluate_sim2real(
        model_path=str(tmp_path / "missing.pt"),
        data_dir=str(tmp_path / "m5"),
        n_customers=4,
        n_warehouses=2,
        seed=42,
        max_days=8,
    )

    assert metrics["model_loaded"] is False
    assert metrics["synthetic_data"] is True
    assert metrics["n_customers"] == 4
    assert 0.0 <= metrics["mean_service_level"] <= 1.0
    assert 0.0 <= metrics["p10_service_level"] <= 1.0
