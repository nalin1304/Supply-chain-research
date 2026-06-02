import numpy as np

from supply_chain_research.phase3_ai.ppo_agent import PPOAgent


class AttackerPPOAgent(PPOAgent):
    """Adversarial PPO Agent for Phase 11 Minimax Training.
    
    This agent acts as the adversary. It takes the environment state and outputs
    perturbations (e.g., demand shocks or lead time delays). Its objective is to
    minimize the defender's reward, which is equivalent to maximizing the negative
    of the defender's reward.
    """

    def __init__(self, obs_dim, action_dim, config=None, device=None, curriculum_scale=1.0):
        super().__init__(obs_dim, action_dim, config=config, device=device)
        self.curriculum_scale = curriculum_scale

    def set_curriculum_scale(self, scale: float):
        """Scale the adversarial perturbation budget.
        
        Parameters
        ----------
        scale : float
            Multiplier in [0, 1] to slowly introduce adversarial hardness.
        """
        self.curriculum_scale = np.clip(scale, 0.0, 1.0)

    def select_action(self, obs):
        """Sample action and apply curriculum scaling to the perturbation budget.
        
        Parameters
        ----------
        obs : np.ndarray
            Observation array.
            
        Returns
        -------
        action : np.ndarray
            Scaled action perturbation.
        value : float
            Value estimate.
        log_prob : float
            Log probability of the unscaled action.
        """
        action, value, log_prob = super().select_action(obs)
        # Scale the action by the curriculum scale to smoothly introduce hardness
        scaled_action = action * self.curriculum_scale
        return scaled_action, value, log_prob

    def update(self, rollout_data, last_value=0.0):
        """PPO update with negated rewards.
        
        Since rollout_data typically contains the defender's reward (which we
        want to minimize), we negate the rewards and values to maximize the
        adversarial objective.
        
        Parameters
        ----------
        rollout_data : dict
            Dictionary containing rollout transitions.
        last_value : float, optional
            Value estimate at the bootstrap step ``T``.
            
        Returns
        -------
        dict
            Dictionary of training metrics.
        """
        # Make a copy of rollout data to avoid modifying the caller's buffer directly
        adv_rollout_data = dict(rollout_data)
        
        # Negate rewards and values to formulate the minimax objective
        # (Attacker wants to minimize defender's reward -> maximize -reward)
        adv_rollout_data['rewards'] = -np.array(rollout_data['rewards'])
        adv_rollout_data['values'] = -np.array(rollout_data['values'])
        last_value_adv = -last_value
        
        # Call standard PPO update with the inverted rewards
        return super().update(adv_rollout_data, last_value=last_value_adv)
