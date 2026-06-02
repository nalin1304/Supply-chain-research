"""Multi-Objective PPO Agent (Phase 14).

Computes GAE independently for Cost and Carbon objectives, then scalarizes
the advantage using preference weights omega to update a shared policy.
"""

import numpy as np
import torch

from supply_chain_research.config import PPOConfig
from supply_chain_research.phase3_ai.ppo_agent import ActorNetwork, CriticNetwork


class MORLAgent:
    """Multi-Objective PPO Agent."""
    
    def __init__(self, obs_dim, action_dim, config=None, device=None):
        if config is None:
            config = PPOConfig()
        self.config = config
        self.obs_dim = obs_dim
        self.action_dim = action_dim
        
        self.device = torch.device(device if device else ('cuda' if torch.cuda.is_available() else 'cpu'))
        
        # Actor
        self.actor = ActorNetwork(
            obs_dim, action_dim, config.hidden_size, config=config,
        ).to(self.device)
        
        # Critic outputs a 2D value vector: [V_cost, V_carbon]
        self.critic = CriticNetwork(obs_dim, config.hidden_size, output_dim=2).to(self.device)
        
        self.actor_optimizer = torch.optim.Adam(self.actor.parameters(), lr=config.lr)
        self.critic_optimizer = torch.optim.Adam(self.critic.parameters(), lr=config.critic_lr_multiplier * config.lr)
        
    def select_action(self, obs):
        """Select action and evaluate 2D value."""
        obs_tensor = torch.FloatTensor(obs).unsqueeze(0).to(self.device)
        with torch.no_grad():
            action, log_prob = self.actor.get_action(obs_tensor)
            value_vec = self.critic(obs_tensor)  # (1, 2)
            
        action_np = action.squeeze().cpu().numpy()
        log_prob_np = float(log_prob.squeeze().cpu().numpy())
        value_np = value_vec.squeeze().cpu().numpy() # [V_cost, V_carbon]
        
        return action_np, value_np, log_prob_np

    def compute_gae(self, rewards_2d, values_2d, dones, omegas):
        """
        Computes GAE independently for cost and carbon, then scalarizes.
        
        rewards_2d: (T, 2)
        values_2d: (T, 2)
        omegas: (T, 2) - usually constant across a single episode
        """
        gamma = self.config.gamma
        gae_lambda = self.config.gae_lambda
        T = len(rewards_2d)
        
        advantages_2d = np.zeros((T, 2), dtype=np.float32)
        returns_2d = np.zeros((T, 2), dtype=np.float32)
        
        for obj_idx in range(2):
            rewards = rewards_2d[:, obj_idx]
            values = values_2d[:, obj_idx]
            
            next_values = np.empty(T)
            next_values[:-1] = values[1:]
            next_values[-1] = 0.0 # simplified terminal value
            
            non_terminal = 1.0 - dones
            deltas = rewards + gamma * next_values * non_terminal - values
            
            adv = np.empty(T)
            last_gae = 0.0
            decay = gamma * gae_lambda
            for t in range(T - 1, -1, -1):
                last_gae = deltas[t] + decay * non_terminal[t] * last_gae
                adv[t] = last_gae
                
            advantages_2d[:, obj_idx] = adv
            returns_2d[:, obj_idx] = adv + values
            
        # Scalarize the advantages
        scalar_adv = np.sum(advantages_2d * omegas, axis=1)
        
        return scalar_adv, returns_2d

    def update(self, rollout_data):
        """PPO update with vectorized value function loss."""
        obs = torch.FloatTensor(rollout_data['observations']).to(self.device)
        actions = torch.FloatTensor(rollout_data['actions']).to(self.device)
        old_log_probs = torch.FloatTensor(rollout_data['log_probs']).to(self.device)
        
        # Omegas are stored at the end of the observation vector
        omegas_np = rollout_data['observations'][:, -2:]
        
        # Compute GAE
        adv_np, returns_np = self.compute_gae(
            rollout_data['rewards'], # (T, 2)
            rollout_data['values'],  # (T, 2)
            rollout_data['dones'],
            omegas_np
        )
        
        # Normalize scalar advantages
        adv_np = (adv_np - adv_np.mean()) / (adv_np.std() + 1e-8)
        
        adv = torch.FloatTensor(adv_np).to(self.device)
        returns = torch.FloatTensor(returns_np).to(self.device) # (T, 2)
        
        metrics = {'actor_loss': [], 'critic_loss': []}
        
        for _ in range(self.config.n_epochs):
            log_probs, entropy = self.actor.evaluate_actions(obs, actions)
            ratio = torch.exp(log_probs - old_log_probs)
            
            surr1 = ratio * adv
            surr2 = torch.clamp(ratio, 1.0 - self.config.clip_range, 1.0 + self.config.clip_range) * adv
            
            actor_loss = -torch.min(surr1, surr2).mean() - self.config.ent_coef * entropy.mean()
            
            self.actor_optimizer.zero_grad()
            actor_loss.backward()
            torch.nn.utils.clip_grad_norm_(self.actor.parameters(), self.config.max_grad_norm)
            self.actor_optimizer.step()
            
            # Critic loss (MSE over both objectives)
            v_pred = self.critic(obs) # (T, 2)
            critic_loss = torch.nn.functional.mse_loss(v_pred, returns)
            
            self.critic_optimizer.zero_grad()
            critic_loss.backward()
            torch.nn.utils.clip_grad_norm_(self.critic.parameters(), self.config.max_grad_norm)
            self.critic_optimizer.step()
            
            metrics['actor_loss'].append(actor_loss.item())
            metrics['critic_loss'].append(critic_loss.item())
            
        return {
            'actor_loss': np.mean(metrics['actor_loss']),
            'critic_loss': np.mean(metrics['critic_loss']),
            'mean_advantage': adv_np.mean()
        }

    def save(self, path):
        torch.save({
            'actor': self.actor.state_dict(),
            'critic': self.critic.state_dict(),
        }, path)

    def load(self, path):
        checkpoint = torch.load(path, map_location=self.device)
        self.actor.load_state_dict(checkpoint['actor'])
        self.critic.load_state_dict(checkpoint['critic'])
