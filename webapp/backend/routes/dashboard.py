"""Dashboard summary metrics endpoint."""

from fastapi import APIRouter
import numpy as np
import os
import json

from schemas import DashboardSummaryResponse, NetworkNodesResponse
from supply_chain_research.config import MasterConfig
from supply_chain_research.phase1_foundation.data_engineering import (
    generate_customer_locations,
    generate_demand,
)

router = APIRouter()

# Path to training results (routes/ → backend/ → webapp/ → project_root/ → data/results/)
RESULTS_DIR = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'data', 'results')


def _get_results_path(filename: str) -> str:
    """Get absolute path to a results file."""
    return os.path.join(RESULTS_DIR, filename)


def _load_training_status():
    """Check if training results exist based on actual files."""
    status = {
        "nsga2_complete": os.path.exists(_get_results_path('nsga2_best_front.npy')),
        "lstm_complete": os.path.exists(_get_results_path('lstm_predictions.npy')),
        "ppo_complete": os.path.exists(_get_results_path('ppo_small_final.pt')),
        "des_complete": os.path.exists(_get_results_path('mc_service_levels.npy')),
    }
    return status


def _load_json(filename: str):
    with open(_get_results_path(filename), "r", encoding="utf-8") as f:
        return json.load(f)


def _load_numeric_array(filename: str) -> np.ndarray:
    return np.load(_get_results_path(filename), allow_pickle=False)


def _summary_des_service_level(training_summary: dict) -> float | None:
    des = training_summary.get("des", {})
    for key in ("mean_sl", "mean_service_level"):
        if key in des:
            return round(float(des[key]) * 100.0, 1)
    return None


def _training_details(training_summary: dict) -> dict:
    ppo_details = {
        "small": training_summary.get("ppo_small", {}),
        "full": training_summary.get("ppo_full", {}),
        "baselines": training_summary.get("baselines", {}),
    }
    return {
        "nsga2": training_summary.get("nsga2", {}),
        "nsga3": training_summary.get("nsga3", {}),
        "moead": training_summary.get("moead", {}),
        "lstm": training_summary.get("lstm", {}),
        "ppo": ppo_details,
        "des": training_summary.get("des", {}),
    }


@router.get("/summary", response_model=DashboardSummaryResponse)
def get_summary():
    """Return dashboard summary metrics from persisted training artifacts."""
    training_status = _load_training_status()

    summary_path = _get_results_path('training_summary.json')
    pareto_path = _get_results_path('nsga2_best_front.npy')

    if not os.path.exists(summary_path) or not os.path.exists(pareto_path):
        return {
            "data": None,
            "is_mock": True,
            "status": "training",
            "error": "training_summary.json or nsga2_best_front.npy is missing",
        }

    try:
        training_summary = _load_json('training_summary.json')
        pareto_front = _load_numeric_array('nsga2_best_front.npy')
        if pareto_front.ndim != 2 or pareto_front.shape[1] < 2:
            raise ValueError("nsga2_best_front.npy must have shape (n, >=2)")

        cfg = MasterConfig()
        total_cost = float(np.min(pareto_front[:, 0]))
        total_emissions = float(np.min(pareto_front[:, 1]))
        service_level = _summary_des_service_level(training_summary)
        fleet_utilization = float(cfg.vehicle.hcv_utilization * 100.0)
        hcv_pct = int(round(cfg.network.hcv_lcv_fleet_ratio * 100))
        lcv_pct = 100 - hcv_pct

        summary = {
            "training_status": training_status,
            "kpis": {
                "total_cost": {
                    "value": total_cost,
                    "unit": "INR",
                    "change": 0.0,
                    "label": "Total Logistics Cost (Min-Cost Pareto Solution)",
                },
                "total_emissions": {
                    "value": total_emissions,
                    "unit": "kgCO2e",
                    "change": 0.0,
                    "label": "Carbon Emissions (Min-Emission Pareto Solution)",
                },
                "fleet_utilization": {
                    "value": fleet_utilization,
                    "unit": "%",
                    "change": 0.0,
                    "label": "Fleet Utilization (Config)",
                },
            },
            "network": {
                "warehouses": cfg.network.n_warehouses,
                "customers": cfg.network.n_customers,
                "routes_active": cfg.network.n_warehouses * cfg.network.n_customers,
                "vehicles": {"HCV_pct": hcv_pct, "LCV_pct": lcv_pct},
            },
            "training_details": _training_details(training_summary),
            "is_mock_data": False,
            "data_sources": {
                "summary": "data/results/training_summary.json",
                "pareto_front": "data/results/nsga2_best_front.npy",
            },
        }
        if service_level is not None:
            summary["kpis"]["service_level"] = {
                "value": service_level,
                "unit": "%",
                "change": 0.0,
                "label": "Service Level (DES Monte Carlo)",
            }

        return summary

    except Exception as e:
        return {
            "data": None,
            "is_mock": True,
            "status": "training",
            "error": str(e),
        }


@router.get("/network-nodes", response_model=NetworkNodesResponse)
def get_network_nodes():
    """Return warehouse and customer locations for the map."""
    PROJECT_ROOT = os.path.join(os.path.dirname(__file__), '..', '..', '..')
    data_dir = os.path.join(PROJECT_ROOT, 'data', 'processed')
    customer_file = os.path.join(data_dir, 'dalal_customer_locations.npy')
    demand_file = os.path.join(data_dir, 'dalal_demand.npy')

    cfg = MasterConfig()
    warehouses = []
    for i, (name, lat, lng) in enumerate(cfg.network.warehouse_locations[: cfg.network.n_warehouses]):
        warehouses.append({
            "id": f"W{i + 1}",
            "name": name,
            "lat": float(lat),
            "lng": float(lng),
            "capacity": float(cfg.network.warehouse_capacities[i]),
        })

    customers = []
    demand = None
    if os.path.exists(demand_file):
        try:
            demand = np.asarray(
                np.load(demand_file, allow_pickle=False)
            ).reshape(-1)
        except (OSError, ValueError):
            demand = None

    if os.path.exists(customer_file):
        try:
            locs = np.load(customer_file, allow_pickle=False)
            for i, loc in enumerate(locs[:50]):
                customers.append({
                    "id": f"C{i+1}",
                    "lat": float(loc[0]),
                    "lng": float(loc[1]),
                    "demand": float(demand[i]) if demand is not None and i < len(demand) else 0.0,
                })
        except (OSError, ValueError, IndexError):
            customers = []

    if not customers:
        rng = np.random.default_rng(cfg.random_seed)
        locs = generate_customer_locations(cfg, rng)
        demand = generate_demand(cfg, rng)
        for i, loc in enumerate(locs[:50]):
            customers.append({
                "id": f"C{i+1}",
                "lat": float(loc[0]),
                "lng": float(loc[1]),
                "demand": float(demand[i]) if i < len(demand) else 0.0,
            })

    return {"warehouses": warehouses, "customers": customers}
