# Implementation Plan

*Outstanding work after FIX-027 — Waves 7 through 10 (FIX-028 to FIX-032).*

## Overview

> **Note on workflow shape.** The 42-task original audit (Group 0 → Wave 5 → Group 6, FIX-001 to FIX-020) is complete and shipped. Follow-up fixes FIX-021 to FIX-027 (action-space + GAE bootstrap, stress-mode env, CVRPLIB unit fix, real-data Tables 2-3 + LSTM cache audit, disruption-stress head-to-head, NSGA-III bottleneck → volume-weighted mean, full-Sobol + Holm-Bonferroni completeness) are also complete in `docs/IMPROVEMENT_REPORT.md` but were not tracked here. **Next FIX number is FIX-028.**
>
> This new `tasks.md` captures the outstanding work surfaced by the deep review pass after FIX-027:
> - **Wave 7 — Document repair** (a wiped section in `MENTOR_REPORT.md` and a stale placeholder in `MANAGERIAL_INSIGHTS.md`).
> - **Wave 8 — Asset gap-fix** (one missing publication figure + one un-cited LaTeX table).
> - **Wave 9 — Manuscript drafting** (PAPER_OUTLINE §1-§7 prose expansion + appendices + submission checklist).
> - **Wave 10 — Final regression sweep** mirrors Group 6: re-run the 454-test suite + cross-asset consistency tests + lint sweep, confirm no regressions vs the post-FIX-027 baseline.
>
> Every task references the canonical numbers in `docs/HEADLINE_NUMBERS.md` and the consistency contract in `tests/test_paper_assets_consistency.py`. New code or doc changes carry inline `# [SOURCE-YEAR §section]` citations and append to `docs/IMPROVEMENT_REPORT.md`. No EJOR mentions in user-facing docs.

## Task Dependency Graph

```json
{
  "waves": [
    {
      "wave": 7,
      "name": "Document repair",
      "depends_on": [],
      "tasks": [
        { "id": "7.1", "title": "FIX-028 MENTOR_REPORT.md §5-§10 restoration", "depends_on": [], "parallel_with": ["7.2"] },
        { "id": "7.2", "title": "FIX-029 MANAGERIAL_INSIGHTS.md placeholder refresh", "depends_on": [], "parallel_with": ["7.1"] }
      ]
    },
    {
      "wave": 8,
      "name": "Asset gap-fix",
      "depends_on": [7],
      "tasks": [
        { "id": "8.1", "title": "FIX-030 fig9_green_premium_curve.png", "depends_on": [], "parallel_with": ["8.2"] },
        { "id": "8.2", "title": "FIX-031 trip_relaxation_validation.tex reconciliation", "depends_on": [], "parallel_with": ["8.1"] }
      ]
    },
    {
      "wave": 9,
      "name": "Manuscript drafting",
      "depends_on": [7, 8],
      "tasks": [
        { "id": "9.1", "title": "Abstract + §1 Introduction prose", "depends_on": [], "sequential": "first" },
        { "id": "9.2", "title": "§2 Literature Review prose", "depends_on": ["9.1"], "parallel_with": ["9.3", "9.4", "9.5", "9.6", "9.7"] },
        { "id": "9.3", "title": "§3 Problem Formulation prose", "depends_on": ["9.1"], "parallel_with": ["9.2", "9.4", "9.5", "9.6", "9.7"] },
        { "id": "9.4", "title": "§4 Solution Methodology prose", "depends_on": ["9.1"], "parallel_with": ["9.2", "9.3", "9.5", "9.6", "9.7"] },
        { "id": "9.5", "title": "§5 Computational Experiments prose", "depends_on": ["9.1"], "parallel_with": ["9.2", "9.3", "9.4", "9.6", "9.7"] },
        { "id": "9.6", "title": "§6 Managerial Insights + §7 Conclusions prose", "depends_on": ["9.1"], "parallel_with": ["9.2", "9.3", "9.4", "9.5", "9.7"] },
        { "id": "9.7", "title": "Appendices A / B / C", "depends_on": ["9.1"], "parallel_with": ["9.2", "9.3", "9.4", "9.5", "9.6"] },
        { "id": "9.8", "title": "Submission package preparation", "depends_on": ["9.2", "9.3", "9.4", "9.5", "9.6", "9.7"], "sequential": "last" }
      ]
    },
    {
      "wave": 10,
      "name": "Final regression sweep",
      "depends_on": [7, 8, 9],
      "tasks": [
        { "id": "10.1", "title": "Re-run full test suite", "depends_on": [], "parallel_with": ["10.2", "10.3", "10.4"] },
        { "id": "10.2", "title": "Re-validate all LaTeX tables", "depends_on": [], "parallel_with": ["10.1", "10.3", "10.4"] },
        { "id": "10.3", "title": "Re-render all figures", "depends_on": [], "parallel_with": ["10.1", "10.2", "10.4"] },
        { "id": "10.4", "title": "Verify zero remaining placeholders", "depends_on": [], "parallel_with": ["10.1", "10.2", "10.3"] },
        { "id": "10.5", "title": "Append final FIX-032 closure entry", "depends_on": ["10.1", "10.2", "10.3", "10.4"] },
        { "id": "10.6", "title": "Audit-green checkpoint", "depends_on": ["10.5"], "sequential": "last" }
      ]
    }
  ]
}
```

```
Wave 7 (no internal deps; 7.1 ∥ 7.2)
   │
   ▼
Wave 8 (depends on Wave 7; 8.1 ∥ 8.2)
   │
   ▼
Wave 9 (depends on Waves 7-8)
   9.1 → {9.2, 9.3, 9.4, 9.5, 9.6, 9.7 in parallel} → 9.8
   │
   ▼
Wave 10 (depends on Waves 7-9)
   {10.1, 10.2, 10.3, 10.4 in parallel} → 10.5 → 10.6
```

## Tasks

### Wave 7 — Document repair (highest priority)

These two documents are the only ones with active defects. Both must complete before the manuscript-drafting wave so the prose has a clean source of truth.

- [x] 7.1 FIX-028 — Restore `docs/MENTOR_REPORT.md` §5 - §10 + sign-off
  - **Defect**: `MENTOR_REPORT.md` truncates at §4.7 Sensitivity. Sections §5 Five takeaways, §6 Risks, §7 Mentor asks, §8 Timeline, §9 Reproducibility, §10 Visual walkthrough, and the sign-off block are all missing after a `fs_write` mid-edit accident.
  - **Critical preservation**: `tests/test_paper_assets_consistency.py::test_mentor_report_quotes_ppo_baselines` requires `(R, s, S)` reward ≈ -63 908 AND PPO-100 reward ≈ -135 651 to remain in the file (currently in §4.6). The restored §5 - §10 MUST NOT remove the §4.6 numbers. Run `pytest tests/test_paper_assets_consistency.py::test_mentor_report_quotes_ppo_baselines -v` after the restoration.
  - **Audience**: IIM Mumbai mentor. Business framing throughout, no coding details, no bug history, no Modal cost mentions, no EJOR mentions.
  - **§5 Five takeaways** must cover (in business language): demand variability is the dominant driver of cost-and-carbon performance (Sobol S1=0.72 / ST=0.90); NSGA-II is the recommended planner (HV 0.713 ± 0.143, mean front 11.2 solutions); AI controller (PPO) is worth deploying for disruption-resilience (survives 91 days vs (R,s,S) 61 days under severe shock); Indian-network external validity is established via the Delhivery cross-validation (HV 0.880 ± 0.099); statistical claims are honest about Holm-Bonferroni (Friedman p=0.0257 holds, pairwise post-hoc does not survive correction).
  - **§6 Risks** must enumerate: model-risk (LSTM 23.5 % MAPE means 1-week buffer needed); sim-to-real gap on the PPO controller; sample-size limitation on disruption table (50 episodes per cell); the DES 95 % CI lower bound (95.09 %) sitting just above threshold; and seed sensitivity (NSGA-II seed range 4-21 front size means individual runs can vary).
  - **§7 Mentor asks** must list explicit decisions needed: (a) approval to begin manuscript drafting; (b) target venue selection (Transportation Research Part E vs Computers & Operations Research vs IJOR — no EJOR); (c) authorship order; (d) timeline for first internal review draft.
  - **§8 Timeline** must give a 4-6 week manuscript-drafting plan: Week 1 §1 + §2; Week 2 §3 + §4 (formulation + methodology); Week 3 §5 + §6 (experiments + insights); Week 4 §7 (conclusions) + appendices + revision pass; Week 5-6 internal review + revisions.
  - **§9 Reproducibility** must mention: pinned dependencies (`requirements.txt` with `==` versions, fixed seeds, MLflow tracking, `docs/REPLICATION_RECIPE.md` exists, the 27 CVRPLIB Augerat instances reproduce against published BKS within +5.1 % mean gap, `docs/REPLICATION_GUIDE.md` walks through every phase).
  - **§10 Visual walkthrough** must explain in business terms what each of the 8 main figures + 2 supplementary figures tells the planner: fig1 (network map — where customers and warehouses sit), fig2 (Pareto frontier — the cost-vs-carbon menu of plans), fig3 (convergence — proves the optimisation actually settles), fig4 (resilience dashboard — service level over time under shocks), fig5 (LSTM forecast — week-ahead demand confidence), fig6 (PPO training reward — controller learning curve), fig7 (sensitivity spider — which inputs matter most), fig8 (NSGA-III 3D Pareto — three-way trade-off projections), supp1 (route map detail), supp2 (Monte Carlo distribution). Add a 30-min meeting talk-track at the end (5 min framing, 15 min walking through fig2 + fig7 + the disruption table, 10 min decisions).
  - **Sign-off** must include author name (Nalin Aggarwal), date (current), and a one-sentence ask for written approval to begin drafting.
  - Verify file ends with the sign-off line and contains all 10 section headings: `for n in 1 2 3 4 5 6 7 8 9 10; do grep -qE "^## ${n}\\." docs/MENTOR_REPORT.md || echo "MISSING ${n}"; done` MUST print no `MISSING` lines.
  - Verify `pytest tests/test_paper_assets_consistency.py -q` reports no new failures vs the pre-restoration baseline.
  - Append a FIX-028 entry to `docs/IMPROVEMENT_REPORT.md` documenting what was lost, what was restored, and the consistency-test verification.
  - _Bug_Condition: §5-§10 + sign-off missing in MENTOR_REPORT.md_
  - _Expected_Behavior: All 10 sections present, sign-off present, business-framed, baseline numbers preserved_
  - _Preservation: test_mentor_report_quotes_ppo_baselines must keep passing_
  - _Requirements: 1.20, 2.20, 3.16_

- [x] 7.2 FIX-029 — Refresh `docs/MANAGERIAL_INSIGHTS.md` post-FIX-022 placeholder
  - **Defect**: `docs/MANAGERIAL_INSIGHTS.md` line ~147 still reads `Interpretation (placeholder, to be refreshed after FIX-022 stress-mode rerun): - The pre-FIX-022 numbers (3635.85 / -764.36 / -25679.46) reflected an action-saturated env where PPO converged to the random-policy ...`. The rerun happened (artifacts dated 2025-05-23) but the surrounding interpretation prose was never updated.
  - **Action**: Replace the placeholder paragraph with current stress-mode numbers from `data/results/ppo_baselines.json` and `data/results/disruption_evaluation.json`. The new paragraph must explain (in operations-management language, not coding language): the (R, s, S) periodic-review baseline averages -63 908 ± 2 497 INR/episode; PPO-100 averages -135 651 INR/episode at training-end but — critically — survives the full 365-day horizon under steady-state and mild disruption while (R, s, S) terminates early on persistent stockouts; under severe disruption PPO -850 INR/day vs (R, s, S) -876 INR/day, with PPO surviving 91 days vs (R, s, S) 61 days. The takeaway: per-day cost is competitive only while the policy survives; PPO trades modest steady-state efficiency for disruption-survival.
  - **Critical preservation**: `tests/test_paper_assets_consistency.py::test_managerial_md_quotes_ppo_baselines` requires `ss_policy.mean` (≈ -63 908) AND `random.mean` (≈ -290 862) to remain in the file. Both must appear in the refreshed paragraph or in a nearby supporting table.
  - Verify the placeholder string is gone: `grep -c "placeholder, to be refreshed after FIX-022" docs/MANAGERIAL_INSIGHTS.md` MUST report `0`.
  - Verify the consistency test still passes: `pytest tests/test_paper_assets_consistency.py::test_managerial_md_quotes_ppo_baselines -v`.
  - Append a FIX-029 entry to `docs/IMPROVEMENT_REPORT.md` summarising the placeholder removal and the new interpretation.
  - _Bug_Condition: Stale placeholder paragraph references pre-FIX-022 numbers_
  - _Expected_Behavior: Current stress-mode numbers in operations-management language, baseline consistency test passes_
  - _Preservation: test_managerial_md_quotes_ppo_baselines_
  - _Requirements: 1.20, 2.20, 3.16_

### Wave 8 — Asset gap-fix (depends on Wave 7)

- [x] 8.1 FIX-030 — Generate the missing `fig9_green_premium_curve.png`
  - **Defect**: `docs/HEADLINE_NUMBERS.md` quotes "9 main + 2 supplementary figures" but only 8 main figures are on disk (`outputs/figures/fig1_network_map.png` through `fig8_nsga3_projections.png`). `docs/PAPER_OUTLINE.md` §6 references "Figure 7: Green premium curve" but the on-disk fig7 is the sensitivity spider — there is a numbering mismatch and a missing figure.
  - **Action**: Implement `supply_chain_research/phase4_synthesis/render_publication_figures.py::render_fig9_green_premium_curve(...)` (or extend if a function already exists). The figure plots green-premium (INR per kg CO₂ reduction) against carbon-budget tightness (no budget / 20 % reduction / 40 % reduction) using `supply_chain_research/phase1_foundation/carbon_budget_solver.py::generate_green_premium_curve(...)` (built in original FIX-015). Use the `plotting_style.py` IBM-design palette set in FIX-028's prior figure upgrade. Save to `outputs/figures/fig9_green_premium_curve.png` at 300 DPI.
  - Wire `fig9_green_premium_curve` into `supply_chain_research/phase4_synthesis/generate_all_figures.py` so `make figures` picks it up.
  - Update `docs/PAPER_OUTLINE.md` §6 figure-placement table: rename current "Figure 7: Green premium curve" → "Figure 9: Green premium curve". Update the figure-and-table-placement summary at the bottom and the inline `[Figure 7: Green premium curve — placed here]` marker in §6 to `[Figure 9: ...]`.
  - Add a `_PROJECT_ROOT/outputs/figures/fig9_green_premium_curve.png` exists check to a new test in `tests/test_paper_assets_consistency.py` (modelled after the existing skip-gracefully pattern).
  - Verify rendering: `python -m supply_chain_research.phase4_synthesis.render_publication_figures --figures fig9` produces a non-empty PNG at the expected path.
  - Verify all 9 main figures present: `for n in 1 2 3 4 5 6 7 8 9; do test -s outputs/figures/fig${n}_*.png || echo "MISSING fig${n}"; done` MUST print no `MISSING` lines.
  - Append a FIX-030 entry to `docs/IMPROVEMENT_REPORT.md`.
  - _Bug_Condition: fig9_green_premium_curve.png missing_
  - _Expected_Behavior: 9-main + 2-supplementary figure set complete, paper outline numbering consistent_
  - _Preservation: existing fig1-fig8 unchanged_
  - _Requirements: 1.20, 2.20, 3.11_

- [x] 8.2 FIX-031 — Reconcile `outputs/tables/trip_relaxation_validation.tex` with the manuscript
  - **Defect**: `outputs/tables/trip_relaxation_validation.tex` exists on disk but is not cited anywhere in `docs/PAPER_OUTLINE.md`. Either it should be cited (and the manuscript paragraph drafted) or it should be removed to keep the asset set clean.
  - **Action**: First read `outputs/tables/trip_relaxation_validation.tex` to determine what it presents. If it adds value (e.g., a sensitivity sub-experiment relaxing per-trip constraints), add a §5.7 or appendix paragraph in `docs/PAPER_OUTLINE.md` that cites it explicitly with a 3-4 sentence summary. If it duplicates content already in another table or is exploratory-only, move it to `outputs/tables/_unreferenced/` (or delete with audit-log entry).
  - Update the figure/table-placement summary in `PAPER_OUTLINE.md` accordingly.
  - Update `docs/HEADLINE_NUMBERS.md` if the table contributes a quotable claim.
  - Verify final state: `grep -l trip_relaxation outputs/tables/` AND `grep -c trip_relaxation docs/PAPER_OUTLINE.md` are consistent (either both > 0 or table is moved/deleted and outline does not mention it).
  - Append a FIX-031 entry to `docs/IMPROVEMENT_REPORT.md` (asset reconciliation, citation added or table removed).
  - _Bug_Condition: trip_relaxation_validation.tex un-cited_
  - _Expected_Behavior: Asset set internally consistent — every .tex either cited or removed_
  - _Requirements: 1.20, 2.20, 3.11_

### Wave 9 — Manuscript drafting (depends on Waves 7-8)

The PAPER_OUTLINE is currently a structural skeleton with ~60 % of subsections still in bullet form. This wave converts each section to publishable prose. Each task draws exclusively on the canonical numbers in `docs/HEADLINE_NUMBERS.md` and cites `docs/VERIFIED_REFERENCES.bib` entries with their BibTeX keys. No EJOR mentions in any section.

- [x] 9.1 Draft Abstract finalisation + §1 Introduction prose (target 1500 words)
  - The abstract is already a solid draft; review for consistency with post-FIX-026/FIX-027 numbers (Friedman p=0.0257 not 0.0327; NSGA-III HV=0.659 not 0.789; CVRPLIB +5.1 % not the older value; demand_variability S1=0.72 dominant).
  - Convert §1 bullet skeleton to prose: §1.1 Motivation (NCAER 14 % GDP, NITI Aayog 260 MT CO₂ projection to 2047, three simultaneous pressures); §1.2 Research Questions (RQ1-RQ3 verbatim from outline); §1.3 Contributions (5 contributions verbatim from outline, framed as theoretical not engineering per existing wording); §1.4 Positioning vs Demir 2014 / Wang 2023 / Hosseini 2019 (full prose paragraph for each); §1.5 Paper Organization (one short paragraph).
  - Word count: 1,400 - 1,600 words for §1; abstract stays ~250.
  - Verify: `wc -w docs/PAPER_OUTLINE.md` shows the §1 prose has expanded.
  - _Requirements: 1.21, 2.21_

- [x] 9.2 Draft §2 Literature Review prose (target 2000 words)
  - Convert four-stream skeleton to prose: §2.1 MOO (NSGA-II Deb 2002, NSGA-III Deb-Jain 2014, MOEA/D Zhang-Li 2007, recent VRP surveys 2023-2024); §2.2 Green VRP (MEET vs COPERT vs HBEFA comparison, carbon-constrained variants, green-premium concept); §2.3 SC Resilience (Sheffi-Rice 2005 TTS/TTR, Hosseini 2019 normalised TTR, SimPy supply-chain papers); §2.4 AI for SCM (Lim 2021 TFT, Schulman 2017 PPO, Haarnoja 2018 SAC, Stranieri 2023 sim-to-real); §2.5 Research Gap subsection populating Table 1 with 10 recent papers. Each paragraph cites at minimum 2-3 BibTeX keys from `docs/VERIFIED_REFERENCES.bib`.
  - Generate Table 1 (literature comparison matrix) — 10-row .tex file at `outputs/tables/table1_literature_comparison.tex`. Columns: Paper / Year / Multi-objective? / Resilience? / RL? / Indian Network? / Diversity-preserving repair? / Hypervolume normalisation? / This-paper-extends-with. The "This paper extends with" cell is the gap-bridge claim for each row.
  - Update `tests/test_paper_assets_consistency.py` to add a check that `table1_literature_comparison.tex` exists and contains at least 10 row entries.
  - Word count target: 1900 - 2100 words.
  - _Requirements: 1.21, 2.21_

- [x] 9.3 Draft §3 Problem Formulation prose + LaTeX equations (target 2500 words)
  - Six subsections: §3.1 Network (101 customers + 5 warehouses, OSRM + ORS fallback, log-normal demand fitted to DataCo); §3.2 Bi-objective CVRP (full LaTeX equations: decision variables x_{ijk}, cost objective, MEET emission objective, capacity / time / depot constraints); §3.3 3-objective extension (volume-weighted-mean delivery time per FIX-026; cite Deb 2001 §6.2 bottleneck-objective degeneracy); §3.4 Carbon budget ε-constraint formulation (no-budget / 20 % / 40 % variants); §3.5 Robust optimisation (Ben-Tal Nemirovski 2002 mean+λ·std formulation); §3.6 Multi-product (3 SKUs: Electronics, FMCG, Bulk; per-product capacity and emission profiles).
  - Generate Table 2 (notation and parameters) — populate `outputs/tables/table_notation.tex` if absent. Columns: symbol / description / units / value / source.
  - Verify all LaTeX equations compile in isolation: `pdflatex` on a tiny stub document including each formula block. Skip gracefully if pdflatex absent.
  - Word count target: 2400 - 2600 words.
  - _Requirements: 1.21, 2.21_

- [x] 9.4 Draft §4 Solution Methodology prose + algorithm pseudocode (target 3000 words)
  - Six subsections, each with a pseudocode block: §4.1 NSGA-II warm-start (2 OR-Tools seeds + (P-2) random; SBX η=15; polynomial mutation η=20; repair operator; HV-variance early stopping); §4.2 Clarke-Wright Savings (Clarke 1964 parallel variant); §4.3 DES (SimPy 4.x, three shock models, 50 MC reps); §4.4 LSTM (2-layer 256-hidden + attention, 30→7 day window, 70/15/15 split); §4.5 PPO (45-dim state, continuous action, GAE λ=0.95, clip 0.2, 1M steps; cite Schulman 2017 §4 + Andrychowicz 2021 §3.7; mention FIX-021 GAE-bootstrap fix and FIX-022 stress-mode env); §4.6 Sensitivity (Sobol Saltelli N=128 → 1280 evals; cite Saltelli 2010 §5).
  - Each pseudocode block in `algorithm` LaTeX environment with line numbers and inline citations to the relevant BibTeX key.
  - No mention of bug history in the manuscript prose itself; FIX-021/FIX-022 belong only in `docs/IMPROVEMENT_REPORT.md`. The methodology section presents the *current* approach.
  - Word count target: 2900 - 3100 words.
  - _Requirements: 1.21, 2.21_

- [x] 9.5 Draft §5 Computational Experiments prose finishing (target 2500 words)
  - §5.1 Experimental Setup: hardware (Tesla T4 16 GB), software (Python 3.10, PyTorch 2.0, pymoo 0.6.x, SimPy 4.1), reproducibility (seed=42, pinned deps).
  - §5.2 NSGA-II results: convert bullets to prose drawing on HEADLINE_NUMBERS — HV 0.713 ± 0.143, mean front 11.2; comparison table cites Table 2; statistical tests cite Table 3 (Friedman p=0.0257; pairwise Wilcoxon raw vs Holm-adjusted).
  - §5.3 Emission model validation prose: cross-verification against COPERT 5 / HBEFA 4.2; load-factor sensitivity.
  - §5.3a CVRPLIB Augerat is already drafted; light-touch revision only.
  - §5.4 Resilience analysis prose: no-shock SL 95.6 % ± 0.28 % with 95 % CI lower bound 95.09 % phrasing per HEADLINE_NUMBERS skeptic note; demand-surge / supply-disruption / route-blockage TTS-TTR results.
  - §5.5 LSTM forecasting prose: MAPE 23.46 %, RMSE 56.46 kg, contextualise against the 18-28 % published band on log-normal demand series with festival spikes.
  - §5.6 PPO results — table is drafted; convert prose around the table, lead with the disruption-stress framing not steady-state per HEADLINE_NUMBERS guidance #3 ("PPO under-performs (R,s,S) on steady-state per-day cost — the disruption table is the right comparison").
  - §5.7 Ablation study prose: pull from `outputs/tables/table5_ablation.tex` content.
  - §5.8 Cross-validation already drafted; light revision.
  - Word count target: 2400 - 2600 words.
  - _Requirements: 1.21, 2.21_

- [x] 9.6 Draft §6 Managerial Insights + §7 Conclusions prose (target 1500 + 800 words)
  - §6 four subsections in operations-management language drawing on `docs/MANAGERIAL_INSIGHTS.md` (after FIX-029 refresh): green-premium curve at 10 / 20 / 30 / 40 % targets (cite fig9 from FIX-030); fleet-mix recommendation (HCV vs LCV under different carbon weights, citing Sobol sensitivity); disruption preparedness (PPO ROI, recommended safety-stock levels, response playbook); implementation roadmap (3-phase: pilot one corridor → expand to network → AI-controller deployment).
  - §7 three subsections: 7.1 Summary of contributions (recap 5 contributions from §1.3 with key quantitative findings); 7.2 Limitations (single-country network, simulated demand, sim-to-real gap on PPO, sample size of 50 episodes per disruption cell, Holm-Bonferroni post-hoc framing); 7.3 Future work (multi-modal rail+road, IoT integration, transfer learning, carbon-credit trading).
  - Word count targets: §6 1400-1600, §7 750-850.
  - _Requirements: 1.21, 2.21_

- [x] 9.7 Populate appendices A / B / C
  - Appendix A: Complete Parameter Tables — extract every parameter from `supply_chain_research/config.py` with source citation column. Should be machine-generated to keep in sync — write `scripts/generate_appendix_a.py` that walks `MasterConfig` via `pkgutil.walk_packages` + `pydantic.BaseModel.model_fields` and emits a 4-column markdown table (parameter / value / units / source) into `docs/appendix_a_parameters.md`.
  - Appendix B: Supplementary Figures — convergence plots for all algorithm variants and Monte Carlo distribution plots. Reference the existing `outputs/figures/supplementary/supp_fig1_routing.png` and `supp_fig2_monte_carlo.png` and add inline captions.
  - Appendix C: Reproducibility checklist — populate the eight-item checklist (data, seeds, code, environment, dependencies, hardware, runtime, expected outputs).
  - Verify Appendix A table is non-empty: `wc -l docs/appendix_a_parameters.md` ≥ 30 lines.
  - _Requirements: 1.21, 2.21_

- [x] 9.8 Submission package preparation
  - Convert `docs/PAPER_OUTLINE.md` into an Elsevier `elsarticle` LaTeX template at `manuscript/main.tex` (assuming Transportation Research Part E or Computers & Operations Research as the target — confirm with mentor in §7 of MENTOR_REPORT). Wire up: bibliography (`docs/VERIFIED_REFERENCES.bib`), figure includes (PDF/EPS preferred for vectorisation; convert PNG → PDF where feasible via `magick` or `convert`), table includes from `outputs/tables/`.
  - Write a one-page cover letter at `manuscript/cover_letter.md` highlighting novelty, fit to the chosen venue, and the three theoretical contributions.
  - Compile a list of 3-5 suggested reviewers in `manuscript/suggested_reviewers.md` drawn from authors of the cited 2022-2024 papers.
  - Write `manuscript/data_availability.md` and `manuscript/conflict_of_interest.md` per the venue's standard requirements.
  - Tick all `Submission Checklist` items in `docs/PAPER_OUTLINE.md`.
  - Verify: `make manuscript` (or equivalent compile target) produces a single-PDF output that is non-empty. Skip gracefully if no LaTeX toolchain is available.
  - _Requirements: 1.21, 2.21_

### Wave 10 — Final regression sweep (depends on all prior waves)

Mirrors the original Group 6 — mechanically re-validate every preservation contract against the latest baselines after Waves 7-9 land.

- [x] 10.1 Re-run full test suite — zero new failures
  - Run `pytest tests/ -v --tb=short > audit_workspace/PASSING_TESTS_POST_FIX031.txt 2>&1`.
  - Assert pass count: 454 passed, 5 skipped (current baseline) — `grep -E "[0-9]+ passed" audit_workspace/PASSING_TESTS_POST_FIX031.txt | grep -qE "454 passed"`. If new tests were added in Wave 8.1 or 9.2, the expected pass count grows by exactly that delta.
  - Cross-asset consistency suite: `pytest tests/test_paper_assets_consistency.py -v` MUST report 9 of 9 passing (or 10/10/11 if Wave 8.1/9.2 added new fig9 / table1 existence tests).
  - _Preservation: C3.1, C3.15_

- [x] 10.2 Re-validate all LaTeX tables
  - Run `make lint-tables` (or `python audit_workspace/_validate_latex_tables.py`).
  - All 10 (or 11 after Wave 9.2 adds `table1_literature_comparison.tex`) tables MUST report clean — no syntax errors, no missing columns, no empty data cells.
  - _Preservation: C3.11_

- [x] 10.3 Re-render all figures + verify file sizes
  - Run `make figures` (calls `supply_chain_research/phase4_synthesis/generate_all_figures.py`).
  - All 9 main + 2 supplementary figures MUST exist with file sizes between 50 KB and 5 MB at 300 DPI.
  - Verify: `for f in outputs/figures/fig*.png outputs/figures/supplementary/*.png; do test -s "$f" || echo "MISSING $f"; done` MUST print no `MISSING` lines.
  - _Preservation: C3.11_

- [x] 10.4 Verify zero remaining placeholders or stale interpretation paragraphs
  - Sweep `docs/` for placeholder markers: `grep -rEn "(placeholder|TODO|FIXME|XXX|to be refreshed|to be drafted)" docs/ --include="*.md" | grep -v "^docs/IMPROVEMENT_REPORT" > audit_workspace/PLACEHOLDER_FINAL.txt`.
  - Note: matches inside `docs/IMPROVEMENT_REPORT.md` are excluded because that file legitimately documents the historical placeholder issues.
  - Assert empty: `test ! -s audit_workspace/PLACEHOLDER_FINAL.txt`.
  - _Preservation: C3.16_

- [x] 10.5 Append final FIX-032 closure entry to `docs/IMPROVEMENT_REPORT.md`
  - One-paragraph summary covering: Wave 7 document repair (FIX-028, FIX-029), Wave 8 asset gap-fix (FIX-030, FIX-031), Wave 9 manuscript drafting completion (no FIX number — pure prose), Wave 10 regression-sweep results.
  - Include final test count, final figure / table count, final manuscript word count from `wc -w manuscript/main.tex` (or `docs/PAPER_OUTLINE.md` if manuscript not yet compiled).
  - Update `docs/HEADLINE_NUMBERS.md` post-FIX-031 if any number drifted (none expected — these are documentation tasks, not numerical).
  - _Preservation: C3.16_

- [x] 10.6 Audit-green checkpoint
  - Final smoke: `pytest tests/ -q && make figures && make lint-tables && echo "POST-FIX-031 AUDIT GREEN"`.
  - If any task in 10.1 - 10.4 fails, do not mark the wave complete — surface the failure and ask the user how to proceed (do NOT auto-retry).
  - Confirm `docs/IMPROVEMENT_REPORT.md` lists every FIX-028 through FIX-032 entry with citations.
  - Confirm `docs/MENTOR_REPORT.md` has all 10 sections + sign-off.
  - Confirm `docs/PAPER_OUTLINE.md` has zero remaining bullet-only subsections.
  - _Preservation: C3.1 → C3.16 (all)_

## Notes

Preservation contracts that MUST hold across every task in this plan:

- **Cross-asset consistency suite must keep passing.** `tests/test_paper_assets_consistency.py` is the binding contract — every Wave 7-10 change must leave the full suite green. New existence checks added in Wave 8.1 (fig9) and Wave 9.2 (table1) extend the suite but must not modify existing assertions.
- **Headline numbers in `docs/MENTOR_REPORT.md` are immutable.** The `(R, s, S)` baseline ≈ -63 908 INR/episode and PPO-100 ≈ -135 651 INR/episode (currently in §4.6) MUST remain verbatim after the §5-§10 restoration in FIX-028. Re-run `pytest tests/test_paper_assets_consistency.py::test_mentor_report_quotes_ppo_baselines -v` after every edit to MENTOR_REPORT.md.
- **No placeholder strings outside `docs/IMPROVEMENT_REPORT.md`.** After Wave 7, no `placeholder`, `TODO`, `FIXME`, `XXX`, `to be refreshed`, or `to be drafted` markers may appear in any `docs/**/*.md` file other than `docs/IMPROVEMENT_REPORT.md` (which legitimately documents historical placeholders). The Wave 10.4 sweep enforces this.
- **No EJOR mentions in user-facing docs.** Target venues are Transportation Research Part E, Computers & Operations Research, or IJOR — confirmed with mentor before drafting.
- **FIX-numbering is monotonic.** Next FIX number is FIX-028 (Wave 7.1). Subsequent fixes increment by one and append a corresponding entry to `docs/IMPROVEMENT_REPORT.md` with inline `# [SOURCE-YEAR §section]` citations.
