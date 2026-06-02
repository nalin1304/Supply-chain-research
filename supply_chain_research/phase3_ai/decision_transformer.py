"""Decision Transformer (Phase 12).

Offline RL Causal Language Model. It processes sequences of 
(Return-to-Go, State, Action) and predicts the next Action.
"""

import math

import torch
import torch.nn as nn


class CausalSelfAttention(nn.Module):
    """A standard multi-head masked self-attention layer."""
    def __init__(self, d_model, n_heads, dropout=0.1):
        super().__init__()
        assert d_model % n_heads == 0
        
        self.c_attn = nn.Linear(d_model, 3 * d_model)
        self.c_proj = nn.Linear(d_model, d_model)
        self.attn_dropout = nn.Dropout(dropout)
        self.resid_dropout = nn.Dropout(dropout)
        
        self.n_heads = n_heads
        self.d_model = d_model

    def forward(self, x, mask=None):
        B, T, C = x.size()
        
        # calculate query, key, values for all heads in batch
        q, k, v = self.c_attn(x).split(self.d_model, dim=2)
        k = k.view(B, T, self.n_heads, C // self.n_heads).transpose(1, 2)
        q = q.view(B, T, self.n_heads, C // self.n_heads).transpose(1, 2)
        v = v.view(B, T, self.n_heads, C // self.n_heads).transpose(1, 2)

        # causal mask
        att = (q @ k.transpose(-2, -1)) * (1.0 / math.sqrt(k.size(-1)))
        if mask is not None:
            att = att.masked_fill(mask == 0, float('-inf'))
            
        att = torch.softmax(att, dim=-1)
        att = self.attn_dropout(att)
        
        y = att @ v
        y = y.transpose(1, 2).contiguous().view(B, T, C)
        
        y = self.resid_dropout(self.c_proj(y))
        return y


class TransformerBlock(nn.Module):
    def __init__(self, d_model, n_heads, dropout=0.1):
        super().__init__()
        self.ln_1 = nn.LayerNorm(d_model)
        self.attn = CausalSelfAttention(d_model, n_heads, dropout)
        self.ln_2 = nn.LayerNorm(d_model)
        self.mlp = nn.Sequential(
            nn.Linear(d_model, 4 * d_model),
            nn.GELU(),
            nn.Linear(4 * d_model, d_model),
            nn.Dropout(dropout),
        )

    def forward(self, x, mask=None):
        x = x + self.attn(self.ln_1(x), mask=mask)
        x = x + self.mlp(self.ln_2(x))
        return x


class DecisionTransformer(nn.Module):
    """Decision Transformer for Offline Reinforcement Learning."""
    def __init__(
        self,
        state_dim,
        act_dim,
        max_length=30,
        max_ep_len=400,
        hidden_size=128,
        n_layer=3,
        n_head=4,
        dropout=0.1,
    ):
        super().__init__()
        self.state_dim = state_dim
        self.act_dim = act_dim
        self.max_length = max_length
        self.hidden_size = hidden_size
        
        # Embeddings
        self.embed_timestep = nn.Embedding(max_ep_len, hidden_size)
        self.embed_return = nn.Linear(1, hidden_size)
        self.embed_state = nn.Linear(state_dim, hidden_size)
        self.embed_action = nn.Linear(act_dim, hidden_size)
        
        self.embed_ln = nn.LayerNorm(hidden_size)
        
        # Transformer blocks
        self.blocks = nn.ModuleList(
            [TransformerBlock(hidden_size, n_head, dropout) for _ in range(n_layer)]
        )
        self.ln_f = nn.LayerNorm(hidden_size)
        
        # Output heads (we mainly care about predicting the action)
        self.predict_action = nn.Sequential(
            nn.Linear(hidden_size, act_dim),
            nn.Tanh()  # Output in [-1, 1], scaling occurs in env or wrapper
        )
        
        # Causal mask for the transformer
        # Sequence layout: R_1, s_1, a_1, R_2, s_2, a_2...
        self.register_buffer(
            "causal_mask",
            torch.tril(torch.ones(max_length * 3, max_length * 3)).view(1, 1, max_length * 3, max_length * 3)
        )

    def forward(self, states, actions, returns_to_go, timesteps):
        """
        states: (B, T, state_dim)
        actions: (B, T, act_dim)
        returns_to_go: (B, T, 1)
        timesteps: (B, T)
        """
        B, T, _ = states.shape
        
        # Embeddings
        time_embeddings = self.embed_timestep(timesteps)
        
        # Combine embeddings with time embeddings
        state_embeddings = self.embed_state(states) + time_embeddings
        action_embeddings = self.embed_action(actions) + time_embeddings
        returns_embeddings = self.embed_return(returns_to_go) + time_embeddings
        
        # Interleave tokens: (R, s, a, R, s, a, ...)
        # Shape: (B, 3, T, hidden_size)
        stacked_inputs = torch.stack(
            (returns_embeddings, state_embeddings, action_embeddings), dim=1
        )
        # Reshape to (B, 3*T, hidden_size)
        x = stacked_inputs.permute(0, 2, 1, 3).reshape(B, 3 * T, self.hidden_size)
        x = self.embed_ln(x)
        
        # Mask out future tokens
        mask = self.causal_mask[:, :, :3 * T, :3 * T]
        
        for block in self.blocks:
            x = block(x, mask=mask)
            
        x = self.ln_f(x)
        
        # Reshape back to (B, T, 3, hidden_size)
        x = x.reshape(B, T, 3, self.hidden_size)
        
        # The prediction for a_t is based on the state representation s_t
        # In our interleaved setup, state is at index 1
        state_repr = x[:, :, 1]
        
        action_preds = self.predict_action(state_repr)
        
        return action_preds
