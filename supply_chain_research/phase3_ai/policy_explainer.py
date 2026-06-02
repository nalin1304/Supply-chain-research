"""Phase 9: Explainable AI (XAI) for MAPPO Policy.

Extracts a human-readable Decision Tree from the neural policy and computes feature attributions.
"""

import numpy as np
from loguru import logger
from sklearn.inspection import permutation_importance
from sklearn.tree import DecisionTreeRegressor, export_text

from supply_chain_research.config import MasterConfig, PPOConfig
from supply_chain_research.phase3_ai.mappo_agent import MAPPOAgent
from supply_chain_research.phase3_ai.marl_env import MultiAgentSupplyChainEnv


class PolicyExplainer:
    def __init__(self, model_path: str, n_episodes: int = 10, max_tree_depth: int = 5):
        """
        Initialize the policy explainer.
        """
        self.model_path = model_path
        self.n_episodes = n_episodes
        self.max_tree_depth = max_tree_depth
        
        self.config = MasterConfig()
        self.ppo_config = PPOConfig()
        
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
            device="cpu",
        )
        self.agent.load(model_path)
        
        # Build feature names
        self.feature_names = ["Warehouse_Inventory"]
        
        n_customers = self.config.network.n_customers
        horizon = self.config.lstm.forecast_horizon
        
        for c in range(n_customers):
            for d in range(horizon):
                self.feature_names.append(f"Forecast_C{c}_D{d}")
                
        self.feature_names.append("Warehouse_Shock")
        
        for c in range(n_customers):
            self.feature_names.append(f"Customer_{c}_Shock")
            
        self.feature_names.append("Time_Fraction")
        
        if len(self.feature_names) != self.env.local_obs_dim:
            logger.warning(f"Feature name count ({len(self.feature_names)}) doesn't match local obs dim ({self.env.local_obs_dim})")
            # Pad or truncate
            if len(self.feature_names) < self.env.local_obs_dim:
                self.feature_names.extend([f"Feature_{i}" for i in range(len(self.feature_names), self.env.local_obs_dim)])
            else:
                self.feature_names = self.feature_names[:self.env.local_obs_dim]

    def collect_data(self):
        """Rollout policy to collect (state, action) dataset."""
        logger.info(f"Collecting data for {self.n_episodes} episodes...")
        X, y = [], []
        
        for ep in range(self.n_episodes):
            local_obs, global_obs, _ = self.env.reset()
            done = False
            
            while not done:
                actions_dict, _, _ = self.agent.select_actions(local_obs, global_obs)
                
                for agent_id in range(self.env.n_agents):
                    X.append(local_obs[agent_id])
                    y.append(actions_dict[agent_id])
                
                local_obs, global_obs, _, terminations, truncations, _ = self.env.step(actions_dict)
                done = terminations[0] or truncations[0]
                
        return np.array(X), np.array(y).squeeze()

    def explain(self):
        """Extract a surrogate tree and compute permutation importance."""
        X, y = self.collect_data()
        
        logger.info(f"Collected {len(X)} samples. Fitting Decision Tree...")
        tree = DecisionTreeRegressor(max_depth=self.max_tree_depth, random_state=42)
        tree.fit(X, y)
        
        score = tree.score(X, y)
        logger.info(f"Surrogate Tree R^2 Score (Fidelity): {score:.4f}")
        
        logger.info("Decision Tree Rules:")
        rules = export_text(tree, feature_names=self.feature_names)
        print(rules)
        
        logger.info("Computing Feature Attributions (Permutation Importance)...")
        result = permutation_importance(tree, X, y, n_repeats=5, random_state=42, n_jobs=-1)
        
        importances = result.importances_mean
        sorted_idx = importances.argsort()[::-1]
        
        print("\nTop 15 Feature Importances:")
        for i in range(min(15, len(sorted_idx))):
            idx = sorted_idx[i]
            print(f"{self.feature_names[idx]}: {importances[idx]:.4f} +/- {result.importances_std[idx]:.4f}")
        
        return tree, score

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=str, required=True, help="Path to MAPPO model checkpoint")
    parser.add_argument("--episodes", type=int, default=10, help="Number of episodes to rollout")
    args = parser.parse_args()
    
    explainer = PolicyExplainer(args.model, n_episodes=args.episodes)
    explainer.explain()
