"""Lightweight Temporal Fusion Transformer (TFT) forecaster.

Implements a simplified TFT architecture for multi-horizon time series
forecasting, following the design of Lim et al. (2021).

Reference
---------
Lim, B., Arık, S.Ö., Loeff, N., & Pfister, T. (2021).
Temporal Fusion Transformers for Interpretable Multi-horizon Time Series
Forecasting. International Journal of Forecasting, 37(4), 1748-1764.
DOI: 10.1016/j.ijforecast.2021.03.012

Architecture Overview
---------------------
This lightweight variant retains the core TFT components:
1. Gated Residual Network (GRN) — Eq. 3 in Lim et al. (2021)
2. Multi-head self-attention over temporal features
3. LSTM encoder for sequential processing

The full TFT includes variable selection networks, static covariate
encoders, and interpretable multi-horizon attention. This lightweight
version omits variable selection (single input stream) and static
covariates to reduce parameter count for our 3-year × 100-customer
synthetic dataset where the full TFT would be over-parameterized.

Typical parameter count: ~150K (vs ~1M for full TFT, ~65K for our LSTM).
"""

import torch
import torch.nn as nn
import torch.nn.functional as F


class GatedResidualNetwork(nn.Module):
    """Gated Residual Network (GRN) per Lim et al. (2021), Eq. 3.

    The GRN applies a non-linear transformation with gating and a skip
    connection. It is the fundamental building block of the TFT architecture.

    Architecture::

        η₁ = ELU(W₁ · x + b₁)
        η₂ = W₂ · η₁ + b₂
        gate = σ(W_g · η₁ + b_g)
        GRN(x) = LayerNorm(x + gate ⊙ η₂)

    Parameters
    ----------
    input_size : int
        Dimensionality of the input features.
    hidden_size : int
        Dimensionality of the intermediate hidden layer.
    output_size : int
        Dimensionality of the output. If different from input_size,
        a linear projection is applied to the skip connection.
    dropout : float, optional
        Dropout probability applied after the first linear layer.
        Default is 0.1.

    Attributes
    ----------
    fc1 : nn.Linear
        First linear transformation (input_size → hidden_size).
    fc2 : nn.Linear
        Second linear transformation (hidden_size → output_size).
    gate_fc : nn.Linear
        Gating linear transformation (hidden_size → output_size).
    layer_norm : nn.LayerNorm
        Layer normalization applied after the residual addition.
    skip_proj : nn.Linear or None
        Projection for the skip connection when input_size != output_size.
    dropout : nn.Dropout
        Dropout layer.
    """

    def __init__(self, input_size, hidden_size, output_size, dropout=0.1):
        """Initialize the Gated Residual Network.

        Parameters
        ----------
        input_size : int
            Dimensionality of the input features.
        hidden_size : int
            Dimensionality of the intermediate hidden layer.
        output_size : int
            Dimensionality of the output.
        dropout : float, optional
            Dropout probability. Default is 0.1.
        """
        super().__init__()
        self.input_size = input_size
        self.hidden_size = hidden_size
        self.output_size = output_size

        # Primary transformation path
        self.fc1 = nn.Linear(input_size, hidden_size)
        self.fc2 = nn.Linear(hidden_size, output_size)

        # Gating mechanism (sigmoid activation)
        self.gate_fc = nn.Linear(hidden_size, output_size)

        # Layer normalization for residual connection
        self.layer_norm = nn.LayerNorm(output_size)

        # Skip connection projection (if dimensions differ)
        if input_size != output_size:
            self.skip_proj = nn.Linear(input_size, output_size)
        else:
            self.skip_proj = None

        self.dropout = nn.Dropout(dropout)

    def forward(self, x):
        """Forward pass through the GRN.

        Parameters
        ----------
        x : torch.Tensor
            Input tensor of shape ``(..., input_size)``.

        Returns
        -------
        torch.Tensor
            Output tensor of shape ``(..., output_size)`` after gated
            residual transformation with layer normalization.
        """
        # Skip connection
        if self.skip_proj is not None:
            skip = self.skip_proj(x)
        else:
            skip = x

        # Primary path: ELU activation (Eq. 3 in Lim et al.)
        eta1 = F.elu(self.fc1(x))
        eta1 = self.dropout(eta1)

        # Second linear transformation
        eta2 = self.fc2(eta1)

        # Gating via sigmoid
        gate = torch.sigmoid(self.gate_fc(eta1))

        # Gated output + skip connection + LayerNorm
        output = self.layer_norm(skip + gate * eta2)

        return output


class LightweightTFT(nn.Module):
    """Lightweight Temporal Fusion Transformer for demand forecasting.

    This simplified TFT architecture combines:
    1. An input GRN for feature transformation
    2. An LSTM encoder for sequential processing
    3. Multi-head self-attention over encoded temporal features
    4. An output GRN for final prediction

    The model accepts a sequence of demand observations across multiple
    customers and produces multi-horizon forecasts with attention weights
    for interpretability.

    Parameters
    ----------
    n_customers : int
        Number of input features (customers/time series).
    hidden_size : int
        Hidden dimensionality used throughout the model.
    n_heads : int
        Number of attention heads in the multi-head self-attention layer.
    forecast_horizon : int
        Number of future time steps to predict.
    n_layers : int, optional
        Number of LSTM layers. Default is 2.
    dropout : float, optional
        Dropout probability. Default is 0.1.

    Attributes
    ----------
    input_grn : GatedResidualNetwork
        GRN applied to input features at each time step.
    lstm_encoder : nn.LSTM
        LSTM encoder for sequential processing.
    attention : nn.MultiheadAttention
        Multi-head self-attention over temporal dimension.
    output_grn : GatedResidualNetwork
        GRN applied to attention output for final transformation.
    output_proj : nn.Linear
        Final projection to (forecast_horizon, n_customers).

    Examples
    --------
    >>> model = LightweightTFT(n_customers=100, hidden_size=64, n_heads=4, forecast_horizon=7)
    >>> x = torch.randn(32, 30, 100)  # (batch, seq_len, n_customers)
    >>> output, attn_weights = model(x)
    >>> output.shape
    torch.Size([32, 7, 100])
    >>> attn_weights.shape
    torch.Size([32, 30, 30])
    """

    def __init__(self, n_customers, hidden_size, n_heads, forecast_horizon,
                 n_layers=2, dropout=0.1):
        """Initialize the Lightweight TFT model.

        Parameters
        ----------
        n_customers : int
            Number of input features (customers/time series).
        hidden_size : int
            Hidden dimensionality used throughout the model.
        n_heads : int
            Number of attention heads in the multi-head self-attention.
        forecast_horizon : int
            Number of future time steps to predict.
        n_layers : int, optional
            Number of LSTM layers. Default is 2.
        dropout : float, optional
            Dropout probability. Default is 0.1.
        """
        super().__init__()
        self.n_customers = n_customers
        self.hidden_size = hidden_size
        self.n_heads = n_heads
        self.forecast_horizon = forecast_horizon
        self.n_layers = n_layers

        # Input GRN: transform raw features to hidden representation
        self.input_grn = GatedResidualNetwork(
            input_size=n_customers,
            hidden_size=hidden_size,
            output_size=hidden_size,
            dropout=dropout,
        )

        # LSTM encoder for sequential dependencies
        self.lstm_encoder = nn.LSTM(
            input_size=hidden_size,
            hidden_size=hidden_size,
            num_layers=n_layers,
            batch_first=True,
            dropout=dropout if n_layers > 1 else 0.0,
        )

        # Multi-head self-attention (Lim et al. 2021, Section 4.4)
        # batch_first=True for (batch, seq_len, hidden_size) input
        self.attention = nn.MultiheadAttention(
            embed_dim=hidden_size,
            num_heads=n_heads,
            dropout=dropout,
            batch_first=True,
        )

        # Output GRN: post-attention transformation
        self.output_grn = GatedResidualNetwork(
            input_size=hidden_size,
            hidden_size=hidden_size,
            output_size=hidden_size,
            dropout=dropout,
        )

        # Final projection: map from (batch, seq_len, hidden_size)
        # to (batch, forecast_horizon, n_customers)
        self.output_proj = nn.Linear(hidden_size, n_customers)

        # Temporal projection to forecast horizon
        self.temporal_proj = nn.Linear(hidden_size, forecast_horizon * hidden_size)

    def forward(self, x):
        """Forward pass through the Lightweight TFT.

        Parameters
        ----------
        x : torch.Tensor
            Input tensor of shape ``(batch, seq_len, n_customers)``
            containing historical demand observations.

        Returns
        -------
        output : torch.Tensor
            Forecast tensor of shape ``(batch, forecast_horizon, n_customers)``.
        attn_weights : torch.Tensor
            Attention weight matrix of shape ``(batch, seq_len, seq_len)``
            averaged across attention heads, useful for interpretability.
        """
        batch_size, seq_len, _ = x.shape

        # 1. Input GRN: (batch, seq_len, n_customers) → (batch, seq_len, hidden)
        grn_out = self.input_grn(x)

        # 2. LSTM encoder: (batch, seq_len, hidden) → (batch, seq_len, hidden)
        lstm_out, _ = self.lstm_encoder(grn_out)

        # 3. Multi-head self-attention over temporal dimension
        # attn_output: (batch, seq_len, hidden)
        # attn_weights: (batch, seq_len, seq_len) with average_attn_weights=True
        attn_output, attn_weights = self.attention(
            lstm_out, lstm_out, lstm_out,
            need_weights=True,
            average_attn_weights=True,
        )

        # 4. Output GRN on attention output
        # Use the last time step's representation for forecasting
        # (batch, seq_len, hidden) → take last → (batch, hidden)
        context = attn_output[:, -1, :]

        # Project to forecast_horizon * hidden_size, then reshape
        temporal = self.temporal_proj(context)
        temporal = temporal.view(batch_size, self.forecast_horizon, self.hidden_size)

        # 5. Apply output GRN to each forecast step
        # (batch, forecast_horizon, hidden) → (batch, forecast_horizon, hidden)
        output_grn = self.output_grn(temporal)

        # 6. Final projection to n_customers
        # (batch, forecast_horizon, hidden) → (batch, forecast_horizon, n_customers)
        output = self.output_proj(output_grn)

        return output, attn_weights
