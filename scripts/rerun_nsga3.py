#!/usr/bin/env python3
"""Re-run NSGA-III after FIX-026 (volume-weighted mean delivery time).

Replaces ``data/results/nsga3_all_results.pkl`` with a 50-seed run
under the corrected third objective. Standalone script so the
training pipeline doesn't need to be rerun end-to-end.

Usage
-----
    python scripts/rerun_nsga3.py [--seeds 50] [--pop-size 92] [--n-gen 200]
"""

from __future__ import annotations

import argparse
import json
import os
import pickle
import sys
import time
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from supply_chain_research.config import MasterConfig  # noqa: E402
from supply_chain_research.phase1_foundation.data_engineering import (  # noqa: E402
    generate_customer_locations,
    get_warehouse_locations,
    generate_demand,
)
from supply_chain_research.phase1_foundation.nsga3_solver import run_nsga3  # noqa: E402
from supply_chain_research.phase1_foundation.pareto_analysis import (  # noqa: E402
    compute_hypervolume,
)


def main() -> None:
    """Run 50-seed NSGA-III and persist updated results."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", type=int, default=50)
    parser.add_argument("--pop-size", type=int, default=92)
    parser.add_argument("--n-gen", type=int, default=200)
    args = parser.parse_args()

    print("=" * 60)
    print("NSGA-III RE-RUN (post-FIX-026 volume-weighted delivery time)")
    print("=" * 60)

    config = MasterConfig()
    rng = np.random.default_rng(42)
    customers = generate_customer_locations(config, rng)
    warehouses = get_warehouse_locations(config)
    demand = generate_demand(config, rng)
    all_locs = np.vstack([warehouses, customers])

    # Haversine distance matrix
    R = 6371.0
    lat1 = np.deg2rad(all_locs[:, 0])[:, None]
    lon1 = np.deg2rad(all_locs[:, 1])[:, None]
    lat2 = np.deg2rad(all_locs[:, 0])[None, :]
    lon2 = np.deg2rad(all_locs[:, 1])[None, :]
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = (
        np.sin(dlat / 2.0) ** 2
        + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2.0) ** 2
    )
    full_dist = R * 2.0 * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))
    distance_matrix = full_dist[
        : config.network.n_warehouses, config.network.n_warehouses :
    ]

    # Duration matrix in minutes (km / kmh × 60)
    duration_matrix = (
        distance_matrix
        / max(config.simulation.truck_speed_kmh, 1.0)
        * 60.0
    )

    print(
        f"  Network    : {config.network.n_warehouses} W x "
        f"{config.network.n_customers} C  |  dist mean={distance_matrix.mean():.0f} km"
    )
    print(f"  Demand     : mean={demand.mean():.0f} kg")
    print(f"  Duration   : {duration_matrix.shape}, mean={duration_matrix.mean():.1f} min")
    print(f"  NSGA-III   : {args.seeds} seeds, pop={args.pop_size}, gen={args.n_gen}")

    fronts = []
    hvs = []
    t_total = time.time()
    for s in range(args.seeds):
        t0 = time.time()
        try:
            r = run_nsga3(
                config, distance_matrix, demand, duration_matrix,
                pop_size=args.pop_size, n_gen=args.n_gen, seed=s,
            )
        except Exception as e:
            print(f"    seed {s:2d}: FAILED ({type(e).__name__}: {e})")
            fronts.append([])
            hvs.append(0.0)
            continue
        F = r.F.tolist() if r.F is not None else []
        fronts.append(F)
        hv = compute_hypervolume(np.asarray(F)) if F else 0.0
        hvs.append(float(hv))
        elapsed = time.time() - t0
        total = time.time() - t_total
        eta = total / (s + 1) * (args.seeds - s - 1) / 60
        if (s + 1) % 5 == 0 or s == 0:
            print(
                f"    seed {s:2d}: {len(F):3d} pts  HV={hv:.4f}  "
                f"({elapsed:.1f}s; total {total/60:.1f}m, ETA {eta:.1f}m)"
            )

    # Persist
    out = PROJECT_ROOT / "data" / "results" / "nsga3_all_results.pkl"
    with open(out, "wb") as f:
        pickle.dump(
            {"fronts": fronts, "hvs": hvs, "n_seeds": args.seeds},
            f,
        )
    print(f"\n  Saved: {out}")

    # Summary
    sizes = np.array([len(F) for F in fronts])
    hvs_arr = np.array(hvs)
    print(
        f"  Summary    : mean front size = {sizes.mean():.2f} "
        f"(range {sizes.min()}-{sizes.max()})"
    )
    print(
        f"             : HV mean={hvs_arr.mean():.4f}  std={hvs_arr.std():.4f}"
    )

    # Also patch training_summary.json with the new mean_hv
    summary_path = PROJECT_ROOT / "data" / "results" / "training_summary.json"
    if summary_path.exists():
        s = json.loads(summary_path.read_text())
        s["nsga3"]["mean_hv"] = float(hvs_arr.mean())
        summary_path.write_text(json.dumps(s, indent=2))
        print(f"  Patched    : {summary_path} (nsga3.mean_hv = {hvs_arr.mean():.4f})")


if __name__ == "__main__":
    main()
