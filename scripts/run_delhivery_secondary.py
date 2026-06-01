#!/usr/bin/env python3
"""Secondary-network NSGA-II validation on the Delhivery topology.

Cross-validation appendix asset for the manuscript. Re-runs the
bi-objective NSGA-II on the Delhivery 10-hub × 150-customer network
(``data/processed/delhivery_*.npy``) and produces:

  - ``data/results/delhivery_nsga2_all_results.pkl`` — per-seed Pareto
    fronts, joint hypervolume, joint ideal/nadir
  - ``outputs/tables/secondary_network_validation.tex`` — comparison
    table to put alongside the primary Dalal-network results

Why a secondary network: addresses external-validity concerns that
the primary results may be over-fit to the Dalal (2022) topology.
The Delhivery network has 10 hubs vs 5 in Dalal, 150 vs 100 customer
nodes, and is calibrated against 144,867 real Indian shipments.

Usage
-----
    python scripts/run_delhivery_secondary.py [--seeds 50] [--gen 100]

References
----------
.. [Delhivery2022] Delhivery Limited. Business Case Study Dataset.
   Kaggle, 2022. https://www.kaggle.com/datasets/benroshan/delhivery-business-case-study
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
from supply_chain_research.phase1_foundation.nsga2_solver import (  # noqa: E402
    run_nsga2,
)
from supply_chain_research.phase1_foundation.pareto_analysis import (  # noqa: E402
    compute_hypervolume,
)


PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
RESULTS_DIR = PROJECT_ROOT / "data" / "results"
TABLES_DIR = PROJECT_ROOT / "outputs" / "tables"


def _load_delhivery_network() -> tuple:
    """Load the Delhivery secondary network arrays.

    The cached distance matrix has ~10 % NaN entries from failed ORS
    routing queries. NaNs are filled with great-circle (haversine)
    distances so NSGA-II's evaluator never sees a non-finite cost.

    Returns
    -------
    tuple[np.ndarray, np.ndarray, np.ndarray, dict]
        warehouses (10, 2), customers (150, 2), distance_matrix (10, 150)
        with all entries finite, metadata dict from
        ``delhivery_network.json``.
    """
    warehouses = np.load(PROCESSED_DIR / "delhivery_warehouse_locations.npy")
    customers = np.load(PROCESSED_DIR / "delhivery_customer_locations.npy")
    distance_matrix = np.load(PROCESSED_DIR / "delhivery_distance_matrix_km.npy")
    with open(PROCESSED_DIR / "delhivery_network.json") as f:
        network = json.load(f)
    distance_matrix = _fill_nan_with_haversine(
        distance_matrix, warehouses, customers
    )
    return warehouses, customers, distance_matrix, network


def _fill_nan_with_haversine(
    distance_matrix: np.ndarray,
    warehouses: np.ndarray,
    customers: np.ndarray,
) -> np.ndarray:
    """Replace NaN entries in the distance matrix with haversine distance.

    Approximately 10% of the cached Delhivery ORS distance matrix is
    NaN (failed routing queries; usually due to ORS rate-limiting or
    the destination being inland of an island/peninsula the road
    graph doesn't cover). Filling with great-circle distance is a
    well-established robust fallback in the OR literature
    [Chen-2024 §3].

    Parameters
    ----------
    distance_matrix : np.ndarray
        Original (n_w, n_c) array, possibly containing NaN.
    warehouses : np.ndarray
        (n_w, 2) lat/lon array.
    customers : np.ndarray
        (n_c, 2) lat/lon array.

    Returns
    -------
    np.ndarray
        Same shape as ``distance_matrix``; every NaN is replaced
        with the haversine distance between the corresponding
        warehouse and customer.
    """
    if not np.isnan(distance_matrix).any():
        return distance_matrix

    R = 6371.0  # Earth radius in km
    out = distance_matrix.copy()
    nan_mask = np.isnan(out)
    if not nan_mask.any():
        return out

    # Compute haversine for every (w, c) pair (vectorised).
    lat1 = np.deg2rad(warehouses[:, 0])[:, None]      # (n_w, 1)
    lon1 = np.deg2rad(warehouses[:, 1])[:, None]
    lat2 = np.deg2rad(customers[:, 0])[None, :]       # (1, n_c)
    lon2 = np.deg2rad(customers[:, 1])[None, :]
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = (
        np.sin(dlat / 2.0) ** 2
        + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2.0) ** 2
    )
    c = 2.0 * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))
    haversine = R * c

    # Apply Delhivery-validated 1.21x correction (the inverse of the
    # 0.83 OSRM-vs-actual ratio in data/processed/delhivery_calibration.json)
    # to convert great-circle to a road-distance proxy.
    out[nan_mask] = haversine[nan_mask] * 1.21
    return out


def _generate_demand_from_volumes(network: dict, n_customers: int) -> np.ndarray:
    """Build the demand vector from observed customer outbound volumes.

    The Delhivery dataset reports observed outbound shipment counts per
    customer node. We treat these as proxy demand intensities (kg/day)
    using a deterministic linear scale from the global mean to the
    network's mean outbound volume so the resulting magnitudes are
    consistent with the primary-network calibration in
    ``MasterConfig.network`` (mean ≈ 1000 kg/day).

    Parameters
    ----------
    network : dict
        Parsed ``delhivery_network.json``.
    n_customers : int
        Number of customer rows expected.

    Returns
    -------
    np.ndarray
        Demand vector of shape ``(n_customers,)`` in kg.
    """
    volumes = np.array(
        [c.get("outbound", 0) or 0 for c in network["customers"][:n_customers]],
        dtype=np.float64,
    )
    if volumes.sum() <= 0.0:
        # Defensive fallback: uniform demand if outbound counts are missing.
        return np.full(n_customers, 1000.0)
    # Scale so the mean matches the primary network mean (1000 kg/day).
    scale = 1000.0 / max(volumes.mean(), 1.0)
    return volumes * scale


def main() -> None:
    """Run NSGA-II on the Delhivery secondary network and write outputs."""
    parser = argparse.ArgumentParser(
        description="Secondary-network NSGA-II validation"
    )
    parser.add_argument(
        "--seeds", type=int, default=20,
        help="Number of independent seeds (default 20 for speed; 50 for paper).",
    )
    parser.add_argument(
        "--pop-size", type=int, default=300,
        help="NSGA-II population size (default 300).",
    )
    parser.add_argument(
        "--gen", type=int, default=80,
        help="NSGA-II generations (default 80).",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("DELHIVERY SECONDARY-NETWORK VALIDATION (NSGA-II)")
    print("=" * 60)

    # 1. Load network and build demand
    warehouses, customers, distance_matrix, network = _load_delhivery_network()
    n_w, n_c = distance_matrix.shape
    demand = _generate_demand_from_volumes(network, n_c)
    print(f"  Network    : {n_w} warehouses × {n_c} customers")
    print(f"  Distance   : {distance_matrix.shape} mean={distance_matrix.mean():.0f} km")
    print(f"  Demand     : mean={demand.mean():.0f} kg, sum={demand.sum():.0f} kg")
    print(f"  Source     : {network['metadata']['source']}")

    # 2. Build a config sized to the secondary network
    cfg = MasterConfig.derive_from_problem_size(
        n_customers=n_c, n_warehouses=n_w
    )
    # Match the warehouse capacities to outbound volumes so capacity is
    # never the binding constraint at this calibration.
    outbound = np.array(
        [w.get("outbound", 0) or 1000 for w in network["warehouses"][:n_w]]
    )
    capacities = np.maximum(outbound, demand.sum() / n_w * 4.0)
    cfg.network.warehouse_capacities = capacities.tolist()

    # 3. Run NSGA-II across seeds
    print(
        f"\n  NSGA-II    : {args.seeds} seeds, "
        f"pop={args.pop_size}, gen={args.gen}"
    )
    all_fronts = []
    seed_durations = []
    t_total = time.time()
    for s in range(args.seeds):
        t0 = time.time()
        result = run_nsga2(
            cfg, distance_matrix, demand,
            pop_size=args.pop_size, n_gen=args.gen, seed=s,
        )
        F = result.F.tolist() if result.F is not None else []
        all_fronts.append(F)
        dt = time.time() - t0
        seed_durations.append(dt)
        elapsed = time.time() - t_total
        eta = (elapsed / (s + 1)) * (args.seeds - s - 1) / 60
        print(
            f"    seed {s:2d}: {len(F):3d} pts, {dt:.1f}s "
            f"[total {elapsed/60:.1f}m, ETA {eta:.1f}m]"
        )

    # 4. Joint-normalised HV across seeds
    joint = np.vstack([np.asarray(f) for f in all_fronts if len(f) > 0])
    if len(joint) == 0:
        raise RuntimeError("Every seed produced an empty Pareto front.")
    joint_ideal = joint.min(axis=0)
    joint_nadir = joint.max(axis=0)
    all_hvs = [
        float(compute_hypervolume(
            np.asarray(f),
            ideal_point=joint_ideal,
            nadir_point=joint_nadir,
        )) if len(f) > 0 else 0.0
        for f in all_fronts
    ]
    front_sizes = [len(f) for f in all_fronts]

    # 5. Persist results
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_pkl = RESULTS_DIR / "delhivery_nsga2_all_results.pkl"
    with open(out_pkl, "wb") as f:
        pickle.dump(
            {
                "fronts": all_fronts,
                "hvs": all_hvs,
                "front_sizes": front_sizes,
                "joint_ideal": joint_ideal.tolist(),
                "joint_nadir": joint_nadir.tolist(),
                "n_seeds": args.seeds,
                "pop_size": args.pop_size,
                "n_gen": args.gen,
                "n_warehouses": n_w,
                "n_customers": n_c,
                "seed_durations_sec": seed_durations,
                "total_minutes": (time.time() - t_total) / 60.0,
            },
            f,
        )
    print(f"\n  Saved      : {out_pkl}")

    # 6. Print headline summary
    hvs = np.array(all_hvs)
    sizes = np.array(front_sizes)
    print(
        f"\n  HEADLINE   : "
        f"HV mean={hvs.mean():.4f} std={hvs.std():.4f}  |  "
        f"front size mean={sizes.mean():.1f} (range {sizes.min()}-{sizes.max()})"
    )

    # 7. LaTeX side-by-side comparison table.
    # Read the primary-network HV and front sizes from the existing
    # training_summary.json for an apples-to-apples row.
    primary_hv_mean = primary_hv_std = None
    primary_size_mean = None
    summary_path = RESULTS_DIR / "training_summary.json"
    if summary_path.exists():
        with open(summary_path) as f:
            summary = json.load(f)
        primary_hv_mean = summary.get("nsga2", {}).get("mean_hv")
        primary_size_mean = summary.get("nsga2", {}).get("mean_front_size")

    body_rows = []
    if primary_hv_mean is not None:
        body_rows.append(
            f"Dalal (2022) primary "
            f"& 5 & 100 & {primary_hv_mean:.4f} & "
            f"{primary_size_mean:.1f} \\\\"
        )
    body_rows.append(
        f"Delhivery secondary "
        f"& {n_w} & {n_c} & {hvs.mean():.4f} $\\pm$ {hvs.std():.4f} & "
        f"{sizes.mean():.1f} \\\\"
    )

    tex = (
        "\\begin{table}[htbp]\n"
        "\\centering\n"
        "\\caption{Cross-validation on a secondary Indian network. "
        "NSGA-II hypervolume and Pareto-front size on the Delhivery "
        "10-hub $\\times$ 150-customer network calibrated against "
        "144{,}867 real shipments \\citep{Delhivery2022} compared with "
        "the primary Dalal (2022) 5-warehouse $\\times$ 100-customer "
        "network. Hypervolumes are joint-normalised within each "
        "network (Audit 3.3) and are not directly comparable across "
        "rows because the joint ideal/nadir points differ; the test "
        "is whether the per-network HV remains in the same "
        "magnitude band, indicating the algorithm generalises beyond "
        "the primary topology.}\n"
        "\\label{tab:secondary_network_validation}\n"
        "\\begin{tabular}{lcccc}\n"
        "\\hline\n"
        "Network & $|W|$ & $|C|$ & Joint-norm. HV & Mean front size \\\\\n"
        "\\hline\n"
        + "\n".join(body_rows) + "\n"
        "\\hline\n"
        "\\end{tabular}\n"
        "\\end{table}\n"
    )
    TABLES_DIR.mkdir(parents=True, exist_ok=True)
    out_tex = TABLES_DIR / "secondary_network_validation.tex"
    out_tex.write_text(tex)
    print(f"  Table      : {out_tex}")


if __name__ == "__main__":
    main()
