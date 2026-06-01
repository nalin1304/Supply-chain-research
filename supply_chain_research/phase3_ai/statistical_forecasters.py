"""Classical statistical forecasting models for demand prediction.

Implements ARIMAForecaster (with AIC-based order search), ETSForecaster (Holt-Winters),
and ThetaForecaster (ThetaModel) extending BaseForecaster.
"""

import numpy as np
import pandas as pd
from loguru import logger
from statsmodels.tsa.arima.model import ARIMA
from statsmodels.tsa.holtwinters import ExponentialSmoothing
from statsmodels.tsa.forecasting.theta import ThetaModel

from supply_chain_research.phase3_ai.forecaster_base import BaseForecaster


class ARIMAForecaster(BaseForecaster):
    """ARIMA forecaster with automatic (p, d, q) order selection based on AIC."""

    def __init__(self, max_p: int = 2, max_d: int = 1, max_q: int = 2):
        self.max_p = max_p
        self.max_d = max_d
        self.max_q = max_q
        self.models = {}

    def fit(self, train_data: np.ndarray, val_data: np.ndarray = None) -> None:
        self.train_data = train_data
        n_customers = train_data.shape[1]

        logger.info(f"Fitting ARIMA models for {n_customers} customers...")
        for c in range(n_customers):
            series = train_data[:, c]

            # Simple grid search for best (p, d, q) order based on AIC
            best_aic = np.inf
            best_order = (1, 1, 1)

            # Try a subset of combinations to keep it fast
            for p in range(self.max_p + 1):
                for d in range(self.max_d + 1):
                    for q in range(self.max_q + 1):
                        try:
                            model = ARIMA(series, order=(p, d, q))
                            res = model.fit()
                            if res.aic < best_aic:
                                best_aic = res.aic
                                best_order = (p, d, q)
                        except Exception:
                            continue

            # Fit the best model
            try:
                best_model = ARIMA(series, order=best_order).fit()
                self.models[c] = best_model
            except Exception as e:
                logger.warning(f"ARIMA fit failed for customer {c}, using naive fallback: {e}")
                self.models[c] = None

    def predict(self, horizon: int) -> np.ndarray:
        n_customers = self.train_data.shape[1]
        predictions = np.zeros((horizon, n_customers))

        for c in range(n_customers):
            model = self.models.get(c)
            if model is not None:
                try:
                    forecast = model.forecast(steps=horizon)
                    predictions[:, c] = np.maximum(0.0, forecast)
                except Exception as e:
                    logger.warning(f"ARIMA predict failed for customer {c}, using naive fallback: {e}")
                    predictions[:, c] = self.train_data[-1, c]
            else:
                # Fallback to naive last value
                predictions[:, c] = self.train_data[-1, c]

        return predictions


class ETSForecaster(BaseForecaster):
    """Exponential Smoothing (ETS / Holt-Winters) forecaster."""

    def __init__(self, seasonal_periods: int = 7):
        self.seasonal_periods = seasonal_periods
        self.models = {}
        self.last_values = []

    def fit(self, train_data: np.ndarray, val_data: np.ndarray = None) -> None:
        self.train_data = train_data
        n_customers = train_data.shape[1]

        logger.info(f"Fitting ETS models for {n_customers} customers...")
        for c in range(n_customers):
            series = train_data[:, c]
            self.last_values.append(series[-1])

            try:
                # Holt-Winters additive model
                model = ExponentialSmoothing(
                    series,
                    trend="add",
                    seasonal="add",
                    seasonal_periods=self.seasonal_periods,
                    initialization_method="estimated",
                )
                res = model.fit()
                self.models[c] = res
            except Exception as e:
                logger.warning(f"ETS fit failed for customer {c}, using trend-only: {e}")
                try:
                    # Fallback to trend-only without seasonality
                    model = ExponentialSmoothing(series, trend="add", initialization_method="estimated")
                    res = model.fit()
                    self.models[c] = res
                except Exception:
                    self.models[c] = None

    def predict(self, horizon: int) -> np.ndarray:
        n_customers = self.train_data.shape[1]
        predictions = np.zeros((horizon, n_customers))

        for c in range(n_customers):
            model = self.models.get(c)
            if model is not None:
                try:
                    forecast = model.forecast(steps=horizon)
                    predictions[:, c] = np.maximum(0.0, forecast)
                except Exception as e:
                    logger.warning(f"ETS predict failed for customer {c}, using naive fallback: {e}")
                    predictions[:, c] = self.last_values[c]
            else:
                predictions[:, c] = self.last_values[c]

        return predictions


class ThetaForecaster(BaseForecaster):
    """Theta Method forecaster (Assimakopoulos & Nikolopoulos 2000)."""

    def __init__(self, period: int = 7):
        self.period = period
        self.train_data = None
        self.last_values = []

    def fit(self, train_data: np.ndarray, val_data: np.ndarray = None) -> None:
        self.train_data = train_data
        self.last_values = [train_data[-1, c] for c in range(train_data.shape[1])]

    def predict(self, horizon: int) -> np.ndarray:
        n_customers = self.train_data.shape[1]
        predictions = np.zeros((horizon, n_customers))

        for c in range(n_customers):
            series = self.train_data[:, c]
            try:
                # ThetaModel requires a pandas Series with a freq or integer index
                df = pd.Series(series)
                model = ThetaModel(df, period=self.period)
                res = model.fit()
                forecast = res.forecast(steps=horizon)
                predictions[:, c] = np.maximum(0.0, forecast.to_numpy())
            except Exception as e:
                logger.warning(f"Theta predict failed for customer {c}, using naive fallback: {e}")
                predictions[:, c] = self.last_values[c]

        return predictions
