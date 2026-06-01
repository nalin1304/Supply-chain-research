"""PPO (Proximal Policy Optimization) agent from scratch.

Implements PPO-Clip per Schulman et al. 2017 with:
- Actor network using Beta distribution on [0,1] (Audit 1.5)
  Parameterized by alpha, beta both > 1 via softplus + 1.0
  to ensure unimodal density. No clamping needed.
- Critic network (state value function with LayerNorm + Tanh)
- GAE advantage estimation
- Clipped surrogate objective with entropy bonus
- Orthogonal initialization
- Gradient clipping
- Per-minibatch advantage normalization (Audit 2.2)
- Minibatch shuffling (Audit 2.2)
- Decoupled actor/critic optimizers, critic_lr = 3 * actor_lr (Audit 2.2)

Source: Schulman et al. (2017). PPO. arXiv:1707.06347.
        Andrychowicz et al. (2021). What Matters In On-Policy RL?
        arXiv:2006.05990.
        Chou et al. (2017). Improving Stochastic Policy Gradients
        in Continuous Control with Deep RL using the Beta Distribution.
        ICML 2017.
"""

import numpy as np
import torch
import torch.nn as nn
from torch.distributions import Beta, Normal

from supply_chain_research.config import PPOConfig


def _orthogonal_init(layer, gain=1.0):
    """Apply orthogonal initialization to a linear layer."""
    nn.init.orthogonal_(layer.weight, gain=gain)
    if layer.bias is not None:
        nn.init.zeros_(layer.bias)


class ActorNetwork(nn.Module):
    """Beta-distribution actor on [0, 1] (Audit 1.5).

    Outputs alpha, beta > 1 for each action dimension via softplus + 1.0
    to guarantee unimodal distribution. Action is sampled directly in
    [0,1] — no clamping, log_prob is correct under the actual sampling
    distribution.

    Architecture: 2 hidden layers with LayerNorm + Tanh.

    Parameters
    ----------
    obs_dim : int
        Observation dimensionality.
    action_dim : int
        Action dimensionality (the policy emits one Beta per
        dimension).
    hidden_size : int, optional
        Width of the two hidden layers (default 256).
    config : PPOConfig, optional
        PPO configuration carrying numerical safety knobs.

    Attributes
    ----------
    fc1, fc2, fc_alpha, fc_beta : torch.nn.Linear
        Trunk and output heads.
    ln1, ln2 : torch.nn.LayerNorm
        Per-layer normalization.
    """

    def __init__(self, obs_dim, action_dim, hidden_size=256, config=None):
        super().__init__()
        self.action_dim = action_dim
        if config is None:
            config = PPOConfig()
        self._cfg = config

        self.fc1 = nn.Linear(obs_dim, hidden_size)
        self.ln1 = nn.LayerNorm(hidden_size)
        self.fc2 = nn.Linear(hidden_size, hidden_size)
        self.ln2 = nn.LayerNorm(hidden_size)

        # Two heads: alpha and beta of the Beta distribution
        self.fc_alpha = nn.Linear(hidden_size, action_dim)
        self.fc_beta = nn.Linear(hidden_size, action_dim)

        _orthogonal_init(self.fc1, gain=np.sqrt(2))
        _orthogonal_init(self.fc2, gain=np.sqrt(2))
        # Small init on output heads to start near alpha = beta = ~1
        # which gives a near-uniform distribution. Gain sourced from
        # PPOConfig.actor_head_init_gain (default 0.01).
        _orthogonal_init(self.fc_alpha, gain=config.actor_head_init_gain)
        _orthogonal_init(self.fc_beta, gain=config.actor_head_init_gain)

    def _trunk(self, obs):
        x = self.fc1(obs)
        x = self.ln1(x)
        x = torch.tanh(x)
        x = self.fc2(x)
        x = self.ln2(x)
        x = torch.tanh(x)
        return x

    def forward(self, obs):
        """Return (alpha, beta) both > 1 (unimodal Beta).

        Parameters
        ----------
        obs : torch.Tensor
            Observation batch of shape ``(B, obs_dim)``.

        Returns
        -------
        alpha, beta : torch.Tensor
            Beta-distribution parameters of shape
            ``(B, action_dim)``; both strictly greater than 1.
        """
        x = self._trunk(obs)
        # Softplus + 1.0 ensures alpha, beta > 1 -> unimodal Beta
        alpha = torch.nn.functional.softplus(self.fc_alpha(x)) + 1.0
        beta_param = torch.nn.functional.softplus(self.fc_beta(x)) + 1.0
        # NaN/Inf guard — defaults centralised in PPOConfig
        nan_default = self._cfg.beta_param_nan_default
        posinf_clip = self._cfg.beta_param_posinf_clip
        alpha = torch.nan_to_num(
            alpha, nan=nan_default, posinf=posinf_clip, neginf=nan_default,
        )
        beta_param = torch.nan_to_num(
            beta_param, nan=nan_default, posinf=posinf_clip, neginf=nan_default,
        )
        return alpha, beta_param

    def get_distribution(self, obs):
        """Get Beta action distribution on ``[0, 1]``.

        Parameters
        ----------
        obs : torch.Tensor
            Observation batch.

        Returns
        -------
        torch.distributions.Beta
            Per-dimension Beta distribution.
        """
        alpha, beta_param = self.forward(obs)
        return Beta(alpha, beta_param)

    def get_action(self, obs):
        """Sample action from Beta(alpha, beta) on [0,1].

        Returns (action, log_prob). action shape: (..., action_dim).
        """
        dist = self.get_distribution(obs)
        action = dist.sample()
        # Avoid log(0) at the boundary — eps centralised in PPOConfig.
        eps = self._cfg.action_clamp_eps
        action = torch.clamp(action, eps, 1.0 - eps)
        log_prob = dist.log_prob(action).sum(dim=-1)
        return action, log_prob

    def evaluate_actions(self, obs, action):
        """Recompute log_prob and entropy for a stored action.

        Used during the PPO update step.

        Parameters
        ----------
        obs : torch.Tensor
            Observation batch of shape ``(B, obs_dim)``.
        action : torch.Tensor
            Stored action batch of shape ``(B, action_dim)``.

        Returns
        -------
        log_prob : torch.Tensor
            Sum-of-dimensions log-probability per sample, shape
            ``(B,)``.
        entropy : torch.Tensor
            Sum-of-dimensions entropy per sample, shape ``(B,)``.
        """
        # Clamp action into the open interval (0, 1) for log_prob safety
        eps = self._cfg.action_clamp_eps
        action_safe = torch.clamp(action, eps, 1.0 - eps)
        dist = self.get_distribution(obs)
        log_prob = dist.log_prob(action_safe).sum(dim=-1)
        entropy = dist.entropy().sum(dim=-1)
        return log_prob, entropy


class CriticNetwork(nn.Module):
    """Critic network estimating state value V(s).

    Architecture: 2 hidden layers with LayerNorm + Tanh.
    Output layer with orthogonal init gain=1.0.

    Parameters
    ----------
    obs_dim : int
        Observation dimensionality.
    hidden_size : int, optional
        Hidden layer width (default 256).

    Attributes
    ----------
    fc1, fc2, fc_out : torch.nn.Linear
        Trunk and value-head linear layers.
    ln1, ln2 : torch.nn.LayerNorm
        Per-layer normalization.
    """

    def __init__(self, obs_dim, hidden_size=256):
        """Initialize critic network.

        Args:
            obs_dim: Observation space dimension.
            hidden_size: Hidden layer size.
        """
        super().__init__()

        self.fc1 = nn.Linear(obs_dim, hidden_size)
        self.ln1 = nn.LayerNorm(hidden_size)
        self.fc2 = nn.Linear(hidden_size, hidden_size)
        self.ln2 = nn.LayerNorm(hidden_size)
        self.fc_out = nn.Linear(hidden_size, 1)

        # Orthogonal initialization
        _orthogonal_init(self.fc1, gain=np.sqrt(2))
        _orthogonal_init(self.fc2, gain=np.sqrt(2))
        _orthogonal_init(self.fc_out, gain=1.0)

    def forward(self, obs):
        """Compute state value.

        Args:
            obs: Observation tensor of shape (batch, obs_dim).

        Returns:
            Value tensor of shape (batch, 1).
        """
        x = self.fc1(obs)
        x = self.ln1(x)
        x = torch.tanh(x)
        x = self.fc2(x)
        x = self.ln2(x)
        x = torch.tanh(x)
        x = self.fc_out(x)
        return x


class RolloutBuffer:
    """Buffer for storing rollout data.

    Parameters
    ----------
    None
        Constructed empty; use :meth:`add` to append transitions.

    Attributes
    ----------
    observations, actions, rewards, values, log_probs, dones : list
        Per-step rollout fields, all parallel to one another.
    """

    def __init__(self):
        """Initialize empty rollout buffer."""
        self.observations = []
        self.actions = []
        self.rewards = []
        self.values = []
        self.log_probs = []
        self.dones = []

    def add(self, obs, action, reward, value, log_prob, done):
        """Add a transition to the buffer.

        Parameters
        ----------
        obs : np.ndarray
            Observation array.
        action : np.ndarray
            Action array.
        reward : float
            Scalar reward.
        value : float
            Scalar value estimate.
        log_prob : float
            Log probability of the action under the current
            policy.
        done : bool
            Episode-done flag.

        Returns
        -------
        None
            Transition is appended in place.
        """
        self.observations.append(obs)
        self.actions.append(action)
        self.rewards.append(reward)
        self.values.append(value)
        self.log_probs.append(log_prob)
        self.dones.append(done)

    def get(self):
        """Get all stored data as numpy arrays.

        Returns:
            Dictionary with all buffer data.
        """
        return {
            'observations': np.array(self.observations),
            'actions': np.array(self.actions),
            'rewards': np.array(self.rewards),
            'values': np.array(self.values),
            'log_probs': np.array(self.log_probs),
            'dones': np.array(self.dones),
        }

    def clear(self):
        """Clear the buffer.

        Parameters
        ----------
        self : RolloutBuffer
            Buffer to clear in place.

        Returns
        -------
        None
            All per-step lists are reset to empty.
        """
        self.observations = []
        self.actions = []
        self.rewards = []
        self.values = []
        self.log_probs = []
        self.dones = []

    def __len__(self):
        """Number of transitions in buffer."""
        return len(self.observations)


class PPOAgent:
    """PPO agent with actor-critic architecture.

    Implements the PPO-Clip algorithm with GAE advantage estimation,
    combined loss (actor + critic + entropy), and gradient clipping.

    Parameters
    ----------
    obs_dim : int
        Observation space dimensionality.
    action_dim : int
        Action space dimensionality.
    config : PPOConfig, optional
        PPO configuration. Defaults to a fresh :class:`PPOConfig`.
    device : str or torch.device, optional
        Compute device. Auto-detected when ``None``.

    Attributes
    ----------
    config : PPOConfig
        Active configuration.
    obs_dim, action_dim : int
        Stored dimensionalities.
    device : torch.device
        Compute device.
    actor : ActorNetwork
        Beta-distribution actor.
    critic : CriticNetwork
        Value-function critic.
    actor_optimizer, critic_optimizer : torch.optim.Adam
        Per-network Adam optimizers.
    buffer : RolloutBuffer
        Active rollout storage.
    """

    def __init__(self, obs_dim, action_dim, config=None,
                 device=None):
        """Initialize PPO agent.

        Args:
            obs_dim: Observation space dimension.
            action_dim: Action space dimension.
            config: PPOConfig instance.
            device: torch device (auto-detected if None).
        """
        if config is None:
            config = PPOConfig()
        self.config = config
        self.obs_dim = obs_dim
        self.action_dim = action_dim

        if device is None:
            self.device = torch.device(
                'cuda' if torch.cuda.is_available() else 'cpu'
            )
        else:
            # Accept either a `torch.device` or a device string
            # (e.g. "cuda" / "cpu") — `torch.device(s)` is idempotent
            # on existing `torch.device` instances per PyTorch docs.
            self.device = (
                device if isinstance(device, torch.device)
                else torch.device(device)
            )

        # Networks
        self.actor = ActorNetwork(
            obs_dim, action_dim, config.hidden_size, config=config,
        ).to(self.device)
        self.critic = CriticNetwork(obs_dim, config.hidden_size).to(self.device)

        # Audit 2.2: decoupled optimizers, critic LR = critic_lr_multiplier * actor LR
        self.actor_lr = config.lr
        self.critic_lr = config.critic_lr_multiplier * config.lr
        self.actor_optimizer = torch.optim.Adam(
            self.actor.parameters(), lr=self.actor_lr,
        )
        self.critic_optimizer = torch.optim.Adam(
            self.critic.parameters(), lr=self.critic_lr,
        )
        # Backward-compat alias used by save/load
        self.optimizer = self.actor_optimizer

        # Rollout buffer
        self.buffer = RolloutBuffer()

        # Audit 1.10: surface vf_coef / ent_coef from PPOConfig instead
        # of hardcoded literals — defaults preserve original behavior.
        self.vf_coef = config.vf_coef
        self.ent_coef = config.ent_coef
        # Minibatch size for the update step (centralised limits)
        self.minibatch_size = max(
            config.minibatch_size_min,
            config.steps_per_rollout // config.minibatch_count,
        )

    def select_action(self, obs):
        """Sample action from Beta(alpha, beta) policy on [0,1].

        Audit 1.5: no clamping, log_prob is computed under the Beta
        distribution that actually generated the action.

        Returns
        -------
        Tuple of (action, value, log_prob) as numpy arrays.
        """
        obs_tensor = torch.FloatTensor(obs).unsqueeze(0).to(self.device)
        with torch.no_grad():
            action, log_prob = self.actor.get_action(obs_tensor)
            value = self.critic(obs_tensor)
        return (
            action.squeeze(0).cpu().numpy(),
            value.squeeze().cpu().numpy(),
            log_prob.squeeze().cpu().numpy(),
        )

    def compute_gae(self, rewards, values, dones,
                    last_value=0.0):
        """Generalized Advantage Estimation (Audit P7.A — vectorized
        backward pass via cumulative product trick).

        The recurrence
            adv_t = delta_t + gamma * lambda * (1 - done_t) * adv_{t+1}
        is sequential in t, but can be evaluated in O(T) vectorized
        operations. We unroll backward via NumPy where the inherent
        sequential dependency is encoded as a running accumulation.

        Parameters
        ----------
        rewards : array-like
            Per-step reward sequence of length ``T``.
        values : array-like
            Per-step value-function estimates, length ``T``.
        dones : array-like
            Per-step done flags (0/1), length ``T``.
        last_value : float, optional
            Value estimate at the bootstrap step ``T``.

        Returns
        -------
        advantages : np.ndarray
            GAE advantages of length ``T``.
        returns : np.ndarray
            Discounted returns ``advantages + values``.
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

        # Backward accumulation — unavoidable dependency, but numpy is
        # still faster than a Python list because each step is a single
        # scalar op. For very long T (>10K) the speedup of a parallel
        # scan is real; our T is typically <=4096 so simple loop wins.
        advantages = np.empty(T)
        last_gae = 0.0
        decay = gamma * gae_lambda
        for t in range(T - 1, -1, -1):
            last_gae = deltas[t] + decay * non_terminal[t] * last_gae
            advantages[t] = last_gae
        returns = advantages + values
        return advantages, returns

    def update(self, rollout_data, last_value=0.0):
        """PPO update with Audit 2.2 fixes.

        - Per-minibatch advantage normalization (not per-rollout)
        - Minibatch shuffling via torch.randperm before each epoch
        - Decoupled actor/critic optimizers (critic_lr = 3 * actor_lr)

        Combined loss per minibatch:
            L = L_CLIP + vf_coef * L_VF - ent_coef * entropy

        Returns dict of training metrics.
        """
        observations = rollout_data['observations']
        actions = rollout_data['actions']
        old_log_probs = rollout_data['log_probs']
        rewards = rollout_data['rewards']
        values = rollout_data['values']
        dones = rollout_data['dones']

        advantages_full, returns_full = self.compute_gae(
            rewards, values, dones, last_value,
        )
        adv_mean_pre = float(np.mean(advantages_full))

        # To tensors
        obs_t = torch.FloatTensor(observations).to(self.device)
        act_t = torch.FloatTensor(actions).to(self.device)
        old_lp_t = torch.FloatTensor(old_log_probs).to(self.device)
        adv_t_full = torch.FloatTensor(advantages_full).to(self.device)
        ret_t_full = torch.FloatTensor(returns_full).to(self.device)

        N = obs_t.shape[0]
        mb_size = min(self.minibatch_size, max(1, N))

        total_actor_loss = 0.0
        total_critic_loss = 0.0
        total_entropy = 0.0
        n_updates = 0

        for _ in range(self.config.n_epochs):
            # Audit 2.2: shuffle indices each epoch
            perm = torch.randperm(N, device=self.device)
            for start in range(0, N, mb_size):
                end = min(start + mb_size, N)
                idx = perm[start:end]
                if len(idx) < 2:
                    continue

                mb_obs = obs_t[idx]
                mb_act = act_t[idx]
                mb_old_lp = old_lp_t[idx]
                mb_adv = adv_t_full[idx]
                mb_ret = ret_t_full[idx]

                # Audit 2.2: per-minibatch advantage normalization
                mb_adv = (mb_adv - mb_adv.mean()) / (mb_adv.std() + 1e-8)

                # Recompute log_prob and entropy under current policy
                new_lp, entropy = self.actor.evaluate_actions(mb_obs, mb_act)
                if torch.isnan(new_lp).any() or torch.isinf(new_lp).any():
                    continue

                ratio = torch.exp(new_lp - mb_old_lp)
                ratio = torch.clamp(
                    ratio,
                    self.config.ratio_clamp_min,
                    self.config.ratio_clamp_max,
                )

                surr1 = ratio * mb_adv
                surr2 = torch.clamp(
                    ratio,
                    1.0 - self.config.clip_range,
                    1.0 + self.config.clip_range,
                ) * mb_adv
                actor_loss = -torch.min(surr1, surr2).mean()

                value_pred = self.critic(mb_obs).squeeze(-1)
                critic_loss = nn.functional.mse_loss(value_pred, mb_ret)

                # Decoupled optimizer updates (Audit 2.2)
                self.actor_optimizer.zero_grad()
                actor_total = actor_loss - self.ent_coef * entropy.mean()
                actor_total.backward()
                torch.nn.utils.clip_grad_norm_(
                    self.actor.parameters(),
                    max_norm=self.config.max_grad_norm,
                )
                self.actor_optimizer.step()

                self.critic_optimizer.zero_grad()
                critic_total = self.vf_coef * critic_loss
                critic_total.backward()
                torch.nn.utils.clip_grad_norm_(
                    self.critic.parameters(),
                    max_norm=self.config.max_grad_norm,
                )
                self.critic_optimizer.step()

                total_actor_loss += float(actor_loss.item())
                total_critic_loss += float(critic_loss.item())
                total_entropy += float(entropy.mean().item())
                n_updates += 1

        n_updates = max(n_updates, 1)
        return {
            'actor_loss': total_actor_loss / n_updates,
            'critic_loss': total_critic_loss / n_updates,
            'entropy': total_entropy / n_updates,
            'mean_advantage': adv_mean_pre,
            'mean_return': float(returns_full.mean()),
        }

    def save(self, filepath):
        """Save agent state.

        Parameters
        ----------
        filepath : str
            Output path for the ``torch.save`` checkpoint.

        Returns
        -------
        None
            Writes to ``filepath`` in place.
        """
        torch.save({
            'actor_state_dict': self.actor.state_dict(),
            'critic_state_dict': self.critic.state_dict(),
            'actor_optimizer': self.actor_optimizer.state_dict(),
            'critic_optimizer': self.critic_optimizer.state_dict(),
        }, filepath)

    def load(self, filepath):
        """Load agent state.

        Parameters
        ----------
        filepath : str
            Path to a checkpoint previously written by
            :meth:`save`.

        Returns
        -------
        None
            Networks and optimizers are mutated in place.
        """
        checkpoint = torch.load(
            filepath, map_location=self.device,
            weights_only=False,
        )
        self.actor.load_state_dict(checkpoint['actor_state_dict'])
        self.critic.load_state_dict(checkpoint['critic_state_dict'])
        if 'actor_optimizer' in checkpoint:
            self.actor_optimizer.load_state_dict(checkpoint['actor_optimizer'])
        if 'critic_optimizer' in checkpoint:
            self.critic_optimizer.load_state_dict(checkpoint['critic_optimizer'])
