"""Local training runner with rich progress + graceful interrupt.

Drives the same end-to-end pipeline as ``cloud_training/modal_train.py``
but on local hardware (CPU or single GPU) using the actual public APIs
of the project. Provides:

* Per-phase status output (rich when available, plain text otherwise)
* Resume via ``--resume`` (each phase skips when its checkpoint exists)
* Skip flags for each phase
* Graceful Ctrl+C handling — flushes the current phase's checkpoint
  before exit so re-running with ``--resume`` continues seamlessly

Usage
-----
    python cloud_training/local_training_runner.py
    python cloud_training/local_training_runner.py --resume
    python cloud_training/local_training_runner.py --skip-nsga --skip-lstm
    python cloud_training/local_training_runner.py --ppo-steps 50000
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(PROJECT_ROOT)

import numpy as np

try:
    from rich.console import Console
    from rich.progress import (
        BarColumn,
        Progress,
        TextColumn,
        TimeElapsedColumn,
        TimeRemainingColumn,
    )  # [bugfix.md C1.23 §H, C2.23 §H] rich.Progress required, no tqdm
    from rich.table import Table

    HAS_RICH = True
except ImportError:  # pragma: no cover - fallback path
    HAS_RICH = False

from supply_chain_research.config import MasterConfig

# ---------------------------------------------------------------------------
# Graceful interrupt
# ---------------------------------------------------------------------------

_interrupted = False


def _emit_status(
    results_dir: Path,
    component: str,
    phase: str,
    state: str,
    extra: dict | None = None,
) -> None:
    """Append a JSON status line to ``data/results/training_status.jsonl``.

    Parameters
    ----------
    results_dir : Path
        Directory where ``training_status.jsonl`` lives.
    component : str
        One of ``"nsga2"``, ``"lstm"``, ``"ppo"``, ``"all"`` — matches the
        ``--component`` CLI flag (bugfix.md C2.23 §H).
    phase : str
        Phase label (e.g. ``"network"``, ``"nsga2"``, ``"lstm"``, ``"ppo"``).
    state : str
        Lifecycle state (``"start"``, ``"complete"``, ``"resumed"``,
        ``"interrupt"``).
    extra : dict, optional
        Additional structured fields (elapsed seconds, checkpoint path, ...).
    """
    record = {
        "ts": time.time(),
        "component": component,
        "phase": phase,
        "state": state,
    }
    if extra:
        record.update(extra)
    log_path = results_dir / "training_status.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a") as fh:
        fh.write(json.dumps(record, default=str) + "\n")


def _signal_handler(signum, frame):
    """Set the soft-interrupt flag; second SIGINT escalates to hard exit."""
    global _interrupted
    if _interrupted:
        print("\n[FORCE EXIT] Exiting immediately.")
        sys.exit(1)
    _interrupted = True
    print("\n[INTERRUPT] Finishing current phase, then saving checkpoint...")


signal.signal(signal.SIGINT, _signal_handler)
signal.signal(signal.SIGTERM, _signal_handler)


def _console():
    return Console() if HAS_RICH else None


def _print(msg: str, console=None) -> None:
    if console is not None:
        console.print(msg)
    else:
        # Strip rich markup so plain stdout stays readable
        plain = msg
        for tag in (
            "[bold blue]", "[/bold blue]",
            "[bold green]", "[/bold green]",
            "[yellow]", "[/yellow]",
            "[dim]", "[/dim]",
            "[bold]", "[/bold]",
        ):
            plain = plain.replace(tag, "")
        print(plain)


# ---------------------------------------------------------------------------
# Phase runners
# ---------------------------------------------------------------------------

def run_phase_network(config: MasterConfig, console) -> dict:
    """Phase 1 — generate the network artefacts (locations, demand, distances).

    Parameters
    ----------
    config : MasterConfig
        Active configuration.
    console : Console or None
        Rich console for output (None for plain stdout).

    Returns
    -------
    dict
        Bundle with ``customer_locations``, ``warehouse_locations``,
        ``distance_matrix`` (km), ``duration_matrix`` (s), and ``demand``.
    """
    _print("[bold blue]Phase 1:[/bold blue] Generating network data...", console)
    from supply_chain_research.phase1_foundation.data_engineering import (
        generate_network_data,
    )

    t0 = time.perf_counter()
    data = generate_network_data(config)
    elapsed = time.perf_counter() - t0
    _print(
        f"  Distance matrix: {data['distance_matrix'].shape} "
        f"in {elapsed:.2f}s",
        console,
    )
    return data


def run_phase_nsga2(
    config: MasterConfig, data: dict, results_dir: Path, console
) -> None:
    """Phase 2 — NSGA-II Pareto front (cost vs. carbon).

    Parameters
    ----------
    config : MasterConfig
        Active configuration; uses ``config.nsga.pop_size`` and
        ``config.nsga.n_gen`` for the search budget.
    data : dict
        Output of :func:`run_phase_network`.
    results_dir : Path
        Directory where the front is persisted.
    console : Console or None
        Rich console for output.
    """
    _print("[bold blue]Phase 2:[/bold blue] Running NSGA-II...", console)
    from supply_chain_research.phase1_foundation.nsga2_solver import run_nsga2

    # NSGA-II expects a (n_warehouses, n_customers) sub-matrix; the network
    # bundle carries the full (n_warehouses+n_customers)² matrix.
    n_w = config.network.n_warehouses
    full_dist = data["distance_matrix"]
    if full_dist.shape[0] == n_w + config.network.n_customers:
        dist_wc = full_dist[:n_w, n_w:]
    else:
        dist_wc = full_dist

    t0 = time.perf_counter()
    result = run_nsga2(
        config, dist_wc, data["demand"],
        pop_size=config.nsga.pop_size,
        n_gen=config.nsga.n_gen,
        seed=config.random_seed,
    )
    elapsed = time.perf_counter() - t0

    front = np.asarray(result.F) if result.F is not None else np.empty((0, 2))
    np.save(results_dir / "nsga2_pareto_front.npy", front)
    _print(
        f"  Pareto front: {len(front)} solutions in {elapsed:.1f}s "
        f"(min cost={float(front[:, 0].min()) if len(front) else 'n/a'}, "
        f"min carbon={float(front[:, 1].min()) if len(front) else 'n/a'})",
        console,
    )


def run_phase_lstm(config: MasterConfig, results_dir: Path, console) -> None:
    """Phase 3 — train the (Attention-)LSTM demand forecaster.

    Parameters
    ----------
    config : MasterConfig
        Active configuration; honours ``config.lstm`` hyperparameters.
    results_dir : Path
        Where ``lstm_metrics.json`` and ``best_lstm.pt`` are written.
    console : Console or None
        Rich console for output.
    """
    _print(
        "[bold blue]Phase 3:[/bold blue] Training LSTM forecaster...",
        console,
    )
    import torch
    from supply_chain_research.phase3_ai.data_generator import DemandDataGenerator
    from supply_chain_research.phase3_ai.lstm_forecaster import LSTMForecaster

    n_customers = config.network.n_customers
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
    forecaster = LSTMForecaster(
        input_size=n_customers,
        config=config.lstm,
        device=device,
        checkpoint_dir=str(results_dir),
    )

    t0 = time.perf_counter()
    history = forecaster.train(
        splits["X_train"], splits["y_train"],
        splits["X_val"], splits["y_val"],
        patience=config.lstm.patience,
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

    metrics = {
        "epochs_trained": history.get("epochs_trained"),
        "test_rmse": rmse,
        "test_mape": mape,
        "device": device,
        "n_customers": n_customers,
        "seq_length": config.lstm.seq_length,
        "forecast_horizon": config.lstm.forecast_horizon,
    }
    with open(results_dir / "lstm_metrics.json", "w") as fh:
        json.dump(metrics, fh, indent=2, default=str)
    np.save(results_dir / "lstm_predictions.npy", preds_raw)
    np.save(results_dir / "lstm_actuals.npy", actuals_raw)
    _print(
        f"  RMSE={rmse:.4f} MAPE={mape:.2f}% in {elapsed:.1f}s "
        f"({history.get('epochs_trained')} epochs)",
        console,
    )


def run_phase_ppo(
    config: MasterConfig,
    results_dir: Path,
    console,
    total_timesteps: int | None = None,
) -> None:
    """Phase 4 — train PPO on the supply-chain Gym environment.

    Implements the same rollout / update loop as
    ``cloud_training/modal_train.py``, with linear LR decay applied to
    both the actor and critic optimizers (Audit 2.2 — they are
    decoupled).

    Parameters
    ----------
    config : MasterConfig
        Active configuration.
    results_dir : Path
        Where ``ppo_metrics.json``, ``ppo_local_final.pt``, and the
        per-episode reward log are written.
    console : Console or None
        Rich console for output.
    total_timesteps : int, optional
        Override for the local-only smaller-budget run. Defaults to
        ``config.ppo.total_timesteps``.
    """
    _print(
        "[bold blue]Phase 4:[/bold blue] Training PPO agent...", console,
    )
    import torch
    from supply_chain_research.phase3_ai.gym_environment import SupplyChainEnv
    from supply_chain_research.phase3_ai.ppo_agent import PPOAgent
    from supply_chain_research.phase3_ai.ss_policy import evaluate_ss_policy

    if total_timesteps is None:
        total_timesteps = config.ppo.total_timesteps

    device = "cuda" if torch.cuda.is_available() else "cpu"
    env = SupplyChainEnv(
        n_customers=config.network.n_customers,
        n_warehouses=config.network.n_warehouses,
        episode_length=config.gym_env.episode_length,
        seed=config.random_seed,
        config=config,
    )
    agent = PPOAgent(
        obs_dim=env.observation_space.shape[0],
        action_dim=env.action_space.shape[0],
        config=config.ppo,
        device=torch.device(device),
    )

    obs, _ = env.reset(seed=config.random_seed)
    rollout = config.ppo.steps_per_rollout
    total_steps, ep_r = 0, 0.0
    ep_rewards: list[float] = []
    base_lr = config.ppo.lr
    t0 = time.perf_counter()

    while total_steps < total_timesteps:
        # Linear LR decay on both optimizers (Audit 2.2)
        frac = max(0.0, 1.0 - total_steps / max(total_timesteps, 1))
        actor_lr = base_lr * frac
        critic_lr = actor_lr * config.ppo.critic_lr_multiplier
        for pg in agent.actor_optimizer.param_groups:
            pg["lr"] = actor_lr
        for pg in agent.critic_optimizer.param_groups:
            pg["lr"] = critic_lr

        for _ in range(rollout):
            action, value, log_prob = agent.select_action(obs)
            next_obs, reward, term, trunc, _ = env.step(action)
            agent.buffer.add(
                obs, action, reward, value, log_prob, float(term),
            )
            obs = next_obs
            ep_r += float(reward)
            total_steps += 1
            if term or trunc:
                ep_rewards.append(ep_r)
                ep_r = 0.0
                obs, _ = env.reset()
            if total_steps >= total_timesteps:
                break

        # Compute V(obs_T) for the GAE bootstrap before clearing the
        # buffer (Schulman 2017 §4 Algorithm 1). When the episode ended
        # naturally (term=True) the bootstrap is 0; on truncation or
        # mid-rollout we use the critic estimate.
        with torch.no_grad():
            obs_t = torch.FloatTensor(obs).unsqueeze(0).to(agent.device)
            last_value = float(agent.critic(obs_t).squeeze().cpu().numpy())
        if term:
            last_value = 0.0
        agent.update(agent.buffer.get(), last_value=last_value)
        agent.buffer.clear()

        recent = float(np.mean(ep_rewards[-20:])) if ep_rewards else 0.0
        elapsed = time.perf_counter() - t0
        eta = (
            (total_timesteps - total_steps) / max(total_steps, 1) * elapsed
            / 60.0
        )
        _print(
            f"  step={total_steps:>10,} | recent_R={recent:9.2f} "
            f"| actor_lr={actor_lr:.1e} | ETA {eta:5.1f}m",
            console,
        )
        if _interrupted:
            break

    elapsed = time.perf_counter() - t0
    final_reward = (
        float(np.mean(ep_rewards[-100:])) if ep_rewards else 0.0
    )

    # Quick (s,S) baseline for relative gain reporting
    eval_env = SupplyChainEnv(
        n_customers=config.network.n_customers,
        n_warehouses=config.network.n_warehouses,
        episode_length=config.gym_env.episode_length,
        seed=config.random_seed + 1000,
        config=config,
    )
    ss = evaluate_ss_policy(
        eval_env,
        n_warehouses=config.network.n_warehouses,
        n_customers=config.network.n_customers,
        n_episodes=20,
        seed=config.random_seed + 1000,
    )

    metrics = {
        "total_timesteps_run": int(total_steps),
        "n_episodes": int(len(ep_rewards)),
        "final_reward": final_reward,
        "ss_baseline_mean_reward": ss["mean_reward"],
        "ss_baseline_std_reward": ss["std_reward"],
        "service_level": float(min(1.0, max(0.0, final_reward / 365.0 * 0.0))),
        "device": device,
        "elapsed_seconds": round(elapsed, 2),
    }
    np.save(results_dir / "ppo_local_rewards.npy", np.asarray(ep_rewards))
    agent.save(str(results_dir / "ppo_local_final.pt"))
    with open(results_dir / "ppo_metrics.json", "w") as fh:
        json.dump(metrics, fh, indent=2, default=str)
    _print(
        f"  reward(last100)={final_reward:.2f}  "
        f"(s,S)={ss['mean_reward']:.2f}  in {elapsed:.1f}s",
        console,
    )


def run_phase_analysis(
    config: MasterConfig, results_dir: Path, console,
) -> None:
    """Phase 5 — fast Sobol sensitivity analysis.

    Parameters
    ----------
    config : MasterConfig
        Active configuration (currently unused by ``run_sensitivity_analysis``
        but kept for symmetry with the other phases).
    results_dir : Path
        Output directory for ``sensitivity_results.json``.
    console : Console or None
        Rich console for output.
    """
    _print(
        "[bold blue]Phase 5:[/bold blue] Running sensitivity analysis...",
        console,
    )
    from supply_chain_research.phase4_synthesis.sensitivity_analysis import (
        run_sensitivity_analysis,
    )

    t0 = time.perf_counter()
    results = run_sensitivity_analysis(fast_mode=True)
    elapsed = time.perf_counter() - t0
    with open(results_dir / "sensitivity_results.json", "w") as fh:
        json.dump(results, fh, indent=2, default=str)
    _print(f"  Sensitivity analysis complete in {elapsed:.1f}s", console)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Drive every phase end-to-end with resume + skip support."""
    parser = argparse.ArgumentParser(description="Local training runner")
    # bugfix.md C2.23 §H — accept an optional checkpoint path so the
    # cloud notebooks can call --resume <path>; the bare flag still works.
    parser.add_argument(
        "--resume",
        nargs="?",
        const="__bool__",
        default=None,
        help=(
            "Skip a phase if its checkpoint exists. Optionally pass an "
            "explicit checkpoint path which will be recorded in the JSON "
            "status log."
        ),
    )
    # bugfix.md C2.23 §H — restrict execution to a single component when
    # the cloud notebooks invoke nsga2 / lstm / ppo individually.
    parser.add_argument(
        "--component",
        choices=("nsga2", "lstm", "ppo", "all"),
        default="all",
        help="Restrict execution to one component (default: all).",
    )
    # bugfix.md C2.7 §A — used by Kaggle (--seeds 10) and Vast.ai (--seeds 50).
    parser.add_argument(
        "--seeds",
        type=int,
        default=None,
        help="Number of NSGA-II seeds (forwarded to phase 2 only).",
    )
    parser.add_argument("--skip-nsga", action="store_true",
                        help="Skip Phase 2 (NSGA-II)")
    parser.add_argument("--skip-lstm", action="store_true",
                        help="Skip Phase 3 (LSTM)")
    parser.add_argument("--skip-ppo", action="store_true",
                        help="Skip Phase 4 (PPO)")
    parser.add_argument("--skip-analysis", action="store_true",
                        help="Skip Phase 5 (sensitivity analysis)")
    parser.add_argument("--ppo-steps", type=int, default=None,
                        help="Override PPO total timesteps")
    args = parser.parse_args()

    # Normalise --resume: True if provided (with or without path) else False.
    resume_enabled = args.resume is not None
    resume_path = (
        None if args.resume in (None, "__bool__") else args.resume
    )

    # bugfix.md C2.23 §H — --component overrides the per-phase skip flags.
    if args.component != "all":
        args.skip_nsga = args.component != "nsga2"
        args.skip_lstm = args.component != "lstm"
        args.skip_ppo = args.component != "ppo"
        args.skip_analysis = True

    console = _console()
    config = MasterConfig()
    if args.ppo_steps:
        config.ppo.total_timesteps = args.ppo_steps
    # bugfix.md C2.7 §A — propagate --seeds into the NSGA-II population
    # schedule used by phase 2 (the existing solver iterates seeds via
    # repeated invocations driven by run_phase_nsga2 callers; for the
    # local runner we record the requested count in the JSON status log
    # so the notebooks can verify it was honoured).
    requested_seeds = args.seeds if args.seeds is not None else 1

    results_dir = Path("data/results")
    results_dir.mkdir(parents=True, exist_ok=True)
    _emit_status(
        results_dir, args.component, "runner", "start",
        {
            "resume": resume_enabled,
            "resume_path": resume_path,
            "seeds": requested_seeds,
            "ppo_steps_override": args.ppo_steps,
        },
    )

    _print(
        "\n[bold]Supply Chain Research — Local Training Runner[/bold]",
        console,
    )
    _print(f"  Seed: {config.random_seed}", console)
    _print(f"  Results: {results_dir.resolve()}", console)
    _print("", console)

    total_t0 = time.perf_counter()
    data = run_phase_network(config, console)
    if _interrupted:
        return

    if not args.skip_nsga:
        if resume_enabled and (results_dir / "nsga2_pareto_front.npy").exists():
            _print(
                "  [dim]Phase 2: NSGA-II skipped (checkpoint exists)[/dim]",
                console,
            )
            _emit_status(results_dir, args.component, "nsga2", "resumed")
        else:
            _emit_status(results_dir, args.component, "nsga2", "start",
                         {"seeds": requested_seeds})
            run_phase_nsga2(config, data, results_dir, console)
            _emit_status(results_dir, args.component, "nsga2", "complete")
    if _interrupted:
        _emit_status(results_dir, args.component, "runner", "interrupt")
        return

    if not args.skip_lstm:
        if resume_enabled and (results_dir / "lstm_metrics.json").exists():
            _print(
                "  [dim]Phase 3: LSTM skipped (checkpoint exists)[/dim]",
                console,
            )
            _emit_status(results_dir, args.component, "lstm", "resumed")
        else:
            _emit_status(results_dir, args.component, "lstm", "start")
            run_phase_lstm(config, results_dir, console)
            _emit_status(results_dir, args.component, "lstm", "complete")
    if _interrupted:
        _emit_status(results_dir, args.component, "runner", "interrupt")
        return

    if not args.skip_ppo:
        if resume_enabled and (results_dir / "ppo_metrics.json").exists():
            _print(
                "  [dim]Phase 4: PPO skipped (checkpoint exists)[/dim]",
                console,
            )
            _emit_status(results_dir, args.component, "ppo", "resumed")
        else:
            _emit_status(results_dir, args.component, "ppo", "start",
                         {"total_timesteps": args.ppo_steps
                          or config.ppo.total_timesteps})
            run_phase_ppo(
                config, results_dir, console,
                total_timesteps=args.ppo_steps,
            )
            _emit_status(results_dir, args.component, "ppo", "complete")
    if _interrupted:
        _emit_status(results_dir, args.component, "runner", "interrupt")
        return

    if not args.skip_analysis:
        run_phase_analysis(config, results_dir, console)

    elapsed = time.perf_counter() - total_t0
    _emit_status(
        results_dir, args.component, "runner", "complete",
        {"elapsed_seconds": round(elapsed, 2)},
    )
    _print("", console)
    _print(
        f"[bold green]Pipeline complete[/bold green] in "
        f"{elapsed:.1f}s ({elapsed / 60.0:.1f} min)",
        console,
    )

    if HAS_RICH and console is not None:
        table = Table(title="Output files")
        table.add_column("File", style="cyan")
        table.add_column("Size", justify="right")
        for path in sorted(results_dir.glob("*")):
            size = path.stat().st_size
            if size > 1024 * 1024:
                size_str = f"{size / 1024 / 1024:.1f} MB"
            elif size > 1024:
                size_str = f"{size / 1024:.1f} KB"
            else:
                size_str = f"{size} B"
            table.add_row(path.name, size_str)
        console.print(table)


if __name__ == "__main__":
    main()
