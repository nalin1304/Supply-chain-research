"""Kaggle M5 Dataset Loader for Sim-to-Real Transfer.

This script parses the Kaggle M5 dataset (sales_train_validation.csv)
and maps its hierarchical structure to our Supply Chain topology.
If the raw dataset is unavailable (e.g. not downloaded), it provides a 
synthetic fallback that mimics the statistical properties of the M5 series
to ensure the pipeline runs zero-shot.

Mapping:
- M5 has 10 stores -> We map them to our n_warehouses (e.g., 5).
- M5 has 30,490 items -> We aggregate/select top n_customers (e.g., 100).
"""

import os
import numpy as np
import pandas as pd
from loguru import logger

class M5DataLoader:
    def __init__(self, data_dir="data/m5", n_customers=100, n_warehouses=5):
        self.data_dir = data_dir
        self.n_customers = n_customers
        self.n_warehouses = n_warehouses
        self.csv_path = os.path.join(data_dir, "sales_train_validation.csv")
        self.demand_series = None
        
    def load_or_simulate(self):
        """Loads M5 data if available, otherwise simulates it."""
        if os.path.exists(self.csv_path):
            logger.info(f"Found M5 dataset at {self.csv_path}. Loading real data...")
            self._load_real_m5()
        else:
            logger.warning(f"M5 dataset not found at {self.csv_path}. Generating M5-like synthetic data.")
            self._generate_synthetic_m5()
            
        return self.demand_series
        
    def _load_real_m5(self):
        """Loads and aggregates real M5 data."""
        df = pd.read_csv(self.csv_path)
        
        # We need to map to n_customers (items) and n_warehouses (stores)
        # 1. Select top n_customers by total volume
        day_cols = [c for c in df.columns if c.startswith('d_')]
        df['total_sales'] = df[day_cols].sum(axis=1)
        
        # Group by item_id to get top items
        top_items = df.groupby('item_id')['total_sales'].sum().nlargest(self.n_customers).index
        df_top = df[df['item_id'].isin(top_items)]
        
        # 2. Map stores to warehouses
        # M5 has 10 stores (CA_1..4, TX_1..3, WI_1..3). We just take the first n_warehouses
        stores = df_top['store_id'].unique()[:self.n_warehouses]
        df_filtered = df_top[df_top['store_id'].isin(stores)]
        
        # 3. Create the demand matrix: shape (T, n_customers)
        # M5 data is per (item, store). We will aggregate across stores for customer demand,
        # or we treat each customer as buying from a specific region.
        # For simplicity in our environment, demand is total demand per customer.
        demand_df = df_filtered.groupby('item_id')[day_cols].sum()
        
        # Transpose so rows are days (T), columns are items (n_customers)
        self.demand_series = demand_df.T.values.astype(np.float32)
        logger.info(f"Successfully loaded real M5 data. Shape: {self.demand_series.shape}")

    def _generate_synthetic_m5(self):
        """Generates synthetic data matching M5 characteristics (intermittent, zero-inflated)."""
        T = 1913  # M5 has 1913 days
        self.demand_series = np.zeros((T, self.n_customers), dtype=np.float32)
        
        for c in range(self.n_customers):
            # M5 is zero-inflated Poisson-like
            base_rate = np.random.uniform(0.5, 5.0)
            demand = np.random.poisson(base_rate, size=T)
            
            # Add intermittency (many zero sales days)
            zero_prob = np.random.uniform(0.1, 0.7)
            zeros = np.random.choice([0, 1], size=T, p=[zero_prob, 1 - zero_prob])
            demand = demand * zeros
            
            # Add some weekly seasonality
            weekly_effect = np.sin(np.arange(T) * (2 * np.pi / 7)) * (base_rate * 0.5)
            demand = np.maximum(0, demand + weekly_effect)
            
            self.demand_series[:, c] = demand
            
        logger.info(f"Generated synthetic M5 data. Shape: {self.demand_series.shape}")

if __name__ == "__main__":
    loader = M5DataLoader()
    data = loader.load_or_simulate()
    print(f"Sample data (first 5 days, first 5 items):\n{data[:5, :5]}")
