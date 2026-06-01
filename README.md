# Multi-Objective Resilient Supply Chain Optimization

A research framework for simultaneous cost and carbon emission minimization in Indian logistics networks, combining evolutionary multi-objective optimization (NSGA-II/III, MOEA/D), discrete event simulation, deep reinforcement learning (PPO), and neural demand forecasting (Attention-LSTM).

---

## What This Does

Finds the Pareto-optimal set of fleet allocation plans that trade off logistics **cost** against **CO₂ emissions** on real Indian road networks, while maintaining supply chain **resilience** under stochastic disruptions.

The system produces:
- Pareto-optimal solutions (10-15 per seed, 30 seeds, statistically validated)
- Resilience metrics under supply/demand shocks (TTS, TTR) via Monte Carlo DES
- Adaptive inventory control via PPO reinforcement learning (5M steps, 500-dim action space)
- 7-day demand forecasts via Attention-LSTM (256 hidden, 3 layers)
- Green premium curve showing marginal cost of decarbonization
- Publication-ready figures and statistical tests (Friedman, Wilcoxon)

---

## Current Status (May 2026)

| Component | Status | Details |
|-----------|--------|---------|
| NSGA-II optimization | Complete | 50 seeds × pop=1000 × gen=200, normalised HV 0.7130 ± 0.1432 |
| NSGA-III (3-objective) | Complete | 50 seeds, normalised HV 0.6588 |
| MOEA/D comparison | Complete | 50 seeds, normalised HV 0.5948 ± 0.3281 |
| Friedman + Wilcoxon tests | Complete | χ² = 6.84, p = 0.033 ; W = 399, p = 0.021 |
| LSTM forecasting | Complete | 256h × 3L, MAPE 23.5 %, RMSE 56.5 kg |
| PPO controller (FIX-022 stress mode) | In progress (T4 Modal) | Periodic-review lost-sales formulation, post-FIX-022 rerun in flight |
| (R, s, S) baseline | Queued (Step 4c) | Periodic-review (R = 7 days, lead = 3 days) |
| DES Monte Carlo | Complete | 100 reps, service level 95.6 % ± 0.3 % |
| Web dashboard | Available | http://localhost:5173 |
| Test suite | Passing | 483 passed, 5 skipped |

---

## Key Differentiators (vs Published Literature)

| Feature | This Work | Soysal 2018 | Demir 2014 | Zhang 2022 | Wang 2023 |
|---------|-----------|-------------|------------|------------|-----------|
| Real road distances (ORS) | ✓ | ✗ | ✗ | ✗ | ✗ |
| India-specific calibration | ✓ | ✗ | ✗ | ✗ | ✗ |
| Multi-algorithm comparison | ✓ (3 algos) | ✗ | ✗ | ✗ | ✗ |
| DES resilience simulation | ✓ | ✗ | ✗ | ✗ | ✗ |
| RL-based inventory control | ✓ | ✗ | ✗ | ✗ | ✓ |
| Demand forecasting (LSTM) | ✓ | ✗ | ✗ | ✗ | ✗ |
| Robust optimization | ✓ | ✗ | ✗ | ✗ | ✗ |
| Carbon budget constraint | ✓ | ✓ | ✗ | ✗ | ✗ |
| Statistical validation (30 seeds) | ✓ | ✗ | ✗ | ✗ | ✗ |

---

## Project Structure

```
├── supply_chain_research/          # Core algorithms
│   ├── config.py                   # All parameters (Pydantic, 120+ fields)
│   ├── phase1_foundation/          # Multi-objective optimization
│   ├── phase2_resilience/          # DES + Monte Carlo
│   ├── phase3_ai/                  # PPO, SAC, LSTM, TFT, Gym env
│   └── phase4_synthesis/           # Statistics, figures, tables
├── data/
│   ├── external/                   # Raw datasets (Dalal, Delhivery, DataCo)
│   ├── processed/                  # Calibrated parameters
│   ├── cache/                      # ORS distance matrices
│   └── results/                    # Training outputs
├── webapp/
│   ├── backend/                    # FastAPI (real data endpoints)
│   └── frontend/                   # React + Recharts dashboard
├── cloud_training/                 # Modal GPU training scripts
├── tests/                          # 33 pytest modules
├── scripts/                        # Data processing utilities
├── docs/                           # Documentation
└── audit_workspace/                # Regression baselines
```

---

## Quick Start

```bash
# Setup
python3 -m venv .venv && source .venv/bin/activate
pip install -r supply_chain_research/requirements.txt

# Run tests
pytest tests/ -q  # 483 passed, 5 skipped, ~315 seconds on Python 3.14

# Start dashboard
cd webapp/backend && uvicorn main:app --reload --port 8000 &
cd webapp/frontend && npm run dev &
# Open http://localhost:5173

# Run training on Modal (T4 GPU, detached, resumable)
modal run --detach cloud_training/modal_train.py

# Download results when done
modal volume get sc-results-v3 / ./data/results/
```

---

## Data Sources

| Dataset | Records | Use |
|---------|---------|-----|
| Dalal (2022) INFORMS | 101 demand points | Network topology, GPS coordinates |
| Delhivery (Kaggle) | 144,867 shipments | OSRM validation, distance correction |
| DataCo Supply Chain | 180,519 orders | Demand calibration (LogNormal fit) |
| NITI Aayog (2021) | Policy report | Truck speed 35 km/h, empty running 35% |
| VAHAN (MoRTH) | Fleet registry | HCV:LCV ratio 70:30 |
| OpenRouteService | API | Real driving distances on Indian roads |

Demand parameters calibrated from DataCo: LogNormal(μ=6.44, σ=0.97) for weekly cluster demand.

---

## Training Pipeline (v3)

Runs on NVIDIA A100 80GB via Modal ($3.40/hr). Each step is resumable — if it crashes, re-run and it picks up from the last completed step.

| Step | What | Duration (est.) |
|------|------|-----------------|
| 1 | Network data generation | <1 min |
| 2 | NSGA-II (30 seeds, pop=1000, gen=200) | ~5.5 hours |
| 2b | NSGA-III (30 seeds, 3-objective) | ~2 hours |
| 2c | MOEA/D (30 seeds) | ~1.5 hours |
| 3 | LSTM (256h, 3L, patience=15) | ~5 min |
| 4a | PPO-20 (3M steps, 100-dim action) | ~45 min |
| 4b | PPO-100 (2M steps, 500-dim action) | ~1 hour |
| 4c | Baselines ((s,S) + random) | ~5 min |
| 5 | DES Monte Carlo (100 runs) | ~2 min |
| 6 | Statistical tests (Friedman + Wilcoxon) | <1 min |

---

## Configuration

All parameters centralized in `supply_chain_research/config.py`:

```python
from supply_chain_research.config import MasterConfig
cfg = MasterConfig()

# Key sub-configs:
cfg.nsga       # NSGA-II: pop=1000, gen=150, crossover_eta=10
cfg.nsga3      # NSGA-III: pop=92, 91 reference points
cfg.moead      # MOEA/D: Tchebycheff, 20 neighbors
cfg.simulation # DES: 365 days, 100 MC runs, truck_speed=35 km/h
cfg.lstm       # LSTM: 256 hidden, 3 layers, 7-day horizon
cfg.ppo        # PPO: 512 hidden, clip=0.2, LR decay 3e-4→0
cfg.robust     # Robust: mean + λ·std over 10 scenarios
cfg.carbon_budget  # Carbon: none / 20pct / 40pct reduction
```

---

## Citation

```bibtex
@article{aggarwal2026supply,
  title={Multi-Objective Resilient Supply Chain Optimization with Deep
         Reinforcement Learning on Indian Road Networks},
  author={Aggarwal, Nalin},
  year={2026},
  note={Manuscript in preparation}
}
```
