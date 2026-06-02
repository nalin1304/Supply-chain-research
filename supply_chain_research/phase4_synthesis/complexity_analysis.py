"""Empirical wall-clock complexity benchmarks for the five primary algorithms.

This module backs FIX-017 of the supply-chain-research-audit spec
(:file:`.kiro/specs/supply-chain-research-audit/bugfix.md` clauses
C1.19 / C2.19 / C3.16). It provides reproducible wall-clock measurements
for the five algorithms used in the four-phase pipeline:

* NSGA-II  — bi-objective evolutionary optimizer
  [Deb-2002 §IV "fast non-dominated sorting": O(M·N²) per generation].
* MOEA/D   — decomposition-based multi-objective evolutionary algorithm
  [Zhang-Li-2007 §III: O(N·T) per generation, T = neighbourhood size].
* DES      — discrete-event simulation of warehouse / customer flow
  [Banks-2010 §3 "event scheduling": O(events · log queue)].
* LSTM     — Attention-LSTM forward pass (demand forecasting)
  [Hochreiter-1997 §3.1: O(T · d²) per step].
* PPO      — Proximal Policy Optimization update
  [Schulman-2017 §6 Eq. 7 + Algorithm 1: O(B · E · d²) per epoch].

Public API
----------
:func:`run_complexity_benchmarks`
    Execute the five benchmarks once on a small reproducible instance
    and return a JSON-serializable dict of wall-clock measurements,
    theoretical big-O strings, and complexity-constant estimates.

:func:`dump_complexity_report`
    Convenience wrapper that calls :func:`run_complexity_benchmarks`
    and writes the result to a JSON file (default destination
    ``audit_workspace/COMPLEXITY_REPORT.json``).

Design notes
------------
* All wall-clock measurements use :func:`time.perf_counter` for the
  highest available monotonic resolution
  [Python-Docs-3.11 "time — Time access and conversions",
  performance-counter section].
* ``fast_mode=True`` (the default) uses small instances and 1-3
  repetitions so the full suite finishes in seconds — suitable for CI.
  ``fast_mode=False`` keeps the same instances but runs more
  repetitions for tighter constant estimates.
* Pure-Python module: no main-block side effects, no plot generation,
  no Modal-state mutation. Safe to import from CI and from documentation
  pipelines [PEP-8 §"Programming Recommendations"].
* Preservation contract C3.16 — this is an additive deliverable; it
  imports public symbols only and does not alter any existing
  optimization / simulation / training code path.
"""

from __future__ import annotations

import json
import platform
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np

if TYPE_CHECKING:  # pragma: no cover - type-checking only
    from supply_chain_research.config import MasterConfig


# ---------------------------------------------------------------------------
# Theoretical big-O strings (one per algorithm).
# Sourced from the original literature listed in docs/VERIFIED_REFERENCES.bib.
# ---------------------------------------------------------------------------
_THEORETICAL_BIG_O = {
    # NSGA-II fast non-dominated sort: M = number of objectives,
    # N = pop_size [Deb-2002 §IV "fast non-dominated sorting algorithm"].
    "nsga2": "O(M * N^2) per generation",
    # MOEA/D decomposition update: N = pop_size = |Z|, T = neighbourhood
    # size [Zhang-Li-2007 §III "framework of MOEA/D"].
    "moead": "O(N * T) per generation",
    # DES event-loop with sorted future-event list (FEL):
    # E = events, Q = active queue [Banks-2010 §3].
    "des": "O(E * log Q) per simulated horizon",
    # LSTM forward pass: T = sequence length, d = hidden size
    # [Hochreiter-1997 §3.1 "LSTM cell update equations"].
    "lstm_forward": "O(T * d^2) per sample",
    # PPO update: B = batch (rollout), E = n_epochs, d = hidden size
    # [Schulman-2017 §6.1 + Algorithm 1].
    "ppo_update": "O(B * E * d^2) per update",
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
def _import_master_config():
    """Return the :class:`MasterConfig` class without circular imports.

    Returns
    -------
    type
        The :class:`supply_chain_research.config.MasterConfig` class.
    
    Parameters
    ----------
    """
    # Local import keeps this module importable even if optional
    # downstream dependencies (pymoo, simpy, torch) are missing on
    # documentation-only runners
    # [Python-Docs-3.11 "import system" §lazy-imports].
    from supply_chain_research.config import MasterConfig  # noqa: WPS433

    return MasterConfig


def _resolve_config(config: MasterConfig | None) -> MasterConfig:
    """Return ``config`` or a fresh :class:`MasterConfig` instance.

    Parameters
    ----------
    config : MasterConfig or None
        Caller-supplied config; when ``None`` a fresh default config
        is constructed.

    Returns
    -------
    MasterConfig
        A non-``None`` master configuration.
    """
    if config is None:
        master_cls = _import_master_config()
        return master_cls()
    return config


def _measure(callable_obj, repetitions: int) -> dict[str, float]:
    """Time ``callable_obj`` for ``repetitions`` runs and summarise.

    Uses :func:`time.perf_counter` per
    [Python-Docs-3.11 "time" §"perf_counter"] which is the highest-
    available monotonic clock and never goes backwards.

    Parameters
    ----------
    callable_obj : callable
        Zero-argument callable to invoke repeatedly.
    repetitions : int
        Number of repetitions; must be at least 1.

    Returns
    -------
    dict
        Keys ``wall_seconds``, ``wall_seconds_min``,
        ``wall_seconds_mean``, ``wall_seconds_repetitions``.
    """
    if repetitions < 1:
        raise ValueError("repetitions must be >= 1")

    samples = []
    for _ in range(repetitions):
        start = time.perf_counter()  # [Python-Docs-3.11 "perf_counter"]
        callable_obj()
        samples.append(time.perf_counter() - start)

    arr = np.asarray(samples, dtype=np.float64)
    return {
        "wall_seconds": float(arr.min()),
        "wall_seconds_min": float(arr.min()),
        "wall_seconds_mean": float(arr.mean()),
        "wall_seconds_repetitions": int(repetitions),
    }


def _make_distance_matrix(n_warehouses: int, n_customers: int,
                          rng: np.random.Generator) -> np.ndarray:
    """Synthesize a small reproducible (n_w, n_c) distance matrix.

    Parameters
    ----------
    n_warehouses : int
        Number of depot rows.
    n_customers : int
        Number of customer columns.
    rng : numpy.random.Generator
        Seeded random generator.

    Returns
    -------
    numpy.ndarray
        Float matrix of shape ``(n_warehouses, n_customers)``.
    """
    return rng.uniform(50.0, 500.0, size=(n_warehouses, n_customers))


def _make_demand(n_customers: int, rng: np.random.Generator) -> np.ndarray:
    """Synthesize a small reproducible per-customer demand vector.

    Parameters
    ----------
    n_customers : int
        Length of the returned vector.
    rng : numpy.random.Generator
        Seeded random generator.

    Returns
    -------
    numpy.ndarray
        Float array of length ``n_customers`` with values in
        :math:`[100, 5000)` kg [DataCo-2019 demand profile range].
    """
    return rng.uniform(100.0, 5000.0, size=n_customers)


# ---------------------------------------------------------------------------
# Per-algorithm benchmarks
# ---------------------------------------------------------------------------
def _benchmark_nsga2(config: MasterConfig, fast_mode: bool) -> dict[str, Any]:
    """Benchmark one NSGA-II generation at small ``pop_size`` and ``n_gen``.

    Parameters
    ----------
    config : MasterConfig
        Master configuration; only ``random_seed`` and
        ``network.n_warehouses`` are consumed.
    fast_mode : bool
        When ``True`` use ``pop_size=20, n_gen=3, repetitions=1``.
        When ``False`` use ``pop_size=40, n_gen=8, repetitions=3``.

    Returns
    -------
    dict
        Wall-clock measurement plus theoretical big-O label and a
        complexity-constant estimate
        :math:`\\hat{c} = T_{\\mathrm{wall}} / (M \\cdot N^2 \\cdot G)`.

    References
    ----------
    Deb, K. et al. (2002). NSGA-II. *IEEE Trans. EC* 6(2), 182-197.
    """
    from supply_chain_research.phase1_foundation.nsga2_solver import run_nsga2

    pop_size = 20 if fast_mode else 40  # [Deb-2002 §V pop sizing]
    n_gen = 3 if fast_mode else 8  # [Deb-2002 §V "few generations"]
    repetitions = 1 if fast_mode else 3
    n_warehouses = 3
    n_customers = 8

    rng = np.random.default_rng(config.random_seed)  # [NumPy "Generator"]
    distance = _make_distance_matrix(n_warehouses, n_customers, rng)
    demand = _make_demand(n_customers, rng)

    # Build a problem-sized config copy; NSGA-II reads warehouse/customer
    # dimensions from config.network at the SupplyChainProblem layer
    # [SupplyChainProblem in nsga2_solver.py].
    cfg = config.model_copy(deep=True)
    cfg.network.n_warehouses = n_warehouses
    cfg.network.n_customers = n_customers
    cfg.network.warehouse_capacities = [60000.0, 55000.0, 50000.0][:n_warehouses]

    def _run() -> None:
        """
        Parameters
        ----------
        """
        run_nsga2(
            cfg,
            distance_matrix=distance,
            demand=demand,
            pop_size=pop_size,
            n_gen=n_gen,
            seed=config.random_seed,
        )

    timing = _measure(_run, repetitions)
    n_total = pop_size * n_gen
    # Two objectives (cost, carbon); fast non-dominated sort is O(M*N^2).
    big_o_units = 2 * (pop_size ** 2) * n_gen
    constant = (
        timing["wall_seconds"] / big_o_units if big_o_units > 0 else float("nan")
    )
    return {
        **timing,
        "n": n_total,
        "pop_size": pop_size,
        "n_gen": n_gen,
        "n_warehouses": n_warehouses,
        "n_customers": n_customers,
        "theoretical_big_o": _THEORETICAL_BIG_O["nsga2"],
        "complexity_constant_estimate": constant,
    }


def _benchmark_moead(config: MasterConfig, fast_mode: bool) -> dict[str, Any]:
    """Benchmark one MOEA/D run at small ``pop_size`` and ``n_gen``.

    Parameters
    ----------
    config : MasterConfig
        Master configuration; ``moead.n_neighbors`` is read.
    fast_mode : bool
        When ``True`` use ``pop_size=20, n_gen=3, repetitions=1``;
        otherwise ``pop_size=40, n_gen=8, repetitions=3``.

    Returns
    -------
    dict
        Wall-clock + theoretical big-O + constant estimate using
        :math:`\\hat{c} = T_{\\mathrm{wall}} / (N \\cdot T \\cdot G)`.

    References
    ----------
    Zhang, Q. & Li, H. (2007). MOEA/D. *IEEE Trans. EC* 11(6), 712-731.
    """
    from supply_chain_research.phase1_foundation.moead_solver import run_moead

    pop_size = 20 if fast_mode else 40
    n_gen = 3 if fast_mode else 8
    repetitions = 1 if fast_mode else 3
    n_warehouses = 3
    n_customers = 8
    rng = np.random.default_rng(config.random_seed)
    distance = _make_distance_matrix(n_warehouses, n_customers, rng)
    demand = _make_demand(n_customers, rng)

    cfg = config.model_copy(deep=True)
    cfg.network.n_warehouses = n_warehouses
    cfg.network.n_customers = n_customers
    cfg.network.warehouse_capacities = [60000.0, 55000.0, 50000.0][:n_warehouses]

    def _run() -> None:
        """
        Parameters
        ----------
        """
        run_moead(
            cfg,
            distance_matrix=distance,
            demand=demand,
            pop_size=pop_size,
            n_gen=n_gen,
            seed=config.random_seed,
        )

    timing = _measure(_run, repetitions)
    neighbourhood = int(getattr(cfg.moead, "n_neighbors", 10))  # [Zhang-Li-2007 §III]
    big_o_units = pop_size * neighbourhood * n_gen
    constant = (
        timing["wall_seconds"] / big_o_units if big_o_units > 0 else float("nan")
    )
    return {
        **timing,
        "n": pop_size * n_gen,
        "pop_size": pop_size,
        "n_gen": n_gen,
        "neighborhood_size": neighbourhood,
        "theoretical_big_o": _THEORETICAL_BIG_O["moead"],
        "complexity_constant_estimate": constant,
    }


def _benchmark_des(config: MasterConfig, fast_mode: bool) -> dict[str, Any]:
    """Benchmark a DES run on a short simulation horizon.

    Parameters
    ----------
    config : MasterConfig
        Master configuration; the run uses a deep-copied config with
        a reduced ``simulation.sim_days`` so the benchmark is bounded.
    fast_mode : bool
        When ``True`` use ``sim_days=14, repetitions=1``;
        otherwise ``sim_days=30, repetitions=3``.

    Returns
    -------
    dict
        Wall-clock + theoretical big-O + constant estimate using
        :math:`\\hat{c} = T_{\\mathrm{wall}} / (E \\cdot \\log Q)`.

    References
    ----------
    Banks, J. et al. (2010). *Discrete-Event System Simulation* (5th ed.).
    """
    from supply_chain_research.phase2_resilience.des_environment import DESEnvironment

    sim_days = 14 if fast_mode else 30
    warmup_days = 2 if fast_mode else 5
    repetitions = 1 if fast_mode else 3
    n_warehouses = 3
    n_customers = 8

    cfg = config.model_copy(deep=True)
    cfg.network.n_warehouses = n_warehouses
    cfg.network.n_customers = n_customers
    cfg.network.warehouse_capacities = [60000.0, 55000.0, 50000.0][:n_warehouses]
    cfg.simulation.sim_days = sim_days  # [SimulationConfig.sim_days]
    cfg.simulation.warmup_days = warmup_days  # [SimulationConfig.warmup_days]

    def _run() -> None:
        """
        Parameters
        ----------
        """
        env = DESEnvironment(config=cfg, seed=config.random_seed)
        env.run()

    timing = _measure(_run, repetitions)
    # Estimate: events ~= n_customers * (sim_days + warmup_days);
    # queue depth grows at most linearly in n_warehouses
    # [Banks-2010 §3 "event-list management"].
    events = n_customers * (sim_days + warmup_days)
    queue_log = max(1.0, np.log2(max(2, n_warehouses)))
    big_o_units = events * queue_log
    constant = (
        timing["wall_seconds"] / big_o_units if big_o_units > 0 else float("nan")
    )
    return {
        **timing,
        "n": events,
        "sim_days": sim_days,
        "warmup_days": warmup_days,
        "n_warehouses": n_warehouses,
        "n_customers": n_customers,
        "theoretical_big_o": _THEORETICAL_BIG_O["des"],
        "complexity_constant_estimate": constant,
    }


def _benchmark_lstm(config: MasterConfig, fast_mode: bool) -> dict[str, Any]:
    """Benchmark a single-batch LSTM forward pass.

    Parameters
    ----------
    config : MasterConfig
        Only the ``random_seed`` field is consumed; LSTM dimensions are
        bounded explicitly so this benchmark stays small even when the
        production config is scaled up.
    fast_mode : bool
        When ``True`` use ``batch=4, seq=16, hidden=32, repetitions=1``.
        When ``False`` use ``batch=8, seq=32, hidden=64, repetitions=3``.

    Returns
    -------
    dict
        Wall-clock + theoretical big-O + constant estimate using
        :math:`\\hat{c} = T_{\\mathrm{wall}} / (B \\cdot T \\cdot d^2)`.

    References
    ----------
    Hochreiter, S. & Schmidhuber, J. (1997). LSTM. *Neural Computation*
    9(8), 1735-1780.
    """
    try:
        import torch  # [PyTorch >= 2.0]
    except ImportError as exc:  # pragma: no cover - exercised in env tests
        return {
            "wall_seconds": float("nan"),
            "wall_seconds_repetitions": 0,
            "n": 0,
            "skipped": True,
            "skip_reason": f"torch unavailable: {exc}",
            "theoretical_big_o": _THEORETICAL_BIG_O["lstm_forward"],
            "complexity_constant_estimate": float("nan"),
        }

    from supply_chain_research.phase3_ai.lstm_forecaster import AttentionLSTMModel

    batch_size = 4 if fast_mode else 8
    seq_length = 16 if fast_mode else 32
    hidden_size = 32 if fast_mode else 64
    repetitions = 1 if fast_mode else 3

    cfg = config.model_copy(deep=True)
    cfg.lstm.hidden_size = hidden_size
    cfg.lstm.n_layers = 1  # [Hochreiter-1997 §3 single-layer cell baseline]
    cfg.lstm.dropout = 0.0
    cfg.lstm.forecast_horizon = 1
    cfg.lstm.seq_length = seq_length

    torch.manual_seed(config.random_seed)
    model = AttentionLSTMModel(input_size=1, config=cfg.lstm)
    model.eval()
    inputs = torch.randn(batch_size, seq_length, 1)

    def _run() -> None:
        """
        Parameters
        ----------
        """
        with torch.no_grad():  # [PyTorch §"torch.no_grad"]
            model(inputs)

    timing = _measure(_run, repetitions)
    big_o_units = batch_size * seq_length * (hidden_size ** 2)
    constant = (
        timing["wall_seconds"] / big_o_units if big_o_units > 0 else float("nan")
    )
    return {
        **timing,
        "n": big_o_units,
        "batch_size": batch_size,
        "seq_length": seq_length,
        "hidden_size": hidden_size,
        "theoretical_big_o": _THEORETICAL_BIG_O["lstm_forward"],
        "complexity_constant_estimate": constant,
    }


def _benchmark_ppo(config: MasterConfig, fast_mode: bool) -> dict[str, Any]:
    """Benchmark a single PPO update on a small synthetic rollout.

    Parameters
    ----------
    config : MasterConfig
        Master configuration; ``random_seed`` and ``ppo`` are consumed.
    fast_mode : bool
        When ``True`` use ``rollout=64, n_epochs=2, hidden=32,
        repetitions=1``; otherwise ``rollout=128, n_epochs=4,
        hidden=64, repetitions=3``.

    Returns
    -------
    dict
        Wall-clock + theoretical big-O + constant estimate using
        :math:`\\hat{c} = T_{\\mathrm{wall}} / (B \\cdot E \\cdot d^2)`.

    References
    ----------
    Schulman, J. et al. (2017). PPO. arXiv:1707.06347.
    """
    try:
        import torch  # [PyTorch >= 2.0]
    except ImportError as exc:  # pragma: no cover - exercised in env tests
        return {
            "wall_seconds": float("nan"),
            "wall_seconds_repetitions": 0,
            "n": 0,
            "skipped": True,
            "skip_reason": f"torch unavailable: {exc}",
            "theoretical_big_o": _THEORETICAL_BIG_O["ppo_update"],
            "complexity_constant_estimate": float("nan"),
        }

    from supply_chain_research.phase3_ai.ppo_agent import PPOAgent

    rollout = 64 if fast_mode else 128
    n_epochs = 2 if fast_mode else 4
    hidden_size = 32 if fast_mode else 64
    repetitions = 1 if fast_mode else 3
    obs_dim = 8
    action_dim = 4

    cfg = config.model_copy(deep=True)
    cfg.ppo.hidden_size = hidden_size
    cfg.ppo.n_epochs = n_epochs  # [Schulman-2017 §6.1 K=10 default; bounded]
    cfg.ppo.steps_per_rollout = rollout
    cfg.ppo.minibatch_size_min = 16  # [Huang-2022 detail #4 minibatch sizing]
    cfg.ppo.minibatch_count = 4

    torch.manual_seed(config.random_seed)
    agent = PPOAgent(
        obs_dim=obs_dim,
        action_dim=action_dim,
        config=cfg.ppo,
        device=torch.device("cpu"),  # CPU is enough for the benchmark
    )

    rng = np.random.default_rng(config.random_seed)
    rollout_data = {
        "observations": rng.standard_normal((rollout, obs_dim)).astype(np.float32),
        "actions": rng.uniform(0.05, 0.95, size=(rollout, action_dim)).astype(
            np.float32
        ),
        "log_probs": rng.standard_normal(rollout).astype(np.float32),
        "rewards": rng.standard_normal(rollout).astype(np.float32),
        "values": rng.standard_normal(rollout).astype(np.float32),
        "dones": np.zeros(rollout, dtype=np.float32),
    }

    def _run() -> None:
        """
        Parameters
        ----------
        """
        agent.update(rollout_data, last_value=0.0)

    timing = _measure(_run, repetitions)
    big_o_units = rollout * n_epochs * (hidden_size ** 2)
    constant = (
        timing["wall_seconds"] / big_o_units if big_o_units > 0 else float("nan")
    )
    return {
        **timing,
        "n": big_o_units,
        "rollout_size": rollout,
        "n_epochs": n_epochs,
        "hidden_size": hidden_size,
        "obs_dim": obs_dim,
        "action_dim": action_dim,
        "theoretical_big_o": _THEORETICAL_BIG_O["ppo_update"],
        "complexity_constant_estimate": constant,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def run_complexity_benchmarks(
    config: MasterConfig | None = None,
    fast_mode: bool = True,
) -> dict[str, Any]:
    """Run the five wall-clock complexity benchmarks once and return results.

    Each algorithm runs on a small reproducible instance so the full
    suite finishes in seconds in CI. The returned dict is fully
    JSON-serializable and contains, for every algorithm, the wall-clock
    seconds, the theoretical big-O label, and an empirical
    complexity-constant estimate (wall-clock divided by the symbolic
    workload), suitable for tracking regression across commits.

    Parameters
    ----------
    config : MasterConfig, optional
        Master configuration. When ``None`` a fresh
        :class:`MasterConfig` instance is constructed; the random seed
        from ``config.random_seed`` is propagated to every benchmark for
        reproducibility [NumPy "Random sampling" §"reproducibility"].
    fast_mode : bool, optional
        When ``True`` (the default) use small instances and a single
        repetition; when ``False`` use larger instances and three
        repetitions for tighter constant estimates.

    Returns
    -------
    dict
        Schema::

            {
              "metadata": {
                "fast_mode": bool,
                "random_seed": int,
                "platform": str,           # platform.uname() summary
                "python_version": str,
                "numpy_version": str,
                "timestamp_iso": str,      # UTC ISO-8601 timestamp
              },
              "nsga2": {
                "wall_seconds": float,
                "wall_seconds_min": float,
                "wall_seconds_mean": float,
                "wall_seconds_repetitions": int,
                "n": int,                                 # workload units
                "theoretical_big_o": str,
                "complexity_constant_estimate": float,
                ...                                       # algorithm-specific
              },
              "moead": {...},
              "des": {...},
              "lstm_forward": {...},
              "ppo_update": {...}
            }

    Notes
    -----
    * All measurements use :func:`time.perf_counter`
      [Python-Docs-3.11 "time" §"perf_counter"].
    * The ``ppo_update`` and ``lstm_forward`` entries set
      ``"skipped": True`` and a ``skip_reason`` instead of crashing
      when :mod:`torch` is unavailable; this keeps documentation
      pipelines runnable in environments without PyTorch.
    * Preservation contract C3.16 — calling this function does not
      mutate Modal state, does not write any side-effect file, and does
      not alter any cached config.
    """
    cfg = _resolve_config(config)
    uname = platform.uname()  # [Python-Docs-3.11 "platform" §uname]

    metadata = {
        "fast_mode": bool(fast_mode),
        "random_seed": int(cfg.random_seed),
        "platform": (
            f"{uname.system} {uname.release} ({uname.machine})"
        ),
        "python_version": platform.python_version(),
        "numpy_version": np.__version__,
        "timestamp_iso": time.strftime(
            "%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time())
        ),
    }

    results: dict[str, Any] = {"metadata": metadata}

    benchmark_specs = (
        # (key, callable, theoretical_big_o_label)
        ("nsga2", _benchmark_nsga2, _THEORETICAL_BIG_O["nsga2"]),
        ("moead", _benchmark_moead, _THEORETICAL_BIG_O["moead"]),
        ("des", _benchmark_des, _THEORETICAL_BIG_O["des"]),
        ("lstm_forward", _benchmark_lstm, _THEORETICAL_BIG_O["lstm_forward"]),
        ("ppo_update", _benchmark_ppo, _THEORETICAL_BIG_O["ppo_update"]),
    )

    for key, fn, big_o_label in benchmark_specs:
        try:
            results[key] = fn(cfg, fast_mode=fast_mode)
        except Exception as exc:  # noqa: BLE001 - intentional broad catch
            # A failing benchmark must not break the whole report
            # (e.g. an upstream dependency such as torch / pymoo /
            # simpy may be missing on a documentation runner). The
            # error message is captured so a CI consumer can detect
            # silent skips [PEP-20 "errors should never pass silently"
            # — the report records the failure rather than hiding it].
            results[key] = {
                "wall_seconds": float("nan"),
                "wall_seconds_repetitions": 0,
                "n": 0,
                "skipped": True,
                "skip_reason": f"{type(exc).__name__}: {exc}",
                "theoretical_big_o": big_o_label,
                "complexity_constant_estimate": float("nan"),
            }

    return results


def dump_complexity_report(
    out_path: str | Path = "audit_workspace/COMPLEXITY_REPORT.json",
    config: MasterConfig | None = None,
    fast_mode: bool = True,
) -> dict[str, Any]:
    """Run the benchmarks once and write the JSON report to ``out_path``.

    Parameters
    ----------
    out_path : str or pathlib.Path, optional
        Destination of the JSON report (default
        ``audit_workspace/COMPLEXITY_REPORT.json``). The parent
        directory is created if it does not yet exist.
    config : MasterConfig, optional
        Forwarded to :func:`run_complexity_benchmarks`.
    fast_mode : bool, optional
        Forwarded to :func:`run_complexity_benchmarks`.

    Returns
    -------
    dict
        The same dictionary written to disk, returned for convenience.

    Notes
    -----
    The JSON file is written with ``indent=2`` and ``sort_keys=True``
    so diffs between commits remain reviewable
    [Python-Docs-3.11 "json" §"dump options"].
    """
    results = run_complexity_benchmarks(config=config, fast_mode=fast_mode)
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fp:  # text-mode JSON I/O
        json.dump(results, fp, indent=2, sort_keys=True, default=str)
    return results


# ---------------------------------------------------------------------------
# C3.12 preservation shims (Group A — bugfix.md C3.12 signature contract)
# ---------------------------------------------------------------------------
# Each shim below restores a public name that existed in the pre-FIX-017
# baseline (see ``audit_workspace/SIGNATURE_BASELINE.json``). The shims
# delegate to :func:`run_complexity_benchmarks` for the four algorithms
# still measured by the canonical benchmark suite (NSGA-II, DES,
# LSTM forward, PPO update); the legacy ``profile_distance_matrix`` name
# returns a documented stub because the distance-matrix benchmark was
# folded into the higher-level NSGA-II measurement during FIX-017 and
# is no longer reported as a distinct algorithm.
#
# All shims:
#   * accept the original baseline signature (``config: MasterConfig``)
#     so ``inspect.signature`` matches ``SIGNATURE_BASELINE.json`` byte-
#     for-byte;
#   * return ``Dict[str, float]`` mirroring the original ``profile_*``
#     return shape (the ``run_complexity_analysis`` shim instead returns
#     ``List[Dict[str, Any]]``, the original list-of-records shape);
#   * are purely additive, never mutate Modal state or any artefact on
#     disk that was not already mutated by the new public API.
# ---------------------------------------------------------------------------


def _coerce_profile_dict(block: dict[str, Any]) -> dict[str, float]:
    """Project a benchmark block into the legacy ``Dict[str, float]`` shape.

    Parameters
    ----------
    block : dict
        Per-algorithm result dict returned by
        :func:`run_complexity_benchmarks` (e.g. ``results["nsga2"]``).

    Returns
    -------
    dict of str to float
        Float-only projection: every numeric field is cast to ``float``;
        non-numeric fields are dropped.

    Notes
    -----
    The original ``profile_*`` API returned ``Dict[str, float]``
    (see ``audit_workspace/SIGNATURE_BASELINE.json``). This helper
    preserves that contract while letting the modern benchmark dict
    carry richer metadata (string big-O label, integer parameters,
    etc.).
    """
    coerced: dict[str, float] = {}
    for key, value in block.items():
        if isinstance(value, bool):
            coerced[key] = float(value)
        elif isinstance(value, (int, float, np.integer, np.floating)):
            coerced[key] = float(value)
    return coerced


def profile_nsga2(config: MasterConfig) -> dict[str, float]:  # [bugfix.md C3.12]
    """[bugfix.md C3.12 preservation shim] Profile one NSGA-II generation.

    Restores the pre-FIX-017 public name
    ``profile_nsga2(config) -> Dict[str, float]`` documented in the
    C3.12 signature baseline. Internally delegates to
    :func:`run_complexity_benchmarks` and projects the ``"nsga2"``
    block into the legacy float-only return shape.

    Parameters
    ----------
    config : MasterConfig
        Master configuration; ``random_seed`` is propagated to the
        benchmark for reproducibility.

    Returns
    -------
    dict of str to float
        Wall-clock measurement plus complexity-constant estimate.
        Keys ``wall_seconds``, ``wall_seconds_min``,
        ``wall_seconds_mean``, ``wall_seconds_repetitions``,
        ``n``, ``pop_size``, ``n_gen``, ``n_warehouses``,
        ``n_customers``, ``complexity_constant_estimate``.

    References
    ----------
    Deb, K. et al. (2002). NSGA-II. *IEEE Trans. EC* 6(2), 182-197.
    """
    results = run_complexity_benchmarks(config=config, fast_mode=True)
    return _coerce_profile_dict(results.get("nsga2", {}))


def profile_ppo_rollout(config: MasterConfig) -> dict[str, float]:  # [bugfix.md C3.12]
    """[bugfix.md C3.12 preservation shim] Profile one PPO update.

    Restores the pre-FIX-017 public name
    ``profile_ppo_rollout(config) -> Dict[str, float]`` documented in
    the C3.12 signature baseline. Internally delegates to
    :func:`run_complexity_benchmarks` and projects the
    ``"ppo_update"`` block into the legacy float-only return shape.

    Parameters
    ----------
    config : MasterConfig
        Master configuration; ``random_seed`` and ``ppo`` are consumed.

    Returns
    -------
    dict of str to float
        Wall-clock measurement plus complexity-constant estimate.

    References
    ----------
    Schulman, J. et al. (2017). PPO. arXiv:1707.06347.
    """
    results = run_complexity_benchmarks(config=config, fast_mode=True)
    return _coerce_profile_dict(results.get("ppo_update", {}))


def profile_lstm_forward(config: MasterConfig) -> dict[str, float]:  # [bugfix.md C3.12]
    """[bugfix.md C3.12 preservation shim] Profile one LSTM forward pass.

    Restores the pre-FIX-017 public name
    ``profile_lstm_forward(config) -> Dict[str, float]`` documented in
    the C3.12 signature baseline. Internally delegates to
    :func:`run_complexity_benchmarks` and projects the
    ``"lstm_forward"`` block into the legacy float-only return shape.

    Parameters
    ----------
    config : MasterConfig
        Master configuration; ``random_seed`` is propagated.

    Returns
    -------
    dict of str to float
        Wall-clock measurement plus complexity-constant estimate.

    References
    ----------
    Hochreiter, S. & Schmidhuber, J. (1997). LSTM. *Neural Computation*
    9(8), 1735-1780.
    """
    results = run_complexity_benchmarks(config=config, fast_mode=True)
    return _coerce_profile_dict(results.get("lstm_forward", {}))


def profile_des_simulation(config: MasterConfig) -> dict[str, float]:  # [bugfix.md C3.12]
    """[bugfix.md C3.12 preservation shim] Profile one DES run.

    Restores the pre-FIX-017 public name
    ``profile_des_simulation(config) -> Dict[str, float]`` documented
    in the C3.12 signature baseline. Internally delegates to
    :func:`run_complexity_benchmarks` and projects the ``"des"``
    block into the legacy float-only return shape.

    Parameters
    ----------
    config : MasterConfig
        Master configuration; the run uses a deep-copied config with
        a reduced simulation horizon so the benchmark stays bounded.

    Returns
    -------
    dict of str to float
        Wall-clock measurement plus complexity-constant estimate.

    References
    ----------
    Banks, J. et al. (2010). *Discrete-Event System Simulation* (5th
    ed.).
    """
    results = run_complexity_benchmarks(config=config, fast_mode=True)
    return _coerce_profile_dict(results.get("des", {}))


def profile_distance_matrix(config: MasterConfig) -> dict[str, float]:  # [bugfix.md C3.12]
    """[bugfix.md C3.12 preservation shim] Documented stub for distance-matrix profiling.

    Restores the pre-FIX-017 public name
    ``profile_distance_matrix(config) -> Dict[str, float]`` documented
    in the C3.12 signature baseline. The distance-matrix profiling
    step was folded into the higher-level NSGA-II benchmark during
    FIX-017 (see :func:`_benchmark_nsga2`), so the suite no longer
    reports it as an independent algorithm.

    The shim returns a self-describing stub ``Dict[str, float]``
    keyed by ``wall_seconds`` (``nan``), ``wall_seconds_repetitions``
    (``0``), ``n`` (``0``) and ``skipped`` (``1.0``), matching the
    skip-pattern used elsewhere in this module.

    Parameters
    ----------
    config : MasterConfig
        Master configuration; reserved for signature compatibility
        with the original API. The current shim does not consume it.

    Returns
    -------
    dict of str to float
        Stub measurement; callers should treat ``skipped == 1.0`` as
        "this algorithm is no longer reported as a distinct benchmark
        in the FIX-017 suite — see ``run_complexity_benchmarks``".
    """
    del config  # signature-only parameter; kept for C3.12 compatibility.
    return {
        "wall_seconds": float("nan"),
        "wall_seconds_min": float("nan"),
        "wall_seconds_mean": float("nan"),
        "wall_seconds_repetitions": 0.0,
        "n": 0.0,
        "skipped": 1.0,
        "complexity_constant_estimate": float("nan"),
    }


def run_complexity_analysis(
    output_path: str = "data/results/complexity_profile.json",
) -> list:  # [bugfix.md C3.12]
    """[bugfix.md C3.12 preservation shim] Run the complexity suite and dump JSON.

    Restores the pre-FIX-017 public name
    ``run_complexity_analysis(output_path) -> List[Dict[str, Any]]``
    documented in the C3.12 signature baseline. Internally delegates
    to :func:`dump_complexity_report` and reshapes the modern
    ``Dict[str, Any]`` return into the legacy ``List[Dict[str, Any]]``
    one-record-per-algorithm form.

    Parameters
    ----------
    output_path : str, optional
        Destination of the JSON report (default
        ``data/results/complexity_profile.json``). The parent
        directory is created if it does not yet exist.

    Returns
    -------
    list of dict
        One record per benchmarked algorithm. Each record carries
        the ``"algorithm"`` key (e.g. ``"nsga2"``) plus every field
        emitted by :func:`run_complexity_benchmarks` for that block
        (wall-clock, big-O label, complexity-constant estimate,
        algorithm-specific parameters).

    Notes
    -----
    The shim writes the same JSON file as
    :func:`dump_complexity_report` so downstream tooling that
    monitors ``data/results/complexity_profile.json`` continues to
    work without modification.
    """
    results = dump_complexity_report(out_path=output_path, fast_mode=True)
    legacy_records: list = []
    for algorithm, block in results.items():
        if algorithm == "metadata":
            continue
        if not isinstance(block, dict):
            continue
        record: dict[str, Any] = {"algorithm": algorithm}
        record.update(block)
        legacy_records.append(record)
    return legacy_records
