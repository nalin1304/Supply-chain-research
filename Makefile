# Reviewer-friendly reproduction targets.
#
# A reviewer who clones this repo can run a single make target and
# get a fully reproduced paper-asset set, without needing to know
# anything about the internal module structure.
#
# Usage examples:
#   make help                  # show every target
#   make tests                 # 488 passed, 5 skipped, ~205 s
#   make figures               # all 9 publication figures
#   make tables                # all 8 LaTeX tables
#   make cvrplib-validation    # the 27 Augerat instances + the table
#   make managerial-thresholds # the 4 quantitative thresholds JSON
#   make paper-assets          # figures + tables + thresholds + tests
#   make clean                 # delete generated artifacts
#   make help-cloud            # Modal training entry-point reminder

PYTHON ?= python3
PYTEST ?= $(PYTHON) -m pytest
RESULTS_DIR := data/results
FIG_DIR := outputs/figures
TBL_DIR := outputs/tables

.DEFAULT_GOAL := help

.PHONY: help help-cloud tests tests-fast figures tables \
        cvrplib-validation managerial-thresholds paper-assets \
        clean clean-pycache lint-tables manuscript

# -----------------------------------------------------------
# Help
# -----------------------------------------------------------

help:
	@echo "Reviewer reproduction targets:"
	@echo ""
	@echo "  make tests                 Run the pytest suite (488 passed, 5 skipped, ~205 s)"
	@echo "  make tests-fast            Run only the non-PBT tests (~30 s)"
	@echo "  make figures               Render all 9 publication figures"
	@echo "  make tables                Render all 8 LaTeX tables"
	@echo "  make cvrplib-validation    Run 27 Augerat instances + table"
	@echo "  make managerial-thresholds Refresh the 4-threshold JSON"
	@echo "  make paper-assets          Run figures + tables + thresholds + tests"
	@echo "  make lint-tables           Validate LaTeX tables syntactically"
	@echo "  make clean                 Delete every generated artifact"
	@echo "  make help-cloud            How to launch the Modal training pipeline"
	@echo "  make manuscript            Compile manuscript/main.tex (skips if no pdflatex)"

help-cloud:
	@echo "Cloud training (Modal):"
	@echo ""
	@echo "  modal run --detach cloud_training/modal_train.py"
	@echo ""
	@echo "  - GPU: T4, ~3 h, ~\$$1.80"
	@echo "  - Resumable: every step skips if its output already exists"
	@echo "  - Outputs land in modal volume sc-results-v3"
	@echo "  - Pull with: modal volume get sc-results-v3 / data/results --force"
	@echo ""
	@echo "Local CPU fallback (slow but works):"
	@echo "  python cloud_training/local_training_runner.py --component all"

# -----------------------------------------------------------
# Tests
# -----------------------------------------------------------

tests:
	$(PYTEST) tests/ -q

tests-fast:
	$(PYTEST) tests/ -q -m "not pbt and not slow"

# -----------------------------------------------------------
# Paper assets
# -----------------------------------------------------------

figures: $(RESULTS_DIR)/training_summary.json
	$(PYTHON) -m supply_chain_research.phase4_synthesis.generate_all_figures
	@echo "Figures written to $(FIG_DIR)/"

tables: $(RESULTS_DIR)/training_summary.json
	$(PYTHON) -m supply_chain_research.phase4_synthesis.generate_latex_tables
	@echo "Tables written to $(TBL_DIR)/"

cvrplib-validation:
	$(PYTHON) scripts/run_cvrplib_benchmark.py
	@echo "CVRPLIB validation table at $(TBL_DIR)/cvrplib_validation.tex"

managerial-thresholds: $(RESULTS_DIR)/training_summary.json
	$(PYTHON) -m supply_chain_research.phase4_synthesis.compute_managerial_thresholds
	@echo "Thresholds JSON at outputs/managerial_thresholds.json"

paper-assets: figures tables cvrplib-validation managerial-thresholds tests
	@echo ""
	@echo "Paper assets ready:"
	@echo "  Figures:  $(FIG_DIR)/*.png ($$(ls $(FIG_DIR)/*.png 2>/dev/null | wc -l | tr -d ' ') files)"
	@echo "  Tables:   $(TBL_DIR)/*.tex ($$(ls $(TBL_DIR)/*.tex 2>/dev/null | wc -l | tr -d ' ') files)"
	@echo "  Tests:    pass"

lint-tables:
	$(PYTHON) audit_workspace/_validate_latex_tables.py

# -----------------------------------------------------------
# Manuscript compile
# -----------------------------------------------------------

# Compile manuscript/main.tex into manuscript/main.pdf using pdflatex
# + bibtex + two more pdflatex passes for cross-references and
# bibliography. Skips gracefully if pdflatex is not installed so the
# target stays a no-op on systems without a LaTeX toolchain.
manuscript:
	@command -v pdflatex >/dev/null 2>&1 && ( \
		cd manuscript && \
		pdflatex -interaction=nonstopmode main.tex && \
		bibtex main && \
		pdflatex -interaction=nonstopmode main.tex && \
		pdflatex -interaction=nonstopmode main.tex && \
		echo "Manuscript compiled to manuscript/main.pdf" \
	) || echo "pdflatex unavailable, skipping manuscript compile"

# -----------------------------------------------------------
# Sentinels
# -----------------------------------------------------------

# If training_summary.json is missing the user needs to either run
# training or fetch from the Modal volume; we don't try to fake it.
$(RESULTS_DIR)/training_summary.json:
	@echo "ERROR: $(RESULTS_DIR)/training_summary.json not found."
	@echo ""
	@echo "Either:"
	@echo "  1. modal volume get sc-results-v3 / data/results --force"
	@echo "  2. python cloud_training/local_training_runner.py --component all"
	@echo "  3. modal run --detach cloud_training/modal_train.py"
	@exit 1

# -----------------------------------------------------------
# Cleanup
# -----------------------------------------------------------

clean: clean-pycache
	rm -rf $(FIG_DIR)/*.png $(FIG_DIR)/supplementary/*.png
	rm -rf $(TBL_DIR)/*.tex
	rm -f outputs/managerial_thresholds.json
	rm -f .coverage
	@echo "Cleaned generated artifacts (figures, tables, thresholds, coverage)."

clean-pycache:
	@find . -type d -name __pycache__ -not -path "*/node_modules/*" \
		-exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name .pytest_cache \
		-exec rm -rf {} + 2>/dev/null || true
	@echo "Cleared __pycache__ and .pytest_cache."
