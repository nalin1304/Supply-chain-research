"""Machine Learning tree-based forecasting models for demand prediction.

Implements XGBoostForecaster, LightGBMForecaster (with fallback),
and RandomForestForecaster using direct multi-step lag and rolling window
feature engineering.
"""

import numpy as np
from loguru import logger
from sklearn.ensemble import RandomForestRegressor
from sklearn.multioutput import MultiOutputRegressor

from supply_chain_research.phase3_ai.forecaster_base import BaseForecaster

# Optional imports with graceful fallbacks
try:
    import xgboost as xgb
    XGB_AVAILABLE = True
except ImportError:
    XGB_AVAILABLE = False
    logger.warning("XGBoost is not installed. XGBoostForecaster will fallback to RandomForest.")

try:
    import lightgbm as lgb
    LGB_AVAILABLE = True
except ImportError:
    LGB_AVAILABLE = False
    logger.warning("LightGBM is not installed. LightGBMForecaster will fallback to XGBoost/RandomForest.")


def engineer_features(series: np.ndarray, horizon: int, seq_length: int = 30):
    """Create lag and rolling features for tabular machine learning models.

    Parameters
    ----------
    series : np.ndarray
        1-D time series of shape (n_days,).
    horizon : int
        Forecast horizon (steps ahead).
    seq_length : int
        History lookback window.

    Returns
    -------
    X, y : np.ndarray
        Feature matrix of shape (n_samples, n_features) and target matrix of shape (n_samples, horizon).
    """
    n_days = len(series)
    X_list, y_list = [], []

    # Features: lags 1, 7, 14, 30; rolling mean/std of 7 and 30 days
    # To avoid data leakage, features are calculated strictly on the lookback window
    for t in range(seq_length, n_days - horizon + 1):
        window = series[t - seq_length:t]
        target = series[t:t + horizon]

        features = [
            window[-1],  # lag 1
            window[-7] if seq_length >= 7 else window[-1],  # lag 7
            window[-14] if seq_length >= 14 else window[-1],  # lag 14
            window[-30] if seq_length >= 30 else window[-1],  # lag 30
            np.mean(window[-7:]),  # rolling mean 7
            np.std(window[-7:]),  # rolling std 7
            np.mean(window[-30:]),  # rolling mean 30
            np.std(window[-30:]),  # rolling std 30
        ]

        X_list.append(features)
        y_list.append(target)

    return np.array(X_list), np.array(y_list)


class RandomForestForecaster(BaseForecaster):
    """Random Forest regressor with direct multi-step forecasting.
    Parameters
    ----------
    """

    def __init__(self, n_estimators: int = 100, max_depth: int = 10, seq_length: int = 30):
        """
        Parameters
        ----------
        """
        self.n_estimators = n_estimators
        self.max_depth = max_depth
        self.seq_length = seq_length
        self.models = {}
        self.train_history = None

    def fit(self, train_data: np.ndarray, val_data: np.ndarray = None) -> None:
        """
        Parameters
        ----------
        """
        self.train_history = train_data
        n_customers = train_data.shape[1]

        logger.info(f"Training Random Forest models for {n_customers} customers...")
        for c in range(n_customers):
            series = train_data[:, c]
            # Use horizon=7 for default feature mapping
            X, y = engineer_features(series, horizon=7, seq_length=self.seq_length)

            if len(X) == 0:
                logger.warning(f"Insufficient history to train RF for customer {c}.")
                self.models[c] = None
                continue

            model = RandomForestRegressor(
                n_estimators=self.n_estimators,
                max_depth=self.max_depth,
                random_state=42,
                n_jobs=-1,
            )
            model.fit(X, y)
            self.models[c] = model

    def predict(self, horizon: int) -> np.ndarray:
        """
        Parameters
        ----------
        """
        n_customers = self.train_history.shape[1]
        predictions = np.zeros((horizon, n_customers))

        for c in range(n_customers):
            series = self.train_history[:, c]
            # Feature vector of the very last sequence window
            window = series[-self.seq_length:]
            features = np.array([
                window[-1],
                window[-7],
                window[-14],
                window[-30],
                np.mean(window[-7:]),
                np.std(window[-7:]),
                np.mean(window[-30:]),
                np.std(window[-30:]),
            ]).reshape(1, -1)

            model = self.models.get(c)
            if model is not None:
                try:
                    pred = model.predict(features)[0]  # shape (7,) or multioutput shape
                    # Interpolate or slice to match target horizon
                    if len(pred) >= horizon:
                        predictions[:, c] = np.maximum(0.0, pred[:horizon])
                    else:
                        # Extrapolate using last value
                        predictions[:len(pred), c] = np.maximum(0.0, pred)
                        predictions[len(pred):, c] = pred[-1]
                except Exception as e:
                    logger.warning(f"RF predict failed for customer {c}: {e}")
                    predictions[:, c] = series[-1]
            else:
                predictions[:, c] = series[-1]

        return predictions


class XGBoostForecaster(BaseForecaster):
    """XGBoost regressor with direct multi-step forecasting.
    Parameters
    ----------
    """

    def __init__(self, n_estimators: int = 100, max_depth: int = 6, seq_length: int = 30):
        """
        Parameters
        ----------
        """
        self.n_estimators = n_estimators
        self.max_depth = max_depth
        self.seq_length = seq_length
        self.models = {}
        self.train_history = None

    def fit(self, train_data: np.ndarray, val_data: np.ndarray = None) -> None:
        """
        Parameters
        ----------
        """
        self.train_history = train_data
        n_customers = train_data.shape[1]

        if not XGB_AVAILABLE:
            # Fallback to RF
            self.fallback = RandomForestForecaster(n_estimators=self.n_estimators, max_depth=self.max_depth, seq_length=self.seq_length)
            self.fallback.fit(train_data, val_data)
            return

        logger.info(f"Training XGBoost models for {n_customers} customers...")
        for c in range(n_customers):
            series = train_data[:, c]
            X, y = engineer_features(series, horizon=7, seq_length=self.seq_length)

            if len(X) == 0:
                self.models[c] = None
                continue

            # XGBoost multi-output training
            base_model = xgb.XGBRegressor(
                n_estimators=self.n_estimators,
                max_depth=self.max_depth,
                random_state=42,
                n_jobs=-1,
            )
            model = MultiOutputRegressor(base_model)
            model.fit(X, y)
            self.models[c] = model

    def predict(self, horizon: int) -> np.ndarray:
        """
        Parameters
        ----------
        """
        if not XGB_AVAILABLE:
            return self.fallback.predict(horizon)

        n_customers = self.train_history.shape[1]
        predictions = np.zeros((horizon, n_customers))

        for c in range(n_customers):
            series = self.train_history[:, c]
            window = series[-self.seq_length:]
            features = np.array([
                window[-1],
                window[-7],
                window[-14],
                window[-30],
                np.mean(window[-7:]),
                np.std(window[-7:]),
                np.mean(window[-30:]),
                np.std(window[-30:]),
            ]).reshape(1, -1)

            model = self.models.get(c)
            if model is not None:
                try:
                    pred = model.predict(features)[0]
                    if len(pred) >= horizon:
                        predictions[:, c] = np.maximum(0.0, pred[:horizon])
                    else:
                        predictions[:len(pred), c] = np.maximum(0.0, pred)
                        predictions[len(pred):, c] = pred[-1]
                except Exception as e:
                    logger.warning(f"XGBoost predict failed for customer {c}: {e}")
                    predictions[:, c] = series[-1]
            else:
                predictions[:, c] = series[-1]

        return predictions


class LightGBMForecaster(BaseForecaster):
    """LightGBM regressor with direct multi-step forecasting.
    Parameters
    ----------
    """

    def __init__(self, n_estimators: int = 100, max_depth: int = 6, seq_length: int = 30):
        """
        Parameters
        ----------
        """
        self.n_estimators = n_estimators
        self.max_depth = max_depth
        self.seq_length = seq_length
        self.fallback = None
        self.models = {}
        self.train_history = None

    def fit(self, train_data: np.ndarray, val_data: np.ndarray = None) -> None:
        """
        Parameters
        ----------
        """
        self.train_history = train_data

        if not LGB_AVAILABLE:
            # Fallback to XGBoost
            self.fallback = XGBoostForecaster(n_estimators=self.n_estimators, max_depth=self.max_depth, seq_length=self.seq_length)
            self.fallback.fit(train_data, val_data)
            return

        n_customers = train_data.shape[1]
        logger.info(f"Training LightGBM models for {n_customers} customers...")
        for c in range(n_customers):
            series = train_data[:, c]
            X, y = engineer_features(series, horizon=7, seq_length=self.seq_length)

            if len(X) == 0:
                self.models[c] = None
                continue

            base_model = lgb.LGBMRegressor(
                n_estimators=self.n_estimators,
                max_depth=self.max_depth,
                random_state=42,
                n_jobs=-1,
                verbosity=-1,
            )
            model = MultiOutputRegressor(base_model)
            model.fit(X, y)
            self.models[c] = model

    def predict(self, horizon: int) -> np.ndarray:
        """
        Parameters
        ----------
        """
        if not LGB_AVAILABLE:
            return self.fallback.predict(horizon)

        n_customers = self.train_history.shape[1]
        predictions = np.zeros((horizon, n_customers))

        for c in range(n_customers):
            series = self.train_history[:, c]
            window = series[-self.seq_length:]
            features = np.array([
                window[-1],
                window[-7],
                window[-14],
                window[-30],
                np.mean(window[-7:]),
                np.std(window[-7:]),
                np.mean(window[-30:]),
                np.std(window[-30:]),
            ]).reshape(1, -1)

            model = self.models.get(c)
            if model is not None:
                try:
                    pred = model.predict(features)[0]
                    if len(pred) >= horizon:
                        predictions[:, c] = np.maximum(0.0, pred[:horizon])
                    else:
                        predictions[:len(pred), c] = np.maximum(0.0, pred)
                        predictions[len(pred):, c] = pred[-1]
                except Exception as e:
                    logger.warning(f"LightGBM predict failed for customer {c}: {e}")
                    predictions[:, c] = series[-1]
            else:
                predictions[:, c] = series[-1]

        return predictions
