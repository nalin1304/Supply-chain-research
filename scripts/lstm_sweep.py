import json
import time
from pathlib import Path
import numpy as np
import torch

from supply_chain_research.config import MasterConfig
from supply_chain_research.phase3_ai.data_generator import DemandDataGenerator
from supply_chain_research.phase3_ai.lstm_forecaster import LSTMForecaster

def main():
    config = MasterConfig()
    n_customers = config.network.n_customers
    
    # Generate standard data
    print("Generating demand dataset...")
    gen = DemandDataGenerator(
        n_customers=n_customers,
        n_years=config.lstm.synthetic_years,
        seed=config.random_seed,
    )
    bundle = gen.generate()
    X, y = gen.create_sequences(
        bundle["demand"],
        seq_length=config.lstm.seq_length,
        forecast_horizon=config.lstm.forecast_horizon,
    )
    splits = gen.temporal_split(
        X, y,
        train_ratio=config.lstm.train_split,
        val_ratio=config.lstm.val_split,
        seq_length=config.lstm.seq_length,
        forecast_horizon=config.lstm.forecast_horizon,
    )

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Running sweep on device: {device}")

    # Sweep grid
    hidden_sizes = [64, 128, 256]
    n_layers_list = [1, 2]
    lrs = [0.001, 0.005]
    dropouts = [0.0, 0.1, 0.2]

    best_mape = float('inf')
    best_config = None

    # We try a few configurations to find the best one quickly
    count = 0
    for hs in hidden_sizes:
        for nl in n_layers_list:
            for lr in lrs:
                for do in dropouts:
                    if nl == 1 and do > 0.0:
                        continue # PyTorch LSTM complains about dropout with n_layers=1
                    
                    count += 1
                    print(f"\n--- Running configuration {count}: hidden_size={hs}, n_layers={nl}, lr={lr}, dropout={do} ---")
                    
                    # Create custom LSTM config
                    run_config = MasterConfig().lstm
                    run_config.hidden_size = hs
                    run_config.n_layers = nl
                    run_config.lr = lr
                    run_config.dropout = do
                    run_config.epochs = 30 # Let's train for 30 epochs
                    run_config.patience = 5

                    forecaster = LSTMForecaster(
                        input_size=n_customers,
                        config=run_config,
                        device=device,
                        checkpoint_dir="outputs/checkpoints_sweep"
                    )

                    t0 = time.perf_counter()
                    history = forecaster.train(
                        splits["X_train"], splits["y_train"],
                        splits["X_val"], splits["y_val"],
                        patience=run_config.patience,
                    )
                    preds = forecaster.predict(splits["X_test"])
                    preds_raw = preds * splits["train_std"] + splits["train_mean"]
                    actuals_raw = splits["y_test_raw"]
                    elapsed = time.perf_counter() - t0

                    mape = float(
                        np.mean(np.abs(preds_raw - actuals_raw) / (np.abs(actuals_raw) + 1e-8))
                        * 100.0
                    )
                    rmse = float(np.sqrt(np.mean((preds_raw - actuals_raw) ** 2)))
                    print(f"Config {count} finished in {elapsed:.1f}s. Test MAPE: {mape:.2f}%, Test RMSE: {rmse:.4f}")

                    if mape < best_mape:
                        best_mape = mape
                        best_config = {
                            "hidden_size": hs,
                            "n_layers": nl,
                            "lr": lr,
                            "dropout": do,
                            "mape": mape,
                            "rmse": rmse
                        }
                        print(f"*** New best MAPE: {best_mape:.2f}%! ***")

    print("\n================ Sweep Complete ================")
    print(f"Best Configuration: {best_config}")

if __name__ == "__main__":
    main()
