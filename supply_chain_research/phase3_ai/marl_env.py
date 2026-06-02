"""Multi-Agent Wrapper for the Supply Chain Environment.

Converts the centralized Gymnasium environment into a decentralized 
Multi-Agent environment suitable for MAPPO (Multi-Agent PPO).
Each warehouse is treated as an independent cooperative agent.
"""

import numpy as np

from supply_chain_research.phase3_ai.gym_environment import SupplyChainEnv


class MultiAgentSupplyChainEnv:
    """Wrapper to convert SupplyChainEnv into a Multi-Agent Environment.
    
    Agents: N warehouses.
    Reward: Cooperative (all agents receive the same global reward).
    Observation:
        - Local: Agent's own inventory, own shock, global forecasts, time.
        - Global: Full state matrix (for centralized critic).
    Action: Each agent outputs a scalar order quantity [0, 1].
    
    Parameters
    ----------
    """
    
    def __init__(self, **kwargs):
        # Force stress_mode=True for multi-agent (per-warehouse scalar action)
        """
        Parameters
        ----------
        """
        kwargs['stress_mode'] = True
        self.env = SupplyChainEnv(**kwargs)
        
        self.n_agents = self.env.n_warehouses
        
        # Dimensions
        self.global_obs_dim = self.env.obs_dim
        # Local obs: 1 (own inv) + 700 (forecasts) + 1 (own shock) + 100 (cust shocks) + 1 (time)
        self.local_obs_dim = 1 + self.env.n_forecast + 1 + self.env.n_customer_shocks + 1
        
        self.action_dim = 1  # Each agent outputs 1 continuous value

    def reset(self, seed=None):
        """
        Parameters
        ----------
        """
        global_obs, info = self.env.reset(seed=seed)
        local_obs = self._get_local_observations(global_obs)
        return local_obs, global_obs, info

    def step(self, actions_dict):
        """
        actions_dict: dict of {agent_id: action_scalar}
        
        Parameters
        ----------
        """
        # Reconstruct centralized action array
        centralized_action = np.zeros(self.n_agents, dtype=np.float32)
        for i in range(self.n_agents):
            centralized_action[i] = float(np.asarray(actions_dict[i]).reshape(-1)[0])
            
        global_obs, reward, terminated, truncated, info = self.env.step(centralized_action)
        
        local_obs = self._get_local_observations(global_obs)
        
        # In a fully cooperative setting, all agents get the same reward and done flags
        rewards = {i: reward for i in range(self.n_agents)}
        terminations = {i: terminated for i in range(self.n_agents)}
        truncations = {i: truncated for i in range(self.n_agents)}
        
        return local_obs, global_obs, rewards, terminations, truncations, info

    def _get_local_observations(self, global_obs):
        """Extract local observations for each agent from the global state.
        Parameters
        ----------
        """
        local_obs_dict = {}
        
        inv_slice = self.env._inv_slice
        forecast_slice = self.env._forecast_slice
        wh_shock_slice = self.env._wh_shock_slice
        cust_shock_slice = self.env._cust_shock_slice
        time_idx = self.env._time_idx
        
        inventories = global_obs[inv_slice]
        forecasts = global_obs[forecast_slice]
        wh_shocks = global_obs[wh_shock_slice]
        cust_shocks = global_obs[cust_shock_slice]
        time_val = np.array([global_obs[time_idx]])
        
        for i in range(self.n_agents):
            local_obs = np.concatenate([
                np.array([inventories[i]]),
                forecasts,
                np.array([wh_shocks[i]]),
                cust_shocks,
                time_val
            ]).astype(np.float32)
            local_obs_dict[i] = local_obs
            
        return local_obs_dict
