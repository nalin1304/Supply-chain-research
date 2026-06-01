"""Facebook Prophet forecasting wrapper for demand prediction.

Implements ProphetForecaster extending BaseForecaster, with a robust fallback
to SeasonalNaiveForecaster if the `prophet` library is not installed.
"""

import numpy as np
import pandas as pd
from loguru import logger

from supply_chain_research.phase3_ai.forecaster_base import BaseForecaster
from supply_chain_research.phase3_ai.naive_forecasters import SeasonalNaiveForecaster

try:
    from prophet import Prophet
    PROPHET_AVAILABLE = True
except ImportError:
    PROPHET_AVAILABLE = False
    logger.warning("Prophet is not installed. ProphetForecaster will use SeasonalNaiveForecaster fallback.")


class ProphetForecaster(BaseForecaster):
    """Facebook Prophet wrapper forecaster with holiday/seasonality options."""

    def __init__(self, yearly_seasonality: bool = True, weekly_seasonality: bool = True, add_holidays: bool = True):
        self.yearly_seasonality = yearly_seasonality
        self.weekly_seasonality = weekly_seasonality
        self.add_holidays = add_holidays
        self.fallback = None
        self.train_data = None
        self.models = {}

    def fit(self, train_data: np.ndarray, val_data: np.ndarray = None) -> None:
        self.train_data = train_data

        if not PROPHET_AVAILABLE:
            self.fallback = SeasonalNaiveForecaster(period=7)
            self.fallback.fit(train_data, val_data)
            return

        n_customers = train_data.shape[1]
        logger.info(f"Fitting Prophet models for {n_customers} customers...")

        # Create a helper date range (Prophet expects actual datetimes in 'ds' column)
        dates = pd.date_range(start="2023-01-01", periods=len(train_data), freq="D")

        for c in range(n_customers):
            # Format dataframe as expected by Prophet: cols ['ds', 'y']
            df = pd.DataFrame({
                "ds": dates,
                "y": train_data[:, c]
            })

            try:
                model = Prophet(
                    yearly_seasonality=self.yearly_seasonality,
                    weekly_seasonality=self.weekly_seasonality,
                )
                if self.add_holidays:
                    model.add_country_holidays(country_name="IN")  # default to India holidays
                model.fit(df)
                self.models[c] = model
            except Exception as e:
                logger.warning(f"Prophet fit failed for customer {c}, using fallback: {e}")
                self.models[c] = None

    def predict(self, horizon: int) -> np.ndarray:
        if not PROPHET_AVAILABLE:
            return self.fallback.predict(horizon)

        n_customers = self.train_data.shape[1]
        predictions = np.zeros((horizon, n_customers))

        for c in range(n_customers):
            model = self.models.get(c)
            if model is not None:
                try:
                    # Create future dataframe for predictions
                    future = model.make_future_dataframe(periods=horizon, include_history=False)
                    forecast = model.predict(future)
                    predictions[:, c] = np.maximum(0.0, forecast["yhat"].to_numpy())
                except Exception as e:
                    logger.warning(f"Prophet predict failed for customer {c}, using naive fallback: {e}")
                    predictions[:, c] = self.train_data[-1, c]
            else:
                predictions[:, c] = self.train_data[-1, c]

        return predictions
