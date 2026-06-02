"""Modal wrapper for cloud Adversarial RL training on A100 GPUs."""

import modal

app = modal.App("supply-chain-adversarial-trainer")

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
def train_adversarial(total_timesteps: int = 500_000):
    import json
    import os
    import sys
    import time

    os.chdir("/app")
    sys.path.insert(0, "/app")

    from loguru import logger

    from supply_chain_research.phase3_ai.adversarial_trainer import AdversarialTrainer

    run_name = f"adversarial_cloud_{int(time.time())}"
    logger.info(f"Starting Adversarial cloud training on A100. Run name: {run_name}")

    trainer = AdversarialTrainer(
        run_name=run_name,
        device="cuda",
        output_root="/root/outputs",
    )
    trainer.train(total_timesteps=total_timesteps)

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
    logger.info(
        f"Download with: modal volume get supply-chain-runs models/{run_name} ./models/{run_name}"
    )
    return manifest

@app.local_entrypoint()
def main(timesteps: int = 500_000):
    call = train_adversarial.spawn(total_timesteps=timesteps)
    print(f"✓ Launched Adversarial trainer on Modal in the background. Call ID: {call.object_id}")
    print("Waiting for training to complete to keep the Modal app 'running'...")
    call.get()
    print("✓ Training completed!")
