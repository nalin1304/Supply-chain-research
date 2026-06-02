"""Multi-Agent PPO (MAPPO) with Parameter Sharing.

Implements Centralized Training with Decentralized Execution (CTDE).
- Shared Actor Network: Takes local observation -> outputs local action.
- Shared Centralized Critic: Takes global observation -> outputs global state value.

References:
    - Yu et al. (2021). The Surprising Effectiveness of PPO in Cooperative MARL.
"""

from pathlib import Path

import numpy as np
import torch
import torch.nn as nn

from supply_chain_research.config import PPOConfig
from supply_chain_research.phase3_ai.ppo_agent import (
    ActorNetwork,
    CriticNetwork,
    RolloutBuffer,
)


class MAPPOAgent:
    """Multi-Agent PPO Agent with parameter sharing.
    
    All agents share the same actor and critic networks.
    
    Parameters
    ----------
    """
    
    def __init__(self, local_obs_dim, global_obs_dim, action_dim, n_agents, config=None, device=None):
        """
        Parameters
        ----------
        """
        if config is None:
            config = PPOConfig()
        self.config = config
        self.local_obs_dim = local_obs_dim
        self.global_obs_dim = global_obs_dim
        self.action_dim = action_dim  # usually 1 per agent
        self.n_agents = n_agents
        
        self.device = torch.device(device if device else ('cuda' if torch.cuda.is_available() else 'cpu'))
        
        # Decentralized Actor (sees local obs)
        self.actor = ActorNetwork(
            local_obs_dim, action_dim, config.hidden_size, config=config,
        ).to(self.device)
        
        # Centralized Critic (sees global obs)
        self.critic = CriticNetwork(global_obs_dim, config.hidden_size).to(self.device)
        
        self.actor_lr = config.lr
        self.critic_lr = config.critic_lr_multiplier * config.lr
        self.actor_optimizer = torch.optim.Adam(self.actor.parameters(), lr=self.actor_lr)
        self.critic_optimizer = torch.optim.Adam(self.critic.parameters(), lr=self.critic_lr)
        
        # We store transitions per agent (unrolled across time and agents)
        self.buffer = RolloutBuffer()
        
        self.vf_coef = config.vf_coef
        self.ent_coef = config.ent_coef
        self.minibatch_size = max(
            config.minibatch_size_min,
            (config.steps_per_rollout * n_agents) // config.minibatch_count,
        )

    def select_actions(self, local_obs_dict, global_obs):
        """Select actions for all agents.
        
        Returns:
            actions_dict: {agent_id: action}
            value: float (global state value)
            log_probs_dict: {agent_id: log_prob}
        
        Parameters
        ----------
        """
        # Batch all local observations to pass through actor once
        local_obs_batch = np.array([local_obs_dict[i] for i in range(self.n_agents)])
        local_obs_tensor = torch.FloatTensor(local_obs_batch).to(self.device)
        
        global_obs_tensor = torch.FloatTensor(global_obs).unsqueeze(0).to(self.device)
        
        with torch.no_grad():
            actions, log_probs = self.actor.get_action(local_obs_tensor)
            value = self.critic(global_obs_tensor)
            
        actions_np = actions.cpu().numpy()
        log_probs_np = log_probs.cpu().numpy()
        value_np = float(value.squeeze().cpu().numpy())
        
        actions_dict = {i: actions_np[i] for i in range(self.n_agents)}
        log_probs_dict = {i: float(log_probs_np[i]) for i in range(self.n_agents)}
        
        return actions_dict, value_np, log_probs_dict

    def compute_gae(self, rewards, values, dones, last_value=0.0):
        """Standard GAE on the global rewards and values.
        Parameters
        ----------
        """
        gamma = self.config.gamma
        gae_lambda = self.config.gae_lambda
        T = len(rewards)
        
        rewards = np.asarray(rewards)
        values = np.asarray(values)
        dones = np.asarray(dones)
        
        next_values = np.empty(T)
        next_values[:-1] = values[1:]
        next_values[-1] = last_value
        non_terminal = 1.0 - dones
        deltas = rewards + gamma * next_values * non_terminal - values
        
        advantages = np.empty(T)
        last_gae = 0.0
        decay = gamma * gae_lambda
        for t in range(T - 1, -1, -1):
            last_gae = deltas[t] + decay * non_terminal[t] * last_gae
            advantages[t] = last_gae
        returns = advantages + values
        return advantages, returns

    def update(self, rollout_data, last_value=0.0):
        """MAPPO update.
        
        Expects rollout_data to contain global values/rewards, and local obs/actions.
        We broadcast the global advantage to all agents sharing the actor.
        
        Parameters
        ----------
        """
        # Unpack global data (T steps)
        global_obs = rollout_data['global_obs']
        rewards = rollout_data['rewards']
        values = rollout_data['values']
        dones = rollout_data['dones']
        
        # Unpack local data (T steps x N agents)
        # Flattened to (T * N) for the actor update
        local_obs = rollout_data['local_obs']
        actions = rollout_data['actions']
        old_log_probs = rollout_data['log_probs']
        
        adv_global, ret_global = self.compute_gae(rewards, values, dones, last_value)
        
        # Phase 10: Risk-Averse RL (CVaR-PG)
        # If enabled, only update the policy on the worst-case (highest cost / lowest return) episodes.
        if getattr(self.config, 'use_cvar_objective', False):
            # var_threshold is the alpha-quantile of returns (e.g., lowest 10% of returns)
            var_threshold = np.quantile(ret_global, self.config.cvar_alpha)
            # Zero out advantages for transitions that are better than the VaR threshold
            cvar_mask = (ret_global <= var_threshold).astype(np.float32)
            adv_global = adv_global * cvar_mask

        adv_mean_pre = float(np.mean(adv_global))
        
        # To update the actor, we broadcast the global advantage to each agent's local action
        adv_expanded = np.repeat(adv_global, self.n_agents)
        
        # Tensors for Critic
        g_obs_t = torch.FloatTensor(global_obs).to(self.device)
        ret_t = torch.FloatTensor(ret_global).to(self.device)
        
        # Tensors for Actor
        l_obs_t = torch.FloatTensor(local_obs).to(self.device)
        act_t = torch.FloatTensor(actions).to(self.device)
        old_lp_t = torch.FloatTensor(old_log_probs).to(self.device)
        adv_t = torch.FloatTensor(adv_expanded).to(self.device)
        
        N_actor = l_obs_t.shape[0]
        N_critic = g_obs_t.shape[0]
        mb_size_actor = min(self.minibatch_size, max(1, N_actor))
        mb_size_critic = min(self.minibatch_size // self.n_agents, max(1, N_critic))
        
        total_actor_loss = 0.0
        total_critic_loss = 0.0
        total_entropy = 0.0
        n_updates = 0
        
        for _ in range(self.config.n_epochs):
            # 1. Update Actor
            perm_a = torch.randperm(N_actor, device=self.device)
            for start in range(0, N_actor, mb_size_actor):
                end = min(start + mb_size_actor, N_actor)
                idx = perm_a[start:end]
                if len(idx) < 2: continue
                
                mb_obs = l_obs_t[idx]
                mb_act = act_t[idx]
                mb_old_lp = old_lp_t[idx]
                mb_adv = adv_t[idx]
                
                mb_adv = (mb_adv - mb_adv.mean()) / (mb_adv.std() + 1e-8)
                
                new_lp, entropy = self.actor.evaluate_actions(mb_obs, mb_act)
                if torch.isnan(new_lp).any() or torch.isinf(new_lp).any(): continue
                
                ratio = torch.exp(new_lp - mb_old_lp)
                ratio = torch.clamp(ratio, self.config.ratio_clamp_min, self.config.ratio_clamp_max)
                
                surr1 = ratio * mb_adv
                surr2 = torch.clamp(ratio, 1.0 - self.config.clip_range, 1.0 + self.config.clip_range) * mb_adv
                actor_loss = -torch.min(surr1, surr2).mean()
                
                self.actor_optimizer.zero_grad()
                (actor_loss - self.ent_coef * entropy.mean()).backward()
                torch.nn.utils.clip_grad_norm_(self.actor.parameters(), self.config.max_grad_norm)
                self.actor_optimizer.step()
                
                total_actor_loss += float(actor_loss.item())
                total_entropy += float(entropy.mean().item())
                
            # 2. Update Critic
            perm_c = torch.randperm(N_critic, device=self.device)
            for start in range(0, N_critic, mb_size_critic):
                end = min(start + mb_size_critic, N_critic)
                idx = perm_c[start:end]
                if len(idx) < 2: continue
                
                mb_g_obs = g_obs_t[idx]
                mb_ret = ret_t[idx]
                
                value_pred = self.critic(mb_g_obs).squeeze(-1)
                critic_loss = nn.functional.mse_loss(value_pred, mb_ret)
                
                self.critic_optimizer.zero_grad()
                (self.vf_coef * critic_loss).backward()
                torch.nn.utils.clip_grad_norm_(self.critic.parameters(), self.config.max_grad_norm)
                self.critic_optimizer.step()
                
                total_critic_loss += float(critic_loss.item())
                n_updates += 1
                
        n_updates = max(n_updates, 1)
        return {
            'actor_loss': total_actor_loss / max(n_updates * self.n_agents, 1),
            'critic_loss': total_critic_loss / n_updates,
            'entropy': total_entropy / max(n_updates * self.n_agents, 1),
            'mean_advantage': adv_mean_pre,
            'mean_return': float(ret_global.mean()),
        }

    def save(self, path: str) -> None:
        """Save MAPPO weights, optimizer states, and shape metadata.
        Parameters
        ----------
        """
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        torch.save(
            {
                "actor": self.actor.state_dict(),
                "critic": self.critic.state_dict(),
                "actor_optimizer": self.actor_optimizer.state_dict(),
                "critic_optimizer": self.critic_optimizer.state_dict(),
                "local_obs_dim": self.local_obs_dim,
                "global_obs_dim": self.global_obs_dim,
                "action_dim": self.action_dim,
                "n_agents": self.n_agents,
            },
            out,
        )

    def load(self, path: str, load_optimizers: bool = False) -> None:
        """Load a checkpoint produced by :meth:`save`.
        Parameters
        ----------
        """
        checkpoint = torch.load(path, map_location=self.device)
        expected = {
            "local_obs_dim": self.local_obs_dim,
            "global_obs_dim": self.global_obs_dim,
            "action_dim": self.action_dim,
            "n_agents": self.n_agents,
        }
        for key, value in expected.items():
            if checkpoint.get(key) != value:
                raise ValueError(
                    f"Checkpoint {key}={checkpoint.get(key)!r} does not match "
                    f"agent {key}={value!r}"
                )
        self.actor.load_state_dict(checkpoint["actor"])
        self.critic.load_state_dict(checkpoint["critic"])
        if load_optimizers:
            self.actor_optimizer.load_state_dict(checkpoint["actor_optimizer"])
            self.critic_optimizer.load_state_dict(checkpoint["critic_optimizer"])
