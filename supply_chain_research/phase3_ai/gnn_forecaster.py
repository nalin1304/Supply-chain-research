"""Spatio-Temporal Graph Neural Network (ST-GNN) for demand forecasting.

This module implements an Adaptive Graph Convolutional Network (AGCN) combined 
with Temporal Convolutional Networks (TCN) or LSTMs to capture both spatial 
dependencies (correlation between customers) and temporal dynamics.

Since fixed geographical distances are not strictly maintained in the abstract 
demand generator, this model uses a Learnable Adjacency Matrix (Adaptive Graph) 
to infer the hidden spatial correlations directly from the demand data.

References:
    - Wu et al. (2019). Graph Wavenet for Deep Spatial-Temporal Graph Modeling.
    - Bai et al. (2020). Adaptive Graph Convolutional Recurrent Network.
"""

import math

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from loguru import logger
from torch.utils.data import DataLoader, TensorDataset

from supply_chain_research.phase3_ai.forecaster_base import BaseForecaster


class AdaptiveGraphConvolution(nn.Module):
    """Adaptive Graph Convolution Layer.
    
    Uses node embeddings to generate a graph adjacency matrix dynamically.
    
    Parameters
    ----------
    """
    def __init__(self, in_features: int, out_features: int, n_nodes: int, embed_dim: int = 10):
        """
        Parameters
        ----------
        """
        super().__init__()
        self.in_features = in_features
        self.out_features = out_features
        self.n_nodes = n_nodes
        
        # Node embeddings to construct the adaptive adjacency matrix
        self.node_embed1 = nn.Parameter(torch.randn(n_nodes, embed_dim))
        self.node_embed2 = nn.Parameter(torch.randn(embed_dim, n_nodes))
        
        # GCN weights
        self.weight = nn.Parameter(torch.Tensor(in_features, out_features))
        self.bias = nn.Parameter(torch.Tensor(out_features))
        
        self.reset_parameters()

    def reset_parameters(self):
        """
        Parameters
        ----------
        """
        stdv = 1. / math.sqrt(self.weight.size(1))
        self.weight.data.uniform_(-stdv, stdv)
        self.bias.data.uniform_(-stdv, stdv)
        nn.init.xavier_uniform_(self.node_embed1)
        nn.init.xavier_uniform_(self.node_embed2)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Args:
            x: Tensor of shape (batch_size, n_nodes, in_features)
        Returns:
            Tensor of shape (batch_size, n_nodes, out_features)
        
        Parameters
        ----------
        """
        # Calculate adaptive adjacency matrix: A = Softmax(ReLU(E1 * E2))
        adj = F.relu(torch.matmul(self.node_embed1, self.node_embed2))
        # Normalize adjacency matrix over nodes
        adj = F.softmax(adj, dim=1)
        
        # Graph convolution: Z = A * X * W
        # x shape: (B, N, C_in)
        # adj shape: (N, N)
        # x_w shape: (B, N, C_out)
        x_w = torch.matmul(x, self.weight)
        
        # output shape: (B, N, C_out)
        out = torch.einsum('vw,bwc->bvc', adj, x_w) + self.bias
        return out


class STGNNModel(nn.Module):
    """Spatio-Temporal Graph Neural Network.
    Parameters
    ----------
    """
    def __init__(
        self,
        n_nodes: int,
        seq_length: int,
        horizon: int,
        gcn_hidden: int = 64,
        rnn_hidden: int = 128,
        embed_dim: int = 10,
        dropout: float = 0.2
    ):
        """
        Parameters
        ----------
        """
        super().__init__()
        self.n_nodes = n_nodes
        self.seq_length = seq_length
        self.horizon = horizon
        
        # Spatial layer: GCN
        self.gcn1 = AdaptiveGraphConvolution(1, gcn_hidden, n_nodes, embed_dim)
        self.gcn2 = AdaptiveGraphConvolution(gcn_hidden, gcn_hidden, n_nodes, embed_dim)
        
        # Temporal layer: GRU
        # Input to GRU is the flattened spatial features over all nodes
        self.gru = nn.GRU(
            input_size=n_nodes * gcn_hidden,
            hidden_size=rnn_hidden,
            num_layers=2,
            batch_first=True,
            dropout=dropout
        )
        
        # Output projection
        self.fc = nn.Sequential(
            nn.Linear(rnn_hidden, 256),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(256, n_nodes * horizon)
        )
        
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Args:
            x: Input of shape (batch_size, seq_length, n_nodes)
        Returns:
            Output of shape (batch_size, horizon, n_nodes)
        
        Parameters
        ----------
        """
        b, s, n = x.shape
        
        # Process each time step through the GCN
        # Reshape to (B*S, N, 1) to apply GCN across all spatial graphs
        x_gcn = x.reshape(b * s, n, 1)
        
        h_gcn = F.relu(self.gcn1(x_gcn))
        h_gcn = F.relu(self.gcn2(h_gcn))  # Shape: (B*S, N, GCN_HIDDEN)
        
        # Reshape back for GRU: (B, S, N * GCN_HIDDEN)
        h_gcn = h_gcn.reshape(b, s, n * self.gcn1.out_features)
        
        # Temporal processing
        gru_out, _ = self.gru(h_gcn)
        
        # Take the last hidden state: (B, RNN_HIDDEN)
        last_hidden = gru_out[:, -1, :]
        
        # Predict horizon: (B, N * HORIZON)
        out = self.fc(last_hidden)
        
        # Reshape to (B, HORIZON, N)
        return out.reshape(b, self.horizon, n)


class GNNForecaster(BaseForecaster):
    """Forecaster wrapper for the ST-GNN Model.
    Parameters
    ----------
    """
    def __init__(
        self,
        seq_length: int = 30,
        batch_size: int = 64,
        epochs: int = 50,
        lr: float = 1e-3,
        gcn_hidden: int = 32,
        rnn_hidden: int = 128,
        device: str = "auto",
        seed: int | None = None,
    ):
        """
        Parameters
        ----------
        """
        self.seq_length = seq_length
        self.batch_size = batch_size
        self.epochs = epochs
        self.lr = lr
        self.gcn_hidden = gcn_hidden
        self.rnn_hidden = rnn_hidden
        self.seed = seed
        
        if device == "auto":
            self.device = torch.device(
                "cuda" if torch.cuda.is_available() else 
                "mps" if torch.backends.mps.is_available() else "cpu"
            )
        else:
            self.device = torch.device(device)
            
        self.model = None
        self.train_history = None

    def _create_sequences(self, data: np.ndarray, horizon: int):
        """Create sequences of shape (seq_length) predicting (horizon).
        Parameters
        ----------
        """
        n_days, n_nodes = data.shape
        n_samples = n_days - self.seq_length - horizon + 1
        
        X = np.zeros((n_samples, self.seq_length, n_nodes), dtype=np.float32)
        y = np.zeros((n_samples, horizon, n_nodes), dtype=np.float32)
        
        for i in range(n_samples):
            X[i] = data[i : i + self.seq_length]
            y[i] = data[i + self.seq_length : i + self.seq_length + horizon]
            
        return torch.tensor(X), torch.tensor(y)

    def fit(self, train_data: np.ndarray, val_data: np.ndarray = None) -> None:
        """Train the ST-GNN model.
        Parameters
        ----------
        """
        self.train_history = train_data
        if self.seed is not None:
            np.random.seed(self.seed)
            torch.manual_seed(self.seed)
        n_nodes = train_data.shape[1]
        
        # We assume predict() will be called for horizon=7 by default in CV
        horizon = 7
        
        X_train, y_train = self._create_sequences(train_data, horizon)
        
        train_dataset = TensorDataset(X_train, y_train)
        train_loader = DataLoader(train_dataset, batch_size=self.batch_size, shuffle=True)
        
        self.model = STGNNModel(
            n_nodes=n_nodes,
            seq_length=self.seq_length,
            horizon=horizon,
            gcn_hidden=self.gcn_hidden,
            rnn_hidden=self.rnn_hidden
        ).to(self.device)
        
        optimizer = torch.optim.AdamW(self.model.parameters(), lr=self.lr, weight_decay=1e-4)
        criterion = nn.HuberLoss(delta=1.0)
        scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
            optimizer, mode='min', factor=0.5, patience=5
        )
        
        logger.info(f"Training ST-GNN on {self.device} for {self.epochs} epochs...")
        
        best_loss = float('inf')
        patience = 10
        patience_counter = 0
        
        for epoch in range(self.epochs):
            self.model.train()
            epoch_loss = 0.0
            for batch_x, batch_y in train_loader:
                batch_x, batch_y = batch_x.to(self.device), batch_y.to(self.device)
                
                optimizer.zero_grad()
                preds = self.model(batch_x)
                loss = criterion(preds, batch_y)
                loss.backward()
                torch.nn.utils.clip_grad_norm_(self.model.parameters(), max_norm=1.0)
                optimizer.step()
                
                epoch_loss += loss.item() * batch_x.size(0)
                
            epoch_loss /= len(train_loader.dataset)
            scheduler.step(epoch_loss)
            
            if epoch_loss < best_loss:
                best_loss = epoch_loss
                patience_counter = 0
            else:
                patience_counter += 1
                
            if patience_counter >= patience:
                logger.info(f"Early stopping at epoch {epoch+1}")
                break

    def predict(self, horizon: int) -> np.ndarray:
        """Forecast future demand.
        Parameters
        ----------
        """
        self.model.eval()
        
        # Need exactly seq_length days of history
        history = self.train_history[-self.seq_length:]
        
        # Shape: (1, seq_length, n_nodes)
        X_test = torch.tensor(history, dtype=torch.float32).unsqueeze(0).to(self.device)
        
        with torch.no_grad():
            preds = self.model(X_test)  # (1, model_horizon, n_nodes)
            
        preds = preds.squeeze(0).cpu().numpy()  # (model_horizon, n_nodes)
        
        # Handle mismatch if asked horizon is different than model trained horizon
        # The model was trained with horizon=7.
        model_horizon = preds.shape[0]
        n_nodes = preds.shape[1]
        
        out = np.zeros((horizon, n_nodes))
        if horizon <= model_horizon:
            out = preds[:horizon, :]
        else:
            out[:model_horizon, :] = preds
            out[model_horizon:, :] = preds[-1, :]
            
        return np.maximum(out, 0.0)
