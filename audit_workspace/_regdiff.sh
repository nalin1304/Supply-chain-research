#!/usr/bin/env bash
set -euo pipefail
cd /Users/nalinaggarwal/Downloads/Supply-chain-main
grep PASSED audit_workspace/PASSING_TESTS_FINAL.txt | sort > audit_workspace/_final_passed.txt
grep PASSED audit_workspace/PASSING_TESTS_BASELINE.txt | sort > audit_workspace/_baseline_passed.txt || true
comm -13 audit_workspace/_final_passed.txt audit_workspace/_baseline_passed.txt > audit_workspace/PASSING_REGRESSIONS.txt
wc -l < audit_workspace/PASSING_REGRESSIONS.txt
