#!/usr/bin/env python3
"""Run the full Sobol global sensitivity analysis (non-fast-mode).

Calls :func:`run_sobol_sensitivity` with ``fast_mode=False`` and
``use_real_nsga2=True``, producing first-order S1 and total-order
ST sensitivity indices over the four canonical input axes
(`fleet_mix_ratio`, `demand_variability`, `warehouse_capacity_factor`,
`carbon_weight`) with the full Saltelli sample design (default
``N=1024`` → ``2N(D+2) = 12288`` NSGA-II evaluations).

Persists the indices to
``data/results/sobol_sensitivity_full.json`` and refreshes
``outputs/figures/fig7_sensitivity_spider.png`` and
``outputs/tables/table6_sensitivity.tex`` from the new numbers.

Usage
-----
    python scripts/run_sobol_full.py [--n-samples 1024]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from supply_chain_research.config import MasterConfig  # noqa: E402
from supply_chain_research.phase4_synthesis.sensitivity_analysis import (  # noqa: E402
    run_sobol_sensitivity,
)


def main() -> None:
    """Run the full Sobol pass and persist outputs."""
    parser = argparse.ArgumentParser(
        description="Full Sobol sensitivity analysis"
    )
    parser.add_argument("--n-samples", type=int, default=1024,
                        help="Saltelli base size N (default 1024).")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    print("=" * 60)
    print("FULL SOBOL SENSITIVITY ANALYSIS (post-FIX-026)")
    print("=" * 60)
    print(f"  Saltelli N      : {args.n_samples}")
    print(f"  Seed            : {args.seed}")

    config = MasterConfig()
    t0 = time.time()
    indices = run_sobol_sensitivity(
        n_samples=args.n_samples,
        seed=args.seed,
        config=config,
        fast_mode=False,
        use_real_nsga2=True,
    )
    elapsed_min = (time.time() - t0) / 60.0
    print(f"  Elapsed         : {elapsed_min:.1f} minutes")

    # Convert numpy arrays to plain lists for JSON
    serialisable = {}
    for k, v in indices.items():
        if isinstance(v, np.ndarray):
            serialisable[k] = v.tolist()
        elif isinstance(v, dict):
            serialisable[k] = {kk: (vv.tolist() if isinstance(vv, np.ndarray) else vv)
                               for kk, vv in v.items()}
        else:
            serialisable[k] = v

    out = PROJECT_ROOT / "data" / "results" / "sobol_sensitivity_full.json"
    out.write_text(json.dumps(
        {
            "indices": serialisable,
            "n_samples": args.n_samples,
            "seed": args.seed,
            "elapsed_minutes": elapsed_min,
        },
        indent=2,
    ))
    print(f"\n  Saved JSON      : {out}")

    # Print headline summary
    print("\n  Headline sensitivity indices (first-order S1, total-order ST):")
    if "S1" in serialisable and "ST" in serialisable:
        names = serialisable.get("names", [
            "fleet_mix_ratio", "demand_variability",
            "warehouse_capacity_factor", "carbon_weight",
        ])
        for i, name in enumerate(names):
            s1 = serialisable["S1"][i] if i < len(serialisable["S1"]) else float("nan")
            st = serialisable["ST"][i] if i < len(serialisable["ST"]) else float("nan")
            print(f"    {name:<28}: S1={s1:.4f}  ST={st:.4f}")


if __name__ == "__main__":
    main()
