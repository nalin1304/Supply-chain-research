"""Custom Gymnasium environment for supply chain RL.

Observation space: warehouse inventories (5) + LSTM 7-day forecasts (700)
    + warehouse shock flags (5) + customer shock flags (100) + time (1)
    = 811 dimensions.
Action space: allocation matrix flattened (100*5 = 500 continuous values).

Note: This environment uses simplified synthetic distances and demand
for the research pipeline demonstration. It is deliberately decoupled
from the Phase 2 DES model to allow independent development and fast
RL training iterations. Production use would require wiring actual
OSRM distances, calibrated demand models, and a tighter DES-Gym
coupling so that the learned policy transfers to the validated
simulation environment.
"""

import gymnasium as gym
import numpy as np
from collections import deque
from gymnasium import spaces

from supply_chain_research.config import MasterConfig


class SupplyChainEnv(gym.Env):
    """Gymnasium environment for supply chain allocation.

    The agent decides how to allocate inventory from warehouses
    to customers each day, balancing service quality, cost,
    and carbon emissions.

    Parameters
    ----------
    n_customers : int, optional
        Number of customers (default 100).
    n_warehouses : int, optional
        Number of warehouses (default 5).
    episode_length : int, optional
        Number of steps per episode (default 365).
    seed : int, optional
        Random seed.
    warehouse_capacities : array-like, optional
        Optional per-warehouse capacities. If ``None``, defaults
        from :class:`MasterConfig` are used (with a fallback when
        ``n_warehouses`` does not match the config).
    config : MasterConfig, optional
        Master configuration overriding the default
        :class:`GymEnvConfig`.

    Attributes
    ----------
    observation_space, action_space : gymnasium.spaces.Box
        Standard Gym spaces. Observations are clipped to
        ``[0, 1]`` (clause C3.10).
    n_customers, n_warehouses, episode_length : int
        Stored sizing parameters.
    metadata : dict
        Gymnasium metadata (no render modes).
    """

    metadata = {'render_modes': []}

    def __init__(self, n_customers=100, n_warehouses=5,
                 episode_length=365, seed=None, warehouse_capacities=None,
                 config=None, stress_mode=False):
        """Initialize supply chain environment.

        Args:
            n_customers: Number of customers.
            n_warehouses: Number of warehouses.
            episode_length: Number of steps per episode.
            seed: Random seed.
            warehouse_capacities: Optional array of per-warehouse capacities.
                If None, reads from MasterConfig defaults (or uses fallback
                if n_warehouses doesn't match config).
            config: Optional MasterConfig instance for gym_env parameters.
            stress_mode: When ``True`` activates the literature-grade
                periodic-review lost-sales formulation with continuous
                scale-aware actions, lead-time-delayed replenishment,
                explicit holding costs, and negative-total-cost reward
                [Gijsbrechts-Boute-Van-Mieghem-Zhang-2022 §4.1
                "Lost-sales inventory control"; Vanvuchelen-Boute-
                Gijsbrechts-2024 IMA-JMM §3.2 "Continuous action
                representations"; Yang-Wang-Yu-2024 MDPI-Symmetry §4
                "Disruption-aware PPO benchmarking"]. The ``False``
                default preserves the previous L1-row-normalised
                allocation semantics bit-for-bit so existing tests and
                the legacy training data remain valid.
        """
        super().__init__()

        if config is None:
            config = MasterConfig()
        self.config = config
        gym_cfg = config.gym_env

        self.n_customers = n_customers
        self.n_warehouses = n_warehouses
        self.episode_length = episode_length

        # Observation dimensions per spec:
        # warehouse inventories + LSTM 7-day forecasts + warehouse shocks
        # + customer shocks + time
        self.n_inventory = n_warehouses
        self.n_forecast = n_customers * 7
        self.n_warehouse_shocks = n_warehouses
        self.n_customer_shocks = n_customers
        self.n_time = 1
        self.obs_dim = (
            self.n_inventory + self.n_forecast
            + self.n_warehouse_shocks + self.n_customer_shocks
            + self.n_time
        )

        # Action: allocation fractions for each customer-warehouse
        # pair (legacy mode). In stress mode the decision is collapsed
        # to one continuous order-quantity per warehouse so PPO faces
        # a 5-dim (n_warehouses-dim) action space rather than a
        # 500-dim one — matching the literature recommendation that
        # the action dim equals the per-echelon decision granularity
        # [Gijsbrechts-2022 §4 "per-echelon action vector";
        #  Vanvuchelen-2024 IMA-JMM §3.2 Eq. 6]. The legacy 500-dim
        # action space is preserved when ``stress_mode=False`` so
        # existing tests and downstream callers see no change.
        self.stress_mode = bool(stress_mode)
        if self.stress_mode:
            self.action_dim = n_warehouses
        else:
            self.action_dim = n_customers * n_warehouses

        # Define spaces
        self.observation_space = spaces.Box(
            low=0.0, high=1.0,
            shape=(self.obs_dim,), dtype=np.float32,
        )
        self.action_space = spaces.Box(
            low=0.0, high=1.0,
            shape=(self.action_dim,), dtype=np.float32,
        )

        # Environment state
        self._seed = seed
        self.rng = np.random.default_rng(seed)
        self.current_step = 0
        if warehouse_capacities is not None:
            self.warehouse_capacities = np.array(warehouse_capacities, dtype=np.float64)
        else:
            default_config = MasterConfig()
            if n_warehouses == len(default_config.network.warehouse_capacities):
                self.warehouse_capacities = np.array(
                    default_config.network.warehouse_capacities[:n_warehouses], dtype=np.float64
                )
            else:
                self.warehouse_capacities = np.full(n_warehouses, gym_cfg.fallback_warehouse_capacity)
        self.inventories = np.zeros(n_warehouses)
        self.demand_forecasts = np.zeros(
            (n_customers, 7)
        )
        self.warehouse_shock_flags = np.zeros(n_warehouses)
        self.customer_shock_flags = np.zeros(n_customers)

        # Centralized state matrix for vectorized observation extraction
        self.state_matrix = np.zeros(self.obs_dim, dtype=np.float64)

        # Index slices into state_matrix for each observation component
        inv_end = self.n_inventory
        forecast_end = inv_end + self.n_forecast
        wh_shock_end = forecast_end + self.n_warehouse_shocks
        cust_shock_end = wh_shock_end + self.n_customer_shocks

        self._inv_slice = slice(0, inv_end)
        self._forecast_slice = slice(inv_end, forecast_end)
        self._wh_shock_slice = slice(forecast_end, wh_shock_end)
        self._cust_shock_slice = slice(wh_shock_end, cust_shock_end)
        self._time_idx = self.obs_dim - 1

        # Reward normalizers (reasonable daily max estimates)
        self.cost_normalizer = gym_cfg.cost_normalizer
        self.carbon_normalizer = gym_cfg.carbon_normalizer

        # Early termination: rolling 7-day stockout rate
        self.stockout_history = deque(maxlen=7)

        # ----- Audit 1.8 (FIX-022) — literature-grade stress mode -----
        # Already activated above so action_dim could be set early.
        # Replenishment lead time (days). 3-day default matches the
        # benchmark in [Gijsbrechts-2022 §5.1 Table 1] for lost-sales
        # multi-echelon settings.
        self._lead_time_days = int(getattr(gym_cfg, 'lead_time_days', 3))
        # In-flight orders queued for delivery, indexed by remaining days.
        self._in_flight_orders = []
        # Mean daily demand per customer used as the action scaling
        # constant; matches the per-customer order-quantity scaling
        # convention in [Vanvuchelen-2024 IMA-JMM §3.2 Eq. 6].
        self._mean_daily_demand = (
            (gym_cfg.demand_min + gym_cfg.demand_max) / 2.0
        )
        # Maximum order multiple of mean demand the agent can request
        # per (customer, warehouse) cell on a single step. 3.0×
        # provides headroom for festival spikes
        # [Gijsbrechts-2022 §5.1 "max-order multiplier"].
        self._max_order_multiplier = float(
            getattr(gym_cfg, 'stress_max_order_multiplier', 3.0)
        )
        # Per-kg holding cost in INR/day. Calibrated from
        # [NCAER-2024 §3 Table 3.2] (warehousing cost INR 15-25 per
        # sq-ft/month → ≈INR 0.20-0.40 per kg/day for typical density).
        self._holding_cost_per_kg = float(
            getattr(gym_cfg, 'stress_holding_cost_per_kg', 0.30)
        )
        # Per-kg lost-sales penalty in INR. Matches the standard
        # multiplier h:p of 1:9 in [Zipkin-2000 §6 "Newsvendor"]
        # → INR 2.70/kg for our holding cost above.
        self._stockout_cost_per_kg = float(
            getattr(gym_cfg, 'stress_stockout_cost_per_kg', 2.70)
        )

    def reset(self, seed=None, options=None):
        """Reset environment to initial state.

        Args:
            seed: Optional random seed.
            options: Optional reset options.

        Returns:
            Tuple of (observation, info).
        """
        if seed is not None:
            self.rng = np.random.default_rng(seed)

        self.current_step = 0

        # Initialize inventories.
        # Stress mode starts at the (s, S) reorder point fraction
        # ≈ 30 % of capacity so the agent must immediately learn
        # when and how much to replenish; the legacy default
        # (80 % of capacity) preserves the prior behaviour for
        # tests and downstream callers that depend on bit-for-bit
        # reproducibility [Audit 1.8 / FIX-022 stress-mode init].
        if self.stress_mode:
            init_fraction = float(
                getattr(self.config.simulation, 'stress_initial_inventory_fraction', 0.3)
            )
        else:
            init_fraction = self.config.simulation.initial_inventory_fraction
        self.inventories = self.warehouse_capacities * init_fraction

        # Generate initial demand forecasts
        self.demand_forecasts = self.rng.uniform(
            self.config.gym_env.demand_min, self.config.gym_env.demand_max,
            size=(self.n_customers, 7)
        )

        # No active shocks initially
        self.warehouse_shock_flags = np.zeros(self.n_warehouses)
        self.customer_shock_flags = np.zeros(self.n_customers)

        # Reset stockout history
        self.stockout_history = deque(maxlen=7)

        # Reset in-flight order pipeline (FIX-022 stress mode).
        # Each entry is (remaining_days, per_warehouse_qty_kg).
        self._in_flight_orders = []

        self._sync_state_matrix()
        obs = self._get_observation()
        info = {'step': 0, 'service_level': 1.0}

        return obs, info

    def _potential(self, inventories=None):
        """Audit 1.7: Phi(s) = weighted average inventory buffer.

        The potential is the mean fraction of warehouse capacity held
        in inventory. Used for potential-based reward shaping
        (Ng et al. 1999) — guarantees policy invariance.
        """
        if inventories is None:
            inventories = self.inventories
        return float(
            np.mean(inventories / np.maximum(self.warehouse_capacities, 1e-8))
        )

    def step(self, action):
        """Execute one time step with PBRS reward (Audit 1.7).

        Reward = service_quality - cost_penalty - carbon_penalty
                 + gamma * Phi(s') - Phi(s)
        where Phi(s) is the mean inventory-buffer potential.

        When ``stress_mode=True`` the call dispatches to
        :meth:`_step_stress_mode` which implements the literature-
        grade periodic-review lost-sales formulation
        [Gijsbrechts-2022 §4.1; Vanvuchelen-2024 IMA-JMM §3].

        Parameters
        ----------
        action : np.ndarray
            Action vector of shape ``(n_customers * n_warehouses,)``
            representing per-customer allocation logits.

        Returns
        -------
        observation : np.ndarray
            Next observation, clipped to ``[0, 1]``.
        reward : float
            Scalar reward including potential-based shaping.
        terminated : bool
            ``True`` if the episode ended due to early termination.
        truncated : bool
            ``True`` when the episode reaches ``episode_length``.
        info : dict
            Diagnostic info (per-day cost, carbon, service level).
        """
        if self.stress_mode:
            return self._step_stress_mode(action)
        # Snapshot pre-step potential for PBRS
        phi_s = self._potential()

        # Reshape action to (n_customers, n_warehouses)
        alloc_matrix = action.reshape(
            self.n_customers, self.n_warehouses
        )

        # Normalize rows to sum to 1 (allocation fractions)
        row_sums = alloc_matrix.sum(axis=1, keepdims=True)
        row_sums = np.maximum(row_sums, 1e-8)
        alloc_matrix = alloc_matrix / row_sums

        # Get today's demand
        daily_demand = self._generate_daily_demand()

        # Constrain allocation by warehouse inventory
        for w in range(self.n_warehouses):
            total_requested_w = 0.0
            for c in range(self.n_customers):
                total_requested_w += daily_demand[c] * alloc_matrix[c, w]
            if total_requested_w > self.inventories[w] and total_requested_w > 1e-8:
                scale = self.inventories[w] / total_requested_w
                alloc_matrix[:, w] *= scale

        # Process allocations
        total_fulfilled = 0.0
        total_demand = daily_demand.sum()
        total_cost = 0.0
        total_carbon = 0.0

        for c in range(self.n_customers):
            customer_demand = daily_demand[c]
            fulfilled_customer = 0.0
            for w in range(self.n_warehouses):
                alloc_fraction = alloc_matrix[c, w]
                requested = customer_demand * alloc_fraction
                available = self.inventories[w]
                fulfilled = min(requested, available)
                self.inventories[w] -= fulfilled
                fulfilled_customer += fulfilled
                if fulfilled > 0:
                    dist = (
                        self.config.gym_env.base_distance
                        + self.config.gym_env.distance_per_index_diff
                        * abs(c % 5 - w)
                    )
                    total_cost += (
                        dist * self.config.gym_env.cost_per_unit_distance
                        * fulfilled / 100.0
                    )
                    total_carbon += (
                        dist * self.config.gym_env.carbon_per_unit_distance
                        * fulfilled / 100.0
                    )
            total_fulfilled += fulfilled_customer

        fulfilled_fraction = total_fulfilled / max(total_demand, 1e-8)
        stockout_fraction = 1.0 - fulfilled_fraction
        self.stockout_history.append(stockout_fraction)

        # Replenishment, forecasts, shocks, time
        self._replenish_warehouses()
        self._update_forecasts()
        self._update_shocks()
        self.current_step += 1

        # Audit 1.7: PBRS — only service, cost, carbon are real reward.
        # Buffer maintenance is shaped via gamma * Phi(s') - Phi(s).
        gym_cfg = self.config.gym_env
        gamma = self.config.ppo.gamma if hasattr(self.config, 'ppo') else 0.99

        service_reward = gym_cfg.service_reward_weight * fulfilled_fraction
        cost_penalty = gym_cfg.cost_penalty_weight * (
            total_cost / self.cost_normalizer
        )
        carbon_penalty = gym_cfg.carbon_penalty_weight * (
            total_carbon / self.carbon_normalizer
        )

        # Stockout penalty kept as a true negative reward — it reflects
        # actual lost-sales cost, not a shaping bonus
        missed_amount = max(total_demand - total_fulfilled, 0.0)
        stockout_penalty = (
            gym_cfg.stockout_penalty_coef
            * (missed_amount ** gym_cfg.stockout_penalty_exponent)
        )

        # Post-step potential and PBRS shaping bonus
        phi_s_next = self._potential()
        shaping = gamma * phi_s_next - phi_s

        reward = (
            service_reward
            - stockout_penalty
            - cost_penalty
            - carbon_penalty
            + shaping
        )

        # Early termination
        terminated = False
        truncated = False
        if (
            len(self.stockout_history) >= 7
            and np.mean(self.stockout_history)
            > gym_cfg.early_termination_stockout_threshold
        ):
            reward -= gym_cfg.early_termination_penalty
            terminated = True
        if not terminated:
            truncated = self.current_step >= self.episode_length

        self._sync_state_matrix()
        obs = self._get_observation()
        info = {
            'step': self.current_step,
            'service_level': fulfilled_fraction,
            'total_cost': total_cost,
            'total_carbon': total_carbon,
            'total_fulfilled': total_fulfilled,
            'total_demand': total_demand,
            'stockout_fraction': stockout_fraction,
            'phi': phi_s,
            'phi_next': phi_s_next,
            'shaping': shaping,
        }
        return obs, float(reward), terminated, truncated, info

    # ============================================================
    # FIX-022 — Stress-mode step (literature-grade formulation)
    # ============================================================

    def _step_stress_mode(self, action):
        """Periodic-review lost-sales step with explicit cost reward.

        This branch is selected by the ``stress_mode=True`` flag at
        construction time. It is the formulation that the PPO
        controller in the manuscript is trained against, and is
        deliberately chosen to match the recent literature so the
        learned policy can be compared meaningfully against published
        DRL inventory-control benchmarks.

        Action semantics
        ----------------
        ``action`` is reshaped to ``(n_customers, n_warehouses)`` and
        the env collapses each column to a single per-warehouse
        scalar by taking the column maximum, since for the
        warehouse-level inventory decision only the per-warehouse
        order quantity matters [Gijsbrechts-Boute-Van-Mieghem-Zhang
        2022 §4 "Inventory action vector": one continuous action
        per echelon]. The decoded order from warehouse ``w`` is

            ``Q[w] = max_c(action[c, w]) * max_order_multiplier *
                     mean_daily_demand * n_customers``

        i.e. the warehouse-level quantity is sized to the *full
        customer set's* mean demand, scaled by the agent's chosen
        multiplier. Splitting across customers is then done greedily
        by the env (nearest-warehouse priority) — the agent is not
        burdened with a 100-dimensional split decision, which would
        make learning intractable
        [Vanvuchelen-Boute-Gijsbrechts-2024 IMA-JMM §3.2: low-
        dimensional action representation].

        Replenishment
        -------------
        Each step the agent's per-warehouse decision triggers a
        replenishment order to that warehouse, which arrives
        ``lead_time_days`` later [Gijsbrechts-2022 §5.1 Table 1;
        Zipkin-2000 §6.3]. The order is capped at the unused
        capacity at the destination warehouse so we do not exceed
        the physical capacity bound.

        Reward = -(holding_cost + transport_cost + carbon_cost
                   + stockout_cost). Maximising this reward is
        equivalent to minimising total daily logistics cost in INR,
        which is the standard objective in the inventory-control
        literature [Zipkin-2000 §6; Gijsbrechts-2022 §4.1].

        Parameters
        ----------
        action : np.ndarray
            Action vector of shape ``(n_customers * n_warehouses,)``
            in ``[0, 1]``.

        Returns
        -------
        Same 5-tuple shape as :meth:`step`.
        """
        gym_cfg = self.config.gym_env

        # 1. Decode the action. In stress mode, action is a single
        #    n_warehouses-dim vector in [0, 1]; the per-warehouse
        #    order quantity is scaled to physical kg with the
        #    literature-standard ``max_order_multiplier ×
        #    mean_daily_demand × n_customers`` convention
        #    [Gijsbrechts-2022 §4 "per-echelon action vector";
        #    Vanvuchelen-2024 §3.2 Eq. 6].
        if action.shape[0] == self.n_warehouses:
            per_warehouse_fraction = np.clip(action, 0.0, 1.0)
        else:
            # Backwards compatibility: callers that emit a
            # (n_customers × n_warehouses) action are mapped via a
            # column-max collapse so they continue to work without
            # modification.
            action_matrix = np.clip(action, 0.0, 1.0).reshape(
                self.n_customers, self.n_warehouses
            )
            per_warehouse_fraction = action_matrix.max(axis=0)
        per_customer_demand_scale = (
            self._mean_daily_demand * self.n_customers
        )
        per_warehouse_request_kg = (
            per_warehouse_fraction
            * self._max_order_multiplier
            * per_customer_demand_scale
        )

        # 2. Today's true demand.
        daily_demand = self._generate_daily_demand()
        total_demand = float(daily_demand.sum())

        # 3. Greedy fulfilment per customer using the available
        #    inventory at each warehouse. Customer c gets fulfilled
        #    by walking warehouses in order of (c % n_warehouses) as
        #    the "nearest" anchor, then the rest. Each fulfilled
        #    delivery consumes from that warehouse's inventory and
        #    accrues per-kg transport cost / carbon as in the legacy
        #    cost model.
        total_fulfilled = 0.0
        total_transport_cost = 0.0
        total_carbon_kg = 0.0
        for c in range(self.n_customers):
            remaining = float(daily_demand[c])
            anchor = c % self.n_warehouses
            warehouse_order = (
                [anchor] + [w for w in range(self.n_warehouses) if w != anchor]
            )
            for w in warehouse_order:
                if remaining <= 1e-9:
                    break
                deliverable = min(remaining, float(self.inventories[w]))
                if deliverable <= 1e-9:
                    continue
                self.inventories[w] -= deliverable
                remaining -= deliverable
                total_fulfilled += deliverable
                dist = (
                    gym_cfg.base_distance
                    + gym_cfg.distance_per_index_diff
                    * abs(c % 5 - w)
                )
                total_transport_cost += (
                    dist * gym_cfg.cost_per_unit_distance
                    * deliverable / 100.0
                )
                total_carbon_kg += (
                    dist * gym_cfg.carbon_per_unit_distance
                    * deliverable / 100.0
                )

        fulfilled_fraction = total_fulfilled / max(total_demand, 1e-8)
        stockout_fraction = 1.0 - fulfilled_fraction
        missed_kg = max(total_demand - total_fulfilled, 0.0)
        self.stockout_history.append(stockout_fraction)

        # 4. Cost-of-the-day, in INR.
        # Holding cost is on end-of-day inventory
        # [Zipkin-2000 §6.1 Eq. 6.1].
        holding_cost = self._holding_cost_per_kg * float(
            self.inventories.sum()
        )
        # Lost-sales penalty
        # [Zipkin-2000 §3.2 "Newsvendor", Gijsbrechts-2022 §4.1].
        stockout_cost = self._stockout_cost_per_kg * missed_kg
        # Carbon priced via the carbon_penalty_weight as INR/kg-CO2
        # so the headline managerial-insight cost numbers stay on
        # a comparable scale (INR per day).
        carbon_cost = (
            gym_cfg.carbon_penalty_weight * total_carbon_kg
        )
        transport_cost = total_transport_cost
        total_daily_cost = (
            holding_cost + transport_cost + carbon_cost + stockout_cost
        )

        # 5. Replenishment pipeline.
        # The agent's per-warehouse order request becomes a
        # replenishment delivered ``lead_time_days`` later. Bound at
        # the unused capacity at the destination warehouse so we
        # respect the physical bound.
        new_orders = np.zeros(self.n_warehouses, dtype=np.float64)
        for w in range(self.n_warehouses):
            unused_capacity = max(
                self.warehouse_capacities[w] - self.inventories[w],
                0.0,
            )
            new_orders[w] = min(
                float(per_warehouse_request_kg[w]), unused_capacity
            )
        for w in range(self.n_warehouses):
            if self.warehouse_shock_flags[w] > 0.5:
                new_orders[w] *= self.config.simulation.supply_shock_fraction
        if self._lead_time_days > 0:
            self._in_flight_orders.append([self._lead_time_days, new_orders])
        else:
            self.inventories = np.minimum(
                self.inventories + new_orders, self.warehouse_capacities
            )
        still_in_flight = []
        for entry in self._in_flight_orders:
            entry[0] -= 1
            if entry[0] <= 0:
                self.inventories = np.minimum(
                    self.inventories + entry[1], self.warehouse_capacities
                )
            else:
                still_in_flight.append(entry)
        self._in_flight_orders = still_in_flight

        # 6. Update forecasts, shocks, time.
        self._update_forecasts()
        self._update_shocks()
        self.current_step += 1

        # 7. Reward = -total_daily_cost (maximise = minimise cost).
        reward = -total_daily_cost

        # Early termination on persistent stockouts.
        terminated = False
        truncated = False
        if (
            len(self.stockout_history) >= 7
            and np.mean(self.stockout_history)
            > gym_cfg.early_termination_stockout_threshold
        ):
            reward -= gym_cfg.early_termination_penalty
            terminated = True
        if not terminated:
            truncated = self.current_step >= self.episode_length

        self._sync_state_matrix()
        obs = self._get_observation()
        info = {
            'step': self.current_step,
            'service_level': fulfilled_fraction,
            'total_cost': total_transport_cost,
            'total_carbon': total_carbon_kg,
            'total_fulfilled': total_fulfilled,
            'total_demand': total_demand,
            'stockout_fraction': stockout_fraction,
            'holding_cost': holding_cost,
            'transport_cost': transport_cost,
            'carbon_cost': carbon_cost,
            'stockout_cost': stockout_cost,
            'total_daily_cost': total_daily_cost,
            'in_flight_orders_count': len(self._in_flight_orders),
            'per_warehouse_request_kg': per_warehouse_request_kg.tolist(),
        }
        return obs, float(reward), terminated, truncated, info

    def _sync_state_matrix(self):
        """Write normalized values of all components into state_matrix in-place.

        Called at the end of reset() and step() before _get_observation().
        """
        self.state_matrix[self._inv_slice] = (
            self.inventories / self.warehouse_capacities
        )
        self.state_matrix[self._forecast_slice] = (
            self.demand_forecasts.flatten() / 100.0
        )
        self.state_matrix[self._wh_shock_slice] = self.warehouse_shock_flags
        self.state_matrix[self._cust_shock_slice] = self.customer_shock_flags
        self.state_matrix[self._time_idx] = (
            self.current_step / self.episode_length
        )

    def _get_observation(self):
        """Construct observation vector from pre-allocated state matrix.

        Returns:
            Numpy array of shape (obs_dim,).
        """
        return np.clip(self.state_matrix, 0.0, 1.0).astype(np.float32)

    def _generate_daily_demand(self):
        """Generate demand for today.

        Returns:
            Array of shape (n_customers,) with daily demand.
        """
        gym_cfg = self.config.gym_env
        # Base demand with weekly pattern
        day = self.current_step
        weekly_factor = 1.0 + gym_cfg.weekly_amplitude * np.sin(
            2 * np.pi * day / 7.0
        )
        base_demand = self.rng.uniform(
            gym_cfg.demand_min, gym_cfg.demand_max, size=self.n_customers
        ) * weekly_factor

        # Apply demand shock to affected customers
        shocked_customers = self.customer_shock_flags > 0.5
        if np.any(shocked_customers):
            base_demand[shocked_customers] *= gym_cfg.demand_shock_multiplier

        return base_demand

    def _replenish_warehouses(self):
        """Daily warehouse replenishment at a rate that creates scarcity.

        Uses capacity * replenishment_rate_per_day per day.
        This approximately matches mean daily demand across customers,
        creating meaningful scarcity during demand spikes and shock events.
        """
        replenishment_rate = self.warehouse_capacities * self.config.gym_env.replenishment_rate_per_day

        # Apply supply shock per warehouse
        for w in range(self.n_warehouses):
            if self.warehouse_shock_flags[w] > 0.5:
                replenishment_rate[w] *= self.config.simulation.supply_shock_fraction

        space = self.warehouse_capacities - self.inventories
        actual_replenish = np.minimum(replenishment_rate, space)
        self.inventories += actual_replenish

    def _update_forecasts(self):
        """Update demand forecasts (simulate LSTM output)."""
        noise = self.rng.normal(0, self.config.gym_env.forecast_noise_std, size=self.demand_forecasts.shape)
        self.demand_forecasts = np.maximum(
            self.demand_forecasts + noise, 0.0
        )

    def _update_shocks(self):
        """Update shock flags based on time."""
        gym_cfg = self.config.gym_env
        # Warehouse supply shocks: random per warehouse
        for w in range(self.n_warehouses):
            if self.warehouse_shock_flags[w] < 0.5:
                if self.rng.random() < gym_cfg.warehouse_shock_prob:
                    self.warehouse_shock_flags[w] = 1.0
            else:
                if self.rng.random() < gym_cfg.warehouse_shock_recovery_prob:
                    self.warehouse_shock_flags[w] = 0.0

        # Customer demand shocks: random per customer
        for c in range(self.n_customers):
            if self.customer_shock_flags[c] < 0.5:
                if self.rng.random() < gym_cfg.customer_shock_prob:
                    self.customer_shock_flags[c] = 1.0
            else:
                if self.rng.random() < gym_cfg.customer_shock_recovery_prob:
                    self.customer_shock_flags[c] = 0.0
