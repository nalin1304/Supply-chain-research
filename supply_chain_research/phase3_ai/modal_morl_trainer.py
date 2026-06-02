"""Modal wrapper for cloud Multi-Objective RL training on A100 GPUs."""

import modal

app = modal.App("supply-chain-morl-trainer")

image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "numpy",
        "pandas",
        "scipy",
        "tqdm",
        "loguru",
        "gymnasium",
        "tensorboard",
        "torch",
        "pydantic",
    )
    .add_local_dir("supply_chain_research", remote_path="/app/supply_chain_research")
)

vol = modal.Volume.from_name("supply-chain-runs", create_if_missing=True)

@app.function(
    image=image,
    gpu="A100",
    timeout=12 * 3600,
    volumes={"/root/outputs": vol},
)
def train_morl(total_timesteps: int = 500_000):
    import json
    import os
    import sys
    import time

    os.chdir("/app")
    sys.path.insert(0, "/app")

    import numpy as np
    from loguru import logger

    from supply_chain_research.config import MasterConfig
    from supply_chain_research.phase3_ai.morl_agent import MORLAgent
    from supply_chain_research.phase3_ai.morl_env import MultiObjectiveSupplyChainEnv

    run_name = f"morl_cloud_{int(time.time())}"
    logger.info(f"Starting MORL cloud training on A100. Run name: {run_name}")
    
    config = MasterConfig.derive_from_problem_size(100, 5)
    env = MultiObjectiveSupplyChainEnv(
        n_customers=config.network.n_customers, 
        n_warehouses=config.network.n_warehouses, 
        config=config, 
        stress_mode=True
    )
    
    agent = MORLAgent(
        obs_dim=env.obs_dim,
        action_dim=env.action_dim,
        device="cuda"
    )
    
    # Real MORL PPO Rollout and Update Loop
    global_step = 0
    obs, _ = env.reset(options={'randomize_omega': True})
    
    rollout_steps = 2048
    
    while global_step < total_timesteps:
        rollout_data = {
            'observations': [],
            'actions': [],
            'rewards': [],
            'values': [],
            'log_probs': [],
            'dones': []
        }
        
        episode_rewards = []
        episode_costs = []
        episode_carbons = []
        
        for _ in range(rollout_steps):
            action, val_vec, log_prob = agent.select_action(obs)
            next_obs, reward_vec, term, trunc, info = env.step(action)
            done = term or trunc
            
            rollout_data['observations'].append(obs)
            rollout_data['actions'].append(action)
            rollout_data['rewards'].append(reward_vec)  # (2,) vector
            rollout_data['values'].append(val_vec)      # (2,) vector
            rollout_data['log_probs'].append(log_prob)
            rollout_data['dones'].append(float(done))
            
            obs = next_obs
            global_step += 1
            
            if done:
                episode_costs.append(info.get('total_logistics_cost', 0))
                episode_carbons.append(info.get('total_emissions', 0))
                obs, _ = env.reset(options={'randomize_omega': True})
                
            if global_step >= total_timesteps:
                break
        
        # Convert lists to numpy arrays
        for k in rollout_data:
            rollout_data[k] = np.array(rollout_data[k])
            
        # Perform PPO update on the rollout buffer
        metrics = agent.update(rollout_data)
        
        if len(episode_costs) > 0:
            mean_cost = np.mean(episode_costs)
            mean_carbon = np.mean(episode_carbons)
            logger.info(f"Step {global_step}/{total_timesteps} | Cost: {mean_cost:.2f} | Carbon: {mean_carbon:.2f} | ActLoss: {metrics['actor_loss']:.4f}")

    # Save the real trained model
    out_dir = f"/root/outputs/models/{run_name}"
    os.makedirs(out_dir, exist_ok=True)
    agent.save(f"{out_dir}/model.pt")

    manifest = {
        "run_name": run_name,
        "total_timesteps": total_timesteps,
        "gpu": "A100",
        "model_dir": f"models/{run_name}",
        "log_dir": f"runs/{run_name}",
    }
    manifest_path = f"/root/outputs/{run_name}_manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
    vol.commit()

    logger.info("Training complete. Outputs saved to Modal volume 'supply-chain-runs'.")
    return manifest

@app.local_entrypoint()
def main(timesteps: int = 500_000):
    call = train_morl.spawn(total_timesteps=timesteps)
    print(f"✓ Launched MORL trainer on Modal in the background. Call ID: {call.object_id}")
    print("Waiting for training to complete to keep the Modal app 'running'...")
    call.get()
    print("✓ Training completed!")
