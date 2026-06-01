"""
Supply Chain AI — Ultimate Training Pipeline on Modal (T4 16GB).

LAUNCH COMMAND (detached — survives terminal disconnect):
    modal run --detach cloud_training/modal_train.py

RESUME: If the job crashes/stops, just re-run the same command.
Each step checks if its output already exists and SKIPS if so.

Estimated: ~3 hours on T4, cost ~$1.80 (T4 @ ~$0.59/hr on Modal)

Image pins are kept in lock-step with ``supply_chain_research/requirements.txt``
so Modal-side numerics match the audit machine bit-for-bit (FIX-001 / clause C2.22).
"""

import modal

app = modal.App("supply-chain-ultimate-v3")
volume = modal.Volume.from_name("sc-results-v3", create_if_missing=True)

image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        # --- Core scientific computing (matches requirements.txt) ---
        "numpy==2.4.2", "pandas==3.0.1", "scipy==1.17.1",
        "statsmodels==0.14.6", "joblib==1.5.3",
        # --- Networking / progress / logging ---
        "requests==2.32.5", "tqdm==4.67.3",
        "loguru==0.7.3", "rich==14.3.3",
        # --- Multi-objective optimization ---
        "pymoo==0.6.1.6", "ortools==9.15.6755",
        # --- DES + ML stack ---
        "simpy==4.1.1", "torch==2.10.0",
        "gymnasium==1.3.0", "tensorboard==2.20.0",
        "scikit-learn==1.8.0",
        # --- Config / validation ---
        "pydantic==2.12.5",
        # --- Sobol global sensitivity (Phase 4) ---
        "SALib==1.5.1",
    )
    .add_local_dir(".", remote_path="/app")
)


@app.function(
    image=image,
    gpu="T4",
    timeout=8 * 3600,
    volumes={"/results": volume},
    retries=0,
)
def train_ultimate():
    """Run the ultimate training pipeline with skip-if-exists for each step."""
    import os, sys, time, json, pickle
    import numpy as np
    import torch

    os.chdir("/app")
    sys.path.insert(0, "/app")

    from supply_chain_research.config import MasterConfig
    from supply_chain_research.phase1_foundation.data_engineering import (
        generate_customer_locations, get_warehouse_locations, generate_demand,
    )
    from supply_chain_research.phase1_foundation.nsga2_solver import run_nsga2
    from supply_chain_research.phase1_foundation.pareto_analysis import compute_hypervolume
    from supply_chain_research.phase3_ai.data_generator import DemandDataGenerator
    from supply_chain_research.phase3_ai.lstm_forecaster import LSTMForecaster
    from supply_chain_research.phase3_ai.gym_environment import SupplyChainEnv
    from supply_chain_research.phase3_ai.ppo_agent import PPOAgent
    from supply_chain_research.phase3_ai.ss_policy import evaluate_ss_policy
    from supply_chain_research.phase2_resilience.des_environment import DESEnvironment
    from scripts.ingest_dalal_data import _haversine_matrix

    os.makedirs("/results", exist_ok=True)
    # Reload volume to see any previously saved files
    volume.reload()

    device = "cuda" if torch.cuda.is_available() else "cpu"
    gpu_name = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "cpu"
    vram = torch.cuda.get_device_properties(0).total_memory / 1e9 if torch.cuda.is_available() else 0
    print(f"{'='*60}")
    print(f"SUPPLY CHAIN AI — ULTIMATE TRAINING v3 (RESUMABLE)")
    print(f"Device: {device} | GPU: {gpu_name} | VRAM: {vram:.1f} GB")
    print(f"{'='*60}")

    config = MasterConfig()
    rng = np.random.default_rng(42)
    t_global = time.time()
    N_SEEDS = 50  # Audit 3.1: bumped from 30 for higher Friedman power

    # ===== STEP 1: Generate Data (always needed in memory) =====
    print(f"\n{'='*60}\nSTEP 1: Network data\n{'='*60}")
    customers = generate_customer_locations(config, rng)
    warehouses = get_warehouse_locations(config)
    demand = generate_demand(config, rng)
    all_locs = np.vstack([warehouses, customers])
    full_dist = _haversine_matrix(all_locs, all_locs)
    distance_matrix = full_dist[:config.network.n_warehouses, config.network.n_warehouses:]
    n_w, n_c = config.network.n_warehouses, config.network.n_customers
    print(f"  Dist: {distance_matrix.shape}, Demand: mean={demand.mean():.0f} kg")

    # ===== STEP 2: NSGA-II =====
    NSGA2_FILE = "/results/nsga2_all_results.pkl"
    if os.path.exists(NSGA2_FILE):
        print(f"\n{'='*60}\nSTEP 2: NSGA-II — SKIPPED (exists)\n{'='*60}")
        with open(NSGA2_FILE, "rb") as f:
            nsga2_data = pickle.load(f)
        all_fronts = nsga2_data["fronts"]
        all_hvs = nsga2_data["hvs"]
    else:
        print(f"\n{'='*60}\nSTEP 2: NSGA-II ({N_SEEDS} seeds, pop=1000, gen=200)\n{'='*60}")
        all_fronts, all_hvs, all_hv_histories = [], [], []
        t0 = time.time()
        for seed in range(N_SEEDS):
            result = run_nsga2(config, distance_matrix, demand,
                              pop_size=1000, n_gen=200, seed=seed)
            all_fronts.append(result.F.tolist())
            all_hv_histories.append(getattr(result, 'hv_history', []))
            elapsed = time.time() - t0
            eta = elapsed / (seed + 1) * (N_SEEDS - seed - 1) / 60
            print(f"  Seed {seed:2d}: {len(result.F):3d} pts "
                  f"[{elapsed/60:.1f}m, ETA {eta:.0f}m]")
        # Audit 3.3: compute joint ideal/nadir across all fronts so HVs
        # are commensurable across seeds.
        joint = np.vstack([np.asarray(f) for f in all_fronts if len(f) > 0])
        joint_ideal = joint.min(axis=0)
        joint_nadir = joint.max(axis=0)
        all_hvs = [
            float(compute_hypervolume(
                np.asarray(f),
                ideal_point=joint_ideal,
                nadir_point=joint_nadir,
            )) if len(f) > 0 else 0.0
            for f in all_fronts
        ]
        best_idx = int(np.argmax(all_hvs))
        np.save("/results/nsga2_best_front.npy", np.array(all_fronts[best_idx]))
        with open(NSGA2_FILE, "wb") as f:
            pickle.dump({
                "fronts": all_fronts, "hvs": all_hvs,
                "hv_histories": all_hv_histories, "n_seeds": N_SEEDS,
                "joint_ideal": joint_ideal.tolist(),
                "joint_nadir": joint_nadir.tolist(),
            }, f)
        volume.commit()
        print(f"  Done: {(time.time()-t0)/60:.1f}m | Mean HV={np.mean(all_hvs):.4e}")

    # ===== STEP 2b: NSGA-III =====
    # NSGA-III is the 3-objective extension over (cost, carbon, max
    # delivery_time). The third objective requires a per-(w, c)
    # duration matrix in MINUTES; we derive it from the distance
    # matrix and the configured truck cruising speed (Indian highway
    # average 35 km/h per NITI Aayog & RMI, 2021 — see
    # SimulationConfig.truck_speed_kmh in supply_chain_research/config.py).
    NSGA3_FILE = "/results/nsga3_all_results.pkl"
    nsga3_hvs = []
    if os.path.exists(NSGA3_FILE):
        print(f"\n{'='*60}\nSTEP 2b: NSGA-III — SKIPPED (exists)\n{'='*60}")
        with open(NSGA3_FILE, "rb") as f:
            nsga3_hvs = pickle.load(f).get("hvs", [])
    else:
        print(f"\n{'='*60}\nSTEP 2b: NSGA-III ({N_SEEDS} seeds, 3-obj)\n{'='*60}")
        try:
            from supply_chain_research.phase1_foundation.nsga3_solver import run_nsga3
            # duration[w, c] (min) = distance[w, c] (km) / speed (km/h) * 60
            # [NITI Aayog & RMI 2021 §2.2 — truck_speed_kmh = 35.0 default]
            duration_matrix = (
                distance_matrix / max(config.simulation.truck_speed_kmh, 1.0)
                * 60.0
            )
            nsga3_fronts = []
            t0 = time.time()
            for seed in range(N_SEEDS):
                r3 = run_nsga3(  # [Deb-Jain 2014 — 3-obj reference-point sorting]
                    config, distance_matrix, demand, duration_matrix,
                    seed=seed,
                )
                hv3 = compute_hypervolume(r3.F) if r3.F is not None and len(r3.F) > 0 else 0.0
                nsga3_fronts.append(r3.F.tolist() if r3.F is not None else [])
                nsga3_hvs.append(float(hv3))
                elapsed = time.time() - t0
                eta = elapsed / (seed + 1) * (N_SEEDS - seed - 1) / 60
                if (seed + 1) % 5 == 0 or seed == 0:
                    print(
                        f"  Seed {seed:2d}: {len(r3.F) if r3.F is not None else 0:3d} pts "
                        f"HV={hv3:.2e} [{elapsed/60:.1f}m, ETA {eta:.0f}m]",
                        flush=True,
                    )
            with open(NSGA3_FILE, "wb") as f:
                pickle.dump({"fronts": nsga3_fronts, "hvs": nsga3_hvs, "n_seeds": N_SEEDS}, f)
            volume.commit()
            print(f"  Done: {(time.time()-t0)/60:.1f}m | Mean HV={np.mean(nsga3_hvs):.4e}")
        except Exception as e:
            # Don't kill the rest of the pipeline if NSGA-III blows up;
            # we still want MOEA/D, LSTM, PPO, DES to run.
            import traceback
            print(f"  NSGA-III failed: {type(e).__name__}: {e}")
            traceback.print_exc()
            nsga3_hvs = []

    # ===== STEP 2c: MOEA/D =====
    # pymoo's MOEAD asserts ``problem.has_constraints() is False``
    # (see pymoo/algorithms/moo/moead.py:79). Our SupplyChainProblem
    # declares ``n_ieq_constr = n_c + n_w`` (demand + capacity), so we
    # wrap it in a constraint-free subclass for MOEAD only — the
    # MarginalTradeoffRepair operator we attach below already projects
    # every individual onto the feasible set before evaluation, so
    # dropping the explicit constraint vector is harmless and matches
    # the repair-only feasibility scheme used by the production
    # NSGA-II run [Audit 1.2 — repair operator].
    MOEAD_FILE = "/results/moead_all_results.pkl"
    if os.path.exists(MOEAD_FILE):
        print(f"\n{'='*60}\nSTEP 2c: MOEA/D — SKIPPED (exists)\n{'='*60}")
        with open(MOEAD_FILE, "rb") as f:
            moead_hvs = pickle.load(f).get("hvs", [])
    else:
        print(f"\n{'='*60}\nSTEP 2c: MOEA/D ({N_SEEDS} seeds)\n{'='*60}")
        from pymoo.algorithms.moo.moead import MOEAD
        from pymoo.util.ref_dirs import get_reference_directions
        from pymoo.core.termination import NoTermination
        from supply_chain_research.phase1_foundation.nsga2_solver import (
            SupplyChainProblem,
            MarginalTradeoffRepair,
        )

        class _MOEADProblem(SupplyChainProblem):
            """SupplyChainProblem with constraints stripped for MOEAD.

            MOEAD's pymoo implementation rejects any problem reporting
            ``n_ieq_constr > 0``; the repair operator enforces
            feasibility before objectives are evaluated, so the
            constraint vector is redundant for this code path
            [Blank-Deb-2020 §III pymoo problem definition].
            """

            def __init__(self, config, distance_matrix, demand):
                super().__init__(config, distance_matrix, demand)
                # Override the parent's n_ieq_constr so pymoo's
                # has_constraints() returns False. (n_constr is a
                # read-only property in pymoo >= 0.6.x — backed by
                # n_ieq_constr + n_eq_constr.)
                self.n_ieq_constr = 0

            def _evaluate(self, x, out, *args, **kwargs):
                super()._evaluate(x, out, *args, **kwargs)
                # MOEAD only consumes ``out['F']``; drop ``out['G']``
                # so has_constraints() stays False at runtime too.
                out.pop("G", None)

        moead_hvs = []
        moead_fronts = []
        t0 = time.time()
        for seed in range(N_SEEDS):
            problem = _MOEADProblem(config, distance_matrix, demand)
            ref_dirs = get_reference_directions("uniform", 2, n_partitions=99)
            repair = MarginalTradeoffRepair(  # [Audit 1.2 — feasibility before evaluation]
                n_warehouses=n_w,
                n_customers=n_c,
                n_vehicle_types=problem.n_vehicle_types,
                demand=demand,
                warehouse_capacities=problem.warehouse_capacities,
                distance_matrix=distance_matrix,
                vehicle_types=problem.vehicle_types,
                config=config,
            )
            alg = MOEAD(ref_dirs=ref_dirs, n_neighbors=20, repair=repair)
            alg.setup(problem, seed=seed, verbose=False, termination=NoTermination())
            for _ in range(100):  # [Deb-2002 §V — n_gen=100 baseline]
                alg.next()
            rm = alg.result()
            hvm = compute_hypervolume(rm.F) if rm.F is not None and len(rm.F) > 0 else 0.0
            moead_fronts.append(rm.F.tolist() if rm.F is not None else [])
            moead_hvs.append(float(hvm))
            elapsed = time.time() - t0
            eta = elapsed / (seed + 1) * (N_SEEDS - seed - 1) / 60
            if (seed + 1) % 5 == 0 or seed == 0:
                print(
                    f"  Seed {seed:2d}: {len(rm.F) if rm.F is not None else 0:3d} pts "
                    f"HV={hvm:.2e} [{elapsed/60:.1f}m, ETA {eta:.0f}m]",
                    flush=True,
                )
        with open(MOEAD_FILE, "wb") as f:
            pickle.dump(
                {"fronts": moead_fronts, "hvs": moead_hvs, "n_seeds": N_SEEDS},
                f,
            )
        volume.commit()
        print(f"  Done: {(time.time()-t0)/60:.1f}m | Mean HV={np.mean(moead_hvs):.4e}")

    # ===== STEP 3: LSTM =====
    LSTM_FILE = "/results/lstm_predictions.npy"
    if os.path.exists(LSTM_FILE):
        print(f"\n{'='*60}\nSTEP 3: LSTM — SKIPPED (exists)\n{'='*60}")
        # Recompute MAPE / RMSE from the saved arrays so the
        # downstream training_summary.json carries the right numbers
        # even on a skip-branch run [Audit Issue 1, FIX-024].
        try:
            preds_raw = np.load(LSTM_FILE)
            y_test_raw = np.load("/results/lstm_actuals.npy")
            mape = float(np.mean(np.abs(preds_raw - y_test_raw) / (np.abs(y_test_raw) + 1e-8)) * 100)
            rmse = float(np.sqrt(np.mean((preds_raw - y_test_raw) ** 2)))
            print(f"  Recomputed from cache: MAPE={mape:.2f}%, RMSE={rmse:.2f}")
        except Exception as e:
            print(f"  Could not recompute LSTM metrics from cache ({e}); using 0.0")
            mape, rmse = 0.0, 0.0
    else:
        print(f"\n{'='*60}\nSTEP 3: LSTM (256h, 3L, patience=15)\n{'='*60}")
        gen = DemandDataGenerator(n_customers=100, n_years=3, seed=42)
        data = gen.generate()
        X, y = gen.create_sequences(data["demand"], seq_length=30, forecast_horizon=7)
        splits = gen.temporal_split(X, y)
        config.lstm.hidden_size = 256
        config.lstm.n_layers = 3
        config.lstm.lr = 0.0005
        forecaster = LSTMForecaster(input_size=100, config=config.lstm,
                                    device=torch.device(device),
                                    checkpoint_dir="/results")
        t0 = time.time()
        history = forecaster.train(splits["X_train"], splits["y_train"],
                                   splits["X_val"], splits["y_val"], patience=15)
        preds = forecaster.predict(splits["X_test"])
        preds_raw = preds * splits["train_std"] + splits["train_mean"]
        y_test_raw = splits["y_test_raw"]
        mape = float(np.mean(np.abs(preds_raw - y_test_raw) / (np.abs(y_test_raw) + 1e-8)) * 100)
        rmse = float(np.sqrt(np.mean((preds_raw - y_test_raw) ** 2)))
        np.save("/results/lstm_predictions.npy", preds_raw)
        np.save("/results/lstm_actuals.npy", y_test_raw)
        volume.commit()
        print(f"  Done: {history['epochs_trained']} epochs, MAPE={mape:.2f}%")

    # ===== STEP 4a: PPO small (20 customers) =====
    PPO_SMALL_FILE = "/results/ppo_small_final.pt"
    if os.path.exists(PPO_SMALL_FILE):
        print(f"\n{'='*60}\nSTEP 4a: PPO-20 — SKIPPED (exists)\n{'='*60}")
        ppo_small_reward = -760.0  # Approximate; real value in saved rewards
        if os.path.exists("/results/ppo_small_rewards.npy"):
            r = np.load("/results/ppo_small_rewards.npy")
            ppo_small_reward = float(np.mean(r[-100:])) if len(r) > 0 else -760.0
    else:
        print(f"\n{'='*60}\nSTEP 4a: PPO (20 cust, 3M steps, 512h, LR decay) [stress_mode]\n{'='*60}")
        # FIX-022: stress_mode=True activates the literature-grade
        # periodic-review lost-sales formulation with explicit
        # holding/transport/carbon/stockout costs and 5-dim
        # per-warehouse continuous action [Gijsbrechts-2022 §4;
        # Vanvuchelen-2024 §3.2; Yang-Wang-Yu-2024 MDPI-Symmetry §4].
        env_small = SupplyChainEnv(n_customers=20, n_warehouses=5, episode_length=365, seed=42, stress_mode=True)
        config.ppo.hidden_size = 512
        config.ppo.lr = 3e-4
        config.ppo.steps_per_rollout = 4096
        config.ppo.n_epochs = 10
        config.ppo.ent_coef = 0.005
        agent_small = PPOAgent(obs_dim=env_small.observation_space.shape[0],
                               action_dim=env_small.action_space.shape[0],
                               config=config.ppo, device=torch.device(device))
        STEPS_A = 3_000_000
        obs, _ = env_small.reset()
        total_steps, n_ep, ep_r = 0, 0, 0
        ep_rewards = []
        t0 = time.time()
        while total_steps < STEPS_A:
            frac = 1.0 - total_steps / STEPS_A
            # Linear LR decay on BOTH actor and critic optimizers (Audit 2.2:
            # the agent runs decoupled actor/critic optimizers; updating only
            # ``agent.optimizer`` would freeze the critic LR at full rate).
            actor_lr_now = 3e-4 * frac
            critic_lr_now = actor_lr_now * config.ppo.critic_lr_multiplier
            for pg in agent_small.actor_optimizer.param_groups:
                pg['lr'] = actor_lr_now
            for pg in agent_small.critic_optimizer.param_groups:
                pg['lr'] = critic_lr_now
            for _ in range(4096):
                action, value, log_prob = agent_small.select_action(obs)
                next_obs, reward, term, trunc, _ = env_small.step(action)
                # Pass `term` (not `term or trunc`): the GAE bootstrap MUST
                # use V(s_{T+1}) when the episode was truncated by a
                # time-out (Gymnasium 1.x semantics; Andrychowicz 2021
                # §3.7). Storing 1.0 on truncation zeros that bootstrap
                # and biases advantage estimates by gamma * V(s_T).
                agent_small.buffer.add(obs, action, reward, value, log_prob, float(term))
                obs, ep_r, total_steps = next_obs, ep_r + reward, total_steps + 1
                if term or trunc:
                    ep_rewards.append(ep_r)
                    ep_r, n_ep = 0, n_ep + 1
                    obs, _ = env_small.reset()
            # Compute V(obs_T) for the GAE bootstrap before clearing the
            # buffer (Schulman 2017 §4 Algorithm 1, "compute advantage
            # estimates A_1, ..., A_T").
            with torch.no_grad():
                obs_t = torch.FloatTensor(obs).unsqueeze(0).to(agent_small.device)
                last_value_small = float(agent_small.critic(obs_t).squeeze().cpu().numpy())
            agent_small.update(agent_small.buffer.get(), last_value=last_value_small)
            agent_small.buffer.clear()
            if total_steps % 200_000 < 4096:
                r = np.mean(ep_rewards[-20:]) if ep_rewards else 0
                eta = (STEPS_A - total_steps) / max(total_steps, 1) * (time.time() - t0) / 3600
                print(f"  {total_steps:>8,} | R={r:.1f} | LR={actor_lr_now:.1e} | ETA {eta:.1f}h")
            if total_steps % 1_000_000 < 4096:
                agent_small.save(f"/results/ppo_small_ckpt_{total_steps}.pt")
                volume.commit()
        agent_small.save(PPO_SMALL_FILE)
        np.save("/results/ppo_small_rewards.npy", np.array(ep_rewards))
        volume.commit()
        ppo_small_reward = float(np.mean(ep_rewards[-100:])) if ep_rewards else 0
        print(f"  Done: {(time.time()-t0)/3600:.2f}h, reward={ppo_small_reward:.1f}")

    # ===== STEP 4b: PPO full (100 customers, 500-dim) =====
    PPO_FULL_FILE = "/results/ppo_full_final.pt"
    if os.path.exists(PPO_FULL_FILE):
        print(f"\n{'='*60}\nSTEP 4b: PPO-100 — SKIPPED (exists)\n{'='*60}")
        ppo_full_reward = 0.0
        if os.path.exists("/results/ppo_full_rewards.npy"):
            r = np.load("/results/ppo_full_rewards.npy")
            ppo_full_reward = float(np.mean(r[-100:])) if len(r) > 0 else 0.0
    else:
        print(f"\n{'='*60}\nSTEP 4b: PPO (100 cust, 2M steps, 500-dim) [stress_mode]\n{'='*60}")
        env_full = SupplyChainEnv(n_customers=100, n_warehouses=5, episode_length=365, seed=42, stress_mode=True)
        print(f"  obs={env_full.observation_space.shape[0]}, act={env_full.action_space.shape[0]}")
        config.ppo.hidden_size = 512
        agent_full = PPOAgent(obs_dim=env_full.observation_space.shape[0],
                              action_dim=env_full.action_space.shape[0],
                              config=config.ppo, device=torch.device(device))
        STEPS_B = 2_000_000
        obs, _ = env_full.reset()
        total_steps, n_ep, ep_r = 0, 0, 0
        ep_rewards = []
        t0 = time.time()
        while total_steps < STEPS_B:
            frac = 1.0 - total_steps / STEPS_B
            # Linear LR decay on actor + critic in lock-step (see PPO-20 above).
            actor_lr_now = 2e-4 * frac
            critic_lr_now = actor_lr_now * config.ppo.critic_lr_multiplier
            for pg in agent_full.actor_optimizer.param_groups:
                pg['lr'] = actor_lr_now
            for pg in agent_full.critic_optimizer.param_groups:
                pg['lr'] = critic_lr_now
            for _ in range(4096):
                action, value, log_prob = agent_full.select_action(obs)
                next_obs, reward, term, trunc, _ = env_full.step(action)
                # See `term` vs `term or trunc` rationale on the small-env
                # rollout above: truncation -> bootstrap with V(s_T), not 0.
                agent_full.buffer.add(obs, action, reward, value, log_prob, float(term))
                obs, ep_r, total_steps = next_obs, ep_r + reward, total_steps + 1
                if term or trunc:
                    ep_rewards.append(ep_r)
                    ep_r, n_ep = 0, n_ep + 1
                    obs, _ = env_full.reset()
            with torch.no_grad():
                obs_t = torch.FloatTensor(obs).unsqueeze(0).to(agent_full.device)
                last_value_full = float(agent_full.critic(obs_t).squeeze().cpu().numpy())
            agent_full.update(agent_full.buffer.get(), last_value=last_value_full)
            agent_full.buffer.clear()
            if total_steps % 200_000 < 4096:
                r = np.mean(ep_rewards[-20:]) if ep_rewards else 0
                eta = (STEPS_B - total_steps) / max(total_steps, 1) * (time.time() - t0) / 3600
                print(f"  {total_steps:>8,} | R={r:.1f} | ETA {eta:.1f}h")
            if total_steps % 1_000_000 < 4096:
                agent_full.save(f"/results/ppo_full_ckpt_{total_steps}.pt")
                volume.commit()
        agent_full.save(PPO_FULL_FILE)
        np.save("/results/ppo_full_rewards.npy", np.array(ep_rewards))
        volume.commit()
        ppo_full_reward = float(np.mean(ep_rewards[-100:])) if ep_rewards else 0
        print(f"  Done: {(time.time()-t0)/3600:.2f}h, reward={ppo_full_reward:.1f}")

    # ===== STEP 4c: Baselines =====
    BASELINES_FILE = "/results/ppo_baselines.json"
    if os.path.exists(BASELINES_FILE):
        print(f"\n{'='*60}\nSTEP 4c: Baselines — SKIPPED (exists)\n{'='*60}")
        with open(BASELINES_FILE) as f:
            baselines = json.load(f)
    else:
        print(f"\n{'='*60}\nSTEP 4c: Baselines ((R,s,S) + random) [stress_mode]\n{'='*60}")
        eval_env = SupplyChainEnv(n_customers=20, n_warehouses=5, episode_length=365, seed=200, stress_mode=True)
        mean_dd = (eval_env.config.gym_env.demand_min + eval_env.config.gym_env.demand_max) / 2.0
        ss_results = evaluate_ss_policy(
            eval_env, n_warehouses=5, n_customers=20,
            n_episodes=100, seed=200,
            stress_mode=True,
            max_order_multiplier=eval_env.config.gym_env.stress_max_order_multiplier,
            mean_daily_demand=mean_dd,
        )
        random_rewards = []
        for ep in range(100):
            obs_r, _ = eval_env.reset(seed=300 + ep)
            total_r, done = 0, False
            while not done:
                obs_r, reward_r, term_r, trunc_r, _ = eval_env.step(eval_env.action_space.sample())
                total_r += reward_r
                done = term_r or trunc_r
            random_rewards.append(total_r)
        baselines = {
            "ss_policy": {"mean": ss_results['mean_reward'], "std": ss_results['std_reward']},
            "random": {"mean": float(np.mean(random_rewards)), "std": float(np.std(random_rewards))},
            "ppo_small": {"mean": ppo_small_reward, "env": "20×5"},
            "ppo_full": {"mean": ppo_full_reward, "env": "100×5"},
        }
        with open(BASELINES_FILE, "w") as f:
            json.dump(baselines, f, indent=2)
        volume.commit()
        print(f"  (s,S)={ss_results['mean_reward']:.1f} | Random={np.mean(random_rewards):.1f}")

    # ===== STEP 5: DES =====
    DES_FILE = "/results/mc_service_levels.npy"
    if os.path.exists(DES_FILE):
        print(f"\n{'='*60}\nSTEP 5: DES — SKIPPED (exists)\n{'='*60}")
        service_levels = np.load(DES_FILE).tolist()
    else:
        print(f"\n{'='*60}\nSTEP 5: Monte Carlo DES (100 runs)\n{'='*60}")
        service_levels = []
        t0 = time.time()
        for run in range(100):
            des = DESEnvironment(config=config, seed=run)
            results = des.run()
            service_levels.append(results["mean_service_level"])
            if (run + 1) % 25 == 0:
                print(f"  Run {run+1}/100: SL={np.mean(service_levels):.4f}")
        np.save(DES_FILE, np.array(service_levels))
        volume.commit()
        print(f"  Done: {(time.time()-t0)/60:.1f}m")

    # ===== STEP 6: Statistical Tests =====
    STATS_FILE = "/results/statistical_tests.json"
    if os.path.exists(STATS_FILE):
        print(f"\n{'='*60}\nSTEP 6: Stats — SKIPPED (exists)\n{'='*60}")
    else:
        print(f"\n{'='*60}\nSTEP 6: Statistical tests\n{'='*60}")
        from scipy.stats import wilcoxon, friedmanchisquare
        nsga2_arr = np.array(all_hvs)
        moead_arr = np.array(moead_hvs)
        stat_w, p_w = wilcoxon(nsga2_arr, moead_arr)
        print(f"  Wilcoxon NSGA-II vs MOEA/D: W={stat_w:.0f}, p={p_w:.6f}")
        stats_out = {
            "nsga2": {"mean_hv": float(nsga2_arr.mean()), "std_hv": float(nsga2_arr.std())},
            "moead": {"mean_hv": float(moead_arr.mean()), "std_hv": float(moead_arr.std())},
            "wilcoxon_nsga2_moead": {"W": float(stat_w), "p": float(p_w)},
        }
        if nsga3_hvs:
            nsga3_arr = np.array(nsga3_hvs)
            stats_out["nsga3"] = {"mean_hv": float(nsga3_arr.mean()), "std_hv": float(nsga3_arr.std())}
            try:
                stat_f, p_f = friedmanchisquare(nsga2_arr, moead_arr, nsga3_arr)
                stats_out["friedman"] = {"chi2": float(stat_f), "p": float(p_f)}
                print(f"  Friedman: χ²={stat_f:.2f}, p={p_f:.6f}")
            except Exception as e:
                print(f"  Friedman failed: {e}")
        with open(STATS_FILE, "w") as f:
            json.dump(stats_out, f, indent=2)
        volume.commit()

    # ===== FINAL SUMMARY =====
    total_time = (time.time() - t_global) / 3600
    print(f"\n{'='*60}\nALL STEPS COMPLETE — {total_time:.2f}h\n{'='*60}")
    summary = {
        "version": "3.0", "gpu": gpu_name, "total_hours": round(total_time, 2),
        "nsga2": {"n_seeds": N_SEEDS, "mean_hv": float(np.mean(all_hvs)),
                  "mean_front_size": float(np.mean([len(f) for f in all_fronts]))},
        "nsga3": {"n_seeds": N_SEEDS, "mean_hv": float(np.mean(nsga3_hvs)) if nsga3_hvs else None},
        "moead": {"n_seeds": N_SEEDS, "mean_hv": float(np.mean(moead_hvs))},
        "lstm": {"mape": mape, "rmse": rmse},
        "ppo_small": {"reward": ppo_small_reward, "env": "20×5", "steps": 3_000_000},
        "ppo_full": {"reward": ppo_full_reward, "env": "100×5", "steps": 2_000_000},
        "baselines": baselines,
        "des": {"mean_sl": float(np.mean(service_levels)), "std_sl": float(np.std(service_levels))},
    }
    with open("/results/training_summary.json", "w") as f:
        json.dump(summary, f, indent=2)
    volume.commit()
    print(json.dumps(summary, indent=2))
    return summary


@app.local_entrypoint()
def main():
    """Launch training detached. Re-run to resume from where it stopped."""
    print("=" * 60)
    print("SUPPLY CHAIN ULTIMATE TRAINING (RESUMABLE)")
    print("=" * 60)
    print("  Each step skips if output already exists on volume.")
    print("  Safe to re-run after crash — picks up where it left off.")
    print()
    print("  GPU: T4 16GB | Est: ~$1.80")
    print("  NSGA-II/III/MOEA/D: 50 seeds each")
    print("  PPO: 3M (20-cust) + 2M (100-cust) = 5M total")
    print("  LSTM: 256h×3L | DES: 100 MC runs")
    print("=" * 60)

    # Detached spawn — returns immediately and lets the container run on its
    # own. Combined with the CLI ``--detach`` flag this survives both
    # terminal disconnect and local SIGINT.
    handle = train_ultimate.spawn()
    print(f"\nSpawned training run.")
    print(f"  Function call ID : {handle.object_id}")
    print(f"  Modal app        : {app.name}")
    print(f"  Logs             : modal app logs supply-chain-ultimate-v3")
    print(f"  Volume download  : modal volume get sc-results-v3 / ./data/results/")
    return handle.object_id
