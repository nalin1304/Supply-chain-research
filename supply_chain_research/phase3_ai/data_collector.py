"""Offline RL Data Collector (Phase 12).

Parses the High-Dimensional Retail Inventory CSV dataset into
(State, Action, Reward, Return-to-Go) trajectories and exports them to HDF5.
"""

import os
from pathlib import Path

import h5py
import numpy as np
import pandas as pd
from loguru import logger


def process_inventory_data_to_hdf5(csv_path: str, hdf5_train_path: str, hdf5_test_path: str, seq_len: int = 30):
    """
    Parses historical inventory data into offline RL trajectories.
    
    State: [Inventory_Level, Demand_Forecast, Lead_Time, Promotion_Flag]
    Action: [Order_Quantity]
    Reward: Computed daily profit/loss
    """
    logger.info(f"Loading data from {csv_path}...")
    df = pd.read_csv(csv_path)
    
    # Sort chronologically per SKU/Warehouse
    df['Date'] = pd.to_datetime(df['Date'])
    df = df.sort_values(by=['SKU_ID', 'Warehouse_ID', 'Date'])
    
    states_list = []
    actions_list = []
    rewards_list = []
    rtg_list = []
    
    logger.info("Processing trajectories...")
    
    # Process each time series independently
    grouped = df.groupby(['SKU_ID', 'Warehouse_ID'])
    
    total_transitions = 0
    
    for (sku, wh), group in grouped:
        if len(group) < seq_len:
            continue
            
        group = group.reset_index(drop=True)
        
        # Calculate Reward: Profit - Holding Cost - Stockout Penalty
        profit = group['Units_Sold'] * (group['Unit_Price'] - group['Unit_Cost'])
        holding_cost = group['Inventory_Level'] * 0.05  # Approximate 5% daily holding
        stockout_penalty = group['Stockout_Flag'] * (group['Unit_Price'] * 0.5) # Penalty
        
        rewards = (profit - holding_cost - stockout_penalty).values.astype(np.float32)
        
        # State: normalize roughly for neural net
        inv_level = group['Inventory_Level'].values / 1000.0
        forecast = group['Demand_Forecast'].values / 100.0
        lead_time = group['Supplier_Lead_Time_Days'].values / 30.0
        promo = group['Promotion_Flag'].values
        
        states = np.stack([inv_level, forecast, lead_time, promo], axis=1).astype(np.float32)
        
        # Action: normalize order quantity
        actions = (group['Order_Quantity'].values / 1000.0).astype(np.float32)[..., np.newaxis]
        
        # Compute Return-to-Go (discounted sum of future rewards)
        gamma = 0.99
        rtg = np.zeros_like(rewards)
        curr_rtg = 0.0
        for t in reversed(range(len(rewards))):
            curr_rtg = rewards[t] + gamma * curr_rtg
            rtg[t] = curr_rtg
            
        # Segment into sequences of length `seq_len`
        for i in range(len(group) - seq_len + 1):
            states_list.append(states[i:i+seq_len])
            actions_list.append(actions[i:i+seq_len])
            rewards_list.append(rewards[i:i+seq_len])
            rtg_list.append(rtg[i:i+seq_len])
            total_transitions += seq_len
            
    # Temporal split 80/20
    split_idx = int(len(states_list) * 0.8)
    
    logger.info(f"Generated {len(states_list)} sequences. Train: {split_idx}, Test: {len(states_list)-split_idx}")
    
    # Save to HDF5 Train
    os.makedirs(os.path.dirname(hdf5_train_path), exist_ok=True)
    logger.info(f"Writing train data to {hdf5_train_path}...")
    with h5py.File(hdf5_train_path, 'w') as f:
        f.create_dataset('states', data=np.stack(states_list[:split_idx]), compression='gzip')
        f.create_dataset('actions', data=np.stack(actions_list[:split_idx]), compression='gzip')
        f.create_dataset('rewards', data=np.stack(rewards_list[:split_idx]), compression='gzip')
        f.create_dataset('rtg', data=np.stack(rtg_list[:split_idx]), compression='gzip')
        
    # Save to HDF5 Test
    logger.info(f"Writing test data to {hdf5_test_path}...")
    with h5py.File(hdf5_test_path, 'w') as f:
        f.create_dataset('states', data=np.stack(states_list[split_idx:]), compression='gzip')
        f.create_dataset('actions', data=np.stack(actions_list[split_idx:]), compression='gzip')
        f.create_dataset('rewards', data=np.stack(rewards_list[split_idx:]), compression='gzip')
        f.create_dataset('rtg', data=np.stack(rtg_list[split_idx:]), compression='gzip')
        
    logger.info("Data export complete.")

if __name__ == "__main__":
    base_dir = Path(__file__).parent.parent.parent
    csv_in = base_dir / "data" / "external" / "offline_rl_data" / "high_dim_inventory.csv"
    hdf5_train_out = base_dir / "data" / "processed" / "offline_rl_expert_train.h5"
    hdf5_test_out = base_dir / "data" / "processed" / "offline_rl_expert_test.h5"
    
    if csv_in.exists():
        process_inventory_data_to_hdf5(str(csv_in), str(hdf5_train_out), str(hdf5_test_out), seq_len=30)
    else:
        logger.error(f"Could not find dataset at {csv_in}")
