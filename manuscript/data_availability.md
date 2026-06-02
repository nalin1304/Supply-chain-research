# Data Availability Statement

This statement is prepared to comply with the data-availability policy
of *Transportation Research Part E: Logistics and Transportation
Review*.

## Code

The complete source code for the framework, including the four-phase
pipeline (`phase1_foundation`, `phase2_resilience`, `phase3_ai`,
`phase4_synthesis`), the `MasterConfig` pydantic schema, the
`tests/` suite of 488 tests plus 5 skipped, the figure and table
renderers, and the cloud-training scaffolds, is available in the
public repository accompanying this submission. Pinned dependencies
live in `supply_chain_research/requirements.txt`; the complete
reproduction recipe is in `docs/REPLICATION_RECIPE.md` and the
replication walkthrough is in `docs/REPLICATION_GUIDE.md`.

## Data sources and licensing

All input datasets are documented with provenance, version, and
licence in `docs/DATA_SOURCES.md`. The headline sources are:

- **DataCo Smart Supply Chain dataset** (180,519 orders, 20,000
  customers): used to fit the log-normal demand parameters
  reported in Section 3.1 of the manuscript. Released by the
  authors under a CC BY licence on the Mendeley Data repository.
- **CVRPLIB Augerat Set-A** (27 capacitated VRP instances): used
  for the implementation-correctness benchmark in Section 5.3.
  Public-domain release with the Augerat 1995 distribution; the
  best-known-solution figures are sourced from the canonical
  CVRPLIB mirror.
- **Delhivery secondary network** (144,867 shipments, 10 hubs by
  150 customers): used for the cross-validation reported in
  Section 5.8. Available under the dataset-card terms of the
  Kaggle release.
- **NITI Aayog and RMI 2021 freight roadmap**: source of the
  empty-running fraction (35 per cent) and HCV load-factor
  (65 per cent) used in the operating-point calibration.

All download URLs, licences, version stamps, and per-source citations
are catalogued in `docs/DATA_SOURCES.md` so a reviewer can re-fetch
each input from the authoritative origin.

## Results data

All results consumed by the manuscript figures and tables are
checkpointed in `data/results/` (training summary, statistical
tests, PPO baselines, disruption evaluation, sensitivity indices)
and are reproducible end-to-end via the recipe in
`docs/REPLICATION_RECIPE.md`. The cross-asset consistency suite
(`tests/test_paper_assets_consistency.py`) pins the headline
numbers in `docs/HEADLINE_NUMBERS.md` against the rendered tables
and the narrative documents, so any drift between the reported
values and the regenerated assets is caught automatically.

## Reproducibility

Reproducibility is enforced through a master seed of 42, propagated
to NumPy, PyTorch, the Python random module, and the pymoo internal
generator. The full test suite (488 passed, 5 skipped) is the
binding correctness contract; the `tests/test_paper_assets_consistency.py`
suite is the binding consistency contract that pins each headline
number in the manuscript to the rendered LaTeX tables. Both must
pass for a reproduction to count as green.
