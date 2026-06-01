"""Unit and integration tests for the expanded forecasting methods (Phase 3)."""

import pytest
import numpy as np

from supply_chain_research.config import LSTMConfig
from supply_chain_research.phase3_ai import (
    NaiveForecaster, SeasonalNaiveForecaster, SimpleMovingAverageForecaster, WeightedMovingAverageForecaster,
    ARIMAForecaster, ETSForecaster, ThetaForecaster,
    ProphetForecaster,
    RandomForestForecaster, XGBoostForecaster, LightGBMForecaster,
    GRUForecaster, NBeatsForecaster, CNNLSTMForecaster,
    run_forecast_comparison, diebold_mariano_test
)


@pytest.fixture
def test_setup():
    config = LSTMConfig()
    config.epochs = 2
    config.batch_size = 4
    config.seq_length = 30
    config.forecast_horizon = 7

    rng = np.random.default_rng(42)
    # Generate 50 days of synthetic demand history for 3 customers
    data = rng.uniform(100, 1000, size=(50, 3))
    return config, data


def test_naive_forecasters(test_setup):
    config, data = test_setup
    for forecaster in [NaiveForecaster(), SeasonalNaiveForecaster(period=7),
                       SimpleMovingAverageForecaster(window=7), WeightedMovingAverageForecaster(window=7)]:
        forecaster.fit(data)
        preds = forecaster.predict(7)
        assert preds.shape == (7, 3)
        assert np.all(preds >= 0.0)


def test_statistical_forecasters(test_setup):
    config, data = test_setup
    for forecaster in [ARIMAForecaster(max_p=1, max_d=0, max_q=1), ETSForecaster(seasonal_periods=7), ThetaForecaster(period=7)]:
        forecaster.fit(data)
        preds = forecaster.predict(7)
        assert preds.shape == (7, 3)
        assert np.all(preds >= 0.0)


def test_prophet_forecaster(test_setup):
    config, data = test_setup
    forecaster = ProphetForecaster(yearly_seasonality=False, weekly_seasonality=True)
    forecaster.fit(data)
    preds = forecaster.predict(7)
    assert preds.shape == (7, 3)


def test_ml_forecasters(test_setup):
    config, data = test_setup
    for forecaster in [RandomForestForecaster(n_estimators=10, max_depth=5, seq_length=30),
                       XGBoostForecaster(n_estimators=10, max_depth=3, seq_length=30),
                       LightGBMForecaster(n_estimators=10, max_depth=3, seq_length=30)]:
        forecaster.fit(data)
        preds = forecaster.predict(7)
        assert preds.shape == (7, 3)


def test_dl_forecasters(test_setup):
    config, data = test_setup
    for forecaster in [GRUForecaster(input_size=3, config=config),
                       NBeatsForecaster(input_size=3, config=config),
                       CNNLSTMForecaster(input_size=3, config=config)]:
        forecaster.fit(data)
        preds = forecaster.predict(7)
        assert preds.shape == (7, 3)


def test_forecast_comparison(test_setup):
    config, data = test_setup
    forecasters = [NaiveForecaster(), SeasonalNaiveForecaster(period=7), SimpleMovingAverageForecaster(window=7)]
    comp_res = run_forecast_comparison(data, forecasters, n_folds=2, horizon=7)

    assert len(comp_res.forecasters) == 3
    assert comp_res.actuals.shape == (14, 3)
    assert "NaiveForecaster" in comp_res.metrics

    # Test DM test
    e1 = comp_res.actuals[:, 0] - comp_res.predictions["NaiveForecaster"][:, 0]
    e2 = comp_res.actuals[:, 0] - comp_res.predictions["SeasonalNaiveForecaster"][:, 0]
    dm_res = diebold_mariano_test(e1, e2)
    assert dm_res.p_value >= 0.0
