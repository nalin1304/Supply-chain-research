# Design Document — Supply Chain Research Audit Bugfix

## Overview

This design resolves 23 defect conditions (C1.1–C1.23) organized into 5 implementation waves with strict regression prevention (C3.1–C3.16). Every new behavior is gated behind a default-off flag or optional argument so that existing outputs remain bit-exact under the same seed.

## Architecture

### Wave 1 — Infrastructure (FIX-001 to FIX-004)

#### FIX-001: Pin dependencies
- **File**: `supply_chain_research/requirements.txt`
- **Action**: Replace all unpinned packages with `==<version>` format
- **Preservation**: C3.1 — existing tests continue to pass

#### FIX-002: Centralize hardcoded values
- **File**: `supply_chain_research/config.py`
- **Action**: Add fields to existing Pydantic sub-configs for every hardcoded numeric literal found in source files. Defaults MUST equal the previously-hardcoded value (C3.13).
- **Affected files**: All modules in `supply_chain_research/` that contain numeric literals ≥ 3 digits
- **Preservation**: C3.13 — identical numeric outputs

#### FIX-003: Implement stubs
- **Files**: All `supply_chain_research/**/*.py` files containing `pass`, `...`, `raise NotImplementedError`, `# TODO`, `# FIXME`
- **Action**: Replace each stub with working implementation
- **Preservation**: C3.1 — no test regressions

#### FIX-004: Add docstrings
- **Files**: All public functions/classes in `supply_chain_research/**/*.py`
- **Action**: Add NumPy-style docstrings (Parameters, Returns, Raises, References)
- **Preservation**: C3.14 — runtime behavior unchanged

### Wave 2 — Research Verification (FIX-005 to FIX-010)

#### FIX-005: Emission parameters
- **Files**: `config.py`, `emission_model.py`
- **Action**: Web-verify MEET/COPERT/IPCC/CPCB/HBEFA values, add inline citations
- **Preservation**: C3.3 — if values confirmed unchanged, bit-exact outputs

#### FIX-006: NSGA-II sizing + NSGA-III
- **New file**: `supply_chain_research/phase1_foundation/nsga3_solver.py`
- **Config addition**: `NSGA3Config` (pop_size=500, n_gen=150, n_partitions=12)
- **Test**: `tests/test_nsga3.py`
- **Preservation**: C3.2 — NSGA-II behavior unchanged

#### FIX-007: OSRM caching + ORS fallback
- **File**: `supply_chain_research/phase1_foundation/data_engineering.py`
- **Config additions**: `NetworkConfig.cache_dir`, `ors_base_url`, `ors_api_key`
- **New functions**: `get_or_compute_matrices()`, `_cache_key()`

#### FIX-008: SimPy 4.x verification + TTR_normalized
- **File**: `supply_chain_research/phase2_resilience/resilience_metrics.py`
- **New function**: `compute_ttr_normalized(ttr_days, shock_magnitude)`
- **Preservation**: C3.9 — existing DES service level preserved

#### FIX-009: TFT baseline
- **New file**: `supply_chain_research/phase3_ai/tft_forecaster.py`
- **Config additions**: `LSTMConfig.model_type`, `tft_hidden_size`, `tft_n_heads`
- **Classes**: `GatedResidualNetwork`, `LightweightTFT`

#### FIX-010: PPO citations + SAC baseline
- **New file**: `supply_chain_research/phase3_ai/sac_agent.py`
- **Config addition**: `SACConfig`
- **Classes**: `ReplayBuffer`, `SACActorNetwork`, `SACCriticNetwork`

### Wave 3 — Architectural Improvements (FIX-011 to FIX-016)

#### FIX-011: Warm-start NSGA-II
- **File**: `supply_chain_research/phase1_foundation/nsga2_solver.py`
- **Signature change**: Add `warm_start: bool = False`, `ortools_cost_solution=None`, `ortools_carbon_solution=None`
- **New function**: `create_warm_start_population()`
- **Preservation**: C3.4 — `warm_start=False` (default) reproduces original behavior

#### FIX-012: Multi-product extension
- **New file**: `supply_chain_research/phase1_foundation/multi_product_solver.py`
- **Config addition**: `ProductConfig` (n_products=1 default)
- **Preservation**: C3.5 — n_products=1 matches single-product

#### FIX-013: Robust optimization
- **New file**: `supply_chain_research/phase1_foundation/robust_solver.py`
- **Config addition**: `RobustConfig` (enabled=False default)
- **Preservation**: C3.6 — enabled=False matches deterministic

#### FIX-014: Clarke-Wright baseline
- **New file**: `supply_chain_research/phase1_foundation/clarke_wright.py`
- **Modified file**: `supply_chain_research/phase1_foundation/baseline_solver.py` (add `method` param)
- **Preservation**: C3.7 — method="ortools" (default) unchanged

#### FIX-015: Carbon-budget variants
- **New file**: `supply_chain_research/phase1_foundation/carbon_budget_solver.py`
- **Config addition**: `CarbonBudgetConfig` (mode="none" default)
- **Preservation**: C3.8 — mode="none" produces unconstrained front

#### FIX-016: Real sensitivity analysis
- **File**: `supply_chain_research/phase4_synthesis/sensitivity_analysis.py`
- **Action**: Replace synthetic Pareto fronts with real `run_nsga2()` calls; add `fast_mode` flag

### Wave 4 — Test Coverage (target ≥ 80%)

New/expanded test files for 7 critical modules:
- `tests/test_emission_model.py` — zero/full load, overload, negative, monotonicity, CIS
- `tests/test_data_engineering.py` — coordinate order, feasibility, matrix properties, caching
- `tests/test_nsga2.py` (expand) — constraints, Pareto non-dominance, repair idempotence, warm-start
- `tests/test_des.py` (expand) — process registration, container guard, time units
- `tests/test_lstm.py` (expand) — input/output shape, no data leakage
- `tests/test_gym_env.py` (expand) — Gymnasium compliance, observation bounds, policy-veto
- `tests/test_ppo_agent.py` (new) — action distribution, advantage normalization, ratio clipping

### Wave 5 — Academic Deliverables + Cloud Training

#### New documents:
- `docs/LITERATURE_GAP_ANALYSIS.md` — 8-12 papers via web search
- `docs/COMPLEXITY_ANALYSIS.md` — theoretical + empirical runtime
- `docs/MANAGERIAL_INSIGHTS.md` — green premium, fleet mix, top-5 routes, playbook, ROI
- `docs/IMPROVEMENT_REPORT.md` — running log of all changes
- `docs/VERIFIED_REFERENCES.bib` — all BibTeX citations
- `docs/PAPER_OUTLINE.md` — full paper structure
- `docs/REPLICATION_GUIDE.md` — step-by-step reproduction

#### New code:
- `supply_chain_research/phase4_synthesis/complexity_analysis.py`
- `supply_chain_research/phase4_synthesis/managerial_insights.py`

#### Cloud training scaffold:
- `cloud_training/README_CLOUD_SETUP.md`
- `cloud_training/kaggle_setup.ipynb`
- `cloud_training/colab_setup.ipynb`
- `cloud_training/vastai_setup.sh`
- `cloud_training/local_training_runner.py` (rich Progress)
- `cloud_training/TRAINING_GUIDE.md`

## Regression Prevention Strategy

All new features gated behind defaults that reproduce original behavior:
| Config key | Default | Effect |
|---|---|---|
| `nsga3.*` | N/A (separate module) | NSGA-II untouched |
| `run_nsga2(warm_start=)` | `False` | Random init preserved |
| `products.n_products` | `1` | Single-SKU preserved |
| `robust.enabled` | `False` | Deterministic preserved |
| `baseline_solver(method=)` | `"ortools"` | OR-Tools preserved |
| `carbon_budget.mode` | `"none"` | Unconstrained preserved |

## Verification

Final regression sweep checks:
1. Zero new test failures vs baseline
2. Coverage ≥ 80%
3. Zero remaining stubs
4. Zero signature violations
5. Numeric regression OK or documented
6. All 21 deliverable files exist
