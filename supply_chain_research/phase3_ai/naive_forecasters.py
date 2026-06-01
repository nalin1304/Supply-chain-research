"""Naive and simple baseline forecasting methods for demand prediction.

Implements Naive, Seasonal Naive, Simple Moving Average, and Weighted Moving Average
forecasters extending BaseForecaster.
"""

import numpy as np
from supply_chain_research.phase3_ai.forecaster_base import BaseForecaster


class NaiveForecaster(BaseForecaster):
    """Naive forecaster: predicts the last observed value for all future steps."""

    def fit(self, train_data: np.ndarray, val_data: np.ndarray = None) -> None:
        self.last_value = train_data[-1]

    def predict(self, horizon: int) -> np.ndarray:
        # shape: (horizon, n_customers)
        return np.repeat(self.last_value[None, :], horizon, axis=0)


class SeasonalNaiveForecaster(BaseForecaster):
    """Seasonal Naive forecaster: predicts values from the previous seasonal cycle (period)."""

    def __init__(self, period: int = 7):
        self.period = period

    def fit(self, train_data: np.ndarray, val_data: np.ndarray = None) -> None:
        self.history = train_data[-self.period:]

    def predict(self, horizon: int) -> np.ndarray:
        # Repeat the last period cycle until horizon is reached
        predictions = []
        for h in range(horizon):
            idx = h % self.period
            predictions.append(self.history[idx])
        return np.array(predictions)


class SimpleMovingAverageForecaster(BaseForecaster):
    """Simple Moving Average forecaster: predicts the average of the last window steps."""

    def __init__(self, window: int = 14):
        self.window = window

    def fit(self, train_data: np.ndarray, val_data: np.ndarray = None) -> None:
        self.history = train_data[-self.window:]

    def predict(self, horizon: int) -> np.ndarray:
        # Recursively forecast using the moving average
        predictions = []
        current_history = list(self.history)
        for _ in range(horizon):
            avg = np.mean(current_history[-self.window:], axis=0)
            predictions.append(avg)
            current_history.append(avg)
        return np.array(predictions)


class WeightedMovingAverageForecaster(BaseForecaster):
    """Weighted Moving Average forecaster: exponential decay weights on the last window steps."""

    def __init__(self, window: int = 14, decay: float = 0.9):
        self.window = window
        self.decay = decay

    def fit(self, train_data: np.ndarray, val_data: np.ndarray = None) -> None:
        self.history = train_data[-self.window:]

    def predict(self, horizon: int) -> np.ndarray:
        # Exponentially decaying weights (most recent observations have highest weight)
        weights = self.decay ** np.arange(self.window)[::-1]
        weights /= weights.sum()

        predictions = []
        current_history = list(self.history)
        for _ in range(horizon):
            recent = np.array(current_history[-self.window:])
            weighted_avg = np.sum(recent * weights[:, None], axis=0)
            predictions.append(weighted_avg)
            current_history.append(weighted_avg)
        return np.array(predictions)
