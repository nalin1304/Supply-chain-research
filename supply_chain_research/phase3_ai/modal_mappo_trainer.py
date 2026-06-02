"""Modal wrapper for cloud MAPPO training on A100 GPUs.

The local entrypoint intentionally calls ``.spawn()`` so the remote
training function keeps running after the local terminal disconnects.
Outputs are written to the persistent ``supply-chain-runs`` volume.
"""

import modal

app = modal.App("supply-chain-mappo-trainer")

image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "numpy==2.4.2",
        "pandas==3.0.1",
        "scipy==1.17.1",
        "tqdm==4.67.3",
        "loguru==0.7.3",
        "gymnasium==1.3.0",
        "tensorboard==2.20.0",
        "torch==2.10.0",
        "pydantic==2.12.5",
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
def train_mappo(total_timesteps: int = 1_000_000, use_cvar: bool = False, cvar_alpha: float = 0.10):
    """
    Parameters
    ----------
    """
    import json
    import os
    import sys
    import time

    os.chdir("/app")
    sys.path.insert(0, "/app")

    from loguru import logger

    from supply_chain_research.phase3_ai.mappo_trainer import MAPPOTrainer

    total_timesteps = int(total_timesteps)
    if not 1_000 <= total_timesteps <= 5_000_000:
        raise ValueError("total_timesteps must be between 1,000 and 5,000,000")

    run_name = f"mappo_cloud_{int(time.time())}"
    logger.info(f"Starting MAPPO cloud training on A100. Run name: {run_name}")

    from supply_chain_research.config import PPOConfig
    
    ppo_config = PPOConfig()
    ppo_config.use_cvar_objective = use_cvar
    ppo_config.cvar_alpha = float(cvar_alpha)

    trainer = MAPPOTrainer(
        run_name=run_name,
        device="cuda",
        ppo_config=ppo_config,
        output_root="/root/outputs",
        domain_randomization=True,
    )
    trainer.train(total_timesteps=total_timesteps)

    manifest = {
        "run_name": run_name,
        "total_timesteps": total_timesteps,
        "gpu": "A100",
        "domain_randomization": True,
        "cvar_alpha": float(cvar_alpha) if use_cvar else None,
        "model_dir": f"models/{run_name}",
        "log_dir": f"runs/{run_name}",
    }
    manifest_path = f"/root/outputs/{run_name}_manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
    vol.commit()

    logger.info("Training complete. Outputs saved to Modal volume 'supply-chain-runs'.")
    logger.info(
        f"Download with: modal volume get supply-chain-runs models/{run_name} ./models/{run_name}"
    )
    return manifest


@app.local_entrypoint()
def main(timesteps: int = 1_000_000, use_cvar: bool = False, cvar_alpha: float = 0.10):
    """
    Parameters
    ----------
    """
    timesteps = int(timesteps)
    if not 1_000 <= timesteps <= 5_000_000:
        raise ValueError("timesteps must be between 1,000 and 5,000,000")

    est_hours = max(0.05, timesteps / 1_000_000 * 1.5)
    est_cost = est_hours * 3.42
    print("Spawning MAPPO training job to Modal (A100)...")
    print(f"  Timesteps             : {timesteps:,}")
    print(f"  Estimated cost        : ~${est_cost:.2f} at A100 public pricing")
    print("  Domain randomization  : enabled")
    print(f"  CVaR optimization     : {'enabled (alpha=' + str(cvar_alpha) + ')' if use_cvar else 'disabled'}")
    job = train_mappo.spawn(total_timesteps=timesteps, use_cvar=use_cvar, cvar_alpha=cvar_alpha)
    print(f"Job spawned successfully. Job ID: {job.object_id}")
    print("Track progress with: modal app logs supply-chain-mappo-trainer")
