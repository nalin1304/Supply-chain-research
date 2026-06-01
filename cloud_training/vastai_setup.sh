#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# vastai_setup.sh — bootstrap a Vast.ai rented A100 instance to run the
#                   resumable NSGA-II x N-seed pipeline.
#
# Spec : .kiro/specs/supply-chain-research-audit/tasks.md  (Task 5.7)
# Bugfix clauses : C1.7  (no cloud-training option),
#                  C1.23 (no cloud_training/ scaffold),
#                  C2.7  (cloud-training scaffold required),
#                  C2.23 (six required files runnable end-to-end),
#                  C3.16 (additive — must not change existing import paths).
#
# Layer of guarantees (Vast.ai documentation, retrieved 2025):
#   * Vast.ai images ship Ubuntu 22.04 LTS with CUDA 12.1 + Python 3.10.
#   * Rentable A100 80GB at ~ USD 0.45-1.10 / hr (interruptible spot).
#   * Storage volume mounted at /workspace by default; /root is ephemeral.
# ---------------------------------------------------------------------------

# [POSIX 2024 §2.5] strict mode: exit on error, undefined var, pipefail.
set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration — override via environment variables.
# ---------------------------------------------------------------------------

# Repository to clone.  The default points at the public mirror; override by
# exporting REPO_URL=... before invoking the script when running against a
# private fork.
REPO_URL="${REPO_URL:-https://github.com/example/Supply-chain.git}"

# Branch / commit to check out (default: main).
REPO_REF="${REPO_REF:-main}"

# Working directory on the rented box.
WORKDIR="${WORKDIR:-/workspace/supply-chain}"

# NSGA-II seed budget (bugfix.md C2.23 §H — 50 seeds is the default budget
# for the rentable-A100 tier).
SEEDS="${SEEDS:-50}"

# Checkpoint location used by --resume (bugfix.md C2.23 §H).
CHECKPOINT="${CHECKPOINT:-./checkpoints/nsga2.pkl}"

# ---------------------------------------------------------------------------
# 1. System dependencies (git + build toolchain + Python tooling).
# ---------------------------------------------------------------------------

echo "[vastai-setup] Installing system dependencies..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y --no-install-recommends \
    git \
    build-essential \
    python3 \
    python3-pip \
    python3-venv \
    ca-certificates

# ---------------------------------------------------------------------------
# 2. Clone the repository (idempotent).
# ---------------------------------------------------------------------------

echo "[vastai-setup] Cloning ${REPO_URL} (ref=${REPO_REF}) into ${WORKDIR}..."
mkdir -p "$(dirname "${WORKDIR}")"
if [ ! -d "${WORKDIR}/.git" ]; then
    git clone --depth 1 --branch "${REPO_REF}" "${REPO_URL}" "${WORKDIR}"
else
    echo "[vastai-setup] Repository already present; pulling latest..."
    git -C "${WORKDIR}" fetch --depth 1 origin "${REPO_REF}"
    git -C "${WORKDIR}" checkout "${REPO_REF}"
    git -C "${WORKDIR}" pull --ff-only origin "${REPO_REF}"
fi

# ---------------------------------------------------------------------------
# 3. Python dependencies (pinned in supply_chain_research/requirements.txt).
# ---------------------------------------------------------------------------

cd "${WORKDIR}"

echo "[vastai-setup] Upgrading pip and installing pinned requirements..."
python3 -m pip install --upgrade pip
python3 -m pip install -r supply_chain_research/requirements.txt

# ---------------------------------------------------------------------------
# 4. Launch the resumable NSGA-II x ${SEEDS} run via the local runner.
#    --resume <CHECKPOINT> lets the same command resume after a spot
#    interruption (Vast.ai may reclaim the GPU at any time).
# ---------------------------------------------------------------------------

mkdir -p "$(dirname "${CHECKPOINT}")"

echo "[vastai-setup] Starting NSGA-II run: seeds=${SEEDS}, checkpoint=${CHECKPOINT}"
python3 cloud_training/local_training_runner.py \
    --component nsga2 \
    --seeds "${SEEDS}" \
    --resume "${CHECKPOINT}"

echo "[vastai-setup] Done. Pareto front written under data/results/."
