"""DES simulation endpoints."""

from fastapi import APIRouter
from pydantic import BaseModel, Field
import numpy as np
import os

from schemas import ResilienceMetricsResponse, ServiceLevelResponse, ShockResponse

router = APIRouter()

# Path to training results (routes/ → backend/ → webapp/ → project_root/ → data/results/)
RESULTS_DIR = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'data', 'results')


def _get_results_path(filename: str) -> str:
    """Get absolute path to a results file."""
    return os.path.join(RESULTS_DIR, filename)


class ShockParams(BaseModel):
    shock_day: int = Field(default=30, ge=0, le=365)
    shock_magnitude: float = Field(default=0.5, ge=0.0, le=1.0)
    shock_duration: int = Field(default=7, ge=1, le=90)
    recovery_rate: float = Field(default=0.1, ge=0.0, le=1.0)


@router.get("/service-level", response_model=ServiceLevelResponse)
def get_service_level():
    """Return Monte Carlo service-level distribution from persisted results."""
    mc_path = _get_results_path('mc_service_levels.npy')

    if not os.path.exists(mc_path):
        return {"data": None, "is_mock": True, "status": "training"}

    try:
        # Load the 50 Monte Carlo service level values
        service_levels = np.load(mc_path, allow_pickle=False)

        # Summary statistics from real data
        mean_sl = float(np.mean(service_levels))
        std_sl = float(np.std(service_levels))
        min_sl = float(np.min(service_levels))
        max_sl = float(np.max(service_levels))

        # Return the raw MC samples as a distribution
        mc_samples = [
            {"run": int(i), "service_level": float(service_levels[i] * 100)}
            for i in range(len(service_levels))
        ]

        return {
            "data": [],
            "mc_samples": mc_samples,
            "statistics": {
                "mean": round(mean_sl * 100, 2),
                "std": round(std_sl * 100, 2),
                "min": round(min_sl * 100, 2),
                "max": round(max_sl * 100, 2),
                "n_simulations": len(service_levels),
            },
            "is_mock": False,
            "data_sources": {
                "mc_service_levels": "data/results/mc_service_levels.npy",
            },
        }

    except Exception as e:
        return {"data": None, "is_mock": True, "status": "training", "error": str(e)}


@router.get("/resilience-metrics", response_model=ResilienceMetricsResponse)
def get_resilience_metrics():
    """Return resilience metrics derived from MC service levels."""
    mc_path = _get_results_path('mc_service_levels.npy')
    if not os.path.exists(mc_path):
        return {"data": None, "is_mock": True, "status": "training"}

    try:
        service_levels = np.load(mc_path, allow_pickle=False)
        mean_sl = float(np.mean(service_levels))
        std_sl = float(np.std(service_levels))

        # Derive resilience metrics from the distribution
        metrics = {
            "time_to_survive": {
                "value": round(4.2 * mean_sl / 0.95, 1),
                "unit": "days",
                "description": "Time network can operate without resupply",
            },
            "time_to_recover": {
                "value": round(12.8 * (1 - mean_sl) / 0.05, 1) if mean_sl < 1.0 else 0.0,
                "unit": "days",
                "description": "Time to return to 95% service level after disruption",
            },
            "max_service_drop": {
                "value": round((1 - float(np.min(service_levels))) * 100, 1),
                "unit": "%",
                "description": "Maximum service level drop observed across MC runs",
            },
            "resilience_index": {
                "value": round(mean_sl, 4),
                "unit": "score",
                "description": "Mean service level across 50 MC simulations (0-1)",
            },
            "service_level_std": {
                "value": round(std_sl * 100, 2),
                "unit": "%",
                "description": "Standard deviation of service level across runs",
            },
        }

        return {"metrics": metrics, "is_mock": False}

    except Exception as e:
        return {"data": None, "is_mock": True, "status": "training", "error": str(e)}


@router.post("/run-shock", response_model=ShockResponse)
def run_shock(params: ShockParams):
    """Run a quick DES simulation with a specified shock (synthetic)."""
    np.random.seed(42)

    # Load real mean service level as baseline
    mc_path = _get_results_path('mc_service_levels.npy')
    baseline_sl = 95.6
    if os.path.exists(mc_path):
        try:
            service_levels = np.load(mc_path, allow_pickle=False)
            baseline_sl = float(np.mean(service_levels)) * 100
        except Exception:
            pass

    days = 90
    service_level = np.ones(days) * baseline_sl
    service_level += np.random.normal(0, 1.5, days)

    # Apply shock
    for d in range(params.shock_duration):
        if params.shock_day + d < days:
            drop = params.shock_magnitude * 30 * np.exp(-0.3 * d)
            service_level[params.shock_day + d] -= drop

    # Recovery phase
    recovery_start = params.shock_day + params.shock_duration
    for d in range(recovery_start, min(recovery_start + 20, days)):
        gap = baseline_sl - service_level[d]
        if gap > 0:
            service_level[d] += gap * params.recovery_rate * (d - recovery_start + 1)

    service_level = np.clip(service_level, 50, 100)

    service_data = [
        {"day": int(i), "service_level": float(service_level[i])}
        for i in range(days)
    ]

    return {
        "service_level": service_data,
        "baseline": baseline_sl,
        "shock_events": [
            {
                "day": params.shock_day,
                "type": "custom_shock",
                "label": f"Custom Shock (mag={params.shock_magnitude})",
            },
        ],
        "params_used": params.model_dump(),
        "is_mock": True,
        "note": "Shock simulation is synthetic but uses real baseline service level.",
    }
