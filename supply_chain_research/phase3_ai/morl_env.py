"""Multi-Objective RL Environment (Phase 14).

Wraps SupplyChainEnv to append preference weights (omega) to observations
and return a vectorized reward [R_cost, R_carbon].
"""

import numpy as np
from gymnasium import spaces

from supply_chain_research.phase3_ai.gym_environment import SupplyChainEnv


class MultiObjectiveSupplyChainEnv(SupplyChainEnv):
    def __init__(self, n_customers=100, n_warehouses=5, episode_length=365, seed=None, config=None, stress_mode=False):
        super().__init__(
            n_customers=n_customers,
            n_warehouses=n_warehouses,
            episode_length=episode_length,
            seed=seed,
            config=config,
            stress_mode=stress_mode
        )
        
        # Extend observation space to include omega (2D preference vector: [omega_cost, omega_carbon])
        original_obs_dim = self.observation_space.shape[0]
        self.obs_dim = original_obs_dim + 2
        self.observation_space = spaces.Box(
            low=0.0, high=1.0,
            shape=(self.obs_dim,), dtype=np.float32
        )
        
        # Default preference (equal weights)
        self.current_omega = np.array([0.5, 0.5], dtype=np.float32)
        
    def set_preference(self, omega_cost: float):
        """Set the scalar preference for cost. Carbon preference is (1 - omega_cost)."""
        omega_cost = float(np.clip(omega_cost, 0.0, 1.0))
        self.current_omega = np.array([omega_cost, 1.0 - omega_cost], dtype=np.float32)
        
    def reset(self, seed=None, options=None):
        obs, info = super().reset(seed=seed, options=options)
        
        # In a dynamic MORL setting, we randomly sample omega at the start of each episode
        # so a single agent learns the entire Pareto front.
        if options and options.get('randomize_omega', True):
            cost_w = self.rng.uniform(0.0, 1.0)
            self.set_preference(cost_w)
            
        morl_obs = np.concatenate([obs, self.current_omega])
        return morl_obs, info

    def step(self, action):
        obs, scalar_reward, terminated, truncated, info = super().step(action)
        
        # Extract individual cost and carbon from info
        # To formulate rewards, we negate the costs (maximization problem)
        # We normalize them roughly so they are on the same magnitude.
        # Cost is usually in tens of thousands, Carbon in hundreds of kg.
        r_cost = -float(info.get('total_daily_cost', 0)) / 10000.0
        r_carbon = -float(info.get('total_carbon', 0)) / 100.0
        
        # Vectorized reward
        vector_reward = np.array([r_cost, r_carbon], dtype=np.float32)
        
        # Append omega to next obs
        morl_obs = np.concatenate([obs, self.current_omega])
        
        return morl_obs, vector_reward, terminated, truncated, info
