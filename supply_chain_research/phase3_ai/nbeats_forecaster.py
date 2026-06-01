"""N-BEATS (Neural Basis Expansion Analysis for Time Series) demand forecasting model.

PyTorch N-BEATS implementation (Oreshkin et al. 2019) with a stack of blocks,
residual connections, and direct forecasting.
"""

import os
import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset
from loguru import logger

from supply_chain_research.config import LSTMConfig
from supply_chain_research.phase3_ai.forecaster_base import BaseForecaster


class NBeatsBlock(nn.Module):
    """Generic N-BEATS block with fully connected layers and backcast/forecast outputs."""

    def __init__(self, input_size: int, theta_size: int, horizon: int):
        super().__init__()
        self.fc1 = nn.Linear(input_size, 128)
        self.fc2 = nn.Linear(128, 128)
        self.fc3 = nn.Linear(128, 128)
        self.fc4 = nn.Linear(128, 128)

        self.fc_backcast = nn.Linear(128, theta_size)
        self.fc_forecast = nn.Linear(128, theta_size)

        self.backcast_out = nn.Linear(theta_size, input_size)
        self.forecast_out = nn.Linear(theta_size, horizon)

    def forward(self, x):
        h = torch.relu(self.fc1(x))
        h = torch.relu(self.fc2(h))
        h = torch.relu(self.fc3(h))
        h = torch.relu(self.fc4(h))

        theta_b = self.fc_backcast(h)
        theta_f = self.fc_forecast(h)

        backcast = self.backcast_out(theta_b)
        forecast = self.forecast_out(theta_f)
        return backcast, forecast


class NBeatsModel(nn.Module):
    """N-BEATS model stack with residual backcast and sum forecast connections."""

    def __init__(self, seq_len: int, horizon: int, input_size: int):
        super().__init__()
        self.seq_len = seq_len
        self.horizon = horizon
        self.input_size = input_size

        # Stack of 3 blocks to allow deep feature extraction
        self.blocks = nn.ModuleList([
            NBeatsBlock(seq_len, 32, horizon) for _ in range(3)
        ])

    def forward(self, x):
        # x shape: (batch, seq_len, input_size)
        batch_size = x.shape[0]

        # Reshape to treat customer channels as batch dimensions for parallel processing
        # new shape: (batch * input_size, seq_len)
        x_flat = x.transpose(1, 2).reshape(-1, self.seq_len)

        residuals = x_flat
        forecast = torch.zeros(x_flat.shape[0], self.horizon, device=x.device)

        for block in self.blocks:
            backcast, block_forecast = block(residuals)
            residuals = residuals - backcast
            forecast = forecast + block_forecast

        # Reshape forecast back to: (batch, horizon, input_size)
        forecast = forecast.view(batch_size, self.input_size, self.horizon).transpose(1, 2)
        return forecast


class NBeatsForecaster(BaseForecaster):
    """Training and inference wrapper for NBeatsModel."""

    def __init__(self, input_size: int, config: LSTMConfig = None, device=None, checkpoint_dir='data/results'):
        if config is None:
            config = LSTMConfig()
        self.config = config
        self.input_size = input_size
        self.checkpoint_dir = checkpoint_dir

        if device is None:
            self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        else:
            self.device = device if isinstance(device, torch.device) else torch.device(device)

        self.model = NBeatsModel(
            seq_len=config.seq_length,
            horizon=config.forecast_horizon,
            input_size=input_size
        ).to(self.device)

        self.optimizer = torch.optim.Adam(
            self.model.parameters(),
            lr=config.lr,
            weight_decay=config.weight_decay,
        )
        self.criterion = nn.HuberLoss(delta=config.huber_delta)
        self.scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
            self.optimizer,
            patience=config.scheduler_patience,
            factor=config.scheduler_factor,
        )
        self.train_losses = []
        self.val_losses = []
        self.best_val_loss = float('inf')
        self.train_history = None

    def fit(self, train_data: np.ndarray, val_data: np.ndarray = None) -> None:
        self.train_history = train_data
        n_customers = train_data.shape[1]

        seq_len = self.config.seq_length
        horizon = self.config.forecast_horizon

        X_train, y_train = self._create_sequences(train_data, seq_len, horizon)
        if val_data is not None:
            X_val, y_val = self._create_sequences(val_data, seq_len, horizon)
        else:
            split = int(len(X_train) * 0.8)
            X_train, X_val = X_train[:split], X_train[split:]
            y_train, y_val = y_train[:split], y_train[split:]

        train_dataset = TensorDataset(torch.FloatTensor(X_train), torch.FloatTensor(y_train))
        val_dataset = TensorDataset(torch.FloatTensor(X_val), torch.FloatTensor(y_val))

        use_pin = (self.device.type == "cuda")
        train_loader = DataLoader(train_dataset, batch_size=self.config.batch_size, shuffle=True, pin_memory=use_pin)
        val_loader = DataLoader(val_dataset, batch_size=self.config.batch_size, shuffle=False, pin_memory=use_pin)

        patience_counter = 0
        patience = 10

        logger.info(f"Training N-BEATS models for {n_customers} customers...")
        for epoch in range(self.config.epochs):
            self.model.train()
            train_loss = 0.0
            n_batches = 0

            for X_batch, y_batch in train_loader:
                X_batch = X_batch.to(self.device)
                y_batch = y_batch.to(self.device)

                self.optimizer.zero_grad()
                predictions = self.model(X_batch)
                loss = self.criterion(predictions, y_batch)
                loss.backward()
                torch.nn.utils.clip_grad_norm_(self.model.parameters(), max_norm=self.config.grad_clip_max_norm)
                self.optimizer.step()

                train_loss += loss.item()
                n_batches += 1

            avg_train_loss = train_loss / max(n_batches, 1)
            self.train_losses.append(avg_train_loss)

            # Validation
            self.model.eval()
            val_loss = 0.0
            val_batches = 0
            with torch.no_grad():
                for X_batch, y_batch in val_loader:
                    X_batch = X_batch.to(self.device)
                    y_batch = y_batch.to(self.device)
                    predictions = self.model(X_batch)
                    loss = self.criterion(predictions, y_batch)
                    val_loss += loss.item()
                    val_batches += 1

            avg_val_loss = val_loss / max(val_batches, 1)
            self.val_losses.append(avg_val_loss)
            self.scheduler.step(avg_val_loss)

            if avg_val_loss < self.best_val_loss:
                self.best_val_loss = avg_val_loss
                patience_counter = 0
                self._save_checkpoint('best_nbeats.pt')
            else:
                patience_counter += 1

            if patience_counter >= patience:
                break

    def predict(self, horizon: int) -> np.ndarray:
        self.model.eval()
        window = self.train_history[-self.config.seq_length:]
        X_tensor = torch.FloatTensor(window[None, :, :]).to(self.device)

        with torch.no_grad():
            predictions = self.model(X_tensor)

        pred_np = predictions.cpu().numpy()[0]

        if len(pred_np) >= horizon:
            return pred_np[:horizon]
        else:
            padded = np.zeros((horizon, self.input_size))
            padded[:len(pred_np)] = pred_np
            padded[len(pred_np):] = pred_np[-1]
            return padded

    def _create_sequences(self, data, seq_length, horizon):
        X, y = [], []
        for i in range(len(data) - seq_length - horizon + 1):
            X.append(data[i:i + seq_length])
            y.append(data[i + seq_length:i + seq_length + horizon])
        return np.array(X), np.array(y)

    def _save_checkpoint(self, filename):
        os.makedirs(self.checkpoint_dir, exist_ok=True)
        filepath = os.path.join(self.checkpoint_dir, filename)
        torch.save({
            'model_state_dict': self.model.state_dict(),
            'best_val_loss': self.best_val_loss,
        }, filepath)
