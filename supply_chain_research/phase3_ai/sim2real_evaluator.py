"""Sim-to-Real Evaluator.

Loads a pre-trained MAPPO agent (trained on synthetic data with Domain Randomization)
and evaluates it zero-shot on the real-world Kaggle M5 dataset.
"""

import os
import torch
import numpy as np
from loguru import logger

from supply_chain_research.config import MasterConfig, PPOConfig
from supply_chain_research.phase3_ai.marl_env import MultiAgentSupplyChainEnv
from supply_chain_research.phase3_ai.mappo_agent import MAPPOAgent
from supply_chain_research.phase3_ai.m5_data_loader import M5DataLoader


class M5Sim2RealEnv(MultiAgentSupplyChainEnv):
    """Wrapper that overrides demand generation with real M5 data."""
    def __init__(self, m5_demand_series, **kwargs):
        super().__init__(**kwargs)
        self.m5_demand_series = m5_demand_series
        self.env.episode_length = len(m5_demand_series)
        
        # Monkey-patch the base environment's demand generator
        self._base_generate = self.env._generate_daily_demand
        self.env._generate_daily_demand = self._m5_generate_daily_demand
        
    def _m5_generate_daily_demand(self):
        """Returns the actual M5 demand for the current timestep."""
        step = self.env.current_step
        if step < len(self.m5_demand_series):
            return self.m5_demand_series[step]
        else:
            return self._base_generate()


def evaluate_sim2real(model_path="models/best_mappo_agent.pt"):
    logger.info("Initializing Sim-to-Real Evaluation...")
    
    # 1. Load Real Data
    loader = M5DataLoader(n_customers=100, n_warehouses=5)
    m5_demand = loader.load_or_simulate()
    
    # 2. Setup Env
    config = MasterConfig()
    ppo_config = PPOConfig()
    
    env = M5Sim2RealEnv(
        m5_demand_series=m5_demand,
        n_customers=config.network.n_customers,
        n_warehouses=config.network.n_warehouses,
        config=config,
    )
    
    # 3. Load Agent
    device = "cuda" if torch.cuda.is_available() else "cpu"
    agent = MAPPOAgent(
        local_obs_dim=env.local_obs_dim,
        global_obs_dim=env.global_obs_dim,
        action_dim=env.action_dim,
        n_agents=env.n_agents,
        config=ppo_config,
        device=device,
    )
    
    if os.path.exists(model_path):
        logger.info(f"Loading trained model from {model_path}")
        agent.load(model_path)
    else:
        logger.warning(f"Model path {model_path} not found! Evaluating an UNTRAINED agent.")
        
    # 4. Rollout
    logger.info(f"Starting zero-shot evaluation on {len(m5_demand)} days of M5 data...")
    local_obs, global_obs, _ = env.reset()
    
    total_costs = []
    service_levels = []
    done = False
    
    while not done:
        # Deterministic evaluation: we could sample the mean of the Beta distribution,
        # but for simplicity we just sample or use the action from get_action.
        actions_dict, _, _ = agent.select_actions(local_obs, global_obs)
        
        local_obs, global_obs, rewards, terminations, truncations, info = env.step(actions_dict)
        done = terminations[0] or truncations[0]
        
        total_costs.append(info.get('total_daily_cost', 0.0))
        service_levels.append(info.get('service_level', 0.0))
        
        if env.env.current_step % 100 == 0:
            logger.info(f"Step {env.env.current_step}/{len(m5_demand)} - Avg Service Level: {np.mean(service_levels):.2f}")

    mean_cost = np.mean(total_costs)
    mean_sl = np.mean(service_levels)
    
    logger.info("===========================================")
    logger.info(" SIM-TO-REAL ZERO-SHOT EVALUATION RESULTS  ")
    logger.info("===========================================")
    logger.info(f" Total Days Simulated : {len(m5_demand)}")
    logger.info(f" Mean Daily Cost (INR): {mean_cost:.2f}")
    logger.info(f" Mean Service Level   : {mean_sl * 100:.2f}%")
    logger.info("===========================================")
    
if __name__ == "__main__":
    # Specify the local model path from your modal run or local run
    evaluate_sim2real("models/best_mappo_agent.pt")
