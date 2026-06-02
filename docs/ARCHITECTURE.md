# Project Architecture — Comprehensive Codebase Tour

This document is the ground truth for what every file and folder in
the repository does, in plain language and in technical terms. Use it
when you need to navigate the codebase, hand it off to a collaborator,
or decide whether to delete something.

Sections:

1. **Project identity** — what this project is, in one breath
2. **Pipeline architecture** — how the four phases fit together
3. **Top-level layout** — every folder at the repo root
4. **`supply_chain_research/`** — the algorithms package, file by file
5. **`webapp/`** — the FastAPI + React dashboard
6. **`cloud_training/`** — the training entry-points and platform setups
7. **`scripts/`** — the data-ingestion / one-off utilities
8. **`tests/`** — the test suite, file by file
9. **`docs/`** — the written documentation
10. **`data/`** — datasets and training outputs, folder by folder
11. **`outputs/`** — generated figures and LaTeX tables
12. **`audit_workspace/`** — the regression-baseline harness
13. **`.kiro/`** — the bugfix-spec ground truth
14. **Auto-generated / cache directories** (`.hypothesis`, `.pytest_cache`, etc.)
15. **Headline configuration values**
16. **Critical algorithms** — quick verification cheat-sheet
17. **Redundant / dead / candidate-for-deletion files**

---

## 1. Project Identity

- **Name**: Multi-Objective Resilient Supply Chain Optimization
- **Author**: Nalin Aggarwal
- **Target**: Tier-1 operations-research / management-science journal
- **Language**: Python 3.11–3.14 (developed on 3.14.3)
- **Frontend stack**: React 18 + Vite + Recharts + Tailwind
- **Cloud-training platform**: Modal (T4 GPU, ~$0.59/h)
- **Plain-English problem statement**: Given a network of warehouses
  and customers across India, find the set of fleet-allocation plans
  that simultaneously minimise rupee cost AND CO₂ emissions, validate
  those plans hold up under real disruptions (demand surges, supply
  disruptions, route blockages), train an AI controller that decides
  daily reorder quantities, and produce statistical evidence the
  results are real.
- **Technical problem statement**: Bi-objective evolutionary
  optimisation of a flat decision tensor `x[w, c, v] ∈ ℝ_≥0` (kg
  shipped from warehouse w to customer c via vehicle type v) under
  capacity and demand constraints, coupled with a SimPy DES for
  resilience validation, an LSTM forecaster for 7-day demand
  prediction, and a PPO agent on a Gymnasium env that learns the
  inventory-control policy.
- **Methodological approach**: NSGA-II/III + MOEA/D (Pareto
  optimisation) + SimPy DES + PPO + LSTM, all unified by a
  Friedman / Wilcoxon / Holm-Bonferroni statistical-validation
  protocol with empirical Friedman power.


---

## 2. Pipeline Architecture

```
┌─────────────────────────────────────────────────────────────┐
│ Phase 1: Foundation  (strategic optimisation)                │
│  - NSGA-II  (cost vs carbon, pop=500-1000, gen=200-400)      │
│  - NSGA-III (cost vs carbon vs max-delivery-time, 91 ref dirs)│
│  - MOEA/D   (Tchebycheff decomposition, 100 weights)         │
│  - Clarke-Wright savings (parallel-merge baseline)           │
│  - OR-Tools warm-start                                        │
└──────────────────────────┬──────────────────────────────────┘
                           │ Pareto front (10-21 solutions/seed)
┌──────────────────────────▼──────────────────────────────────┐
│ Phase 2: Resilience  (stochastic validation)                 │
│  - SimPy DES (365 days, eps-guarded Container ops)           │
│  - Monte Carlo (100 reps, joblib parallel)                   │
│  - Conover order-statistic CI on 95th-percentile TTR         │
└──────────────────────────┬──────────────────────────────────┘
                           │ TTS, TTR, normalised TTR
┌──────────────────────────▼──────────────────────────────────┐
│ Phase 3: AI / ML     (forecasting + control)                  │
│  - Attention-LSTM (256h × 3L, attention head)                │
│  - Lightweight TFT (Lim 2021, GRN + multi-head attention)    │
│  - PPO with Beta(α, β) actor on [0, 1]                        │
│  - SAC (twin-Q, polyak, alpha auto-tune)                      │
│  - FIX-022 stress-mode env: periodic-review lost-sales,       │
│    5-dim per-warehouse action, INR cost reward                 │
│    [Gijsbrechts 2022, Vanvuchelen 2024, Yang-Wang-Yu 2024]    │
│  - (R, s, S) periodic-review baseline + random policy         │
└──────────────────────────┬──────────────────────────────────┘
                           │ Trained models + baseline rewards
┌──────────────────────────▼──────────────────────────────────┐
│ Phase 4: Synthesis    (statistics + figures + insights)      │
│  - Friedman omnibus + paired Wilcoxon + Holm-Bonferroni      │
│  - Empirical Friedman power simulation (10 000 iterations)   │
│  - 2^(4-1) resolution-IV factorial ablation                   │
│  - Sobol global sensitivity (SALib, Saltelli sampling)       │
│  - 7 publication figures + 6 LaTeX tables                     │
│  - 4 quantitative managerial thresholds                       │
└─────────────────────────────────────────────────────────────┘
```

The phases run in order on Modal (`cloud_training/modal_train.py`)
with skip-if-exists gating per artifact, so re-running the pipeline
after a crash or after a partial fix recomputes only the affected
steps. Phases also expose Python APIs that the FastAPI dashboard
calls on demand for what-if analysis.


---

## 3. Top-Level Layout

```
Supply-chain-main/
├── README.md                # one-page elevator pitch + quick-start
├── pytest.ini               # test runner config (markers, paths)
├── .gitignore               # ignored paths
├── .coverage                # coverage.py state (auto-generated)
├── supply_chain_research/   # the algorithms package (Phases 1-4)
├── webapp/                  # FastAPI backend + React frontend
├── cloud_training/          # Modal entry-point + alt-platform notes
├── scripts/                 # data ingestion / one-off utilities
├── tests/                   # 33 pytest modules (pytest + hypothesis)
├── docs/                    # written documentation (this file)
├── data/                    # datasets and training outputs
├── outputs/                 # generated figures and LaTeX tables
├── audit_workspace/         # regression-baseline harness
├── .kiro/                   # bugfix-spec ground truth
├── .hypothesis/             # property-based-testing cache (auto)
├── .pytest_cache/           # pytest cache (auto)
└── (no other files)
```

| Top-level item | Plain English | Technical |
|---|---|---|
| `README.md` | The "what is this and how do I run it" page | Markdown overview, quick-start, current status, structure, tech stack |
| `pytest.ini` | Tells pytest where tests live and which markers exist | Sets `testpaths = tests`, registers `slow`, `pbt`, etc. markers, configures hypothesis profiles |
| `.gitignore` | Files git should pretend don't exist | Standard Python + Node + macOS ignores |
| `.coverage` | Cached test-coverage state | Auto-generated by `coverage.py`; never edit |



---

## 4. `supply_chain_research/` — The Algorithms Package

This is the heart of the project. Everything else (webapp,
training script, scripts/, tests/) consumes the public API exposed
here.

### 4.0 Package-level files

| File | Plain English | Technical |
|---|---|---|
| `__init__.py` | Marks this folder as a Python package | Empty / imports nothing — keeps the import system simple |
| `config.py` | The single source of truth for every parameter in the pipeline | One big Pydantic v2 module with `MasterConfig` and a dozen sub-configs (`NSGAConfig`, `PPOConfig`, `GymEnvConfig`, …). Every parameter has an inline `# [SOURCE-YEAR §section]` citation. ~1200 lines, ~120 tunable fields. **DO NOT inline numeric constants anywhere else** |
| `requirements.txt` | The exact pinned dependency versions for the algorithm package | Lock-step with `cloud_training/modal_train.py`'s `image.pip_install(...)` block |

### 4.1 `phase1_foundation/` — Strategic optimisation

Multi-objective evolutionary algorithms over the bi- and three-objective
fleet-allocation problem.

| File | Plain English | Technical |
|---|---|---|
| `__init__.py` | Re-exports the public solver entry-points | `run_nsga2`, `run_nsga3`, `run_moead`, `run_clarke_wright`, etc. |
| `data_engineering.py` | Generates the synthetic Indian network (warehouses, customers, demand) | `generate_customer_locations`, `get_warehouse_locations`, `generate_demand` (LogNormal μ=6.44, σ=0.97 from DataCo fit), `_haversine_matrix` for great-circle distances. Demand-shock multiplier and weekly periodicity are configurable |
| `emission_model.py` | Computes CO₂ emissions per route segment using the MEET model | `EmissionCalculator.emission_rate(load, vehicle)` → `k + L · load` (Hickman 1999 §3 Tab. 3.2/3.3); cross-verified against COPERT 5, HBEFA 4.2, IPCC AR6. HCV `k = 2.61 kg/km`, LCV `k = 0.89 kg/km` |
| `nsga2_solver.py` | The main bi-objective optimiser (cost vs carbon) | `SupplyChainProblem` (pymoo problem) + `MarginalTradeoffRepair` (per-individual α scalarisation, the diversity-preserving repair operator that's our core contribution) + `run_nsga2(...)` with optional OR-Tools warm-start (FIX-011). Produces 10-21 Pareto-optimal solutions per seed |
| `nsga3_solver.py` | Three-objective extension (adds max-delivery-time) | Das-Dennis reference directions (91 dirs at p=12), pop_size=92, `DemandRepair3Obj` proportional repair. Higher hypervolume than NSGA-II on this instance because the third objective discriminates more solutions |
| `moead_solver.py` | Decomposition-based comparator (Tchebycheff) | Wraps pymoo's `MOEAD` with 100 reference directions and a constraint-stripped problem subclass (MOEAD rejects problems with `n_ieq_constr > 0`). The repair operator handles feasibility |
| `pareto_analysis.py` | Hypervolume + non-domination utilities | `compute_hypervolume(F, ideal_point, nadir_point)` with margin guard against degenerate fronts; cross-algorithm joint-normalisation (Audit 3.3) |
| `clarke_wright.py` | Classic savings-based VRP heuristic for benchmark comparison | Parallel-merge canonical Clarke-Wright (1964); used as a deterministic baseline against the NSGA-II Pareto front |
| `baseline_solver.py` | OR-Tools and Clarke-Wright wrapper for the NSGA-II warm-start path | Returns route lists with `(warehouse, customers, load_kg, distance_km)` so the encoding bridge in `nsga2_solver.py` can lift them into pymoo decision tensors |
| `carbon_budget_solver.py` | ε-constraint variant: minimise cost subject to a carbon cap | Used to draw the green-premium curve (Bektaş & Laporte 2011 §6) |
| `multi_product_solver.py` | Extension to multiple SKU categories (Electronics, Apparel, Grocery, Books per Dalal 2022) | Density-weighted capacity constraints, per-product emission profiles |
| `robust_solver.py` | Robust optimisation under demand uncertainty | LogNormal demand + `mean + λ·std` formulation (Ben-Tal & Nemirovski 2002), evaluated across 10 scenarios |
| `formulation_latex.py` | Renders the optimisation problem as LaTeX for the manuscript | Pure utility — generates `\begin{align*}...\end{align*}` blocks directly from `SupplyChainProblem` for paper inclusion |



### 4.2 `phase2_resilience/` — Stochastic disruption validation

Discrete-event simulation that "stress-tests" a chosen plan against
shocks before it goes to operational deployment.

| File | Plain English | Technical |
|---|---|---|
| `__init__.py` | Re-exports the DES entry-point + helpers | `DESEnvironment`, `MonteCarloRunner`, `ResilienceMetrics`, shock-model classes |
| `des_environment.py` | The SimPy-based simulation: warehouses replenish, customers order, shocks fire | `DESEnvironment.run()` — uses `simpy.Container` for inventory with eps-guarded operations to avoid the SimPy zero-token deadlock; 365-day horizon by default |
| `monte_carlo_runner.py` | Runs many DES replications in parallel and aggregates | `joblib.Parallel` over `n_replications` (default 100), seed-stratified to allow Conover order-statistic CI on the 95th-percentile TTR |
| `resilience_metrics.py` | Computes the resilience metrics (TTS, TTR, normalised TTR) | Per Hosseini et al. (2019, TR-E) — Time-to-Survive, Time-to-Recover, normalised TTR with confidence intervals |
| `shock_models.py` | The three disruption classes used in the resilience ensemble | `DemandSurgeShock`, `SupplyDisruptionShock`, `RouteBlockageShock`. Each has `(start_day, duration_days, intensity)` parameters drawn from configurable distributions (Sheffi & Rice 2005 framework) |

### 4.3 `phase3_ai/` — Forecasting and reinforcement-learning control

The AI layer: 7-day demand forecasts + a learned inventory-control
policy.

| File | Plain English | Technical |
|---|---|---|
| `__init__.py` | Re-exports the public AI classes lazily | Lazy `__getattr__` so importing the package doesn't drag in PyTorch unless needed (matters for tests that don't touch ML) |
| `data_generator.py` | Generates the 3-year × 100-customer synthetic demand series for the LSTM | `DemandDataGenerator(n_customers, n_years, seed).generate()` — produces Diwali spike + weekly periodicity + Poisson noise; `create_sequences(...)` produces (X, y) supervised pairs; `temporal_split(...)` does 70/15/15 chronological split |
| `attention_lstm.py` | The in-house Attention-LSTM model class | `AttentionLSTMModel` — 2-layer LSTM (configurable hidden=256) + additive Bahdanau-style attention head over the temporal axis |
| `tft_forecaster.py` | Lightweight Temporal Fusion Transformer (Lim et al. 2021 §4.1+§4.4) — selectable alternative | `LightweightTFT` — drops the variable-selection / static-covariate stack (which is redundant for our single-stream demand series) and keeps the GRN block + interpretable multi-head attention. Activated by `LSTMConfig.model_type = "tft"` |
| `lstm_forecaster.py` | The training-loop wrapper that owns either model | `LSTMForecaster` — common `.train(X, y, X_val, y_val, patience)` and `.predict(X_test)` API; dispatches to AttentionLSTM (default) or LightweightTFT based on `LSTMConfig.model_type`. Saves to `best_lstm.pt` |
| `gym_environment.py` | The Gymnasium env PPO is trained against | `SupplyChainEnv` — Box action ∈ `[0, 1]^(C × W)` (legacy) or ∈ `[0, 1]^W` (FIX-022 stress mode). Observation = warehouse inventory + 7-day forecast + shock flags + time. Two reward modes: legacy PBRS service-quality vs FIX-022 negative-INR-cost |
| `ppo_agent.py` | The PPO-Clip implementation with Beta-distribution actor | `ActorNetwork` (Beta(α, β) parameterised by softplus + 1.0 to guarantee unimodal), `CriticNetwork` (state-value LayerNorm + Tanh), `RolloutBuffer`, `PPOAgent.update(...)` with decoupled actor/critic LR (Audit 2.2) and the GAE truncation-bootstrap fix (FIX-021) |
| `sac_agent.py` | Soft Actor-Critic baseline (Haarnoja 2018a/b) | Twin clipped-double-Q, polyak target update τ=0.005, automatic α tuning with `target_entropy = -dim(A)`. Off-policy alternative to PPO |
| `ss_policy.py` | Periodic-review (R, s, S) inventory baseline | `SSPolicy` with both a legacy continuous-time mode (`stress_mode=False`) and a periodic-review mode (`stress_mode=True`, FIX-022) that orders up-to-S only every R days. `evaluate_ss_policy(env, ...)` runs n_episodes evaluations |
| `drl_trainer.py` | High-level DRL training loop helper | Owns the env↔agent loop, episode-reward bookkeeping, checkpoint saving. The Modal training script (`cloud_training/modal_train.py`) inlines this loop for finer step-by-step control, but `drl_trainer.py` is the canonical reference implementation |



### 4.4 `phase4_synthesis/` — Statistics, figures, managerial insights

The "what does it all mean" layer: takes the trained models and the
DES output and produces statistical evidence, publication figures,
and managerial recommendations.

| File | Plain English | Technical |
|---|---|---|
| `__init__.py` | Re-exports public functions | The phase 4 module is mostly script-style; imports flow through here |
| `statistical_tests.py` | Runs Friedman + paired Wilcoxon + Holm-Bonferroni + Friedman empirical-power simulation | `friedman_test`, `pairwise_wilcoxon_holm`, `friedman_power_simulation(n_iter=10000)`. Produces `data/results/statistical_tests.json` |
| `sensitivity_analysis.py` | Sobol global sensitivity over four parameter axes | SALib Saltelli sampling, base size N=1024 → 10 240 NSGA-II evaluations per pass. Real (non-surrogate) Sobol — slow but defensible. Outputs first-order S1 and total-order ST indices |
| `ablation_study.py` | 2^(4-1) resolution-IV factorial ablation | Tests whether each of the four pipeline components (NSGA-II, MOEA/D, NSGA-III, PPO) contributes independently or via interaction. The `IV` resolution is what makes interactions identifiable |
| `complexity_analysis.py` | Empirical big-O benchmarks for each algorithm | `dump_complexity_report(fast_mode)` → `audit_workspace/COMPLEXITY_REPORT.json` and `docs/COMPLEXITY_ANALYSIS.md`. Uses `time.perf_counter()` with min/mean over reps |
| `compute_managerial_thresholds.py` | Derives the four quantitative thresholds for the Managerial Insights doc | Mean utilisation, p95 disruption recovery, green-premium knee, fleet-mix optimum |
| `managerial_insights.py` | Renders the Managerial Insights markdown from the result files | Reads `training_summary.json`, `ppo_baselines.json`, `mc_service_levels.npy`; writes `docs/MANAGERIAL_INSIGHTS.md`. Module-private `_haversine_km` after the FIX-021 DRY refactor |
| `generate_all_figures.py` | The one-shot figure renderer for the paper | 7 publication figures (`outputs/figures/fig1_*.png` through `fig7_*.png`) + 2 supplementary. Uses the matplotlib style from `utils/plotting_style.py` |
| `generate_latex_tables.py` | Renders the 6 main + 2 supplementary LaTeX tables | All in `\begin{table}...\end{table}` form with `\caption` and `\label`, ready to drop into the manuscript |

### 4.5 `utils/` — Cross-cutting infrastructure

| File | Plain English | Technical |
|---|---|---|
| `__init__.py` | Re-exports utility helpers | |
| `reproducibility.py` | The `SeedSequence`-based deterministic RNG path | Wraps `np.random.SeedSequence` so every algorithm's seeds are derived deterministically from a single project seed (default 42). Avoids the silent-divergence trap of `np.random.seed()` |
| `serialization.py` | Atomic-write helpers for result files | `atomic_write_json`, `atomic_write_npy` — write to a tmp file then `os.replace()`, so a crash mid-write doesn't leave a half-written corrupted artifact. Used by every Modal-step writer |
| `validators.py` | Non-domination / Pareto-dominance validators used in tests | `is_non_dominated(F)`, `dominates(a, b)`. Pure NumPy, used both at runtime (sanity assertions) and in the test suite |
| `plotting_style.py` | Centralised matplotlib style for the paper figures | Greyscale-friendly, vector-fonts, fixed DPI. `apply_paper_style()` is called by every figure generator so they look consistent |



---

## 5. `webapp/` — Interactive Dashboard

The dashboard is a developer tool, not a deployment target. It lets
you (or a reviewer) point-and-click through the Pareto front, the
resilience-shock outcomes, and the LSTM forecasts without re-running
the full pipeline.

### 5.0 Top-level

| File | Plain English | Technical |
|---|---|---|
| `webapp/README.md` | How to start the dashboard | Two-line dev quick-start: `uvicorn` for backend, `npm run dev` for frontend |

### 5.1 `webapp/backend/` — FastAPI server

Reads pre-computed result files from `data/results/` and exposes them
as JSON endpoints. Read-only and CORS-locked to `localhost:5173`.

| File | Plain English | Technical |
|---|---|---|
| `main.py` | The FastAPI app entry-point | Mounts the four route modules, configures explicit CORS (no wildcards) per audit Section 6, listens on port 8000 |
| `schemas.py` | Pydantic response models for the endpoints | Type-safe `OptimizationResult`, `ResilienceMetrics`, `ForecastResponse` so the frontend never has to guess the shape |
| `requirements.txt` | Backend-only pinned deps (FastAPI, uvicorn, pydantic) | Lock-step with the `image.pip_install` block in `cloud_training/modal_train.py` for the shared algorithm package |
| `README.md` | Backend-only setup notes | |
| `routes/__init__.py` | Marker file | |
| `routes/dashboard.py` | "Show me an overview of the network and the latest run" | Returns the warehouse + customer locations, mean demand, KPI tiles |
| `routes/optimization.py` | "Show me the Pareto front" | Reads `nsga2_best_front.npy`, returns the (cost, carbon) points + chosen-solution metadata |
| `routes/forecasting.py` | "Show me the LSTM forecasts" | Reads `lstm_predictions.npy` + `lstm_actuals.npy`, returns 7-day overlay |
| `routes/simulation.py` | "Run a what-if disruption scenario right now" | Calls `phase2_resilience.des_environment.DESEnvironment` with the scenario the user picked. The only endpoint that does live computation |

### 5.2 `webapp/frontend/` — React + Vite + Recharts dashboard

| Path | Plain English | Technical |
|---|---|---|
| `index.html` | The single HTML entry-point | Standard Vite template, mounts `<div id="root">` |
| `package.json` | Frontend deps (React 18, Recharts 3, Tailwind, Lucide) | npm scripts: `dev` (Vite dev server :5173), `build` (Vite production bundle), `preview` |
| `package-lock.json` | Exact-version dep lock | Committed for reproducibility |
| `vite.config.js` | Vite bundler config | Proxy `/api` → `localhost:8000` so the frontend can call the backend without CORS pain in dev |
| `tailwind.config.js` + `postcss.config.js` | Tailwind CSS config | Standard JIT config |
| `public/vite.svg` | Vite logo for `<link rel="icon">` | Trivial asset |
| `dist/` | Vite production build output | Auto-generated by `npm run build`; safe to delete |
| `node_modules/` | npm dependency tree | Auto-generated by `npm install`; ~500 MB; safe to delete |
| `src/main.jsx` | React mount point | `ReactDOM.createRoot(document.getElementById('root')).render(<App />)` |
| `src/App.jsx` | Top-level layout (sidebar + active panel) | Holds the `activeSection` state; switches between Dashboard / NetworkMap / ParetoChart / ResiliencePanel / TrainingProgress / CarbonBudget |
| `src/api/client.js` | The thin axios/fetch wrapper for backend calls | Centralises base URL, error handling |
| `src/styles/globals.css` | Global Tailwind imports | `@tailwind base/components/utilities` + a few custom utilities |
| `src/components/Sidebar.jsx` | Left-rail navigation | |
| `src/components/Dashboard.jsx` | Overview panel (KPI tiles + summary) | Reads `/api/dashboard` |
| `src/components/MetricCard.jsx` | Reusable KPI card | Pure presentation component |
| `src/components/EmptyState.jsx` | "No data yet, run the pipeline" placeholder | Pure presentation component |
| `src/components/NetworkMap.jsx` | Indian network map (warehouses + customers + routes) | SVG-based map using the Dalal lat/lon points |
| `src/components/ParetoChart.jsx` | Cost-vs-carbon Pareto-front plot | Recharts scatter; reads `/api/optimization/pareto` |
| `src/components/CarbonBudget.jsx` | Green-premium curve view | Reads the carbon-budget solver outputs (10 %, 20 %, 40 % cuts) |
| `src/components/ResiliencePanel.jsx` | TTS / TTR / service-level dashboard under shocks | Reads `/api/simulation/run` |
| `src/components/TrainingProgress.jsx` | Live PPO / NSGA-II training-curve viewer | Reads `data/results/*_rewards.npy` and `*_hv_history` arrays |


---

## 6. `cloud_training/` — Training Entry-Points

| File | Plain English | Technical |
|---|---|---|
| `modal_train.py` | The single production training entry-point. One command, runs the whole pipeline on Modal cloud GPU | `@app.function(gpu="T4", timeout=8h, volumes={"/results": volume})` decorated `train_ultimate()`; six skip-if-exists steps (data → NSGA-II → NSGA-III → MOEA/D → LSTM → PPO-20 stress mode → PPO-100 stress mode → (R,s,S)+random baselines → DES → stats); `@app.local_entrypoint()` `main()` calls `.spawn()` so combined with `--detach` it survives terminal disconnect |
| `local_training_runner.py` | CPU/local fallback driver for laptops without GPU access | `--component {nsga2|nsga3|moead|lstm|ppo|all}` flags; rich.Progress bars; `--resume <checkpoint>` for crash-resilient runs. Used for fast smoke tests during development |
| `TRAINING_GUIDE.md` | Runbook: launch, monitor, download, troubleshoot | Now updated for T4 GPU + ~$1.80 cost + FIX-022 stress-mode pipeline |
| `README_CLOUD_SETUP.md` | Platform comparison: Modal vs Kaggle vs Colab vs Vast.ai | Cost-and-feature matrix; recommendations for which platform fits which workload |
| `kaggle_setup.ipynb` | Pre-baked Kaggle T4 × 2 notebook | Self-contained; clones repo, installs pinned deps, runs `local_training_runner.py` with the appropriate `--component` flags within the 9-hour Kaggle session limit |
| `colab_setup.ipynb` | Pre-baked Google Colab Pro notebook | Same idea for Colab's A100 / V100 / T4 tier; uses `/content/drive/MyDrive` for resumable checkpoints |
| `vastai_setup.sh` | Bootstrap script for Vast.ai rented GPUs | Apt installs + venv + clone + pinned-deps install + `local_training_runner.py` invocation |

`modal_train.py` is the production canonical entry-point; everything
else is for "I want to verify or reproduce this without spending
Modal credit."



---

## 7. `scripts/` — Data Ingestion & One-Off Utilities

These are CLI scripts; not imported by the main pipeline (with one
exception: `_haversine_matrix` is imported from `ingest_dalal_data`
by `cloud_training/modal_train.py`).

| File | Plain English | Technical | Status |
|---|---|---|---|
| `__init__.py` | Marks `scripts/` as a Python package so `from scripts.ingest_dalal_data import _haversine_matrix` works inside Modal | Empty | KEEP |
| `ingest_dalal_data.py` | The primary Dalal (2022) dataset ingestion script | Reads `data/external/dalal_2022/DataSet.xlsx`, supports `--synthetic` fallback, exports `_haversine_matrix` used by Modal's Step 1 (network setup). 17 KB / ~470 lines | KEEP — actively imported by `cloud_training/modal_train.py:73` |
| `integrate_dalal_data.py` | An older, simpler Dalal ingestion script — superseded by `ingest_dalal_data.py` | 10 KB / ~270 lines. Reads the same Excel files but lacks the synthetic-fallback path and the haversine helper Modal needs | **REDUNDANT** — see §17 below |
| `calibrate_demand.py` | One-off script: fit LogNormal(μ, σ) to the DataCo dataset to update `MasterConfig` defaults | Reads `data/external/dataco/DataCoSupplyChainDataset.csv`, fits LogNormal, prints (μ=6.44, σ=0.97) which is the value that landed in `config.py`. Run-once-then-archive | KEEP (low-cost) |
| `run_cvrplib_benchmark.py` | Benchmarks the Clarke-Wright + NSGA-II solvers against CVRPLIB Augerat-Set-A | Reads `data/external/cvrplib/A-n32-k5.vrp`, runs both solvers, computes gap-to-BKS, dumps a LaTeX table to `outputs/tables/cvrplib_validation.tex`. Used to satisfy the implementation-correctness audit point in the manuscript | KEEP |



---

## 8. `tests/` — The Test Suite

488 tests pass, 5 skipped, runs in ~205 s on the Python 3.14 audit
environment. The naming convention
deserves explanation: where you see two test files with similar
names (e.g. `test_nsga2.py` AND `test_nsga2_solver.py`), the
**shorter** name is the legacy unit-test file (small, fast, ad-hoc
checks) and the **longer** name is the property-based-testing
companion that came out of the formal bugfix-spec audit (Hypothesis
strategies, invariants encoded from the bugfix.md clauses). Both
provide value and both pass; they are NOT duplicates.

| File | What it tests | Pair? |
|---|---|---|
| `__init__.py` | Marks `tests/` as a package | n/a |
| `test_carbon_budget.py` | ε-constraint solver: feasibility, monotonic green-premium, edge cases | — |
| `test_clarke_wright.py` | Clarke-Wright savings: capacity feasibility, route concatenation correctness | — |
| `test_complexity_analysis.py` | Complexity benchmark harness: monotone in workload, no NaN, JSON-serialisable | — |
| `test_data_engineering.py` | Network-data generators: shape, demand statistics, distance-matrix symmetry | — |
| `test_des.py` | DES legacy unit tests: SimPy container ops, basic shock firing | paired with `test_des_environment.py` |
| `test_des_environment.py` | DES property-based tests (Audit task 4.4): service-level invariants, eps-guard correctness, replication-scaling laws | paired with `test_des.py` |
| `test_emission_model.py` | MEET model: load-zero rate equals `k`, full-load rate equals `k + L · capacity`, matches IPCC AR6 cross-validation | — |
| `test_gym_env.py` | Gym env legacy unit tests: action/observation bounds, reset behaviour | paired with `test_gym_environment.py` |
| `test_gym_environment.py` | Gym env property-based tests (Audit task 4.6): Gymnasium 1.x API compliance via `check_env`, observation-clip invariant, allocation idempotence | paired with `test_gym_env.py` |
| `test_lstm.py` | LSTM legacy unit tests: training step convergence on a tiny problem | paired with `test_lstm_forecaster.py` |
| `test_lstm_forecaster.py` | LSTM property-based tests (Audit task 4.5): forecast-shape contract, MAPE finiteness, seed reproducibility | paired with `test_lstm.py` |
| `test_managerial_insights.py` | Managerial-insights renderer: schema, citation density, threshold derivation | — |
| `test_math_correctness.py` | Cross-cutting numerical-correctness checks: hypervolume, Pareto dominance, normalisation | — |
| `test_multi_product.py` | Multi-product solver: per-product capacity, density-weighted constraints | — |
| `test_nsga2.py` | NSGA-II legacy unit tests | paired with `test_nsga2_solver.py` |
| `test_nsga2_solver.py` | NSGA-II property-based tests (Audit task 4.3): non-domination invariant, repair-feasibility, joint-HV monotonicity | paired with `test_nsga2.py` |
| `test_nsga2_warmstart.py` | OR-Tools warm-start (FIX-011): cold-start preservation, warm-start HV ≥ cold-start | — |
| `test_nsga3.py` | NSGA-III: 3-objective shape, reproducibility, Pareto non-domination | — |
| `test_pareto_analysis.py` | Hypervolume + Pareto utilities: margin-guard correctness, joint-normalisation | — |
| `test_phase4.py` | Phase 4 statistical-tests harness: Friedman edge cases, Wilcoxon symmetry | — |
| `test_ppo_agent.py` | PPO: Beta(α, β) actor unimodality, ratio-clamp correctness, gradient flow | — |
| `test_regression_baseline.py` | Numeric-baseline regression: re-runs `audit_workspace/capture_numeric_baseline.py` and asserts bit-for-bit / 1e-9 tolerance against `NUMERIC_BASELINE.json` | — |
| `test_robust.py` | Robust solver: LogNormal sampling, mean+λσ formulation | — |
| `test_sac_agent.py` | SAC: action range, log-prob shape, twin-Q shape, no-NaN single update | — |
| `test_sensitivity.py` | Sobol sensitivity: index sums, monotonicity, no-NaN | — |
| `test_ss_policy.py` | (R, s, S) policy: action ∈ [0, 1] (FIX-021), reorder triggers, fall-through, env integration | — |
| `test_tft_forecaster.py` | LightweightTFT: GRN block, attention-row sums, parameter count under 1 M | — |
| `test_utils_reproducibility.py` | SeedSequence-derived RNGs: determinism, divergence-free | — |
| `test_utils_serialization.py` | Atomic-write helpers: never leaves half-written file on simulated crash | — |
| `test_utils_validators.py` | Non-domination validator: pure-numpy correctness | — |
| `test_webapp_endpoints.py` | FastAPI endpoints: status codes, schema-validity, 404 handling | — |



---

## 9. `docs/` — Written Documentation

| File | Plain English | Technical |
|---|---|---|
| `ARCHITECTURE.md` | This file | The codebase tour |
| `IMPROVEMENT_REPORT.md` | The append-only audit log: every parameter change, every fix, every preservation check | Formal record-of-truth tied to the bugfix-spec clauses (FIX-005 through FIX-022). NEVER edit history; only append |
| `MENTOR_REPORT.md` | The status report I send my mentor to get drafting approval | Business-first framing of problem, Dalal dataset, current results, asks |
| `PAPER_OUTLINE.md` | The 9–11 k word draft outline of the manuscript | Section-by-section skeleton from abstract → conclusions; updated post-FIX-022 to flag PPO numbers as "populated after rerun" |
| `MANAGERIAL_INSIGHTS.md` | Practitioner-facing translation of the results | Five takeaways for a planner: green-premium curve, fleet-mix, top routes by tonne-km, disruption playbook, PPO ROI |
| `LITERATURE_GAP_ANALYSIS.md` | The 10-paper gap matrix for §2.5 of the manuscript | Compares this work against ten recent papers (Demir 2014, Wang 2023, Hosseini 2019, Boute 2022, Gijsbrechts 2022, Vanvuchelen 2024, etc.) |
| `COMPLEXITY_ANALYSIS.md` | Per-algorithm theoretical big-O alongside empirical wall-clock | Generated from `audit_workspace/COMPLEXITY_REPORT.json`; satisfies bugfix clauses C1.19 / C2.19 |
| `DATA_SOURCES.md` | Plain-English description of every external dataset and report | Data realism strategy: tier-1 directly-usable, tier-2 India-specific government, tier-3 academic benchmarks, tier-4 industry APIs |
| `REPLICATION_GUIDE.md` | Step-by-step "how to reproduce every artifact in the paper from scratch" | 10-step recipe; matches the manuscript's reproducibility-checklist |
| `HUMAN_INTERFERENCE.md` | The decisions a human had to make and why | Captures non-automatable choices (e.g. "we picked NSGA-III over NSGA-II for the 3-obj front because…") for transparency |
| `VERIFIED_REFERENCES.bib` | The single BibTeX bibliography used everywhere | One entry per cited source; every entry has a `note = {Used in FIX-XXX for ...}` field tying it to the audit log |



---

## 10. `data/` — Datasets and Training Outputs

```
data/
├── README.md             # plain-English description of every subdir
├── external/             # raw third-party datasets (read-only)
├── processed/            # derived numpy arrays calibrated from external/
├── cache/                # cached API responses (ORS distance API)
├── raw/                  # currently empty (placeholder for raw scrapes)
└── results/              # outputs from training runs (PPO weights, NSGA-II fronts, …)
```

### 10.1 `data/external/`

Raw third-party data, never modified after download. Most subdirs are
git-tracked; the large CSVs are git-LFS or ignored.

| Path | Plain English | Technical |
|---|---|---|
| `dalal_2022/DataSet.xlsx` | The Dalal (2022) INFORMS supplement: 101 Indian demand points + 4 product categories + masked lat/lon | Read by `scripts/ingest_dalal_data.py` |
| `dalal_2022/distance_matrix.xlsx` | Pre-computed pairwise OSRM road distances from the paper supplement | Used as the road-distance ground truth |
| `dalal_2022/warehouses.xlsx` | The 5 candidate warehouse locations from the paper supplement | |
| `dalal_2022/demand_location_data_2021.xlsx` | Demand snapshot for an alternate year (used for robustness check) | |
| `dalal_2022/calcDM.py` | The original author's helper to compute the distance matrix | Reference only — we use our own ingestion |
| `dataco/DataCoSupplyChainDataset.csv` | Kaggle DataCo dataset: 180 519 orders × 53 cols (used for demand calibration) | 96 MB |
| `dataco/DescriptionDataCoSupplyChain.csv` | Column-key dictionary for the DataCo CSV | |
| `delhivery/delhivery_data.csv` | Kaggle Delhivery shipments dataset (144 867 shipments, OSRM-vs-actual distance/time) | 56 MB; calibrates OSRM correction factor 0.83 |
| `cvrplib/A-n32-k5.vrp` | One CVRPLIB Augerat-Set-A instance (32 customers, BKS = 784) | Used as a textbook benchmark in `scripts/run_cvrplib_benchmark.py` |
| `vahan_fleet_data.json` | VAHAN dashboard FY2024 fleet-composition snapshot | Compiled from VAHAN + CEIC + Mahindra annual report; gives HCV:LCV = 70:30 |
| `reports/FreightReportNationalLevel.pdf` | Reference report (Indian freight statistics) | |
| `reports/NCAER_Report_LogisticsCost2023.pdf` | NCAER 2024 logistics-cost framework | Source for warehousing INR 15-25 / sq-ft / month |
| `reports/SFC-India-TERI.pdf` | TERI + Smart Freight Centre 2025 emissions whitepaper | Source for India-specific HDV emission validation |
| `supplygraph/` | NeurIPS 2023 SupplyGraph benchmark (held for future GNN comparison) | Currently unused; reserved for follow-up work |
| `svrpbench/` | Stochastic VRP benchmark suite (held for future stochastic-VRP comparison) | Currently unused; reserved for follow-up work |

### 10.2 `data/processed/`

Numpy arrays derived from the raw external data. These are the
artifacts the algorithms actually consume.

| File | Plain English | Technical |
|---|---|---|
| `dalal_customer_locations.npy` | (101, 2) — the lat/lon of every Dalal customer | float64; spans 8.48° N–31.00° N, 72.32° E–92.79° E |
| `dalal_warehouse_locations.npy` | (5, 2) — warehouse coordinates | |
| `dalal_demand.npy` | (101, 4) — per-customer demand for the 4 product categories | |
| `dalal_distance_matrix_km.npy` | (101+5, 101+5) — pairwise road distances in km | OSRM-derived |
| `delhivery_calibration.json` | Fit results: OSRM correction factor 0.83, distance-error stats | |
| `delhivery_customer_locations.npy` | (150, 2) — Delhivery network customer locations | Used as a robustness-check secondary network |
| `delhivery_distance_matrix_km.npy` | Validated road distance matrix from Delhivery shipments | |
| `delhivery_warehouse_locations.npy` | (10, 2) — Delhivery hub locations | |
| `delhivery_network.json` | The full Delhivery network metadata | |
| `demand_calibration.json` | LogNormal(μ=6.44, σ=0.97) fit from DataCo orders | |
| `calibration_params.json` | Aggregated calibration params used by `MasterConfig` | |
| `ors_distance_matrix_km.npy` | (5, 100) — OpenRouteService warehouse-to-customer driving distances | |
| `ors_full_distance_matrix_km.npy` | (105, 105) — full OSRM matrix including warehouse-warehouse | |

### 10.3 `data/cache/`

| File | Plain English |
|---|---|
| `ors_distance_104x104.npy` | Cached ORS API responses for the (warehouse + customer) pairs to avoid re-querying |

### 10.4 `data/raw/`

Empty directory; reserved for raw scrape outputs that haven't yet been
processed. Safe to leave empty.

### 10.5 `data/results/`

Training outputs. After a successful Modal run, this is what
`modal volume get sc-results-v3 / data/results/` populates.

| File | Plain English | Technical |
|---|---|---|
| `nsga2_all_results.pkl` | All 50-seed NSGA-II Pareto fronts + HV histories + joint ideal/nadir | Pickled dict; ~100 KB |
| `nsga2_best_front.npy` | The single highest-HV NSGA-II front (for plotting) | (N, 2) cost-carbon points |
| `nsga3_all_results.pkl` | All 50-seed NSGA-III 3-objective fronts | |
| `moead_all_results.pkl` | All 50-seed MOEA/D fronts | |
| `best_lstm.pt` | Trained LSTM weights | 19 MB |
| `lstm_predictions.npy` / `lstm_actuals.npy` | Held-out 7-day forecasts vs ground truth | For plotting Figure 5 |
| `mc_service_levels.npy` | (100,) — service-level samples from the DES Monte Carlo run | |
| `ppo_small_final.pt` | Final PPO weights for the 20-customer env | 9-21 MB |
| `ppo_full_final.pt` | Final PPO weights for the 100-customer env | |
| `ppo_small_rewards.npy` / `ppo_full_rewards.npy` | Episode-reward traces (training curves) | |
| `ppo_small_ckpt_*.pt` / `ppo_full_ckpt_*.pt` | Checkpoints every 1 M steps for resumable training | |
| `ppo_baselines.json` | (R, s, S) and random-policy mean rewards | |
| `statistical_tests.json` | Friedman + Wilcoxon p-values | |
| `training_summary.json` | The aggregated headline numbers (HVs, MAPE, service level, etc.) | The single file every downstream consumer reads |
| `ppo_ckpt_*.pt`, `ppo_episode_rewards.npy`, `ppo_final.pt` | Legacy PPO outputs from earlier training runs | **OBSOLETE** — see §17 |



---

## 11. `outputs/` — Publication Artifacts

Only the artifacts that ship with the manuscript live here. Anything
that's a "result file" (model weights, raw arrays) lives in
`data/results/` instead.

```
outputs/
├── managerial_thresholds.json   # 4 quantitative thresholds for managers
├── figures/                     # 7 main + 2 supplementary publication figures
│   ├── fig1_network_map.png
│   ├── fig2_pareto_front.png
│   ├── fig3_convergence.png
│   ├── fig4_resilience_dashboard.png
│   ├── fig5_lstm_forecast.png
│   ├── fig6_ppo_training.png
│   ├── fig7_sensitivity_spider.png
│   └── supplementary/
│       ├── supp_fig1_routing.png
│       └── supp_fig2_monte_carlo.png
└── tables/                      # 6 main + 2 validation LaTeX tables
    ├── table1_parameters.tex
    ├── table2_algorithm_comparison.tex
    ├── table3_statistical_tests.tex
    ├── table4_resilience.tex
    ├── table5_ablation.tex
    ├── table6_sensitivity.tex
    ├── cvrplib_validation.tex
    └── trip_relaxation_validation.tex
```

Each table is in `\begin{table}...\end{table}` form with `\caption`
and `\label` so it slots into the manuscript without modification.

| File | Plain English |
|---|---|
| `managerial_thresholds.json` | The 4 quantitative thresholds (utilisation, p95-recovery, green-premium knee, fleet-mix optimum) the managerial-insights doc cites |
| `fig1_network_map.png` | The Indian network map (warehouses + customers + sample routes) |
| `fig2_pareto_front.png` | NSGA-II cost-vs-carbon Pareto front, with marked operating points |
| `fig3_convergence.png` | NSGA-II hypervolume vs generation, mean ± std across 50 seeds |
| `fig4_resilience_dashboard.png` | TTS / TTR / service-level under the three shock classes |
| `fig5_lstm_forecast.png` | LSTM 7-day forecasts vs ground truth, per-customer MAPE band |
| `fig6_ppo_training.png` | PPO reward curve, KL divergence, clip fraction, entropy |
| `fig7_sensitivity_spider.png` | Sobol total-order indices on a radar chart |
| `supplementary/supp_fig1_routing.png` | Detailed route plot for one Pareto solution |
| `supplementary/supp_fig2_monte_carlo.png` | Monte-Carlo replication histograms |



---

## 12. `audit_workspace/` — Regression-Baseline Harness

The forensic-audit workspace from the formal bugfix-spec series
(FIX-005 through FIX-022). Most of these files exist to prove
"the patched code does not change behaviour for inputs outside the
bug condition" (preservation clauses C3.x).

| File | Plain English | Technical | Status |
|---|---|---|---|
| `capture_numeric_baseline.py` | Run the pipeline at fixed seed 42 and dump every numeric output to JSON | Used as the regression-baseline source. Re-run after every fix and diff against `NUMERIC_BASELINE.json` | KEEP (used by `tests/test_regression_baseline.py`) |
| `capture_signatures.py` | Walk every public symbol in the package and dump signatures to JSON | Used to detect breaking signature changes. Diffs against `SIGNATURE_BASELINE.json` | KEEP |
| `check_deliverables.sh` | Bash script that asserts every paper deliverable exists | Pre-submission gate | KEEP |
| `check_docstrings.py` | Asserts every public function has a NumPy-style docstring | Style enforcement | KEEP |
| `check_emissions_block.py` | Asserts emission-model output matches MEET / IPCC AR6 cross-validation | Numeric correctness | KEEP |
| `diff_numeric.py` | Diff two `NUMERIC_BASELINE`-shaped JSON files with tolerance | Used post-fix | KEEP |
| `diff_signatures.py` | Diff two `SIGNATURE_BASELINE`-shaped JSON files | Used post-fix | KEEP |
| `NUMERIC_BASELINE.json` | The captured numeric output from the pre-FIX state | Source-of-truth for the regression test | KEEP |
| `NUMERIC_FINAL.json` | The post-fix capture | KEEP — diff vs `NUMERIC_BASELINE.json` proves preservation |
| `NUMERIC_DIFF_RESULT.txt` | Output of the diff | KEEP |
| `SIGNATURE_BASELINE.json` / `SIGNATURE_FINAL.json` / `SIGNATURE_FINAL_v2.json` | Captured public-API signatures | KEEP — `_v2` is the post-additive-only-changes capture |
| `SIGNATURE_DIFF_RESULT.txt` / `SIGNATURE_DIFF_RESULT_v2.txt` | Diff outputs | KEEP |
| `COMPLEXITY_REPORT.json` | Output of `phase4_synthesis/complexity_analysis.py` | Source for `docs/COMPLEXITY_ANALYSIS.md` | KEEP |
| `COVERAGE_BASELINE.txt` / `COVERAGE_FINAL.txt` / `COVERAGE_FINAL_FULL.txt` | Captured `coverage.py` reports | KEEP |
| `PASSING_TESTS_BASELINE.txt` / `PASSING_TESTS_FINAL.txt` / `PASSING_REGRESSIONS.txt` | Captured pytest run lists | KEEP |
| `_baseline_passed.txt` / `_final_passed.txt` | Marker files for the audit harness | KEEP |
| `DELIVERABLES_FINAL.txt` | Final inventory of paper deliverables | KEEP |
| `STUB_CANDIDATES.txt` / `STUB_FINAL.txt` / `STUB_ALLOWLIST.txt` | The `pass`/`raise NotImplementedError` audit (FIX-014) | KEEP |
| `HARDCODED_CANDIDATES.txt` | The "literals that should live in `MasterConfig`" audit | KEEP |
| `_regdiff.sh` | Shell wrapper for the regression-diff workflow | KEEP |
| `FIX_017_verification.log`, `FIX_018_verification.log`, `FIX_019c_verification.log`, `FIX_019d_verification.log`, `FIX_020_verification.log` | Per-fix verification logs | KEEP — historical record |
| `PBT_4.3_test_nsga2_solver.log`, `PBT_4.4_test_des_environment.log`, `PBT_4.5_test_lstm_forecaster.log`, `PBT_4.6_test_gym_environment.log`, `PBT_4.7_test_ppo_agent.log` | Per-task PBT verification logs | KEEP — historical record |
| `NUMERIC_BASELINE_capture.log` / `NUMERIC_FINAL_capture.log` | Capture-script outputs | KEEP |
| `__pycache__/` | Python bytecode cache | AUTO-GENERATED — safe to delete |

The audit_workspace is large but every file is a verification artifact.
Deleting any of them reduces the project's auditability.



---

## 13. `.kiro/` — Bugfix-Spec Ground Truth

Used by the spec-driven workflow (`Kiro Spec Format`) to track the
formal audit. Treat as historical / read-only.

| File | Plain English | Technical |
|---|---|---|
| `specs/supply-chain-research-audit/bugfix.md` | The original "what's broken and what fixed looks like" spec | Defines bug conditions C(X) and expected behaviour C2.X for every issue surfaced by the audit. ~30 KB |
| `specs/supply-chain-research-audit/design.md` | Architectural decisions for the fix series | The "how we'll go about fixing it" doc |
| `specs/supply-chain-research-audit/tasks.md` | The DAG of fix tasks (1.1 through 5.6) | Status: all 42 tasks completed; this is the reference for which fix touched which files |
| `specs/supply-chain-research-audit/.config.kiro` | Kiro spec metadata | Auto-managed |

---

## 14. Auto-Generated / Cache Directories

These are NOT under version control (or shouldn't be) and are
regenerated as a side-effect of running tests / Python / pytest.
Safe to delete at any time; they will reappear.

| Path | Plain English | Source |
|---|---|---|
| `.coverage` | coverage.py state file | `pytest --cov` runs |
| `.hypothesis/` | Hypothesis property-based-testing example database (cached counter-examples for faster failure-replay) | Hypothesis library, populated automatically |
| `.pytest_cache/` | pytest's last-run cache | pytest itself |
| `**/__pycache__/` | Python bytecode caches scattered across every package | Python interpreter |
| `webapp/frontend/node_modules/` | npm dep tree (~500 MB, ~150 sub-packages) | `npm install` |
| `webapp/frontend/dist/` | Vite production-build output | `npm run build` |



---

## 15. Headline Configuration Values

The single source of truth is `supply_chain_research/config.py`.
Every parameter has a citation comment at point of definition. Below
are the headline values that drive the headline numbers.

| Component | Parameter | Value | Source |
|---|---|---|---|
| Network | n_warehouses | 5 | Dalal 2022 |
| Network | n_customers | 100 (PPO-100, full pipeline) / 20 (PPO-20, smoke) | Dalal 2022 / Boute 2022 §5.1 |
| Demand | LogNormal μ | 6.44 | DataCo 180K-orders fit |
| Demand | LogNormal σ | 0.97 | DataCo fit |
| Vehicle | HCV `k` (CO₂ rate) | 2.610 kg/km | MEET 1999 §3 Tab. 3.2 |
| Vehicle | LCV `k` | 0.890 kg/km | MEET 1999 §3 Tab. 3.3 |
| Vehicle | Diesel CO₂ factor | 2.68 kg/L | IPCC AR6 (2022) |
| Vehicle | Empty-running fraction | 0.35 | NITI Aayog & RMI 2021 §2.2 |
| Vehicle | HCV utilisation | 0.65 | NITI Aayog & RMI 2021 §2.2 |
| Vehicle | HCV : LCV ratio | 70 : 30 | VAHAN dashboard FY2024 |
| Simulation | Truck cruising speed | 35 km/h | NITI Aayog & RMI 2021 §2.2 |
| NSGA-II | pop_size / n_gen | 1000 / 200 (production) / 500 / 400 (default) | Deb 2002 §V; Deb-Jain 2014 |
| NSGA-III | n_partitions | 12 (Das-Dennis → 91 dirs) | Deb-Jain 2014 §IV-D |
| MOEA/D | n_partitions | 99 (uniform → 100 weights) | Zhang & Li 2007 |
| LSTM | hidden_size / n_layers | 256 / 3 | PACF-driven lookback choice |
| PPO | hidden_size | 512 | Andrychowicz 2021 §3.16 |
| PPO | actor LR / critic LR | 3e-4 / 9e-4 (multiplier 3.0) | Andrychowicz 2021 §3.6 Fig. 7 |
| PPO | clip_range / γ / λ | 0.2 / 0.99 / 0.95 | Schulman 2017 §6.1 |
| PPO | rollout / epochs | 4096 / 10 | Schulman 2017 Tab. 3; Huang 2022 detail #1 |
| FIX-022 stress | lead_time_days | 3 | Gijsbrechts 2022 §5.1 Tab. 1 |
| FIX-022 stress | max_order_multiplier | 0.4 | Vanvuchelen 2024 §3.2 (action ranges) |
| FIX-022 stress | holding cost | INR 0.015 / kg-day | NCAER 2024 §3 Tab. 3.2 |
| FIX-022 stress | stockout cost | INR 2.70 / kg | Zipkin 2000 §3.2 newsvendor 1 : 9 |
| FIX-022 stress | initial inventory | 30 % of capacity | Forces immediate reorder decisions |
| Modal | GPU | T4 16 GB at ~$0.59/h | Cost-tuned for $2.85 budget |
| Modal | App name / volume | `supply-chain-ultimate-v3` / `sc-results-v3` | |



---

## 16. Critical Algorithms — Quick Verification Cheat-Sheet

Use this to sanity-check that an output came from the right algorithm.

### NSGA-II (`phase1_foundation/nsga2_solver.py`)
- **Decision tensor**: `x[w, c, v] ∈ ℝ_≥0` shape (5, 100, 2) = 1000 vars
  for the production instance
- **Repair**: `MarginalTradeoffRepair` with per-individual α ~ U(0, 1)
  for the cost-carbon scalarisation — preserves Pareto diversity
- **Evaluation**: vectorised einsum `_evaluate_einsum(x_pop)` —
  ~54× speedup over the naive Python loop
- **Verifier**: 11.2 average Pareto solutions per seed (range 4–21)
  on the production instance

### MEET emission model (`phase1_foundation/emission_model.py`)
- **Formula**: `E(load) = k + L · load` per vehicle type
- **Verifier**: HCV at full load (10 t) → 2.61 + 0.000147 × 10000 =
  4.08 kg CO₂ / km; LCV at full load (3 t) → 0.89 + 0.000079 × 3000 =
  1.13 kg CO₂ / km. These two values appear in
  `audit_workspace/NUMERIC_BASELINE.json` and must reproduce
  bit-for-bit

### DES (`phase2_resilience/des_environment.py`)
- **State**: SimPy `Container` per warehouse for inventory; processes
  for replenishment, customer-order, shock-firing
- **Eps-guard**: every `container.get(amount)` checks
  `amount < container.level + ε` to avoid the SimPy zero-token deadlock
- **Verifier**: 95.6 % service level under no-shock, 100 reps;
  std 0.28 %

### LSTM forecaster (`phase3_ai/lstm_forecaster.py` + `attention_lstm.py`)
- **Inputs**: 30-day window × 100 customers
- **Output**: 7-day forecast horizon
- **Verifier**: MAPE 23.46 %, RMSE 56.46 kg on held-out data

### PPO agent (`phase3_ai/ppo_agent.py`)
- **Actor**: Beta(α, β) on [0, 1], `α = softplus(W₁·h) + 1`,
  `β = softplus(W₂·h) + 1` — guaranteed unimodal, no clamping needed
- **Critic**: state-value LayerNorm + Tanh
- **Buffer**: `RolloutBuffer` with `add(obs, action, reward, value, log_prob, done)`
  — `done = float(term)` per FIX-021 (NOT `term or trunc`)
- **Update**: 2-stage PPO-Clip (Schulman 2017 §3 Eq. 7), entropy bonus,
  decoupled actor/critic LR
- **Verifier**: under FIX-022 stress mode, beats (R, s, S) on per-day
  cost AND service AND completes the full 365-day horizon

### Stress-mode env (`phase3_ai/gym_environment.py`, `_step_stress_mode`)
- **Action**: `[0, 1]^5` — one continuous order-quantity-fraction per
  warehouse
- **Decoded order**: `Q[w] = action[w] × 0.4 × mean_demand × 100`
- **Replenishment**: 3-day lead-time pipeline, capped at unused capacity
- **Reward**: `−(holding + transport + carbon + stockout)` in INR
- **Termination**: 7-day rolling stockout > 50 % triggers early term
  with -500 penalty



---

## 17. Redundant / Dead / Candidate-for-Deletion Files

I went through every file end-to-end. Here's the honest list of
what's redundant, dead, or auto-generated noise. Recommendations are
ranked by how confident I am it's safe to delete.

### 17.1 Definitely safe to delete

| Path | Why | How to verify before deleting |
|---|---|---|
| `data/results/ppo_final.pt` | Legacy single-env PPO weights from a pre-FIX-021 run, before the small/full split. Not loaded anywhere | `grep -r "ppo_final.pt" --include="*.py" .` returns 0 hits |
| `data/results/ppo_episode_rewards.npy` | Legacy single-trace from the same pre-split run | Same — 0 hits |
| `data/results/ppo_ckpt_100352.pt` through `data/results/ppo_ckpt_1001472.pt` (10 files, ~93 MB total) | Legacy 10× checkpoint dumps from a pre-split run; superseded by `ppo_small_ckpt_*.pt` and `ppo_full_ckpt_*.pt` | Same — 0 hits in src code |
| `webapp/frontend/dist/` | Vite production build output; regenerated by `npm run build` | Pure derived artifact |
| Every `__pycache__/` | Python bytecode | Pure derived artifact; pytest regenerates |
| `.coverage` | coverage.py state | Regenerates with `pytest --cov` |

### 17.2 Redundant — recommend deletion after backup

| Path | Why | Mitigation |
|---|---|---|
| `scripts/integrate_dalal_data.py` | Older, simpler Dalal ingestion that's been superseded by `scripts/ingest_dalal_data.py` (which has the synthetic fallback AND exports `_haversine_matrix` that Modal imports). The two scripts exist because the newer one was written from scratch rather than refactoring the older one. **Only `ingest_dalal_data.py` is referenced by the production pipeline.** | Confirm with `grep -r "integrate_dalal_data" --include="*.py" .` (should return 0 imports outside `scripts/compute_ors_distances.py` which doesn't exist anymore) before deleting |

### 17.3 Auto-generated and ignorable

| Path | Action |
|---|---|
| `webapp/frontend/node_modules/` | Add to `.gitignore` if not already. ~500 MB; npm regenerates with `npm install` |
| `.hypothesis/constants/` and `.hypothesis/examples/` | Hypothesis caches counter-examples; safe to leave |
| `.pytest_cache/` | pytest cache; safe to leave |

### 17.4 Looks suspicious but is actually NOT redundant

These are pairs that look duplicate at first glance but are
deliberately separate. Keep both.

| Path A | Path B | Why both exist |
|---|---|---|
| `tests/test_nsga2.py` (341 lines) | `tests/test_nsga2_solver.py` (666 lines) | A is legacy unit tests, B is the property-based-testing companion from audit task 4.3. Both pass; together they cover unit + property invariants |
| `tests/test_lstm.py` (397 lines) | `tests/test_lstm_forecaster.py` (605 lines) | Same pattern — legacy unit + audit task 4.5 PBT |
| `tests/test_des.py` (519 lines) | `tests/test_des_environment.py` (590 lines) | Same pattern — legacy unit + audit task 4.4 PBT |
| `tests/test_gym_env.py` (599 lines) | `tests/test_gym_environment.py` (671 lines) | Same pattern — legacy unit + audit task 4.6 PBT |
| `audit_workspace/SIGNATURE_FINAL.json` | `audit_workspace/SIGNATURE_FINAL_v2.json` | The `_v2` is the post-additive-only-changes capture (FIX-019d); both are kept because the diff between them is itself an audit artifact |
| `audit_workspace/COVERAGE_FINAL.txt` | `audit_workspace/COVERAGE_FINAL_FULL.txt` | `_FULL` is the verbose per-line report; the shorter one is the per-module summary that goes in the manuscript appendix |
| `audit_workspace/NUMERIC_BASELINE.json` | `audit_workspace/NUMERIC_FINAL.json` | The whole point of the audit is to diff these two; both are required |
| `data/external/dalal_2022/DataSet.xlsx` | `data/external/dalal_2022/demand_location_data_2021.xlsx` | DataSet.xlsx is the primary 2022 dataset; the 2021 file is a robustness-check alternate year. Both are referenced in the manuscript |

### 17.5 Quick clean-up commands

```bash
# 1. Delete the legacy PPO artifacts (saves ~93 MB)
rm data/results/ppo_final.pt data/results/ppo_episode_rewards.npy
rm data/results/ppo_ckpt_*.pt

# 2. Delete the redundant Dalal ingestion script (after grep-verify)
rm scripts/integrate_dalal_data.py

# 3. Delete the Vite build output (regenerable)
rm -rf webapp/frontend/dist/

# 4. Delete every __pycache__ (regenerable)
find . -type d -name __pycache__ -exec rm -rf {} +

# 5. Add node_modules to .gitignore if not already
grep -q "node_modules" .gitignore || echo "webapp/frontend/node_modules/" >> .gitignore
```

After these clean-ups: `pytest -q` should still report **488 passed,
5 skipped** on the current audit environment (no test exercises any of
the deleted artifacts).



---

## 18. How to Navigate This Codebase Quickly

If you have 30 minutes and need to understand what's going on, the
optimal reading path is:

1. **`README.md`** (5 min) — Elevator pitch and quick-start
2. **This file, §1–§2** (5 min) — Project identity + pipeline diagram
3. **`docs/MENTOR_REPORT.md`** (5 min) — Business framing of the
   problem and current results
4. **`supply_chain_research/config.py`** skim (5 min) — Every parameter,
   every citation. The "what knobs exist" reference
5. **`cloud_training/modal_train.py`** (10 min) — How the four phases
   chain together end-to-end on Modal

If you have 30 minutes and need to understand a specific algorithm:

- **NSGA-II repair operator**: `phase1_foundation/nsga2_solver.py` →
  `MarginalTradeoffRepair` class
- **Stress-mode env**: `phase3_ai/gym_environment.py` →
  `_step_stress_mode` method, plus `docs/IMPROVEMENT_REPORT.md`
  FIX-022 section
- **Statistical-validation protocol**: `phase4_synthesis/statistical_tests.py`
  → `friedman_test` + `pairwise_wilcoxon_holm`
- **Reproducibility**: `utils/reproducibility.py` →
  `derive_rngs(project_seed)` for the SeedSequence story

If you want to **run the whole pipeline end-to-end**:

```bash
# On a laptop (CPU, slow but works for smoke):
python cloud_training/local_training_runner.py --component all

# On Modal cloud GPU (T4, ~3 h, ~$1.80):
modal run --detach cloud_training/modal_train.py
```

If you want to **just look at the results without running anything**:

```bash
# Start the dashboard
cd webapp/backend && uvicorn main:app --reload --port 8000 &
cd webapp/frontend && npm install && npm run dev
# Visit http://localhost:5173
```

---

## 18. Advanced Phases (7-14)

The project has recently been extended to cover highly advanced RL, resilience, and operational aspects:
- **Phase 7 (Multi-Agent RL):** Replaces centralized PPO with MAPPO and ST-GNN architectures for decentralized, cooperative warehouse control.
- **Phase 8 (Sim-to-Real Domain Randomization):** Bridges the simulation gap using Kaggle M5 dataset and Domain Randomization (`dr_env_wrapper.py`). Note that `DemandDataGenerator` is intentionally synthetic for pre-training, but real-world evaluation uses real data.
- **Phase 9 (Explainable AI):** SHAP and LIME values to interpret RL actions (e.g. why did the agent order X units?).
- **Phase 10 (Dynamic Routing):** Real-time responsive VRP adjustments using Google OR-Tools.
- **Phase 11 (Adversarial RL):** Minimax CVaR-MAPPO against an adversarial agent (`adversarial_trainer.py`) that purposefully disrupts the supply chain to build robustness.
- **Phase 12 (Offline RL):** Decision Transformer (`offline_trainer.py`) trained on static historical expert logs to avoid costly online env interaction during initial training.
- **Phase 13 (Real-Time Traffic):** `TrafficMatrix` using OpenRouteService or pre-computed Delhi travel times to adjust pathing dynamically.
- **Phase 14 (Multi-Objective RL):** `MORLAgent` + `MultiObjectiveSupplyChainEnv` extending PPO to dynamically trade-off Carbon vs Cost based on an input preference vector.

---

*Last updated alongside the FIX-022 stress-mode reformulation and Advanced Phases additions. Every
file path in this document was verified by directory walk on the
date of the FIX-022 commit. If you find a stale reference, it's a
bug — please flag it.*
