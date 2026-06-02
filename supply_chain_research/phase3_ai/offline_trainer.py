"""Offline RL Trainer (Phase 12).

Trains the Decision Transformer on the exported HDF5 offline dataset.
"""

import time
from pathlib import Path

import h5py
import numpy as np
import torch
import torch.nn.functional as F
from loguru import logger
from torch.utils.data import DataLoader, Dataset
from torch.utils.tensorboard import SummaryWriter

from supply_chain_research.phase3_ai.decision_transformer import DecisionTransformer


class OfflineRLDataset(Dataset):
    """Loads trajectories from HDF5 exported by data_collector.py."""
    def __init__(self, hdf5_path, seq_len=30):
        self.seq_len = seq_len
        
        with h5py.File(hdf5_path, 'r') as f:
            self.states = f['states'][:]
            self.actions = f['actions'][:]
            self.rewards = f['rewards'][:]
            self.rtg = f['rtg'][:]
            
        self.num_samples = len(self.states)
        
    def __len__(self):
        return self.num_samples
        
    def __getitem__(self, idx):
        # Time steps for positional encoding
        timesteps = np.arange(self.seq_len)
        
        s = torch.FloatTensor(self.states[idx])
        a = torch.FloatTensor(self.actions[idx])
        rtg = torch.FloatTensor(self.rtg[idx]).unsqueeze(-1)
        t = torch.LongTensor(timesteps)
        
        return s, a, rtg, t


class OfflineTrainer:
    def __init__(self, hdf5_path, output_root="."):
        self.hdf5_path = hdf5_path
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        
        run_name = f"dt_offline_{int(time.time())}"
        self.save_dir = Path(output_root) / "models" / run_name
        self.save_dir.mkdir(parents=True, exist_ok=True)
        
        self.writer = SummaryWriter(log_dir=str(Path(output_root) / "runs" / run_name))

    def train(self, epochs=50, batch_size=64, lr=1e-4):
        logger.info(f"Loading dataset from {self.hdf5_path}")
        dataset = OfflineRLDataset(self.hdf5_path)
        loader = DataLoader(dataset, batch_size=batch_size, shuffle=True, drop_last=True)
        
        # State dim = 4 [Inventory, Forecast, LeadTime, Promo]
        # Action dim = 1 [Order_Quantity]
        model = DecisionTransformer(
            state_dim=4,
            act_dim=1,
            max_length=30,
            max_ep_len=400,
            hidden_size=128,
            n_layer=3,
            n_head=4,
            dropout=0.1,
        ).to(self.device)
        
        optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
        
        logger.info(f"Starting Offline Training on {self.device}...")
        
        global_step = 0
        best_loss = float('inf')
        
        for epoch in range(epochs):
            model.train()
            epoch_losses = []
            
            for s, a, rtg, t in loader:
                s, a, rtg, t = s.to(self.device), a.to(self.device), rtg.to(self.device), t.to(self.device)
                
                optimizer.zero_grad()
                
                # Predict action
                a_preds = model(s, a, rtg, t)
                
                # MSE loss against the true expert actions
                loss = F.mse_loss(a_preds, a)
                
                loss.backward()
                torch.nn.utils.clip_grad_norm_(model.parameters(), 0.25)
                optimizer.step()
                
                epoch_losses.append(loss.item())
                self.writer.add_scalar("Train/ActionMSE", loss.item(), global_step)
                global_step += 1
                
            mean_loss = np.mean(epoch_losses)
            logger.info(f"Epoch {epoch+1}/{epochs} | Action MSE Loss: {mean_loss:.4f}")
            
            if mean_loss < best_loss:
                best_loss = mean_loss
                torch.save(model.state_dict(), self.save_dir / "best_dt_agent.pt")
                logger.info(f"New best model saved! (Loss: {best_loss:.4f})")
                
        torch.save(model.state_dict(), self.save_dir / "final_dt_agent.pt")
        self.writer.close()
        logger.info("Decision Transformer Offline Training Complete.")

if __name__ == "__main__":
    base_dir = Path(__file__).parent.parent.parent
    hdf5_path = base_dir / "data" / "processed" / "offline_rl_expert.h5"
    if hdf5_path.exists():
        trainer = OfflineTrainer(str(hdf5_path), output_root=str(base_dir))
        trainer.train(epochs=10)
    else:
        logger.error(f"HDF5 dataset not found at {hdf5_path}. Run data_collector.py first.")
