"""DRL training loop for PPO agent in supply chain environment.

Handles rollout collection, policy updates, TensorBoard logging,
checkpoint saving, and periodic evaluation.
"""

import os
import time

import numpy as np
import torch
from torch.utils.tensorboard import SummaryWriter

from supply_chain_research.config import PPOConfig
from supply_chain_research.phase3_ai.gym_environment import (
    SupplyChainEnv,
)
from supply_chain_research.phase3_ai.ppo_agent import PPOAgent


class DRLTrainer:
    """Training loop for PPO agent in SupplyChainEnv.

    Collects rollouts, performs PPO updates, logs to TensorBoard,
    saves checkpoints, and runs evaluation episodes.

    Parameters
    ----------
    config : PPOConfig, optional
        PPO hyperparameter configuration. Defaults to a fresh
        :class:`PPOConfig`.
    log_dir : str, optional
        Directory for TensorBoard logs.
    checkpoint_dir : str, optional
        Directory where model checkpoints are written.
    env_kwargs : dict, optional
        Extra keyword arguments forwarded to
        :class:`SupplyChainEnv`.

    Attributes
    ----------
    config : PPOConfig
        Active PPO configuration.
    log_dir, checkpoint_dir : str
        Stored output paths.
    env : SupplyChainEnv
        Hosting Gymnasium environment.
    agent : PPOAgent
        Wrapped PPO agent driving the rollouts.
    total_timesteps, episodes_completed, update_count : int
        Cumulative training counters.
    episode_rewards : list of float
        Per-episode reward history.
    """

    def __init__(self, config=None, log_dir='data/results/runs',
                 checkpoint_dir='data/results/checkpoints',
                 env_kwargs=None):
        """Initialize DRL trainer.

        Args:
            config: PPOConfig instance.
            log_dir: Directory for TensorBoard logs.
            checkpoint_dir: Directory for model checkpoints.
            env_kwargs: Optional kwargs for SupplyChainEnv.
        
        Parameters
        ----------
        """
        if config is None:
            config = PPOConfig()
        self.config = config
        self.log_dir = log_dir
        self.checkpoint_dir = checkpoint_dir

        # Create environment
        if env_kwargs is None:
            env_kwargs = {}
        self.env = SupplyChainEnv(**env_kwargs)

        # Create agent
        obs_dim = self.env.observation_space.shape[0]
        action_dim = self.env.action_space.shape[0]
        self.agent = PPOAgent(obs_dim, action_dim, config)

        # Training state
        self.total_timesteps = 0
        self.episodes_completed = 0
        self.episode_rewards = []
        self.update_count = 0

    def train(self, total_timesteps=None, eval_interval=50000):
        """Run the full training loop.

        Args:
            total_timesteps: Total environment steps. Uses config
                value if None.
            eval_interval: Steps between evaluation episodes.

        Returns:
            Dictionary with training results.
        
        Parameters
        ----------
        """
        if total_timesteps is None:
            total_timesteps = self.config.total_timesteps

        os.makedirs(self.log_dir, exist_ok=True)
        os.makedirs(self.checkpoint_dir, exist_ok=True)

        writer = SummaryWriter(self.log_dir)
        start_time = time.time()

        obs, _ = self.env.reset()
        episode_reward = 0.0
        episode_length = 0

        while self.total_timesteps < total_timesteps:
            # Collect rollout
            self.agent.buffer.clear()

            for _ in range(self.config.steps_per_rollout):
                action, value, log_prob = (
                    self.agent.select_action(obs)
                )

                next_obs, reward, terminated, truncated, info = (
                    self.env.step(action)
                )
                done = terminated or truncated

                self.agent.buffer.add(
                    obs, action, reward, value, log_prob,
                    float(terminated)  # Only true termination zeros GAE bootstrap, not truncation
                )

                obs = next_obs
                episode_reward += reward
                episode_length += 1
                self.total_timesteps += 1

                if done:
                    self.episode_rewards.append(episode_reward)
                    self.episodes_completed += 1

                    writer.add_scalar(
                        'train/episode_reward',
                        episode_reward,
                        self.total_timesteps,
                    )
                    writer.add_scalar(
                        'train/episode_length',
                        episode_length,
                        self.total_timesteps,
                    )

                    obs, _ = self.env.reset()
                    episode_reward = 0.0
                    episode_length = 0

                if self.total_timesteps >= total_timesteps:
                    break

            # Compute last value for GAE
            with torch.no_grad():
                obs_tensor = torch.FloatTensor(obs).unsqueeze(0).to(
                    self.agent.device
                )
                last_value = (
                    self.agent.critic(obs_tensor)
                    .squeeze().cpu().numpy()
                )

            # PPO update
            rollout_data = self.agent.buffer.get()
            metrics = self.agent.update(
                rollout_data, float(last_value)
            )
            self.update_count += 1

            # Log metrics
            writer.add_scalar(
                'train/actor_loss',
                metrics['actor_loss'],
                self.total_timesteps,
            )
            writer.add_scalar(
                'train/critic_loss',
                metrics['critic_loss'],
                self.total_timesteps,
            )
            writer.add_scalar(
                'train/mean_return',
                metrics['mean_return'],
                self.total_timesteps,
            )

            # Evaluation
            if (self.total_timesteps % eval_interval
                    < self.config.steps_per_rollout):
                eval_reward = self.evaluate(n_episodes=3)
                writer.add_scalar(
                    'eval/mean_reward',
                    eval_reward,
                    self.total_timesteps,
                )

                # Save checkpoint
                ckpt_path = os.path.join(
                    self.checkpoint_dir,
                    f'ppo_step_{self.total_timesteps}.pt',
                )
                self.agent.save(ckpt_path)

        # Final save
        final_path = os.path.join(
            self.checkpoint_dir, 'ppo_final.pt'
        )
        self.agent.save(final_path)
        writer.close()

        elapsed = time.time() - start_time
        return {
            'total_timesteps': self.total_timesteps,
            'episodes_completed': self.episodes_completed,
            'mean_episode_reward': float(
                np.mean(self.episode_rewards[-100:])
            ) if self.episode_rewards else 0.0,
            'updates': self.update_count,
            'elapsed_seconds': elapsed,
        }

    def evaluate(self, n_episodes=5):
        """Run evaluation episodes.

        Args:
            n_episodes: Number of evaluation episodes.

        Returns:
            Mean episode reward.
        
        Parameters
        ----------
        """
        eval_env = SupplyChainEnv(
            n_customers=self.env.n_customers,
            n_warehouses=self.env.n_warehouses,
            episode_length=self.env.episode_length,
        )

        rewards = []
        for ep in range(n_episodes):
            obs, _ = eval_env.reset(seed=1000 + ep)
            ep_reward = 0.0
            done = False

            while not done:
                action, _, _ = self.agent.select_action(obs)
                obs, reward, terminated, truncated, _ = (
                    eval_env.step(action)
                )
                ep_reward += reward
                done = terminated or truncated

            rewards.append(ep_reward)

        return float(np.mean(rewards))
