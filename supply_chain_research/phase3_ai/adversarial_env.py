import numpy as np
from gymnasium import spaces

from supply_chain_research.phase3_ai.gym_environment import SupplyChainEnv


class AdversarialSupplyChainEnv(SupplyChainEnv):
    """Adversarial Supply Chain Environment for Phase 11.
    
    Takes two actions per step:
    1. Defender Action: Inventory control allocation.
    2. Attacker Action: [lead_time_multiplier, demand_spike, capacity_reduction]
    
    The attacker action space is continuous [0, 1] of size 3.
    """

    def __init__(self, n_customers=100, n_warehouses=5, episode_length=365,
                 seed=None, warehouse_capacities=None, config=None, stress_mode=False):
        super().__init__(
            n_customers=n_customers,
            n_warehouses=n_warehouses,
            episode_length=episode_length,
            seed=seed,
            warehouse_capacities=warehouse_capacities,
            config=config,
            stress_mode=stress_mode
        )
        
        # Attacker action: [lead_time_multiplier, demand_spike, capacity_reduction]
        self.attacker_action_dim = 3
        self.attacker_action_space = spaces.Box(
            low=0.0, high=1.0,
            shape=(self.attacker_action_dim,), dtype=np.float32
        )
        
        # Store base values for perturbation
        self._base_lead_time_days = getattr(self.config.gym_env, 'lead_time_days', 3)
        if hasattr(self, '_lead_time_days'):
            self._base_lead_time_days = self._lead_time_days
        self._base_warehouse_capacities = self.warehouse_capacities.copy()
        
        # We will hold current attacker multipliers here to be applied in the environment
        self._current_demand_spike = 1.0

    def step_adversarial(self, defender_action, attacker_action):
        """Perform a single step taking both defender and attacker actions.
        
        Parameters
        ----------
        defender_action : np.ndarray
            Action vector from the defender policy.
        attacker_action : np.ndarray
            Action vector from the attacker policy in [0, 1].
            
        Returns
        -------
        obs : np.ndarray
            Next observation.
        defender_reward : float
            Defender's reward (Attacker's reward is -defender_reward).
        terminated : bool
            Early termination flag.
        truncated : bool
            Time limit truncation flag.
        info : dict
            Diagnostic information.
        """
        if attacker_action is not None:
            attacker_action = np.clip(attacker_action, 0.0, 1.0)
            
            # Map [0, 1] actions to physical bounds (to prevent trivial impossible states)
            # lead_time_multiplier: [1.0, 3.0] -> up to 3x lead time
            lead_time_mult = 1.0 + 2.0 * attacker_action[0]
            
            # demand_spike: [1.0, 2.5] -> up to 2.5x demand spike
            self._current_demand_spike = 1.0 + 1.5 * attacker_action[1]
            
            # capacity_reduction: [0.1, 1.0] -> down to 10% capacity
            cap_mult = 1.0 - 0.9 * attacker_action[2]
            
            # Apply to environment state
            self._lead_time_days = max(1, int(self._base_lead_time_days * lead_time_mult))
            self.warehouse_capacities = self._base_warehouse_capacities * cap_mult
        else:
            self._lead_time_days = self._base_lead_time_days
            self.warehouse_capacities = self._base_warehouse_capacities
            self._current_demand_spike = 1.0
            
        # Step the environment
        # Note: the demand generation will use _generate_daily_demand which we override below
        obs, reward, terminated, truncated, info = self.step(defender_action)
        
        return obs, float(reward), terminated, truncated, info

    def _generate_daily_demand(self):
        """Override to apply the attacker's demand spike multiplier globally."""
        base_demand = super()._generate_daily_demand()
        # Apply the adversarial global demand spike
        return base_demand * self._current_demand_spike
