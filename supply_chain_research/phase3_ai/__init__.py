"""Phase 3: AI - LSTM forecasting and PPO agent.

Lazy imports: heavy modules (DRLTrainer pulls TensorBoard) are imported
on demand to keep package import time low. Test startup is ~5x faster.
"""

# Light-weight modules: always imported
from supply_chain_research.phase3_ai.attention_lstm import (
    TemporalAttention,
)
from supply_chain_research.phase3_ai.data_generator import (
    DemandDataGenerator,
)
from supply_chain_research.phase3_ai.gym_environment import (
    SupplyChainEnv,
)
from supply_chain_research.phase3_ai.ss_policy import (
    SSPolicy,
    evaluate_ss_policy,
)


def __getattr__(name):
    """PEP 562 lazy attribute loader for heavy modules.
    Parameters
    ----------
    """
    if name in ["LSTMForecaster", "AttentionLSTMModel"]:
        from supply_chain_research.phase3_ai.lstm_forecaster import (
            AttentionLSTMModel,
            LSTMForecaster,
        )
        return LSTMForecaster if name == "LSTMForecaster" else AttentionLSTMModel
    if name == "PPOAgent":
        from supply_chain_research.phase3_ai.ppo_agent import PPOAgent
        return PPOAgent
    if name == "DRLTrainer":
        from supply_chain_research.phase3_ai.drl_trainer import DRLTrainer
        return DRLTrainer
    if name in ["ForecastResult", "BaseForecaster"]:
        from supply_chain_research.phase3_ai.forecaster_base import (
            BaseForecaster,
            ForecastResult,
        )
        return ForecastResult if name == "ForecastResult" else BaseForecaster
    if name in ["NaiveForecaster", "SeasonalNaiveForecaster", "SimpleMovingAverageForecaster", "WeightedMovingAverageForecaster"]:
        from supply_chain_research.phase3_ai.naive_forecasters import (
            NaiveForecaster,
            SeasonalNaiveForecaster,
            SimpleMovingAverageForecaster,
            WeightedMovingAverageForecaster,
        )
        if name == "NaiveForecaster": return NaiveForecaster
        if name == "SeasonalNaiveForecaster": return SeasonalNaiveForecaster
        if name == "SimpleMovingAverageForecaster": return SimpleMovingAverageForecaster
        return WeightedMovingAverageForecaster
    if name in ["ARIMAForecaster", "ETSForecaster", "ThetaForecaster"]:
        from supply_chain_research.phase3_ai.statistical_forecasters import (
            ARIMAForecaster,
            ETSForecaster,
            ThetaForecaster,
        )
        if name == "ARIMAForecaster": return ARIMAForecaster
        if name == "ETSForecaster": return ETSForecaster
        return ThetaForecaster
    if name == "ProphetForecaster":
        from supply_chain_research.phase3_ai.prophet_forecaster import ProphetForecaster
        return ProphetForecaster
    if name in ["RandomForestForecaster", "XGBoostForecaster", "LightGBMForecaster"]:
        from supply_chain_research.phase3_ai.ml_forecasters import (
            LightGBMForecaster,
            RandomForestForecaster,
            XGBoostForecaster,
        )
        if name == "RandomForestForecaster": return RandomForestForecaster
        if name == "XGBoostForecaster": return XGBoostForecaster
        return LightGBMForecaster
    if name in ["GRUForecaster", "AttentionGRUModel"]:
        from supply_chain_research.phase3_ai.gru_forecaster import (
            AttentionGRUModel,
            GRUForecaster,
        )
        return GRUForecaster if name == "GRUForecaster" else AttentionGRUModel
    if name in ["NBeatsForecaster", "NBeatsModel"]:
        from supply_chain_research.phase3_ai.nbeats_forecaster import (
            NBeatsForecaster,
            NBeatsModel,
        )
        return NBeatsForecaster if name == "NBeatsForecaster" else NBeatsModel
    if name in ["CNNLSTMForecaster", "CNNLSTMModel"]:
        from supply_chain_research.phase3_ai.cnn_lstm_forecaster import (
            CNNLSTMForecaster,
            CNNLSTMModel,
        )
        return CNNLSTMForecaster if name == "CNNLSTMForecaster" else CNNLSTMModel
    if name in ["ForecastComparisonResult", "DMResult", "diebold_mariano_test", "expanding_window_cv", "run_forecast_comparison", "plot_forecast_comparison"]:
        from supply_chain_research.phase3_ai.forecaster_comparison import (
            DMResult,
            ForecastComparisonResult,
            diebold_mariano_test,
            expanding_window_cv,
            plot_forecast_comparison,
            run_forecast_comparison,
        )
        if name == "ForecastComparisonResult": return ForecastComparisonResult
        if name == "DMResult": return DMResult
        if name == "diebold_mariano_test": return diebold_mariano_test
        if name == "expanding_window_cv": return expanding_window_cv
        if name == "run_forecast_comparison": return run_forecast_comparison
        return plot_forecast_comparison

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "DemandDataGenerator",
    "TemporalAttention",
    "AttentionLSTMModel",
    "LSTMForecaster",
    "SupplyChainEnv",
    "PPOAgent",
    "DRLTrainer",
    "SSPolicy",
    "evaluate_ss_policy",
    "ForecastResult",
    "BaseForecaster",
    "NaiveForecaster",
    "SeasonalNaiveForecaster",
    "SimpleMovingAverageForecaster",
    "WeightedMovingAverageForecaster",
    "ARIMAForecaster",
    "ETSForecaster",
    "ThetaForecaster",
    "ProphetForecaster",
    "RandomForestForecaster",
    "XGBoostForecaster",
    "LightGBMForecaster",
    "GRUForecaster",
    "AttentionGRUModel",
    "NBeatsForecaster",
    "NBeatsModel",
    "CNNLSTMForecaster",
    "CNNLSTMModel",
    "ForecastComparisonResult",
    "DMResult",
    "diebold_mariano_test",
    "expanding_window_cv",
    "run_forecast_comparison",
    "plot_forecast_comparison",
]
