# Advanced Research Roadmap

This is the improved implementation plan for the next research layer.
It treats the original Phase 7-10 proposal as a direction, but adds
gates that protect the current passing codebase and keep claims
reviewer-defensible.

## Goal

Strengthen the paper around two reviewer questions:

1. Does the policy generalize beyond the synthetic simulator?
2. Can practitioners understand and trust the learned policy?

The implementation should be additive. Existing NSGA-II/III, MOEA/D,
DES, PPO, forecasting, figures, tables, and dashboard behavior must keep
passing before cloud runs are launched.

## Phase 7 — Graph Forecasting And MAPPO

Scope:

- Harden the existing `GNNForecaster` as a tested ST-GNN baseline.
- Harden MAPPO checkpointing and cloud training.
- Compare ST-GNN against the existing forecast leaderboard before
  making any accuracy claim.

Acceptance gates:

- ST-GNN trains on a small synthetic series and returns non-negative
  `(horizon, n_customers)` predictions.
- MAPPO can save and reload actor/critic weights without shape drift.
- Modal MAPPO job writes models/logs to the `supply-chain-runs` volume.

## Phase 8 — Sim-To-Real Transfer

Scope:

- Use M5 as the first external demand stress test, with deterministic
  synthetic fallback when Kaggle files are absent.
- Use domain randomization during training, then evaluate zero-shot on
  real or M5-like demand.
- Always mark whether the evaluation used real M5 files or fallback
  synthetic data.

Acceptance gates:

- M5 loader returns deterministic shape-stable data.
- Domain randomization records the sampled parameters for each episode.
- Sim-to-real evaluator returns a metrics dictionary including
  `mean_service_level`, `p10_service_level`, and `synthetic_data`.

## Phase 9 — Explainability

Scope:

- Extract a shallow tree policy from a trained PPO/MAPPO checkpoint.
- Add forecast attribution only after the forecasting comparison
  identifies the model worth explaining.

Acceptance gates:

- Tree depth is configurable and defaults to `<= 8`.
- Extracted policy is evaluated against the source agent on identical
  seeds.
- Explanations are saved as artifacts, not only logs.

## Phase 10 — Risk-Averse RL

Scope:

- Add CVaR evaluation first, then consider CVaR training.
- Report mean reward, p10 reward, worst decile service level, and
  stockout-tail metrics.

Acceptance gates:

- Tail-risk metrics run against existing PPO checkpoints.
- CVaR improvement claims require paired seeds and statistical tests.

## Phase 11 — Adversarial Robust RL

Scope:

- Transition from Domain Randomization to an active Minimax Adversarial RL setup.
- Introduce an `AttackerPPOAgent` that perturbs lead times and capacities to minimize the MAPPO agent's reward.

Acceptance gates:

- Zero-sum reward constraint is mathematically verified.
- The Defender agent demonstrates lower cost variance against the trained Attacker compared to the Phase 10 CVaR baseline.

## Phase 12 — Offline RL (Decision Transformers)

Scope:

- Extract $1,000,000$ historical transitions using the `(R,s,S)` policy into an HDF5 dataset.
- Train a Causal Decision Transformer on expert historical sequences before online fine-tuning.

Acceptance gates:

- Causal masking correctly prevents the Transformer from looking at future states.
- Sim-to-Real gap is explicitly measured before online fine-tuning.

## Phase 13 — Dynamic Spatio-Temporal Routing

Scope:

- Integrate Kaggle Delhi Traffic datasets to construct time-of-day penalty matrices.
- Move beyond static OSRM corrections and penalize NSGA-II routes dynamically during 09:00 and 18:00 rush hours.

Acceptance gates:

- Identical route permutations yield different objective costs depending on the exact dispatch time.

## Phase 14 — Multi-Objective RL (MORL)

Scope:

- Deprecate NSGA-II and upgrade MAPPO to natively output Pareto-optimal solutions for both Inventory Cost and Routing Emissions.
- Inject a continuous preference vector $\omega$ into the agent's observation space.

Acceptance gates:

- The MORL agent can dynamically trade-off Carbon vs Cost at inference time without re-training.
- Joint-Normalized Hypervolume (JNHV) matches or exceeds the Phase 1 NSGA-II baseline.

## Modal Runbook

The local Modal profile is `nalinaggarwal28`, corresponding to the user's
Modal account. Use detached jobs for long training:

```bash
modal run --detach cloud_training/modal_train.py
modal run --detach supply_chain_research/phase3_ai/modal_mappo_trainer.py --timesteps 1000000
```

Monitor:

```bash
modal app logs supply-chain-ultimate-v3
modal app logs supply-chain-mappo-trainer
```

Download MAPPO outputs:

```bash
modal volume get supply-chain-runs / ./cloud_training/modal_outputs/
```

## Guardrails

- Run local contract tests before any cloud job.
- Do not overwrite existing `data/results` unless the artifact name is
  versioned or explicitly intended to replace the current paper number.
- Keep all fallback synthetic data clearly labeled.
- Do not claim top-tier performance until the artifact-backed comparison
  and statistical test exist.
