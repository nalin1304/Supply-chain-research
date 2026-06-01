#!/usr/bin/env bash
# check_deliverables.sh — Wave 6 task 6.6 verification.
# Prints "PRESENT <bytes> <path>" or "MISSING <path>" per spec deliverable.
set -u
missing=0
for f in \
    supply_chain_research/requirements.txt \
    supply_chain_research/phase1_foundation/nsga3_solver.py \
    supply_chain_research/phase1_foundation/multi_product_solver.py \
    supply_chain_research/phase1_foundation/robust_solver.py \
    supply_chain_research/phase1_foundation/clarke_wright.py \
    supply_chain_research/phase1_foundation/carbon_budget_solver.py \
    supply_chain_research/phase3_ai/tft_forecaster.py \
    supply_chain_research/phase3_ai/sac_agent.py \
    supply_chain_research/phase4_synthesis/complexity_analysis.py \
    supply_chain_research/phase4_synthesis/managerial_insights.py \
    docs/LITERATURE_GAP_ANALYSIS.md \
    docs/COMPLEXITY_ANALYSIS.md \
    docs/MANAGERIAL_INSIGHTS.md \
    docs/IMPROVEMENT_REPORT.md \
    docs/VERIFIED_REFERENCES.bib \
    docs/PAPER_OUTLINE.md \
    docs/REPLICATION_GUIDE.md \
    cloud_training/README_CLOUD_SETUP.md \
    cloud_training/kaggle_setup.ipynb \
    cloud_training/colab_setup.ipynb \
    cloud_training/vastai_setup.sh \
    cloud_training/local_training_runner.py \
    cloud_training/TRAINING_GUIDE.md ; do
    if test -s "$f"; then
        bytes=$(wc -c < "$f")
        printf "  PRESENT %10d  %s\n" "$bytes" "$f"
    else
        echo "  MISSING $f"
        missing=$((missing+1))
    fi
done
echo
echo "TOTAL MISSING: $missing"
exit $missing
