"""MAPPO Trainer.

Trains the MAPPO Agent in the Multi-Agent Supply Chain environment.
"""

import time
from pathlib import Path

import numpy as np
from loguru import logger
from torch.utils.tensorboard import SummaryWriter

from supply_chain_research.config import MasterConfig, PPOConfig
from supply_chain_research.phase3_ai.dr_env_wrapper import DomainRandomizationConfig
from supply_chain_research.phase3_ai.mappo_agent import MAPPOAgent
from supply_chain_research.phase3_ai.marl_env import MultiAgentSupplyChainEnv


class MAPPOTrainer:
    """
    Parameters
    ----------
    """
    def __init__(
        self,
        config=None,
        ppo_config=None,
        run_name=None,
        device="auto",
        output_root: str = ".",
        domain_randomization: bool = True,
        randomization_config: DomainRandomizationConfig | None = None,
    ):
        """
        Parameters
        ----------
        """
        self.config = config if config else MasterConfig()
        self.ppo_config = ppo_config if ppo_config else PPOConfig()
        
        self.env = MultiAgentSupplyChainEnv(
            n_customers=self.config.network.n_customers,
            n_warehouses=self.config.network.n_warehouses,
            config=self.config,
        )
        self.domain_randomization = bool(domain_randomization)
        self.randomization_config = randomization_config or DomainRandomizationConfig()
        base_env = self.env.env
        self._nominal_dr = {
            "lead_time": base_env._lead_time_days,
            "holding_cost": base_env._holding_cost_per_kg,
            "stockout_cost": base_env._stockout_cost_per_kg,
            "capacities": base_env.warehouse_capacities.copy(),
            "demand_min": base_env.config.gym_env.demand_min,
            "demand_max": base_env.config.gym_env.demand_max,
        }
        self._dr_rng = np.random.default_rng(self.config.random_seed)
        
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
        self.output_root = Path(output_root)
        self.run_dir = self.output_root / "runs" / run_name
        self.save_dir = self.output_root / "models" / run_name
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.save_dir.mkdir(parents=True, exist_ok=True)
        self.writer = SummaryWriter(log_dir=str(self.run_dir))

    def _apply_domain_randomization(self) -> None:
        """
        Parameters
        ----------
        """
        cfg = self.randomization_config
        base_env = self.env.env
        base_env._lead_time_days = int(
            self._dr_rng.integers(cfg.lead_time_min, cfg.lead_time_max + 1)
        )
        holding_factor = self._dr_rng.uniform(1.0 - cfg.cost_scale, 1.0 + cfg.cost_scale)
        stockout_factor = self._dr_rng.uniform(1.0 - cfg.cost_scale, 1.0 + cfg.cost_scale)
        capacity_factors = self._dr_rng.uniform(
            1.0 - cfg.capacity_scale,
            1.0 + cfg.capacity_scale,
            size=base_env.n_warehouses,
        )
        demand_factor = self._dr_rng.uniform(
            1.0 - cfg.demand_scale,
            1.0 + cfg.demand_scale,
        )
        base_env._holding_cost_per_kg = self._nominal_dr["holding_cost"] * holding_factor
        base_env._stockout_cost_per_kg = self._nominal_dr["stockout_cost"] * stockout_factor
        base_env.warehouse_capacities = self._nominal_dr["capacities"] * capacity_factors
        base_env.config.gym_env.demand_min = self._nominal_dr["demand_min"] * demand_factor
        base_env.config.gym_env.demand_max = self._nominal_dr["demand_max"] * demand_factor

    def _reset_env(self, seed=None):
        """
        Parameters
        ----------
        """
        if self.domain_randomization:
            self._apply_domain_randomization()
        return self.env.reset(seed=seed)
        
    def train(self, total_timesteps=1_000_000):
        """
        Parameters
        ----------
        """
        logger.info(f"Starting MAPPO training on {self.agent.device}...")
        
        timestep = 0
        episodes = 0
        best_reward = -float("inf")
        
        local_obs, global_obs, _ = self._reset_env()
        
        while timestep < total_timesteps:
            # Collect Rollout
            rollout_data = {
                'local_obs': [], 'global_obs': [], 'actions': [],
                'rewards': [], 'values': [], 'log_probs': [], 'dones': []
            }
            
            episode_rewards = []
            
            rollout_steps = min(
                self.ppo_config.steps_per_rollout,
                total_timesteps - timestep,
            )
            for _ in range(rollout_steps):
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
                    local_obs, global_obs, _ = self._reset_env()
            
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
                    self.agent.save(str(self.save_dir / "best_mappo_agent.pt"))
                    logger.info("New best model saved!")

        self.agent.save(str(self.save_dir / "final_mappo_agent.pt"))
        self.writer.close()
        logger.info("MAPPO Training Completed.")

if __name__ == "__main__":
    trainer = MAPPOTrainer()
    trainer.train(total_timesteps=100_000)  # Short test run
