"""Soft Actor-Critic (SAC) agent implementation.

Implements the SAC algorithm following Haarnoja et al. (2018) with:
- Gaussian policy with tanh squashing and reparameterization trick
- Twin Q-networks (clipped double-Q) to reduce overestimation bias
- Automatic temperature (alpha) tuning
- Uniform replay buffer

References
----------
Haarnoja, T., Zhou, A., Abbeel, P., & Levine, S. (2018).
    Soft Actor-Critic: Off-Policy Maximum Entropy Deep Reinforcement
    Learning with a Stochastic Actor. ICML 2018.
    arXiv:1801.01290. https://arxiv.org/abs/1801.01290

Haarnoja, T., Zhou, A., Hartikainen, K., Tucker, G., Ha, S., Tan, J.,
    Kumar, V., Zhu, H., Gupta, A., Abbeel, P., & Levine, S. (2018).
    Soft Actor-Critic Algorithms and Applications.
    arXiv:1812.05905. https://arxiv.org/abs/1812.05905
"""

import random
from collections import deque
from typing import Tuple

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.distributions import Normal

from supply_chain_research.config import SACConfig


class ReplayBuffer:
    """Uniform experience replay buffer using a deque.

    Stores transitions (obs, action, reward, next_obs, done) and
    samples uniformly at random for off-policy learning.

    Parameters
    ----------
    capacity : int
        Maximum number of transitions to store. When full, oldest
        transitions are discarded (FIFO).

    Attributes
    ----------
    buffer : collections.deque
        Internal storage with maxlen=capacity.
    """

    def __init__(self, capacity: int):
        """Initialize the replay buffer.

        Parameters
        ----------
        capacity : int
            Maximum number of transitions to store.
        """
        self.buffer = deque(maxlen=capacity)

    def push(self, obs: np.ndarray, action: np.ndarray, reward: float,
             next_obs: np.ndarray, done: bool) -> None:
        """Add a transition to the buffer.

        Parameters
        ----------
        obs : np.ndarray
            Current observation, shape (obs_dim,).
        action : np.ndarray
            Action taken, shape (action_dim,).
        reward : float
            Scalar reward received.
        next_obs : np.ndarray
            Next observation, shape (obs_dim,).
        done : bool
            Whether the episode terminated.
        """
        self.buffer.append((obs, action, reward, next_obs, done))

    def sample(self, batch_size: int) -> Tuple[
        torch.FloatTensor, torch.FloatTensor, torch.FloatTensor,
        torch.FloatTensor, torch.FloatTensor
    ]:
        """Sample a random batch of transitions.

        Parameters
        ----------
        batch_size : int
            Number of transitions to sample.

        Returns
        -------
        obs : torch.FloatTensor
            Batch of observations, shape (batch_size, obs_dim).
        actions : torch.FloatTensor
            Batch of actions, shape (batch_size, action_dim).
        rewards : torch.FloatTensor
            Batch of rewards, shape (batch_size, 1).
        next_obs : torch.FloatTensor
            Batch of next observations, shape (batch_size, obs_dim).
        dones : torch.FloatTensor
            Batch of done flags, shape (batch_size, 1).
        """
        batch = random.sample(self.buffer, batch_size)
        obs, actions, rewards, next_obs, dones = zip(*batch)

        return (
            torch.FloatTensor(np.array(obs)),
            torch.FloatTensor(np.array(actions)),
            torch.FloatTensor(np.array(rewards)).unsqueeze(1),
            torch.FloatTensor(np.array(next_obs)),
            torch.FloatTensor(np.array(dones, dtype=np.float32)).unsqueeze(1),
        )

    def __len__(self) -> int:
        """Return the current number of stored transitions.

        Returns
        -------
        int
            Number of transitions in the buffer.
        """
        return len(self.buffer)


class SACActorNetwork(nn.Module):
    """Gaussian policy network with tanh squashing for SAC.

    Outputs mean and log_std of a Gaussian distribution. Actions are
    sampled via the reparameterization trick and squashed through tanh
    to bound them to [-1, 1]. The log-probability is corrected for the
    tanh transformation.

    Architecture: 2 hidden layers with ReLU activation.

    Parameters
    ----------
    obs_dim : int
        Dimension of the observation space.
    action_dim : int
        Dimension of the action space.
    hidden_size : int, optional
        Number of units in each hidden layer. Default is 256.

    Attributes
    ----------
    fc1 : nn.Linear
        First hidden layer.
    fc2 : nn.Linear
        Second hidden layer.
    fc_mean : nn.Linear
        Output layer for action mean.
    fc_log_std : nn.Linear
        Output layer for action log standard deviation.

    Notes
    -----
    log_std is clamped to [-5, 2] following the recommendation in
    Haarnoja et al. (2018), arXiv:1812.05905, Appendix D.
    """

    LOG_STD_MIN = -5.0
    LOG_STD_MAX = 2.0

    def __init__(self, obs_dim: int, action_dim: int,
                 hidden_size: int = 256):
        """Initialize the SAC actor network.

        Parameters
        ----------
        obs_dim : int
            Dimension of the observation space.
        action_dim : int
            Dimension of the action space.
        hidden_size : int, optional
            Number of units in each hidden layer. Default is 256.
        """
        super().__init__()
        self.fc1 = nn.Linear(obs_dim, hidden_size)
        self.fc2 = nn.Linear(hidden_size, hidden_size)
        self.fc_mean = nn.Linear(hidden_size, action_dim)
        self.fc_log_std = nn.Linear(hidden_size, action_dim)

    def forward(self, obs: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        """Compute action mean and log_std.

        Parameters
        ----------
        obs : torch.Tensor
            Observation tensor of shape (batch, obs_dim).

        Returns
        -------
        mean : torch.Tensor
            Action mean, shape (batch, action_dim).
        log_std : torch.Tensor
            Clamped log standard deviation, shape (batch, action_dim).
        """
        x = F.relu(self.fc1(obs))
        x = F.relu(self.fc2(x))
        mean = self.fc_mean(x)
        log_std = self.fc_log_std(x)
        log_std = torch.clamp(log_std, self.LOG_STD_MIN, self.LOG_STD_MAX)
        return mean, log_std

    def sample(self, obs: torch.Tensor) -> Tuple[
        torch.Tensor, torch.Tensor
    ]:
        """Sample an action using the reparameterization trick with tanh squashing.

        Parameters
        ----------
        obs : torch.Tensor
            Observation tensor of shape (batch, obs_dim).

        Returns
        -------
        action : torch.Tensor
            Squashed action in [-1, 1], shape (batch, action_dim).
        log_prob : torch.Tensor
            Log probability of the action corrected for tanh squashing,
            shape (batch, 1).

        Notes
        -----
        The log-probability correction for tanh squashing is:
            log_prob -= sum(log(1 - tanh(x)^2 + eps))
        where eps=1e-6 for numerical stability. This follows Eq. 21 in
        Haarnoja et al. (2018), arXiv:1801.01290, Appendix C.
        """
        mean, log_std = self.forward(obs)
        std = log_std.exp()
        normal = Normal(mean, std)

        # Reparameterization trick: x = mean + std * epsilon
        x_t = normal.rsample()
        action = torch.tanh(x_t)

        # Log-probability with tanh squashing correction
        log_prob = normal.log_prob(x_t)
        # Correction for tanh squashing (Haarnoja et al. 2018, Appendix C)
        log_prob -= torch.log(1.0 - action.pow(2) + 1e-6)
        log_prob = log_prob.sum(dim=-1, keepdim=True)

        return action, log_prob


class SACCriticNetwork(nn.Module):
    """Twin Q-network for SAC (clipped double-Q learning).

    Implements two independent Q-networks (q1, q2) that take
    concatenated (observation, action) as input and output scalar
    Q-values. Using the minimum of the two Q-values reduces
    overestimation bias (Fujimoto et al. 2018, TD3; adopted by SAC).

    Architecture: Each Q-network has 2 hidden layers with ReLU.

    Parameters
    ----------
    obs_dim : int
        Dimension of the observation space.
    action_dim : int
        Dimension of the action space.
    hidden_size : int, optional
        Number of units in each hidden layer. Default is 256.

    Attributes
    ----------
    q1_fc1 : nn.Linear
        First hidden layer of Q1 network.
    q1_fc2 : nn.Linear
        Second hidden layer of Q1 network.
    q1_out : nn.Linear
        Output layer of Q1 network.
    q2_fc1 : nn.Linear
        First hidden layer of Q2 network.
    q2_fc2 : nn.Linear
        Second hidden layer of Q2 network.
    q2_out : nn.Linear
        Output layer of Q2 network.
    """

    def __init__(self, obs_dim: int, action_dim: int,
                 hidden_size: int = 256):
        """Initialize the twin Q-networks.

        Parameters
        ----------
        obs_dim : int
            Dimension of the observation space.
        action_dim : int
            Dimension of the action space.
        hidden_size : int, optional
            Number of units in each hidden layer. Default is 256.
        """
        super().__init__()
        input_dim = obs_dim + action_dim

        # Q1 network
        self.q1_fc1 = nn.Linear(input_dim, hidden_size)
        self.q1_fc2 = nn.Linear(hidden_size, hidden_size)
        self.q1_out = nn.Linear(hidden_size, 1)

        # Q2 network
        self.q2_fc1 = nn.Linear(input_dim, hidden_size)
        self.q2_fc2 = nn.Linear(hidden_size, hidden_size)
        self.q2_out = nn.Linear(hidden_size, 1)

    def forward(self, obs: torch.Tensor,
                action: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        """Compute Q-values from both networks.

        Parameters
        ----------
        obs : torch.Tensor
            Observation tensor of shape (batch, obs_dim).
        action : torch.Tensor
            Action tensor of shape (batch, action_dim).

        Returns
        -------
        q1 : torch.Tensor
            Q-value from network 1, shape (batch, 1).
        q2 : torch.Tensor
            Q-value from network 2, shape (batch, 1).
        """
        x = torch.cat([obs, action], dim=-1)

        q1 = F.relu(self.q1_fc1(x))
        q1 = F.relu(self.q1_fc2(q1))
        q1 = self.q1_out(q1)

        q2 = F.relu(self.q2_fc1(x))
        q2 = F.relu(self.q2_fc2(q2))
        q2 = self.q2_out(q2)

        return q1, q2

    def q1_forward(self, obs: torch.Tensor,
                   action: torch.Tensor) -> torch.Tensor:
        """Compute Q-value from network 1 only.

        Parameters
        ----------
        obs : torch.Tensor
            Observation tensor of shape (batch, obs_dim).
        action : torch.Tensor
            Action tensor of shape (batch, action_dim).

        Returns
        -------
        q1 : torch.Tensor
            Q-value from network 1, shape (batch, 1).
        """
        x = torch.cat([obs, action], dim=-1)
        q1 = F.relu(self.q1_fc1(x))
        q1 = F.relu(self.q1_fc2(q1))
        q1 = self.q1_out(q1)
        return q1


class SACAgent:
    """Soft Actor-Critic agent (Haarnoja 2018a/b).

    Combines a Gaussian / tanh-squashed policy, twin clipped-double-Q
    critics, soft (polyak) target-network updates, and optional
    automatic temperature tuning into a single off-policy agent.

    Parameters
    ----------
    obs_dim : int
        Observation-space dimension.
    action_dim : int
        Action-space dimension; the policy emits actions in
        ``[-1, 1]`` per dimension.
    config : SACConfig, optional
        SAC hyperparameter container. If ``None`` defaults are used.
    device : torch.device, optional
        Compute device; auto-detected when ``None``.

    Attributes
    ----------
    actor : SACActorNetwork
        Stochastic Gaussian/tanh policy.
    critic : SACCriticNetwork
        Twin-Q critic (online).
    critic_target : SACCriticNetwork
        Twin-Q critic (slow / target). Polyak-updated each step.
    log_alpha : torch.nn.Parameter
        Logarithm of the entropy temperature; learnable iff
        ``config.alpha_auto`` is True.
    target_entropy : float
        Target policy entropy ``-dim(A)`` (Haarnoja 2018b Eq. 17).
    replay_buffer : ReplayBuffer
        Uniform off-policy buffer.

    References
    ----------
    Haarnoja et al. (2018a). Soft Actor-Critic: Off-Policy Maximum
        Entropy Deep RL with a Stochastic Actor. ICML 2018.
        arXiv:1801.01290.
    Haarnoja et al. (2018b). Soft Actor-Critic Algorithms and
        Applications. arXiv:1812.05905.
    Fujimoto et al. (2018). Addressing Function Approximation Error
        in Actor-Critic Methods (TD3). ICML 2018. arXiv:1802.09477 —
        twin clipped-double-Q trick adopted by SAC.
    """

    def __init__(self, obs_dim: int, action_dim: int,
                 config: SACConfig = None, device=None):
        if config is None:
            config = SACConfig()
        self.config = config
        self.obs_dim = obs_dim
        self.action_dim = action_dim

        if device is None:
            device = torch.device(
                'cuda' if torch.cuda.is_available() else 'cpu',
            )
        # Accept either a `torch.device` or a device string
        # (e.g. "cuda" / "cpu") — `torch.device(s)` is idempotent
        # on existing `torch.device` instances per PyTorch docs.
        self.device = (
            device if isinstance(device, torch.device)
            else torch.device(device)
        )

        # Networks
        self.actor = SACActorNetwork(
            obs_dim, action_dim, hidden_size=config.hidden_size,
        ).to(self.device)
        self.critic = SACCriticNetwork(
            obs_dim, action_dim, hidden_size=config.hidden_size,
        ).to(self.device)
        self.critic_target = SACCriticNetwork(
            obs_dim, action_dim, hidden_size=config.hidden_size,
        ).to(self.device)
        # Hard-copy online weights into target at construction time
        self.critic_target.load_state_dict(self.critic.state_dict())
        for p in self.critic_target.parameters():
            p.requires_grad = False

        # Optimizers — Haarnoja 2018a Table 1 uses Adam with lr=3e-4
        # for actor / critic / temperature.
        self.actor_optimizer = torch.optim.Adam(
            self.actor.parameters(), lr=config.learning_rate,
        )
        self.critic_optimizer = torch.optim.Adam(
            self.critic.parameters(), lr=config.learning_rate,
        )

        # Entropy temperature alpha — Haarnoja 2018b Eq. 17–18.
        # log_alpha is the optimisation variable so alpha stays
        # positive without an explicit constraint.
        self.alpha_auto = bool(config.alpha_auto)
        self.target_entropy = -float(action_dim)  # Haarnoja 2018b §5
        if self.alpha_auto:
            self.log_alpha = torch.nn.Parameter(
                torch.log(torch.tensor(float(config.alpha), device=self.device)),
            )
            self.alpha_optimizer = torch.optim.Adam(
                [self.log_alpha], lr=config.learning_rate,
            )
        else:
            # Fixed alpha (Haarnoja 2018a Table 1 default)
            self.log_alpha = torch.tensor(
                float(np.log(config.alpha)),
                device=self.device,
                requires_grad=False,
            )
            self.alpha_optimizer = None

        # Replay buffer
        self.replay_buffer = ReplayBuffer(config.replay_buffer_size)

    @property
    def alpha(self) -> torch.Tensor:
        """Current entropy temperature (always positive).

        Returns
        -------
        torch.Tensor
            Scalar tensor ``exp(log_alpha)``.
        """
        return self.log_alpha.exp()

    def select_action(self, obs: np.ndarray,
                      deterministic: bool = False) -> np.ndarray:
        """Sample an action from the current policy.

        Parameters
        ----------
        obs : np.ndarray
            Observation of shape ``(obs_dim,)``.
        deterministic : bool, optional
            If True, return ``tanh(mean)`` (greedy). If False (default),
            sample with the reparameterisation trick.

        Returns
        -------
        np.ndarray
            Action of shape ``(action_dim,)`` in ``[-1, 1]``.
        """
        obs_t = torch.as_tensor(
            obs, dtype=torch.float32, device=self.device,
        ).unsqueeze(0)
        with torch.no_grad():
            if deterministic:
                mean, _ = self.actor.forward(obs_t)
                action = torch.tanh(mean)
            else:
                action, _ = self.actor.sample(obs_t)
        return action.squeeze(0).cpu().numpy()

    def soft_update(self, tau: float = None) -> None:
        """Polyak update target critic towards online critic.

        ``θ̄ ← τ·θ + (1-τ)·θ̄`` per Haarnoja 2018a Eq. 6.

        Parameters
        ----------
        tau : float, optional
            Smoothing coefficient. Defaults to ``config.tau``.
        """
        if tau is None:
            tau = self.config.tau
        with torch.no_grad():
            for p, p_targ in zip(
                self.critic.parameters(),
                self.critic_target.parameters(),
            ):
                p_targ.data.mul_(1.0 - tau)
                p_targ.data.add_(tau * p.data)

    def update(self, batch_size: int = None) -> dict:
        """Run one off-policy SAC gradient step.

        Performs (in order): critic loss + step, actor loss + step,
        optional alpha (temperature) loss + step, soft target update.

        Parameters
        ----------
        batch_size : int, optional
            Minibatch size sampled from the replay buffer; defaults to
            ``config.batch_size``.

        Returns
        -------
        dict
            Scalar metrics: ``critic_loss``, ``actor_loss``,
            ``alpha_loss``, ``alpha`` (current temperature),
            ``q1_mean``, ``q2_mean``, ``log_prob_mean``.
        """
        if batch_size is None:
            batch_size = self.config.batch_size
        if len(self.replay_buffer) < batch_size:
            return {}

        obs, actions, rewards, next_obs, dones = self.replay_buffer.sample(
            batch_size,
        )
        obs = obs.to(self.device)
        actions = actions.to(self.device)
        rewards = rewards.to(self.device)
        next_obs = next_obs.to(self.device)
        dones = dones.to(self.device)

        # ---- Critic update (Haarnoja 2018b Eq. 5) -----------------
        with torch.no_grad():
            next_action, next_log_prob = self.actor.sample(next_obs)
            q1_next, q2_next = self.critic_target(next_obs, next_action)
            q_next = torch.min(q1_next, q2_next) - self.alpha * next_log_prob
            target_q = rewards + (1.0 - dones) * self.config.gamma * q_next

        q1, q2 = self.critic(obs, actions)
        critic_loss = F.mse_loss(q1, target_q) + F.mse_loss(q2, target_q)

        self.critic_optimizer.zero_grad()
        critic_loss.backward()
        self.critic_optimizer.step()

        # ---- Actor update (Haarnoja 2018b Eq. 7) ------------------
        new_action, log_prob = self.actor.sample(obs)
        q1_pi, q2_pi = self.critic(obs, new_action)
        q_pi = torch.min(q1_pi, q2_pi)
        actor_loss = (self.alpha.detach() * log_prob - q_pi).mean()

        self.actor_optimizer.zero_grad()
        actor_loss.backward()
        self.actor_optimizer.step()

        # ---- Temperature update (Haarnoja 2018b Eq. 18) -----------
        if self.alpha_auto:
            alpha_loss = -(
                self.log_alpha * (log_prob.detach() + self.target_entropy)
            ).mean()
            self.alpha_optimizer.zero_grad()
            alpha_loss.backward()
            self.alpha_optimizer.step()
            alpha_loss_val = float(alpha_loss.item())
        else:
            alpha_loss_val = 0.0

        # ---- Soft target update (Haarnoja 2018a Eq. 6) ------------
        self.soft_update()

        return {
            'critic_loss': float(critic_loss.item()),
            'actor_loss': float(actor_loss.item()),
            'alpha_loss': alpha_loss_val,
            'alpha': float(self.alpha.detach().item()),
            'q1_mean': float(q1.mean().item()),
            'q2_mean': float(q2.mean().item()),
            'log_prob_mean': float(log_prob.mean().item()),
        }

    def save(self, filepath: str) -> None:
        """Save full agent state to ``filepath``.

        Parameters
        ----------
        filepath : str
            Output path for the ``torch.save`` checkpoint.
        """
        ckpt = {
            'actor_state_dict': self.actor.state_dict(),
            'critic_state_dict': self.critic.state_dict(),
            'critic_target_state_dict': self.critic_target.state_dict(),
            'actor_optimizer': self.actor_optimizer.state_dict(),
            'critic_optimizer': self.critic_optimizer.state_dict(),
            'log_alpha': self.log_alpha.detach().cpu(),
            'alpha_auto': self.alpha_auto,
        }
        if self.alpha_auto:
            ckpt['alpha_optimizer'] = self.alpha_optimizer.state_dict()
        torch.save(ckpt, filepath)

    def load(self, filepath: str) -> None:
        """Load full agent state from ``filepath``.

        Parameters
        ----------
        filepath : str
            Path to a checkpoint previously written by :meth:`save`.
        """
        ckpt = torch.load(
            filepath, map_location=self.device, weights_only=False,
        )
        self.actor.load_state_dict(ckpt['actor_state_dict'])
        self.critic.load_state_dict(ckpt['critic_state_dict'])
        self.critic_target.load_state_dict(ckpt['critic_target_state_dict'])
        self.actor_optimizer.load_state_dict(ckpt['actor_optimizer'])
        self.critic_optimizer.load_state_dict(ckpt['critic_optimizer'])
        log_alpha_val = ckpt['log_alpha']
        if self.alpha_auto:
            with torch.no_grad():
                self.log_alpha.copy_(log_alpha_val.to(self.device))
            if 'alpha_optimizer' in ckpt:
                self.alpha_optimizer.load_state_dict(ckpt['alpha_optimizer'])
        else:
            self.log_alpha = log_alpha_val.to(self.device)
