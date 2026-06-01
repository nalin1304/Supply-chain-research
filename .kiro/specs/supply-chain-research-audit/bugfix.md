# Bugfix Requirements Document

## Introduction

The `supply_chain_research` codebase is a four-phase research pipeline for AI-driven multi-objective resilient supply chain optimization (NSGA-II / MOEA/D bi-objective optimization, SimPy DES with shock models, Attention-LSTM forecasting, and PPO-based RL allocation). It is functionally executable today, but a comprehensive audit against journal-acceptance criteria (EJOR, Transportation Research Part B, Nature Scientific Reports) has surfaced a systemic class of defects: outdated/unverified academic parameters, unimplemented stubs, hardcoded values that bypass the central Pydantic config, missing docstrings, gaps in unit-test coverage, missing architectural variants required to support the paper's claims, and a complete absence of cloud-training scaffolding for the expensive components (NSGA-II × 10 runs, LSTM training, PPO 1M-step training).

This bugfix treats each missing or defective area as a distinct **bug condition C(X)** following the bug condition methodology. For each condition, the original system F either crashes, produces unverified/incorrect results, silently skips work, or fails to expose the artifact required by the paper. The fixed system F' must (a) eliminate the defect for inputs that satisfy C(X), and (b) preserve identical behavior for inputs that do not satisfy C(X) — i.e., previously-correct outputs (NSGA-II Pareto fronts, MEET emission values, DES service-level traces, LSTM forecasts, PPO checkpoints, Phase 4 figures and LaTeX tables) must remain bit-or-statistically equivalent under the same seed unless a citation explicitly mandates a numeric change.

The bug surface spans four parts of the master audit protocol:
- **Part 1 — Research Verification**: Parameters, APIs, and methods that have not been web-verified against 2022–2025 literature (MEET, NSGA-II/III, OSRM, SimPy, LSTM/TFT, PPO/SAC, cloud resources).
- **Part 2 — Code Audit**: Stub functions, hardcoded values not in `config.py`, missing NumPy-style docstrings, and unit-test coverage below 80% for the critical modules. Architectural gaps (NSGA-III, warm-start, multi-product, stochastic demand, Clarke-Wright, carbon-budget variants) that are missing entirely.
- **Part 3 — Academic Improvement**: Missing literature gap analysis, complexity analysis, managerial insights.
- **Part 4 — Cloud Training Setup**: Missing `cloud_training/` directory with Kaggle / Colab / Vast.ai / AWS runbooks and a local progress monitor.
- **Part 5 — Final Deliverables**: Missing `IMPROVEMENT_REPORT.md`, `VERIFIED_REFERENCES.bib`, `PAPER_OUTLINE.md`, `REPLICATION_GUIDE.md`, and pinned `requirements.txt`.

## Bug Analysis

### Current Behavior (Defect)

The codebase exhibits the following defective behaviors when subjected to a journal-acceptance audit. Each clause names the specific input/condition that triggers the defect and the observable incorrect outcome.

**A. Outdated or unverified parameters and methods (Part 1 — Research Verification)**

1.1 WHEN `EmissionModel` is invoked with HCV parameters `k=2.61`, `L=0.000147`, or the diesel emission factor `2.68 kg CO₂/litre` THEN the system uses these values without an inline citation linking them to MEET / IPCC AR6 / CPCB India / COPERT 5 / HBEFA 4.2, and there is no evidence that a 2022–2025 verification was performed.

1.2 WHEN `run_nsga2(...)` is called for the 1000-variable bi-objective problem with `pop_size=500`, `n_gen=100` THEN the system uses sizing that has not been verified against pymoo 0.6.x guidance for high-dimensional MOO and never exposes an NSGA-III alternative for 3-objective extensions.

1.3 WHEN `data_engineering.generate_network_data(config)` is called with the public OSRM endpoint `http://router.project-osrm.org` THEN the system relies on a service whose rate-limits / availability / OpenRouteService alternative have not been verified for 2024–2025, and distance matrices are not cached to disk for reproducibility.

1.4 WHEN any module in `phase2_resilience/` uses SimPy 4.x APIs or computes resilience metrics (TTS, TTR) THEN the system uses patterns and metric definitions that have not been verified against current SimPy 4.x best-practice guidance or current resilience-metric literature (2023–2024).

1.5 WHEN `attention_lstm.AttentionLSTM` is instantiated for demand forecasting THEN the system uses a Bahdanau-style LSTM+Attention without any documented comparison or fallback to Temporal Fusion Transformer (TFT), which is the dominant 2022–2024 baseline.

1.6 WHEN `ppo_agent.PPOAgent` is trained on the `SupplyChainEnv` THEN the system uses PPO-Clip with hyperparameters that have not been justified against 2023–2024 PPO best-practice surveys, and there is no SAC baseline for continuous-action supply-chain disruption recovery.

1.7 WHEN the user attempts to run the expensive components (NSGA-II × 10 runs, LSTM training, PPO 1M steps) THEN the system provides no documented cloud-training option (Kaggle free, Colab Pro, Vast.ai, AWS spot) and assumes local execution.

**B. Stub functions (Issue Class A)**

1.8 WHEN any function or method in `supply_chain_research/**/*.py` is invoked whose body is `pass`, `raise NotImplementedError(...)`, `...`, or contains a `TODO` / `FIXME` comment marking incomplete logic THEN the system either silently does nothing, raises an exception at runtime, or returns placeholder values, which causes downstream modules to receive defective inputs.

1.9 WHEN `phase4_synthesis/sensitivity_analysis.py` is invoked THEN per `KNOWN_ISSUES.md §5.1` the system generates synthetic Pareto fronts instead of running real NSGA-II per parameter configuration, so reported sensitivity indices do not reflect true parameter sensitivity.

**C. Hardcoded values not in `config.py` (Issue Class B)**

1.10 WHEN any module reads a numeric constant (emission coefficients, vehicle capacities, fuel prices, NSGA pop/gen sizes, DES days, replenishment rate, shock multipliers, LSTM/PPO hyperparameters, ratios such as 0.7 capacity / 30/70 mix / 1.1 reference-point margin) directly from a literal in source code rather than from `MasterConfig` THEN the system makes parameters opaque to reviewers and prevents config-driven sensitivity studies.

**D. Missing NumPy-style docstrings (Issue Class C)**

1.11 WHEN a public function, class, or method in `supply_chain_research/**/*.py` is inspected via `help(...)` or `inspect.getdoc(...)` THEN the system returns `None` or a non-NumPy-style description, blocking auto-generated API documentation and reviewer comprehension.

**E. Insufficient unit-test coverage (Issue Class D)**

1.12 WHEN `pytest --cov=supply_chain_research` is executed against the existing `tests/` suite THEN the system reports overall coverage below 80%, and the seven critical modules (`emission_model`, `data_engineering`, `nsga2_solver`, `des_environment`, `lstm_forecaster`, `gym_environment`, `ppo_agent`) lack the targeted unit tests required for journal-acceptance.

**F. Missing architectural improvements (I1–I6)**

1.13 WHEN the user requests a 3-objective Pareto front (cost, carbon, max delivery time) THEN the system has no NSGA-III implementation and cannot answer the question.

1.14 WHEN `run_nsga2(...)` initializes its population THEN the system seeds randomly only and provides no warm-start option using OR-Tools cost-only and carbon-only solutions, slowing convergence and weakening any "novel hybrid" claim in the paper.

1.15 WHEN the bi-objective formulation is solved THEN the system treats demand as a single homogeneous SKU and has no multi-product extension (Electronics / FMCG / Bulk), which is a known reviewer concern for industrial realism.

1.16 WHEN demand uncertainty is considered THEN the system treats demand as deterministic in the optimization (only the DES is stochastic) and has no robust-optimization formulation over `n_scenarios=10` with `mean + λ·std` objectives.

1.17 WHEN `baseline_solver.solve_cvrp_baseline(...)` is invoked as the non-OR-Tools baseline THEN the system has no Clarke-Wright Savings Algorithm baseline for direct comparison against the multi-objective Pareto front.

1.18 WHEN the user requests a carbon-budget-constrained scenario (no budget / 20% reduction / 40% reduction) THEN the system has no constraint variant and cannot generate the green-premium-vs-budget curve.

**G. Missing academic / paper deliverables (Part 3 + Part 5)**

1.19 WHEN a journal reviewer requests a literature gap analysis or a complexity analysis (time/space + empirical runtime) for NSGA-II, MOEA/D, DES, LSTM, and PPO THEN the system has no such analysis on disk.

1.20 WHEN a journal reviewer requests managerial insights (green-premium curve, fleet mix, top-5 routes, disruption playbook, ROI of the PPO agent) THEN the system has no document containing these.

1.21 WHEN the deliverables `IMPROVEMENT_REPORT.md`, `VERIFIED_REFERENCES.bib`, `PAPER_OUTLINE.md`, `REPLICATION_GUIDE.md` are requested THEN the system does not contain them.

1.22 WHEN `pip install -r supply_chain_research/requirements.txt` is executed THEN the system installs unpinned versions (`torch`, `pymoo`, `gymnasium`, etc. with no `==` specifier), so reproducibility across machines and across time is not guaranteed.

**H. Missing cloud-training scaffold (Part 4)**

1.23 WHEN the user wants to run NSGA-II × 10 seeds, LSTM training, or PPO 1M-step training on cloud infrastructure THEN the system has no `cloud_training/` directory containing `README_CLOUD_SETUP.md`, `kaggle_setup.ipynb`, `colab_setup.ipynb`, `vastai_setup.sh`, `local_training_runner.py` (with rich progress monitoring), or `TRAINING_GUIDE.md` (ordered runbook + resume instructions).

### Expected Behavior (Correct)

For each defect above, the fixed system F' must produce the following correct behavior. Each Expected clause is paired with its corresponding Current clause.

**A. Verified parameters and methods**

2.1 WHEN `EmissionModel` is invoked with HCV parameters `k`, `L`, and the diesel emission factor THEN the system SHALL use values that are either confirmed against MEET (Hickman 1999 / Ntziachristos & Samaras 2009), IPCC AR6, CPCB India, COPERT 5, and HBEFA 4.2 — with the source of each value cited inline as a Python-comment citation in `emission_model.py` and recorded in `VERIFIED_REFERENCES.bib`. If web verification reveals a more current value, the parameter SHALL be updated and the change documented in `IMPROVEMENT_REPORT.md`.

2.2 WHEN `run_nsga2(...)` is called for the 1000-variable bi-objective problem THEN the system SHALL use `pop_size` and `n_gen` justified against current pymoo 0.6.x guidance (cited inline in `nsga2_solver.py`), and an NSGA-III implementation SHALL be available (`run_nsga3(...)` in `phase1_foundation/nsga3_solver.py`) for the 3-objective extension `(cost, carbon, max_delivery_time)`.

2.3 WHEN `data_engineering.generate_network_data(config)` is called THEN the system SHALL document the current OSRM endpoint status, expose an OpenRouteService alternative, and cache computed distance matrices to `data/cache/distance_matrix.npy` so that subsequent runs are deterministic and offline-capable.

2.4 WHEN any module in `phase2_resilience/` uses SimPy 4.x APIs or computes TTS / TTR THEN the system SHALL follow current SimPy 4.x best-practice patterns (cited inline) and use TTS / TTR definitions that match the 2023–2024 resilience-metric literature, with citations recorded in `VERIFIED_REFERENCES.bib`.

2.5 WHEN `attention_lstm.AttentionLSTM` is instantiated THEN the system SHALL provide either (a) an inline citation justifying LSTM+Attention against TFT for this problem size, or (b) a TFT baseline implementation that can be selected via config — and the chosen approach SHALL be documented in `IMPROVEMENT_REPORT.md`.

2.6 WHEN `ppo_agent.PPOAgent` is trained THEN the system SHALL use hyperparameters justified against 2023–2024 PPO best-practice surveys (cited inline in `ppo_agent.py`), and a SAC baseline SHALL be available so the paper can claim PPO-vs-SAC comparison.

2.7 WHEN the user wants to run expensive components on cloud infrastructure THEN the system SHALL provide a complete `cloud_training/` directory (see clause 2.23).

**B. No stub functions**

2.8 WHEN any public function or method in `supply_chain_research/**/*.py` is invoked THEN the system SHALL execute fully-implemented logic — every `pass`, `raise NotImplementedError`, `...`, `TODO`, and `FIXME` related to incomplete implementation in production modules SHALL be replaced by working code with tests covering it.

2.9 WHEN `phase4_synthesis/sensitivity_analysis.py` is invoked THEN the system SHALL invoke `run_nsga2(...)` for each parameter configuration and compute sensitivity indices from real Pareto fronts (with a fast-mode flag for CI that uses a reduced grid but never synthetic data).

**C. All numeric values centralized in `config.py`**

2.10 WHEN any module reads a non-trivial numeric constant THEN the system SHALL retrieve it from `MasterConfig` (or a sub-config attached to `MasterConfig`) — including emission coefficients, vehicle capacities, fuel prices, NSGA pop/gen sizes, DES days, replenishment rate, shock multipliers, LSTM/PPO hyperparameters, and ratios such as 0.7 capacity-fraction, 30/70 augmentation mix, 1.1 reference-point margin. New parameters introduced by improvements I1–I6 SHALL also live in `config.py`.

**D. NumPy-style docstrings on all public APIs**

2.11 WHEN a public function, class, or method in `supply_chain_research/**/*.py` is inspected via `help(...)` or `inspect.getdoc(...)` THEN the system SHALL return a NumPy-style docstring containing at minimum `Parameters`, `Returns`, and (where applicable) `Raises` and `References` sections.

**E. Unit-test coverage ≥ 80% with targeted module tests**

2.12 WHEN `pytest --cov=supply_chain_research` is executed THEN the system SHALL report overall coverage ≥ 80%, and each of the seven critical modules (`emission_model`, `data_engineering`, `nsga2_solver`, `des_environment`, `lstm_forecaster`, `gym_environment`, `ppo_agent`) SHALL have at least one dedicated test file in `tests/` exercising its core paths (correctness, edge cases, regression).

**F. Architectural improvements I1–I6 implemented**

2.13 WHEN the user requests a 3-objective Pareto front THEN the system SHALL provide `run_nsga3(config, distance_matrix, demand, ...)` returning a 3-objective Pareto set over `(cost, carbon, max_delivery_time)`, with config in `MasterConfig.nsga3`.

2.14 WHEN `run_nsga2(...)` is invoked with `warm_start=True` THEN the system SHALL seed the initial population with OR-Tools cost-only and OR-Tools carbon-only solutions, and SHALL accept `warm_start=False` to preserve the original random-seeding behavior bit-for-bit (see preservation clause 3.4).

2.15 WHEN the bi-objective formulation is solved with `n_products > 1` THEN the system SHALL handle three SKU categories (Electronics, FMCG, Bulk) with per-SKU demand vectors, capacities, and emission profiles. When `n_products = 1`, the system SHALL behave identically to the original single-product formulation (preservation clause 3.5).

2.16 WHEN robust optimization is requested via `MasterConfig.robust.enabled = True` THEN the system SHALL evaluate every candidate over `n_scenarios = 10` stochastic-demand draws and use `mean + λ·std` as the objective. When `MasterConfig.robust.enabled = False`, behavior SHALL be identical to the deterministic formulation (preservation clause 3.6).

2.17 WHEN `baseline_solver` is invoked with `method="clarke_wright"` THEN the system SHALL execute the Clarke-Wright Savings Algorithm and return a route plan comparable to the OR-Tools baseline in cost / emission units. The OR-Tools method SHALL remain available unchanged (preservation clause 3.7).

2.18 WHEN a carbon-budget variant is requested via `MasterConfig.carbon_budget.mode in {"none", "20pct", "40pct"}` THEN the system SHALL solve the optimization under the corresponding constraint and return both the constrained Pareto front and the green-premium curve. `mode="none"` SHALL reproduce the original unconstrained behavior (preservation clause 3.8).

**G. Academic deliverables present**

2.19 WHEN a journal reviewer requests literature gap analysis (8–12 papers) and complexity analysis THEN the system SHALL contain both in `docs/LITERATURE_GAP_ANALYSIS.md` and `docs/COMPLEXITY_ANALYSIS.md` (theoretical big-O plus measured wall-clock from the test suite).

2.20 WHEN a journal reviewer requests managerial insights THEN the system SHALL contain `docs/MANAGERIAL_INSIGHTS.md` covering green-premium curve, fleet mix, top-5 routes, disruption playbook, and ROI of the PPO agent — each backed by figures already produced by `phase4_synthesis/`.

2.21 WHEN the final deliverables are requested THEN `IMPROVEMENT_REPORT.md`, `VERIFIED_REFERENCES.bib`, `PAPER_OUTLINE.md`, and `REPLICATION_GUIDE.md` SHALL exist at the repository root and SHALL document, respectively: every stub fixed and every parameter updated (with citation); all academic citations in BibTeX; the paper outline (abstract, sections, figure/table placement, word counts, key claims); and step-by-step replication instructions.

2.22 WHEN `pip install -r supply_chain_research/requirements.txt` is executed THEN the system SHALL install pinned versions (every package with `==<version>`) consistent with the versions used to produce the audit results.

**H. Cloud-training scaffold present**

2.23 WHEN the user wants cloud training THEN the system SHALL provide a `cloud_training/` directory containing exactly `README_CLOUD_SETUP.md`, `kaggle_setup.ipynb`, `colab_setup.ipynb`, `vastai_setup.sh`, `local_training_runner.py` (with rich progress monitoring via `rich` or `tqdm`), and `TRAINING_GUIDE.md` (ordered runbook + resume instructions for NSGA-II × 10, LSTM training, PPO 1M-step). Each file SHALL be runnable end-to-end on its target platform.

### Unchanged Behavior (Regression Prevention)

For inputs that do not satisfy any bug condition above, the fixed system F' must behave identically to the original system F. The following clauses define that preservation contract.

3.1 WHEN existing tests in `tests/test_emission_model.py`, `tests/test_des.py`, `tests/test_gym_env.py`, `tests/test_lstm.py`, `tests/test_math_correctness.py`, `tests/test_nsga2.py`, `tests/test_phase4.py` are executed against F' under the same Python and dependency versions THEN the system SHALL CONTINUE TO pass every assertion that previously passed (no regression in the existing suite).

3.2 WHEN `run_nsga2(config, distance_matrix, demand, pop_size=500, n_gen=100, seed=42)` is invoked with the default arguments and `warm_start=False` (or the parameter absent) THEN the system SHALL CONTINUE TO produce a Pareto front whose objective values match the pre-fix results within numerical tolerance for the same seed (the random-seed schedule is preserved).

3.3 WHEN `EmissionModel.compute(...)` is called with HCV parameters that the verification step confirms unchanged THEN the system SHALL CONTINUE TO return the same kg-CO₂ values bit-for-bit. Only parameters that the citation step explicitly mandates an update SHALL change, and each such change SHALL be enumerated in `IMPROVEMENT_REPORT.md`.

3.4 WHEN `run_nsga2(..., warm_start=False)` is invoked (or the argument is absent) THEN the system SHALL CONTINUE TO seed the initial population randomly using the original RNG path so that pre-fix Pareto fronts reproduce exactly under the same seed.

3.5 WHEN the multi-product extension is disabled (`MasterConfig.products.n_products = 1`, the default) THEN the system SHALL CONTINUE TO behave as a single-SKU optimization with identical objective values for the same seed.

3.6 WHEN robust optimization is disabled (`MasterConfig.robust.enabled = False`, the default) THEN the system SHALL CONTINUE TO solve the deterministic formulation with identical objective values for the same seed.

3.7 WHEN `baseline_solver.solve_cvrp_baseline(...)` is invoked with `method="ortools"` (or the argument is absent, defaulting to OR-Tools) THEN the system SHALL CONTINUE TO produce the same route plan and objective values as before.

3.8 WHEN the carbon-budget variant is disabled (`MasterConfig.carbon_budget.mode = "none"`, the default) THEN the system SHALL CONTINUE TO produce the unconstrained Pareto front with identical objective values for the same seed.

3.9 WHEN `phase2_resilience/des_environment.py` is run under the no-shock baseline THEN the system SHALL CONTINUE TO produce the ~95% mean service level documented in `audit_workspace/AUDIT_LOG.md` (the previously-applied DES replenishment fix is preserved and not re-broken).

3.10 WHEN `phase3_ai/gym_environment.py` returns observations THEN the system SHALL CONTINUE TO clip observations to `[0.0, 1.0]` and use the policy-veto / proportional-scaling mechanism described in `docs/HUMAN_INTERFERENCE.md §7` (these prior fixes are preserved).

3.11 WHEN `phase4_synthesis/generate_all_figures.py` and `phase4_synthesis/generate_latex_tables.py` are invoked THEN the system SHALL CONTINUE TO produce the same nine figures and six LaTeX tables (filenames and on-disk locations unchanged); only figures/tables newly required by the architectural improvements SHALL be added.

3.12 WHEN any user code imports a public symbol from `supply_chain_research` (e.g., `from supply_chain_research.phase1_foundation.nsga2_solver import run_nsga2`) THEN the system SHALL CONTINUE TO expose that symbol with the same signature; new optional arguments SHALL have default values that preserve original behavior.

3.13 WHEN parameters that are moved into `config.py` to fix clause 1.10 are read by their existing call sites THEN the system SHALL CONTINUE TO produce identical numeric outputs because `config.py` defaults SHALL be set to the exact values previously hardcoded.

3.14 WHEN docstrings are added to fix clause 1.11 THEN the system SHALL CONTINUE TO execute every function with the same runtime behavior (docstrings affect introspection only).

3.15 WHEN new tests are added to fix clause 1.12 THEN the system SHALL CONTINUE TO pass the existing `pytest` suite without modification to non-test source files (test additions alone SHALL NOT cause production-code regressions).

3.16 WHEN any new artifact under `cloud_training/`, `docs/`, or new top-level deliverable files (`IMPROVEMENT_REPORT.md`, `VERIFIED_REFERENCES.bib`, `PAPER_OUTLINE.md`, `REPLICATION_GUIDE.md`) is added THEN the system SHALL CONTINUE TO run the existing pipeline locally exactly as before — these are additive deliverables and SHALL NOT alter any import path or execution path of the existing modules.
