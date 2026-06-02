"""MORL Evaluator (Phase 14).

Extracts the Pareto Front from a trained MORLAgent by sweeping the preference
weight omega. Compares it against the NSGA-II baseline using JNHV.
"""


import numpy as np
from loguru import logger

from supply_chain_research.config import MasterConfig
from supply_chain_research.phase3_ai.morl_agent import MORLAgent
from supply_chain_research.phase3_ai.morl_env import MultiObjectiveSupplyChainEnv


def extract_pareto_front(agent, env, episodes_per_weight=5):
    """
    Sweeps omega from [1, 0] to [0, 1] in steps of 0.1 to extract the Pareto Front.
    Returns a list of (cost, carbon) tuples representing the front.
    """
    front = []
    
    weights = np.linspace(0.0, 1.0, 11) # 0.0, 0.1, ..., 1.0
    
    for w in weights:
        env.set_preference(w)
        
        costs = []
        carbons = []
        
        for _ in range(episodes_per_weight):
            obs, _ = env.reset(options={'randomize_omega': False})
            done = False
            ep_cost = 0.0
            ep_carbon = 0.0
            
            while not done:
                action, _, _ = agent.select_action(obs)
                obs, reward_vec, term, trunc, info = env.step(action)
                done = term or trunc
                
                # Undo normalization to get true values for evaluation
                # Note: reward_vec was [-cost/10000, -carbon/100]
                ep_cost += -reward_vec[0] * 10000.0
                ep_carbon += -reward_vec[1] * 100.0
                
            costs.append(ep_cost)
            carbons.append(ep_carbon)
            
        mean_cost = np.mean(costs)
        mean_carbon = np.mean(carbons)
        front.append((mean_cost, mean_carbon))
        logger.info(f"Omega (Cost={w:.1f}, Carbon={1.0-w:.1f}) -> Cost: {mean_cost:.2f}, Carbon: {mean_carbon:.2f}")
        
    return front

def test_dynamic_preference_shift(agent, env, shift_timestep=180):
    """
    Tests the MORL agent's zero-shot ability to adapt to a sudden 
    preference shift mid-episode.
    Starts with 100% Cost focus (omega=[1.0, 0.0]).
    At shift_timestep, abruptly switches to 100% Carbon focus (omega=[0.0, 1.0]).
    """
    logger.info(f"--- Running Dynamic Preference Shift Test (Shift at t={shift_timestep}) ---")
    
    env.set_preference(1.0) # 100% Cost
    obs, _ = env.reset(options={'randomize_omega': False})
    
    done = False
    t = 0
    
    cost_before, carbon_before = 0.0, 0.0
    cost_after, carbon_after = 0.0, 0.0
    
    while not done:
        # Abrupt ESG policy change
        if t == shift_timestep:
            logger.info(f"Timestep {t}: Abrupt shift from Cost (1.0) to Carbon (1.0) focus!")
            env.set_preference(0.0) # 100% Carbon
            # Inject new omega into observation without resetting env
            obs[-2:] = env.current_omega
            
        action, _, _ = agent.select_action(obs)
        obs, reward_vec, term, trunc, info = env.step(action)
        done = term or trunc
        
        c = -reward_vec[0] * 10000.0
        carb = -reward_vec[1] * 100.0
        
        if t < shift_timestep:
            cost_before += c
            carbon_before += carb
        else:
            cost_after += c
            carbon_after += carb
            
        t += 1
        
    logger.info(f"Phase 1 (Cost Focus)   -> Avg Cost/step: {cost_before/shift_timestep:.2f}, Avg Carbon/step: {carbon_before/shift_timestep:.2f}")
    steps_after = t - shift_timestep
    logger.info(f"Phase 2 (Carbon Focus) -> Avg Cost/step: {cost_after/steps_after:.2f}, Avg Carbon/step: {carbon_after/steps_after:.2f}")
    return True

def compute_jnhv(morl_front, nsga2_front, reference_point):
    """
    Computes the Joint-Normalized Hypervolume (JNHV) to compare fronts.
    Requires pymoo's HV indicator.
    """
    from pymoo.indicators.hv import HV
    
    # Normalize fronts
    combined = np.vstack([morl_front, nsga2_front])
    min_vals = combined.min(axis=0)
    max_vals = combined.max(axis=0)
    
    def normalize(front):
        # Add epsilon to prevent division by zero
        return (np.array(front) - min_vals) / (max_vals - min_vals + 1e-8)
        
    norm_morl = normalize(morl_front)
    norm_nsga2 = normalize(nsga2_front)
    
    ind = HV(ref_point=np.array(reference_point))
    
    hv_morl = ind(norm_morl)
    hv_nsga2 = ind(norm_nsga2)
    
    return hv_morl, hv_nsga2

if __name__ == "__main__":
    logger.info("Initializing MORL Pareto Front Extraction...")
    
    config = MasterConfig.derive_from_problem_size(100, 5)
    env = MultiObjectiveSupplyChainEnv(
        n_customers=100, n_warehouses=5, config=config, stress_mode=True
    )
    
    agent = MORLAgent(
        obs_dim=env.obs_dim,
        action_dim=env.action_dim,
    )
    
    # In a real scenario, we would load the trained agent here:
    # agent.actor.load_state_dict(torch.load("models/best_morl_agent.pt")['actor'])
    
    logger.info("Sweeping omega values...")
    morl_front = extract_pareto_front(agent, env, episodes_per_weight=1)
    
    # Dummy NSGA-II front for demonstration (simulating classical GA results)
    nsga2_front = [
        (c * 1.1, carb * 1.1) for c, carb in morl_front 
    ]
    
    # Reference point for JNHV (normalized space is [0, 1], so [1.1, 1.1] is a safe reference)
    hv_morl, hv_nsga2 = compute_jnhv(morl_front, nsga2_front, reference_point=[1.1, 1.1])
    
    logger.info(f"MORL Hypervolume: {hv_morl:.4f}")
    logger.info(f"NSGA-II Hypervolume: {hv_nsga2:.4f}")
    
    if hv_morl >= hv_nsga2:
        logger.info("MORL successfully matched or exceeded NSGA-II Pareto Front quality.")
    else:
        logger.info("MORL did not exceed NSGA-II Pareto Front quality (Expected if agent is untrained).")
        
    # Test Dynamic Preference Shift
    test_dynamic_preference_shift(agent, env, shift_timestep=180)
