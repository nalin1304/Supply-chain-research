"""Domain Randomization Wrapper for the Supply Chain Environment.

Randomizes core environment dynamics (costs, lead times, capacities) 
at the start of each episode to train a highly robust policy capable of 
Sim-to-Real transfer.
"""

import numpy as np
import gymnasium as gym
from loguru import logger

class DomainRandomizationWrapper(gym.Wrapper):
    """Randomizes environment parameters on every reset."""
    
    def __init__(self, env, randomization_scale=0.2, seed=None):
        """
        Args:
            env: The underlying environment (e.g. MultiAgentSupplyChainEnv or SupplyChainEnv)
            randomization_scale: Float [0, 1]. The maximum percentage deviation from nominal.
                e.g., 0.2 means +/- 20%.
        """
        super().__init__(env)
        self.randomization_scale = randomization_scale
        self.rng = np.random.default_rng(seed)
        
        # Access the base SupplyChainEnv (handling potential nested wrappers)
        base_env = env
        while hasattr(base_env, "env") and not hasattr(base_env, "_lead_time_days"):
            base_env = base_env.env
        self.base_env = base_env
        
        # Store nominal (original) values
        self.nominal_lead_time = self.base_env._lead_time_days
        self.nominal_holding_cost = self.base_env._holding_cost_per_kg
        self.nominal_stockout_cost = self.base_env._stockout_cost_per_kg
        self.nominal_capacities = self.base_env.warehouse_capacities.copy()
        
    def reset(self, **kwargs):
        # Apply domain randomization before resetting the base env
        scale = self.randomization_scale
        
        # 1. Randomize Lead Time (discrete)
        # Lead time is typically 3 days. Randomize between nominal-1 and nominal+1.
        lt_shift = self.rng.integers(-1, 2)  # -1, 0, or 1
        self.base_env._lead_time_days = max(1, self.nominal_lead_time + lt_shift)
        
        # 2. Randomize Costs (continuous +/- scale)
        holding_factor = self.rng.uniform(1.0 - scale, 1.0 + scale)
        self.base_env._holding_cost_per_kg = self.nominal_holding_cost * holding_factor
        
        stockout_factor = self.rng.uniform(1.0 - scale, 1.0 + scale)
        self.base_env._stockout_cost_per_kg = self.nominal_stockout_cost * stockout_factor
        
        # 3. Randomize Physical Capacities
        cap_factors = self.rng.uniform(1.0 - scale, 1.0 + scale, size=self.base_env.n_warehouses)
        self.base_env.warehouse_capacities = self.nominal_capacities * cap_factors
        
        # Reset the underlying environment which will now use the new parameters
        return self.env.reset(**kwargs)
