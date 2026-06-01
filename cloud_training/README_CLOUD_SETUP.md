<!--
README_CLOUD_SETUP.md — top-level platform-comparison readme.

Spec   : .kiro/specs/supply-chain-research-audit/tasks.md  (Task 5.7)
Bugfix : C1.7 (no documented cloud-training option),
         C1.23 (no cloud_training/ scaffold),
         C2.7 (cloud-training scaffold required),
         C2.23 (six required files runnable end-to-end),
         C3.16 (additive — must not change existing import paths).

Append-only audit deliverable. The companion runbook is
TRAINING_GUIDE.md and the canonical resumable A100 pipeline lives in
modal_train.py — both referenced from the table below.
-->

# Cloud training — platform comparison

This document is the entry point for running the expensive components of
the supply-chain research pipeline (NSGA-II x N seeds, Attention-LSTM
training, PPO 1M-step training) on cloud infrastructure. It compares the
four targets we provide scaffolding for and points at the two reference
documents that drive each runbook.

The canonical resumable A100 pipeline is `cloud_training/modal_train.py`.
The ordered runbook (per component, per platform, with `--resume`
examples) is `cloud_training/TRAINING_GUIDE.md`.

## At-a-glance comparison

| Platform                | GPU              | VRAM        | Max session | Indicative cost (USD) | Recommended invocation                                                                                          |
|-------------------------|------------------|-------------|-------------|-----------------------|-----------------------------------------------------------------------------------------------------------------|
| Kaggle Notebooks (free) | NVIDIA T4 x2     | 16 GB each  | 9 h         | 0.00                  | `python cloud_training/local_training_runner.py --component nsga2 --seeds 10 --resume /kaggle/working/checkpoints/nsga2.pkl` |
| Colab Pro               | NVIDIA A100 40GB or V100 16 GB (quota-dependent) | 40 GB / 16 GB | 24 h | ~10/month subscription | `python cloud_training/local_training_runner.py --component lstm --resume /content/drive/MyDrive/supply_chain_checkpoints/lstm.pt` |
| Vast.ai (rentable)      | NVIDIA A100 80GB | 80 GB       | unlimited   | 0.45 - 1.10 / hr      | `bash cloud_training/vastai_setup.sh` (drives `--component nsga2 --seeds 50 --resume ./checkpoints/nsga2.pkl`)  |
| Local CUDA workstation  | RTX 3090 / 4090 / A6000 (typical) | 24 - 48 GB | unlimited | hardware capex only  | `python cloud_training/local_training_runner.py --component ppo --resume ./checkpoints/ppo.pt`                  |

## Component-to-platform fit

| Component        | Budget                | Best fit             | Rationale                                                                                                  |
|------------------|-----------------------|----------------------|------------------------------------------------------------------------------------------------------------|
| NSGA-II x seeds  | 10 - 50 seeds         | Kaggle, Vast.ai      | Embarrassingly parallel; T4 x2 is enough at 10 seeds, A100 80 GB is required to reach the 50-seed budget.  |
| Attention-LSTM   | ~2 h on A100          | Colab Pro, Vast.ai   | Single-GPU training; benefits from A100 / V100 throughput more than from a second GPU.                     |
| PPO 1M-step      | ~3 - 5 h on A100      | Vast.ai, local CUDA  | Long wall-clock + frequent checkpoints; rentable A100 or local 24+ GB GPU is the safe choice.              |

## Files in this directory

| File                            | Purpose                                                                  |
|---------------------------------|--------------------------------------------------------------------------|
| `README_CLOUD_SETUP.md`         | This document — platform comparison and entry point.                     |
| `kaggle_setup.ipynb`            | Self-contained Kaggle (T4 x2) notebook that runs NSGA-II + LSTM.         |
| `colab_setup.ipynb`             | Self-contained Colab Pro notebook with Drive-mounted checkpoints.        |
| `vastai_setup.sh`               | Bash bootstrap script for a rented Vast.ai A100 instance.                |
| `local_training_runner.py`      | Local / cloud driver with rich progress, `--component`, and `--resume`.  |
| `TRAINING_GUIDE.md`             | Ordered runbook (NSGA-II x 10, LSTM, PPO 1M) with `--resume` examples.   |
| `modal_train.py`                | Canonical resumable A100 pipeline on Modal (do not edit while running).  |

## Reproducibility contract

Every cloud script in this directory drives the same `MasterConfig` and
respects the same random-seed schedule as the local pipeline; the only
difference between platforms is the checkpoint root and the wall-clock
budget. `--resume <path>` is honoured by all four runbooks so a
preempted spot instance (Vast.ai) or a hit on the 9 h Kaggle cap can be
restarted with the same command and pick up at the last completed
component. Numerical outputs are bit-equivalent to the local run for the
same seed because no parameter is overridden by the cloud scaffolding.

## What this scaffold deliberately does not do

* It does not modify any module under `supply_chain_research/`. The
  cloud scripts are pure drivers (`bugfix.md` clause C3.16).
* It does not introduce any new dependency: every package the cloud
  scripts use is already pinned in
  `supply_chain_research/requirements.txt`.
* It does not auto-launch training; every notebook / script is opt-in
  and prints the exact command before executing.
