"""GRU demand forecasting model.

PyTorch GRU model with temporal attention for multi-step demand forecasting.
Matches the interface of AttentionLSTMModel but uses GRU cells.
"""

import os

import numpy as np
import torch
import torch.nn as nn
from loguru import logger
from torch.utils.data import DataLoader, TensorDataset

from supply_chain_research.config import LSTMConfig
from supply_chain_research.phase3_ai.attention_lstm import TemporalAttention
from supply_chain_research.phase3_ai.forecaster_base import BaseForecaster


class AttentionGRUModel(nn.Module):
    """GRU with temporal attention for demand forecasting.
    Parameters
    ----------
    """

    def __init__(self, input_size: int, config: LSTMConfig = None):
        """
        Parameters
        ----------
        """
        super().__init__()
        if config is None:
            config = LSTMConfig()

        self.hidden_size = config.hidden_size
        self.n_layers = config.n_layers
        self.forecast_horizon = config.forecast_horizon
        self.input_size = input_size

        # GRU layer
        self.gru = nn.GRU(
            input_size=input_size,
            hidden_size=config.hidden_size,
            num_layers=config.n_layers,
            dropout=config.dropout if config.n_layers > 1 else 0.0,
            batch_first=True,
        )

        # Temporal attention
        self.attention = TemporalAttention(config.hidden_size)

        # Output projection
        self.fc_out = nn.Linear(
            config.hidden_size,
            config.forecast_horizon * input_size,
        )

    def forward(self, x):
        # GRU forward
        """
        Parameters
        ----------
        """
        gru_out, _ = self.gru(x)
        # Temporal attention
        context, _ = self.attention(gru_out)
        # Output projection
        output = self.fc_out(context)
        return output.view(-1, self.forecast_horizon, self.input_size)


class GRUForecaster(BaseForecaster):
    """Training and inference wrapper for AttentionGRUModel.
    Parameters
    ----------
    """

    def __init__(self, input_size: int, config: LSTMConfig = None, device=None, checkpoint_dir='data/results'):
        """
        Parameters
        ----------
        """
        if config is None:
            config = LSTMConfig()
        self.config = config
        self.input_size = input_size
        self.checkpoint_dir = checkpoint_dir

        if device is None:
            self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        else:
            self.device = device if isinstance(device, torch.device) else torch.device(device)

        self.model = AttentionGRUModel(input_size, config).to(self.device)
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
        """
        Parameters
        ----------
        """
        self.train_history = train_data
        n_customers = train_data.shape[1]

        # Prepare sequences for training (lookback window of 30 days)
        seq_len = self.config.seq_length
        horizon = self.config.forecast_horizon

        X_train, y_train = self._create_sequences(train_data, seq_len, horizon)
        if val_data is not None:
            X_val, y_val = self._create_sequences(val_data, seq_len, horizon)
        else:
            # Split train into train/val
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

        logger.info(f"Training GRU models for {n_customers} customers...")
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

            # Early stopping check
            if avg_val_loss < self.best_val_loss:
                self.best_val_loss = avg_val_loss
                patience_counter = 0
                self._save_checkpoint('best_gru.pt')
            else:
                patience_counter += 1

            if patience_counter >= patience:
                break

    def predict(self, horizon: int) -> np.ndarray:
        """
        Parameters
        ----------
        """
        self.model.eval()
        # Take the last seq_length window from train history
        window = self.train_history[-self.config.seq_length:]
        X_tensor = torch.FloatTensor(window[None, :, :]).to(self.device)

        with torch.no_grad():
            predictions = self.model(X_tensor)

        pred_np = predictions.cpu().numpy()[0]  # shape (forecast_horizon, n_customers)

        # Slice/extrapolate to match requested horizon
        if len(pred_np) >= horizon:
            return pred_np[:horizon]
        else:
            padded = np.zeros((horizon, self.input_size))
            padded[:len(pred_np)] = pred_np
            padded[len(pred_np):] = pred_np[-1]
            return padded

    def _create_sequences(self, data, seq_length, horizon):
        """
        Parameters
        ----------
        """
        X, y = [], []
        for i in range(len(data) - seq_length - horizon + 1):
            X.append(data[i:i + seq_length])
            y.append(data[i + seq_length:i + seq_length + horizon])
        return np.array(X), np.array(y)

    def _save_checkpoint(self, filename):
        """
        Parameters
        ----------
        """
        os.makedirs(self.checkpoint_dir, exist_ok=True)
        filepath = os.path.join(self.checkpoint_dir, filename)
        torch.save({
            'model_state_dict': self.model.state_dict(),
            'best_val_loss': self.best_val_loss,
        }, filepath)
