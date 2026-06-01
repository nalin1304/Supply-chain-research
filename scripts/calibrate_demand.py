"""Calibrate demand distribution parameters from DataCo Supply Chain dataset.

Fits LogNormal, Gamma, and Weibull distributions to real order quantities
aggregated at the weekly customer level, then updates config recommendations.

Usage:
    python scripts/calibrate_demand.py
"""

import numpy as np
import pandas as pd
from scipy import stats
import json
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATACO_PATH = os.path.join(
    PROJECT_ROOT, "data", "external", "dataco", "DataCoSupplyChainDataset.csv"
)
OUTPUT_PATH = os.path.join(PROJECT_ROOT, "data", "processed", "demand_calibration.json")


def load_dataco():
    """Load DataCo dataset and extract order quantities."""
    print("Loading DataCo dataset...")
    df = pd.read_csv(DATACO_PATH, encoding="latin-1", low_memory=False)
    print(f"  Loaded {len(df):,} orders, {df.columns.size} columns")
    return df


def compute_weekly_demand(df):
    """Aggregate orders to weekly demand per customer (in kg equivalent).

    DataCo has 'Order Item Quantity' (units) and 'Sales' (revenue).
    We convert to kg-equivalent using average product weight assumption:
    - Electronics: ~2 kg/unit
    - Clothing/Apparel: ~0.5 kg/unit
    - Sports/Outdoors: ~3 kg/unit
    - Other: ~1.5 kg/unit

    This gives a realistic demand distribution in kg for our supply chain model.
    """
    # Parse dates
    df["order_date"] = pd.to_datetime(df["order date (DateOrders)"], format="mixed")
    df["week"] = df["order_date"].dt.isocalendar().week.astype(int)
    df["year"] = df["order_date"].dt.year

    # Assign weight per unit based on category
    weight_map = {
        "Electronics": 2.0,
        "Computers": 3.5,
        "Cell Phones": 0.3,
        "Cameras": 1.0,
        "Video Games": 0.5,
        "Music": 0.2,
        "Sporting Goods": 3.0,
        "Outdoors": 2.5,
        "Fitness": 5.0,
        "Golf": 2.0,
        "Fan Shop": 1.0,
        "Footwear": 1.2,
        "Apparel": 0.5,
        "Clothing": 0.5,
        "Health and Beauty": 0.8,
        "Garden": 4.0,
        "Furniture": 15.0,
        "Home": 3.0,
        "Kitchen": 2.0,
        "Office Supplies": 1.5,
        "Pet Supplies": 2.0,
        "Toys": 1.0,
        "Baby": 1.5,
        "Books": 0.8,
    }

    # Map category to weight (default 1.5 kg)
    df["weight_per_unit"] = df["Category Name"].map(weight_map).fillna(1.5)
    df["demand_kg"] = df["Order Item Quantity"] * df["weight_per_unit"]

    # Aggregate: weekly demand per customer
    weekly = (
        df.groupby(["Customer Id", "year", "week"])["demand_kg"]
        .sum()
        .reset_index()
    )

    print(f"  Weekly demand records: {len(weekly):,}")
    print(f"  Unique customers: {weekly['Customer Id'].nunique():,}")
    print(f"  Demand range: {weekly['demand_kg'].min():.1f} - {weekly['demand_kg'].max():.1f} kg")
    print(f"  Mean weekly demand: {weekly['demand_kg'].mean():.1f} kg")
    print(f"  Median weekly demand: {weekly['demand_kg'].median():.1f} kg")

    return weekly["demand_kg"].values


def fit_distributions(demand_data):
    """Fit LogNormal, Gamma, and Weibull to the demand data."""
    # Filter positive values only
    data = demand_data[demand_data > 0]
    print(f"\n  Fitting distributions to {len(data):,} positive demand values...")

    results = {}

    # LogNormal fit
    shape, loc, scale = stats.lognorm.fit(data, floc=0)
    mu_ln = np.log(scale)
    sigma_ln = shape
    ks_stat, ks_p = stats.kstest(data, "lognorm", args=(shape, loc, scale))
    results["lognormal"] = {
        "mu": float(mu_ln),
        "sigma": float(sigma_ln),
        "scipy_params": {"shape": float(shape), "loc": float(loc), "scale": float(scale)},
        "ks_statistic": float(ks_stat),
        "ks_pvalue": float(ks_p),
        "mean_kg": float(np.exp(mu_ln + sigma_ln**2 / 2)),
    }
    print(f"  LogNormal: μ={mu_ln:.4f}, σ={sigma_ln:.4f}, KS p={ks_p:.4f}")

    # Gamma fit
    a, loc_g, scale_g = stats.gamma.fit(data, floc=0)
    ks_stat, ks_p = stats.kstest(data, "gamma", args=(a, loc_g, scale_g))
    results["gamma"] = {
        "shape": float(a),
        "scale": float(scale_g),
        "ks_statistic": float(ks_stat),
        "ks_pvalue": float(ks_p),
        "mean_kg": float(a * scale_g),
    }
    print(f"  Gamma: shape={a:.4f}, scale={scale_g:.4f}, KS p={ks_p:.4f}")

    # Weibull fit
    c, loc_w, scale_w = stats.weibull_min.fit(data, floc=0)
    ks_stat, ks_p = stats.kstest(data, "weibull_min", args=(c, loc_w, scale_w))
    results["weibull"] = {
        "shape": float(c),
        "scale": float(scale_w),
        "ks_statistic": float(ks_stat),
        "ks_pvalue": float(ks_p),
        "mean_kg": float(scale_w * float(stats.weibull_min.mean(c, loc=0, scale=1))),
    }
    print(f"  Weibull: shape={c:.4f}, scale={scale_w:.4f}, KS p={ks_p:.4f}")

    # Summary statistics
    results["empirical"] = {
        "n_samples": int(len(data)),
        "mean": float(np.mean(data)),
        "std": float(np.std(data)),
        "median": float(np.median(data)),
        "p5": float(np.percentile(data, 5)),
        "p25": float(np.percentile(data, 25)),
        "p75": float(np.percentile(data, 75)),
        "p95": float(np.percentile(data, 95)),
        "min": float(np.min(data)),
        "max": float(np.max(data)),
    }

    return results


def scale_to_supply_chain(results):
    """Scale weekly per-customer demand to match our supply chain model.

    Our model has 100 customers with daily demand in kg.
    DataCo has ~10K customers with weekly demand.

    Scaling: each of our 100 "customers" represents a cluster of ~100 real
    customers. So multiply per-customer weekly demand by ~100, then divide
    by 7 for daily.

    Target range: 100-10000 kg/day per customer (matching config clip bounds).
    """
    empirical_mean = results["empirical"]["mean"]
    # Scale factor: cluster of 100 customers, weekly → daily
    cluster_size = 100
    daily_factor = cluster_size / 7.0

    scaled_mean = empirical_mean * daily_factor
    scaled_std = results["empirical"]["std"] * daily_factor

    # Compute LogNormal params for the scaled distribution
    # If X ~ LogNormal(μ, σ), then c*X ~ LogNormal(μ + ln(c), σ)
    ln_mu = results["lognormal"]["mu"] + np.log(daily_factor)
    ln_sigma = results["lognormal"]["sigma"]

    results["scaled_for_model"] = {
        "description": "Scaled to represent 100-customer clusters, daily demand",
        "cluster_size": cluster_size,
        "lognormal_mu": float(ln_mu),
        "lognormal_sigma": float(ln_sigma),
        "expected_mean_kg": float(np.exp(ln_mu + ln_sigma**2 / 2)),
        "expected_median_kg": float(np.exp(ln_mu)),
        "clip_min": 100.0,
        "clip_max": 10000.0,
        "recommendation": f"Update config: order_size_mu={ln_mu:.4f}, order_size_sigma={ln_sigma:.4f}",
    }

    print(f"\n  Scaled for model (100-customer clusters, daily):")
    print(f"    LogNormal μ={ln_mu:.4f}, σ={ln_sigma:.4f}")
    print(f"    Expected mean: {np.exp(ln_mu + ln_sigma**2/2):.0f} kg/day")
    print(f"    Expected median: {np.exp(ln_mu):.0f} kg/day")

    return results


def main():
    """Run demand calibration pipeline."""
    print("=" * 60)
    print("DEMAND CALIBRATION FROM DATACO SUPPLY CHAIN DATASET")
    print("=" * 60)

    df = load_dataco()
    demand_data = compute_weekly_demand(df)
    results = fit_distributions(demand_data)
    results = scale_to_supply_chain(results)

    # Best fit recommendation
    fits = [(k, v["ks_pvalue"]) for k, v in results.items() if "ks_pvalue" in v]
    best_fit = max(fits, key=lambda x: x[1])
    results["best_fit"] = best_fit[0]
    print(f"\n  Best fit: {best_fit[0]} (KS p-value = {best_fit[1]:.6f})")

    # Save results
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n  Results saved to: {OUTPUT_PATH}")

    # Print config update recommendation
    print("\n" + "=" * 60)
    print("RECOMMENDED CONFIG UPDATES:")
    print("=" * 60)
    scaled = results["scaled_for_model"]
    print(f"  simulation.order_size_mu = {scaled['lognormal_mu']:.4f}")
    print(f"  simulation.order_size_sigma = {scaled['lognormal_sigma']:.4f}")
    print(f"  (Currently: mu=7.5, sigma=0.6)")
    print(f"  Citation: Constante et al. (2019), DataCo Smart Supply Chain, Kaggle.")
    print("=" * 60)


if __name__ == "__main__":
    main()
