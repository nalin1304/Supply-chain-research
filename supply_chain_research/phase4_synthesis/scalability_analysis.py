"""Empirical scalability analysis of optimization solvers.

Sweeps network scales from Small (3 warehouses, 30 customers) to Very Large (20 warehouses, 1000 customers),
measuring runtime scaling, memory footprint, and solution quality. Fits empirical complexity curves to
compare against theoretical Big-O limits.
"""

import json
import os
import time
from pathlib import Path
import numpy as np

from supply_chain_research.config import MasterConfig
from supply_chain_research.phase1_foundation.data_engineering import generate_network_data
from supply_chain_research.phase1_foundation.clarke_wright import solve_cvrp_clarke_wright
from supply_chain_research.phase1_foundation.nsga2_solver import run_nsga2
from supply_chain_research.phase1_foundation.moead_solver import run_moead

def run_scalability_sweep(config: MasterConfig = None, seed: int = 42) -> dict:
    """Run the scalability benchmarks across four network scales.

    Parameters
    ----------
    config : MasterConfig, optional
        Master configuration template.
    seed : int, optional
        RNG seed for reproducibility.

    Returns
    -------
    dict
        Scalability metrics and fitted complexity parameters.
    """
    if config is None:
        config = MasterConfig()

    scales = {
        "Small": {"n_w": 3, "n_c": 30},
        "Medium": {"n_w": 5, "n_c": 100},
        "Large": {"n_w": 10, "n_c": 300},
        "Very Large": {"n_w": 20, "n_c": 1000},
    }

    results = {
        "metadata": {
            "seed": seed,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        },
        "runs": {},
    }

    for scale_name, dims in scales.items():
        print(f"\nBenchmarking scale: {scale_name} ({dims['n_w']} WH, {dims['n_c']} Cust)...")
        n_w = dims["n_w"]
        n_c = dims["n_c"]

        # 1. Setup MasterConfig for this scale
        scale_config = config.model_copy(deep=True)
        scale_config.network.n_warehouses = n_w
        scale_config.network.n_customers = n_c
        scale_config.network.warehouse_locations = scale_config.network.warehouse_locations[:n_w]
        
        # Populate warehouse capacities and locations to match dims
        rng = np.random.default_rng(seed)
        scale_config.network.warehouse_capacities = list(rng.uniform(100000.0, 500000.0, size=n_w))
        
        # 2. Generate network data (synthesized offline to avoid slow/failing OSRM demo API requests)
        t0 = time.perf_counter()
        n_total = n_w + n_c
        
        # Symmetric random matrix with 0 diagonal for distances
        full_dist = rng.uniform(50.0, 500.0, size=(n_total, n_total))
        full_dist = (full_dist + full_dist.T) / 2.0
        np.fill_diagonal(full_dist, 0.0)
        
        # Duration matrix (distance / average speed * 3600 seconds)
        full_dur = full_dist * 60.0
        
        # Coordinates in India bounds
        cust_locs = np.zeros((n_c, 2))
        cust_locs[:, 0] = rng.uniform(8.0, 37.0, size=n_c)
        cust_locs[:, 1] = rng.uniform(68.0, 97.0, size=n_c)
        
        wh_locs = np.zeros((n_w, 2))
        wh_locs[:, 0] = rng.uniform(8.0, 37.0, size=n_w)
        wh_locs[:, 1] = rng.uniform(68.0, 97.0, size=n_w)
        
        # LogNormal demand
        demand = rng.lognormal(mean=np.log(1000.0), sigma=0.5, size=n_c)
        
        net_data = {
            "customer_locations": cust_locs,
            "warehouse_locations": wh_locs,
            "distance_matrix": full_dist,
            "duration_matrix": full_dur,
            "demand": demand,
        }
        net_gen_time = time.perf_counter() - t0

        # Memory footprint estimate of raw arrays (in KB)
        memory_kb = sum(arr.nbytes for arr in net_data.values() if isinstance(arr, np.ndarray)) / 1024.0

        # Extract matrices
        full_dist = net_data["distance_matrix"]
        if full_dist.shape[0] == n_w + n_c:
            dist_wc = full_dist[:n_w, n_w:]
        else:
            dist_wc = full_dist

        # 3. Benchmark Clarke-Wright CVRP Heuristic
        t0 = time.perf_counter()
        cw_res = solve_cvrp_clarke_wright(
            config=scale_config,
            distance_matrix=full_dist,
            demand=net_data["demand"],
            vehicle_type="HCV",
        )
        cw_time = time.perf_counter() - t0

        # 4. Benchmark NSGA-II (1 generation, small pop for Very Large compatibility)
        pop_size = 10
        n_gen = 1
        t0 = time.perf_counter()
        nsga_res = run_nsga2(
            scale_config,
            dist_wc,
            net_data["demand"],
            pop_size=pop_size,
            n_gen=n_gen,
            seed=seed,
        )
        nsga_gen_time = time.perf_counter() - t0

        # 5. Benchmark MOEA/D (1 generation, small pop)
        t0 = time.perf_counter()
        moead_res = run_moead(
            scale_config,
            dist_wc,
            net_data["demand"],
            pop_size=pop_size,
            n_gen=n_gen,
            seed=seed,
        )
        moead_gen_time = time.perf_counter() - t0

        results["runs"][scale_name] = {
            "n_warehouses": n_w,
            "n_customers": n_c,
            "network_generation_seconds": net_gen_time,
            "memory_kb": memory_kb,
            "clarke_wright_seconds": cw_time,
            "clarke_wright_cost": cw_res.get("total_cost", 0.0) if cw_res.get("feasible") else 0.0,
            "nsga2_generation_seconds": nsga_gen_time,
            "moead_generation_seconds": moead_gen_time,
        }

    # 6. Fit empirical complexity curves (e.g. for Clarke-Wright runtime: T = c * N^2)
    # We fit runtime of Clarke-Wright to T = c * (n_c^2) using least squares
    xs = np.array([dims["n_c"] for dims in scales.values()], dtype=float)
    ys_cw = np.array([results["runs"][name]["clarke_wright_seconds"] for name in scales], dtype=float)
    
    # Fit y = c * x^2
    c_cw = np.sum(ys_cw * (xs**2)) / np.sum(xs**4)
    results["complexity_fit"] = {
        "clarke_wright_constant": float(c_cw),
        "clarke_wright_fitted_model": f"T = {c_cw:.2e} * N^2",
    }

    return results

def dump_scalability_report(out_path: str = "data/results/scalability_results.json") -> dict:
    """Run scalability benchmarks and save the JSON report.

    Parameters
    ----------
    out_path : str, optional
        Path where the JSON report will be saved.

    Returns
    -------
    dict
        The benchmarking results dictionary.
    """
    config = MasterConfig()
    results = run_scalability_sweep(config)
    
    out_dir = Path(out_path).parent
    out_dir.mkdir(parents=True, exist_ok=True)
    
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2, sort_keys=True)
        
    print(f"Scalability report successfully saved to {out_path}")
    return results

if __name__ == "__main__":
    dump_scalability_report()
