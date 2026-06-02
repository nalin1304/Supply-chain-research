# Training Guide

The training pipeline runs on NVIDIA T4 16 GB via Modal. It is fully resumable — if a job stops, re-running the same command picks up at the last completed step.

PPO Steps 4a, 4b, 4c (and the (R, s, S) baseline) instantiate the gym
environment with `stress_mode=True` per FIX-022. This activates the
literature-grade periodic-review lost-sales formulation
[Gijsbrechts et al. 2022, Vanvuchelen et al. 2024]; the legacy code
path remains the default for everything else.

## Launch (detached)

Make sure the local Modal profile is authenticated first:

```bash
modal profile current
modal token new
```

This workstation is expected to use the `nalinaggarwal28` profile for the
user's Modal account.

```bash
modal run --detach cloud_training/modal_train.py
```

The `--detach` flag survives terminal disconnect; the entry point also calls `train_ultimate.spawn()`, so even a local SIGINT will not kill the cloud function once it has been queued. The CLI prints the function-call ID and the volume name immediately after launch.

## Monitor

```bash
# Live logs for the current run
modal app logs supply-chain-ultimate-v3

# All running apps under the workspace
modal app list
```

Web UI: [https://modal.com/apps/nalinaggarwal28](https://modal.com/apps/nalinaggarwal28)

## Download results

```bash
modal volume get sc-results-v3 / ./data/results/
```

## Pipeline steps

| Step | Output file | Skip when |
|------|-------------|-----------|
| 1. Data generation | (in-memory) | never |
| 2. NSGA-II (50 seeds, pop=1000, gen=200) | `nsga2_all_results.pkl` | file exists |
| 2b. NSGA-III (50 seeds) | `nsga3_all_results.pkl` | file exists |
| 2c. MOEA/D (50 seeds) | `moead_all_results.pkl` | file exists |
| 3. LSTM (256 hidden × 3 layers, patience=15) | `lstm_predictions.npy` | file exists |
| 4a. PPO-20 (3 M steps, stress_mode) | `ppo_small_final.pt` | file exists |
| 4b. PPO-100 (2 M steps, stress_mode) | `ppo_full_final.pt` | file exists |
| 4c. (R, s, S) + random baselines (stress_mode) | `ppo_baselines.json` | file exists |
| 5. DES Monte-Carlo (100 runs) | `mc_service_levels.npy` | file exists |
| 6. Statistical tests | `statistical_tests.json` | file exists |

## Cost

- GPU: T4 16 GB at ~$0.59/hr on Modal
- Duration: ~3 hours (Steps 4a + 4b + 4c + 6 only when keepers are on the volume; ~7-8 h for a full cold-cache run)
- Total: ~$1.80 (rerun-only) / ~$5 (full cold cache)

## Advanced MAPPO run

The advanced research runner trains the domain-randomized MAPPO policy
and writes models/logs to the `supply-chain-runs` Modal volume. It also
uses `.spawn()` from the local entrypoint.

```bash
# cheap container/code smoke run
modal run --detach supply_chain_research/phase3_ai/modal_mappo_trainer.py --timesteps 1000

# main advanced run
modal run --detach supply_chain_research/phase3_ai/modal_mappo_trainer.py --timesteps 1000000
```

Monitor with:

```bash
modal app logs supply-chain-mappo-trainer
```

## Troubleshooting

**Job stopped unexpectedly?** Re-run `modal run --detach cloud_training/modal_train.py`. Each step skips when its output file already exists on the `sc-results-v3` volume.

**Import error in container?** All dependencies are pinned in the script's `image` block in lock-step with `supply_chain_research/requirements.txt`. If a new module is added to the codebase, add it to the `.pip_install(...)` list and bump the pin in both places.

**Need more time?** Default container timeout is 8 hours. Increase `timeout=10 * 3600` (or longer) in the `@app.function(...)` decorator if needed.

## Configuration snapshot

| Parameter | Value | Justification |
|-----------|-------|---------------|
| NSGA-II `pop_size` | 1000 | ≥ n_var for good coverage (Deb et al. 2002) |
| NSGA-II `n_gen` | 200 | HV plateau verified empirically |
| Seeds per algorithm | 50 | Friedman power at α=0.05 (Audit 3.1) |
| PPO total steps | 5 M (3 M + 2 M) | Literature: 3–5 M for convergence |
| PPO `hidden_size` | 512 | Capacity for the stress-mode inventory policy; legacy non-stress calls still support the 500-dim allocation action space |
| PPO LR schedule | linear `3e-4 → 0` (PPO-20, actor) and `2e-4 → 0` (PPO-100, actor); critic `multiplier × actor` per Andrychowicz et al. (2021); decay applied to BOTH actor and critic optimizers (Audit 2.2) | Andrychowicz et al. (2021); critic LR = `critic_lr_multiplier × actor LR` (Audit 2.2) |
| PPO rollout | 4096 steps | Stable gradients for high-dim actions |
| LSTM | 256 hidden × 3 layers | Capacity for 100-customer demand |
| DES replications | 100 | Tight CI on service-level (~±0.3 %) |

## Result manifest

After completion, `data/results/` contains:

```
data/results/
├── nsga2_best_front.npy          # Best Pareto front (N × 2)
├── nsga2_all_results.pkl         # All seeds + HV histories + joint ideal/nadir
├── nsga3_all_results.pkl         # NSGA-III (3-objective) results
├── moead_all_results.pkl         # MOEA/D results
├── lstm_predictions.npy          # LSTM test predictions
├── lstm_actuals.npy              # LSTM test actuals
├── best_lstm.pt                  # LSTM weights
├── ppo_small_final.pt            # PPO (20-customer) weights
├── ppo_full_final.pt             # PPO (100-customer) weights
├── ppo_small_rewards.npy         # PPO-20 episode rewards
├── ppo_full_rewards.npy          # PPO-100 episode rewards
├── ppo_baselines.json            # (s, S) and random baselines
├── mc_service_levels.npy         # 100 Monte-Carlo service-level samples
├── statistical_tests.json        # Friedman + Wilcoxon
└── training_summary.json         # Aggregated metrics
```

## Local fallback

For a smaller end-to-end smoke test on the laptop:

```bash
python cloud_training/local_training_runner.py --resume --ppo-steps 50000
```

The local runner uses the same public APIs as the Modal pipeline (NSGA-II → LSTM → PPO → sensitivity analysis), with linear LR decay applied to both the actor and critic optimizers (Audit 2.2 — they are decoupled).


## Ordered runbook by component and platform

The matrix below lists the exact `local_training_runner.py` invocation for each `(component, platform)` pair. All commands are resumable: re-running with the same `--resume <checkpoint>` continues at the last completed phase. See `README_CLOUD_SETUP.md` for the platform comparison.

### NSGA-II x 10 seeds (Kaggle and Colab) and x 50 seeds (Vast.ai / local)

```bash
# Kaggle (T4 x2, 9 h cap) — checkpoint on /kaggle/working
python cloud_training/local_training_runner.py \
    --component nsga2 --seeds 10 \
    --resume /kaggle/working/checkpoints/nsga2.pkl

# Colab Pro (A100 / V100, 24 h cap) — checkpoint on Drive
python cloud_training/local_training_runner.py \
    --component nsga2 --seeds 10 \
    --resume /content/drive/MyDrive/supply_chain_checkpoints/nsga2.pkl

# Vast.ai (rentable A100 80 GB) — wraps the same command in vastai_setup.sh
bash cloud_training/vastai_setup.sh   # drives --seeds 50 --resume ./checkpoints/nsga2.pkl

# Local CUDA workstation
python cloud_training/local_training_runner.py \
    --component nsga2 --seeds 10 \
    --resume ./checkpoints/nsga2.pkl
```

### LSTM demand forecaster

```bash
# Kaggle
python cloud_training/local_training_runner.py \
    --component lstm \
    --resume /kaggle/working/checkpoints/lstm.pt

# Colab Pro
python cloud_training/local_training_runner.py \
    --component lstm \
    --resume /content/drive/MyDrive/supply_chain_checkpoints/lstm.pt

# Vast.ai
python cloud_training/local_training_runner.py \
    --component lstm \
    --resume /workspace/supply-chain/checkpoints/lstm.pt

# Local CUDA workstation
python cloud_training/local_training_runner.py \
    --component lstm \
    --resume ./checkpoints/lstm.pt
```

### PPO 1M-step training

PPO is the most wall-clock-intensive component; Kaggle is not recommended because the 9 h cap is tight for 1M steps. Colab Pro (A100), Vast.ai (A100 80 GB), or a local 24+ GB GPU is the safe choice.

```bash
# Colab Pro
python cloud_training/local_training_runner.py \
    --component ppo --ppo-steps 1000000 \
    --resume /content/drive/MyDrive/supply_chain_checkpoints/ppo.pt

# Vast.ai
python cloud_training/local_training_runner.py \
    --component ppo --ppo-steps 1000000 \
    --resume /workspace/supply-chain/checkpoints/ppo.pt

# Local CUDA workstation
python cloud_training/local_training_runner.py \
    --component ppo --ppo-steps 1000000 \
    --resume ./checkpoints/ppo.pt
```

### JSON status log

Every invocation appends one JSON record per phase transition to
`data/results/training_status.jsonl` with the schema
`{ts, component, phase, state, ...}`. This is the canonical way to
monitor a long-running cloud run from outside the notebook (e.g. a
local `tail -f` against the Drive-mounted file).
