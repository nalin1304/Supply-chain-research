# Data Directory

## Structure

```
data/
├── external/                    # Raw third-party datasets (not modified)
│   ├── dalal_2022/             # INFORMS dataset: 101 Indian demand points
│   ├── dataco/                 # DataCo: 180K orders (demand calibration)
│   ├── delhivery/              # Delhivery: 145K shipments (distance validation)
│   ├── reports/                # PDF reports (NITI Aayog, NCAER, TERI)
│   ├── supplygraph/           # NeurIPS 2023 graph benchmark
│   ├── svrpbench/              # SVRPBench: Stochastic VRP benchmark instances
│   ├── traffic_data/           # New Delhi Traffic Probe (Time-of-day matrices)
│   └── offline_rl_data/        # High-Dimensional SC Inventory (Expert trajectories)
├── processed/                  # Derived/calibrated data
│   ├── dalal_customer_locations.npy    # 101 GPS coordinates
│   ├── delhivery_distance_matrix_km.npy # Validated distances
│   ├── delhivery_network.json          # 10 hubs + 150 customers
│   ├── ors_distance_matrix_km.npy      # ORS real driving distances
│   └── demand_calibration.json         # Fitted distribution params
├── cache/                      # Cached API responses
│   └── ors_distance_104x104.npy        # ORS distance cache
└── results/                    # Training outputs (from Modal)
    ├── nsga2_best_front.npy
    ├── nsga2_all_results.pkl
    ├── lstm_predictions.npy
    ├── ppo_final.pt
    ├── mc_service_levels.npy
    └── training_summary.json
```

## Key Datasets

### Dalal (2022) — Network Topology
- **Source**: INFORMS Transportation Science dataset
- **Content**: 101 demand points + 5 warehouses across India with GPS coordinates
- **Use**: Defines the physical network for optimization

### DataCo Supply Chain — Demand Calibration
- **Source**: Kaggle (Constante et al., 2019)
- **Content**: 180,519 orders with quantities, categories, dates
- **Use**: Fitted LogNormal(μ=6.44, σ=0.97) for realistic demand

### Delhivery — Distance Validation
- **Source**: Kaggle (Delhivery Business Case Study, 2022)
- **Content**: 144,867 shipment records with OSRM vs actual distances
- **Use**: Quantified OSRM underestimation (correction factor 0.83)

### OpenRouteService — Real Distances
- **Source**: ORS API (openrouteservice.org)
- **Content**: Driving distances between all warehouse-customer pairs
- **Use**: Replaces Euclidean/Haversine with real road distances

### SVRPBench — Stochastic Routing
- **Source**: SVRPBench Benchmark Data
- **Content**: Stochastic delivery scenarios and urban delays
- **Use**: Baseline for robust routing under disruption (Phase 11 & Phase 13)

### New Delhi Traffic Probe — Traffic Matrices
- **Source**: 2024 Traffic Probe Data
- **Content**: Time-of-day congestion penalties
- **Use**: Dynamic Spatio-Temporal Routing algorithms (Phase 13)

### High-Dimensional SC Inventory — Offline RL
- **Source**: Expert Trajectory Data
- **Content**: Sequential human-like replenishment actions
- **Use**: Pre-training Decision Transformers for offline reinforcement learning (Phase 12)

## Calibration Parameters (from real data)

| Parameter | Value | Source |
|-----------|-------|--------|
| Demand μ (LogNormal) | 6.44 | DataCo fit |
| Demand σ (LogNormal) | 0.97 | DataCo fit |
| Truck speed | 35 km/h | NITI Aayog 2021 |
| Empty running | 35% | NITI Aayog 2021 |
| HCV utilization | 65% | NITI Aayog 2021 |
| HCV:LCV ratio | 70:30 | VAHAN 2023 |
| OSRM correction | 0.83 | Delhivery validation |
