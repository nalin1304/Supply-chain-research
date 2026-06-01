"""Capture pre-fix numeric baseline outputs for regression testing.

Per task 0.4 of the supply-chain-research-audit spec:

- Use seed=42 throughout
- Persist deterministic outputs of key functions to
  ``audit_workspace/NUMERIC_BASELINE.json`` with a per-key
  ``tolerance`` field. Group 6 reads this file to mechanically
  prove no regressions across waves 1-5.

Captured artifacts (one top-level key per preservation clause):

- ``emissions``           -> EmissionCalculator HCV / LCV outputs (C3.3)
- ``nsga2_pareto``        -> Pareto-front objective vectors from
                              ``run_nsga2(pop_size=500, n_gen=100, seed=42)``
                              (C3.2)
- ``cvrp_baseline``       -> ``solve_baseline_cvrp(method="ortools")``
                              total cost / emission (C3.7)
- ``des_service_level``   -> DES no-shock mean service level over
                              30 replications starting at seed=42 (C3.9)

Run from repo root::

    python audit_workspace/capture_numeric_baseline.py

The script intentionally has *no test-time mocking*: it calls the
real public APIs so the captured values are a faithful snapshot of
current behavior.
"""

from __future__ import annotations

import json
import sys
import time
import warnings
from pathlib import Path
from typing import Any

import numpy as np

# Make the script runnable from anywhere by inserting the repo root
# (parent of the audit_workspace/ directory) onto sys.path.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Suppress non-fatal noise (deprecation warnings from third-party libs,
# pymoo runtime warnings, etc.) so the captured JSON output is the only
# thing on stdout the user has to inspect.
warnings.filterwarnings("ignore")

from supply_chain_research.config import MasterConfig  # noqa: E402
from supply_chain_research.phase1_foundation.emission_model import (  # noqa: E402
    EmissionCalculator,
)
from supply_chain_research.phase1_foundation.nsga2_solver import (  # noqa: E402
    run_nsga2,
)
from supply_chain_research.phase1_foundation.baseline_solver import (  # noqa: E402
    solve_baseline_cvrp,
)
from supply_chain_research.phase2_resilience.des_environment import (  # noqa: E402
    DESEnvironment,
)

# ---------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------

OUTPUT_PATH = Path(__file__).resolve().parent / "NUMERIC_BASELINE.json"
SEED = 42

# NSGA-II runtime parameters (per task 0.4 spec).
NSGA2_POP_SIZE = 500
NSGA2_N_GEN = 100

# DES baseline parameters (per task 0.4 spec).
DES_N_REPLICATIONS = 30


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------


def _build_synthetic_problem(cfg: MasterConfig, seed: int):
    """Build a deterministic synthetic distance matrix + demand vector.

    Mirrors the construction used in ``tests/test_regression_baseline.py``
    so the regression test and this baseline capture stay in lockstep.

    Parameters
    ----------
    cfg : MasterConfig
        Master configuration. ``cfg.network.n_warehouses`` and
        ``cfg.network.n_customers`` determine matrix shape.
    seed : int
        Seed for ``numpy.random.default_rng`` to ensure determinism.

    Returns
    -------
    distance_matrix : np.ndarray, shape (n_w, n_c)
        Distances in km, drawn uniformly from [50, 500].
    demand : np.ndarray, shape (n_c,)
        Customer demand in kg, drawn uniformly from [100, 5000].
    """
    n_w = cfg.network.n_warehouses
    n_c = cfg.network.n_customers
    rng = np.random.default_rng(seed)
    distance_matrix = rng.uniform(50.0, 500.0, size=(n_w, n_c))
    demand = rng.uniform(100.0, 5000.0, size=n_c)
    return distance_matrix, demand


# ---------------------------------------------------------------------
# Capture functions
# ---------------------------------------------------------------------


def capture_emissions() -> dict[str, Any]:
    """Capture EmissionCalculator outputs for HCV / LCV scenarios.

    Preservation clause: C3.3 — when HCV parameters are unchanged the
    kg-CO2 outputs MUST be bit-for-bit identical post-fix.
    """
    cfg = MasterConfig()
    calc = EmissionCalculator(cfg)
    return {
        "tolerance": 1.0e-9,
        "tolerance_kind": "absolute",
        "scenario": (
            "HCV (Hickman 1999 MEET Table 3.2; cross-verified "
            "COPERT 5 / HBEFA 4.2) and LCV (Hickman 1999 Table 3.3)"
        ),
        "hcv_capacity_kg": float(cfg.vehicle.hcv_capacity),
        "lcv_capacity_kg": float(cfg.vehicle.lcv_capacity),
        "hcv_zero_rate_kgco2_per_km": float(
            calc.emission_rate("HCV", 0.0)
        ),
        "hcv_half_rate_kgco2_per_km": float(
            calc.emission_rate("HCV", cfg.vehicle.hcv_capacity / 2.0)
        ),
        "hcv_full_rate_kgco2_per_km": float(
            calc.emission_rate("HCV", cfg.vehicle.hcv_capacity)
        ),
        "hcv_route_100km_full_kgco2": float(
            calc.route_emission(
                "HCV", cfg.vehicle.hcv_capacity, 100.0
            )
        ),
        "lcv_zero_rate_kgco2_per_km": float(
            calc.emission_rate("LCV", 0.0)
        ),
        "lcv_full_rate_kgco2_per_km": float(
            calc.emission_rate("LCV", cfg.vehicle.lcv_capacity)
        ),
        "diesel_co2_factor_kgco2_per_litre": float(
            cfg.vehicle.diesel_co2_factor
        ),
    }


def capture_nsga2() -> dict[str, Any]:
    """Capture NSGA-II Pareto front under fixed seed.

    Preservation clauses: C3.2, C3.4 — ``warm_start=False`` (the default
    here) MUST reproduce these objective vectors after Wave 1-5 fixes.

    Notes
    -----
    Uses ``pop_size=500`` and ``n_gen=100`` per task 0.4. The actual
    NSGA-II run may stop early via the configured hypervolume-based
    termination criterion (see ``NSGAConfig.early_stop_*``); the
    ``hv_history`` length captures the actual generations executed.
    """
    cfg = MasterConfig()
    distance_matrix, demand = _build_synthetic_problem(cfg, SEED)

    t0 = time.perf_counter()
    result = run_nsga2(
        cfg,
        distance_matrix,
        demand,
        pop_size=NSGA2_POP_SIZE,
        n_gen=NSGA2_N_GEN,
        seed=SEED,
    )
    elapsed = time.perf_counter() - t0

    front_F = result.F if result.F is not None else np.empty((0, 2))
    front = np.asarray(front_F)
    hv_history = list(getattr(result, "hv_history", []) or [])

    payload: dict[str, Any] = {
        "tolerance": 1.0e-6,
        "tolerance_kind": "relative",
        "config": {
            "pop_size": NSGA2_POP_SIZE,
            "n_gen": NSGA2_N_GEN,
            "seed": SEED,
            "n_warehouses": cfg.network.n_warehouses,
            "n_customers": cfg.network.n_customers,
            "warm_start": False,
        },
        "objective_names": ["cost_inr", "carbon_kg_co2"],
        "n_solutions": int(front.shape[0]) if front.size else 0,
        "front": front.tolist() if front.size else [],
        "min_cost": float(front[:, 0].min()) if front.size else None,
        "min_carbon": float(front[:, 1].min()) if front.size else None,
        "max_cost": float(front[:, 0].max()) if front.size else None,
        "max_carbon": float(front[:, 1].max()) if front.size else None,
        "n_generations_executed": len(hv_history),
        "hv_final": float(hv_history[-1]) if hv_history else None,
        "elapsed_seconds": round(elapsed, 3),
    }
    return payload


def capture_cvrp_baseline() -> dict[str, Any]:
    """Capture OR-Tools CVRP baseline cost / emission under seed=42.

    Preservation clause: C3.7 — ``method="ortools"`` (default) MUST
    reproduce these values post-fix.
    """
    cfg = MasterConfig()
    distance_matrix, demand = _build_synthetic_problem(cfg, SEED)

    t0 = time.perf_counter()
    result = solve_baseline_cvrp(
        config=cfg,
        distance_matrix=distance_matrix,
        demand=demand,
        vehicle_type="HCV",
        time_limit_seconds=30,
        method="ortools",
    )
    elapsed = time.perf_counter() - t0

    routes = result.get("routes", []) or []
    return {
        "tolerance": 1.0e-6,
        "tolerance_kind": "relative",
        "config": {
            "method": "ortools",
            "vehicle_type": "HCV",
            "time_limit_seconds": 30,
            "seed": SEED,
            "n_warehouses": cfg.network.n_warehouses,
            "n_customers": cfg.network.n_customers,
        },
        "total_cost_inr": float(result.get("total_cost", 0.0)),
        "total_emission_kgco2": float(result.get("total_emission", 0.0)),
        "n_routes": len(routes),
        "feasible": bool(result.get("feasible", False)),
        "elapsed_seconds": round(elapsed, 3),
    }


def capture_des_no_shock() -> dict[str, Any]:
    """Capture DES no-shock mean service level over 30 replications.

    Preservation clause: C3.9 — DES under the no-shock baseline MUST
    continue to produce ~95% mean service level post-fix.

    Notes
    -----
    The 30 replications use seeds ``[SEED, SEED+1, ..., SEED+29]`` —
    matching the per-job seed scheme used by ``MonteCarloRunner``
    (``base_seed + job_id``). No shocks are added to the environment,
    so this measures the unperturbed service level only.
    """
    cfg = MasterConfig()

    service_levels: list[float] = []
    total_costs: list[float] = []
    total_emissions: list[float] = []

    t0 = time.perf_counter()
    for i in range(DES_N_REPLICATIONS):
        des = DESEnvironment(config=cfg, seed=SEED + i)
        run_results = des.run()
        service_levels.append(float(run_results["mean_service_level"]))
        total_costs.append(float(run_results.get("total_cost", 0.0)))
        total_emissions.append(
            float(run_results.get("total_emissions", 0.0))
        )
    elapsed = time.perf_counter() - t0

    sl_arr = np.asarray(service_levels)
    cost_arr = np.asarray(total_costs)
    emis_arr = np.asarray(total_emissions)

    return {
        # Absolute tolerance: clause C3.9 / task 4.4 calls for ±0.005.
        "tolerance": 5.0e-3,
        "tolerance_kind": "absolute",
        "config": {
            "n_replications": DES_N_REPLICATIONS,
            "base_seed": SEED,
            "sim_days": cfg.simulation.sim_days,
            "warmup_days": cfg.simulation.warmup_days,
            "n_warehouses": cfg.network.n_warehouses,
            "n_customers": cfg.network.n_customers,
            "shocks": [],
        },
        "mean_service_level": float(sl_arr.mean()),
        "std_service_level": float(sl_arr.std(ddof=0)),
        "min_service_level": float(sl_arr.min()),
        "max_service_level": float(sl_arr.max()),
        "mean_total_cost_inr": float(cost_arr.mean()),
        "mean_total_emission_kgco2": float(emis_arr.mean()),
        "per_replication_service_level": service_levels,
        "elapsed_seconds": round(elapsed, 3),
    }


# ---------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------


def main() -> int:
    """Capture all baselines and persist them to NUMERIC_BASELINE.json."""
    print(f"Capturing numeric baseline (seed={SEED}) -> {OUTPUT_PATH}")

    print("  [1/4] EmissionCalculator (HCV / LCV) ...", flush=True)
    emissions = capture_emissions()
    print(
        f"        hcv_full_rate = "
        f"{emissions['hcv_full_rate_kgco2_per_km']:.6f} kgCO2/km"
    )

    print(
        f"  [2/4] NSGA-II Pareto front "
        f"(pop={NSGA2_POP_SIZE}, gen={NSGA2_N_GEN}) ...",
        flush=True,
    )
    nsga2_pareto = capture_nsga2()
    print(
        f"        n_solutions = {nsga2_pareto['n_solutions']}, "
        f"min_cost = {nsga2_pareto['min_cost']}, "
        f"min_carbon = {nsga2_pareto['min_carbon']}, "
        f"elapsed = {nsga2_pareto['elapsed_seconds']}s"
    )

    print("  [3/4] CVRP OR-Tools baseline ...", flush=True)
    cvrp_baseline = capture_cvrp_baseline()
    print(
        f"        total_cost = {cvrp_baseline['total_cost_inr']:.2f} INR, "
        f"total_emission = "
        f"{cvrp_baseline['total_emission_kgco2']:.2f} kgCO2, "
        f"elapsed = {cvrp_baseline['elapsed_seconds']}s"
    )

    print(
        f"  [4/4] DES no-shock baseline "
        f"(n_replications={DES_N_REPLICATIONS}) ...",
        flush=True,
    )
    des_service_level = capture_des_no_shock()
    print(
        f"        mean_service_level = "
        f"{des_service_level['mean_service_level']:.6f}, "
        f"std = {des_service_level['std_service_level']:.6f}, "
        f"elapsed = {des_service_level['elapsed_seconds']}s"
    )

    payload = {
        "spec": "supply-chain-research-audit",
        "task": "0.4",
        "seed": SEED,
        "preservation_clauses": ["C3.2", "C3.3", "C3.7", "C3.9"],
        "emissions": emissions,
        "nsga2_pareto": nsga2_pareto,
        "cvrp_baseline": cvrp_baseline,
        "des_service_level": des_service_level,
    }

    OUTPUT_PATH.write_text(json.dumps(payload, indent=2))
    print(f"Wrote {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
