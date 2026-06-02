"""Adversarial Minimax RL Trainer (Phase 11).

Trains a MAPPO/PPO defender agent against an AttackerPPOAgent using alternating
gradient descents to prevent mode collapse.
"""

import time
from pathlib import Path

import numpy as np
import torch
from loguru import logger
from torch.utils.tensorboard import SummaryWriter

from supply_chain_research.config import MasterConfig, PPOConfig
from supply_chain_research.phase3_ai.adversarial_env import AdversarialSupplyChainEnv
from supply_chain_research.phase3_ai.attacker_agent import AttackerPPOAgent
from supply_chain_research.phase3_ai.ppo_agent import PPOAgent


class AdversarialTrainer:
    """Trainer for Phase 11 Adversarial Robust RL."""
    def __init__(
        self,
        config=None,
        ppo_config=None,
        run_name=None,
        device="auto",
        output_root: str = ".",
    ):
        self.config = config if config else MasterConfig()
        self.ppo_config = ppo_config if ppo_config else PPOConfig()
        
        # Initialize the adversarial environment (stress mode enabled to match manuscript benchmarks)
        self.env = AdversarialSupplyChainEnv(
            n_customers=self.config.network.n_customers,
            n_warehouses=self.config.network.n_warehouses,
            config=self.config,
            stress_mode=True
        )
        
        self.device = torch.device(
            device if device != "auto" else ('cuda' if torch.cuda.is_available() else 'cpu')
        )
        
        # Defender Agent (Inventory Controller)
        self.defender = PPOAgent(
            obs_dim=self.env.obs_dim,
            action_dim=self.env.action_dim,
            config=self.ppo_config,
            device=self.device,
        )
        
        # Attacker Agent (Shock Injector)
        self.attacker = AttackerPPOAgent(
            obs_dim=self.env.obs_dim,  # Attacker receives the exact same state matrix
            action_dim=self.env.attacker_action_dim,
            config=self.ppo_config,
            device=self.device,
            curriculum_scale=0.0  # Start soft
        )
        
        if run_name is None:
            run_name = f"adversarial_{int(time.time())}"
        self.run_name = run_name
        self.output_root = Path(output_root)
        self.run_dir = self.output_root / "runs" / run_name
        self.save_dir = self.output_root / "models" / run_name
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.save_dir.mkdir(parents=True, exist_ok=True)
        self.writer = SummaryWriter(log_dir=str(self.run_dir))
        
        self.alternating_k_steps = self.ppo_config.steps_per_rollout * 2

    def train(self, total_timesteps=1_000_000):
        """Train both agents in a minimax game."""
        logger.info(f"Starting Adversarial Minimax Training on {self.device}...")
        
        timestep = 0
        episodes = 0
        
        # We track whether we are currently training the defender or the attacker
        training_defender = True
        steps_since_switch = 0
        
        obs, _ = self.env.reset()
        
        while timestep < total_timesteps:
            # Curriculum: ramp up attacker budget linearly over the first 50% of training
            curriculum = min(1.0, timestep / (total_timesteps * 0.5))
            self.attacker.set_curriculum_scale(curriculum)
            
            def_rollout = {'observations': [], 'actions': [], 'rewards': [], 'values': [], 'log_probs': [], 'dones': []}
            att_rollout = {'observations': [], 'actions': [], 'rewards': [], 'values': [], 'log_probs': [], 'dones': []}
            
            episode_rewards = []
            
            rollout_steps = min(
                self.ppo_config.steps_per_rollout,
                total_timesteps - timestep,
            )
            
            for _ in range(rollout_steps):
                # Both agents select actions simultaneously
                def_action, def_val, def_logp = self.defender.select_action(obs)
                att_action, att_val, att_logp = self.attacker.select_action(obs)
                
                # Step the environment
                next_obs, def_reward, term, trunc, info = self.env.step_adversarial(
                    defender_action=def_action, 
                    attacker_action=att_action
                )
                done = term or trunc
                
                # Store rollouts
                def_rollout['observations'].append(obs)
                def_rollout['actions'].append(def_action)
                def_rollout['rewards'].append(def_reward)
                def_rollout['values'].append(def_val)
                def_rollout['log_probs'].append(def_logp)
                def_rollout['dones'].append(float(done))
                
                # Attacker's reward is -defender_reward, but our AttackerPPOAgent's update method
                # handles the negation of rewards and values. We just store the defender's reward.
                att_rollout['observations'].append(obs)
                att_rollout['actions'].append(att_action)
                att_rollout['rewards'].append(def_reward)
                att_rollout['values'].append(att_val)
                att_rollout['log_probs'].append(att_logp)
                att_rollout['dones'].append(float(done))
                
                obs = next_obs
                timestep += 1
                steps_since_switch += 1
                
                if done:
                    episodes += 1
                    episode_rewards.append(info.get('total_daily_cost', 0))
                    obs, _ = self.env.reset()
                    
            # Switch roles if k steps have passed
            if steps_since_switch >= self.alternating_k_steps:
                training_defender = not training_defender
                steps_since_switch = 0
                logger.info(f"Switched role: Now training {'Defender' if training_defender else 'Attacker'}")
                
            # Bootstrap value
            _, def_last_val, _ = self.defender.select_action(obs)
            _, att_last_val, _ = self.attacker.select_action(obs)
            
            # Format and Update
            if training_defender:
                metrics = self.defender.update(
                    {k: np.array(v) for k, v in def_rollout.items()},
                    last_value=float(def_last_val)
                )
                if len(episode_rewards) > 0:
                    mean_cost = np.mean(episode_rewards)
                    self.writer.add_scalar("Train/Defender_MeanCost", mean_cost, timestep)
                    self.writer.add_scalar("Train/Curriculum", curriculum, timestep)
                    logger.info(f"DEF | Step: {timestep} | Cost: {mean_cost:.2f} | Adv: {metrics['mean_advantage']:.4f} | Cur: {curriculum:.2f}")
            else:
                metrics = self.attacker.update(
                    {k: np.array(v) for k, v in att_rollout.items()},
                    last_value=float(att_last_val)
                )
                if len(episode_rewards) > 0:
                    mean_cost = np.mean(episode_rewards)
                    self.writer.add_scalar("Train/Attacker_MeanCost", mean_cost, timestep)
                    self.writer.add_scalar("Train/Curriculum", curriculum, timestep)
                    logger.info(f"ATT | Step: {timestep} | Cost: {mean_cost:.2f} | Adv: {metrics['mean_advantage']:.4f} | Cur: {curriculum:.2f}")

        # Save both models
        self.defender.save(str(self.save_dir / "adversarial_defender.pt"))
        self.attacker.save(str(self.save_dir / "adversarial_attacker.pt"))
        self.writer.close()
        logger.info("Adversarial Minimax Training Completed.")

if __name__ == "__main__":
    trainer = AdversarialTrainer()
    trainer.train(total_timesteps=50_000)
