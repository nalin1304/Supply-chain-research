"""MAPPO Trainer.

Trains the MAPPO Agent in the Multi-Agent Supply Chain environment.
"""

import os
import time
import numpy as np
import torch
from loguru import logger
from torch.utils.tensorboard import SummaryWriter

from supply_chain_research.config import MasterConfig, PPOConfig
from supply_chain_research.phase3_ai.marl_env import MultiAgentSupplyChainEnv
from supply_chain_research.phase3_ai.mappo_agent import MAPPOAgent


class MAPPOTrainer:
    def __init__(self, config=None, ppo_config=None, run_name=None, device="auto"):
        self.config = config if config else MasterConfig()
        self.ppo_config = ppo_config if ppo_config else PPOConfig()
        
        self.env = MultiAgentSupplyChainEnv(
            n_customers=self.config.network.n_customers,
            n_warehouses=self.config.network.n_warehouses,
            config=self.config,
        )
        
        self.agent = MAPPOAgent(
            local_obs_dim=self.env.local_obs_dim,
            global_obs_dim=self.env.global_obs_dim,
            action_dim=self.env.action_dim,
            n_agents=self.env.n_agents,
            config=self.ppo_config,
            device=device,
        )
        
        if run_name is None:
            run_name = f"mappo_{int(time.time())}"
        self.run_name = run_name
        self.writer = SummaryWriter(log_dir=f"runs/{run_name}")
        self.save_dir = f"models/{run_name}"
        os.makedirs(self.save_dir, exist_ok=True)
        
    def train(self, total_timesteps=1_000_000):
        logger.info(f"Starting MAPPO training on {self.agent.device}...")
        
        timestep = 0
        episodes = 0
        best_reward = -float("inf")
        
        local_obs, global_obs, _ = self.env.reset()
        
        while timestep < total_timesteps:
            # Collect Rollout
            rollout_data = {
                'local_obs': [], 'global_obs': [], 'actions': [],
                'rewards': [], 'values': [], 'log_probs': [], 'dones': []
            }
            
            episode_rewards = []
            
            for _ in range(self.ppo_config.steps_per_rollout):
                actions_dict, value, log_probs_dict = self.agent.select_actions(local_obs, global_obs)
                
                next_local_obs, next_global_obs, rewards, terminations, truncations, info = self.env.step(actions_dict)
                
                # In cooperative env, reward is the same for all, we just use one
                global_reward = rewards[0]
                done = terminations[0] or truncations[0]
                
                # Store
                # For actor, we flatten the local states of all agents
                local_obs_flat = np.array([local_obs[i] for i in range(self.env.n_agents)])
                actions_flat = np.array([actions_dict[i] for i in range(self.env.n_agents)])
                log_probs_flat = np.array([log_probs_dict[i] for i in range(self.env.n_agents)])
                
                rollout_data['local_obs'].append(local_obs_flat)
                rollout_data['global_obs'].append(global_obs)
                rollout_data['actions'].append(actions_flat)
                rollout_data['rewards'].append(global_reward)
                rollout_data['values'].append(value)
                rollout_data['log_probs'].append(log_probs_flat)
                rollout_data['dones'].append(float(done))
                
                local_obs = next_local_obs
                global_obs = next_global_obs
                timestep += 1
                
                if done:
                    episodes += 1
                    episode_rewards.append(info.get('total_daily_cost', 0))
                    local_obs, global_obs, _ = self.env.reset()
            
            # Bootstrap value for GAE
            _, last_value, _ = self.agent.select_actions(local_obs, global_obs)
            
            # Format Rollout Data
            formatted_data = {
                'local_obs': np.concatenate(rollout_data['local_obs']),  # (T*N, dim)
                'global_obs': np.array(rollout_data['global_obs']),      # (T, dim)
                'actions': np.concatenate(rollout_data['actions']),      # (T*N, dim)
                'rewards': np.array(rollout_data['rewards']),            # (T,)
                'values': np.array(rollout_data['values']),              # (T,)
                'log_probs': np.concatenate(rollout_data['log_probs']),  # (T*N,)
                'dones': np.array(rollout_data['dones']),                # (T,)
            }
            
            # Update MAPPO Agent
            update_metrics = self.agent.update(formatted_data, last_value=last_value)
            
            # Logging
            if len(episode_rewards) > 0:
                mean_cost = np.mean(episode_rewards)
                self.writer.add_scalar("Train/MeanCost", mean_cost, timestep)
                logger.info(f"Steps: {timestep} | Episodes: {episodes} | Mean Cost (INR): {mean_cost:.2f} | Adv: {update_metrics['mean_advantage']:.4f}")
                
                # Save best model
                # We want to minimize cost, so reward is negative cost. 
                # Mean cost lower is better.
                if -mean_cost > best_reward:
                    best_reward = -mean_cost
                    self.agent.save(f"{self.save_dir}/best_mappo_agent.pt")
                    logger.info("New best model saved!")

        self.agent.save(f"{self.save_dir}/final_mappo_agent.pt")
        self.writer.close()
        logger.info("MAPPO Training Completed.")

if __name__ == "__main__":
    trainer = MAPPOTrainer()
    trainer.train(total_timesteps=100_000)  # Short test run
