"""NSGA-II optimization results endpoints."""

from fastapi import APIRouter
from pydantic import BaseModel, Field
import numpy as np
import os
import pickle

from schemas import HypervolumeResponse, ParetoFrontResponse

router = APIRouter()

# Path to training results (routes/ → backend/ → webapp/ → project_root/ → data/results/)
RESULTS_DIR = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'data', 'results')


def _get_results_path(filename: str) -> str:
    """Get absolute path to a results file."""
    return os.path.join(RESULTS_DIR, filename)


class ScenarioParams(BaseModel):
    population_size: int = Field(default=50, ge=2, le=1000)
    generations: int = Field(default=10, ge=1, le=500)
    carbon_weight: float = Field(default=0.5, ge=0.0, le=1.0)
    ev_ratio: float = Field(default=0.3, ge=0.0, le=1.0)
    demand_multiplier: float = Field(default=1.0, ge=0.1, le=10.0)


@router.get("/pareto-front", response_model=ParetoFrontResponse)
def get_pareto_front():
    """Return Pareto front points (cost vs carbon) from real NSGA-II results."""
    pareto_path = _get_results_path('nsga2_best_front.npy')

    if not os.path.exists(pareto_path):
        return {"data": None, "is_mock": True, "status": "training"}

    try:
        pareto_front = np.load(pareto_path, allow_pickle=False)
        # Shape: (N, 2) where col 0 = cost, col 1 = emissions
        points = []
        for i in range(pareto_front.shape[0]):
            points.append({
                "id": i,
                "cost": float(pareto_front[i, 0]),
                "carbon": float(pareto_front[i, 1]),
            })

        return {"points": points, "is_mock": False}

    except Exception as e:
        return {"data": None, "is_mock": True, "status": "training", "error": str(e)}


@router.get("/hypervolume", response_model=HypervolumeResponse)
def get_hypervolume():
    """Return hypervolume convergence history from all seed results."""
    results_path = _get_results_path('nsga2_all_results.pkl')

    if not os.path.exists(results_path):
        return {"data": None, "is_mock": True, "status": "training"}

    try:
        with open(results_path, 'rb') as f:
            all_results = pickle.load(f)

        # all_results has 'fronts' and 'hvs' keys
        # 'hvs' is a list of hypervolume values per seed (or per generation)
        hvs = all_results.get('hvs', [])

        # If hvs is a list of lists (per seed), compute mean across seeds
        if hvs and isinstance(hvs[0], (list, np.ndarray)):
            hvs_array = np.array(hvs)
            mean_hv = hvs_array.mean(axis=0).tolist()
            std_hv = hvs_array.std(axis=0).tolist()
            history = [
                {
                    "generation": i,
                    "hypervolume": float(mean_hv[i]),
                    "std": float(std_hv[i]),
                }
                for i in range(len(mean_hv))
            ]
        else:
            # hvs is a flat list (one value per seed)
            history = [
                {"seed": i, "hypervolume": float(hv)}
                for i, hv in enumerate(hvs)
            ]

        # Also include all fronts info
        fronts = all_results.get('fronts', [])
        n_seeds = len(fronts) if isinstance(fronts, list) else 0

        return {
            "history": history,
            "n_seeds": n_seeds,
            "is_mock": False,
        }

    except Exception as e:
        return {"data": None, "is_mock": True, "status": "training", "error": str(e)}


@router.post("/run-scenario", response_model=ParetoFrontResponse)
def run_scenario(params: ScenarioParams):
    """Run a quick NSGA-II scenario with custom parameters."""
    np.random.seed(int(params.carbon_weight * 1000))

    n_points = min(params.population_size, 30)
    t = np.linspace(0, 1, n_points)

    # Adjust based on parameters
    base_cost = 2_000_000 * params.demand_multiplier
    cost = base_cost + 1_500_000 * (1 - t) ** 1.5
    carbon = (800 + 1800 * t ** 1.3) * (1 - params.ev_ratio * 0.3)

    cost += np.random.normal(0, 30000, n_points)
    carbon += np.random.normal(0, 20, n_points)

    points = []
    for i in range(n_points):
        points.append({
            "id": i,
            "cost": float(cost[i]),
            "carbon": float(carbon[i]),
            "service_level": float(np.clip(90 + np.random.normal(0, 3), 82, 99)),
            "ev_fraction": float(params.ev_ratio + np.random.normal(0, 0.05)),
        })

    return {
        "points": points,
        "params_used": params.model_dump(),
        "is_mock": True,
        "note": "Scenario simulation uses synthetic generation. Real results from /pareto-front endpoint.",
    }
