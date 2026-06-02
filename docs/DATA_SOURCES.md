# Data Sources & Realism Strategy

## Current State

| Component | Source | Realism Level | Gap |
|-----------|--------|---------------|-----|
| Road distances | OSRM (OpenStreetMap India) | ★★★★☆ Real | No traffic/congestion modeling |
| Warehouse locations | 5 GPS coords (industrial areas) | ★★★☆☆ Approximate | Not actual facility addresses |
| Customer placement | Gaussian around 20 cities | ★★☆☆☆ Semi-synthetic | Not real customer addresses |
| Demand volumes | LogNormal(μ=7.5, σ=0.6) | ★★☆☆☆ Synthetic | Not calibrated to real orders |
| Demand time series | Poisson + seasonality | ★★☆☆☆ Synthetic | Patterns assumed, not measured |
| Vehicle parameters | MEET/COPERT (verified) | ★★★★★ Real | Literature-validated |
| Fuel costs | INR 95/litre (2024) | ★★★★☆ Real | Static, not dynamic pricing |

---

## Tier 1: Directly Usable Datasets (Free, Downloadable)

### 1.1 Delhivery Business Case Dataset
- **URL**: https://www.kaggle.com/datasets/benroshan/delhivery-business-case-study
- **Size**: ~145K shipment records
- **Fields**: trip_uuid, route_type, source/destination centers, actual_time, osrm_time, osrm_distance, actual_distance, segment_actual_time, start_scan_to_end_scan
- **Key value**: **OSRM vs actual distance/time comparison** — directly validates our distance matrix accuracy
- **Use for**:
  - Quantify OSRM error distribution for Indian roads (expected: OSRM underestimates by 10-20%)
  - Calibrate travel time noise parameter (`truck_speed_noise_pct`)
  - Extract hub-to-hub transit time distributions
  - Validate that our 50-500 km distance range is realistic
- **Citation**: Delhivery Limited. Business Case Study Dataset. Kaggle, 2022.

### 1.2 DataCo Smart Supply Chain
- **URL**: https://www.kaggle.com/datasets/shashwatwork/dataco-smart-supply-chain-for-big-data-analysis
- **Size**: 180K orders, 53 columns
- **Fields**: order_date, shipping_mode, delivery_status, customer_segment, product_category, order_item_quantity, sales, profit, late_delivery_risk
- **Key value**: **Real order patterns with product categories** — calibrates multi-product extension
- **Use for**:
  - Fit demand distribution parameters (replace LogNormal assumptions)
  - Validate weekly/seasonal demand cycles
  - Calibrate product category mix (Electronics 15%, FMCG 60%, Bulk 25%)
  - Late delivery risk → validate DES service level predictions
- **Citation**: Constante et al. DataCo Smart Supply Chain for Big Data Analysis. Kaggle, 2019.

### 1.3 Amazon Last-Mile Routing Research Challenge
- **URL**: https://registry.opendata.aws/amazon-last-mile-challenges/
- **Size**: 6,112 routes, 228K stops across US cities
- **Fields**: route_id, stops (lat/lon), actual_sequences, travel_times, package_dimensions
- **Key value**: **Real VRP solutions with actual travel times** — validates routing algorithms
- **Use for**:
  - Benchmark Clarke-Wright and NSGA-II route quality against real optimal routes
  - Validate that our route distance calculations are in the right ballpark
  - Extract stop-density patterns for customer clustering
- **Citation**: Amazon. Last Mile Routing Research Challenge. MIT License, 2023.

### 1.4 LaDe: Last-Mile Delivery Dataset (JD.com)
- **URL**: https://huggingface.co/datasets/Cainiao-AI/LaDe
- **Paper**: Wu et al. (2023). "LaDe: The First Comprehensive Last-mile Delivery Dataset from Industry." KDD 2023.
- **Size**: 10M+ packages, 2 cities, courier trajectories
- **Fields**: package_id, courier_id, delivery_time, lat/lon, accept_time, delivery_gps_time
- **Key value**: **Industrial-scale delivery data with GPS trajectories**
- **Use for**:
  - Validate delivery time distributions
  - Calibrate demand arrival patterns (Poisson assumption check)
  - Real courier routing behavior for PPO comparison

### 1.5 New Delhi Traffic Probe & Analytics 2024
- **Folder**: `data/external/traffic_data/new_delhi_probe_2024`
- **Key value**: **Time-of-day specific traffic penalties** for routing.
- **Use for**: Dynamic Spatio-Temporal routing (Phase 13), creating a time-penalty matrix to penalize paths driving through heavy rush hour traffic nodes.

### 1.6 High-Dimensional Supply Chain Inventory Dataset
- **Folder**: `data/external/offline_rl_data/high_dim_inventory.csv`
- **Key value**: **Real sequential inventory decisions** representing expert state-action trajectories.
- **Use for**: Offline Reinforcement Learning (Phase 12). Used to pre-train the Decision Transformers on human-like replenishment actions before online fine-tuning.

### 1.7 Indian Supply Chain Demand & Network (Dalal 2022)
- **Folder**: `data/external/dalal_2022/`
- **Files**: `demand_location_data_2021.xlsx`, `distance_matrix.xlsx`, `warehouses.xlsx`
- **Key value**: **Real-world Indian supply chain locations, warehouses, and demand metrics**.
- **Use for**: Validating spatial distribution of customer demand and baseline warehouse network structure in the simulation environment.

---

## Tier 2: India-Specific Government & Policy Data

### 2.1 NITI Aayog + RMI: "Fast Tracking Freight in India"
- **URL**: https://rmi.org/insight/fast-tracking-freight-in-india-a-roadmap-for-clean-and-cost-effective-goods-transport/
- **Key data**:
  - India logistics cost: 14% of GDP (target: 10%)
  - Road freight: 70% of domestic freight by volume
  - Truck utilization: 60-65% (empty running 35-40%)
  - Average truck speed: 20-40 km/h (vs our 60 km/h assumption — **needs correction**)
  - CO₂ from road freight: 260 MT/year (2020)
- **Use for**: Calibrating truck speed, empty-running factor, macro cost validation
- **Citation**: NITI Aayog & RMI (2021). Fast Tracking Freight in India.

### 2.2 TERI + Smart Freight Centre: India Freight Emissions
- **URL**: https://smartfreightcentre.org/en/about-sfc/news/sfc-teri-whitepaper/
- **Key data**:
  - Trucks = 3% of vehicles but 53% of PM emissions, 70% of NOx
  - Freight emissions could quadruple by 2047 without reform
  - India-specific emission factors for BS-VI trucks
- **Use for**: Validating MEET parameters against India-specific measurements
- **Citation**: TERI & SFC (2025). Freight Emissions Measurement in India.

### 2.3 NCAER: Logistics Cost Framework
- **URL**: https://ncaer.org/publication/logistics-cost-in-india-assessment-and-long-term-framework/
- **Key data**:
  - Breakdown: transport 60%, warehousing 25%, inventory 15%
  - Road freight cost: INR 2.5-4.0 per tonne-km (validates our cost_per_km)
  - Warehousing cost: INR 15-25 per sq ft/month
- **Use for**: Validating total cost calculations, warehousing cost component
- **Citation**: NCAER (2024). Logistics Cost in India: Assessment and Long-term Framework.

### 2.4 data.gov.in: Indian Railways Freight
- **URL**: https://data.gov.in/search?title=freight
- **Key data**:
  - Commodity-wise freight volumes (coal, cement, food grains, fertilizer, iron ore)
  - Origin-destination matrices for major corridors
  - Monthly/annual trends
- **Use for**: Demand volume calibration by corridor, seasonal patterns

### 2.5 VAHAN (Ministry of Road Transport)
- **URL**: https://vahan.parivahan.gov.in/vahan4dashboard/
- **Key data**:
  - Vehicle registration by type and state
  - HCV vs LCV fleet composition (actual ratio for India)
  - Age distribution of commercial vehicles
- **Use for**: Validating fleet mix assumptions (currently 50/50 HCV/LCV)

---

## Tier 3: Academic Benchmark Datasets

### 3.1 SupplyGraph (NeurIPS 2023)
- **URL**: https://github.com/ciol-researchlab/SupplyGraph
- **Paper**: Aziz et al. (2023). "SupplyGraph: A Benchmark Dataset for Supply Chain Planning Using Graph Neural Networks." NeurIPS Datasets Track.
- **Key value**: Graph-structured SC benchmark with temporal demand signals
- **Use for**: Network topology validation, GNN comparison baseline

### 3.2 CVRPLIB (Standard VRP Benchmarks)
- **URL**: http://vrp.atd-lab.inf.puc-rio.br/index.php/en/
- **Key value**: Standard CVRP instances (Augerat, Christofides, Golden) with known optimal solutions
- **Use for**: Validating Clarke-Wright and NSGA-II solution quality against known optima

### 3.3 Supply Chain Data Hub
- **URL**: https://supplychaindatahub.org
- **Key value**: Curated collection of SC datasets for benchmarking
- **Use for**: Cross-referencing demand patterns, network structures

### 3.4 PLOS ONE Real-World VRP Dataset (2024)
- **Paper**: "Generating large-scale real-world vehicle routing dataset with novel spatial data extraction tool"
- **URL**: https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0304422
- **Key value**: Geocoded VRP instances from real urban environments with OSRM distances
- **Use for**: Validating our OSRM-based approach against published methodology

### 3.5 SVRPBench: Stochastic Vehicle Routing Benchmark
- **URL**: https://github.com/yehias21/vrp-benchmarks
- **Folder**: `data/external/svrpbench/`
- **Key value**: **Open and extensible benchmark for the Stochastic Vehicle Routing Problem (SVRP)**, evaluating algorithms under realistic urban logistics conditions (time-dependent travel delays, uncertain customer availability, dynamic disruptions).
- **Use for**: Validating stochastic routing algorithms against realistic urban traffic baselines.
- **Citation**: Heakl, Ahmed et al. (2025). "SVRPBench: A Benchmark for Stochastic Vehicle Routing Problems."

---

## Tier 4: Industry APIs (Requires Partnership/Keys)

### 4.1 Delhivery Developer API
- **URL**: https://delhivery-express-api-doc.readme.io/
- **Access**: Requires business account
- **Data**: Real-time tracking, pin-code serviceability, rate calculator
- **Use for**: Live distance/time validation, serviceability constraints

### 4.2 BlackBuck (now Zinka) Freight Exchange
- **What**: India's largest digital freight marketplace
- **Data**: Spot freight rates by route, truck availability, load matching
- **Use for**: Real-time cost calibration (INR/km by route and vehicle type)
- **Access**: Partnership required

### 4.3 Indian Logistics Exchange (ILE)
- **What**: Government-backed logistics marketplace
- **Data**: Freight rates, route demand, truck utilization
- **Use for**: Market-rate validation for cost objective

---

## Integration Priority (Recommended Order)

### Immediate (before training):
1. **Download Delhivery dataset** → Run OSRM validation script → Quantify distance error
2. **Download DataCo dataset** → Fit demand distributions → Update LogNormal parameters
3. **Read NITI Aayog report** → Correct truck speed from 60 to 30-40 km/h → Update config

### Before paper submission:
4. **VAHAN data** → Get real HCV:LCV ratio for India → Update fleet mix assumptions
5. **NCAER report** → Validate cost per tonne-km → Cross-check with our model output
6. **CVRPLIB benchmarks** → Run Clarke-Wright on standard instances → Report optimality gap

### For reviewer response:
7. **LaDe dataset** → Show PPO generalizes to real delivery patterns
8. **SupplyGraph** → Compare network topology with our generated network

---

## Critical Corrections Needed (from NITI Aayog data)

| Parameter | Current | Real (India) | Source | Impact |
|-----------|---------|--------------|--------|--------|
| Truck speed | 60 km/h | 20-40 km/h | NITI Aayog 2021 | Travel times 1.5-3x longer |
| Empty running | 0% (implicit) | 35-40% | NITI Aayog 2021 | Cost underestimated |
| HCV utilization | 100% | 60-65% | NITI Aayog 2021 | Effective capacity lower |
| Logistics cost/GDP | N/A | 14% | NCAER 2024 | Macro validation |
| HCV:LCV ratio | 50:50 | ~70:30 | VAHAN 2023 | Fleet mix bias |

These corrections should be applied to `config.py` after downloading and analyzing the source data.
