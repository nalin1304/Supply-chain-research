"""Sim-to-Real Evaluator.

Loads a pre-trained MAPPO agent (trained on synthetic data with Domain Randomization)
and evaluates it zero-shot on the real-world Kaggle M5 dataset.
"""

import os

import numpy as np
import torch
from loguru import logger

from supply_chain_research.config import MasterConfig, PPOConfig
from supply_chain_research.phase3_ai.m5_data_loader import M5DataLoader
from supply_chain_research.phase3_ai.mappo_agent import MAPPOAgent
from supply_chain_research.phase3_ai.marl_env import MultiAgentSupplyChainEnv


class M5Sim2RealEnv(MultiAgentSupplyChainEnv):
    """Wrapper that overrides demand generation with real M5 data.
    Parameters
    ----------
    """
    def __init__(self, m5_demand_series, **kwargs):
        """
        Parameters
        ----------
        """
        super().__init__(**kwargs)
        self.m5_demand_series = m5_demand_series
        self.env.episode_length = len(m5_demand_series)
        
        # Monkey-patch the base environment's demand generator
        self._base_generate = self.env._generate_daily_demand
        self.env._generate_daily_demand = self._m5_generate_daily_demand
        
    def _m5_generate_daily_demand(self):
        """Returns the actual M5 demand for the current timestep.
        Parameters
        ----------
        """
        step = self.env.current_step
        if step < len(self.m5_demand_series):
            return self.m5_demand_series[step]
        else:
            return self._base_generate()


def evaluate_sim2real(
    model_path="models/best_mappo_agent.pt",
    data_dir="data/m5",
    n_customers=100,
    n_warehouses=5,
    seed=42,
    max_days=None,
):
    """
    Parameters
    ----------
    """
    logger.info("Initializing Sim-to-Real Evaluation...")
    
    # 1. Load Real Data
    loader = M5DataLoader(
        data_dir=data_dir,
        n_customers=n_customers,
        n_warehouses=n_warehouses,
        seed=seed,
    )
    m5_demand = loader.load_or_simulate()
    if max_days is not None:
        m5_demand = m5_demand[: int(max_days)]
    
    # 2. Setup Env
    config = MasterConfig.derive_from_problem_size(n_customers, n_warehouses)
    config.gym_env.episode_length = len(m5_demand)
    config.simulation.sim_days = len(m5_demand)
    ppo_config = PPOConfig()
    
    env = M5Sim2RealEnv(
        m5_demand_series=m5_demand,
        n_customers=n_customers,
        n_warehouses=n_warehouses,
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
    
    model_loaded = os.path.exists(model_path)
    if model_loaded:
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

    mean_cost = float(np.mean(total_costs))
    mean_sl = float(np.clip(np.mean(service_levels), 0.0, 1.0))
    p10_sl = float(np.clip(np.percentile(service_levels, 10), 0.0, 1.0))
    
    logger.info("===========================================")
    logger.info(" SIM-TO-REAL ZERO-SHOT EVALUATION RESULTS  ")
    logger.info("===========================================")
    logger.info(f" Total Days Simulated : {len(m5_demand)}")
    logger.info(f" Mean Daily Cost (INR): {mean_cost:.2f}")
    logger.info(f" Mean Service Level   : {mean_sl * 100:.2f}%")
    logger.info("===========================================")
    return {
        "model_loaded": model_loaded,
        "synthetic_data": bool(loader.used_synthetic),
        "n_customers": int(n_customers),
        "n_warehouses": int(n_warehouses),
        "days": int(len(m5_demand)),
        "mean_daily_cost": mean_cost,
        "mean_service_level": mean_sl,
        "p10_service_level": p10_sl,
    }

def evaluate_robustness(
    standard_model_path="models/best_mappo_agent.pt",
    adversarial_model_path="models/adversarial_defender.pt",
    n_customers=100,
    n_warehouses=5,
    seed=42,
    episodes=10,
):
    """Phase 11: Evaluate standard vs adversarial policies under hostile shocks.
    
    Loads both agents and subjects them to deterministic shock profiles.
    Returns metrics on cost standard deviation.
    """
    logger.info("Initializing Robustness Evaluation...")
    
    from supply_chain_research.phase3_ai.adversarial_env import (
        AdversarialSupplyChainEnv,
    )
    from supply_chain_research.phase3_ai.ppo_agent import PPOAgent
    
    config = MasterConfig.derive_from_problem_size(n_customers, n_warehouses)
    ppo_config = PPOConfig()
    
    device = "cuda" if torch.cuda.is_available() else "cpu"
    
    # Standard Agent (Assuming PPOAgent for apples-to-apples, or MAPPO)
    env = AdversarialSupplyChainEnv(
        n_customers=n_customers, n_warehouses=n_warehouses, 
        config=config, stress_mode=True, seed=seed
    )
    
    std_agent = PPOAgent(
        obs_dim=env.obs_dim, action_dim=env.action_dim, config=ppo_config, device=device
    )
    if os.path.exists(standard_model_path):
        std_agent.load(standard_model_path)
        
    adv_agent = PPOAgent(
        obs_dim=env.obs_dim, action_dim=env.action_dim, config=ppo_config, device=device
    )
    if os.path.exists(adversarial_model_path):
        adv_agent.load(adversarial_model_path)
        
    # We test on increasingly hostile deterministic shock scenarios
    # Shock vector: [lead_time_mult, demand_spike, capacity_reduction]
    shock_scenarios = [
        ("Mild", np.array([0.0, 0.0, 0.0], dtype=np.float32)),
        ("Moderate", np.array([0.5, 0.5, 0.5], dtype=np.float32)),
        ("Severe", np.array([1.0, 1.0, 1.0], dtype=np.float32)),
    ]
    
    results = {}
    
    for scenario_name, attacker_action in shock_scenarios:
        for agent_name, agent in [("Standard", std_agent), ("Adversarial", adv_agent)]:
            costs = []
            obs, _ = env.reset(seed=seed)
            done = False
            while not done:
                action, _, _ = agent.select_action(obs)
                obs, reward, term, trunc, info = env.step_adversarial(
                    defender_action=action, attacker_action=attacker_action
                )
                done = term or trunc
                costs.append(info.get('total_daily_cost', 0.0))
            
            key = f"{agent_name}_{scenario_name}"
            results[key] = {
                "mean_cost": np.mean(costs),
                "std_cost": np.std(costs)
            }
            logger.info(f"[{scenario_name}] {agent_name} Agent - Cost: {results[key]['mean_cost']:.2f} ± {results[key]['std_cost']:.2f}")
            
    return results

    
if __name__ == "__main__":
    # Specify the local model path from your modal run or local run
    evaluate_sim2real("models/best_mappo_agent.pt")
