# Evaluating multi-stage supply-chain decisions

Research from my internship at IIM Mumbai (supervisor: Dr. Nikhil Ghag). Manuscript submitted to the Asia-Pacific Journal of Operational Research.

One protocol grades forecasting, multi-objective optimization and disruption simulation to the same standard, on a public Indian freight network (Dalal, 2022: 3 warehouses, 101 customers, 101,072 kg of demand).

Two results:
- An attention-LSTM looked cheaper than a naive forecast under its own safety-stock sizing (28.86 vs 34.10 per decision). Under one shared sizing rule it cost 136.7 versus 33.6.
- Across ten solvers and 50 matched seeds (Friedman χ² = 425.95), SPEA2 and NSGA-II lead, and they still differ after Holm correction (p = 0.0087).

Write-up: https://nalinaggarwal.me/work/supply-chain-evaluation/

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
  note={Manuscript submitted to the Asia-Pacific Journal of Operational Research}
}
```
