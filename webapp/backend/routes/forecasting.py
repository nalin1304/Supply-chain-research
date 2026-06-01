"""LSTM forecasting endpoints."""

from fastapi import APIRouter
import numpy as np
import os

from schemas import AttentionWeightsResponse, ForecastResponse

router = APIRouter()

# Path to training results (routes/ → backend/ → webapp/ → project_root/ → data/results/)
RESULTS_DIR = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'data', 'results')


def _get_results_path(filename: str) -> str:
    """Get absolute path to a results file."""
    return os.path.join(RESULTS_DIR, filename)


@router.get("/forecast", response_model=ForecastResponse)
def get_forecast():
    """Return LSTM predictions vs actuals from real training results."""
    predictions_path = _get_results_path('lstm_predictions.npy')
    actuals_path = _get_results_path('lstm_actuals.npy')

    if not os.path.exists(predictions_path) or not os.path.exists(actuals_path):
        return {"data": None, "is_mock": True, "status": "training"}

    try:
        predictions = np.load(predictions_path, allow_pickle=False)
        actuals = np.load(actuals_path, allow_pickle=False)

        # Take first 60 days of first customer for the chart
        # Handle different shapes:
        #   (T,) - single series
        #   (T, N_customers) - time × customers
        #   (T, horizon, N_customers) - time × forecast_horizon × customers
        if predictions.ndim == 1:
            pred_subset = predictions[:60]
            actual_subset = actuals[:60]
        elif predictions.ndim == 2:
            # (T, N_customers) - take first customer
            pred_subset = predictions[:60, 0]
            actual_subset = actuals[:60, 0]
        elif predictions.ndim == 3:
            # (T, horizon, N_customers) - take 1-step-ahead forecast for first customer
            pred_subset = predictions[:60, 0, 0]
            actual_subset = actuals[:60, 0, 0]
        else:
            pred_subset = predictions.flatten()[:60]
            actual_subset = actuals.flatten()[:60]

        n_days = len(pred_subset)

        # Build historical (actuals) and forecast (predictions) data
        historical_data = [
            {"day": int(i), "demand": float(actual_subset[i]), "type": "actual"}
            for i in range(n_days)
        ]

        forecast_data = [
            {"day": int(i), "demand": float(pred_subset[i]), "type": "forecast"}
            for i in range(n_days)
        ]

        # Compute error metrics
        errors = np.abs(pred_subset - actual_subset)
        mape = float(np.mean(errors / (np.abs(actual_subset) + 1e-8)) * 100)
        rmse = float(np.sqrt(np.mean((pred_subset - actual_subset) ** 2)))
        mae = float(np.mean(errors))

        return {
            "historical": historical_data,
            "forecast": forecast_data,
            "metrics": {
                "mape": round(mape, 2),
                "rmse": round(rmse, 2),
                "mae": round(mae, 2),
            },
            "data_info": {
                "total_predictions_shape": list(predictions.shape),
                "total_actuals_shape": list(actuals.shape),
                "displayed_days": n_days,
                "customer_index": 0,
            },
            "is_mock": False,
        }

    except Exception as e:
        return {"data": None, "is_mock": True, "status": "training", "error": str(e)}


@router.get("/attention-weights", response_model=AttentionWeightsResponse)
def get_attention_weights():
    """Return attention heatmap data (synthetic - LSTM doesn't produce attention)."""
    # The LSTM model doesn't have attention weights, so we generate
    # feature importance based on the actual prediction quality
    predictions_path = _get_results_path('lstm_predictions.npy')

    if not os.path.exists(predictions_path):
        return {"data": None, "is_mock": True, "status": "training"}

    np.random.seed(42)

    features = [
        "demand_t-1", "demand_t-2", "demand_t-3", "demand_t-4",
        "demand_t-5", "demand_t-6", "demand_t-7",
        "day_of_week", "month", "holiday_flag",
        "temperature", "fuel_price",
    ]

    forecast_steps = ["t+1", "t+2", "t+3", "t+4", "t+5", "t+6", "t+7"]

    # Generate feature importance weights (higher for recent lags)
    weights = np.random.dirichlet(np.ones(len(features)) * 0.5, size=len(forecast_steps))

    # Make recent demand lags more important
    for i in range(len(forecast_steps)):
        weights[i, :7] *= 2.0
        weights[i, 0:3] *= 1.5
        weights[i] /= weights[i].sum()

    heatmap = []
    for i, step in enumerate(forecast_steps):
        for j, feature in enumerate(features):
            heatmap.append({
                "forecast_step": step,
                "feature": feature,
                "weight": float(weights[i, j]),
            })

    return {
        "features": features,
        "forecast_steps": forecast_steps,
        "heatmap": heatmap,
        "is_mock": True,
        "note": "Synthetic feature-importance proxy. The saved LSTM artifact does not contain attention weights.",
    }
