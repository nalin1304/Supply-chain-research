"""Modal wrapper for Cloud Training MAPPO on A100 GPUs.

Submits the training job to Modal with all necessary dependencies and 
syncs the resulting Tensorboard logs and model weights back to the 
local machine.
"""

import os
import modal

# Define the Modal App
app = modal.App("supply-chain-mappo-trainer")

# Define the container image with all dependencies
# We use a base Debian image with Python and install our requirements
image = (
    modal.Image.debian_slim(python_version="3.10")
    .pip_install(
        "numpy==2.4.2",
        "pandas==3.0.1",
        "scipy==1.17.1",
        "tqdm==4.67.3",
        "loguru==0.7.3",
        "gymnasium==1.3.0",
        "tensorboard==2.20.0",
        "torch==2.10.0",
        "pydantic==2.12.5"
    )
)

# Define the remote volume to persist models and logs
vol = modal.Volume.from_name("supply-chain-runs", create_if_missing=True)

# Mount the entire local supply_chain_research directory into the container
source_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)))
remote_source = modal.Mount.from_local_dir(source_dir, remote_path="/root/supply_chain_research")


@app.function(
    image=image,
    gpu="A100",  # Requesting A100 GPU
    timeout=86400,  # Allow up to 24 hours
    volumes={"/root/outputs": vol},
    mounts=[remote_source]
)
def train_mappo(total_timesteps: int = 1_000_000):
    import sys
    sys.path.append("/root")
    
    from loguru import logger
    from supply_chain_research.phase3_ai.mappo_trainer import MAPPOTrainer
    import time
    
    run_name = f"mappo_cloud_{int(time.time())}"
    logger.info(f"Starting cloud training on A100! Run Name: {run_name}")
    
    # Run the trainer. Force the trainer to save to the persistent volume
    trainer = MAPPOTrainer(run_name=run_name, device="cuda")
    
    # Overwrite the save directories so they end up on the Modal Volume
    trainer.save_dir = f"/root/outputs/models/{run_name}"
    trainer.writer.log_dir = f"/root/outputs/runs/{run_name}"
    os.makedirs(trainer.save_dir, exist_ok=True)
    os.makedirs(trainer.writer.log_dir, exist_ok=True)
    
    trainer.train(total_timesteps=total_timesteps)
    
    logger.info(f"Training Complete! Models and logs saved to Modal volume 'supply-chain-runs'.")
    logger.info(f"To download them, you can run: modal volume get supply-chain-runs models/{run_name} ./models")


@app.local_entrypoint()
def main(timesteps: int = 1_000_000):
    print("🚀 Spawning MAPPO Training Job to Modal (A100)...")
    # Use .spawn() so the job runs asynchronously and detaches from the local terminal
    job = train_mappo.spawn(total_timesteps=timesteps)
    print(f"✅ Job spawned successfully! Job ID: {job.object_id}")
    print("You can safely close this terminal. Track progress at https://modal.com/apps")
