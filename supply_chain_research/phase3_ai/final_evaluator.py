import os
import sys


def run_adversarial_eval():
    from supply_chain_research.phase3_ai.sim2real_evaluator import evaluate_robustness
    print("=== ADVERSARIAL ROBUSTNESS ===")
    results = evaluate_robustness(
        standard_model_path="dummy.pt",
        adversarial_model_path="models/models/adversarial_cloud_1780342379/adversarial_defender.pt",
        n_customers=100,
        n_warehouses=5,
        seed=42,
        episodes=5
    )
    for k, v in results.items():
        print(f"{k}: Mean Cost {v['mean_cost']:.2f}, Std {v['std_cost']:.2f}")

def run_morl_eval():
    from supply_chain_research.config import MasterConfig
    from supply_chain_research.phase3_ai.morl_agent import MORLAgent
    from supply_chain_research.phase3_ai.morl_env import MultiObjectiveSupplyChainEnv
    from supply_chain_research.phase3_ai.morl_evaluator import extract_pareto_front
    
    print("\n=== MORL PARETO FRONT ===")
    config = MasterConfig.derive_from_problem_size(100, 5)
    env = MultiObjectiveSupplyChainEnv(n_customers=100, n_warehouses=5, config=config, seed=42, stress_mode=True)
    
    agent = MORLAgent(obs_dim=env.obs_dim, action_dim=env.action_dim, config=config.ppo)
    agent.load("models/models/morl_cloud_1780342527/model.pt")
    
    front = extract_pareto_front(agent, env, episodes_per_weight=2)
    for cost, carbon in front:
        print(f"Cost: {cost:.2f}, Carbon: {carbon:.2f}")

if __name__ == "__main__":
    sys.path.insert(0, os.path.abspath("."))
    # run_adversarial_eval()
    run_morl_eval()
