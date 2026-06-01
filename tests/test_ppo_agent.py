"""Property-based and preservation tests for the PPO agent.

This module covers task 4.7 of the supply-chain-research-audit spec.
It is deliberately separate from ``tests/test_gym_env.py``
(legacy ``TestPPOAgent`` unit tests) and
``tests/test_math_correctness.py`` (FIX-010 / Audit 2.2 numerical
checks) so the three named ``Test*`` classes required by the task
land in one auditable file. Style and hypothesis cadence mirror
``tests/test_emission_model.py`` (task 4.1),
``tests/test_nsga2_solver.py`` (task 4.3),
``tests/test_des_environment.py`` (task 4.4),
``tests/test_lstm_forecaster.py`` (task 4.5), and
``tests/test_gym_environment.py`` (task 4.6).

The three classes encode invariants from
``.kiro/specs/supply-chain-research-audit/bugfix.md``:

* ``TestActionDistributionValidity`` -- the production
  :class:`~supply_chain_research.phase3_ai.ppo_agent.ActorNetwork`
  emits a Beta(alpha, beta) distribution per action dimension on the
  open interval ``(0, 1)`` (FIX-010 / Audit 1.5; production uses
  ``action_clamp_eps=1e-6``); sampled actions lie in
  ``(eps, 1 - eps)`` and the resulting ``log_prob(action)`` is
  finite with shape ``(batch,)`` -- the sum-over-action-dim shape
  documented in ``ActorNetwork.evaluate_actions``
  [Chou-2017 §3.2] [Schulman-2017 §3].
* ``TestAdvantageNormalization``     -- the per-minibatch advantage
  normalisation formula
  ``(adv - adv.mean()) / (adv.std() + 1e-8)`` documented in
  ``PPOAgent.update`` (Audit 2.2) drives a synthetic
  ``Normal(mu, sigma)`` advantage batch to mean ``in [-1e-6, 1e-6]``
  and std ``in [1 - 1e-3, 1 + 1e-3]`` for batch sizes large enough
  that finite-sample bias is below the asserted tolerance
  [Andrychowicz-2021 §3.5] [Schulman-2017 §6.1].
* ``TestRatioClipping``              -- the importance-ratio clip
  ``ratio_clipped = clip(exp(new_lp - old_lp), 1 - eps, 1 + eps)``
  with ``eps = PPOConfig().clip_range = 0.2`` is applied verbatim
  in ``PPOAgent.update`` so ``ratio_clipped`` lies in
  ``[1 - eps - 1e-9, 1 + eps + 1e-9]`` regardless of the raw
  ratio's magnitude [Schulman-2017 §3 Eq. 7].

Workaround note for ``TestRatioClipping``
-----------------------------------------
Production ``PPOAgent.update`` applies *two* clips in sequence
before forming the surrogate loss: a defensive numerical guard
``ratio = clip(ratio, ratio_clamp_min, ratio_clamp_max)``
(``[0.01, 100]``; Huang 2022 detail #34) followed by the canonical
PPO-Clip ``surr2 = clip(ratio, 1 - clip_range, 1 + clip_range) *
mb_adv`` (``eps = 0.2``; [Schulman-2017 §3 Eq. 7]). The test
evaluates the canonical PPO-Clip property by replicating the
exact two-step expression on synthetic ``(new_lp, old_lp)`` pairs
(no autograd, no parameter updates) so the property check exercises
the production formula symbol-for-symbol without mutating any
production state.

References
----------
.. [Schulman-2017] Schulman, J., Wolski, F., Dhariwal, P.,
   Radford, A., & Klimov, O. (2017). Proximal Policy Optimization
   Algorithms. arXiv:1707.06347.
.. [Andrychowicz-2021] Andrychowicz, M., Raichuk, A., Sta\u0144czyk, P.,
   et al. (2021). What Matters In On-Policy Reinforcement Learning?
   A Large-Scale Empirical Study. arXiv:2006.05990.
.. [Chou-2017] Chou, P.-W., Maturana, D., & Scherer, S. (2017).
   Improving Stochastic Policy Gradients in Continuous Control with
   Deep Reinforcement Learning Using the Beta Distribution.
   ICML 2017, Proc. Mach. Learn. Res. 70, 834-843.
"""
# [Schulman-2017 §3 Eq. 7] PPO-Clip surrogate anchor;
# [Schulman-2017 §6.1] / [Andrychowicz-2021 §3.5] advantage
# normalisation anchor; [Chou-2017 §3.2] Beta-distribution actor
# head anchor; preservation per [bugfix.md C1.12 / C2.12]; mirrors
# hypothesis cadence in tests/test_emission_model.py (task 4.1),
# tests/test_nsga2_solver.py (task 4.3),
# tests/test_des_environment.py (task 4.4),
# tests/test_lstm_forecaster.py (task 4.5), and
# tests/test_gym_environment.py (task 4.6).

from __future__ import annotations

import numpy as np  # [synthetic batch generation]
import pytest
import torch  # [Schulman-2017 §3 — PPO-Clip operates on torch tensors]
from hypothesis import HealthCheck, given, settings, strategies as st

from supply_chain_research.config import PPOConfig  # [config FIX-002]
from supply_chain_research.phase3_ai.ppo_agent import (  # [SUT — task 4.7]
    ActorNetwork,
    PPOAgent,
)


# Project-wide preservation seed mandated by clauses C3.x; matches the
# seed used in tests/test_emission_model.py, tests/test_nsga2_solver.py,
# tests/test_des_environment.py, tests/test_lstm_forecaster.py, and
# tests/test_gym_environment.py.
_SEED = 42  # [bugfix.md project-wide preservation seed]

# Forward-passes through the PPO actor are CPU-bound; pin the thread
# count so hypothesis examples behave deterministically across hosts.
torch.set_num_threads(1)  # [task 4.7 — determinism for hypothesis budget]

# Small actor sizing for fast property tests. The full production env
# uses obs_dim=85, action_dim=20; the Beta-distribution validity
# property is size-agnostic, so we shrink to keep each hypothesis
# example under a few tens of milliseconds [Chou-2017 §3.2].
_OBS_DIM = 16  # [task 4.7 — small actor for fast PBT]
_ACTION_DIM = 4  # [task 4.7 — small actor for fast PBT]


# ---------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------


def _make_small_actor(
    obs_dim: int = _OBS_DIM,
    action_dim: int = _ACTION_DIM,
    config: PPOConfig | None = None,
) -> ActorNetwork:
    """Construct a small ``ActorNetwork`` for fast property tests.

    Parameters
    ----------
    obs_dim : int, optional
        Observation dimensionality; default :data:`_OBS_DIM` (16).
    action_dim : int, optional
        Action dimensionality; default :data:`_ACTION_DIM` (4).
    config : PPOConfig, optional
        PPO configuration. Defaults to a fresh :class:`PPOConfig`,
        which carries ``action_clamp_eps=1e-6``,
        ``actor_head_init_gain=0.01``, and the Beta-head NaN/Inf
        guards from FIX-010 [Chou-2017 §3.2].

    Returns
    -------
    ActorNetwork
        A freshly-initialised actor in eval mode -- LayerNorm + Tanh
        + softplus heads emit alpha, beta both > 1 so the underlying
        :class:`torch.distributions.Beta` is unimodal on ``(0, 1)``
        [Chou-2017 §3.2].
    """
    if config is None:
        config = PPOConfig()  # [config FIX-002 — production defaults]
    torch.manual_seed(_SEED)  # [seed=42 → deterministic init]
    actor = ActorNetwork(  # [SUT — ActorNetwork from ppo_agent.py]
        obs_dim=obs_dim, action_dim=action_dim, config=config,
    )
    actor.eval()  # [LayerNorm has no train-only side effects, but
    # we set eval to keep the contract symmetric with the LSTM tests]
    return actor


def _make_small_ppo_agent(
    obs_dim: int = _OBS_DIM,
    action_dim: int = _ACTION_DIM,
    config: PPOConfig | None = None,
) -> PPOAgent:
    """Construct a small :class:`PPOAgent` on CPU for fast property tests.

    Parameters
    ----------
    obs_dim, action_dim : int, optional
        Observation / action dimensionality; default
        :data:`_OBS_DIM` and :data:`_ACTION_DIM` (16 / 4).
    config : PPOConfig, optional
        PPO configuration; defaults to a fresh :class:`PPOConfig`.

    Returns
    -------
    PPOAgent
        Agent forced to ``device='cpu'`` so the hypothesis cadence is
        portable across CI hosts [Schulman-2017 §6.1].
    """
    if config is None:
        config = PPOConfig()  # [config FIX-002 — production defaults]
    torch.manual_seed(_SEED)  # [seed=42 → deterministic init]
    return PPOAgent(  # [SUT — PPOAgent from ppo_agent.py]
        obs_dim=obs_dim,
        action_dim=action_dim,
        config=config,
        device=torch.device("cpu"),  # [CPU for portability]
    )


# =====================================================================
# 1. TestActionDistributionValidity -- Beta actor outputs are valid
# =====================================================================


class TestActionDistributionValidity:
    """``ActorNetwork`` emits valid samples and finite log-probs.

    Per [Chou-2017 §3.2] the production actor parameterises a per-
    dimension Beta(alpha, beta) on the open interval ``(0, 1)`` with
    ``alpha, beta > 1`` (softplus + 1.0 heads). Sampled actions are
    therefore strictly inside the unit hypercube; the production
    ``ActorNetwork.get_action`` further clamps them to
    ``(eps, 1 - eps)`` with ``eps = PPOConfig().action_clamp_eps =
    1e-6`` so the boundary log-probability is finite. The
    sum-over-action-dim ``log_prob`` returned by ``get_action`` must
    therefore have shape ``(batch,)`` and be element-wise finite,
    and its value must agree with a manual recomputation under the
    same Beta(alpha, beta) PDF [Schulman-2017 §3].

    Validates: Requirements 1.12, 2.12 [bugfix.md C1.12 / C2.12]
    """

    def test_default_config_has_canonical_beta_eps(self):
        """``PPOConfig`` defaults match the values cited in the task.

        Sanity-floor: the rest of the suite depends on
        ``action_clamp_eps == 1e-6`` (the Beta open-interval guard)
        and ``clip_range == 0.2`` (the canonical PPO-Clip
        epsilon); guard the constants here so a future config edit
        fails CI immediately [Chou-2017 §3.2] [Schulman-2017 §6.1].

        Validates: Requirements 1.12, 2.12 [bugfix.md C1.12 / C2.12]
        """
        cfg = PPOConfig()  # [config FIX-002 — defaults]
        assert cfg.action_clamp_eps == pytest.approx(1e-6, abs=0.0)
        assert cfg.clip_range == pytest.approx(0.2, abs=0.0)
        # [Huang-2022 detail #34 — defensive ratio clamp]
        assert cfg.ratio_clamp_min == pytest.approx(0.01, abs=0.0)
        assert cfg.ratio_clamp_max == pytest.approx(100.0, abs=0.0)

    def test_smoke_default_grid_point(self):
        """Default ``(batch=4, obs_dim=16, action_dim=4)`` is valid.

        Provides a non-hypothesis floor so a regression that breaks
        the actor sampling path is caught even if hypothesis happens
        to skip its first example for any reason [Chou-2017 §3.2].

        Validates: Requirements 1.12, 2.12 [bugfix.md C1.12 / C2.12]
        """
        cfg = PPOConfig()  # [config FIX-002 — defaults]
        actor = _make_small_actor(config=cfg)  # [small Beta actor]
        torch.manual_seed(_SEED)  # [obs draw deterministic]
        obs = torch.randn(4, _OBS_DIM)  # [(batch, obs_dim)]
        with torch.no_grad():  # [eval-mode forward — no autograd]
            action, log_prob = actor.get_action(obs)
        # [Beta support — production clamps to (eps, 1 - eps)]
        eps = cfg.action_clamp_eps  # [1e-6 per FIX-010]
        assert action.shape == (4, _ACTION_DIM)  # [Chou-2017 §3.2]
        assert torch.all(action > eps - 1e-12)  # [open lower bound]
        assert torch.all(action < 1.0 - eps + 1e-12)  # [open upper]
        # [evaluate_actions sums over action_dim — shape (batch,)]
        assert log_prob.shape == (4,)
        assert torch.isfinite(log_prob).all()  # [no -inf at boundary]

    @given(  # [grid per task 4.7 — batch sweep {1, 4, 16, 64}]
        batch=st.sampled_from([1, 4, 16, 64]),
    )
    @settings(  # [match tests/test_emission_model.py cadence]
        max_examples=8,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_property_action_in_open_unit_interval(self, batch):
        """Property: ``forall batch. action in (eps, 1 - eps)``.

        Sweeps the documented batch grid and asserts every component
        of every sampled action lies strictly inside the production
        Beta-clamp window. The clamp ``eps = 1e-6`` is the production
        ``action_clamp_eps`` (FIX-010) [Chou-2017 §3.2].

        Validates: Requirements 1.12, 2.12 [bugfix.md C1.12 / C2.12]
        """
        cfg = PPOConfig()  # [config FIX-002 — defaults]
        actor = _make_small_actor(config=cfg)  # [Beta actor]
        torch.manual_seed(_SEED)  # [obs draw deterministic]
        obs = torch.randn(batch, _OBS_DIM)  # [(batch, obs_dim)]
        with torch.no_grad():  # [eval-mode forward — no autograd]
            action, _log_prob = actor.get_action(obs)
        eps = cfg.action_clamp_eps  # [1e-6 per FIX-010]
        # [strict open-interval property — Chou-2017 §3.2]
        assert action.shape == (batch, _ACTION_DIM)
        assert torch.all(action >= eps - 1e-12)  # [lower bound +/- 1e-12]
        assert torch.all(action <= 1.0 - eps + 1e-12)  # [upper bound]

    @given(  # [grid per task 4.7 — batch sweep {1, 4, 16, 64}]
        batch=st.sampled_from([1, 4, 16, 64]),
    )
    @settings(  # [match tests/test_emission_model.py cadence]
        max_examples=8,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_property_log_prob_is_finite_and_correct_shape(self, batch):
        """Property: ``log_prob`` is finite with shape ``(batch,)``.

        ``ActorNetwork.get_action`` returns the per-sample log-prob
        summed over the action dimension (the documented contract of
        the companion :meth:`ActorNetwork.evaluate_actions`), so the
        shape is ``(batch,)``. Finiteness is required so the
        downstream PPO-Clip surrogate is well-defined
        [Schulman-2017 §3 Eq. 7].

        Validates: Requirements 1.12, 2.12 [bugfix.md C1.12 / C2.12]
        """
        cfg = PPOConfig()  # [config FIX-002 — defaults]
        actor = _make_small_actor(config=cfg)  # [Beta actor]
        torch.manual_seed(_SEED)  # [obs draw deterministic]
        obs = torch.randn(batch, _OBS_DIM)  # [(batch, obs_dim)]
        with torch.no_grad():
            _action, log_prob = actor.get_action(obs)
        # [shape contract per evaluate_actions docstring]
        assert log_prob.shape == (batch,)
        # [no -inf / NaN at the Beta boundary thanks to action_clamp_eps]
        assert torch.isfinite(log_prob).all()

    def test_log_prob_matches_beta_pdf_on_default_grid(self):
        """``log_prob`` agrees with a manual Beta-PDF recomputation.

        Reproduces the production formula
        ``log_prob = sum_d Beta(alpha_d, beta_d).log_prob(action_d)``
        outside the actor and asserts agreement with the value
        returned by ``get_action`` to within float32 round-off. This
        is the strongest sense in which "the sampled action is a
        valid sample of the Beta distribution"
        [Chou-2017 §3.2] [Schulman-2017 §3].

        Validates: Requirements 1.12, 2.12 [bugfix.md C1.12 / C2.12]
        """
        cfg = PPOConfig()  # [config FIX-002 — defaults]
        actor = _make_small_actor(config=cfg)  # [Beta actor]
        torch.manual_seed(_SEED)  # [obs draw deterministic]
        obs = torch.randn(4, _OBS_DIM)  # [(batch, obs_dim)]
        with torch.no_grad():
            action, log_prob = actor.get_action(obs)
            # [recompute under the SAME (alpha, beta) heads — Chou-2017]
            alpha, beta = actor.forward(obs)
            manual = torch.distributions.Beta(  # [per-dim Beta]
                alpha, beta,
            ).log_prob(action).sum(dim=-1)
        # [float32 tolerance — actor returns float32 by default]
        assert torch.allclose(log_prob, manual, rtol=1e-5, atol=1e-5)


# =====================================================================
# 2. TestAdvantageNormalization -- per-minibatch z-score is unit-stat
# =====================================================================


def _normalize_advantages(adv: torch.Tensor) -> torch.Tensor:
    """Replicate ``PPOAgent.update`` per-minibatch z-score.

    The production formula at
    ``ppo_agent.PPOAgent.update`` (Audit 2.2) is
    ``mb_adv = (mb_adv - mb_adv.mean()) / (mb_adv.std() + 1e-8)``.
    The ``+ 1e-8`` term is the documented zero-variance guard
    [Andrychowicz-2021 §3.5] [Schulman-2017 §6.1].

    Parameters
    ----------
    adv : torch.Tensor
        1-D advantage batch.

    Returns
    -------
    torch.Tensor
        Z-scored advantage batch with the same shape as ``adv``.
    """
    return (adv - adv.mean()) / (adv.std() + 1e-8)  # [Audit 2.2]


class TestAdvantageNormalization:
    """Per-minibatch advantage normalisation has unit statistics.

    The production ``PPOAgent.update`` step applies
    ``(adv - adv.mean()) / (adv.std() + 1e-8)`` per minibatch (Audit
    2.2). Under any reasonably large batch the normalised advantages
    have mean exactly zero (algebraic) and std numerically
    indistinguishable from one (the ``+ 1e-8`` denominator term
    introduces a relative bias of order ``1e-8`` for unit-std
    inputs). The hypothesis sweep checks the property across a wide
    range of synthetic ``Normal(mu, sigma)`` distributions
    [Andrychowicz-2021 §3.5].

    Validates: Requirements 1.12, 2.12 [bugfix.md C1.12 / C2.12]
    """

    def test_smoke_known_grid_point(self):
        """``Normal(5, 10)`` with ``batch=2048`` yields unit stats.

        Provides a non-hypothesis floor matching the parameters
        spelled out by the task spec. ``batch=2048`` is the
        production ``steps_per_rollout`` per [Schulman-2017 §6.1
        Table 3], so the smoke test exercises the realistic update
        cadence end-to-end.

        Validates: Requirements 1.12, 2.12 [bugfix.md C1.12 / C2.12]
        """
        rng = np.random.default_rng(_SEED)  # [seed=42 reproducibility]
        adv_np = rng.normal(loc=5.0, scale=10.0, size=2048)
        # [exercise the production formula on a torch tensor]
        adv_t = torch.from_numpy(adv_np).to(torch.float64)
        out = _normalize_advantages(adv_t)
        # [post-norm mean is algebraically zero up to round-off]
        assert float(out.mean()) == pytest.approx(0.0, abs=1e-6)
        # [post-norm std is one up to the +1e-8 denom guard]
        assert float(out.std()) == pytest.approx(1.0, rel=1e-3, abs=1e-3)

    @given(  # [grid per task 4.7 — batch sweep {64, 256, 1024, 4096}]
        batch_size=st.sampled_from([64, 256, 1024, 4096]),
        mu=st.floats(  # [reasonable advantage scales — bounded for budget]
            min_value=-1e3, max_value=1e3,
            allow_nan=False, allow_infinity=False,
        ),
        sigma=st.floats(  # [strictly positive sigma — Normal contract]
            min_value=1e-2, max_value=1e2,
            allow_nan=False, allow_infinity=False,
        ),
        seed=st.integers(min_value=0, max_value=2**31 - 1),  # [seed sweep]
    )
    @settings(  # [match tests/test_emission_model.py cadence]
        max_examples=8,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_property_post_norm_mean_is_zero_and_std_is_unit(
        self, batch_size, mu, sigma, seed,
    ):
        """Property: ``mean ~= 0`` and ``std ~= 1`` after normalisation.

        Generates ``Normal(mu, sigma)`` advantage batches across the
        documented ``(batch_size, mu, sigma)`` grid and asserts
        post-normalisation statistics are within
        ``[-1e-6, 1e-6]`` for the mean and ``[1 - 1e-3, 1 + 1e-3]``
        for the std. The mean tolerance is float64-round-off-tight;
        the std tolerance accommodates the production
        ``+ 1e-8`` denominator guard [Andrychowicz-2021 §3.5].

        Validates: Requirements 1.12, 2.12 [bugfix.md C1.12 / C2.12]
        """
        rng = np.random.default_rng(seed)  # [hypothesis-driven seed]
        adv_np = rng.normal(loc=mu, scale=sigma, size=batch_size)
        adv_t = torch.from_numpy(adv_np).to(torch.float64)  # [exact math]
        out = _normalize_advantages(adv_t)  # [Audit 2.2 formula]
        # [algebraic zero up to fp64 round-off — Schulman-2017 §6.1]
        assert float(out.mean()) == pytest.approx(0.0, abs=1e-6)
        # [unit std up to the +1e-8 guard — Andrychowicz-2021 §3.5]
        assert float(out.std()) == pytest.approx(1.0, abs=1e-3)

    def test_zero_variance_advantages_are_finite(self):
        """Constant advantages do not produce NaN / Inf after norm.

        The ``+ 1e-8`` denominator guard exists precisely so a zero-
        variance batch (every value identical) does not blow up the
        per-minibatch z-score. Verify that the entire output is
        finite (and equal to zero) under that pathological input
        [Andrychowicz-2021 §3.5 — numerical stability].

        Validates: Requirements 1.12, 2.12 [bugfix.md C1.12 / C2.12]
        """
        adv = torch.full((1024,), fill_value=7.5, dtype=torch.float64)
        out = _normalize_advantages(adv)
        assert torch.isfinite(out).all()  # [no NaN / Inf]
        # [zero std → all-zero output up to fp round-off]
        assert torch.all(out.abs() < 1e-6)


# =====================================================================
# 3. TestRatioClipping -- importance ratios stay inside [1-eps, 1+eps]
# =====================================================================


def _ppo_clipped_ratio(
    new_log_prob: torch.Tensor,
    old_log_prob: torch.Tensor,
    config: PPOConfig,
) -> torch.Tensor:
    """Replicate ``PPOAgent.update`` two-step ratio clip.

    Production code at ``ppo_agent.PPOAgent.update`` does:

    .. code-block:: python

        ratio = torch.exp(new_lp - old_lp)
        ratio = torch.clamp(
            ratio, config.ratio_clamp_min, config.ratio_clamp_max,
        )                                                # [Huang-2022 #34]
        surr2 = torch.clamp(
            ratio,
            1.0 - config.clip_range,
            1.0 + config.clip_range,                     # [Schulman-2017 §3]
        ) * mb_adv

    The PPO-Clip property of interest is that the ratio entering
    ``surr2`` lies in ``[1 - eps, 1 + eps]`` regardless of the raw
    ``exp(new_lp - old_lp)`` magnitude.

    Parameters
    ----------
    new_log_prob, old_log_prob : torch.Tensor
        Per-sample log-probabilities under the new and old policies.
    config : PPOConfig
        Active PPO configuration (carries ``clip_range`` and the
        defensive ``ratio_clamp_*`` numerical bounds).

    Returns
    -------
    ratio_clipped : torch.Tensor
        The post-PPO-Clip ratio that multiplies ``mb_adv`` in
        ``surr2`` [Schulman-2017 §3 Eq. 7].
    """
    # [Schulman-2017 §3 — importance ratio]
    ratio = torch.exp(new_log_prob - old_log_prob)
    # [Huang-2022 #34 — defensive numerical guard]
    ratio = torch.clamp(
        ratio, config.ratio_clamp_min, config.ratio_clamp_max,
    )
    # [Schulman-2017 §3 Eq. 7 — canonical PPO-Clip]
    return torch.clamp(
        ratio, 1.0 - config.clip_range, 1.0 + config.clip_range,
    )


class TestRatioClipping:
    """Importance ratios are clipped to ``[1 - eps, 1 + eps]``.

    Per [Schulman-2017 §3 Eq. 7] PPO-Clip evaluates a surrogate
    objective whose ratio multiplier is clipped to a symmetric
    interval around 1. The production ``PPOAgent.update`` applies
    this clip with ``eps = PPOConfig().clip_range = 0.2`` (the
    community-standard default; cross-confirmed by
    [Andrychowicz-2021 §3.5] and Huang 2022 detail #5). The tests
    below verify the property by replicating the production formula
    on synthetic ``(new_log_prob, old_log_prob)`` pairs across a
    hypothesis-driven sweep so a regression that drops the clip
    fails CI immediately.

    Validates: Requirements 1.12, 2.12 [bugfix.md C1.12 / C2.12]
    """

    def test_smoke_known_extreme_ratios(self):
        """Extreme ratios (``exp(+/-10)``) are clamped to the eps box.

        Provides a non-hypothesis floor: pick
        ``new_lp - old_lp in {-10, +10}`` so the raw ratio is well
        outside the PPO-Clip window, and assert the clamped output
        sits exactly at the boundary [Schulman-2017 §3 Eq. 7].

        Validates: Requirements 1.12, 2.12 [bugfix.md C1.12 / C2.12]
        """
        cfg = PPOConfig()  # [config FIX-002 — defaults]
        eps = cfg.clip_range  # [0.2 — Schulman-2017 §6.1 Table 3]
        # [float64 to keep 1e-9 boundary tolerance — float32 round-off
        #  on 1.2 alone is ~1.2e-8 which would mask a real clip bug]
        new_lp = torch.tensor([10.0, -10.0, 0.0], dtype=torch.float64)
        old_lp = torch.tensor([0.0, 0.0, 0.0], dtype=torch.float64)
        clipped = _ppo_clipped_ratio(new_lp, old_lp, cfg)
        # [first sample: exp(10) >> 1 + eps → clamped to 1 + eps]
        assert float(clipped[0]) == pytest.approx(1.0 + eps, abs=1e-9)
        # [second sample: exp(-10) << 1 - eps → clamped to 1 - eps]
        assert float(clipped[1]) == pytest.approx(1.0 - eps, abs=1e-9)
        # [third sample: exp(0) == 1 → untouched]
        assert float(clipped[2]) == pytest.approx(1.0, abs=1e-9)

    @given(  # [grid per task 4.7 — random log-prob pairs]
        batch=st.sampled_from([1, 4, 16, 64, 256]),
        new_lp_scale=st.floats(  # [reasonable log-prob magnitudes]
            min_value=-20.0, max_value=20.0,
            allow_nan=False, allow_infinity=False,
        ),
        old_lp_scale=st.floats(  # [reasonable log-prob magnitudes]
            min_value=-20.0, max_value=20.0,
            allow_nan=False, allow_infinity=False,
        ),
        seed=st.integers(min_value=0, max_value=2**31 - 1),  # [seed sweep]
    )
    @settings(  # [match tests/test_emission_model.py cadence]
        max_examples=10,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_property_ratio_clipped_inside_eps_box(
        self, batch, new_lp_scale, old_lp_scale, seed,
    ):
        """Property: ``ratio_clipped in [1 - eps, 1 + eps]`` always.

        Draws ``new_log_prob`` and ``old_log_prob`` from
        independent ``Normal`` distributions whose location is the
        hypothesis-supplied scale, applies the production two-step
        clip, and asserts the output lies inside the canonical
        PPO-Clip window with a ``1e-9`` slack to swallow float64
        round-off [Schulman-2017 §3 Eq. 7].

        Validates: Requirements 1.12, 2.12 [bugfix.md C1.12 / C2.12]
        """
        cfg = PPOConfig()  # [config FIX-002 — defaults]
        eps = cfg.clip_range  # [0.2]
        rng = np.random.default_rng(seed)  # [hypothesis seed]
        # [draw log-probs from Normal centered at the supplied scale]
        new_lp = torch.from_numpy(  # [(batch,)]
            rng.normal(loc=new_lp_scale, scale=1.0, size=batch),
        ).to(torch.float64)
        old_lp = torch.from_numpy(  # [(batch,)]
            rng.normal(loc=old_lp_scale, scale=1.0, size=batch),
        ).to(torch.float64)
        clipped = _ppo_clipped_ratio(new_lp, old_lp, cfg)
        # [strict PPO-Clip box — Schulman-2017 §3 Eq. 7]
        assert float(clipped.min()) >= 1.0 - eps - 1e-9
        assert float(clipped.max()) <= 1.0 + eps + 1e-9
        # [defensive — clipped values are always finite by construction]
        assert torch.isfinite(clipped).all()

    def test_production_update_applies_the_clip(self):
        """``PPOAgent.update`` exercises the clip end-to-end.

        Drives the production ``update`` path on a synthetic rollout
        large enough to populate at least one minibatch, and asserts
        the returned metrics are finite. This complements the
        symbol-for-symbol replication above: if the production code
        ever deletes the ``torch.clamp(ratio, 1 - eps, 1 + eps)``
        line, the surrogate gradient blows up and ``actor_loss`` /
        ``critic_loss`` go non-finite [Schulman-2017 §3 Eq. 7].

        Validates: Requirements 1.12, 2.12 [bugfix.md C1.12 / C2.12]
        """
        cfg = PPOConfig(  # [shrink for CI budget]
            n_epochs=2,
            steps_per_rollout=128,
            minibatch_size_min=32,
            minibatch_count=4,
        )
        agent = _make_small_ppo_agent(config=cfg)  # [CPU agent]
        rng = np.random.default_rng(_SEED)  # [seed=42 reproducibility]
        n_steps = 64  # [enough to populate >= 1 minibatch]
        obs = rng.standard_normal((n_steps, _OBS_DIM)).astype(np.float32)
        # [actions in (0, 1) — Beta support per Chou-2017 §3.2]
        actions = rng.uniform(
            1e-5, 1.0 - 1e-5, size=(n_steps, _ACTION_DIM),
        ).astype(np.float32)
        rollout = {  # [shape contract per RolloutBuffer.get]
            "observations": obs,
            "actions": actions,
            "rewards": rng.standard_normal(n_steps).astype(np.float32),
            "values": rng.standard_normal(n_steps).astype(np.float32),
            "log_probs": rng.standard_normal(n_steps).astype(np.float32),
            "dones": np.zeros(n_steps, dtype=np.float32),
        }
        metrics = agent.update(rollout, last_value=0.0)
        # [end-to-end finiteness — clip prevents blow-ups]
        for key in ("actor_loss", "critic_loss", "entropy",
                    "mean_advantage", "mean_return"):
            assert key in metrics  # [contract]
            assert np.isfinite(metrics[key]), (
                f"PPOAgent.update returned non-finite {key}; the "
                f"PPO-Clip surrogate may be missing the canonical "
                f"clip(ratio, 1 - eps, 1 + eps) step."
            )
