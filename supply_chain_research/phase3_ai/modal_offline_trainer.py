"""Modal wrapper for cloud Offline RL (Decision Transformer) on A100 GPUs."""

import modal

app = modal.App("supply-chain-offline-trainer")

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
        "h5py",
    )
    .add_local_dir("supply_chain_research", remote_path="/app/supply_chain_research")
)

vol = modal.Volume.from_name("supply-chain-runs", create_if_missing=True)
data_vol = modal.Volume.from_name("supply-chain-data", create_if_missing=True)

@app.function(
    image=image,
    gpu="A100",
    timeout=12 * 3600,
    volumes={"/root/outputs": vol, "/root/data": data_vol},
)
def train_offline():
    import json
    import os
    import sys
    import time

    os.chdir("/app")
    sys.path.insert(0, "/app")

    from loguru import logger

    from supply_chain_research.phase3_ai.offline_trainer import OfflineTrainer

    run_name = f"dt_offline_cloud_{int(time.time())}"
    logger.info(f"Starting Offline RL (DT) cloud training on A100. Run name: {run_name}")

    # Data leakage check: enforce distinct training dataset
    train_data_path = "/root/data/offline_rl_expert_train.h5"
    if not os.path.exists(train_data_path):
        raise FileNotFoundError(f"Training data not found at {train_data_path}. Please upload it to 'supply-chain-data' volume first to prevent data leakage.")

    trainer = OfflineTrainer(
        hdf5_path=train_data_path,
        output_root="/root/outputs",
    )
    trainer.train(epochs=10, batch_size=256)

    manifest = {
        "run_name": run_name,
        "epochs": 10,
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
def main():
    call = train_offline.spawn()
    print(f"✓ Launched Offline trainer on Modal in the background. Call ID: {call.object_id}")
    print("Waiting for training to complete to keep the Modal app 'running'...")
    call.get()
    print("✓ Training completed!")
