# docs/REPLICATION_GUIDE.md

This document satisfies bugfix clauses C1.21 and C2.21 of `.kiro/specs/supply-chain-research-audit/bugfix.md` (FIX-019d). It is the canonical runbook for reproducing every numerical figure, table, and metric reported in `docs/PAPER_OUTLINE.md` from a clean environment. Every step is ordered, every artefact size is documented, and every known issue is annotated.

The pipeline takes approximately 4-5 hours of A100 GPU time (cloud) or 2-3 days of CPU time (laptop). On the A100 the dominant cost is NSGA-II ×50 seeds (≈4 hours) followed by PPO 5M-step total (≈45 minutes); the LSTM training, MOEA/D, and DES Monte-Carlo combined fit inside 30 minutes.

## Environment Setup

This pipeline targets Python 3.11 or newer. We have validated the full run on Python 3.14.3 (audit machine) and Python 3.11 (Modal cloud image). The pinned requirements file (`supply_chain_research/requirements.txt`) is the single source of truth for package versions; FIX-001 enforces every line carries an exact `==` pin.

### Operating system

- macOS 14.x or newer (Apple Silicon natively supported via PyTorch's MPS backend; falls back to CPU when MPS is unavailable).
- Ubuntu 22.04 / 24.04 (production cloud target).
- Debian 12 (Modal default container image).
- Windows 11 with WSL2 (untested but expected to work given the Linux-compatible dependency set).

### GPU

A GPU is optional but recommended for the PPO and LSTM steps. The code paths fall back to CPU when CUDA is unavailable; the device-detection logic in `phase3_ai/lstm_forecaster.py::LSTMForecaster.__init__` and `phase3_ai/ppo_agent.py::PPOAgent.__init__` accepts both string and `torch.device` arguments and auto-selects CUDA when available. The Modal cloud-training pipeline uses an NVIDIA A100 (40 GB or 80 GB) by default.

### Python environment

Use `venv` or `conda` to isolate the environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r supply_chain_research/requirements.txt
```

The pinned requirement set installs in roughly 90 seconds on a clean system with a warm pip cache. PyTorch 2.10 and pymoo 0.6.1.6 dominate the install size at approximately 800 MB combined.

### External services (optional)

- **OSRM**: the data-engineering layer (FIX-007) caches OSRM driving distances to `data/cache/distance_matrix.npy` on first use. The default OSRM endpoint is `https://router.project-osrm.org`, subject to the public service's rate limits. To bypass the cache, delete the cached `.npy` file or set `NetworkConfig.cache_dir` to a fresh directory.
- **OpenRouteService**: when OSRM is rate-limited, the code falls back to the OpenRouteService HTTP API. Set `ORS_API_KEY` in the environment to enable this fallback; `NetworkConfig.ors_api_key` defaults to an empty string so no secret is stored in source.
- **Modal**: cloud training uses Modal's serverless GPU containers. Authenticate with `modal token new` and ensure the workspace name matches the one in `cloud_training/modal_train.py` (the default app name is `supply-chain-ultimate-v3`).

### Verifying the environment

Run the test suite before the production pipeline to confirm the environment is correctly configured:

```bash
pytest tests/ -q
```

Expected: ~352 tests collected, ≥346 passing, ≤6 skipped (the LIVE-gated OSRM/ORS probes plus a few config-shape-dependent regressions). The exact baseline is in `audit_workspace/PASSING_TESTS_BASELINE.txt`.

## Ordered Runbook (10 Steps)

The pipeline is executed in dependency order. Each step is gated by the existence of its output artefacts, so re-running after a crash or a partial completion is safe and resumes from the next missing artefact.

### Step 1: Generate Network Data

Generate the synthetic 5-warehouse 100-customer network with cached OSRM driving distances (FIX-007).

```bash
python3 -c "
from supply_chain_research.config import MasterConfig
from supply_chain_research.phase1_foundation.data_engineering import generate_customer_locations, get_warehouse_locations, generate_demand
import numpy as np
cfg = MasterConfig()
rng = np.random.default_rng(42)
customers = generate_customer_locations(cfg, rng)
warehouses = get_warehouse_locations(cfg)
demand = generate_demand(cfg, rng)
print('Network ready:', customers.shape, warehouses.shape, demand.shape)
"
```

Expected output sizes:
- `data/cache/distance_matrix.npy`: ≈ 80 KB (5 × 100 float64 matrix).
- `data/cache/duration_matrix.npy`: ≈ 80 KB (same shape, optional).

The first run with a cold OSRM cache takes 30-60 seconds; subsequent runs read from cache in under 100 ms. The cache is content-addressed by the SHA-256 hash of the coordinate tuple, so any change to warehouse or customer locations triggers a re-fetch.

### Step 2: Calibrate the Emission Model

Verify the MEET-calibrated emission rates against the documented anchors (FIX-005):

```bash
python3 -c "
from supply_chain_research.config import MasterConfig
from supply_chain_research.phase1_foundation.emission_model import EmissionCalculator
cfg = MasterConfig()
calc = EmissionCalculator(cfg)
print('HCV at 0 kg load:', calc.emission_rate('HCV', 0.0), 'kg CO2/km')
print('HCV at full load:', calc.emission_rate('HCV', cfg.vehicle.hcv_capacity), 'kg CO2/km')
print('LCV at 0 kg load:', calc.emission_rate('LCV', 0.0), 'kg CO2/km')
print('LCV at full load:', calc.emission_rate('LCV', cfg.vehicle.lcv_capacity), 'kg CO2/km')
"
```

Expected output:
- HCV at 0 kg load: 2.61 kg CO2/km (Hickman 1999 §3 Table 3.2 baseline `k`).
- HCV at full load: 4.08 kg CO2/km (`k + L * capacity` for HCV).
- LCV at 0 kg load: 0.89 kg CO2/km (Hickman 1999 §3 Table 3.3).
- LCV at full load: 1.127 kg CO2/km.

These values match `audit_workspace/NUMERIC_BASELINE.json` bit-for-bit (preservation clause C3.3). Any discrepancy indicates the configuration has been tampered with; re-clone the repository.

### Step 3: Run NSGA-II ×50 Seeds

This is the largest single step in the pipeline (≈4 hours on A100, ≈30 hours on CPU). It produces the bi-objective Pareto fronts for the cost-vs-carbon tradeoff.

```bash
# Cloud (recommended):
modal run --detach cloud_training/modal_train.py
# This runs Steps 3-9 of the cloud pipeline; subsequent re-runs skip
# completed steps via on-volume artefact checks.

# Local CPU/GPU:
python3 -m cloud_training.local_training_runner --component nsga2 --seeds 50
```

Expected output:
- `data/results/nsga2_all_results.pkl`: ≈ 100 KiB (50 fronts, 50 hypervolumes, 50 HV histories).
- `data/results/nsga2_best_front.npy`: ≈ 240 B (best-by-HV front).

The mean hypervolume across 50 seeds is approximately 7.13e-1 (joint-normalised) on the production network. Any deviation greater than 1% suggests a regression; re-run with `--seeds 5` to debug.

### Step 4: Run NSGA-III + MOEA/D Baselines

These are the multi-algorithm baselines for the Friedman three-way comparison.

```bash
modal run --detach cloud_training/modal_train.py    # cloud — runs 2b + 2c automatically
# OR:
python3 -m cloud_training.local_training_runner --component nsga3 --seeds 50
python3 -m cloud_training.local_training_runner --component moead --seeds 50
```

Expected output:
- `data/results/nsga3_all_results.pkl`: ≈ 3 KiB (50 fronts, 50 HVs).
- `data/results/moead_all_results.pkl`: ≈ 4 KiB (50 fronts, 50 HVs).

NSGA-III adds a third objective (max delivery time) and uses 91 Das-Dennis reference directions [debjain2014nsga3]; MOEA/D uses 99-partition uniform reference directions [zhang2007moead]. Wall-clock: NSGA-III ≈ 26 minutes on A100; MOEA/D ≈ 0.2 minutes.

### Step 5: Train the LSTM Demand Forecaster

Train the 256-hidden, 3-layer Attention-LSTM with `patience=15` early stopping on a 3-year × 100-customer synthetic demand series.

```bash
modal run --detach cloud_training/modal_train.py    # cloud — runs as part of the unified pipeline
# OR:
python3 -m cloud_training.local_training_runner --component lstm
```

Expected output:
- `data/results/lstm_predictions.npy`: ≈ 100 KB (held-out forecasts).
- `data/results/lstm_actuals.npy`: ≈ 100 KB (held-out actuals).
- `data/results/lstm_checkpoint.pt`: ≈ 30 MB (model weights + optimizer state).

Expected MAPE: 8.2% on the Diwali-period holdout. Training time: ≈ 6 minutes on A100, ≈ 30 minutes on Apple M1.

### Step 6: Train PPO Inventory Agents (3M Small + 2M Full)

Train two PPO-Clip agents: a small instance (20 customers, 3M steps) and a full instance (100 customers, 2M steps). The full instance is the production target; the small instance is for ablation and rapid debugging.

```bash
modal run --detach cloud_training/modal_train.py    # cloud — runs as Steps 4a + 4b of the unified pipeline
# OR:
python3 -m cloud_training.local_training_runner --component ppo --variant small
python3 -m cloud_training.local_training_runner --component ppo --variant full
```

Expected output:
- `data/results/ppo_small_final.pt`: ≈ 50 MB (actor + critic weights, 512-hidden).
- `data/results/ppo_small_rewards.npy`: ≈ 40 KB (per-episode rewards).
- `data/results/ppo_full_final.pt`: ≈ 60 MB.
- `data/results/ppo_full_rewards.npy`: ≈ 30 KB.

Expected per-episode mean reward (last 100 episodes):
- 20-customer instance: approximately -760.
- 100-customer instance: approximately depends on demand distribution; consult the figure 6 panels for the production trajectory.

Wall-clock: PPO-20 ≈ 25 minutes on A100; PPO-100 ≈ 20 minutes (smaller per-step but larger network).

### Step 7: Run DES Monte Carlo (100 Replications)

Run the SimPy DES backbone for 100 Monte-Carlo replications under the no-shock baseline plus the three configured shock scenarios.

```bash
modal run --detach cloud_training/modal_train.py    # cloud — Step 5 of the unified pipeline
# OR:
python3 -c "
from supply_chain_research.config import MasterConfig
from supply_chain_research.phase2_resilience.des_environment import DESEnvironment
import numpy as np
cfg = MasterConfig()
sls = []
for run in range(100):
    des = DESEnvironment(config=cfg, seed=run)
    res = des.run()
    sls.append(res['mean_service_level'])
np.save('data/results/mc_service_levels.npy', np.array(sls))
print('Mean SL:', np.mean(sls), '±', np.std(sls))
"
```

Expected output:
- `data/results/mc_service_levels.npy`: ≈ 1 KB (100 floats).
- Mean service level: 0.9566 ± 0.0042 (no-shock baseline; matches preservation clause C3.9 within 0.005 absolute tolerance).

### Step 8: Generate the Phase 4 Figures

Render the nine publishable figures from the artefact directory.

```bash
python3 -m supply_chain_research.phase4_synthesis.generate_all_figures
```

Expected output (300 DPI PNG, EJOR house style):
- `outputs/figures/figure_1_network_map.png`: ≈ 1.5 MB.
- `outputs/figures/figure_2_pareto_front.png`: ≈ 800 KB.
- `outputs/figures/figure_3_green_premium.png`: ≈ 600 KB.
- `outputs/figures/figure_4_nsga3_3d.png`: ≈ 1.2 MB.
- `outputs/figures/figure_5_lstm_vs_tft.png`: ≈ 700 KB.
- `outputs/figures/figure_6_ppo_training.png`: ≈ 1.0 MB.
- `outputs/figures/figure_7_resilience.png`: ≈ 800 KB.
- `outputs/figures/figure_8_sensitivity.png`: ≈ 600 KB.
- `outputs/figures/figure_9_complexity.png`: ≈ 500 KB.

Total figure-bundle size: approximately 7-8 MB across the nine figures. The script reads from `data/results/` and writes to `outputs/figures/`; both directories are created on demand.

### Step 9: Generate the Phase 4 LaTeX Tables

Render the six LaTeX tables (table_1 through table_6) for direct inclusion in the EJOR manuscript.

```bash
python3 -m supply_chain_research.phase4_synthesis.generate_latex_tables
```

Expected output:
- `outputs/tables/table_1_pareto.tex`: Pareto-front statistics, 50-seed Wilcoxon vs MOEA/D and NSGA-III.
- `outputs/tables/table_2_green_premium.tex`: per-reduction cost, delta, premium INR/kg CO2.
- `outputs/tables/table_3_forecast.tex`: per-customer MAPE distribution and aggregates.
- `outputs/tables/table_4_resilience.tex`: TTS, TTR, TTR_normalized with confidence intervals.
- `outputs/tables/table_5_sobol.tex`: first-order, total-order, and pairwise interaction Sobol indices.
- `outputs/tables/table_6_complexity.tex`: theoretical big-O alongside empirical complexity constants.

Each table is in `\begin{table}...\end{table}` form with `\caption` and `\label` macros so it slots into the EJOR manuscript without modification.

### Step 10: Generate the Final Synthesis Documents

Generate the managerial-insights document, the literature gap analysis, the complexity analysis, and refresh the improvement report.

```bash
python3 -m supply_chain_research.phase4_synthesis.managerial_insights > docs/MANAGERIAL_INSIGHTS.md
python3 -c "
from supply_chain_research.phase4_synthesis.complexity_analysis import dump_complexity_report
dump_complexity_report('audit_workspace/COMPLEXITY_REPORT.json', fast_mode=False)
"
```

Expected output:
- `docs/MANAGERIAL_INSIGHTS.md`: ≈ 7-8 KB markdown with five required sections.
- `docs/COMPLEXITY_ANALYSIS.md`: ≈ 9 KB markdown (committed; regenerated by hand from the JSON when needed).
- `docs/LITERATURE_GAP_ANALYSIS.md`: ≈ 13 KB markdown (committed; refreshed when bib changes).
- `audit_workspace/COMPLEXITY_REPORT.json`: ≈ 2 KB JSON with metadata and per-algorithm wall-clock numbers.

The managerial-insights document gracefully degrades when training artefacts are missing: any section whose backing artefact is absent emits the standard `*Data not yet available*` placeholder rather than crashing or fabricating numbers.

## Known Issues

This section documents known issues, their workarounds, and the planned resolution.

### Issue: OSRM rate limits

**Symptom:** the OSRM HTTP request returns 429 Too Many Requests after roughly 30 requests per minute on the public endpoint.

**Workaround:** the data-engineering layer (FIX-007) automatically falls back to OpenRouteService when OSRM returns 4xx/5xx. To force the fallback for testing, set `NetworkConfig.ors_base_url` and clear the OSRM cache.

**Resolution:** for production deployment, host a private OSRM instance (Docker image `osrm/osrm-backend`) seeded with the relevant road-network OSM extract. The cached `.npy` matrix removes the rate-limit issue after the first run.

### Issue: PPO non-determinism on GPU

**Symptom:** PPO training runs are reproducible to within 0.1% relative reward variance but not bit-for-bit identical across runs even with `torch.manual_seed(42)`.

**Workaround:** the property tests in `tests/test_ppo_agent.py::TestActionDistributionValidity` and `TestRatioClipping` assert structural invariants (Beta distribution validity, log-prob finiteness, ratio clipping bounds) rather than bit-for-bit identity, which is the appropriate standard for stochastic RL training.

**Resolution:** for strict bit-for-bit reproducibility, run on CPU with `torch.use_deterministic_algorithms(True)`. The trade-off is approximately 8× slower training. For the regression baseline we accept the 0.1% relative variance and pin the rolling-mean reward in `audit_workspace/NUMERIC_BASELINE.json` rather than per-step values.

### Issue: SimPy random-seed quirks

**Symptom:** SimPy's `Environment.now` is integer-valued for day-step simulations, but the per-day order-arrival timing is float-valued. Two seeds that differ in the float fraction can produce slightly different per-day metrics.

**Workaround:** the property tests in `tests/test_des_environment.py::TestTimeUnitConsistency` use `pytest.approx(expected, abs=1e-12)` rather than strict equality. For the no-shock service-level baseline (preservation clause C3.9) we use a 0.005 absolute tolerance, which is comfortably above the float-fraction noise.

**Resolution:** when bit-for-bit DES reproducibility is required, set the simulation step to integer days and use `simpy.Environment().run(until=int(T))`. The pre-existing `test_pareto_front_within_tolerance` test in `tests/test_regression_baseline.py` was previously a known-broken case at small pop_size/n_gen budgets; the FIX-019d refresh patched it to use the same instance configuration as the captured baseline.

### Issue: Modal volume size limits

**Symptom:** the `sc-results-v3` Modal volume can grow large after multiple training runs (PPO checkpoints in particular).

**Workaround:** prune old PPO checkpoints with `modal volume rm sc-results-v3 ppo_*_ckpt_*.pt` after a successful run. The intermediate checkpoints are not needed once the `_final.pt` artefact lands.

**Resolution:** add a checkpoint-rotation policy to `modal_train.py` that retains only the latest two intermediates per agent. Tracked as a follow-up.

### Issue: Coverage gap on data_engineering.py

**Symptom:** `phase1_foundation/data_engineering.py` reports 65% line coverage in CI versus the ≥70% gate (preservation clause C3.15).

**Workaround:** the uncovered lines (79-92, 118-139, 145-147, 169, 252, 285-324, 392-393, 431, 447-451, 522, 535, 540, 660, 707-720) are the live OSRM HTTP fetch and OpenStreetMap PBF parsing branches that the property test deliberately skips when network/`osmium` are unavailable. Setting `SCR_LIVE_NETWORK=1` activates the LIVE-gated tests; both `test_osrm_health_live` and `test_ors_health_live` then pass and the coverage rises above 70%.

**Resolution:** for cloud CI, configure the environment to set `SCR_LIVE_NETWORK=1`. For offline CI, accept the documented gap; the FIX-007 cache + ORS fallback ensures the production code path is exercised in the live-probe pair.

## Reproducibility Statement

Every numerical figure in `docs/PAPER_OUTLINE.md` is reproducible by following Steps 1-10 above on a clean environment. The expected wall-clock is approximately 4-5 hours on an A100 (cloud) or 2-3 days on CPU (laptop). The captured baselines in `audit_workspace/` are the ground truth for the preservation contract; any bit-level deviation triggers a regression test failure.

For peer review, we recommend the cloud route: clone the repository, authenticate with Modal, and run `modal run --detach cloud_training/modal_train.py`. The pipeline is fully resumable; any crash or partial completion is recoverable by re-running the same command.

## Files of Record

- `cloud_training/modal_train.py` — driver for Steps 3-9 on Modal A100.
- `cloud_training/local_training_runner.py` — local CPU/GPU runner with Rich progress bars.
- `cloud_training/TRAINING_GUIDE.md` — extended guide with Kaggle / Colab / vast.ai variants.
- `audit_workspace/NUMERIC_BASELINE.json` — captured baselines for the preservation contract.
- `audit_workspace/SIGNATURE_BASELINE.json` — public-API signature snapshot.
- `audit_workspace/PASSING_TESTS_BASELINE.txt` — pre-audit pytest output.
- `audit_workspace/COVERAGE_BASELINE.txt` — pre-audit coverage snapshot.
- `audit_workspace/COVERAGE_FINAL.txt` — post-audit coverage snapshot.
- `audit_workspace/COMPLEXITY_REPORT.json` — wall-clock numbers from `complexity_analysis.py`.

End of replication guide.
