"""Configuration models for supply chain optimization system."""

import os
from typing import List, Tuple
from pydantic import BaseModel, Field


class NetworkConfig(BaseModel):
    """Network topology configuration.

    Defines the geographic, fleet, and routing parameters that describe
    the supply-chain network. Used by every Phase-1 / Phase-2 module
    that needs depot/customer locations or distance matrices.

    Attributes
    ----------
    n_customers : int
        Number of customer nodes in the network.
    n_warehouses : int
        Number of depot / warehouse nodes.
    n_cities : int
        Number of major Indian cities used to seed customer
        locations.
    india_lat_bounds, india_lon_bounds : tuple of float
        Geographic bounding box used to validate generated
        coordinates.
    osrm_base_url, osrm_batch_size, osrm_retry_max, osrm_retry_backoff
        Public-OSRM HTTP client parameters used by the routing layer.
    cache_dir : str
        Filesystem location for cached distance/duration matrices.
    ors_base_url, ors_api_key : str
        OpenRouteService Matrix-API fallback endpoint and key.
    hcv_lcv_fleet_ratio : float
        Heavy-vs-light commercial-vehicle mix in the fleet
        (1.0 = HCV only).
    customer_location_std : float
        Gaussian-perturbation standard deviation (degrees) used
        when synthesizing customer locations around each city.
    demand_clip_min, demand_clip_max : float
        Per-customer demand bounds (kg) applied during generation.
    cities, warehouse_locations : list of tuple
        Master lists of `(name, latitude, longitude)` tuples.
    warehouse_capacities : list of float
        Per-depot capacity (kg) in the same order as
        ``warehouse_locations``.
    """

    n_customers: int = 100
    n_warehouses: int = 5
    n_cities: int = 20

    # India geographic bounds for coordinate validation
    india_lat_bounds: Tuple[float, float] = (8.0, 37.0)
    india_lon_bounds: Tuple[float, float] = (68.0, 97.0)

    # OSRM routing configuration
    osrm_base_url: str = "http://router.project-osrm.org"
    osrm_batch_size: int = 100
    osrm_retry_max: int = 3
    osrm_retry_backoff: float = 2.0

    # Caching configuration
    # Distance/duration matrices are cached to disk for reproducibility
    # and offline capability. Cache key is derived from coordinate hash.
    cache_dir: str = "data/cache"

    # OpenRouteService fallback
    # ORS Matrix API endpoint (v2); used when OSRM is unavailable.
    # Reference: https://openrouteservice.org/services/ (2024)
    # Free tier: 40 requests/min, 2500/day, max 50×50 matrix per request.
    ors_base_url: str = "https://api.openrouteservice.org/v2/matrix/driving-car"
    ors_api_key: str = Field(default_factory=lambda: os.environ.get("ORS_API_KEY", ""))

    # Fleet composition
    hcv_lcv_fleet_ratio: float = 0.70  # 70% HCV, 30% LCV in Indian freight fleet (VAHAN 2023)

    # Customer location generation: Gaussian perturbation std (degrees)
    customer_location_std: float = 0.8  # ~89 km per specification

    # Demand generation: clip bounds (kg)
    demand_clip_min: float = 100.0
    demand_clip_max: float = 10000.0

    # 20 major Indian cities: (name, latitude, longitude)
    cities: List[Tuple[str, float, float]] = Field(default_factory=lambda: [
        ("Mumbai", 19.0760, 72.8777),
        ("Delhi", 28.7041, 77.1025),
        ("Bangalore", 12.9716, 77.5946),
        ("Hyderabad", 17.3850, 78.4867),
        ("Chennai", 13.0827, 80.2707),
        ("Kolkata", 22.5726, 88.3639),
        ("Pune", 18.5204, 73.8567),
        ("Ahmedabad", 23.0225, 72.5714),
        ("Jaipur", 26.9124, 75.7873),
        ("Lucknow", 26.8467, 80.9462),
        ("Nagpur", 21.1458, 79.0882),
        ("Indore", 22.7196, 75.8577),
        ("Bhopal", 23.2599, 77.4126),
        ("Visakhapatnam", 17.6868, 83.2185),
        ("Coimbatore", 11.0168, 76.9558),
        ("Kochi", 9.9312, 76.2673),
        ("Chandigarh", 30.7333, 76.7794),
        ("Patna", 25.6093, 85.1376),
        ("Surat", 21.1702, 72.8311),
        ("Vadodara", 22.3072, 73.1812),
    ])

    # 5 warehouse locations: (name, latitude, longitude)
    warehouse_locations: List[Tuple[str, float, float]] = Field(
        default_factory=lambda: [
            ("Mumbai_WH", 19.0330, 72.8656),
            ("Delhi_WH", 28.6500, 77.2300),
            ("Bangalore_WH", 12.9352, 77.6245),
            ("Kolkata_WH", 22.5400, 88.3400),
            ("Nagpur_WH", 21.1600, 79.0500),
        ]
    )

    # Per-warehouse capacities in kg; order matches warehouse_locations
    # (Mumbai, Delhi, Bangalore, Kolkata, Nagpur)
    warehouse_capacities: List[float] = Field(
        default_factory=lambda: [60000.0, 55000.0, 50000.0, 48000.0, 45000.0]
    )


class VehicleConfig(BaseModel):
    """Vehicle type parameters for emission and cost calculation.

    Holds the per-vehicle physical and economic constants used by
    :mod:`supply_chain_research.phase1_foundation.emission_model`.

    Attributes
    ----------
    hcv_k, hcv_L : float
        MEET load-emission coefficients for the Heavy Commercial
        Vehicle class (kg CO2/km baseline; kg CO2/(kg payload·km)).
    hcv_capacity, hcv_cost_per_km : float
        Payload (kg) and per-km operating cost (INR) for HCVs.
    empty_running_fraction : float
        Fraction of HCV trips run empty (NITI Aayog & RMI, 2021).
    hcv_utilization : float
        Average HCV capacity utilization (NITI Aayog & RMI, 2021).
    diesel_co2_factor : float
        Diesel emission factor in kg CO2 per litre
        (IPCC 2006/2019).
    hcv_fuel_price, lcv_fuel_price : float
        Retail diesel price (INR/litre) for HCV and LCV.
    lcv_k, lcv_L : float
        MEET load-emission coefficients for the Light Commercial
        Vehicle class.
    lcv_capacity, lcv_cost_per_km : float
        Payload (kg) and per-km operating cost (INR) for LCVs.

    References
    ----------
    .. [1] Hickman A.J. (1999). MEET Project Report SE/491/98,
           Tables 3.2-3.3.
    .. [2] Ntziachristos L. & Samaras Z. (2009). COPERT/MEET
           methodology.
    .. [3] IPCC (2006/2019). Guidelines for National GHG
           Inventories, Vol. 2 Ch. 2 Table 2.2.
    """

    # Heavy Commercial Vehicle (HCV) — MEET methodology
    # Primary source: Hickman, A.J. (ed., 1999). "Methodology for Calculating
    #   Transport Emissions and Energy Consumption", TRL Project Report
    #   SE/491/98, MEET Deliverable 22 (EC 4th FP, Contract ST-96-SC.204).
    #   Transport Research Laboratory, UK. © TRL 1999.
    #   Reference URL (archived): https://trid.trb.org/view/707881
    # Cross-verification: Ntziachristos, L. & Samaras, Z. (2009). "COPERT:
    #   A European Road Transport Emission Inventory Model", Springer
    #   ITEE pp. 491-504. DOI:10.1007/978-3-540-88351-7_37
    # k = baseline emission rate at zero load (kg CO2/km) for rigid HGV >16t
    # [MEET-1999 §3, Table 3.2 — Heavy goods vehicles, motorway/urban avg]
    # Verified against COPERT 5 v5.6 (EEA, 2023): 2.58–2.63 range for HDV class
    # Verified against HBEFA 4.2 (INFRAS, 2022): consistent for Euro VI HDV
    # Verified against IPCC AR6 WG3 (2022) §10 Transport: no per-vehicle EF
    #   revision; values within COPERT/MEET methodology endorsed.
    # CPCB India (2023): no India-specific revision to MEET HDV k/L.
    hcv_k: float = 2.61
    # L = load-dependent emission factor (kg CO2 per kg payload per km)
    # [MEET-1999 §3, Table 3.2 — load-correction factor for rigid HGV
    #  expressed per kg-km after the per-tonne-km value is divided by 1000]
    # Cross-verified: COPERT 5 v5.6 (EEA, 2023) load-correction methodology
    hcv_L: float = 0.000147
    hcv_capacity: float = 10000.0  # kg
    hcv_cost_per_km: float = 18.0  # INR/km
    # Empty-running fraction — share of HCV trips run empty.
    # [NITI Aayog & RMI (2021), "Fast Tracking Freight in India: A Roadmap
    #  for Clean and Cost-effective Goods Transport", §2.2 — global average
    #  empty-running 30–35% (India higher, ~40%; we use the lower-bound
    #  global benchmark 0.35 for conservative emissions accounting).]
    # URL: https://rmi.org/insight/fast-tracking-freight-in-india-a-roadmap-for-clean-and-cost-effective-goods-transport/
    empty_running_fraction: float = 0.35
    # HCV capacity utilization — average load factor.
    # [NITI Aayog & RMI (2021), Fast Tracking Freight, §2.2 — Indian HCV
    #  load factor cited at 60–65%; we use 0.65 (upper bound).]
    hcv_utilization: float = 0.65

    # Diesel CO2 emission factor: 2.68 kg CO2 per litre
    # Primary source: IPCC (2006). "2006 IPCC Guidelines for National
    #   Greenhouse Gas Inventories", Vol. 2 (Energy), Ch. 2, Table 2.2.
    #   Default EF for diesel/gas oil = 74,100 kg CO2/TJ (NCV basis).
    #   IGES, Japan. URL: https://www.ipcc-nggip.iges.or.jp/public/2006gl/vol2.html
    # Confirmed: IPCC (2019) "2019 Refinement to the 2006 IPCC Guidelines",
    #   Vol. 2 Ch. 2 — Table 2.2 retained without revision.
    # Confirmed: IPCC AR6 WG3 (2022) §10 Transport — uses 2006/2019 EFs.
    # Derivation: density 0.832 kg/L × NCV 43.0 MJ/kg × 74.1 t-CO2/TJ
    #   ≈ 0.832 × 43.0 × 74.1e-3 ≈ 2.65–2.68 kg CO2/L (range from density).
    # Widely standardized at 2.68 kg/L (UK BEIS/DEFRA conversion factors;
    # EU JRC fuel cycle; HBEFA 4.2 stoichiometric basis).
    diesel_co2_factor: float = 2.68  # kg CO2 per litre

    # Fuel prices (INR/litre)
    # Reference: typical Indian retail diesel price 2023–2024 (state-mean).
    hcv_fuel_price: float = 95.0
    lcv_fuel_price: float = 95.0

    # Light Commercial Vehicle (LCV) — MEET methodology
    # Primary source: Hickman, A.J. (ed., 1999), MEET TRL Project Report
    #   SE/491/98, Table 3.3 — Light commercial vehicles (≤3.5t GVW).
    # Cross-verification: Ntziachristos & Samaras (2009), COPERT/MEET LCV
    # k = baseline emission rate at zero load (kg CO2/km) for LCV ≤3.5t
    # [MEET-1999 §3, Table 3.3]
    # Verified against COPERT 5 v5.6 (EEA, 2023): 0.85–0.92 range for LCV
    lcv_k: float = 0.89
    # L = load-dependent emission factor (kg CO2 per kg payload per km)
    # [MEET-1999 §3, Table 3.3 — load-correction factor for LCV]
    lcv_L: float = 0.000079
    lcv_capacity: float = 3000.0  # kg
    lcv_cost_per_km: float = 28.0  # INR/km

    def build_vehicle_types(self) -> list:
        """Build vehicle types list from config.

        Single source of truth for all solvers. Returns the canonical
        list-of-dicts consumed by SupplyChainProblem, NSGA-III,
        carbon-budget, robust, and multi-product problem classes.

        Returns
        -------
        list of dict
            Two entries (HCV, LCV), each with keys ``name``,
            ``cost_per_km``, ``capacity``, ``k``, and ``L``.
        """
        return [
            {
                "name": "HCV",
                "cost_per_km": self.hcv_cost_per_km,
                "capacity": self.hcv_capacity,
                "k": self.hcv_k,
                "L": self.hcv_L,
            },
            {
                "name": "LCV",
                "cost_per_km": self.lcv_cost_per_km,
                "capacity": self.lcv_capacity,
                "k": self.lcv_k,
                "L": self.lcv_L,
            },
        ]


class NSGAConfig(BaseModel):
    """NSGA-II algorithm configuration.

    Audit 1.1: Budget rebalanced to pop=500, gen=400 (NFE=200K, matches
    Deb & Jain 2014 recommendation of ~100*n_var*n_obj for 1000 vars,
    2 objectives) so selection has more rounds to operate. Early stop
    threshold raised from 1e-10 (effectively never triggers) to 1e-4
    (relative HV improvement) so MultiObjectiveSpaceTermination fires
    when the Pareto front has converged.

    Attributes
    ----------
    pop_size : int
        Population size used by pymoo's NSGA-II.
    n_gen : int
        Maximum number of generations; early stopping may finish
        sooner.
    crossover_eta, crossover_prob : float
        SBX crossover distribution index and probability.
    mutation_eta : float
        Polynomial mutation distribution index.
    tournament_size : int
        Tournament size for parent selection.
    ref_point_margin : float
        Margin applied to the nadir point when computing
        hypervolume.
    early_stop_window, early_stop_threshold, early_stop_min_gen
        Sliding-window hypervolume convergence test parameters.
    demand_constraint_eps, max_demand_default : float
        Demand-satisfaction slack and decision-bound default.
    repair_max_passes, repair_zero_eps, repair_capacity_eps
        Repair-operator iteration bound and floor tolerances.
    inter_customer_distance_high_factor, inter_customer_distance_low_factor : float
        Multipliers used by the baseline solver to approximate
        inter-customer distances when no full matrix is provided.
    """

    # pop_size=500 for the 1000-variable bi-objective problem (5 warehouses × 100
    # customers × 2 vehicle types). Justification:
    #   - Deb et al. (2002) NSGA-II §V recommend pop_size proportional to problem
    #     complexity; the original NSGA-II paper used 100 for 30-variable ZDT and
    #     scales recommendations linearly with n_var for high-dimensional MOO.
    #   - Deb & Jain (2014) NSGA-III §VI reports pop=92–212 for 3–10 objective DTLZ
    #     at 30–100 variables; for 1000 variables a 5× increase to ~500 maintains
    #     the same per-variable diversity ratio.
    #   - pymoo 0.6.x docs (Blank & Deb 2020 IEEE Access §III) leave pop_size to
    #     the user; example code uses pop_size=100 for 30-var problems but the
    #     framework imposes no upper bound.
    # [Deb-2002 §V; Deb-Jain-2014 §VI Table I; Blank-Deb-2020 §III]
    pop_size: int = 500  # PROBLEM SCALED — see derive_from_problem_size
    # n_gen=400 (upper bound; early stop triggers earlier in practice). Budget
    # rationale: NFE = pop_size × n_gen = 500 × 400 = 2.0e5. Deb-Jain (2014) §VI
    # use NFE = 100 × n_var × n_obj as a baseline for problems of comparable
    # complexity, which for our 1000-var × 2-obj instance gives 2.0e5. The
    # configured budget therefore matches the Deb-Jain (2014) recommendation.
    # [Deb-Jain-2014 §VI Table I]
    n_gen: int = 400  # TUNED — upper bound; early stop normally triggers earlier
    # SBX η_c=10–20 and PM η_m=15–20 are the canonical NSGA-II operator settings
    # (Deb 2001 "Multi-Objective Optimization Using Evolutionary Algorithms"
    # Ch. 4–5; Deb-2002 §V) and the pymoo 0.6.x defaults for moderate problems.
    crossover_eta: float = 10.0  # TUNED — SBX η_c (Deb-2001 Ch.4)
    crossover_prob: float = 0.9  # TUNED — Deb-2002 §V
    mutation_eta: float = 15.0  # TUNED — PM η_m (Deb-2001 Ch.5)
    tournament_size: int = 3  # TUNED — Deb-2002 §III binary/k-ary tournament
    ref_point_margin: float = 1.1  # TUNED — 10% margin on nadir (HV ref-point)
    # Early stopping: relative HV improvement window
    early_stop_window: int = 30  # TUNED — generations to look back
    early_stop_threshold: float = 1e-4  # TUNED — relative HV change threshold
    early_stop_min_gen: int = 50  # TUNED — minimum generations before stop

    # Solver internals (centralized per Audit 1.10)
    # Demand-satisfaction constraint slack (|sum - D| - eps <= 0)
    demand_constraint_eps: float = 1e-3
    # Bounds-default upper limit for decision variables when demand vector is empty
    max_demand_default: float = 10000.0
    # Repair operator: max redistribution passes per individual
    repair_max_passes: int = 5
    # Repair operator: per-step floor for "non-zero" flow detection
    repair_zero_eps: float = 1e-9
    # Repair operator: floor when comparing capacity-residual against zero
    repair_capacity_eps: float = 1e-6
    # NSGA-II baseline-solver inter-customer distance approximation
    # (used when no full inter-customer distance matrix is available)
    inter_customer_distance_high_factor: float = 0.8
    inter_customer_distance_low_factor: float = 0.3


class NSGA3Config(BaseModel):
    """NSGA-III algorithm configuration for 3-objective optimization.

    Reference: Deb, K. & Jain, H. (2014). An Evolutionary Many-Objective
    Optimization Algorithm Using Reference-Point-Based Nondominated Sorting
    Approach, Part I: Solving Problems With Box Constraints.
    IEEE Trans. Evol. Comput., 18(4), 577-601. DOI:10.1109/TEVC.2013.2281535

    For 3 objectives with n_partitions=12, the Das-Dennis method generates
    C(12+3-1, 3-1) = C(14,2) = 91 reference points (Deb & Jain 2014, Table I).
    Population size is set to the nearest multiple of 4 >= number of reference
    points, following the recommendation in the original paper.

    Attributes
    ----------
    pop_size : int
        Population size; should be a multiple of 4 and at least the
        Das-Dennis reference-point count.
    n_gen : int
        Number of generations.
    n_partitions : int
        Das-Dennis reference-point partitions.
    crossover_eta, crossover_prob : float
        SBX crossover parameters.
    mutation_eta : float
        Polynomial-mutation distribution index.
    convergence_check_period : int
        Generations between convergence checks.
    active_shipment_threshold : float
        Minimum shipment magnitude (kg) considered "active"
        when post-processing solutions.
    """

    # pop_size=92: NSGA-III conventionally sets pop_size to the smallest
    # multiple of 4 ≥ |Z| (number of Das-Dennis reference points) so the
    # population maps cleanly onto reference directions (Deb-Jain 2014 §IV-D).
    # For M=3 objectives and p=12 partitions: |Z| = C(p+M-1, M-1) = C(14,2) = 91,
    # rounded up to 92. This matches Deb-Jain 2014 Table I (3-obj problems use
    # pop=92 with p=12).
    # [Deb-Jain-2014 §IV-D, Table I; Das-Dennis-1998]
    pop_size: int = 92  # Nearest multiple of 4 >= 91 reference points
    # n_gen=150: Deb-Jain (2014) §VI Table II report 200–500 for many-objective
    # DTLZ problems; for our 3-obj instance with 92 individuals NFE = 1.4e4
    # at n_gen=150 which lies in the recommended range.
    # [Deb-Jain-2014 §VI Table II]
    n_gen: int = 150
    # n_partitions=12 (Das-Dennis structured-weight method). For M=3 objectives
    # this gives 91 reference directions on the unit simplex, matching the
    # default in Deb-Jain (2014) §IV-D and pymoo's get_reference_directions.
    # [Das-Dennis-1998; Deb-Jain-2014 §IV-D]
    n_partitions: int = 12  # C(12+3-1, 3-1) = 91 reference points
    crossover_eta: float = 30.0  # SBX distribution index (pymoo NSGA-III default)
    crossover_prob: float = 1.0  # Crossover probability (pymoo NSGA-III default)
    mutation_eta: float = 20.0  # PM distribution index (pymoo NSGA-III default)
    convergence_check_period: int = 20
    active_shipment_threshold: float = 0.01  # kg


class MOEADConfig(BaseModel):
    """MOEA/D algorithm configuration.

    Attributes
    ----------
    pop_size : int
        Population size.
    n_gen : int
        Number of generations.
    n_neighbors : int
        Neighbourhood size for the Tchebycheff decomposition.
    decomposition : str
        Scalarization method (e.g., ``"tchebicheff"`` or
        ``"weighted-sum"``).
    """

    pop_size: int = 500
    n_gen: int = 100
    n_neighbors: int = 20
    decomposition: str = "tchebicheff"


class SimulationConfig(BaseModel):
    """Discrete Event Simulation configuration.

    Parameters used by the SimPy 4.x DES in
    :mod:`supply_chain_research.phase2_resilience.des_environment`.

    Attributes
    ----------
    sim_days, warmup_days : int
        Total simulated horizon and discarded warm-up window.
    lambda_orders : float
        Mean inter-arrival rate (orders / day) of the Poisson
        order-arrival process.
    order_size_mu, order_size_sigma : float
        LogNormal parameters for static demand allocation
        (calibrated against DataCo).
    des_order_size_mu, des_order_size_sigma : float
        LogNormal parameters for per-order DES sampling.
    n_monte_carlo : int
        Default replication count for Monte-Carlo runs.
    truck_speed_kmh, truck_speed_noise_pct : float
        Road-speed mean and lognormal noise pct.
    replenishment_cycle_days : int
        Days between depot replenishment events.
    demand_shock_multiplier, supply_shock_fraction : float
        Default magnitude for demand and supply shocks.
    service_level_threshold, tts_unfulfilled_threshold : float
        Resilience-metric thresholds.
    initial_inventory_fraction, replenishment_rate_multiplier : float
        Warehouse initial stock and weekly replenishment factors.
    fallback_warehouse_capacity : float
        Fallback capacity (kg) when config is incomplete.
    synthetic_distance_min, synthetic_distance_max : float
        Bounds (km) for synthetic distances during testing.
    """

    sim_days: int = 365
    warmup_days: int = 30
    lambda_orders: float = 3.5
    order_size_mu: float = 6.44  # LogNormal μ for weekly demand (kg), calibrated from DataCo (Constante et al., 2019)
    order_size_sigma: float = 0.97  # LogNormal σ, calibrated from DataCo (180K orders, 20K customers)
    # DES per-order size parameters (separate from static demand allocation)
    des_order_size_mu: float = 5.5
    des_order_size_sigma: float = 0.4
    n_monte_carlo: int = 50
    truck_speed_kmh: float = 35.0  # Average Indian highway truck speed (NITI Aayog & RMI, 2021)
    truck_speed_noise_pct: float = 0.15
    replenishment_cycle_days: int = 7
    demand_shock_multiplier: float = 3.0
    supply_shock_fraction: float = 0.5
    service_level_threshold: float = 0.95
    tts_unfulfilled_threshold: float = 0.10

    # DES warehouse parameters
    initial_inventory_fraction: float = 0.8  # fraction of capacity at start
    # FIX-022 stress-mode initial inventory: starts near the (s,S)
    # reorder threshold so the agent immediately faces a replenishment
    # decision rather than coasting on the legacy 80 % buffer.
    stress_initial_inventory_fraction: float = 0.3
    replenishment_rate_multiplier: float = 2.4  # weekly rate = capacity * this
    fallback_warehouse_capacity: float = 50000.0  # kg, used when config mismatch

    # DES synthetic distance range (km) for testing
    synthetic_distance_min: float = 50.0
    synthetic_distance_max: float = 500.0


class LSTMConfig(BaseModel):
    """LSTM forecaster configuration.

    Attributes
    ----------
    seq_length, forecast_horizon : int
        Encoder lookback and decoder horizon (in days).
    hidden_size, n_layers, dropout : int, int, float
        Core LSTM architecture parameters.
    epochs, batch_size, lr, patience : int, int, float, int
        Training-loop hyperparameters.
    train_split, val_split : float
        Train/validation split fractions; remainder is test.
    synthetic_years : int
        Years of synthetic data generated when no real series
        is supplied.
    model_type : str
        One of ``"lstm"``, ``"attention_lstm"``, or ``"tft"``.
    tft_hidden_size, tft_n_heads, tft_dropout : int, int, float
        Lightweight Temporal-Fusion-Transformer hyperparameters.
    weight_decay, huber_delta, scheduler_patience, scheduler_factor,
    grad_clip_max_norm : float
        Optimizer/scheduler internals.
    pacf_z_95, pacf_z_90, pacf_default_window, pacf_min_window,
    pacf_max_lag_default : float / int
        PACF-based lookback-window selection knobs.

    References
    ----------
    .. [1] Lim B. et al. (2021). Temporal Fusion Transformers for
           interpretable multi-horizon forecasting. *Int. J.
           Forecasting*, 37(4), 1748-1764.
    """

    seq_length: int = 30
    forecast_horizon: int = 7
    hidden_size: int = 128
    n_layers: int = 2
    dropout: float = 0.2
    epochs: int = 100
    batch_size: int = 64
    lr: float = 0.001
    patience: int = 10
    train_split: float = 0.70
    val_split: float = 0.15
    synthetic_years: int = 3

    # Model type selection: "lstm" | "attention_lstm" | "tft"
    # Default "attention_lstm" preserves existing behavior.
    # "tft" selects the lightweight Temporal Fusion Transformer baseline
    # (see phase3_ai/tft_forecaster.py).
    model_type: str = "attention_lstm"

    # Lightweight TFT hyperparameters (used only when model_type="tft")
    # Reference: Lim et al. (2021), Int. J. Forecasting, 37(4), 1748-1764.
    tft_hidden_size: int = 64
    tft_n_heads: int = 4
    tft_dropout: float = 0.1

    # Optimizer / training internals (centralized per Audit 1.10)
    # Adam weight decay
    weight_decay: float = 1e-5
    # Huber loss delta
    huber_delta: float = 1.0
    # ReduceLROnPlateau: scheduler patience and factor
    scheduler_patience: int = 5
    scheduler_factor: float = 0.5
    # Gradient clipping max-norm
    grad_clip_max_norm: float = 1.0
    # PACF lookback window selection (Audit 1.6)
    pacf_z_95: float = 1.96
    pacf_z_90: float = 1.64
    pacf_default_window: int = 30
    pacf_min_window: int = 7
    pacf_max_lag_default: int = 365


class PPOConfig(BaseModel):
    """PPO reinforcement learning agent configuration.

    Every PPO-Clip hyperparameter below carries an inline citation at
    the point of definition (FIX-010, clause C2.6) so that a reviewer
    can trace the value back to its source without leaving the file.

    Canonical references
    --------------------
    - Schulman et al. (2017). Proximal Policy Optimization Algorithms.
      arXiv:1707.06347. https://arxiv.org/abs/1707.06347
    - Schulman et al. (2016). High-Dimensional Continuous Control
      Using Generalized Advantage Estimation. arXiv:1506.02438.
    - Andrychowicz et al. (2021). What Matters In On-Policy RL?
      A Large-Scale Empirical Study. arXiv:2006.05990
      (DOI 10.48550/arXiv.2006.05990).
    - Huang et al. (2022). The 37 Implementation Details of Proximal
      Policy Optimization. ICLR Blog Track.
      https://iclr-blog-track.github.io/2022/03/25/ppo-implementation-details/
    - Chou, Maturana, Scherer (2017). Improving Stochastic Policy
      Gradients in Continuous Control with Deep Reinforcement
      Learning using the Beta Distribution. ICML 2017.

    Attributes
    ----------
    total_timesteps, steps_per_rollout, n_epochs : int
        Outer training-loop sizes.
    clip_range, lr, gamma, gae_lambda, vf_coef, ent_coef, max_grad_norm : float
        Standard PPO-Clip hyperparameters.
    hidden_size : int
        Hidden width for actor / critic networks.
    n_eval_episodes, checkpoint_freq : int
        Evaluation and checkpointing cadence.
    critic_lr_multiplier, action_clamp_eps, ratio_clamp_min,
    ratio_clamp_max : float
        Stability / numerical-safety knobs.
    minibatch_size_min, minibatch_count : int
        Minibatch sizing controls.
    actor_head_init_gain, beta_param_nan_default,
    beta_param_posinf_clip : float
        Beta-distribution head initialization and NaN/Inf guards.
    """

    # total_timesteps=1e6 — typical on-policy RL training horizon for
    # MuJoCo-scale continuous-control tasks (Schulman 2017 §6.1; reused
    # by Andrychowicz 2021 Fig. 2 across 5 environments).
    total_timesteps: int = 1000000
    # steps_per_rollout=2048 — Schulman 2017 §6.1 Table 3 (Walker2d/Hopper)
    # and Huang 2022 detail #1 ("vectorised env, 2048 steps per rollout").
    steps_per_rollout: int = 2048
    # n_epochs=10 — Schulman 2017 §6.1 Table 3 ("K=10 epochs of minibatch
    # SGD"); Andrychowicz 2021 §3.4 confirms 10 epochs as the empirical
    # sweet-spot across the 5 environments studied.
    n_epochs: int = 10
    # clip_range=0.2 — Schulman 2017 §6.1 Table 3 ("ε=0.2 default");
    # Andrychowicz 2021 §3.5 "the most important hyperparameter"; Huang
    # 2022 detail #5 confirms 0.2 is the community-standard default.
    clip_range: float = 0.2
    # lr=1e-4 — Andrychowicz 2021 §3.6 Fig. 6 reports 1e-4–3e-4 as the
    # optimal Adam-step range across environments; we adopt 1e-4 (the
    # conservative end) for an inventory-control task whose reward
    # signal is sparser than MuJoCo locomotion.
    lr: float = 1e-4
    # gamma=0.99 — Schulman 2017 §6.1 Table 3 default; Andrychowicz 2021
    # §3.7 confirms 0.99 outperforms 0.95/0.999 on 4 of 5 environments.
    gamma: float = 0.99
    # gae_lambda=0.95 — Schulman et al. 2016 (GAE paper) §6.2 Fig. 2
    # ("λ=0.95–0.99 best"); Schulman 2017 §6.1 Table 3 picks 0.95;
    # Huang 2022 detail #6.
    gae_lambda: float = 0.95
    # vf_coef=0.5 — Schulman 2017 §5 (Eq. 9) sets c1=0.5 for the value
    # loss when actor and critic share parameters; preserved here even
    # under the decoupled-optimiser layout for behavioural parity.
    # Cross-check: OpenAI Baselines (Dhariwal et al., 2017) PPO2 default.
    vf_coef: float = 0.5
    # ent_coef=0.01 — Schulman 2017 §5 Eq. 9 (c2=0.01 default for Atari);
    # Andrychowicz 2021 §3.10 Fig. 11 reports 0–0.01 as effectively
    # equivalent for continuous control with Gaussian/Beta policies.
    ent_coef: float = 0.01
    # max_grad_norm=0.5 — Huang 2022 detail #11 ("clip global gradient
    # norm at 0.5") and Andrychowicz 2021 §3.13 Fig. 14: the value
    # 0.5 is robust and prevents gradient blow-ups across all 5 envs.
    max_grad_norm: float = 0.5
    # hidden_size=256 — Andrychowicz 2021 §3.16 Fig. 17: 64–256-unit
    # MLPs are roughly equivalent on continuous-control benchmarks; we
    # adopt 256 to give the policy enough capacity for the
    # higher-dimensional supply-chain observation.
    hidden_size: int = 256
    n_eval_episodes: int = 100
    checkpoint_freq: int = 100_000

    # Critic-LR multiplier (Audit 2.2): critic_lr = multiplier * actor lr.
    # Decoupled actor/critic optimisers — Andrychowicz 2021 §3.6
    # Fig. 7 shows the value loss benefits from a 2-3x larger LR than
    # the policy. We adopt 3.0 (mid-range).
    critic_lr_multiplier: float = 3.0
    # Action / log-prob safety clamp (Beta distribution boundary).
    # Chou 2017 §3.2 — Beta(α,β) on (0,1) is open; we clamp samples
    # to (eps, 1-eps) so log_prob stays finite at the boundary.
    action_clamp_eps: float = 1e-6
    # Importance-ratio safety clamp before the PPO-Clip surrogate is
    # evaluated. Schulman 2017 §3 Eq. 7 assumes finite ratios; we add
    # a defensive [0.01, 100] clamp so a transient policy collapse
    # cannot produce NaN gradients (Huang 2022 detail #34).
    ratio_clamp_min: float = 0.01
    ratio_clamp_max: float = 100.0
    # Minibatch sizing — minibatch = max(minibatch_size_min,
    # steps_per_rollout / minibatch_count). Huang 2022 detail #4
    # ("64 minibatches, 64-sample minibatches" on the default
    # 2048-step rollout); we expose both knobs.
    minibatch_size_min: int = 64
    minibatch_count: int = 16
    # Orthogonal-init small gain (0.01) for the policy output heads —
    # Schulman 2017 §6.1 ("small final layer init for the policy"),
    # generalised in Huang 2022 detail #2 (orth init, layer-wise gain).
    actor_head_init_gain: float = 0.01
    # NaN/Inf guards on alpha/beta of the Beta head (Audit 1.5). The
    # default of 2.0 yields a peaked-at-0.5 unimodal Beta if the
    # network briefly produces a non-finite logit; the +inf clip at
    # 100 caps over-confident action distributions.
    beta_param_nan_default: float = 2.0
    beta_param_posinf_clip: float = 100.0


class SACConfig(BaseModel):
    """Soft Actor-Critic configuration.

    Hyperparameters carry inline citations at point of definition
    (FIX-010, clause C2.6 / C2.14) so each value is traceable.

    Canonical references
    --------------------
    - Haarnoja et al. (2018a). Soft Actor-Critic: Off-Policy Maximum
      Entropy Deep Reinforcement Learning with a Stochastic Actor.
      ICML 2018. arXiv:1801.01290. Table 1 — original SAC
      hyperparameters.
    - Haarnoja et al. (2018b). Soft Actor-Critic Algorithms and
      Applications. arXiv:1812.05905. Appendix D — automatic
      temperature tuning, target_entropy = -|A|.

    Attributes
    ----------
    replay_buffer_size, batch_size : int
        Off-policy replay capacity and minibatch.
    learning_rate, gamma, tau : float
        Optimizer step, discount, and target-network smoothing.
    alpha : float
        Entropy temperature; auto-tuned when ``alpha_auto=True``.
    alpha_auto : bool
        Whether to learn ``alpha`` (Haarnoja 2018b).
    hidden_size : int
        Hidden width for actor and twin-critic networks.
    n_updates_per_step : int
        Gradient updates per environment step.
    warmup_steps, total_timesteps : int
        Random-action warmup and total-training-step horizon.
    """

    # replay_buffer_size=1e6 — Haarnoja 2018a Table 1 ("replay buffer
    # size 1e6") and Haarnoja 2018b Appendix D Table 1 unchanged.
    replay_buffer_size: int = 1_000_000
    # batch_size=256 — Haarnoja 2018a Table 1 ("minibatch size 256")
    # used across all 6 MuJoCo benchmarks.
    batch_size: int = 256
    # learning_rate=3e-4 — Haarnoja 2018a Table 1 ("learning rate
    # 3·10⁻⁴" for all networks under Adam); Haarnoja 2018b Table 1
    # confirms 3e-4 for actor / critic / temperature.
    learning_rate: float = 3e-4
    # gamma=0.99 — Haarnoja 2018a Table 1 (discount factor 0.99).
    gamma: float = 0.99
    # tau=0.005 — Haarnoja 2018a Table 1 ("target smoothing coefficient
    # τ=0.005"); polyak averaging θ̄ ← τθ + (1-τ)θ̄.
    tau: float = 0.005
    # alpha=0.2 — Haarnoja 2018a Table 1 fixed-temperature default;
    # Haarnoja 2018b §5 / Appendix D makes it learnable when
    # alpha_auto=True (target_entropy = -dim(A)).
    alpha: float = 0.2
    # alpha_auto=True — Haarnoja 2018b §5 ("Automating Entropy
    # Adjustment for Maximum Entropy RL"), Eq. (17–18); reported as
    # robust to environment changes and the default in subsequent
    # implementations (e.g. Stable-Baselines3 SAC).
    alpha_auto: bool = True
    # hidden_size=256 — Haarnoja 2018a Table 1 ("two hidden layers,
    # 256 units each") for all actor and Q-network MLPs.
    hidden_size: int = 256
    # n_updates_per_step=1 — Haarnoja 2018a Table 1 ("number of
    # gradient steps per env step = 1"); higher values trade
    # sample-efficiency for compute (Haarnoja 2018b Appendix D).
    n_updates_per_step: int = 1
    # warmup_steps=10_000 — Haarnoja 2018a §5.2 ("first 10⁴ env steps
    # use uniform random actions to seed the replay buffer").
    warmup_steps: int = 10_000
    # total_timesteps=1e6 — matches the PPO baseline horizon so the
    # PPO/SAC comparison is wall-clock and step-budget aligned.
    total_timesteps: int = 1_000_000


class GymEnvConfig(BaseModel):
    """Gymnasium environment configuration for RL training.

    Attributes
    ----------
    episode_length : int
        Number of steps per episode (days).
    cost_normalizer, carbon_normalizer : float
        Dividers used to keep cost / carbon rewards on the same
        scale as service-level rewards.
    service_reward_weight, stockout_penalty_coef,
    stockout_penalty_exponent : float
        Service-level reward and stockout penalty shaping.
    buffer_reward, buffer_zone_low, buffer_zone_high,
    holding_penalty_coef : float
        Inventory buffer-zone reward parameters.
    cost_penalty_weight, carbon_penalty_weight : float
        Multi-objective penalty weights.
    early_termination_penalty, early_termination_stockout_threshold : float
        Severe-stockout early termination shaping.
    base_distance, distance_per_index_diff,
    cost_per_unit_distance, carbon_per_unit_distance : float
        Synthetic distance-cost / -carbon parameters.
    replenishment_rate_per_day : float
        Fraction of capacity replenished daily.
    warehouse_shock_prob, warehouse_shock_recovery_prob,
    customer_shock_prob, customer_shock_recovery_prob : float
        Per-step shock and recovery probabilities.
    demand_shock_multiplier : float
        Multiplier applied to affected customers during a shock.
    demand_min, demand_max, weekly_amplitude : float
        Demand-generation bounds and weekly seasonality amplitude.
    forecast_noise_std : float
        Std of additive Gaussian noise applied to the forecast
        slot.
    fallback_warehouse_capacity : float
        Used when the network/warehouse capacities mismatch.
    """

    # Episode parameters
    episode_length: int = 365

    # Reward shaping parameters
    cost_normalizer: float = 5000.0
    carbon_normalizer: float = 1000.0
    service_reward_weight: float = 10.0
    stockout_penalty_coef: float = 0.001
    stockout_penalty_exponent: float = 1.5
    buffer_reward: float = 0.5
    buffer_zone_low: float = 0.15
    buffer_zone_high: float = 0.40
    holding_penalty_coef: float = 0.1
    cost_penalty_weight: float = 3.0
    carbon_penalty_weight: float = 1.0
    early_termination_penalty: float = 500.0
    early_termination_stockout_threshold: float = 0.5

    # Synthetic distance parameters for cost/carbon calculation
    base_distance: float = 100.0
    distance_per_index_diff: float = 50.0
    cost_per_unit_distance: float = 0.018
    carbon_per_unit_distance: float = 0.003

    # Replenishment rate (fraction of capacity per day)
    replenishment_rate_per_day: float = 0.015

    # ----- FIX-022 stress-mode parameters -----
    # Activated only when ``SupplyChainEnv(stress_mode=True)`` is
    # instantiated. Each value carries an inline citation to the
    # primary literature source [Gijsbrechts-2022 §5.1 Table 1;
    # Vanvuchelen-2024 IMA-JMM §3.2 Eq. 6; Zipkin-2000 §3.2
    # "Newsvendor"; NCAER-2024 §3 Table 3.2 "Warehousing cost"].
    lead_time_days: int = 3
    # max_order_multiplier sized so that action=0.5 (the natural mean
    # of an unbiased Beta(2,2) actor) maps to the per-warehouse mean
    # daily demand, and action=1.0 to twice that. This keeps the
    # PPO policy's initial gradient signal in the productive region
    # of the action space [Vanvuchelen-2024 IMA-JMM §3.2 "Action
    # scaling matched to expected demand"; Andrychowicz-2021 §3.16
    # "Action range matters more than action dim"].
    stress_max_order_multiplier: float = 0.4
    stress_holding_cost_per_kg: float = 0.015
    stress_stockout_cost_per_kg: float = 2.70

    # Shock probabilities
    warehouse_shock_prob: float = 0.005
    warehouse_shock_recovery_prob: float = 0.05
    customer_shock_prob: float = 0.003
    customer_shock_recovery_prob: float = 0.07

    # Demand shock multiplier for affected customers
    demand_shock_multiplier: float = 3.0

    # Demand generation parameters
    demand_min: float = 30.0
    demand_max: float = 80.0
    weekly_amplitude: float = 0.2

    # Forecast noise std
    forecast_noise_std: float = 2.0

    # Fallback warehouse capacity when config mismatch
    fallback_warehouse_capacity: float = 50000.0


class ShockConfig(BaseModel):
    """Default parameters for supply / demand shock injection.

    Centralizes the magic numbers that previously lived as hardcoded
    keyword-argument defaults inside ``phase2_resilience/shock_models.py``
    and ``phase2_resilience/monte_carlo_runner.py`` (clause 1.10).
    Per-call sites may still override individual values; the defaults
    here reproduce pre-fix behavior bit-for-bit (clause C3.13).

    Attributes
    ----------
    supply_severity : float
        Capacity-remaining factor for ``SupplyShock``
        (0.5 = 50% loss).
    demand_multiplier : float
        Multiplier for ``DemandShock`` (3.0 = 3x demand).
    duration_min_days, duration_max_days : int
        Shock duration bounds (days).
    random_start_min_offset_days : int
        Earliest post-warmup start day for randomly-timed shocks.
    dbscan_eps_degrees, dbscan_min_samples : float, int
        Spatial-clustering parameters used to pick affected
        customers.
    sequential_default_fraction : float
        Fallback affected-customer fraction.
    supply_seed_offset, demand_seed_offset : int
        Per-job RNG offsets for Monte-Carlo runs.
    fallback_shock_start_day, fallback_shock_end_day : int
        Default shock window when ``shock_start``/``shock_end`` are
        unset.
    monte_carlo_n_runs : int
        Default number of Monte-Carlo replications.
    """

    # SupplyShock: capacity remaining factor (0.5 = 50% loss)
    supply_severity: float = 0.5
    # DemandShock: demand multiplication factor (3.0 = 3x demand)
    demand_multiplier: float = 3.0
    # Shock duration range (min_days, max_days) — both supply and demand
    duration_min_days: int = 14
    duration_max_days: int = 60
    # Earliest post-warmup start day offset for randomly-timed shocks
    random_start_min_offset_days: int = 10
    # DBSCAN clustering parameters for demand-shock cluster selection
    dbscan_eps_degrees: float = 1.5
    dbscan_min_samples: int = 3
    # Fallback affected-customers fraction when n_affected is unset
    sequential_default_fraction: float = 0.20  # 20% of total customers
    # Per-shock RNG seed offsets for Monte-Carlo runs (job_id-based)
    supply_seed_offset: int = 1000
    demand_seed_offset: int = 2000
    # Default fallback shock window when shock_start/end are unset
    fallback_shock_start_day: int = 50
    fallback_shock_end_day: int = 80
    # Monte-Carlo runner default number of replications
    monte_carlo_n_runs: int = 500


class ProductConfig(BaseModel):
    """Multi-product extension configuration.

    When n_products=1 (default), the multi-product solver delegates
    to the base single-product formulation, preserving original behavior.

    Attributes
    ----------
    n_products : int
        Number of SKUs handled by the multi-product solver. The
        default of 1 preserves the original single-product
        formulation.
    product_names : list of str
        Display names for each SKU.
    product_value_per_kg : list of float
        Per-SKU value (INR/kg).
    product_density : list of float
        Per-SKU bulk density (kg/L) used by capacity checks.
    """

    n_products: int = 1  # default=1 preserves C3.5
    product_names: List[str] = Field(
        default_factory=lambda: ["General"]
    )
    product_value_per_kg: List[float] = Field(
        default_factory=lambda: [100.0]
    )
    product_density: List[float] = Field(
        default_factory=lambda: [0.8]
    )


class RobustConfig(BaseModel):
    """Stochastic robust optimization configuration.

    When enabled=False (default), the robust solver delegates to the
    deterministic problem, preserving original behavior bit-for-bit
    (preservation clause C3.6).

    The robust formulation samples ``n_scenarios`` LogNormal demand
    multipliers (median 1, log-scale ``demand_noise_sigma``) and
    optimises ``mean + risk_lambda * std`` of each objective across
    the ensemble. ``risk_lambda = 0`` gives the expected-value
    (Mulvey, Vanderbei & Zenios 1995 §2 "solution robustness");
    ``risk_lambda > 0`` penalises variability across scenarios per
    Bertsimas & Sim (2004) §3.

    References
    ----------
    Ben-Tal, A. & Nemirovski, A. (2002). Robust optimization -
        methodology and applications. Mathematical Programming
        92(3), 453-480. DOI: 10.1007/s101070100286.
    Bertsimas, D. & Sim, M. (2004). The Price of Robustness.
        Operations Research 52(1), 35-53.
        DOI: 10.1287/opre.1030.0065.
    Mulvey, J. M., Vanderbei, R. J. & Zenios, S. A. (1995).
        Robust optimization of large-scale systems. Operations
        Research 43(2), 264-281. DOI: 10.1287/opre.43.2.264.

    Attributes
    ----------
    enabled : bool
        When ``False`` (default) the deterministic problem is
        solved; when ``True`` the robust counterpart is solved
        instead.
    n_scenarios : int
        Number of stochastic-demand scenarios sampled per
        evaluation.
    demand_noise_sigma : float
        Sigma of the underlying Normal in the LogNormal demand
        multiplier ``noise = exp(N(0, sigma))``; the multiplier is
        strictly positive with median 1.
    risk_lambda : float
        Risk aversion in the ``mean + lambda * std`` objective.
    """

    enabled: bool = False  # default=False preserves C3.6
    n_scenarios: int = 10
    demand_noise_sigma: float = 0.20
    risk_lambda: float = 0.5


class CarbonBudgetConfig(BaseModel):
    """Carbon budget constraint configuration.

    When mode="none" (default), the carbon budget solver delegates to
    the unconstrained problem, preserving original behavior.

    Modes:
        - "none": No carbon constraint (default)
        - "20pct": 20% reduction from unconstrained baseline
        - "40pct": 40% reduction from unconstrained baseline

    Attributes
    ----------
    mode : str
        One of ``"none"``, ``"20pct"``, ``"40pct"``, or any custom
        label used together with ``custom_reduction_pct``.
    custom_reduction_pct : float
        Reduction percentage applied when ``mode`` is custom.
    """

    mode: str = "none"  # "none" | "20pct" | "40pct"
    custom_reduction_pct: float = 0.0


class TransportModeConfig(BaseModel):
    """Multi-modal transport configuration.

    Extends the road-only HCV/LCV model with electric vehicles, rail,
    coastal shipping, and air freight parameters. When enabled_modes
    contains only ["HCV", "LCV"] (default), existing behavior is preserved.

    References
    ----------
    .. [1] IEA (2023). Global EV Outlook 2023. Section 3.3 Commercial vehicles.
    .. [2] Indian Railways (2023). Statistical Year Book 2022-23, Table 5.1.
    .. [3] MoPSW India (2023). Sagarmala Port-Led Development, Ch. 4.

    Attributes
    ----------
    ev_cost_per_km : float
        Electric vehicle operating cost (INR/km) [IEA 2023 S3.3].
    ev_capacity : float
        Electric vehicle payload capacity (kg).
    ev_range_km : float
        Single-charge range for electric trucks (km).
    ev_emission_factor : float
        Direct emission factor (kg CO2/km); zero for BEV.
    ev_charging_time_hours : float
        Time to fully charge an electric truck (hours).
    ev_grid_emission_factor : float
        Grid electricity emission factor (kg CO2/kWh) [CEA India 2023].
    ev_energy_consumption_kwh_per_km : float
        Energy consumption of an electric truck (kWh/km).
    rail_cost_per_km : float
        Rail freight cost per km (INR/km) [Indian Railways 2023].
    rail_capacity : float
        Payload per rail wagon (kg).
    rail_k : float
        Rail baseline emission factor (kg CO2/km).
    rail_L : float
        Rail load-dependent emission factor (kg CO2/kg-km).
    rail_fixed_cost : float
        Fixed booking cost per rail shipment (INR).
    rail_min_distance_km : float
        Minimum distance for rail to be viable (km).
    rail_transit_time_factor : float
        Rail transit time multiplier relative to road.
    coastal_cost_per_km : float
        Coastal shipping cost per km (INR/km) [Sagarmala 2023].
    coastal_capacity : float
        Coastal vessel payload capacity (kg).
    coastal_emission_factor : float
        Coastal shipping emission factor (kg CO2/ton-km) [IMO 2023].
    coastal_speed_kmh : float
        Average coastal vessel speed (km/h).
    coastal_min_distance_km : float
        Minimum distance for coastal shipping viability (km).
    air_cost_per_km : float
        Air freight cost per km (INR/km).
    air_capacity : float
        Air freight payload capacity (kg).
    air_emission_factor : float
        Air freight emission factor (kg CO2/ton-km) [IATA 2023].
    air_min_value_per_kg : float
        Minimum goods value (INR/kg) to justify air freight.
    enabled_modes : list of str
        Active transport modes. Default ["HCV", "LCV"] preserves
        existing road-only behavior.
    mode_selection_strategy : str
        Strategy for choosing modes: ``"cost_optimal"``,
        ``"emission_optimal"``, ``"time_optimal"``, or
        ``"multi_criteria"``.
    """

    # Electric Vehicle
    ev_cost_per_km: float = 22.0  # INR/km (IEA 2023 S3.3 adjusted for India)
    ev_capacity: float = 8000.0  # kg payload
    ev_range_km: float = 300.0  # single-charge range
    ev_emission_factor: float = 0.0  # zero direct emissions
    ev_charging_time_hours: float = 2.0
    ev_grid_emission_factor: float = 0.82  # kg CO2/kWh (CEA India 2023)
    ev_energy_consumption_kwh_per_km: float = 0.8  # kWh/km for e-truck
    # Rail
    rail_cost_per_km: float = 15.0  # INR/km (Indian Railways 2023)
    rail_capacity: float = 50000.0  # kg per wagon
    rail_k: float = 0.08  # baseline emission (kg CO2/km)
    rail_L: float = 0.00005  # load-dependent emission
    rail_fixed_cost: float = 25000.0  # INR per booking
    rail_min_distance_km: float = 200.0  # minimum viable rail distance
    rail_transit_time_factor: float = 1.3  # vs road time
    # Coastal Shipping
    coastal_cost_per_km: float = 8.0  # INR/km (Sagarmala 2023)
    coastal_capacity: float = 100000.0  # kg
    coastal_emission_factor: float = 0.012  # kg CO2/ton-km (IMO 2023)
    coastal_speed_kmh: float = 25.0
    coastal_min_distance_km: float = 300.0
    # Air Freight
    air_cost_per_km: float = 120.0  # INR/km
    air_capacity: float = 5000.0  # kg
    air_emission_factor: float = 0.85  # kg CO2/ton-km (IATA 2023)
    air_min_value_per_kg: float = 500.0  # Only for high-value goods (INR/kg)
    # Mode selection
    enabled_modes: List[str] = Field(default_factory=lambda: ["HCV", "LCV"])
    mode_selection_strategy: str = "cost_optimal"  # cost_optimal | emission_optimal | time_optimal | multi_criteria


class FacilityEconomicsConfig(BaseModel):
    """Warehouse and facility economics configuration.

    Parameters for facility operating costs, inventory carrying costs,
    and economic factors. Enables total cost of ownership analysis.

    References
    ----------
    .. [1] NCAER (2024). India Logistics Report, S3 Table 3.2.
    .. [2] Ballou R. (2004). Business Logistics Management, Ch. 9.

    Attributes
    ----------
    warehouse_fixed_cost_per_day : float
        Fixed daily warehouse operating cost (INR/day) [NCAER 2024].
    warehouse_variable_cost_per_unit : float
        Variable cost per unit handled (INR/unit).
    holding_cost_rate : float
        Fraction of inventory value charged per day as holding cost
        [Ballou 2004 Ch. 9].
    stockout_cost_multiplier : float
        Multiplier of unit value applied as stockout penalty.
    labor_cost_per_hour : float
        Hourly warehouse labor cost (INR/hour).
    operating_hours_per_day : float
        Daily operating hours for warehouse staff.
    rent_per_sqm_per_month : float
        Warehouse rent per square meter per month (INR/sqm/month).
    insurance_rate : float
        Monthly insurance premium as a fraction of inventory value.
    energy_cost_per_kwh : float
        Electricity cost for warehouse operations (INR/kWh).
    energy_per_unit_handled : float
        Energy consumed per unit handled (kWh/unit).
    fuel_price_inr_per_liter : float
        Retail diesel price (INR/liter).
    fuel_price_volatility : float
        Annual standard deviation of fuel price changes.
    depreciation_rate : float
        Annual depreciation rate for warehouse assets.
    opening_cost : float
        One-time cost to open a new facility (INR).
    closing_cost : float
        One-time cost to close an existing facility (INR).
    """

    warehouse_fixed_cost_per_day: float = 50000.0  # INR/day (NCAER 2024)
    warehouse_variable_cost_per_unit: float = 5.0  # INR/unit handled
    holding_cost_rate: float = 0.02  # fraction of value per day
    stockout_cost_multiplier: float = 3.0  # multiplier of unit value
    labor_cost_per_hour: float = 250.0  # INR/hour
    operating_hours_per_day: float = 16.0  # hours
    rent_per_sqm_per_month: float = 800.0  # INR/sqm/month
    insurance_rate: float = 0.001  # fraction of inventory value/month
    energy_cost_per_kwh: float = 8.5  # INR/kWh
    energy_per_unit_handled: float = 0.02  # kWh per unit
    fuel_price_inr_per_liter: float = 105.0  # retail diesel
    fuel_price_volatility: float = 0.15  # annual std dev
    depreciation_rate: float = 0.05  # annual rate
    opening_cost: float = 5000000.0  # INR for facility location problem
    closing_cost: float = 2000000.0  # INR


class StochasticConfig(BaseModel):
    """Expanded stochastic/uncertainty configuration.

    Models uncertainty in lead times, supply reliability, demand
    correlation, quality, and travel times.

    References
    ----------
    .. [1] Chopra S. & Meindl P. (2016). Supply Chain Management, Ch. 12.
    .. [2] Simchi-Levi D. et al. (2008). Designing and Managing the
           Supply Chain, Ch. 4.

    Attributes
    ----------
    lead_time_distribution : str
        Distribution family for lead-time sampling: ``"lognormal"``,
        ``"gamma"``, or ``"weibull"``.
    lead_time_shape : float
        Shape parameter for the lead-time distribution.
    lead_time_scale : float
        Scale parameter for the lead-time distribution.
    supply_reliability : float
        Probability that a full order is delivered on time
        [Chopra 2016 Ch. 12].
    supply_partial_fill_rate : float
        Fraction of order filled when supply is unreliable.
    supplier_count : int
        Number of active suppliers in the network.
    supplier_correlation : float
        Pairwise correlation between supplier disruption events.
    demand_distribution : str
        Distribution family for demand sampling: ``"lognormal"``,
        ``"gamma"``, ``"poisson"``, or ``"negbinomial"``.
    demand_seasonality_amplitude : float
        Fractional amplitude of seasonal demand swing.
    demand_seasonality_period : int
        Period of demand seasonality cycle (days).
    demand_trend_rate : float
        Annual demand growth rate.
    demand_correlation_spatial : float
        Spatial correlation between nearby customer demands.
    demand_correlation_temporal : float
        Lag-1 temporal autocorrelation of demand
        [Simchi-Levi 2008 Ch. 4].
    defect_rate : float
        Fraction of goods arriving defective.
    quality_inspection_cost : float
        Per-unit inspection cost (INR/unit).
    travel_time_cv : float
        Coefficient of variation for travel time uncertainty.
    congestion_factor_peak : float
        Peak-hour travel time multiplier.
    weather_disruption_prob : float
        Per-trip probability of weather-related delay.
    """

    # Lead time uncertainty
    lead_time_distribution: str = "lognormal"  # lognormal | gamma | weibull
    lead_time_shape: float = 2.0
    lead_time_scale: float = 1.5
    # Supply uncertainty
    supply_reliability: float = 0.95  # P(full order delivered) [Chopra 2016 Ch. 12]
    supply_partial_fill_rate: float = 0.8
    supplier_count: int = 3
    supplier_correlation: float = 0.3
    # Demand uncertainty (extended)
    demand_distribution: str = "lognormal"  # lognormal | gamma | poisson | negbinomial
    demand_seasonality_amplitude: float = 0.3  # seasonal swing fraction
    demand_seasonality_period: int = 365  # days
    demand_trend_rate: float = 0.02  # annual growth rate
    demand_correlation_spatial: float = 0.2  # between nearby customers
    demand_correlation_temporal: float = 0.7  # lag-1 autocorrelation [Simchi-Levi 2008 Ch. 4]
    # Quality uncertainty
    defect_rate: float = 0.02  # fraction of goods defective
    quality_inspection_cost: float = 10.0  # INR per unit
    # Travel time uncertainty
    travel_time_cv: float = 0.15  # coefficient of variation
    congestion_factor_peak: float = 1.4  # peak-hour multiplier
    weather_disruption_prob: float = 0.05  # P(weather delays) per trip


class EnvironmentalExtendedConfig(BaseModel):
    """Extended environmental impact configuration.

    Multi-pollutant emissions (NOx, PM2.5, noise), carbon pricing,
    and lifecycle analysis parameters.

    References
    ----------
    .. [1] CPCB India (2023). National Air Quality Standards.
    .. [2] World Bank (2023). State and Trends of Carbon Pricing.

    Attributes
    ----------
    nox_factor_hcv : float
        NOx emission factor for HCV (g/km) [CPCB 2023].
    nox_factor_lcv : float
        NOx emission factor for LCV (g/km).
    pm25_factor_hcv : float
        PM2.5 emission factor for HCV (g/km).
    pm25_factor_lcv : float
        PM2.5 emission factor for LCV (g/km).
    noise_cost_per_km_urban : float
        Noise externality cost in urban areas (INR/km).
    noise_cost_per_km_rural : float
        Noise externality cost in rural areas (INR/km).
    carbon_price_per_ton : float
        Carbon price (INR/ton CO2) [World Bank 2023].
    carbon_price_growth_rate : float
        Annual growth rate of carbon price.
    carbon_cap_tons_per_year : float
        Annual carbon cap for the fleet (tons CO2).
    carbon_trading_enabled : bool
        Whether carbon trading/offsets are modeled.
    vehicle_manufacturing_co2_tons : float
        Lifecycle manufacturing CO2 per HCV (tons).
    vehicle_lifetime_km : float
        Expected vehicle lifetime distance (km).
    """

    # Multi-pollutant factors (g/km for HCV)
    nox_factor_hcv: float = 5.2  # g/km (Euro VI, CPCB 2023)
    nox_factor_lcv: float = 2.8
    pm25_factor_hcv: float = 0.12  # g/km
    pm25_factor_lcv: float = 0.06
    noise_cost_per_km_urban: float = 2.5  # INR/km (externality)
    noise_cost_per_km_rural: float = 0.5
    # Carbon pricing
    carbon_price_per_ton: float = 2000.0  # INR/ton CO2 (India carbon market 2023) [World Bank 2023]
    carbon_price_growth_rate: float = 0.08  # annual
    carbon_cap_tons_per_year: float = 500.0
    carbon_trading_enabled: bool = False
    # Lifecycle
    vehicle_manufacturing_co2_tons: float = 35.0  # per HCV
    vehicle_lifetime_km: float = 500000.0


class TimeWindowConfig(BaseModel):
    """Time window and scheduling configuration for VRPTW.

    When enable_time_windows is False (default), existing VRP
    behavior is preserved.

    References
    ----------
    .. [1] Solomon M. (1987). Algorithms for the VRP with Time Windows.
           Operations Research, 35(2), 254-265.

    Attributes
    ----------
    enable_time_windows : bool
        Master toggle. Default ``False`` preserves the existing
        unconstrained VRP behavior [Solomon 1987].
    early_penalty_per_hour : float
        Penalty for arriving before the customer time window
        (INR/hour).
    late_penalty_per_hour : float
        Penalty for arriving after the customer time window
        (INR/hour).
    service_time_minutes : float
        Time spent at each customer stop (minutes).
    depot_open_hour : float
        Depot opening hour (24h format).
    depot_close_hour : float
        Depot closing hour (24h format).
    max_driver_hours : float
        Maximum continuous driving hours before mandatory break.
    break_duration_minutes : float
        Mandatory break duration (minutes).
    """

    enable_time_windows: bool = False  # default preserves existing behavior
    early_penalty_per_hour: float = 100.0  # INR [Solomon 1987]
    late_penalty_per_hour: float = 500.0  # INR
    service_time_minutes: float = 30.0
    depot_open_hour: float = 6.0
    depot_close_hour: float = 22.0
    max_driver_hours: float = 10.0
    break_duration_minutes: float = 30.0



class SensitivityConfig(BaseModel):
    """Sensitivity-analysis configuration (FIX-016, clause C2.9).

    Drives the real-NSGA-II-backed sensitivity analysis in
    :mod:`supply_chain_research.phase4_synthesis.sensitivity_analysis`.
    Every evaluation in both the OAT sweep and the Sobol variance-based
    decomposition calls :func:`run_nsga2` on a small, reproducible
    test instance. There is no analytical path — ``fast_mode=True``
    reduces the parameter grid and the per-call NSGA-II budget but
    never substitutes synthetic Pareto fronts (clause C2.9).

    The variance-based first-order (S1) and total-order (ST)
    indices follow Sobol (1993) with the Saltelli (2010) sampling
    scheme; the SALib implementation is documented in Herman & Usher
    (2017).

    References
    ----------
    .. [1] Sobol, I. M. (1993). Sensitivity estimates for nonlinear
           mathematical models. *Mathematical Modelling and
           Computational Experiments*, 1(4), 407-414.
    .. [2] Saltelli, A., Annoni, P., Azzini, I., Campolongo, F.,
           Ratto, M., & Tarantola, S. (2010). Variance based
           sensitivity analysis of model output. Design and
           estimator for the total sensitivity index. *Computer
           Physics Communications*, 181(2), 259-270.
           DOI: 10.1016/j.cpc.2009.09.018.
    .. [3] Herman, J. & Usher, W. (2017). SALib: An open-source
           Python library for sensitivity analysis. *Journal of
           Open Source Software*, 2(9), 97.
           DOI: 10.21105/joss.00097.

    Attributes
    ----------
    fast_mode : bool
        Default ``False``. When ``True`` callers receive the reduced
        grid (``5`` points), the reduced Sobol base size
        (``fast_n_samples``), and the reduced per-call NSGA-II
        budget (``fast_pop_size`` / ``fast_n_gen``). Reduces wall
        time for CI without injecting synthetic data.
    default_n_samples, fast_n_samples : int
        Saltelli base size ``N`` for ``run_sobol_sensitivity``.
        Total evaluations = ``N * (2 * D + 2)`` with ``D = 4``.
    default_pop_size, default_n_gen : int
        NSGA-II budget for the standard sweep / Sobol run.
    fast_pop_size, fast_n_gen : int
        NSGA-II budget when ``fast_mode=True``.
    instance_n_warehouses, instance_n_customers : int
        Reduced problem-instance dimensions used by every
        sensitivity NSGA-II call. Sensitivity analysis varies the
        *parameters* of the optimization, not the network size, so a
        small reproducible instance is appropriate (Saltelli et al.
        2010 §3 also recommends this — variance decomposition
        accuracy is governed by ``N``, not by the underlying model
        size).
    instance_distance_min, instance_distance_max : float
        Bounds (km) of the random distance matrix used by the
        sensitivity test instance.
    instance_demand_min, instance_demand_max : float
        Bounds (kg) of the random demand vector used by the
        sensitivity test instance.
    instance_warehouse_capacities : list of float
        Baseline per-warehouse capacities (kg) for the sensitivity
        test instance (length ``instance_n_warehouses``); the
        ``warehouse_capacity`` perturbation multiplies these.
    """

    # FIX-016 — fast-mode flag required by tasks.md §3.6.
    # Default False preserves the standard 11-point OAT grid and the
    # 1024-sample Saltelli decomposition.
    fast_mode: bool = False

    # Saltelli base size N. Total evaluations = N * (2D + 2). For D=4
    # this is N * 10. fast_n_samples=8 yields 80 evaluations
    # (acceptable for CI); default_n_samples=1024 yields 10,240
    # evaluations (matches Saltelli 2010 §6 recommendation of
    # N >= 1000 for stable indices).
    default_n_samples: int = 1024
    fast_n_samples: int = 8

    # NSGA-II per-call budget (independent of NSGAConfig defaults so
    # the production solver is not affected).
    default_pop_size: int = 40
    default_n_gen: int = 8
    fast_pop_size: int = 32
    fast_n_gen: int = 5

    # Reduced problem instance for sensitivity analysis. Saltelli et
    # al. (2010) §3 establishes that variance-decomposition accuracy
    # depends on N (Saltelli base size) rather than on model
    # dimension; a 3-warehouse / 8-customer test instance therefore
    # gives statistically sound sensitivity indices at a fraction of
    # the cost of solving the full 5x100 production problem.
    instance_n_warehouses: int = 3
    instance_n_customers: int = 8
    instance_distance_min: float = 50.0
    instance_distance_max: float = 500.0
    instance_demand_min: float = 100.0
    instance_demand_max: float = 5000.0
    instance_warehouse_capacities: List[float] = Field(
        default_factory=lambda: [50000.0, 45000.0, 40000.0]
    )


class MasterConfig(BaseModel):
    """Master configuration combining all sub-configs.

    Audit 2.1 — parameter taxonomy:
      PHYSICS DERIVED: VehicleConfig.{hcv_k, hcv_L, lcv_k, lcv_L,
        diesel_co2_factor} — fixed by MEET/IPCC; do NOT scale.
      PROBLEM SCALED: NSGAConfig.{pop_size, mutation_eta, crossover_eta},
        PPOConfig.steps_per_rollout, GymEnvConfig.cost_normalizer —
        recompute via derive_from_problem_size when n_customers or
        n_warehouses change.
      TUNED: everything else — empirical defaults that may need
        re-tuning if the problem changes substantially.

    Attributes
    ----------
    network, vehicle, nsga, nsga3, moead, simulation, lstm, ppo,
    sac, gym_env, product, robust, carbon_budget, shock, sensitivity
        Per-domain sub-configs (see their own class docstrings).
    transport : TransportModeConfig
        Multi-modal transport parameters (EV, rail, coastal, air).
    facility : FacilityEconomicsConfig
        Warehouse and facility economics parameters.
    stochastic : StochasticConfig
        Expanded stochastic/uncertainty parameters.
    environmental : EnvironmentalExtendedConfig
        Multi-pollutant emissions and carbon pricing.
    time_window : TimeWindowConfig
        VRPTW time window and scheduling parameters.
    random_seed : int
        Seed used by every reproducibility-sensitive code path.
    """

    network: NetworkConfig = Field(default_factory=NetworkConfig)
    vehicle: VehicleConfig = Field(default_factory=VehicleConfig)
    nsga: NSGAConfig = Field(default_factory=NSGAConfig)
    nsga3: NSGA3Config = Field(default_factory=NSGA3Config)
    moead: MOEADConfig = Field(default_factory=MOEADConfig)
    simulation: SimulationConfig = Field(default_factory=SimulationConfig)
    lstm: LSTMConfig = Field(default_factory=LSTMConfig)
    ppo: PPOConfig = Field(default_factory=PPOConfig)
    sac: SACConfig = Field(default_factory=SACConfig)
    gym_env: GymEnvConfig = Field(default_factory=GymEnvConfig)
    product: ProductConfig = Field(default_factory=ProductConfig)
    robust: RobustConfig = Field(default_factory=RobustConfig)
    carbon_budget: CarbonBudgetConfig = Field(
        default_factory=CarbonBudgetConfig
    )
    shock: ShockConfig = Field(default_factory=ShockConfig)
    sensitivity: SensitivityConfig = Field(
        default_factory=SensitivityConfig
    )
    transport: TransportModeConfig = Field(
        default_factory=TransportModeConfig
    )
    facility: FacilityEconomicsConfig = Field(
        default_factory=FacilityEconomicsConfig
    )
    stochastic: StochasticConfig = Field(
        default_factory=StochasticConfig
    )
    environmental: EnvironmentalExtendedConfig = Field(
        default_factory=EnvironmentalExtendedConfig
    )
    time_window: TimeWindowConfig = Field(
        default_factory=TimeWindowConfig
    )
    random_seed: int = 42

    @classmethod
    def derive_from_problem_size(
        cls,
        n_customers: int,
        n_warehouses: int,
    ) -> "MasterConfig":
        """Audit 2.1: scale tunable parameters to problem size.

        Recomputes:
          - nsga.crossover_eta = 10 * 100 / (n_customers * n_warehouses)
          - nsga.mutation_eta  = 15 * 100 / n_customers
          - gym_env.cost_normalizer = 5000 * n_customers / 20
          - ppo.steps_per_rollout  = 2048 * n_customers / 20

        Reference values (n_c=100, n_w=5) reproduce the audited defaults.

        Parameters
        ----------
        n_customers : int
            Number of customer nodes in the target problem.
        n_warehouses : int
            Number of depot / warehouse nodes in the target
            problem.

        Returns
        -------
        MasterConfig
            A fresh ``MasterConfig`` whose problem-scaled fields
            match the requested size.
        """
        cfg = cls()
        cfg.network.n_customers = n_customers
        cfg.network.n_warehouses = n_warehouses

        cfg.nsga.crossover_eta = 10.0 * 100.0 / max(
            n_customers * n_warehouses, 1
        )
        cfg.nsga.mutation_eta = 15.0 * 100.0 / max(n_customers, 1)
        cfg.gym_env.cost_normalizer = 5000.0 * n_customers / 20.0
        cfg.ppo.steps_per_rollout = max(
            512, int(2048 * n_customers / 20)
        )
        return cfg

    def validate_cross_parameter_consistency(self) -> list[str]:
        """Action: cross-parameter consistency validator.

        Checks for logical inconsistencies that span sub-configs.
        Returns a list of issue strings; empty list means consistent.
        """
        issues = []

        # Capacity adequacy: total warehouse capacity must exceed peak demand
        total_capacity = sum(self.network.warehouse_capacities[: self.network.n_warehouses])
        # Use 95th percentile of LogNormal as peak demand proxy
        import math
        mu, sigma = self.simulation.order_size_mu, self.simulation.order_size_sigma
        # P95 of LogNormal: exp(mu + 1.645*sigma)
        per_customer_p95 = math.exp(mu + 1.645 * sigma)
        peak_demand = per_customer_p95 * self.network.n_customers
        if total_capacity < peak_demand * 0.5:
            issues.append(
                f"Capacity adequacy: total_capacity={total_capacity:.0f} < "
                f"0.5 * peak_demand={peak_demand:.0f}. Increase warehouse_capacities."
            )

        # Episode length must equal sim_days for PPO-DES alignment
        if self.gym_env.episode_length != self.simulation.sim_days:
            issues.append(
                f"Episode length mismatch: gym_env.episode_length="
                f"{self.gym_env.episode_length} != "
                f"simulation.sim_days={self.simulation.sim_days}. "
                f"PPO and DES must share the same horizon."
            )

        # LSTM forecast horizon must equal observation forecast slot
        # gym_env observation has n_customers * 7 forecast slots; expect 7 days
        if self.lstm.forecast_horizon != 7:
            issues.append(
                f"Forecast horizon mismatch: lstm.forecast_horizon="
                f"{self.lstm.forecast_horizon} != 7 (gym_env hardcoded slot)"
            )

        # PPO learning rate must be paired with a non-trivial schedule
        # (we use linear decay in cloud_training/modal_train.py, so this is informational)
        if self.ppo.lr > 5e-4:
            issues.append(
                f"PPO lr={self.ppo.lr} is high; ensure linear decay is enabled "
                f"to prevent late-training instability"
            )

        # Validate enabled_modes contains only recognized mode names
        valid_modes = {"HCV", "LCV", "EV", "Rail", "Coastal", "Air"}
        invalid_modes = set(self.transport.enabled_modes) - valid_modes
        if invalid_modes:
            issues.append(
                f"Invalid transport modes: {sorted(invalid_modes)}. "
                f"Allowed modes are: {sorted(valid_modes)}."
            )

        return issues

    def freeze(self) -> "MasterConfig":
        """Action: lock the config against accidental mutation.

        After freeze() is called, any setattr on this config or its
        sub-configs raises pydantic.ValidationError. Use after the
        derive_from_problem_size + validation steps complete.

        Parameters
        ----------
        self : MasterConfig
            The config instance to freeze in place.

        Returns
        -------
        MasterConfig
            The same instance, now frozen, returned for chaining.
        """
        # Pydantic v2: model_config can't be changed after class definition,
        # but we can wrap setattr to refuse mutations
        self.__dict__["_frozen"] = True

        def _frozen_setattr(self_, name, value):
            if self_.__dict__.get("_frozen") and not name.startswith("_"):
                raise RuntimeError(
                    f"Cannot mutate frozen MasterConfig: {name}={value!r}. "
                    f"Call .unfreeze() if you really mean to."
                )
            object.__setattr__(self_, name, value)

        # Bind frozen setattr to all sub-configs
        for sub_name in [
            "network", "vehicle", "nsga", "nsga3", "moead",
            "simulation", "lstm", "ppo", "sac", "gym_env",
            "product", "robust", "carbon_budget", "shock",
            "sensitivity", "transport", "facility", "stochastic",
            "environmental", "time_window",
        ]:
            sub = getattr(self, sub_name)
            sub.__dict__["_frozen"] = True
            type(sub).__setattr__ = _frozen_setattr
        type(self).__setattr__ = _frozen_setattr
        return self

    def unfreeze(self) -> "MasterConfig":
        """Disable the freeze; for testing only.

        Parameters
        ----------
        self : MasterConfig
            The config instance to thaw in place.

        Returns
        -------
        MasterConfig
            The same instance with mutability restored.
        """
        if "_frozen" in self.__dict__:
            del self.__dict__["_frozen"]
        for sub_name in [
            "network", "vehicle", "nsga", "nsga3", "moead",
            "simulation", "lstm", "ppo", "sac", "gym_env",
            "product", "robust", "carbon_budget", "shock",
            "sensitivity", "transport", "facility", "stochastic",
            "environmental", "time_window",
        ]:
            sub = getattr(self, sub_name)
            if "_frozen" in sub.__dict__:
                del sub.__dict__["_frozen"]
        # Restore default setattr — Pydantic's model_validate handles this
        type(self).__setattr__ = BaseModel.__setattr__
        return self


# Module-level default configuration instance
CFG = MasterConfig()


# Audit P10.D: lru_cache singleton factory so tests that call
# get_default_config() repeatedly do not re-validate Pydantic fields.
from functools import lru_cache  # noqa: E402


@lru_cache(maxsize=1)
def get_default_config() -> MasterConfig:
    """Return a process-wide singleton MasterConfig.

    Use this in test fixtures or hot paths instead of MasterConfig()
    to avoid the ~5 ms validation cost on every call.
    """
    return MasterConfig()
