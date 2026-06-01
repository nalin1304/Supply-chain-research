"""Base forecaster interface for demand prediction.

Defines the ForecastResult container and the BaseForecaster abstract base class,
including comprehensive evaluation metrics (MAPE, SMAPE, MASE, RMSE, MAE).
"""

from abc import ABC, abstractmethod
import numpy as np
from dataclasses import dataclass, field


@dataclass
class ForecastResult:
    """Unified container for forecasting results."""

    predictions: np.ndarray  # shape (horizon, n_customers) or (n_samples, horizon, n_customers)
    actuals: np.ndarray = None  # same shape as predictions
    metrics: dict = field(default_factory=dict)
    confidence_lower: np.ndarray = None
    confidence_upper: np.ndarray = None


class BaseForecaster(ABC):
    """Abstract base class for all demand forecasting methods."""

    @abstractmethod
    def fit(self, train_data: np.ndarray, val_data: np.ndarray = None) -> None:
        """Fit the forecaster on training time series.

        Parameters
        ----------
        train_data : np.ndarray
            Historical demand series of shape (n_days, n_customers).
        val_data : np.ndarray, optional
            Validation demand series of shape (n_val_days, n_customers).
        """
        pass

    @abstractmethod
    def predict(self, horizon: int) -> np.ndarray:
        """Predict future demand.

        Parameters
        ----------
        horizon : int
            Number of future days to predict.

        Returns
        -------
        np.ndarray
            Predicted demand of shape (horizon, n_customers).
        """
        pass

    def evaluate(self, actuals: np.ndarray, predictions: np.ndarray, train_history: np.ndarray = None) -> dict:
        """Evaluate predictions against actuals using 5 standard metrics.

        Parameters
        ----------
        actuals : np.ndarray
            True future values of shape (horizon, n_customers).
        predictions : np.ndarray
            Predicted values of shape (horizon, n_customers).
        train_history : np.ndarray, optional
            In-sample historical training data, used to compute MASE denominator.

        Returns
        -------
        dict
            Dict containing MAE, RMSE, MAPE, SMAPE, and MASE metrics.
        """
        actuals = np.asarray(actuals, dtype=np.float64)
        predictions = np.asarray(predictions, dtype=np.float64)

        mae = np.mean(np.abs(actuals - predictions))
        rmse = np.sqrt(np.mean((actuals - predictions) ** 2))

        # Safe MAPE: avoid division by zero
        eps = 1e-9
        mape = np.mean(np.abs(actuals - predictions) / np.maximum(np.abs(actuals), eps))

        # SMAPE
        smape = np.mean(2.0 * np.abs(actuals - predictions) / np.maximum(np.abs(actuals) + np.abs(predictions), eps))

        # MASE (using in-sample naive forecast as scaling factor)
        mase = 0.0
        if train_history is not None and len(train_history) > 1:
            # Denominator: Mean Absolute Error of in-sample one-step naive forecast
            naive_errors = np.abs(train_history[1:] - train_history[:-1])
            mase_denom = np.mean(naive_errors)
            if mase_denom > eps:
                mase = mae / mase_denom
        else:
            # Fallback if no history is provided: use actuals sequential diff
            if len(actuals) > 1:
                mase_denom = np.mean(np.abs(actuals[1:] - actuals[:-1]))
                if mase_denom > eps:
                    mase = mae / mase_denom

        return {
            "MAE": float(mae),
            "RMSE": float(rmse),
            "MAPE": float(mape),
            "SMAPE": float(smape),
            "MASE": float(mase),
        }
