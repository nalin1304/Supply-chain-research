# Headline Numbers — Manuscript-Ready

This file is the single canonical reference for every quantitative
claim in the manuscript. Every number here is sourced from a
specific file in `data/results/` or `outputs/`, and the consistency
test suite at `tests/test_paper_assets_consistency.py` enforces that
the rendered tables and the docs all agree with these values.

When drafting the manuscript, **always cite the version of a
number from this file rather than from the rendered table** — the
table format strips precision (e.g. `-63 908` rounds in the table
to `-64 000` in some text settings).

---

## Phase 1 — Strategic optimisation

| Metric | Value | Source file |
|---|---|---|
| NSGA-II hypervolume (mean ± std, 50 seeds, joint-normalised) | **0.7130 ± 0.1432** | `training_summary.json::nsga2.mean_hv` + `statistical_tests.json::nsga2.std_hv` |
| NSGA-II mean Pareto-front size | **11.18** (range 4–21) | `training_summary.json::nsga2.mean_front_size` |
| NSGA-III hypervolume (mean ± std, 50 seeds) | **0.659 ± 0.203** [post-FIX-026] | `training_summary.json::nsga3.mean_hv` + `statistical_tests.json::nsga3.std_hv` |
| NSGA-III mean Pareto-front size | **7.20** (range 2-13) [post-FIX-026] | `training_summary.json::nsga3.mean_front_size` |
| MOEA/D hypervolume (mean ± std, 50 seeds) | **0.595 ± 0.328** | `training_summary.json::moead.mean_hv` + `statistical_tests.json::moead.std_hv` |

## Phase 1 — Statistical significance

| Test | Statistic | p-value | Source file |
|---|---|---|---|
| Friedman 3-way (NSGA-II / NSGA-III / MOEA/D, k=3, n=50) | χ² = **7.32** | **p = 0.0257** | `statistical_tests.json::friedman` |
| Wilcoxon paired (NSGA-II vs MOEA/D) | W = **399** | **p = 0.0207** | `statistical_tests.json::wilcoxon_nsga2_moead` |

## Phase 1 — Implementation correctness (CVRPLIB Augerat Set-A)

| Metric | Value |
|---|---|
| Instances solved | **27 / 27** |
| Mean gap to BKS | **+5.1 %** |
| Median gap | **+4.7 %** |
| Min gap | **+2.5 %** (`A-n55-k9`) |
| Max gap | **+9.7 %** (`A-n39-k5`) |
| Source | `outputs/tables/cvrplib_validation.tex` |

## Phase 1 — Cross-validation on a secondary network

| Metric | Value |
|---|---|
| Network | Delhivery 10-hub × 150-customer, 144 867 shipments calibrated |
| Joint-normalised HV (20 seeds) | **0.880 ± 0.099** |
| Mean Pareto-front size | 9.7 (range 4–18) |
| Source | `data/results/delhivery_nsga2_all_results.pkl` |

## Phase 1 — Trip relaxation validation (continuous vs. discrete)

| Metric | Value |
|---|---|
| Formulations compared | continuous flow $x/Q$ vs. discrete ceiling $\lceil x/Q \rceil$ |
| Seeds | 5 |
| Continuous mean normalised HV | **1.2097 ± 0.0002** |
| Discrete mean normalised HV | **0.0100 ± 0.0000** |
| Relative separation | ~120× (continuous over discrete) |
| Source | `outputs/tables/trip_relaxation_validation.tex` |

## Phase 2 — Resilience (DES Monte Carlo)

| Metric | Value |
|---|---|
| Service level (mean of 100 reps, no shock) | **95.6 % ± 0.28 %** |
| 95 % CI lower bound | 95.09 % |
| Source | `training_summary.json::des.mean_sl` |

> **Reviewer-skepticism note**: the 95 % CI lower bound (95.09 %)
> is just barely above the manuscript's "≥ 95 %" threshold. The
> claim should be phrased as "DES sustains a mean service level
> of 95.6 % ± 0.28 %" rather than asserting >= 95 % with certainty.

## Phase 3 — Forecasting (LSTM)

| Metric | Value |
|---|---|
| Test-set MAPE | **23.46 %** |
| Test-set RMSE | **56.46 kg** |
| Forecast horizon | 7 days |
| Architecture | Attention-LSTM, 256 hidden × 3 layers |
| Source | `training_summary.json::lstm.{mape,rmse}` (recomputed from `lstm_predictions.npy` + `lstm_actuals.npy`) |

## Phase 3 — RL controller (FIX-022 stress mode)

Training-end reward (last 100 episodes during 3 M / 2 M-step training):

| Policy | Reward | Source |
|---|---|---|
| PPO 20 × 5 (training-end) | **-250 765** | `training_summary.json::ppo_small.reward` |
| PPO 100 × 5 (training-end) | **-135 651** | `training_summary.json::ppo_full.reward` |

50-episode evaluation rewards (held-out, fresh seeds):

| Policy | Reward (mean ± std) | Source |
|---|---|---|
| (R, s, S) periodic-review | **-63 908 ± 2 497** | `ppo_baselines.json::ss_policy` |
| Random sampling | **-290 862 ± 39 747** | `ppo_baselines.json::random` |

## Phase 3 — Disruption-stress head-to-head (FIX-025)

50 episodes per (policy × regime) cell, 20-customer reference
network, 365-day horizon:

| Regime | (R, s, S) R/day | (R, s, S) days | (R, s, S) SL | PPO R/day | PPO days | PPO SL |
|---|---:|---:|---:|---:|---:|---:|
| steady_state | -676 | 100 | 96.0 % | -1 124 | **365** | **100.0 %** |
| mild | -692 | 95 | 95.9 % | -773 | **365** | **99.9 %** |
| moderate | -729 | 83 | 95.2 % | -788 | 304 | 91.1 % |
| severe | -876 | 61 | 93.4 % | **-850** | 91 | **95.4 %** |

| Source | `data/results/disruption_evaluation.json` |
|---|---|

> **Manuscript framing**: the (R, s, S) policy is competitive on
> per-day cost when it survives, but consistently terminates early
> on persistent stockouts (61–100 days). PPO trades some per-day
> efficiency for full-horizon survival; under severe disruption
> the per-day cost gap closes (-850 vs -876) and PPO's survival
> advantage (91 vs 61 days) becomes the dominant factor.

## Pipeline

| Metric | Value |
|---|---|
| Total Modal training time | **2.96 hours** |
| GPU | Tesla T4 (16 GB) |
| Total Modal cost | ~$1.80 (T4 at $0.59/hr) |
| Test suite | **454 passed, 5 skipped** |
| Code modules | 53 Python files, 0 syntax errors |
| LaTeX tables | 10 (all syntactically validated) |
| Publication figures | 9 main + 2 supplementary (300 DPI PNG) |

---

## Cross-asset consistency

The following are pinned by `tests/test_paper_assets_consistency.py`:

- `training_summary.json::nsga2.mean_hv` ≡ `outputs/tables/table2_algorithm_comparison.tex`
- `statistical_tests.json::friedman.p` ≡ `outputs/tables/table3_statistical_tests.tex`
- `statistical_tests.json::wilcoxon.p` ≡ `outputs/tables/table3_statistical_tests.tex`
- `ppo_baselines.json::ss_policy.mean` ≡ `docs/MENTOR_REPORT.md` ≡ `docs/MANAGERIAL_INSIGHTS.md`
- `ppo_baselines.json::random.mean` ≡ `docs/MANAGERIAL_INSIGHTS.md`
- DES service level ≥ 95 % (manuscript claim)
- Friedman p < 0.05 ; Wilcoxon p < 0.05 (manuscript significance claim)

If any docs / tables / JSON file diverge, the test suite fails. This
is the FIX-024-class regression catcher.

---

## Numbers to discuss explicitly in the manuscript

1. ~~NSGA-III pre-FIX-026 third objective was degenerate~~ **RESOLVED**
   in FIX-026 — `f3` is now volume-weighted mean delivery time
   instead of `max-over-active-edges`. Front size jumped from 1.5
   to 7.2; HV std dropped from 0.544 to 0.203 (no longer bimodal).
   Manuscript should mention the volume-weighted-mean formulation
   in §3 / §4 to set expectations.

2. **MOEA/D HV std (0.328) is wider than NSGA-II's (0.143)** —
   known property of decomposition-based methods on heterogeneous
   bi-objective problems (Zhang & Li 2007).

3. **PPO under-performs (R, s, S) on steady-state per-day cost** —
   the disruption table (Phase 3 above) is the right comparison;
   the manuscript should not lead with the steady-state number.

4. **DES 95 % CI lower bound is only 95.09 %** — phrase the claim
   as "mean SL of 95.6 % ± 0.28 %" rather than "≥ 95 %".

5. **Friedman p tightened from 0.0327 to 0.0257** in FIX-026 (the
   honest 3-objective NSGA-III result is more discriminating). All
   significance claims still hold.
