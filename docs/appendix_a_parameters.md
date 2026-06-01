# Appendix A — Complete Parameter Tables

Auto-generated from `supply_chain_research/config.py` via `scripts/generate_appendix_a.py`. Every scalar field of `MasterConfig` is enumerated below with its current default value, the units inferred from the pydantic field description (when present), and the inline citation captured from the source file. The taxonomy tags PHYSICS DERIVED / PROBLEM SCALED / TUNED that appear in the source column follow the convention declared in the `MasterConfig` docstring (Audit 2.1).

Regenerate after a config change with `python scripts/generate_appendix_a.py`.

Total parameters listed: **212**.

| Parameter | Value | Units | Source |
|-----------|-------|-------|--------|
| `network.n_customers` | `100` |  |  |
| `network.n_warehouses` | `5` |  |  |
| `network.n_cities` | `20` |  |  |
| `network.india_lat_bounds` | `(8.0, 37.0)` |  | India geographic bounds for coordinate validation |
| `network.india_lon_bounds` | `(68.0, 97.0)` |  |  |
| `network.osrm_base_url` | `"http://router.project-osrm.org"` |  | OSRM routing configuration |
| `network.osrm_batch_size` | `100` |  |  |
| `network.osrm_retry_max` | `3` |  |  |
| `network.osrm_retry_backoff` | `2.0` |  |  |
| `network.cache_dir` | `"data/cache"` |  | Caching configuration Distance/duration matrices are cached to disk for reproducibility and offline capability. Cache key is derived from coordinate hash. |
| `network.ors_base_url` | `"https://api.openrouteservice.org/v2/matrix/driving-car"` |  | OpenRouteService fallback ORS Matrix API endpoint (v2); used when OSRM is unavailable. Reference: https://openrouteservice.org/services/ (2024) Free tier: 40 requests/min, 2500/day, max 50×50 matrix per request. |
| `network.ors_api_key` | `""` |  | OpenRouteService API key, read from `ORS_API_KEY` when set |
| `network.hcv_lcv_fleet_ratio` | `0.7` |  | 70% HCV, 30% LCV in Indian freight fleet (VAHAN 2023) |
| `network.customer_location_std` | `0.8` |  | ~89 km per specification |
| `network.demand_clip_min` | `100.0` |  | Demand generation: clip bounds (kg) |
| `network.demand_clip_max` | `10000.0` |  |  |
| `network.cities` | `[('Mumbai', 19.076, 72.8777), ('Delhi', 28.7041, 77.1025), ('Bangalore', 12.9716, 77.5946), ...] (20 items)` |  | 20 major Indian cities: (name, latitude, longitude) |
| `network.warehouse_locations` | `[('Mumbai_WH', 19.033, 72.8656), ('Delhi_WH', 28.65, 77.23), ('Bangalore_WH', 12.9352, 77.6245), ...] (5 items)` |  | 5 warehouse locations: (name, latitude, longitude) |
| `network.warehouse_capacities` | `[60000.0, 55000.0, 50000.0, ...] (5 items)` |  | Per-warehouse capacities in kg; order matches warehouse_locations (Mumbai, Delhi, Bangalore, Kolkata, Nagpur) |
| `vehicle.hcv_k` | `2.61` |  | ITEE pp. 491-504. DOI:10.1007/978-3-540-88351-7_37 k = baseline emission rate at zero load (kg CO2/km) for rigid HGV >16t [MEET-1999 §3, Table 3.2 — Heavy goods vehicles, motorway/urban avg] Verified against COPERT 5 v5.6 (EEA, 2023): 2.... |
| `vehicle.hcv_L` | `0.000147` |  | L = load-dependent emission factor (kg CO2 per kg payload per km) [MEET-1999 §3, Table 3.2 — load-correction factor for rigid HGV expressed per kg-km after the per-tonne-km value is divided by 1000] Cross-verified: COPERT 5 v5.6 (EEA, 20... |
| `vehicle.hcv_capacity` | `10000.0` |  | kg |
| `vehicle.hcv_cost_per_km` | `18.0` |  | INR/km |
| `vehicle.empty_running_fraction` | `0.35` |  | Empty-running fraction — share of HCV trips run empty. [NITI Aayog & RMI (2021), "Fast Tracking Freight in India: A Roadmap for Clean and Cost-effective Goods Transport", §2.2 — global average empty-running 30–35% (India higher, ~40%; we... |
| `vehicle.hcv_utilization` | `0.65` |  | HCV capacity utilization — average load factor. [NITI Aayog & RMI (2021), Fast Tracking Freight, §2.2 — Indian HCV load factor cited at 60–65%; we use 0.65 (upper bound).] |
| `vehicle.diesel_co2_factor` | `2.68` |  | kg CO2 per litre |
| `vehicle.hcv_fuel_price` | `95.0` |  | Fuel prices (INR/litre) Reference: typical Indian retail diesel price 2023–2024 (state-mean). |
| `vehicle.lcv_fuel_price` | `95.0` |  |  |
| `vehicle.lcv_k` | `0.89` |  | Light Commercial Vehicle (LCV) — MEET methodology Primary source: Hickman, A.J. (ed., 1999), MEET TRL Project Report SE/491/98, Table 3.3 — Light commercial vehicles (≤3.5t GVW). Cross-verification: Ntziachristos & Samaras (2009), COPERT... |
| `vehicle.lcv_L` | `7.9e-05` |  | L = load-dependent emission factor (kg CO2 per kg payload per km) [MEET-1999 §3, Table 3.3 — load-correction factor for LCV] |
| `vehicle.lcv_capacity` | `3000.0` |  | kg |
| `vehicle.lcv_cost_per_km` | `28.0` |  | INR/km |
| `nsga.pop_size` | `500` |  | PROBLEM SCALED — see derive_from_problem_size |
| `nsga.n_gen` | `400` |  | TUNED — upper bound; early stop normally triggers earlier |
| `nsga.crossover_eta` | `10.0` |  | TUNED — SBX η_c (Deb-2001 Ch.4) |
| `nsga.crossover_prob` | `0.9` |  | TUNED — Deb-2002 §V |
| `nsga.mutation_eta` | `15.0` |  | TUNED — PM η_m (Deb-2001 Ch.5) |
| `nsga.tournament_size` | `3` |  | TUNED — Deb-2002 §III binary/k-ary tournament |
| `nsga.ref_point_margin` | `1.1` |  | TUNED — 10% margin on nadir (HV ref-point) |
| `nsga.early_stop_window` | `30` |  | TUNED — generations to look back |
| `nsga.early_stop_threshold` | `0.0001` |  | TUNED — relative HV change threshold |
| `nsga.early_stop_min_gen` | `50` |  | TUNED — minimum generations before stop |
| `nsga.demand_constraint_eps` | `0.001` |  | Solver internals (centralized per Audit 1.10) Demand-satisfaction constraint slack (\|sum - D\| - eps <= 0) |
| `nsga.max_demand_default` | `10000.0` |  | Bounds-default upper limit for decision variables when demand vector is empty |
| `nsga.repair_max_passes` | `5` |  | Repair operator: max redistribution passes per individual |
| `nsga.repair_zero_eps` | `1e-09` |  | Repair operator: per-step floor for "non-zero" flow detection |
| `nsga.repair_capacity_eps` | `1e-06` |  | Repair operator: floor when comparing capacity-residual against zero |
| `nsga.inter_customer_distance_high_factor` | `0.8` |  | NSGA-II baseline-solver inter-customer distance approximation (used when no full inter-customer distance matrix is available) |
| `nsga.inter_customer_distance_low_factor` | `0.3` |  |  |
| `nsga3.pop_size` | `92` |  | Nearest multiple of 4 >= 91 reference points |
| `nsga3.n_gen` | `150` |  | n_gen=150: Deb-Jain (2014) §VI Table II report 200–500 for many-objective DTLZ problems; for our 3-obj instance with 92 individuals NFE = 1.4e4 at n_gen=150 which lies in the recommended range. [Deb-Jain-2014 §VI Table II] |
| `nsga3.n_partitions` | `12` |  | C(12+3-1, 3-1) = 91 reference points |
| `nsga3.crossover_eta` | `30.0` |  | SBX distribution index (pymoo NSGA-III default) |
| `nsga3.crossover_prob` | `1.0` |  | Crossover probability (pymoo NSGA-III default) |
| `nsga3.mutation_eta` | `20.0` |  | PM distribution index (pymoo NSGA-III default) |
| `nsga3.convergence_check_period` | `20` |  |  |
| `nsga3.active_shipment_threshold` | `0.01` |  | kg |
| `moead.pop_size` | `500` |  |  |
| `moead.n_gen` | `100` |  |  |
| `moead.n_neighbors` | `20` |  |  |
| `moead.decomposition` | `"tchebicheff"` |  |  |
| `simulation.sim_days` | `365` |  |  |
| `simulation.warmup_days` | `30` |  |  |
| `simulation.lambda_orders` | `3.5` |  |  |
| `simulation.order_size_mu` | `6.44` |  | LogNormal μ for weekly demand (kg), calibrated from DataCo (Constante et al., 2019) |
| `simulation.order_size_sigma` | `0.97` |  | LogNormal σ, calibrated from DataCo (180K orders, 20K customers) |
| `simulation.des_order_size_mu` | `5.5` |  | DES per-order size parameters (separate from static demand allocation) |
| `simulation.des_order_size_sigma` | `0.4` |  |  |
| `simulation.n_monte_carlo` | `50` |  |  |
| `simulation.truck_speed_kmh` | `35.0` |  | Average Indian highway truck speed (NITI Aayog & RMI, 2021) |
| `simulation.truck_speed_noise_pct` | `0.15` |  |  |
| `simulation.replenishment_cycle_days` | `7` |  |  |
| `simulation.demand_shock_multiplier` | `3.0` |  |  |
| `simulation.supply_shock_fraction` | `0.5` |  |  |
| `simulation.service_level_threshold` | `0.95` |  |  |
| `simulation.tts_unfulfilled_threshold` | `0.1` |  |  |
| `simulation.initial_inventory_fraction` | `0.8` |  | fraction of capacity at start |
| `simulation.stress_initial_inventory_fraction` | `0.3` |  | FIX-022 stress-mode initial inventory: starts near the (s,S) reorder threshold so the agent immediately faces a replenishment decision rather than coasting on the legacy 80 % buffer. |
| `simulation.replenishment_rate_multiplier` | `2.4` |  | weekly rate = capacity * this |
| `simulation.fallback_warehouse_capacity` | `50000.0` |  | kg, used when config mismatch |
| `simulation.synthetic_distance_min` | `50.0` |  | DES synthetic distance range (km) for testing |
| `simulation.synthetic_distance_max` | `500.0` |  |  |
| `lstm.seq_length` | `30` |  |  |
| `lstm.forecast_horizon` | `7` |  |  |
| `lstm.hidden_size` | `128` |  |  |
| `lstm.n_layers` | `2` |  |  |
| `lstm.dropout` | `0.2` |  |  |
| `lstm.epochs` | `100` |  |  |
| `lstm.batch_size` | `64` |  |  |
| `lstm.lr` | `0.001` |  |  |
| `lstm.patience` | `10` |  |  |
| `lstm.train_split` | `0.7` |  |  |
| `lstm.val_split` | `0.15` |  |  |
| `lstm.synthetic_years` | `3` |  |  |
| `lstm.model_type` | `"attention_lstm"` |  | Model type selection: "lstm" \| "attention_lstm" \| "tft" Default "attention_lstm" preserves existing behavior. "tft" selects the lightweight Temporal Fusion Transformer baseline (see phase3_ai/tft_forecaster.py). |
| `lstm.tft_hidden_size` | `64` |  | Lightweight TFT hyperparameters (used only when model_type="tft") Reference: Lim et al. (2021), Int. J. Forecasting, 37(4), 1748-1764. |
| `lstm.tft_n_heads` | `4` |  |  |
| `lstm.tft_dropout` | `0.1` |  |  |
| `lstm.weight_decay` | `1e-05` |  | Optimizer / training internals (centralized per Audit 1.10) Adam weight decay |
| `lstm.huber_delta` | `1.0` |  | Huber loss delta |
| `lstm.scheduler_patience` | `5` |  | ReduceLROnPlateau: scheduler patience and factor |
| `lstm.scheduler_factor` | `0.5` |  |  |
| `lstm.grad_clip_max_norm` | `1.0` |  | Gradient clipping max-norm |
| `lstm.pacf_z_95` | `1.96` |  | PACF lookback window selection (Audit 1.6) |
| `lstm.pacf_z_90` | `1.64` |  |  |
| `lstm.pacf_default_window` | `30` |  |  |
| `lstm.pacf_min_window` | `7` |  |  |
| `lstm.pacf_max_lag_default` | `365` |  |  |
| `ppo.total_timesteps` | `1000000` |  | total_timesteps=1e6 — typical on-policy RL training horizon for MuJoCo-scale continuous-control tasks (Schulman 2017 §6.1; reused by Andrychowicz 2021 Fig. 2 across 5 environments). |
| `ppo.steps_per_rollout` | `2048` |  | steps_per_rollout=2048 — Schulman 2017 §6.1 Table 3 (Walker2d/Hopper) and Huang 2022 detail #1 ("vectorised env, 2048 steps per rollout"). |
| `ppo.n_epochs` | `10` |  | n_epochs=10 — Schulman 2017 §6.1 Table 3 ("K=10 epochs of minibatch SGD"); Andrychowicz 2021 §3.4 confirms 10 epochs as the empirical sweet-spot across the 5 environments studied. |
| `ppo.clip_range` | `0.2` |  | clip_range=0.2 — Schulman 2017 §6.1 Table 3 ("ε=0.2 default"); Andrychowicz 2021 §3.5 "the most important hyperparameter"; Huang 2022 detail #5 confirms 0.2 is the community-standard default. |
| `ppo.lr` | `0.0001` |  | lr=1e-4 — Andrychowicz 2021 §3.6 Fig. 6 reports 1e-4–3e-4 as the optimal Adam-step range across environments; we adopt 1e-4 (the conservative end) for an inventory-control task whose reward signal is sparser than MuJoCo locomotion. |
| `ppo.gamma` | `0.99` |  | gamma=0.99 — Schulman 2017 §6.1 Table 3 default; Andrychowicz 2021 §3.7 confirms 0.99 outperforms 0.95/0.999 on 4 of 5 environments. |
| `ppo.gae_lambda` | `0.95` |  | gae_lambda=0.95 — Schulman et al. 2016 (GAE paper) §6.2 Fig. 2 ("λ=0.95–0.99 best"); Schulman 2017 §6.1 Table 3 picks 0.95; Huang 2022 detail #6. |
| `ppo.vf_coef` | `0.5` |  | vf_coef=0.5 — Schulman 2017 §5 (Eq. 9) sets c1=0.5 for the value loss when actor and critic share parameters; preserved here even under the decoupled-optimiser layout for behavioural parity. Cross-check: OpenAI Baselines (Dhariwal et al.... |
| `ppo.ent_coef` | `0.01` |  | ent_coef=0.01 — Schulman 2017 §5 Eq. 9 (c2=0.01 default for Atari); Andrychowicz 2021 §3.10 Fig. 11 reports 0–0.01 as effectively equivalent for continuous control with Gaussian/Beta policies. |
| `ppo.max_grad_norm` | `0.5` |  | max_grad_norm=0.5 — Huang 2022 detail #11 ("clip global gradient norm at 0.5") and Andrychowicz 2021 §3.13 Fig. 14: the value 0.5 is robust and prevents gradient blow-ups across all 5 envs. |
| `ppo.hidden_size` | `256` |  | hidden_size=256 — Andrychowicz 2021 §3.16 Fig. 17: 64–256-unit MLPs are roughly equivalent on continuous-control benchmarks; we adopt 256 to give the policy enough capacity for the higher-dimensional supply-chain observation. |
| `ppo.n_eval_episodes` | `100` |  |  |
| `ppo.checkpoint_freq` | `100000` |  |  |
| `ppo.critic_lr_multiplier` | `3.0` |  | Critic-LR multiplier (Audit 2.2): critic_lr = multiplier * actor lr. Decoupled actor/critic optimisers — Andrychowicz 2021 §3.6 Fig. 7 shows the value loss benefits from a 2-3x larger LR than the policy. We adopt 3.0 (mid-range). |
| `ppo.action_clamp_eps` | `1e-06` |  | Action / log-prob safety clamp (Beta distribution boundary). Chou 2017 §3.2 — Beta(α,β) on (0,1) is open; we clamp samples to (eps, 1-eps) so log_prob stays finite at the boundary. |
| `ppo.ratio_clamp_min` | `0.01` |  | Importance-ratio safety clamp before the PPO-Clip surrogate is evaluated. Schulman 2017 §3 Eq. 7 assumes finite ratios; we add a defensive [0.01, 100] clamp so a transient policy collapse cannot produce NaN gradients (Huang 2022 detail #... |
| `ppo.ratio_clamp_max` | `100.0` |  |  |
| `ppo.minibatch_size_min` | `64` |  | Minibatch sizing — minibatch = max(minibatch_size_min, steps_per_rollout / minibatch_count). Huang 2022 detail #4 ("64 minibatches, 64-sample minibatches" on the default 2048-step rollout); we expose both knobs. |
| `ppo.minibatch_count` | `16` |  |  |
| `ppo.actor_head_init_gain` | `0.01` |  | Orthogonal-init small gain (0.01) for the policy output heads — Schulman 2017 §6.1 ("small final layer init for the policy"), generalised in Huang 2022 detail #2 (orth init, layer-wise gain). |
| `ppo.beta_param_nan_default` | `2.0` |  | NaN/Inf guards on alpha/beta of the Beta head (Audit 1.5). The default of 2.0 yields a peaked-at-0.5 unimodal Beta if the network briefly produces a non-finite logit; the +inf clip at 100 caps over-confident action distributions. |
| `ppo.beta_param_posinf_clip` | `100.0` |  |  |
| `sac.replay_buffer_size` | `1000000` |  | replay_buffer_size=1e6 — Haarnoja 2018a Table 1 ("replay buffer size 1e6") and Haarnoja 2018b Appendix D Table 1 unchanged. |
| `sac.batch_size` | `256` |  | batch_size=256 — Haarnoja 2018a Table 1 ("minibatch size 256") used across all 6 MuJoCo benchmarks. |
| `sac.learning_rate` | `0.0003` |  | learning_rate=3e-4 — Haarnoja 2018a Table 1 ("learning rate 3·10⁻⁴" for all networks under Adam); Haarnoja 2018b Table 1 confirms 3e-4 for actor / critic / temperature. |
| `sac.gamma` | `0.99` |  | gamma=0.99 — Haarnoja 2018a Table 1 (discount factor 0.99). |
| `sac.tau` | `0.005` |  | tau=0.005 — Haarnoja 2018a Table 1 ("target smoothing coefficient τ=0.005"); polyak averaging θ̄ ← τθ + (1-τ)θ̄. |
| `sac.alpha` | `0.2` |  | alpha=0.2 — Haarnoja 2018a Table 1 fixed-temperature default; Haarnoja 2018b §5 / Appendix D makes it learnable when alpha_auto=True (target_entropy = -dim(A)). |
| `sac.alpha_auto` | `True` |  | alpha_auto=True — Haarnoja 2018b §5 ("Automating Entropy Adjustment for Maximum Entropy RL"), Eq. (17–18); reported as robust to environment changes and the default in subsequent implementations (e.g. Stable-Baselines3 SAC). |
| `sac.hidden_size` | `256` |  | hidden_size=256 — Haarnoja 2018a Table 1 ("two hidden layers, 256 units each") for all actor and Q-network MLPs. |
| `sac.n_updates_per_step` | `1` |  | n_updates_per_step=1 — Haarnoja 2018a Table 1 ("number of gradient steps per env step = 1"); higher values trade sample-efficiency for compute (Haarnoja 2018b Appendix D). |
| `sac.warmup_steps` | `10000` |  | warmup_steps=10_000 — Haarnoja 2018a §5.2 ("first 10⁴ env steps use uniform random actions to seed the replay buffer"). |
| `sac.total_timesteps` | `1000000` |  | total_timesteps=1e6 — matches the PPO baseline horizon so the PPO/SAC comparison is wall-clock and step-budget aligned. |
| `gym_env.episode_length` | `365` |  | Episode parameters |
| `gym_env.cost_normalizer` | `5000.0` |  | Reward shaping parameters |
| `gym_env.carbon_normalizer` | `1000.0` |  |  |
| `gym_env.service_reward_weight` | `10.0` |  |  |
| `gym_env.stockout_penalty_coef` | `0.001` |  |  |
| `gym_env.stockout_penalty_exponent` | `1.5` |  |  |
| `gym_env.buffer_reward` | `0.5` |  |  |
| `gym_env.buffer_zone_low` | `0.15` |  |  |
| `gym_env.buffer_zone_high` | `0.4` |  |  |
| `gym_env.holding_penalty_coef` | `0.1` |  |  |
| `gym_env.cost_penalty_weight` | `3.0` |  |  |
| `gym_env.carbon_penalty_weight` | `1.0` |  |  |
| `gym_env.early_termination_penalty` | `500.0` |  |  |
| `gym_env.early_termination_stockout_threshold` | `0.5` |  |  |
| `gym_env.base_distance` | `100.0` |  | Synthetic distance parameters for cost/carbon calculation |
| `gym_env.distance_per_index_diff` | `50.0` |  |  |
| `gym_env.cost_per_unit_distance` | `0.018` |  |  |
| `gym_env.carbon_per_unit_distance` | `0.003` |  |  |
| `gym_env.replenishment_rate_per_day` | `0.015` |  | Replenishment rate (fraction of capacity per day) |
| `gym_env.lead_time_days` | `3` |  | ----- FIX-022 stress-mode parameters ----- Activated only when ``SupplyChainEnv(stress_mode=True)`` is instantiated. Each value carries an inline citation to the primary literature source [Gijsbrechts-2022 §5.1 Table 1; Vanvuchelen-2024... |
| `gym_env.stress_max_order_multiplier` | `0.4` |  | max_order_multiplier sized so that action=0.5 (the natural mean of an unbiased Beta(2,2) actor) maps to the per-warehouse mean daily demand, and action=1.0 to twice that. This keeps the PPO policy's initial gradient signal in the product... |
| `gym_env.stress_holding_cost_per_kg` | `0.015` |  |  |
| `gym_env.stress_stockout_cost_per_kg` | `2.7` |  |  |
| `gym_env.warehouse_shock_prob` | `0.005` |  | Shock probabilities |
| `gym_env.warehouse_shock_recovery_prob` | `0.05` |  |  |
| `gym_env.customer_shock_prob` | `0.003` |  |  |
| `gym_env.customer_shock_recovery_prob` | `0.07` |  |  |
| `gym_env.demand_shock_multiplier` | `3.0` |  | Demand shock multiplier for affected customers |
| `gym_env.demand_min` | `30.0` |  | Demand generation parameters |
| `gym_env.demand_max` | `80.0` |  |  |
| `gym_env.weekly_amplitude` | `0.2` |  |  |
| `gym_env.forecast_noise_std` | `2.0` |  | Forecast noise std |
| `gym_env.fallback_warehouse_capacity` | `50000.0` |  | Fallback warehouse capacity when config mismatch |
| `product.n_products` | `1` |  | default=1 preserves C3.5 |
| `product.product_names` | `['General']` |  |  |
| `product.product_value_per_kg` | `[100.0]` |  |  |
| `product.product_density` | `[0.8]` |  |  |
| `robust.enabled` | `False` |  | default=False preserves C3.6 |
| `robust.n_scenarios` | `10` |  |  |
| `robust.demand_noise_sigma` | `0.2` |  |  |
| `robust.risk_lambda` | `0.5` |  |  |
| `carbon_budget.mode` | `"none"` |  | "none" \| "20pct" \| "40pct" |
| `carbon_budget.custom_reduction_pct` | `0.0` |  |  |
| `shock.supply_severity` | `0.5` |  | SupplyShock: capacity remaining factor (0.5 = 50% loss) |
| `shock.demand_multiplier` | `3.0` |  | DemandShock: demand multiplication factor (3.0 = 3x demand) |
| `shock.duration_min_days` | `14` |  | Shock duration range (min_days, max_days) — both supply and demand |
| `shock.duration_max_days` | `60` |  |  |
| `shock.random_start_min_offset_days` | `10` |  | Earliest post-warmup start day offset for randomly-timed shocks |
| `shock.dbscan_eps_degrees` | `1.5` |  | DBSCAN clustering parameters for demand-shock cluster selection |
| `shock.dbscan_min_samples` | `3` |  |  |
| `shock.sequential_default_fraction` | `0.2` |  | 20% of total customers |
| `shock.supply_seed_offset` | `1000` |  | Per-shock RNG seed offsets for Monte-Carlo runs (job_id-based) |
| `shock.demand_seed_offset` | `2000` |  |  |
| `shock.fallback_shock_start_day` | `50` |  | Default fallback shock window when shock_start/end are unset |
| `shock.fallback_shock_end_day` | `80` |  |  |
| `shock.monte_carlo_n_runs` | `500` |  | Monte-Carlo runner default number of replications |
| `sensitivity.fast_mode` | `False` |  | FIX-016 — fast-mode flag required by tasks.md §3.6. Default False preserves the standard 11-point OAT grid and the 1024-sample Saltelli decomposition. |
| `sensitivity.default_n_samples` | `1024` |  | Saltelli base size N. Total evaluations = N * (2D + 2). For D=4 this is N * 10. fast_n_samples=8 yields 80 evaluations (acceptable for CI); default_n_samples=1024 yields 10,240 evaluations (matches Saltelli 2010 §6 recommendation of N >=... |
| `sensitivity.fast_n_samples` | `8` |  |  |
| `sensitivity.default_pop_size` | `40` |  | NSGA-II per-call budget (independent of NSGAConfig defaults so the production solver is not affected). |
| `sensitivity.default_n_gen` | `8` |  |  |
| `sensitivity.fast_pop_size` | `32` |  |  |
| `sensitivity.fast_n_gen` | `5` |  |  |
| `sensitivity.instance_n_warehouses` | `3` |  | Reduced problem instance for sensitivity analysis. Saltelli et al. (2010) §3 establishes that variance-decomposition accuracy depends on N (Saltelli base size) rather than on model dimension; a 3-warehouse / 8-customer test instance ther... |
| `sensitivity.instance_n_customers` | `8` |  |  |
| `sensitivity.instance_distance_min` | `50.0` |  |  |
| `sensitivity.instance_distance_max` | `500.0` |  |  |
| `sensitivity.instance_demand_min` | `100.0` |  |  |
| `sensitivity.instance_demand_max` | `5000.0` |  |  |
| `sensitivity.instance_warehouse_capacities` | `[50000.0, 45000.0, 40000.0]` |  |  |
| `random_seed` | `42` |  |  |
