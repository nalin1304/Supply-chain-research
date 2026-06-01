"""Property-based and preservation tests for the LSTM forecaster.

This module covers task 4.5 of the supply-chain-research-audit spec.
It is deliberately separate from ``tests/test_lstm.py`` (legacy unit
tests) and ``tests/test_tft_forecaster.py`` (FIX-009 TFT-baseline
regression) so the three named ``Test*`` classes required by the task
land in one auditable file. Style and hypothesis cadence mirror
``tests/test_emission_model.py`` (task 4.1),
``tests/test_nsga2_solver.py`` (task 4.3), and
``tests/test_des_environment.py`` (task 4.4).

The three classes encode the LSTM forecaster contract surfaced in
``.kiro/specs/supply-chain-research-audit/bugfix.md``:

* ``TestInputShapeContract``  -- ``AttentionLSTMModel`` accepts the
  documented ``(batch, seq_len, n_features)`` input grid for the
  default ``LSTMConfig`` without raising and returns finite values
  [Hochreiter-1997 §3] [bugfix.md C1.5 / C2.5].
* ``TestOutputShapeContract`` -- ``model(x).shape`` is exactly
  ``(batch, forecast_horizon, n_features)`` -- the multi-feature
  contract documented in ``AttentionLSTMModel.forward`` (which
  generalises the simplified ``(batch, horizon)`` contract noted in
  the task) [Hochreiter-1997 §3] [bugfix.md C1.5 / C2.5].
* ``TestNoDataLeakage``       -- normalization statistics
  (``train_mean``, ``train_std``) recorded by
  ``DemandDataGenerator.temporal_split`` are computed on the train
  slice only; perturbations confined to the val/test source-day
  windows leave them bit-for-bit unchanged [Tashman-2000 §3]
  [bugfix.md C1.12 / C2.12].

Workaround note for ``TestNoDataLeakage``
-----------------------------------------
The production wrapper ``LSTMForecaster`` does not expose explicit
``fit_normalizer`` / ``transform`` methods; the entire normalization
pipeline is performed inline by
``DemandDataGenerator.temporal_split``, which fits ``train_mean`` /
``train_std`` on ``X[train_indices]`` and applies them uniformly to
val / test. The leakage tests therefore verify the equivalent
property at the API actually exposed: (1) the recorded
``train_mean`` / ``train_std`` match a manually-computed mean / std
of the train slice, (2) corrupting only val/test source days does
not perturb the recorded train stats, and (3) repeated invocations
on identical inputs are bit-for-bit deterministic.

References
----------
.. [Hochreiter-1997] Hochreiter, S. & Schmidhuber, J. (1997).
   Long Short-Term Memory. Neural Computation, 9(8), 1735-1780.
   doi:10.1162/neco.1997.9.8.1735.
.. [Tashman-2000] Tashman, L. J. (2000). Out-of-sample tests of
   forecasting accuracy: an analysis and review. International
   Journal of Forecasting, 16(4), 437-450.
   doi:10.1016/S0169-2070(00)00065-0.
"""
# [Hochreiter-1997 §3] LSTM contract anchor; [Tashman-2000 §3]
# out-of-sample / no-data-leakage anchor; preservation per
# [bugfix.md C1.5 / C2.5 / C1.12 / C2.12]; mirrors hypothesis cadence
# in tests/test_emission_model.py (task 4.1),
# tests/test_nsga2_solver.py (task 4.3), and
# tests/test_des_environment.py (task 4.4).

from __future__ import annotations

import numpy as np  # [numeric stats for leakage tests]
import pytest
import torch  # [PyTorch — Hochreiter-1997 LSTM forward path]
from hypothesis import HealthCheck, given, settings, strategies as st

from supply_chain_research.config import LSTMConfig  # [config FIX-002]
from supply_chain_research.phase3_ai.data_generator import (  # [SUT — split]
    DemandDataGenerator,
)
from supply_chain_research.phase3_ai.lstm_forecaster import (  # [SUT — model]
    AttentionLSTMModel,
    LSTMForecaster,
)


# Project-wide preservation seed mandated by clauses C3.x; matches the
# seed used in tests/test_emission_model.py and tests/test_nsga2_solver.py.
_SEED = 42  # [bugfix.md project-wide preservation seed]

# Forward-passes through PyTorch LSTMs are CPU-bound; pin the thread
# count so hypothesis examples behave deterministically across hosts.
torch.set_num_threads(1)  # [task 4.5 — determinism for hypothesis budget]


# ---------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------


def _make_small_lstm(input_size: int = 8) -> AttentionLSTMModel:
    """Construct a small ``AttentionLSTMModel`` for fast property tests.

    Parameters
    ----------
    input_size : int, optional
        Number of input features (``n_customers``); default ``8``
        keeps each forward-pass under a few milliseconds so the
        hypothesis budget (``max_examples=8``) finishes promptly.

    Returns
    -------
    AttentionLSTMModel
        A freshly-initialised model in eval mode -- dropout is
        disabled so repeated forward passes are deterministic
        [Hochreiter-1997 §3 forget-gate init].
    """
    cfg = LSTMConfig()  # [config FIX-002 — production defaults]
    torch.manual_seed(_SEED)  # [seed=42 → deterministic init]
    model = AttentionLSTMModel(input_size=input_size, config=cfg)
    model.eval()  # [disable dropout for deterministic forwards]
    return model


def _make_demand_series(
    n_customers: int = 8,
    n_years: int = 1,
    seed: int = _SEED,
):
    """Generate a small synthetic demand series via ``DemandDataGenerator``.

    Parameters
    ----------
    n_customers : int, optional
        Customer count; default ``8`` to keep test arrays small.
    n_years : int, optional
        Number of years of daily data; default ``1`` so the
        block-bootstrap Diwali holdout in ``temporal_split`` produces
        a single, predictable test block (the lone Diwali run).
    seed : int, optional
        Generator seed; default ``42``.

    Returns
    -------
    gen : DemandDataGenerator
        The generator instance (carries ``n_customers`` / ``n_years``
        / ``seed`` attributes used by ``temporal_split``).
    demand : numpy.ndarray, shape (n_days, n_customers)
        Raw daily demand series.
    """
    gen = DemandDataGenerator(  # [synthetic data — task 4.5]
        n_customers=n_customers, n_years=n_years, seed=seed,
    )
    data = gen.generate()
    return gen, data["demand"]


# =====================================================================
# 1. TestInputShapeContract -- model accepts the documented input grid
# =====================================================================


class TestInputShapeContract:
    """``AttentionLSTMModel`` accepts the documented input grid.

    [Hochreiter-1997 §3] specifies a fixed-input-size LSTM with no
    constraint on the sequence length presented at runtime; the
    project's ``AttentionLSTMModel`` follows that contract. The
    encoder lookback ``seq_length`` is data-driven via PACF
    (``select_lookback_window``), so the forward path must be robust
    to any lookback in the range used by the audit (we sweep
    ``{7, 14, 30}``). Batch size is also unconstrained.

    Validates: Requirements 1.12, 2.12 [bugfix.md C1.5 / C2.5]
    """

    def test_default_config_input_size(self):
        """Default ``LSTMConfig`` gives ``forecast_horizon == 7``.

        Sanity-check: the rest of the suite depends on ``horizon=7``,
        which is the production default and is also asserted by
        ``MasterConfig.validate_consistency`` upstream
        [bugfix.md C3.1 / C3.12].

        Validates: Requirements 1.12, 2.12 [bugfix.md C1.5 / C2.5]
        """
        cfg = LSTMConfig()  # [config FIX-002 — defaults]
        assert cfg.seq_length == 30  # [encoder lookback default]
        assert cfg.forecast_horizon == 7  # [decoder horizon default]
        assert cfg.hidden_size == 128  # [Hochreiter-1997 §3 hidden width]
        assert cfg.n_layers == 2  # [stacked LSTM contract]

    def test_smoke_default_grid_point(self):
        """Default ``(batch=4, seq_len=30, n_features=8)`` runs forward.

        Provides a non-hypothesis floor so a regression that breaks
        the forward path is caught even if the property test happens
        to skip its first example for any reason.

        Validates: Requirements 1.12, 2.12 [bugfix.md C1.5 / C2.5]
        """
        model = _make_small_lstm(input_size=8)  # [small model]
        x = torch.randn(4, 30, 8)  # [(batch, seq_len, n_features)]
        with torch.no_grad():  # [eval-mode forward — no autograd]
            out = model(x)
        assert torch.isfinite(out).all()  # [no NaN/Inf]
        assert out.dtype == torch.float32  # [model dtype contract]

    @given(  # [grid per task 4.5 — batch x seq_len sweep]
        batch=st.sampled_from([1, 2, 4, 8]),
        seq_len=st.sampled_from([7, 14, 30]),
    )
    @settings(  # [match tests/test_emission_model.py cadence]
        max_examples=8,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_property_input_grid_runs_without_error(self, batch, seq_len):
        """Property: ``forall (batch, seq_len). model(x)`` is finite.

        Sweeps the documented ``(batch, seq_len, n_features)`` grid
        and asserts the forward pass returns finite values for every
        triple. ``n_features`` is fixed to ``8`` to match the active
        model build (the task spec mandates the active config and
        ``AttentionLSTMModel`` cannot accept a runtime-varying
        ``input_size`` because the projection ``fc_out`` is sized at
        ``__init__`` time per [Hochreiter-1997 §3]).

        Validates: Requirements 1.12, 2.12 [bugfix.md C1.5 / C2.5]
        """
        model = _make_small_lstm(input_size=8)  # [n_features fixed]
        x = torch.randn(batch, seq_len, 8)  # [grid sample]
        with torch.no_grad():  # [forward — no grad]
            out = model(x)
        assert torch.isfinite(out).all()  # [no NaN/Inf — Hochreiter §3]
        assert out.shape[0] == batch  # [batch dim preserved]


# =====================================================================
# 2. TestOutputShapeContract -- output shape exactly matches the docstring
# =====================================================================


class TestOutputShapeContract:
    """``AttentionLSTMModel`` output shape is the documented contract.

    The production docstring of ``AttentionLSTMModel.forward`` pins
    the output shape to ``(batch, forecast_horizon, input_size)`` --
    a multi-feature generalisation of the simplified
    ``(batch, horizon)`` contract noted in the task spec. Encoding
    that here means any future refactor that drops the per-customer
    feature dimension (or accidentally collapses the horizon) fails
    CI immediately [Hochreiter-1997 §3].

    Validates: Requirements 1.12, 2.12 [bugfix.md C1.5 / C2.5]
    """

    def test_smoke_default_grid_point(self):
        """Default ``(batch=2, seq_len=30, n_features=8)`` reaches horizon=7.

        Validates: Requirements 1.12, 2.12 [bugfix.md C1.5 / C2.5]
        """
        cfg = LSTMConfig()  # [defaults]
        model = _make_small_lstm(input_size=8)  # [small model]
        x = torch.randn(2, 30, 8)  # [(batch, seq_len, features)]
        with torch.no_grad():
            out = model(x)
        # [docstring contract — (batch, forecast_horizon, input_size)]
        assert out.shape == (2, cfg.forecast_horizon, 8)

    @given(  # [grid per task 4.5 — batch x seq_len sweep]
        batch=st.sampled_from([1, 2, 4, 8]),
        seq_len=st.sampled_from([7, 14, 30]),
    )
    @settings(  # [match tests/test_emission_model.py cadence]
        max_examples=8,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_property_output_shape_exact(self, batch, seq_len):
        """Property: ``forall (batch, seq_len). out.shape == (batch, H, F)``.

        ``H = config.forecast_horizon`` (default ``7``) and
        ``F = input_size`` (the model's fixed feature dimension).
        Asserting equality of the tuple -- not just the leading
        dimension -- catches any refactor that silently rearranges
        the output axes.

        Validates: Requirements 1.12, 2.12 [bugfix.md C1.5 / C2.5]
        """
        cfg = LSTMConfig()  # [defaults — horizon, n_layers]
        model = _make_small_lstm(input_size=8)  # [fixed feature dim]
        x = torch.randn(batch, seq_len, 8)  # [grid sample]
        with torch.no_grad():
            out = model(x)
        # [exact shape per AttentionLSTMModel.forward docstring]
        assert out.shape == (batch, cfg.forecast_horizon, 8)
        assert torch.isfinite(out).all()  # [defensive — no NaN/Inf]

    def test_lstm_forecaster_predict_shape_attention_lstm(self, tmp_path):
        """``LSTMForecaster.predict`` keeps the same output shape.

        ``LSTMForecaster`` is the training-and-inference wrapper; for
        the default ``model_type='attention_lstm'`` the predict path
        unwraps tensor outputs to numpy and must preserve the
        ``(n, horizon, n_features)`` shape.

        Validates: Requirements 1.12, 2.12 [bugfix.md C1.5 / C2.5]
        """
        cfg = LSTMConfig()  # [default model_type = attention_lstm]
        forecaster = LSTMForecaster(  # [wrapper FIX-009 dispatch]
            input_size=8, config=cfg, checkpoint_dir=str(tmp_path),
        )
        x = np.random.default_rng(_SEED).standard_normal(  # [seed=42]
            size=(3, cfg.seq_length, 8),
        ).astype(np.float32)
        preds = forecaster.predict(x)
        # [predict returns numpy with the same shape contract]
        assert preds.shape == (3, cfg.forecast_horizon, 8)
        assert np.isfinite(preds).all()  # [no NaN/Inf]


# =====================================================================
# 3. TestNoDataLeakage -- normalization fit on train slice only
# =====================================================================


class TestNoDataLeakage:
    """Normalization stats come from the train slice and never peek.

    The ``DemandDataGenerator.temporal_split`` pipeline is the only
    stage of the LSTM training path that fits any normalization
    statistics; ``LSTMForecaster`` does not expose its own
    ``fit_normalizer`` / ``transform`` methods, so the leakage
    contract is enforced here. Per [Tashman-2000 §3] the normalizer
    must be fit on the in-sample window only -- val/test data must
    never influence the recorded mean/std. The tests below verify
    that contract via three complementary properties:

    1. The recorded ``train_mean`` / ``train_std`` match a manually
       computed mean / std of the train slice (recovered from the
       returned normalised ``X_train`` via inverse normalisation).
    2. Two calls on identical inputs return identical statistics
       (deterministic snapshot — the documented "fit, snapshot,
       transform val/test" property collapsed onto the one-shot
       ``temporal_split`` API).
    3. Perturbing only val/test source days leaves the recorded
       ``train_mean`` / ``train_std`` bit-for-bit unchanged.

    Validates: Requirements 1.12, 2.12 [bugfix.md C1.12 / C2.12]
    """

    def test_split_metadata_is_well_formed(self):
        """``temporal_split`` returns the expected metadata keys.

        Sanity-floor for the assertions below; if the schema changes
        the rest of the suite fails fast with a clear error.

        Validates: Requirements 1.12, 2.12 [bugfix.md C1.12 / C2.12]
        """
        gen, demand = _make_demand_series()  # [seed=42, n_years=1]
        cfg = LSTMConfig()  # [defaults — seq_length=30, horizon=7]
        x_arr, y_arr = gen.create_sequences(  # [shape (n_samples, ...)]
            demand,
            seq_length=cfg.seq_length,
            forecast_horizon=cfg.forecast_horizon,
        )
        split = gen.temporal_split(  # [block-bootstrap Diwali holdout]
            x_arr, y_arr,
            seq_length=cfg.seq_length,
            forecast_horizon=cfg.forecast_horizon,
        )
        # [schema contract — used by the leakage tests below]
        for key in (
            "X_train", "X_val", "X_test",
            "y_train", "y_val", "y_test",
            "train_mean", "train_std",
            "n_train_samples", "n_val_samples", "n_test_samples",
        ):
            assert key in split  # [missing key would mask leakage]
        assert split["n_train_samples"] > 0  # [non-empty train]
        assert split["n_test_samples"] > 0  # [non-empty test]

    def test_train_stats_match_manual_train_slice(self):
        """``train_mean`` / ``train_std`` equal manual stats on train.

        Recovers the raw train slice from the returned normalised
        ``X_train`` via inverse normalisation
        (``X_train_raw = X_train * train_std + train_mean``) and
        re-computes the per-array mean / std. The recorded stats
        MUST match the manual ones to within a small numerical
        tolerance -- if they did not, the production code would have
        used a different slice (val/test peeking) to fit the
        normaliser [Tashman-2000 §3].

        Validates: Requirements 1.12, 2.12 [bugfix.md C1.12 / C2.12]
        """
        gen, demand = _make_demand_series()  # [seed=42 — deterministic]
        cfg = LSTMConfig()  # [defaults]
        x_arr, y_arr = gen.create_sequences(  # [(n, seq_len, n_cust)]
            demand,
            seq_length=cfg.seq_length,
            forecast_horizon=cfg.forecast_horizon,
        )
        split = gen.temporal_split(  # [Diwali block holdout]
            x_arr, y_arr,
            seq_length=cfg.seq_length,
            forecast_horizon=cfg.forecast_horizon,
        )
        train_mean = float(split["train_mean"])  # [recorded]
        train_std = float(split["train_std"])  # [recorded]
        # [recover raw train from normalised tensor — train fit only]
        x_train_raw = (
            split["X_train"].astype(np.float64) * train_std + train_mean
        )
        manual_mean = float(x_train_raw.mean())  # [Tashman-2000 §3]
        manual_std = float(x_train_raw.std())  # [Tashman-2000 §3]
        # [absolute tolerance — float32 round-trip noise <= 1e-3]
        assert manual_mean == pytest.approx(train_mean, rel=1e-4, abs=1e-3)
        assert manual_std == pytest.approx(train_std, rel=1e-4, abs=1e-3)

    def test_normalised_train_slice_has_unit_stats(self):
        """``X_train`` has zero mean and unit std after normalisation.

        Algebraic consequence of fitting on the train slice only --
        if the production code peeked at val/test the post-norm train
        mean would not be zero, because the subtracted mean would not
        equal the train slice's own mean [Tashman-2000 §3].

        Validates: Requirements 1.12, 2.12 [bugfix.md C1.12 / C2.12]
        """
        gen, demand = _make_demand_series()  # [seed=42]
        cfg = LSTMConfig()  # [defaults]
        x_arr, y_arr = gen.create_sequences(  # [(n, seq_len, n_cust)]
            demand,
            seq_length=cfg.seq_length,
            forecast_horizon=cfg.forecast_horizon,
        )
        split = gen.temporal_split(
            x_arr, y_arr,
            seq_length=cfg.seq_length,
            forecast_horizon=cfg.forecast_horizon,
        )
        x_train = split["X_train"].astype(np.float64)  # [normalised]
        # [unit-stat contract — fitted on train slice]
        assert float(x_train.mean()) == pytest.approx(0.0, abs=1e-3)
        assert float(x_train.std()) == pytest.approx(1.0, abs=1e-3)

    def test_repeated_split_is_deterministic(self):
        """Two calls on identical inputs return identical stats.

        The "fit, snapshot, transform val/test" property collapsed
        onto the one-shot ``temporal_split`` API: invoking the
        pipeline twice on the same input must produce bit-for-bit
        identical ``train_mean`` / ``train_std`` (i.e. no hidden
        state mutates the normaliser between calls).

        Validates: Requirements 1.12, 2.12 [bugfix.md C1.12 / C2.12]
        """
        gen_a, demand_a = _make_demand_series(seed=_SEED)  # [seed=42]
        gen_b, demand_b = _make_demand_series(seed=_SEED)  # [seed=42]
        cfg = LSTMConfig()  # [defaults]
        # [identical inputs — generators are seeded identically]
        np.testing.assert_array_equal(demand_a, demand_b)
        x_a, y_a = gen_a.create_sequences(
            demand_a,
            seq_length=cfg.seq_length,
            forecast_horizon=cfg.forecast_horizon,
        )
        x_b, y_b = gen_b.create_sequences(
            demand_b,
            seq_length=cfg.seq_length,
            forecast_horizon=cfg.forecast_horizon,
        )
        split_a = gen_a.temporal_split(  # [first invocation]
            x_a, y_a,
            seq_length=cfg.seq_length,
            forecast_horizon=cfg.forecast_horizon,
        )
        split_b = gen_b.temporal_split(  # [second invocation]
            x_b, y_b,
            seq_length=cfg.seq_length,
            forecast_horizon=cfg.forecast_horizon,
        )
        # [bit-for-bit equality — no state leak between calls]
        assert split_a["train_mean"] == split_b["train_mean"]
        assert split_a["train_std"] == split_b["train_std"]
        np.testing.assert_array_equal(
            split_a["X_train"], split_b["X_train"],
        )

    def test_no_peeking_when_val_test_days_are_perturbed(self):
        """Corrupting only val/test source days leaves train stats fixed.

        The strongest no-leakage assertion: if ``train_mean`` and
        ``train_std`` were fit on the train slice only, perturbing
        source days that never appear in any train sample's window
        cannot change them. The Diwali-block holdout in
        ``temporal_split`` is data-derived, so we discover the train
        day-coverage at runtime (rather than hard-coding day
        boundaries that would silently drift if the split logic
        evolves). The procedure is:

        1. Run ``temporal_split`` once on the clean series and
           snapshot ``(train_mean, train_std)`` plus the source-day
           windows touched by every train sample.
        2. Pick a perturbation window that is disjoint from the
           train-day set above (we use the union of val + test
           source days).
        3. Re-run ``temporal_split`` on a perturbed series whose
           values inside that window carry a large additive offset
           and assert the two snapshots are bit-for-bit identical.

        [Tashman-2000 §3 — out-of-sample isolation].

        Validates: Requirements 1.12, 2.12 [bugfix.md C1.12 / C2.12]
        """
        gen_clean, demand_clean = _make_demand_series(seed=_SEED)
        cfg = LSTMConfig()  # [defaults — seq_length=30, horizon=7]
        x_clean, y_clean = gen_clean.create_sequences(
            demand_clean,
            seq_length=cfg.seq_length,
            forecast_horizon=cfg.forecast_horizon,
        )
        split_clean = gen_clean.temporal_split(
            x_clean, y_clean,
            seq_length=cfg.seq_length,
            forecast_horizon=cfg.forecast_horizon,
        )
        train_mean_clean = float(split_clean["train_mean"])  # [snapshot]
        train_std_clean = float(split_clean["train_std"])  # [snapshot]

        # [discover train-day coverage from the captured split — this
        #  avoids hard-coding boundaries that would drift if the split
        #  logic changes]
        n_train = int(split_clean["n_train_samples"])  # [recorded]
        n_val = int(split_clean["n_val_samples"])  # [recorded]
        n_test = int(split_clean["n_test_samples"])  # [recorded]
        assert n_train + n_val + n_test == x_clean.shape[0]
        # [build a boolean mask over source days touched by train]
        n_days = demand_clean.shape[0]  # [365 for n_years=1]
        # [reconstruct train sample indices: same logic as production
        #  temporal_split — Diwali-touching samples form the test
        #  block, the trailing val_ratio of non-test, non-Diwali
        #  samples are val, the rest are train]
        diwali_day_mask = np.zeros(n_days, dtype=bool)  # [days mask]
        for year in range(gen_clean.n_years):  # [Diwali per year]
            start_d = year * 365 + 285  # [Diwali start — data_generator]
            end_d = year * 365 + 320  # [Diwali end — data_generator]
            if end_d <= n_days:
                diwali_day_mask[start_d:end_d] = True  # [mark Diwali]
        n_samples = x_clean.shape[0]  # [n_days - seq_len - horizon + 1]
        diwali_sample = np.zeros(n_samples, dtype=bool)  # [sample mask]
        window = cfg.seq_length + cfg.forecast_horizon  # [37 days]
        for i in range(n_samples):
            diwali_sample[i] = diwali_day_mask[i:i + window].any()
        # [test = LAST run of Diwali-touching samples]
        test_idx: list[int] = []
        if diwali_sample.any():
            in_run, run_start = False, None
            runs = []
            for i, v in enumerate(diwali_sample):
                if v and not in_run:
                    in_run, run_start = True, i
                elif not v and in_run:
                    runs.append((run_start, i))
                    in_run = False
            if in_run:
                runs.append((run_start, n_samples))
            if runs:
                test_idx = list(range(*runs[-1]))  # [last run]
        non_test = [i for i in range(n_samples) if i not in set(test_idx)]
        non_test_non_diwali = [i for i in non_test if not diwali_sample[i]]
        n_val_calc = int(len(non_test_non_diwali) * 0.15)  # [val_ratio]
        val_idx = non_test_non_diwali[-n_val_calc:] if n_val_calc else []
        train_idx = [i for i in non_test if i not in set(val_idx)]
        # [sanity-check the reconstruction matches the split metadata]
        assert len(train_idx) == n_train  # [counts agree]
        assert len(val_idx) == n_val  # [counts agree]
        assert len(test_idx) == n_test  # [counts agree]
        # [build a day-coverage mask for train samples only]
        train_day_mask = np.zeros(n_days, dtype=bool)  # [train days]
        for i in train_idx:  # [each train sample reads days i..i+window]
            train_day_mask[i:i + window] = True
        # [perturb only days NOT in train coverage — i.e. pure val/test]
        perturb_day_mask = ~train_day_mask  # [val + test days only]
        assert perturb_day_mask.any(), (  # [must have non-train days]
            "Train coverage spans every source day; the perturbation "
            "test cannot construct a disjoint val/test window."
        )

        gen_pert, demand_pert = _make_demand_series(seed=_SEED)
        # [apply a large additive offset to the val/test-only days]
        demand_pert[perturb_day_mask, :] = (
            demand_pert[perturb_day_mask, :] + 1.0e6  # [huge offset]
        )
        x_pert, y_pert = gen_pert.create_sequences(
            demand_pert,
            seq_length=cfg.seq_length,
            forecast_horizon=cfg.forecast_horizon,
        )
        split_pert = gen_pert.temporal_split(
            x_pert, y_pert,
            seq_length=cfg.seq_length,
            forecast_horizon=cfg.forecast_horizon,
        )
        # [bit-for-bit identical — train stats untouched by val/test]
        assert split_pert["train_mean"] == train_mean_clean
        assert split_pert["train_std"] == train_std_clean
        # [Tashman-2000 §3 — out-of-sample window isolation]
        np.testing.assert_array_equal(  # [normalised train identical]
            split_pert["X_train"], split_clean["X_train"],
        )


# --- Merged from test_lstm.py ---

from supply_chain_research.phase3_ai.attention_lstm import (
    TemporalAttention,
)


class TestDataGenerator:
    """Tests for DemandDataGenerator."""

    def test_generate_shape(self):
        """Data generator produces correct shape."""
        gen = DemandDataGenerator(
            n_customers=10, n_years=1, seed=42
        )
        data = gen.generate()
        assert data['demand'].shape == (365, 10)
        assert data['n_days'] == 365
        assert data['n_customers'] == 10

    def test_generate_3_years(self):
        """Data generator produces 3 years of data."""
        gen = DemandDataGenerator(
            n_customers=100, n_years=3, seed=42
        )
        data = gen.generate()
        assert data['demand'].shape == (1095, 100)

    def test_non_negative_demand(self):
        """All demand values are non-negative."""
        gen = DemandDataGenerator(
            n_customers=50, n_years=2, seed=42
        )
        data = gen.generate()
        assert np.all(data['demand'] >= 0)

    def test_demand_always_positive(self):
        """Multiplicative model guarantees positive demand (no zeros)."""
        gen = DemandDataGenerator(n_customers=50, n_years=2, seed=42)
        data = gen.generate()
        assert np.all(data['demand'] > 0)

    def test_demand_weekly_periodicity(self):
        """Demand shows weekly periodicity."""
        gen = DemandDataGenerator(n_customers=1, n_years=1, seed=42)
        data = gen.generate()
        # Use only non-Diwali period to avoid spike dominating correlations
        demand = data['demand'][:280, 0]
        # Autocorrelation at lag 7 should be higher than lag 3
        n = len(demand)
        mean = demand.mean()
        var = demand.var()
        acf_7 = np.sum((demand[:n-7] - mean) * (demand[7:] - mean)) / (n * var)
        acf_3 = np.sum((demand[:n-3] - mean) * (demand[3:] - mean)) / (n * var)
        assert acf_7 > acf_3

    def test_demand_has_growth_trend(self):
        """Demand increases over time due to trend factor."""
        gen = DemandDataGenerator(n_customers=20, n_years=3, seed=42)
        data = gen.generate()
        demand = data['demand']
        # Average of year 3 should be higher than year 1
        year1_mean = demand[:365, :].mean()
        year3_mean = demand[730:, :].mean()
        assert year3_mean > year1_mean

    def test_demand_multiplicative_composition(self):
        """Verify demand model uses multiplicative (not additive) factors."""
        gen = DemandDataGenerator(n_customers=5, n_years=1, seed=42)
        data = gen.generate()
        demand = data['demand']
        # In multiplicative model, demand is always positive
        assert np.all(demand > 0)
        # And should have significant variation (not flat)
        cv = demand.std() / demand.mean()
        assert cv > 0.1  # Coefficient of variation should be substantial

    def test_diwali_spike(self):
        """Diwali period shows higher demand than average."""
        gen = DemandDataGenerator(
            n_customers=20, n_years=1, seed=42
        )
        data = gen.generate()
        demand = data['demand']

        # Diwali days: 285-320
        diwali_demand = demand[285:320, :].mean()
        # Non-diwali period
        non_diwali = np.concatenate([
            demand[:285, :], demand[320:, :]
        ], axis=0).mean()

        assert diwali_demand > non_diwali

    def test_create_sequences_shape(self):
        """Sequence creation produces correct shapes."""
        gen = DemandDataGenerator(
            n_customers=10, n_years=1, seed=42
        )
        data = gen.generate()
        X, y = gen.create_sequences(
            data['demand'], seq_length=30, forecast_horizon=7
        )

        n_expected = 365 - 30 - 7 + 1
        assert X.shape == (n_expected, 30, 10)
        assert y.shape == (n_expected, 7, 10)

    @pytest.mark.skip(reason="Audit 2.5: temporal_split replaced with block-bootstrap Diwali holdout")
    def test_temporal_split_ordering(self):
        """Temporal split preserves time ordering."""
        gen = DemandDataGenerator(
            n_customers=10, n_years=1, seed=42
        )
        data = gen.generate()
        X, y = gen.create_sequences(
            data['demand'], seq_length=30, forecast_horizon=7
        )
        split = gen.temporal_split(X, y)

        n_total = X.shape[0]
        n_train = int(n_total * 0.7)
        n_val = int(n_total * 0.15)

        assert split['X_train'].shape[0] == n_train
        assert split['X_val'].shape[0] == n_val - n_train + int(
            n_total * 0.7
        ) or split['X_val'].shape[0] > 0
        assert split['X_test'].shape[0] > 0

    def test_normalization_uses_train_stats(self):
        """Normalization uses only training set statistics."""
        gen = DemandDataGenerator(
            n_customers=10, n_years=1, seed=42
        )
        data = gen.generate()
        X, y = gen.create_sequences(
            data['demand'], seq_length=30, forecast_horizon=7
        )
        split = gen.temporal_split(X, y)

        # Training data should have mean close to 0
        train_mean = split['X_train'].mean()
        assert abs(train_mean) < 0.1

        # Check that stats are stored
        assert 'train_mean' in split
        assert 'train_std' in split
        assert split['train_std'] > 0


class TestTemporalAttention:
    """Tests for TemporalAttention module."""

    def test_output_shape(self):
        """Attention produces correct output shapes."""
        hidden_size = 128
        batch_size = 4
        seq_len = 30

        attn = TemporalAttention(hidden_size)
        hidden_states = torch.randn(batch_size, seq_len, hidden_size)

        context, weights = attn(hidden_states)
        assert context.shape == (batch_size, hidden_size)
        assert weights.shape == (batch_size, seq_len)

    def test_attention_weights_sum_to_one(self):
        """Attention weights sum to 1 across time dimension."""
        hidden_size = 64
        batch_size = 8
        seq_len = 30

        attn = TemporalAttention(hidden_size)
        hidden_states = torch.randn(batch_size, seq_len, hidden_size)

        _, weights = attn(hidden_states)
        weight_sums = weights.sum(dim=1)

        # Should sum to 1.0 for each sample in batch
        assert torch.allclose(
            weight_sums, torch.ones(batch_size), atol=1e-5
        )

    def test_attention_weights_non_negative(self):
        """Attention weights are non-negative (softmax output)."""
        attn = TemporalAttention(128)
        hidden_states = torch.randn(4, 30, 128)

        _, weights = attn(hidden_states)
        assert torch.all(weights >= 0)

    def test_gradient_flow(self):
        """Gradients flow through attention mechanism."""
        attn = TemporalAttention(64)
        hidden_states = torch.randn(2, 10, 64, requires_grad=True)

        context, _ = attn(hidden_states)
        loss = context.sum()
        loss.backward()

        assert hidden_states.grad is not None
        assert hidden_states.grad.abs().sum() > 0


class TestAttentionLSTMModelUnit:
    """Unit tests for AttentionLSTMModel."""

    def test_forward_pass_shape(self):
        """Model produces correct output shape."""
        config = LSTMConfig()
        input_size = 100  # n_customers
        model = AttentionLSTMModel(input_size, config)

        batch_size = 4
        x = torch.randn(batch_size, config.seq_length, input_size)
        output = model(x)

        assert output.shape == (
            batch_size, config.forecast_horizon, input_size
        )

    def test_forward_small_input(self):
        """Model works with small input size."""
        config = LSTMConfig()
        input_size = 10
        model = AttentionLSTMModel(input_size, config)

        x = torch.randn(2, 30, 10)
        output = model(x)
        assert output.shape == (2, 7, 10)

    def test_get_attention_weights(self):
        """get_attention_weights returns valid weights."""
        config = LSTMConfig()
        input_size = 10
        model = AttentionLSTMModel(input_size, config)

        x = torch.randn(3, 30, 10)
        weights = model.get_attention_weights(x)

        assert weights.shape == (3, 30)
        # Check they sum to 1
        sums = weights.sum(dim=1)
        assert torch.allclose(sums, torch.ones(3), atol=1e-5)


class TestLSTMForecasterUnit:
    """Unit tests for LSTMForecaster training wrapper."""

    def test_training_runs(self, tmp_path):
        """Training loop runs for a few epochs without error."""
        config = LSTMConfig(epochs=3, batch_size=8)
        input_size = 10
        n_samples = 50

        forecaster = LSTMForecaster(
            input_size, config,
            checkpoint_dir=str(tmp_path),
        )

        X_train = np.random.randn(n_samples, 30, input_size)
        y_train = np.random.randn(n_samples, 7, input_size)
        X_val = np.random.randn(20, 30, input_size)
        y_val = np.random.randn(20, 7, input_size)

        history = forecaster.train(
            X_train, y_train, X_val, y_val, patience=5
        )

        assert 'train_losses' in history
        assert len(history['train_losses']) > 0
        assert history['epochs_trained'] <= 3

    def test_predict_shape(self, tmp_path):
        """Predict returns correct shape."""
        config = LSTMConfig(epochs=1, batch_size=8)
        input_size = 10
        forecaster = LSTMForecaster(
            input_size, config,
            checkpoint_dir=str(tmp_path),
        )

        X = np.random.randn(5, 30, input_size)
        predictions = forecaster.predict(X)
        assert predictions.shape == (5, 7, input_size)

    def test_checkpoint_save(self, tmp_path):
        """Checkpoint is saved during training."""
        config = LSTMConfig(epochs=2, batch_size=8)
        input_size = 10

        forecaster = LSTMForecaster(
            input_size, config,
            checkpoint_dir=str(tmp_path),
        )

        X_train = np.random.randn(30, 30, input_size)
        y_train = np.random.randn(30, 7, input_size)
        X_val = np.random.randn(10, 30, input_size)
        y_val = np.random.randn(10, 7, input_size)

        forecaster.train(X_train, y_train, X_val, y_val)

        # Check checkpoint file exists
        checkpoint_file = tmp_path / 'best_lstm.pt'
        assert checkpoint_file.exists()

    def test_gradient_clipping_applied(self, tmp_path):
        """Gradient clipping is applied during training (max_norm=1.0)."""
        config = LSTMConfig(epochs=2, batch_size=8)
        input_size = 10
        n_samples = 30

        forecaster = LSTMForecaster(
            input_size, config, checkpoint_dir=str(tmp_path),
        )

        # Create data with large values to generate large gradients
        X_train = np.random.randn(n_samples, 30, input_size) * 100
        y_train = np.random.randn(n_samples, 7, input_size) * 100
        X_val = np.random.randn(10, 30, input_size) * 100
        y_val = np.random.randn(10, 7, input_size) * 100

        # Train - should not error even with large values due to clipping
        history = forecaster.train(X_train, y_train, X_val, y_val, patience=5)
        assert history['epochs_trained'] > 0
        # Verify model parameters are finite (clipping prevents explosion)
        for param in forecaster.model.parameters():
            assert torch.all(torch.isfinite(param))


class TestEdgeCaseData:
    """Tests for edge-case demand generation and augmented datasets."""

    def test_edge_case_demand_shape(self):
        """generate_edge_case_demand() returns array of shape (n_days, n_customers)."""
        gen = DemandDataGenerator(n_customers=10, n_years=1, seed=42)
        edge_demand = gen.generate_edge_case_demand()
        assert edge_demand.shape == (365, 10)

    def test_edge_case_demand_has_spikes(self):
        """Edge-case data contains values significantly larger than standard mean."""
        gen = DemandDataGenerator(n_customers=10, n_years=1, seed=42)
        standard_data = gen.generate()
        standard_mean = standard_data['demand'].mean()

        gen2 = DemandDataGenerator(n_customers=10, n_years=1, seed=42)
        edge_demand = gen2.generate_edge_case_demand()

        # Some values should be at least 2.5x the standard mean
        assert np.any(edge_demand > 2.5 * standard_mean)

    def test_edge_case_demand_positive(self):
        """All edge-case demand values are positive."""
        gen = DemandDataGenerator(n_customers=20, n_years=2, seed=99)
        edge_demand = gen.generate_edge_case_demand()
        assert np.all(edge_demand > 0)

    def test_augmented_dataset_ratio(self):
        """create_augmented_dataset() produces approximately 30% edge-case fraction."""
        gen = DemandDataGenerator(n_customers=10, n_years=1, seed=42)
        result = gen.create_augmented_dataset(
            seq_length=30, forecast_horizon=7, edge_case_ratio=0.3
        )

        # Standard sequences for 1 year, 10 customers: 365 - 30 - 7 + 1 = 329
        n_standard = 365 - 30 - 7 + 1
        n_total = result['X'].shape[0]
        n_edge_in_result = n_total - n_standard

        edge_fraction = n_edge_in_result / n_total
        # Should be between 25% and 35%
        assert 0.25 <= edge_fraction <= 0.35

    def test_augmented_dataset_shape(self):
        """X and y have correct dimensions in augmented dataset."""
        gen = DemandDataGenerator(n_customers=10, n_years=1, seed=42)
        result = gen.create_augmented_dataset(
            seq_length=30, forecast_horizon=7, edge_case_ratio=0.3
        )

        n_total = result['X'].shape[0]
        assert result['X'].shape == (n_total, 30, 10)
        assert result['y'].shape == (n_total, 7, 10)

