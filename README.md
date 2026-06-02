# Multi-Objective Resilient Supply Chain Optimization

A comprehensive research framework for simultaneous cost and carbon emission minimization in Indian logistics networks. This project combines evolutionary multi-objective optimization (NSGA-II/III, MOEA/D), discrete event simulation, and advanced deep reinforcement learning paradigms to create highly resilient, green supply chains under stochastic disruptions.

---

## 🚀 Overview

Finds the Pareto-optimal set of fleet allocation plans that trade off logistics **cost** against **CO₂ emissions** on real Indian road networks, while maintaining supply chain **resilience** under stochastic supply and demand shocks.

The framework produces publication-ready analytics, bridging traditional operations research with cutting-edge artificial intelligence, structured across **14 distinct research phases**.

## 🧠 Advanced Capabilities (Phases 1-14)

### Core Optimization & Simulation (Phases 1-4)
- **Multi-Objective Evolutionary Algorithms:** NSGA-II, NSGA-III, and MOEA/D solvers computing the exact cost-carbon trade-off and Green Premium Curve.
- **Monte Carlo DES:** Discrete Event Simulation evaluating Time-To-Survive (TTS) and Time-To-Recover (TTR) under massive supply/demand shocks.
- **Base AI Forecasting:** Attention-LSTM and Temporal Fusion Transformers (TFT) for 7-day multi-horizon demand forecasting.
- **Base AI Control:** PPO and SAC reinforcement learning for continuous dynamic inventory replenishment (Periodic-review lost-sales formulation).
- **Statistical Synthesis:** Automated non-parametric significance testing (Friedman + Wilcoxon) and publication figure generation.

### Advanced AI & Robustness (Phases 7-14)
- **Phase 7: MAPPO & ST-GNNs:** Multi-Agent PPO for decentralized warehouse control, alongside Spatio-Temporal Graph Neural Networks for correlated demand forecasting across geographic clusters.
- **Phase 8: Sim-to-Real Transfer:** Domain randomization and evaluation against exogenous real-world demand data (e.g., M5 datasets) to prove policy generalization beyond the synthetic simulator.
- **Phase 9: Explainable AI (XAI):** Interpretability layer using SHAP values and attention-weight probing to explain black-box replenishment decisions to supply chain practitioners.
- **Phase 10: Risk-Averse RL (CVaR):** Conditional Value-at-Risk objectives injected into MAPPO (CVaR-MAPPO) to optimize for the worst 5% of disruption scenarios.
- **Phase 11: Adversarial Robustness RL:** Minimax attacker-defender training paradigm where a secondary RL agent learns to maliciously perturb demands to harden the primary defender policy.
- **Phase 12: Offline RL (Decision Transformers):** Pre-training inventory policies strictly from static, high-dimensional expert demonstration datasets before online fine-tuning, solving the sample-inefficiency of standard RL.
- **Phase 13: Dynamic Spatio-Temporal Routing:** Integration of hourly urban traffic matrices (New Delhi probe data) to penalize rush-hour routing and ensure realistic driving delays.
- **Phase 14: Multi-Objective RL (MORL):** Dynamic scalarization allowing the RL agent to shift its preference between cost and carbon emissions dynamically during deployment, without needing to be retrained.

---

## 📊 Current Status (June 2026)

All 14 phases are fully implemented, tested, and validated.
- **Models:** Cloud training for all advanced RL variants (CVaR-MAPPO, Adversarial, Decision Transformers) successfully completed on Modal A100 GPUs. Pre-trained weights are available in `models/`.
- **Metrics:** Evolutionary solvers consistently extract valid Pareto fronts (Hypervolume ~0.71).
- **Test Suite:** The complete integration test suite passes fully (491 tests, 0 failures, 100% stable).
- **Data:** Grounded in peer-reviewed Indian datasets (Dalal 2022) with real OSMR distances, Delhivery transit times, DataCo demand calibration, and SVRPBench routing scenarios. 

---

## 📁 Project Structure

```
├── supply_chain_research/          # Core algorithms and simulation framework
│   ├── phase1_foundation/          # Multi-objective optimization (NSGA/MOEAD)
│   ├── phase2_resilience/          # Discrete Event Simulation & Shocks
│   ├── phase3_ai/                  # All RL Agents, Offline DTs, MAPPO, ST-GNN
│   └── phase4_synthesis/           # Statistics, XAI plotting, figure generation
├── data/
│   ├── external/                   # Raw empirical datasets
│   ├── processed/                  # Calibrated demand/cost parameters
│   └── results/                    # Cloud training artifacts & evaluation JSONs
├── models/                         # Trained neural network weights (.pt)
├── webapp/                         # React + FastAPI dashboard for scenario testing
├── cloud_training/                 # Modal cloud execution scripts
├── tests/                          # Comprehensive pytest suite (491 tests)
└── docs/                           # Manuscripts, Reports, and Roadmaps
```

---

## ⚡ Quick Start

### 1. Setup Environment
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r supply_chain_research/requirements.txt
```

### 2. Verify Codebase
```bash
pytest tests/ -v  # Expect 491 passing tests
```

### 3. Generate Analytics and Figures
Run the automated synthesis pipeline to regenerate all publication figures from the latest model checkpoints:
```bash
cd supply_chain_research/phase4_synthesis
python generate_all_figures.py
```

### 4. Cloud Training (Modal)
All heavy RL algorithms are pre-configured to run asynchronously on Modal cloud GPUs.
```bash
modal run --detach supply_chain_research/phase3_ai/modal_adversarial_trainer.py
modal run --detach supply_chain_research/phase3_ai/modal_offline_trainer.py
```

### 5. Launch Dashboard
```bash
# Terminal 1
cd webapp/backend && uvicorn main:app --reload --port 8000
# Terminal 2
cd webapp/frontend && npm run dev
```

---

## 📚 Data Sources & Realism
Every parameter is grounded in measured data:
- **Dalal (2022) / SVRPBench:** Spatial distribution, customer hubs, and distance mapping.
- **NITI Aayog (2021):** Truck utilization, empty-running percentages, and macro logistics cost.
- **OpenRouteService:** Real Indian road distances replacing Euclidean assumptions.
- **Delhivery / DataCo:** Demand distributions and travel time calibration.

For a full breakdown, see `docs/DATA_SOURCES.md`.

---

## 📝 Citation

If you use this framework or the dataset compilation in your research, please cite:

```bibtex
@article{aggarwal2026supply,
  title={An Integrated Multi-Objective Optimization and Deep Reinforcement Learning Framework for Green, Resilient Supply Chain Management — Evidence from Indian Logistics Networks},
  author={Aggarwal, Nalin},
  year={2026},
  note={Manuscript in preparation}
}
```
