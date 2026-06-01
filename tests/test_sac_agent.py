"""Tests for the SAC baseline agent (FIX-010, clause C2.6 / C2.14).

Covers six contracts:
    1. Actor produces actions in [-1, 1] under tanh squashing.
    2. log_prob shape contract.
    3. Twin-Q critic produces matching Q1 / Q2 shape.
    4. One ``SACAgent.update`` step runs without producing NaN/Inf.
    5. ``ReplayBuffer`` push / sample contract.
    6. Reproducibility under fixed seed (two builds → bit-identical
       first-batch update outputs).

Validates: Requirements 2.6.
"""

from __future__ import annotations

import random

import numpy as np
import pytest
import torch

from supply_chain_research.config import SACConfig
from supply_chain_research.phase3_ai.sac_agent import (
    ReplayBuffer,
    SACActorNetwork,
    SACAgent,
    SACCriticNetwork,
)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

OBS_DIM = 8
ACTION_DIM = 3
SEED = 42


def _seed_everything(seed: int = SEED) -> None:
    """Force determinism for the seeded-reproducibility test."""
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    torch.use_deterministic_algorithms(False)


def _make_config(buffer_size: int = 256) -> SACConfig:
    """Return a small SACConfig suitable for unit testing."""
    return SACConfig(
        replay_buffer_size=buffer_size,
        batch_size=16,
        learning_rate=3e-4,
        gamma=0.99,
        tau=0.005,
        alpha=0.2,
        alpha_auto=True,
        hidden_size=32,
        n_updates_per_step=1,
        warmup_steps=0,
        total_timesteps=100,
    )


def _populate_buffer(agent: SACAgent, n: int = 64,
                     rng: np.random.Generator | None = None) -> None:
    """Fill ``agent.replay_buffer`` with ``n`` random transitions."""
    if rng is None:
        rng = np.random.default_rng(SEED)
    for _ in range(n):
        obs = rng.standard_normal(OBS_DIM).astype(np.float32)
        action = rng.uniform(-1.0, 1.0, ACTION_DIM).astype(np.float32)
        reward = float(rng.standard_normal())
        next_obs = rng.standard_normal(OBS_DIM).astype(np.float32)
        done = bool(rng.integers(0, 2))
        agent.replay_buffer.push(obs, action, reward, next_obs, done)


# --------------------------------------------------------------------------- #
# 1. Actor produces actions in [-1, 1] under tanh squashing
# --------------------------------------------------------------------------- #

class TestActorTanhSquashing:
    """Validates: Requirements 2.6 (Gaussian actor + tanh squashing)."""

    def test_sample_in_unit_interval(self):
        _seed_everything()
        actor = SACActorNetwork(OBS_DIM, ACTION_DIM, hidden_size=32)
        obs = torch.randn(64, OBS_DIM)
        action, _ = actor.sample(obs)
        assert action.shape == (64, ACTION_DIM)
        # Closed interval [-1, 1] per Haarnoja 2018a Eq. 21
        # (tanh saturates at ±1 in float32 for |x| ≳ 9).
        assert torch.all(action >= -1.0)
        assert torch.all(action <= 1.0)

    def test_deterministic_action_in_unit_interval(self):
        """tanh(mean) must lie in [-1, 1] for any input magnitude."""
        _seed_everything()
        actor = SACActorNetwork(OBS_DIM, ACTION_DIM, hidden_size=32)
        obs = torch.randn(32, OBS_DIM) * 50.0  # large magnitudes
        mean, _ = actor.forward(obs)
        action = torch.tanh(mean)
        assert torch.all(action >= -1.0)
        assert torch.all(action <= 1.0)


# --------------------------------------------------------------------------- #
# 2. log_prob shape contract
# --------------------------------------------------------------------------- #

class TestLogProbShape:
    """Validates: Requirements 2.6 (log_prob shape (batch, 1))."""

    def test_log_prob_is_finite_and_shaped(self):
        _seed_everything()
        actor = SACActorNetwork(OBS_DIM, ACTION_DIM, hidden_size=32)
        obs = torch.randn(7, OBS_DIM)
        action, log_prob = actor.sample(obs)
        # Per Haarnoja 2018 Eq. 21 the squashed log-prob is summed over
        # action dimensions and kept as a column vector.
        assert log_prob.shape == (7, 1)
        assert torch.isfinite(log_prob).all()


# --------------------------------------------------------------------------- #
# 3. Twin-Q critic produces matching Q1 / Q2 shape
# --------------------------------------------------------------------------- #

class TestTwinQShape:
    """Validates: Requirements 2.6 (twin clipped-double-Q)."""

    def test_q1_q2_match_shape(self):
        _seed_everything()
        critic = SACCriticNetwork(OBS_DIM, ACTION_DIM, hidden_size=32)
        obs = torch.randn(11, OBS_DIM)
        action = torch.tanh(torch.randn(11, ACTION_DIM))
        q1, q2 = critic(obs, action)
        assert q1.shape == (11, 1)
        assert q2.shape == (11, 1)
        # Independent networks → values differ for almost any input.
        assert not torch.allclose(q1, q2)

    def test_q1_forward_matches_full_forward(self):
        _seed_everything()
        critic = SACCriticNetwork(OBS_DIM, ACTION_DIM, hidden_size=32)
        obs = torch.randn(5, OBS_DIM)
        action = torch.tanh(torch.randn(5, ACTION_DIM))
        q1_only = critic.q1_forward(obs, action)
        q1, _ = critic(obs, action)
        assert torch.allclose(q1_only, q1)


# --------------------------------------------------------------------------- #
# 4. One SACAgent.update step runs without NaN
# --------------------------------------------------------------------------- #

class TestUpdateStepNoNaN:
    """Validates: Requirements 2.6 (full SAC update, no NaN)."""

    def test_single_update_step(self):
        _seed_everything()
        cfg = _make_config()
        agent = SACAgent(OBS_DIM, ACTION_DIM, config=cfg,
                         device=torch.device('cpu'))
        _populate_buffer(agent, n=64)
        metrics = agent.update()
        assert metrics, "update should return non-empty metrics"
        for key in (
            'critic_loss', 'actor_loss', 'alpha_loss', 'alpha',
            'q1_mean', 'q2_mean', 'log_prob_mean',
        ):
            assert key in metrics
            value = metrics[key]
            assert np.isfinite(value), f"{key} produced non-finite value {value!r}"
        assert metrics['alpha'] > 0.0  # alpha = exp(log_alpha) > 0

    def test_target_critic_polyak_updated(self):
        """The target network must drift toward the online network."""
        _seed_everything()
        cfg = _make_config()
        agent = SACAgent(OBS_DIM, ACTION_DIM, config=cfg,
                         device=torch.device('cpu'))
        _populate_buffer(agent, n=64)
        # Before any update target == online (hard-copy at construction)
        for p, p_targ in zip(
            agent.critic.parameters(), agent.critic_target.parameters(),
        ):
            assert torch.allclose(p, p_targ)
        agent.update()
        # After one update online has moved; target has only moved by tau
        any_drift = False
        for p, p_targ in zip(
            agent.critic.parameters(), agent.critic_target.parameters(),
        ):
            if not torch.allclose(p, p_targ, atol=1e-7):
                any_drift = True
                break
        assert any_drift, (
            "Soft target update should produce a small drift between "
            "online and target critics after one gradient step."
        )


# --------------------------------------------------------------------------- #
# 5. Replay buffer push / sample contract
# --------------------------------------------------------------------------- #

class TestReplayBuffer:
    """Validates: Requirements 2.6 (replay buffer contract)."""

    def test_push_increments_length(self):
        buf = ReplayBuffer(capacity=10)
        assert len(buf) == 0
        for i in range(5):
            buf.push(
                np.zeros(OBS_DIM, dtype=np.float32),
                np.zeros(ACTION_DIM, dtype=np.float32),
                float(i),
                np.zeros(OBS_DIM, dtype=np.float32),
                False,
            )
        assert len(buf) == 5

    def test_sample_shapes_and_dtypes(self):
        buf = ReplayBuffer(capacity=64)
        rng = np.random.default_rng(SEED)
        for _ in range(32):
            buf.push(
                rng.standard_normal(OBS_DIM).astype(np.float32),
                rng.uniform(-1, 1, ACTION_DIM).astype(np.float32),
                float(rng.standard_normal()),
                rng.standard_normal(OBS_DIM).astype(np.float32),
                bool(rng.integers(0, 2)),
            )
        obs, actions, rewards, next_obs, dones = buf.sample(16)
        assert obs.shape == (16, OBS_DIM)
        assert actions.shape == (16, ACTION_DIM)
        assert rewards.shape == (16, 1)
        assert next_obs.shape == (16, OBS_DIM)
        assert dones.shape == (16, 1)
        for t in (obs, actions, rewards, next_obs, dones):
            assert t.dtype == torch.float32

    def test_capacity_eviction(self):
        buf = ReplayBuffer(capacity=4)
        for i in range(10):
            buf.push(
                np.array([float(i)] * OBS_DIM, dtype=np.float32),
                np.zeros(ACTION_DIM, dtype=np.float32),
                float(i),
                np.zeros(OBS_DIM, dtype=np.float32),
                False,
            )
        # Only the last `capacity` transitions should remain.
        assert len(buf) == 4

    def test_sample_requires_enough_data(self):
        buf = ReplayBuffer(capacity=8)
        buf.push(
            np.zeros(OBS_DIM, dtype=np.float32),
            np.zeros(ACTION_DIM, dtype=np.float32),
            0.0,
            np.zeros(OBS_DIM, dtype=np.float32),
            False,
        )
        with pytest.raises(ValueError):
            buf.sample(16)


# --------------------------------------------------------------------------- #
# 6. Seeded reproducibility — two builds with the same seed produce
#    bit-identical first-batch metrics.
# --------------------------------------------------------------------------- #

class TestReproducibility:
    """Validates: Requirements 2.6 (deterministic build under fixed seed)."""

    @staticmethod
    def _build_and_step(seed: int) -> dict:
        _seed_everything(seed)
        cfg = _make_config()
        agent = SACAgent(OBS_DIM, ACTION_DIM, config=cfg,
                         device=torch.device('cpu'))
        # Populate with a deterministic transition stream.
        rng = np.random.default_rng(seed)
        _populate_buffer(agent, n=64, rng=rng)
        # Re-seed torch right before the update so the in-update
        # randomness (replay sampling, reparam noise) is reproducible.
        _seed_everything(seed)
        return agent.update()

    def test_two_builds_match(self):
        m1 = self._build_and_step(SEED)
        m2 = self._build_and_step(SEED)
        assert set(m1.keys()) == set(m2.keys())
        for key in m1:
            assert m1[key] == pytest.approx(m2[key], rel=0, abs=0), (
                f"Reproducibility violated for {key}: {m1[key]} vs {m2[key]}"
            )

    def test_different_seeds_diverge(self):
        m_a = self._build_and_step(SEED)
        m_b = self._build_and_step(SEED + 7)
        # At least one metric must differ; otherwise the seed plumbing
        # is broken and reproducibility above would be vacuous.
        assert any(m_a[k] != m_b[k] for k in m_a)
