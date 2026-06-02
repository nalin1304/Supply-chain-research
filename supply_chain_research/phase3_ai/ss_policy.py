"""(s, S) Inventory Policy Baseline for PPO Comparison.

Implements the classic (s, S) reorder-point / order-up-to policy:
- When inventory drops below reorder point `s`, place an order
- Order enough to bring inventory up to level `S`

This serves as the baseline that the PPO agent must beat to justify
the use of reinforcement learning for inventory management.

References:
    - Zipkin, P.H. (2000). Foundations of Inventory Management. McGraw-Hill.
    - Silver, E.A., Pyke, D.F., & Thomas, D.J. (2017). Inventory and
      Production Management in Supply Chains. 4th ed. CRC Press.
"""


import numpy as np


class SSPolicy:
    """(s, S) inventory policy for supply chain environment.

    Parameters
    ----------
    n_warehouses : int
        Number of warehouses.
    n_customers : int
        Number of customers.
    reorder_point_fraction : float
        Fraction of capacity at which to trigger reorder (s = fraction * capacity).
        Default 0.3 means reorder when stock drops below 30% of capacity.
    order_up_to_fraction : float
        Fraction of capacity to order up to (S = fraction * capacity).
        Default 0.9 means order enough to fill to 90% of capacity.
    warehouse_capacities : np.ndarray, optional
        Per-warehouse capacity in kg. If None, uses 50000 for all.

    Attributes
    ----------
    s : np.ndarray
        Reorder points per warehouse, shape (n_warehouses,).
    S : np.ndarray
        Order-up-to levels per warehouse, shape (n_warehouses,).
    """

    def __init__(
        self,
        n_warehouses: int,
        n_customers: int,
        reorder_point_fraction: float = 0.3,
        order_up_to_fraction: float = 0.9,
        warehouse_capacities: np.ndarray | None = None,
        review_period_days: int = 7,
    ):
        """
        Parameters
        ----------
        """
        self.n_warehouses = n_warehouses
        self.n_customers = n_customers
        self.reorder_point_fraction = reorder_point_fraction
        self.order_up_to_fraction = order_up_to_fraction
        self.review_period_days = int(review_period_days)
        # Track how many days since each warehouse last placed an
        # order — only place a fresh order when this counter reaches
        # ``review_period_days`` [Silver-Pyke-Thomas-2017 §5.4
        # "Periodic-review (R, s, S)" policy]. The continuous-time
        # version of (s, S) is for a separate model (Zipkin 2000 §5).
        self._days_since_order = np.zeros(n_warehouses, dtype=np.int64)

        if warehouse_capacities is None:
            warehouse_capacities = np.full(n_warehouses, 50000.0)
        self.warehouse_capacities = warehouse_capacities

        # Compute s and S levels
        self.s = self.reorder_point_fraction * self.warehouse_capacities
        self.S = self.order_up_to_fraction * self.warehouse_capacities

    def get_action(
        self,
        observation: np.ndarray,
        stress_mode: bool = False,
        max_order_multiplier: float = 3.0,
        mean_daily_demand: float = 800.0,
    ) -> np.ndarray:
        """Compute reorder action based on current inventory levels.

        The observation is expected to contain normalized inventory levels
        for each warehouse in the first n_warehouses elements (matching
        the :class:`SupplyChainEnv` observation space).

        Two action conventions are supported:

        - **Default mode** (``stress_mode=False``): the
          :class:`SupplyChainEnv` reshapes the action to a
          ``(n_customers, n_warehouses)`` matrix and L1-row-normalises
          across warehouses. The policy emits allocation magnitudes
          in ``[0, 1]`` that are 0 for warehouses above ``s`` and a
          uniform positive fraction across customers for warehouses
          below ``s``. Behaviour is bit-for-bit identical to the
          pre-FIX-022 implementation [bugfix.md C2.12].

        - **Stress mode** (``stress_mode=True``): the action is
          interpreted scale-aware as
          ``q[c, w] = action[c, w] * max_order_multiplier *
          mean_daily_demand`` (kg) following
          [Vanvuchelen-Boute-Gijsbrechts-2024 IMA-JMM §3.2 Eq. 6].
          The (s, S) policy translates a per-warehouse "order up to
          S" decision into the agent's action by spreading the order
          quantity uniformly across customers and dividing by the
          per-cell scaling constant
          ``max_order_multiplier * mean_daily_demand``.

        Parameters
        ----------
        observation : np.ndarray
            Environment observation vector. First ``n_warehouses``
            elements are normalised inventory levels (0-1).
        stress_mode : bool, optional
            Whether the target environment is running in stress mode.
            Default ``False`` for backward compatibility.
        max_order_multiplier : float, optional
            Must match ``GymEnvConfig.stress_max_order_multiplier``
            (default 3.0). Ignored when ``stress_mode=False``.
        mean_daily_demand : float, optional
            Must match ``(demand_min + demand_max) / 2`` from
            ``GymEnvConfig`` (≈800 kg with the defaults).

        Returns
        -------
        np.ndarray
            Action vector of shape ``(n_customers * n_warehouses,)``
            with allocation magnitudes in ``[0, 1]`` matching the
            :class:`SupplyChainEnv` action space.
        """
        # Extract inventory levels (first n_warehouses elements of obs)
        inv_levels = observation[: self.n_warehouses]  # normalized 0-1
        current_inventory = inv_levels * self.warehouse_capacities

        action_dim = self.n_customers * self.n_warehouses
        action = np.zeros(action_dim)

        if stress_mode:
            # Stress-mode: the env's action space is just
            # n_warehouses-dim; we emit one continuous order
            # quantity per warehouse following the periodic-review
            # (R, s, S) policy [Silver-Pyke-Thomas-2017 §5.4].
            scale_per_warehouse = max(
                max_order_multiplier
                * mean_daily_demand
                * self.n_customers,
                1e-6,
            )
            stress_action = np.zeros(self.n_warehouses, dtype=np.float64)
            for w in range(self.n_warehouses):
                cell_action = 0.0
                # Only review every R days
                if self._days_since_order[w] >= self.review_period_days:
                    self._days_since_order[w] = 0
                    if current_inventory[w] < self.s[w]:
                        order_kg = self.S[w] - current_inventory[w]
                        cell_action = float(
                            np.clip(order_kg / scale_per_warehouse, 0.0, 1.0)
                        )
                self._days_since_order[w] += 1
                stress_action[w] = cell_action
            return stress_action

        # ----- Default (legacy) mode: L1-row-normalised allocation -----
        for w in range(self.n_warehouses):
            if current_inventory[w] < self.s[w]:
                order_qty = self.S[w] - current_inventory[w]
                per_customer = order_qty / self.n_customers
                action_value = float(
                    np.clip(
                        per_customer / self.warehouse_capacities[w],
                        0.0,
                        1.0,
                    )
                )
                for c in range(self.n_customers):
                    idx = c * self.n_warehouses + w
                    if idx < action_dim:
                        action[idx] = action_value

        return action


def evaluate_ss_policy(
    env,
    n_warehouses: int = 5,
    n_customers: int = 20,
    n_episodes: int = 100,
    reorder_point_fraction: float = 0.3,
    order_up_to_fraction: float = 0.9,
    seed: int = 42,
    stress_mode: bool = False,
    max_order_multiplier: float = 3.0,
    mean_daily_demand: float = 800.0,
) -> dict:
    """Evaluate (s,S) policy on the supply chain environment.

    Parameters
    ----------
    env : gymnasium.Env
        The supply chain Gymnasium environment.
    n_warehouses : int
        Number of warehouses.
    n_customers : int
        Number of customers.
    n_episodes : int
        Number of evaluation episodes.
    reorder_point_fraction : float
        Reorder point as fraction of capacity.
    order_up_to_fraction : float
        Order-up-to level as fraction of capacity.
    seed : int
        Random seed for environment resets.
    stress_mode : bool, optional
        Set ``True`` when ``env`` was constructed with
        ``stress_mode=True``; the policy then emits actions in the
        scale-aware action space [Vanvuchelen-2024 IMA-JMM §3.2].
    max_order_multiplier : float, optional
        Must match ``env.config.gym_env.stress_max_order_multiplier``.
    mean_daily_demand : float, optional
        Must match ``(demand_min + demand_max) / 2`` in env config.

    Returns
    -------
    dict
        Evaluation results with keys:
        - mean_reward: Mean episode reward
        - std_reward: Std of episode rewards
        - mean_service_level: Mean service level across episodes
        - episode_rewards: List of all episode rewards
    """
    policy = SSPolicy(
        n_warehouses=n_warehouses,
        n_customers=n_customers,
        reorder_point_fraction=reorder_point_fraction,
        order_up_to_fraction=order_up_to_fraction,
        warehouse_capacities=getattr(env, 'warehouse_capacities', None),
    )

    episode_rewards = []
    episode_lengths = []

    for ep in range(n_episodes):
        obs, _ = env.reset(seed=seed + ep)
        # Reset (R, s, S) review-period counters every episode so
        # the policy starts each evaluation from a clean state.
        policy._days_since_order = np.zeros(n_warehouses, dtype=np.int64)
        total_reward = 0.0
        steps = 0
        done = False

        while not done:
            action = policy.get_action(
                obs,
                stress_mode=stress_mode,
                max_order_multiplier=max_order_multiplier,
                mean_daily_demand=mean_daily_demand,
            )
            obs, reward, terminated, truncated, info = env.step(action)
            total_reward += reward
            steps += 1
            done = terminated or truncated

        episode_rewards.append(total_reward)
        episode_lengths.append(steps)

    rewards = np.array(episode_rewards)

    return {
        "mean_reward": float(np.mean(rewards)),
        "std_reward": float(np.std(rewards)),
        "min_reward": float(np.min(rewards)),
        "max_reward": float(np.max(rewards)),
        "median_reward": float(np.median(rewards)),
        "n_episodes": n_episodes,
        "mean_episode_length": float(np.mean(episode_lengths)),
        "policy_params": {
            "reorder_point_fraction": reorder_point_fraction,
            "order_up_to_fraction": order_up_to_fraction,
        },
        "episode_rewards": rewards.tolist(),
    }
