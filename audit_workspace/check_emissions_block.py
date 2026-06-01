"""Quick emissions-block regression check for FIX-005.

Re-computes the same outputs the audit_workspace/capture_numeric_baseline.py
script writes to NUMERIC_BASELINE.json -> "emissions" block, and asserts
they match the recorded baseline within the recorded 1e-9 tolerance.
This proves preservation clause C3.3 for FIX-005 in seconds rather than
re-running the full multi-minute baseline capture.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from supply_chain_research.config import MasterConfig
from supply_chain_research.phase1_foundation.emission_model import (
    EmissionCalculator,
)

baseline_path = REPO_ROOT / "audit_workspace" / "NUMERIC_BASELINE.json"
baseline = json.loads(baseline_path.read_text())["emissions"]
tol = baseline["tolerance"]

cfg = MasterConfig()
calc = EmissionCalculator(cfg)

hcv_cap = cfg.vehicle.hcv_capacity
lcv_cap = cfg.vehicle.lcv_capacity

hcv_zero = calc.emission_rate("HCV", 0.0)
hcv_half = calc.emission_rate("HCV", hcv_cap / 2.0)
hcv_full = calc.emission_rate("HCV", hcv_cap)
hcv_route = calc.route_emission("HCV", hcv_cap, 100.0)
lcv_zero = calc.emission_rate("LCV", 0.0)
lcv_full = calc.emission_rate("LCV", lcv_cap)
diesel_ef = cfg.vehicle.diesel_co2_factor

checks = [
    ("hcv_capacity_kg", hcv_cap),
    ("lcv_capacity_kg", lcv_cap),
    ("hcv_zero_rate_kgco2_per_km", hcv_zero),
    ("hcv_half_rate_kgco2_per_km", hcv_half),
    ("hcv_full_rate_kgco2_per_km", hcv_full),
    ("hcv_route_100km_full_kgco2", hcv_route),
    ("lcv_zero_rate_kgco2_per_km", lcv_zero),
    ("lcv_full_rate_kgco2_per_km", lcv_full),
    ("diesel_co2_factor_kgco2_per_litre", diesel_ef),
]

failed = []
for key, current in checks:
    expected = baseline[key]
    diff = abs(current - expected)
    status = "OK" if diff <= tol else "FAIL"
    print(f"{status:4s}  {key:42s}  expected={expected!r:24s}  got={current!r:24s}  diff={diff:.3e}")
    if diff > tol:
        failed.append((key, expected, current, diff))

if failed:
    print(f"\nFAILED: {len(failed)} key(s) exceeded tolerance {tol}")
    sys.exit(1)
else:
    print(f"\nPASS: all {len(checks)} emissions-block keys match within tolerance {tol}")
    sys.exit(0)
