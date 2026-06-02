"""Statistical comparison framework for forecasting methods.

Enables rigorous evaluation of different forecasting algorithms using expanding-window
cross-validation, standard metrics, and the Diebold-Mariano statistical test.

References
----------
.. [1] Diebold, F. X. & Mariano, R. S. (1995). Comparing Predictive Accuracy.
       Journal of Business & Economic Statistics, 13(3), 253-263.
.. [2] Tashman, L. J. (2000). Out-of-sample Forecasting: The Trial of More
       Forecast Methods. International Journal of Forecasting, 16(4), 437-450.
"""

from dataclasses import dataclass

import matplotlib.pyplot as plt
import numpy as np
import scipy.stats as stats
from loguru import logger

from supply_chain_research.phase3_ai.forecaster_base import BaseForecaster


@dataclass
class ForecastComparisonResult:
    """Unified container for all forecasting comparison results.
    Parameters
    ----------
    """

    forecasters: list[str]
    metrics: dict[str, dict[str, float]]  # {forecaster_name: {MAE: xx, RMSE: xx, ...}}
    predictions: dict[str, np.ndarray]  # {forecaster_name: predictions_array}
    actuals: np.ndarray


@dataclass
class DMResult:
    """
    Parameters
    ----------
    """
    statistic: float
    p_value: float
    significant: bool


def diebold_mariano_test(errors1: np.ndarray, errors2: np.ndarray, h: int = 1) -> DMResult:
    """Perform the Diebold-Mariano test for predictive accuracy (Diebold & Mariano 1995).

    Parameters
    ----------
    errors1, errors2 : np.ndarray
        1-D arrays of forecasting errors (actual - prediction) for model 1 and model 2.
    h : int
        Forecast horizon (used to compute autocovariance lag adjustment).

    Returns
    -------
    DMResult
        Container with test statistic, p-value, and significance flag.
    """
    e1 = np.asarray(errors1, dtype=np.float64)
    e2 = np.asarray(errors2, dtype=np.float64)

    # Loss differential (using squared error)
    d = e1**2 - e2**2
    d_mean = np.mean(d)
    n = len(d)

    if n <= 1:
        return DMResult(0.0, 1.0, False)

    # Compute autocovariance up to lag h-1 to adjust for multi-step autocorrelation
    gamma = np.zeros(h)
    gamma[0] = np.var(d)

    for lag in range(1, h):
        if n - lag > 0:
            gamma[lag] = np.mean((d[lag:] - d_mean) * (d[:-lag] - d_mean))

    # Variance of the mean loss differential (Diebold-Mariano variance estimate)
    var_d = (gamma[0] + 2.0 * np.sum(gamma[1:])) / n

    if var_d <= 1e-9:
        return DMResult(0.0, 1.0, False)

    # Test statistic
    dm_stat = d_mean / np.sqrt(var_d)

    # Two-sided p-value
    p_val = 2.0 * (1.0 - stats.norm.cdf(np.abs(dm_stat)))

    return DMResult(
        statistic=float(dm_stat),
        p_value=float(p_val),
        significant=(p_val < 0.05),
    )


def expanding_window_cv(
    data: np.ndarray,
    forecaster: BaseForecaster,
    n_folds: int = 5,
    horizon: int = 7,
    seq_length: int = 30,
) -> list[dict]:
    """Perform expanding-window cross-validation (Tashman 2000).
    Parameters
    ----------
    """
    logger.info(f"Running expanding-window CV for {forecaster.__class__.__name__}...")
    n_days = len(data)
    fold_size = (n_days - seq_length - horizon) // n_folds

    fold_results = []

    for fold in range(n_folds):
        # Determine split index
        split_idx = seq_length + (fold + 1) * fold_size
        if split_idx + horizon > n_days:
            break

        train_data = data[:split_idx]
        val_data = data[split_idx:split_idx + horizon]  # subsequent actuals

        # Fit and predict
        forecaster.fit(train_data)
        preds = forecaster.predict(horizon)

        # Evaluate this fold
        metrics = forecaster.evaluate(actuals=val_data, predictions=preds, train_history=train_data)
        fold_results.append({
            "fold": fold,
            "metrics": metrics,
            "predictions": preds,
            "actuals": val_data,
        })

    return fold_results


def run_forecast_comparison(
    data: np.ndarray,
    forecasters: list[BaseForecaster],
    n_folds: int = 5,
    horizon: int = 7,
) -> ForecastComparisonResult:
    """Compare multiple forecasting methods using expanding-window cross-validation.
    Parameters
    ----------
    """
    logger.info("Starting forecasting comparison framework...")

    avg_metrics = {}
    all_predictions = {}
    var_names = [f.__class__.__name__ for f in forecasters]

    # Warm-up a single fold to capture prediction actuals
    first_cv = expanding_window_cv(data, forecasters[0], n_folds=n_folds, horizon=horizon)
    actuals = np.concatenate([f["actuals"] for f in first_cv], axis=0)

    for forecaster in forecasters:
        name = forecaster.__class__.__name__
        fold_res = expanding_window_cv(data, forecaster, n_folds=n_folds, horizon=horizon)

        # Aggregate metrics across folds
        aggregated = {}
        for metric_name in ["MAE", "RMSE", "MAPE", "SMAPE", "MASE"]:
            vals = [f["metrics"][metric_name] for f in fold_res]
            aggregated[metric_name] = float(np.mean(vals))

        avg_metrics[name] = aggregated
        all_predictions[name] = np.concatenate([f["predictions"] for f in fold_res], axis=0)

    return ForecastComparisonResult(
        forecasters=var_names,
        metrics=avg_metrics,
        predictions=all_predictions,
        actuals=actuals,
    )


def plot_forecast_comparison(results: ForecastComparisonResult, output_path: str = "outputs/forecast_comparison.png") -> None:
    """Generate and save forecasting comparison overlay plot.
    Parameters
    ----------
    """
    logger.info(f"Generating forecasting comparison plot at {output_path}...")
    plt.figure(figsize=(10, 5))

    # Plot actuals (first customer series)
    plt.plot(results.actuals[:, 0], label="Actual Demand", lw=2, color="black", linestyle="--")

    # Plot predictions from top-3 models for clarity
    for name in results.forecasters[:4]:
        plt.plot(results.predictions[name][:, 0], label=f"Predicted ({name})", alpha=0.8)

    plt.xlabel("Days (CV Horizon)")
    plt.ylabel("Demand (kg)")
    plt.title("Demand Forecast vs Actual Overlay (Customer 0)")
    plt.grid(True, linestyle="--", alpha=0.5)
    plt.legend()

    plt.tight_layout()
    plt.savefig(output_path, dpi=300)
    plt.close()
