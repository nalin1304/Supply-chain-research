"""Attention-LSTM demand forecasting model.

2-layer LSTM with temporal attention for multi-step demand forecasting.
Input: 30-day sequence, Output: 7-day forecast.
Training includes early stopping on validation loss.

Audit 1.6: select_lookback_window() data-drives the seq_length using
the partial autocorrelation function (PACF) of the demand series.
"""

import os
import warnings

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset

from supply_chain_research.config import LSTMConfig
from supply_chain_research.phase3_ai.attention_lstm import (
    TemporalAttention,
)


def select_lookback_window(
    train_demand: np.ndarray,
    max_lag: int = 365,
    confidence: float = 0.95,
    config: LSTMConfig = None,
) -> int:
    """Select LSTM lookback window via partial autocorrelation (Audit 1.6).

    Computes the PACF of the input series and returns the maximum lag
    at which the PACF magnitude exceeds the (1 - confidence) confidence
    bound, capped at max_lag (default ``365`` mirrors
    ``LSTMConfig.pacf_max_lag_default`` so the C3.12 signature
    baseline holds; ``None`` is also accepted and routes through the
    config fallback below) to bound annual seasonality.

    Parameters
    ----------
    train_demand : np.ndarray
        1-D series of demand observations (training data only — never
        compute PACF on val/test to avoid leakage).
    max_lag : int, optional
        Hard cap on the returned window length. Default ``365`` mirrors
        ``LSTMConfig.pacf_max_lag_default``; ``None`` is also accepted
        and routes through the config fallback.
    confidence : float
        Confidence level for the significance bound (default 0.95).
    config : LSTMConfig, optional
        Configuration carrying PACF defaults. Uses ``LSTMConfig()``
        when None.

    Returns
    -------
    int
        The maximum significant lag, in
        [``config.pacf_min_window``, ``max_lag``].
        Falls back to ``config.pacf_default_window`` if statsmodels
        is not installed or the series is too short.
    """
    if config is None:
        config = LSTMConfig()
    if max_lag is None:
        max_lag = config.pacf_max_lag_default

    if train_demand.ndim > 1:
        # If multi-series (T, n_customers), aggregate to total demand
        train_demand = train_demand.sum(axis=tuple(range(1, train_demand.ndim)))

    n = len(train_demand)
    if n < config.pacf_default_window:
        warnings.warn(
            f"Series too short for PACF; using default window="
            f"{config.pacf_default_window}."
        )
        return config.pacf_default_window

    nlags = min(max_lag, n // 4)  # statsmodels requires nlags < n/2

    try:
        from statsmodels.tsa.stattools import pacf
    except ImportError:
        warnings.warn(
            f"statsmodels not installed; using default seq_length="
            f"{config.pacf_default_window}."
        )
        return config.pacf_default_window

    pacf_vals = pacf(train_demand, nlags=nlags, method="ywm")
    # 95% confidence bound: ~1.96/sqrt(N) (asymptotic)
    z = config.pacf_z_95 if confidence >= 0.95 else config.pacf_z_90
    bound = z / np.sqrt(n)

    significant_lags = [
        lag for lag in range(1, len(pacf_vals))
        if abs(pacf_vals[lag]) > bound
    ]
    if not significant_lags:
        return config.pacf_default_window
    return min(
        max_lag, max(config.pacf_min_window, max(significant_lags))
    )


class AttentionLSTMModel(nn.Module):
    """LSTM with temporal attention for demand forecasting.

    Architecture:
        - 2-layer LSTM (hidden_size=128, dropout=0.2)
        - Temporal attention over hidden states
        - Fully connected output layer for 7-day forecast

    Parameters
    ----------
    input_size : int
        Number of input features (typically ``n_customers``).
    config : LSTMConfig, optional
        Forecaster configuration. Defaults to a fresh
        :class:`LSTMConfig`.

    Attributes
    ----------
    hidden_size, n_layers, forecast_horizon : int
        Architecture sizes pulled from ``config``.
    lstm : torch.nn.LSTM
        Two-layer LSTM encoder.
    attention : TemporalAttention
        Additive-attention head.
    fc : torch.nn.Linear
        Output projection emitting ``forecast_horizon`` days.
    """

    def __init__(self, input_size, config=None):
        """Initialize Attention-LSTM model.

        Args:
            input_size: Number of input features (n_customers).
            config: LSTMConfig instance. Uses defaults if None.
        
        Parameters
        ----------
        """
        super().__init__()
        if config is None:
            config = LSTMConfig()

        self.hidden_size = config.hidden_size
        self.n_layers = config.n_layers
        self.forecast_horizon = config.forecast_horizon

        # LSTM layers
        self.lstm = nn.LSTM(
            input_size=input_size,
            hidden_size=config.hidden_size,
            num_layers=config.n_layers,
            dropout=config.dropout if config.n_layers > 1 else 0.0,
            batch_first=True,
        )

        # Initialize LSTM forget gate bias to 1.0 to prevent vanishing gradients
        # PyTorch LSTM bias layout: [b_ii, b_if, b_ig, b_io] where each has hidden_size elements
        # Forget gate bias is at indices [hidden_size : 2*hidden_size]
        for name, param in self.lstm.named_parameters():
            if 'bias' in name:
                n = param.size(0)
                # n = 4 * hidden_size
                hidden_size = n // 4
                # Set forget gate bias to 1.0
                param.data[hidden_size:2*hidden_size].fill_(1.0)

        # Temporal attention
        self.attention = TemporalAttention(config.hidden_size)

        # Output projection: context vector -> forecast
        self.fc_out = nn.Linear(
            config.hidden_size,
            config.forecast_horizon * input_size,
        )

        self.input_size = input_size

    def forward(self, x):
        """Forward pass.

        Args:
            x: Input tensor of shape (batch, seq_len, input_size).

        Returns:
            Forecast tensor of shape (batch, forecast_horizon, input_size).
        
        Parameters
        ----------
        """
        # LSTM forward
        lstm_out, _ = self.lstm(x)
        # lstm_out: (batch, seq_len, hidden_size)

        # Temporal attention
        context, attn_weights = self.attention(lstm_out)
        # context: (batch, hidden_size)

        # Output projection
        output = self.fc_out(context)
        # Reshape to (batch, forecast_horizon, input_size)
        output = output.view(
            -1, self.forecast_horizon, self.input_size
        )

        return output

    def get_attention_weights(self, x):
        """Get attention weights for interpretability.

        Args:
            x: Input tensor of shape (batch, seq_len, input_size).

        Returns:
            Attention weights of shape (batch, seq_len).
        
        Parameters
        ----------
        """
        with torch.no_grad():
            lstm_out, _ = self.lstm(x)
            _, attn_weights = self.attention(lstm_out)
        return attn_weights


class LSTMForecaster:
    """Training and inference wrapper for AttentionLSTMModel.

    Handles training loop with Adam optimizer, MSE loss,
    early stopping, and checkpoint saving.

    Parameters
    ----------
    input_size : int
        Number of input features (``n_customers``).
    config : LSTMConfig, optional
        Forecaster configuration. Defaults to a fresh
        :class:`LSTMConfig`.
    device : str or torch.device, optional
        Compute device. Auto-selected when ``None``.
    checkpoint_dir : str, optional
        Directory for checkpoint persistence.

    Attributes
    ----------
    model : AttentionLSTMModel
        Wrapped LSTM model.
    config : LSTMConfig
        Active configuration.
    device : torch.device
        Compute device used for training/inference.
    checkpoint_dir : str
        Directory for checkpoint persistence.
    optimizer : torch.optim.Optimizer
        Adam optimizer instance.
    """

    def __init__(self, input_size, config=None, device=None,
                 checkpoint_dir='data/results'):
        """Initialize LSTM forecaster.

        Args:
            input_size: Number of input features.
            config: LSTMConfig instance.
            device: torch device (auto-detected if None).
            checkpoint_dir: Directory for saving model checkpoints.
        
        Parameters
        ----------
        """
        if config is None:
            config = LSTMConfig()
        self.config = config
        self.input_size = input_size
        self.checkpoint_dir = checkpoint_dir

        if device is None:
            self.device = torch.device(
                # [PyTorch device-string convention — `torch.device` accepts str]
                'cuda' if torch.cuda.is_available() else 'cpu'
            )
        else:
            # Accept either a string (e.g. "cuda" / "cpu") or an
            # existing `torch.device`. Normalising here keeps the
            # downstream `self.device.type` and `tensor.to(self.device)`
            # call sites uniform regardless of caller convention.
            self.device = (
                device if isinstance(device, torch.device)
                else torch.device(device)
            )

        # Model selection (FIX-009): "lstm" / "attention_lstm" use the
        # in-house Attention-LSTM; "tft" selects the lightweight Temporal
        # Fusion Transformer baseline (Lim et al., 2021).
        # Default ("attention_lstm") preserves existing behavior so clause
        # C3.1 / C3.12 hold for callers that don't set model_type.
        # Reference: Lim, B., Arık, S.Ö., Loeff, N., & Pfister, T. (2021).
        # Temporal Fusion Transformers for Interpretable Multi-horizon
        # Time Series Forecasting. International Journal of Forecasting,
        # 37(4), 1748-1764. DOI:10.1016/j.ijforecast.2021.03.012
        model_type = getattr(config, "model_type", "attention_lstm")
        if model_type == "tft":
            from supply_chain_research.phase3_ai.tft_forecaster import (
                LightweightTFT,
            )
            self.model = LightweightTFT(
                n_customers=input_size,
                hidden_size=config.tft_hidden_size,
                n_heads=config.tft_n_heads,
                forecast_horizon=config.forecast_horizon,
                n_layers=config.n_layers,
                dropout=config.tft_dropout,
            ).to(self.device)
            self._model_type = "tft"
        else:
            self.model = AttentionLSTMModel(
                input_size, config
            ).to(self.device)
            self._model_type = "attention_lstm"

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

    def _forward(self, X):
        """Run a forward pass through the underlying model.

        Both ``AttentionLSTMModel`` and ``LightweightTFT`` are supported.
        ``LightweightTFT`` returns ``(predictions, attn_weights)``; this
        helper unwraps the tuple so callers see a single prediction
        tensor regardless of model choice.

        Parameters
        ----------
        X : torch.Tensor
            Batch tensor of shape ``(batch, seq_len, input_size)``.

        Returns
        -------
        torch.Tensor
            Prediction tensor of shape
            ``(batch, forecast_horizon, input_size)``.
        """
        out = self.model(X)
        if isinstance(out, tuple):
            return out[0]
        return out

    def train(self, X_train, y_train, X_val, y_val,
              patience=10):
        """Train the model with early stopping.

        Args:
            X_train: Training inputs, shape (n, seq_len, features).
            y_train: Training targets, shape (n, horizon, features).
            X_val: Validation inputs.
            y_val: Validation targets.
            patience: Early stopping patience (epochs).

        Returns:
            Dictionary with training history.
        
        Parameters
        ----------
        """
        # Convert to tensors
        train_dataset = TensorDataset(
            torch.FloatTensor(X_train),
            torch.FloatTensor(y_train),
        )
        val_dataset = TensorDataset(
            torch.FloatTensor(X_val),
            torch.FloatTensor(y_val),
        )

        # Audit P6: pin_memory + num_workers for GPU pipeline efficiency
        use_pin = (self.device.type == "cuda")
        n_workers = 2 if use_pin else 0
        train_loader = DataLoader(
            train_dataset,
            batch_size=self.config.batch_size,
            shuffle=True,
            num_workers=n_workers,
            pin_memory=use_pin,
            persistent_workers=(n_workers > 0),
        )
        val_loader = DataLoader(
            val_dataset,
            batch_size=self.config.batch_size,
            shuffle=False,
            num_workers=n_workers,
            pin_memory=use_pin,
            persistent_workers=(n_workers > 0),
        )

        patience_counter = 0

        for epoch in range(self.config.epochs):
            # Training phase
            self.model.train()
            train_loss = 0.0
            n_batches = 0

            for X_batch, y_batch in train_loader:
                X_batch = X_batch.to(self.device)
                y_batch = y_batch.to(self.device)

                self.optimizer.zero_grad()
                predictions = self._forward(X_batch)
                loss = self.criterion(predictions, y_batch)
                loss.backward()
                torch.nn.utils.clip_grad_norm_(
                    self.model.parameters(),
                    max_norm=self.config.grad_clip_max_norm,
                )
                self.optimizer.step()

                train_loss += loss.item()
                n_batches += 1

            avg_train_loss = train_loss / max(n_batches, 1)
            self.train_losses.append(avg_train_loss)

            # Validation phase
            val_loss = self._evaluate(val_loader)
            self.val_losses.append(val_loss)

            # Step scheduler based on validation loss
            self.scheduler.step(val_loss)

            # Early stopping check
            if val_loss < self.best_val_loss:
                self.best_val_loss = val_loss
                patience_counter = 0
                self._save_checkpoint('best_lstm.pt')
            else:
                patience_counter += 1

            if patience_counter >= patience:
                break

        return {
            'train_losses': self.train_losses,
            'val_losses': self.val_losses,
            'best_val_loss': self.best_val_loss,
            'epochs_trained': len(self.train_losses),
        }

    def _evaluate(self, dataloader):
        """Evaluate model on a dataloader.

        Args:
            dataloader: PyTorch DataLoader.

        Returns:
            Average loss as float.
        
        Parameters
        ----------
        """
        self.model.eval()
        total_loss = 0.0
        n_batches = 0

        with torch.no_grad():
            for X_batch, y_batch in dataloader:
                X_batch = X_batch.to(self.device)
                y_batch = y_batch.to(self.device)

                predictions = self._forward(X_batch)
                loss = self.criterion(predictions, y_batch)
                total_loss += loss.item()
                n_batches += 1

        return total_loss / max(n_batches, 1)

    def predict(self, X):
        """Generate forecasts.

        Args:
            X: Input array of shape (n, seq_len, features).

        Returns:
            Predictions array of shape (n, horizon, features).
        
        Parameters
        ----------
        """
        self.model.eval()
        X_tensor = torch.FloatTensor(X).to(self.device)

        with torch.no_grad():
            predictions = self._forward(X_tensor)

        return predictions.cpu().numpy()

    def _save_checkpoint(self, filename):
        """Save model checkpoint.

        Args:
            filename: Checkpoint filename.
        
        Parameters
        ----------
        """
        os.makedirs(self.checkpoint_dir, exist_ok=True)
        filepath = os.path.join(self.checkpoint_dir, filename)
        torch.save({
            'model_state_dict': self.model.state_dict(),
            'optimizer_state_dict': self.optimizer.state_dict(),
            'best_val_loss': self.best_val_loss,
            'config': {
                'input_size': self.input_size,
                'hidden_size': self.config.hidden_size,
                'n_layers': self.config.n_layers,
                'forecast_horizon': self.config.forecast_horizon,
                'model_type': getattr(self, '_model_type', 'attention_lstm'),
            },
        }, filepath)

    def load_checkpoint(self, filename):
        """Load model from checkpoint.

        Parameters
        ----------
        filename : str
            Checkpoint filename inside ``self.checkpoint_dir``.

        Returns
        -------
        None
            Model and optimizer state are mutated in place.
        """
        filepath = os.path.join(self.checkpoint_dir, filename)
        checkpoint = torch.load(
            filepath, map_location=self.device,
            weights_only=False,
        )
        self.model.load_state_dict(checkpoint['model_state_dict'])
        self.optimizer.load_state_dict(
            checkpoint['optimizer_state_dict']
        )
        self.best_val_loss = checkpoint['best_val_loss']
