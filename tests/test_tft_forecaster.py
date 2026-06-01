"""Tests for the Lightweight Temporal Fusion Transformer baseline.

Covers FIX-009 (clause C1.5 / C2.5):
- ``GatedResidualNetwork`` shape contract and gradient flow
- ``LightweightTFT`` forward shape, attention-weight properties, and
  gradient flow
- ``LSTMForecaster`` integration via ``LSTMConfig.model_type = "tft"``
  (preserves clause C3.1 for the default ``"attention_lstm"`` path)

Reference
---------
Lim, B., Arık, S.Ö., Loeff, N., & Pfister, T. (2021). Temporal Fusion
Transformers for Interpretable Multi-horizon Time Series Forecasting.
International Journal of Forecasting, 37(4), 1748-1764.
DOI: 10.1016/j.ijforecast.2021.03.012
"""

import numpy as np
import pytest
import torch

from supply_chain_research.config import LSTMConfig
from supply_chain_research.phase3_ai.tft_forecaster import (
    GatedResidualNetwork,
    LightweightTFT,
)
from supply_chain_research.phase3_ai.lstm_forecaster import (
    LSTMForecaster,
)


class TestGatedResidualNetwork:
    """Tests for the Gated Residual Network (Lim 2021, Eq. 3)."""

    def test_output_shape_same_dim(self):
        """GRN with input_size == output_size returns matching shape."""
        grn = GatedResidualNetwork(
            input_size=16, hidden_size=32, output_size=16
        )
        x = torch.randn(4, 10, 16)
        out = grn(x)
        assert out.shape == (4, 10, 16)

    def test_output_shape_projected(self):
        """GRN with input_size != output_size projects skip correctly."""
        grn = GatedResidualNetwork(
            input_size=16, hidden_size=32, output_size=8
        )
        x = torch.randn(2, 5, 16)
        out = grn(x)
        assert out.shape == (2, 5, 8)

    def test_gradient_flow(self):
        """Gradients flow through the GRN."""
        grn = GatedResidualNetwork(8, 16, 8)
        x = torch.randn(3, 7, 8, requires_grad=True)
        out = grn(x)
        out.sum().backward()
        assert x.grad is not None
        assert torch.isfinite(x.grad).all()
        assert x.grad.abs().sum() > 0


class TestLightweightTFT:
    """Tests for the LightweightTFT model."""

    @pytest.fixture
    def small_model(self):
        """Reusable small TFT for fast tests."""
        return LightweightTFT(
            n_customers=10,
            hidden_size=32,
            n_heads=4,
            forecast_horizon=7,
            n_layers=1,
            dropout=0.0,
        )

    def test_forward_pass_shape(self, small_model):
        """Forward returns (batch, horizon, n_customers) and attention map."""
        x = torch.randn(4, 30, 10)
        output, attn = small_model(x)
        assert output.shape == (4, 7, 10)
        # Multi-head attention with average_attn_weights=True returns
        # (batch, seq_len, seq_len)
        assert attn.shape == (4, 30, 30)

    def test_attention_rows_sum_to_one(self, small_model):
        """Each attention row is a probability distribution over the sequence."""
        x = torch.randn(2, 30, 10)
        _, attn = small_model(x)
        row_sums = attn.sum(dim=-1)
        assert torch.allclose(
            row_sums, torch.ones_like(row_sums), atol=1e-5
        )
        assert torch.all(attn >= 0)

    def test_output_finite(self, small_model):
        """Output and attention contain only finite values."""
        x = torch.randn(2, 30, 10)
        output, attn = small_model(x)
        assert torch.isfinite(output).all()
        assert torch.isfinite(attn).all()

    def test_gradient_flow(self, small_model):
        """Gradients flow end-to-end through the TFT."""
        x = torch.randn(2, 30, 10, requires_grad=True)
        output, _ = small_model(x)
        output.sum().backward()
        assert x.grad is not None
        assert torch.isfinite(x.grad).all()
        assert x.grad.abs().sum() > 0

    def test_n_heads_must_divide_hidden_size(self):
        """``hidden_size`` must be divisible by ``n_heads`` (PyTorch MHA)."""
        with pytest.raises(AssertionError):
            LightweightTFT(
                n_customers=4,
                hidden_size=10,
                n_heads=4,
                forecast_horizon=3,
            )

    def test_parameter_count_lightweight(self, small_model):
        """The lightweight variant is smaller than a full TFT (sanity check)."""
        n_params = sum(p.numel() for p in small_model.parameters())
        # With hidden_size=32, n_layers=1, this should be well under 100K.
        assert n_params < 100_000
        assert n_params > 0

    def test_parameter_count_below_full_tft(self):
        """Lightweight TFT (hidden=64) is smaller than a full TFT (~1M params).

        The full TFT (Lim et al. 2021) with variable selection networks,
        static covariate encoders, and decoder GRNs typically has ~1M+
        parameters at hidden_size=160 with realistic feature counts. Our
        lightweight variant strips the variable-selection and static-covariate
        machinery, so a same-hidden-size build should sit well under 1M.
        """
        light = LightweightTFT(
            n_customers=100,
            hidden_size=64,
            n_heads=4,
            forecast_horizon=7,
            n_layers=2,
            dropout=0.1,
        )
        n_params = sum(p.numel() for p in light.parameters())
        # Full TFT in the original paper is ~1M+ parameters; our lightweight
        # version drops variable-selection + static-covariate stacks so it
        # must come in well under that threshold.
        assert n_params < 1_000_000
        assert n_params > 1_000

    def test_reproducibility_under_fixed_seed(self):
        """Two TFT runs under identical seed produce identical outputs.

        Validates determinism contract used by ``LSTMForecaster`` and
        downstream regression tests. Dropout is set to 0.0 to remove
        stochastic regularization and isolate the seed-driven init path.
        """
        def build_and_run():
            torch.manual_seed(123)
            model = LightweightTFT(
                n_customers=10,
                hidden_size=32,
                n_heads=4,
                forecast_horizon=7,
                n_layers=1,
                dropout=0.0,
            )
            model.eval()
            torch.manual_seed(123)
            x = torch.randn(2, 30, 10)
            with torch.no_grad():
                output, attn = model(x)
            return output, attn

        out1, attn1 = build_and_run()
        out2, attn2 = build_and_run()
        assert torch.equal(out1, out2)
        assert torch.equal(attn1, attn2)


class TestLSTMForecasterTFTIntegration:
    """LSTMForecaster correctly dispatches to the TFT when configured."""

    def test_tft_selection(self, tmp_path):
        """``model_type="tft"`` instantiates ``LightweightTFT``."""
        config = LSTMConfig(
            model_type="tft",
            tft_hidden_size=16,
            tft_n_heads=4,
            forecast_horizon=7,
            n_layers=1,
            tft_dropout=0.0,
        )
        forecaster = LSTMForecaster(
            input_size=10, config=config,
            checkpoint_dir=str(tmp_path),
        )
        assert forecaster.model.__class__.__name__ == "LightweightTFT"
        assert forecaster._model_type == "tft"

    def test_default_path_uses_attention_lstm(self, tmp_path):
        """Default path remains ``AttentionLSTMModel`` (preservation C3.1)."""
        config = LSTMConfig()  # model_type defaults to "attention_lstm"
        forecaster = LSTMForecaster(
            input_size=10, config=config,
            checkpoint_dir=str(tmp_path),
        )
        assert forecaster.model.__class__.__name__ == "AttentionLSTMModel"
        assert forecaster._model_type == "attention_lstm"

    def test_tft_predict_shape(self, tmp_path):
        """``predict`` returns ``(n, horizon, n_customers)`` for the TFT path."""
        config = LSTMConfig(
            model_type="tft",
            tft_hidden_size=16,
            tft_n_heads=4,
            forecast_horizon=7,
            n_layers=1,
            tft_dropout=0.0,
            epochs=1,
            batch_size=4,
        )
        forecaster = LSTMForecaster(
            input_size=10, config=config,
            checkpoint_dir=str(tmp_path),
        )
        X = np.random.randn(5, 30, 10).astype(np.float32)
        preds = forecaster.predict(X)
        assert preds.shape == (5, 7, 10)
        assert np.isfinite(preds).all()

    def test_tft_train_smoke(self, tmp_path):
        """Training the TFT for one epoch runs end-to-end and saves a checkpoint."""
        config = LSTMConfig(
            model_type="tft",
            tft_hidden_size=16,
            tft_n_heads=4,
            forecast_horizon=7,
            n_layers=1,
            tft_dropout=0.0,
            epochs=1,
            batch_size=8,
        )
        forecaster = LSTMForecaster(
            input_size=10, config=config,
            checkpoint_dir=str(tmp_path),
        )
        n = 32
        X_train = np.random.randn(n, 30, 10).astype(np.float32)
        y_train = np.random.randn(n, 7, 10).astype(np.float32)
        X_val = np.random.randn(8, 30, 10).astype(np.float32)
        y_val = np.random.randn(8, 7, 10).astype(np.float32)

        history = forecaster.train(
            X_train, y_train, X_val, y_val, patience=2
        )
        assert history["epochs_trained"] >= 1
        assert np.isfinite(history["train_losses"][0])
        # Checkpoint path is shared with the LSTM (same wrapper).
        assert (tmp_path / "best_lstm.pt").exists()
