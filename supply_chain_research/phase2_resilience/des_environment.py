"""Discrete Event Simulation environment using SimPy.

Models a supply chain network with warehouses as inventory containers
and customers generating orders via Poisson process. Tracks service
levels, delivery times, costs, and emissions.

Design Note on Time-Stepped Approach:
    The current implementation processes all customer orders in a single
    loop per day (time-stepped) rather than modeling individual order
    arrivals as stochastic inter-arrival events. This is a deliberate
    design choice that avoids SimPy Container race conditions. Because
    all orders for a given day are processed sequentially within the same
    simulation step (no yield between check and get), there is no risk of
    interleaving where two processes both observe sufficient inventory and
    then both attempt to withdraw, potentially causing negative levels.
    If future versions adopt an event-driven per-order architecture with
    separate SimPy processes for each order, a timeout-based reservation
    pattern (request -> yield timeout -> confirm/rollback) would be needed
    to prevent Container race conditions.
"""

import numpy as np
import simpy

# SimPy 4.x version guard — ensures compatibility with current API patterns.
# SimPy 4.0 (2020-04-06) eliminated BaseEnvironment and Environment.exit();
# all other core APIs (Container, Resource, env.process, env.timeout, env.now,
# env.run) remain unchanged from 3.x.
# Reference: https://simpy.readthedocs.io/en/stable/about/history.html
assert tuple(int(x) for x in simpy.__version__.split(".")[:2]) >= (4, 0), \
    f"SimPy >= 4.0 required; found {simpy.__version__}"

from supply_chain_research.config import MasterConfig


class Warehouse:
    """Warehouse with SimPy Container-based inventory management.

    Uses SimPy 4.x Container resource for inventory tracking.
    SimPy 4.x API patterns verified against SimPy 4.1.1 documentation:
    - simpy.Container(env, capacity, init) — unchanged from 3.x [SimPy docs §Resources]
    - container.get(amount) / container.put(amount) — unchanged from 3.x
    - container.level property — unchanged from 3.x
    Reference: https://simpy.readthedocs.io/en/stable/api_reference/simpy.resources.html

    Parameters
    ----------
    env : simpy.Environment
        Hosting SimPy environment.
    warehouse_id : int
        Integer ID of this warehouse.
    capacity : float
        Maximum inventory capacity in kg.
    initial_level : float
        Starting inventory level in kg.
    replenishment_rate_multiplier : float, optional
        Weekly replenishment as a fraction of capacity (default
        2.4 — see :class:`SimulationConfig`).

    Attributes
    ----------
    env : simpy.Environment
        Hosting SimPy environment.
    warehouse_id : int
        Integer warehouse identifier.
    capacity : float
        Maximum inventory capacity (kg).
    container : simpy.Container
        Underlying SimPy resource that holds the inventory level.
    replenishment_rate : float
        Weekly replenishment quantity (kg/week).
    shock_factor : float
        Capacity-availability multiplier; ``1.0`` is healthy,
        smaller values indicate active supply shocks.
    """

    def __init__(self, env, warehouse_id, capacity, initial_level,
                 replenishment_rate_multiplier=2.4):
        """Initialize warehouse.

        Args:
            env: SimPy environment.
            warehouse_id: Integer ID of this warehouse.
            capacity: Maximum inventory capacity in kg.
            initial_level: Starting inventory level in kg.
            replenishment_rate_multiplier: Weekly replenishment as fraction of capacity.
        
        Parameters
        ----------
        """
        self.env = env
        self.warehouse_id = warehouse_id
        self.capacity = capacity
        self.container = simpy.Container(
            env, capacity=capacity, init=initial_level
        )
        # Calibrated for: 100 customers * lambda=3.5 * exp(5.5 + 0.4^2/2) ~ 92,775 kg/day demand.
        # Daily inflow = sum(cap_i * 2.4 / 7) ~ 88,457 kg/day; initial 80% fill provides buffer.
        # Must recalibrate if lambda_orders, n_customers, or des_order_size_mu change.
        self.replenishment_rate = capacity * replenishment_rate_multiplier  # weekly rate, applied daily as rate/7
        self.shock_factor = 1.0  # 1.0 = normal, <1.0 = reduced

    @property
    def level(self):
        """Current inventory level.
        Parameters
        ----------
        """
        return self.container.level

    def fulfill(self, quantity):
        """Try to fulfill an order quantity.

        This method checks level before get() and is called within
        a non-yielding loop (time-stepped), so there is no
        interleaving risk from other SimPy processes between the
        check and the get.

        Args:
            quantity: Requested quantity in kg.

        Returns:
            Tuple of (fulfilled_quantity, success_bool).
        
        Parameters
        ----------
        """
        available = self.container.level
        # Audit P5.B: epsilon guard against SimPy float-comparison
        # spurious blocking when accumulated rounding makes `available`
        # slightly negative. We do NOT subtract eps from the fulfilled
        # quantity itself — that would break tests asserting exact
        # equality and is unnecessary because the SimPy guard happens
        # only at the level check.
        EPS = 1e-9
        if available <= EPS:
            return 0.0, False

        fulfill_qty = min(quantity, available)
        if fulfill_qty > EPS:
            # Clip ever-so-slight overshoot to available level
            fulfill_qty = min(fulfill_qty, available)
            self.container.get(fulfill_qty)
            return fulfill_qty, True
        return 0.0, False


class DESEnvironment:
    """SimPy-based discrete event simulation for supply chain.

    Simulates order arrivals, warehouse fulfillment, and tracks
    service level metrics over configurable time periods. Includes
    SLA tracking against the configured service_level_threshold
    (default 95%).

    SimPy 4.x API patterns used (all verified compatible with 4.1.1):
    - simpy.Environment() — replaces BaseEnvironment from 3.x [SimPy 4.0 changelog]
    - env.process(generator) — unchanged from 3.x
    - env.timeout(delay) — unchanged from 3.x
    - env.now — unchanged from 3.x
    - env.run(until=T) — unchanged from 3.x
    - yield env.timeout(1) — standard time-advance pattern
    Reference: https://simpy.readthedocs.io/en/stable/topical_guides/index.html

    Parameters
    ----------
    config : MasterConfig, optional
        Master configuration. When ``None`` a fresh config is
        constructed.
    distance_matrix : np.ndarray, optional
        Warehouse → customer distance matrix in km. When ``None``
        synthetic distances are generated.
    customer_locations : np.ndarray, optional
        Customer ``(lat, lon)`` array; passed through to shock
        models.
    seed : int, optional
        Reproducibility seed; defaults to ``config.random_seed``.

    Attributes
    ----------
    env : simpy.Environment
        Hosting SimPy 4.x environment.
    warehouses : list of Warehouse
        Per-warehouse SimPy actors.
    metrics : dict
        Running totals (orders served, stockouts, ...).
    shocks : list
        Registered ``DemandShock`` / ``SupplyShock`` instances.
    """

    def __init__(
        self,
        config=None,
        distance_matrix=None,
        seed=42,
    ):
        """Initialize DES environment.

        Args:
            config: MasterConfig instance. Uses defaults if None.
            distance_matrix: Distance matrix in km, shape
                (n_warehouses, n_customers) or
                (n_warehouses + n_customers, n_warehouses + n_customers).
                If None, generates synthetic distances.
            seed: Random seed for reproducibility.
        
        Parameters
        ----------
        """
        if config is None:
            config = MasterConfig()
        self.config = config
        self.seed = seed
        self.rng = np.random.default_rng(seed)

        self.n_warehouses = config.network.n_warehouses
        self.n_customers = config.network.n_customers
        self.sim_days = config.simulation.sim_days
        self.warmup_days = config.simulation.warmup_days
        self.lambda_orders = config.simulation.lambda_orders
        self.order_size_mu = config.simulation.order_size_mu
        self.order_size_sigma = config.simulation.order_size_sigma
        self.service_level_threshold = config.simulation.service_level_threshold
        self.truck_speed_kmh = config.simulation.truck_speed_kmh
        self.truck_speed_noise_pct = config.simulation.truck_speed_noise_pct
        self.des_order_size_mu = config.simulation.des_order_size_mu
        self.des_order_size_sigma = config.simulation.des_order_size_sigma

        # Setup distance matrix
        self._setup_distance_matrix(distance_matrix)

        # Results tracking
        self.daily_orders = []
        self.daily_fulfilled = []
        self.daily_service_level = []
        self.daily_costs = []
        self.daily_emissions = []
        self.daily_sla_met = []
        self.daily_travel_times = []
        self.total_days_simulated = 0

        # Shock state
        self.active_shocks = []

    def _setup_distance_matrix(self, distance_matrix):
        """Setup the warehouse-to-customer distance matrix.

        Args:
            distance_matrix: Raw distance matrix or None.
        
        Parameters
        ----------
        """
        if distance_matrix is not None:
            if distance_matrix.ndim == 2:
                n_total = self.n_warehouses + self.n_customers
                if distance_matrix.shape[0] == n_total:
                    # Full matrix: extract warehouse-to-customer block
                    self.dist_matrix = distance_matrix[
                        :self.n_warehouses,
                        self.n_warehouses:
                    ]
                elif distance_matrix.shape == (
                    self.n_warehouses, self.n_customers
                ):
                    self.dist_matrix = distance_matrix
                else:
                    # Use as-is, best effort
                    self.dist_matrix = distance_matrix[
                        :self.n_warehouses, :self.n_customers
                    ]
            else:
                self.dist_matrix = self._generate_synthetic_distances()
        else:
            self.dist_matrix = self._generate_synthetic_distances()

    def _generate_synthetic_distances(self):
        """Generate synthetic distance matrix for testing.

        Returns:
            Array of shape (n_warehouses, n_customers) in km.
        
        Parameters
        ----------
        """
        return self.rng.uniform(
            self.config.simulation.synthetic_distance_min,
            self.config.simulation.synthetic_distance_max,
            size=(self.n_warehouses, self.n_customers)
        )

    def _find_nearest_warehouse(self, customer_id):
        """Find nearest warehouse to a customer.

        Args:
            customer_id: Integer customer index.

        Returns:
            Tuple of (warehouse_id, distance_km).
        
        Parameters
        ----------
        """
        distances = self.dist_matrix[:, customer_id]
        nearest = int(np.argmin(distances))
        return nearest, distances[nearest]

    def run(self):
        """Run the full simulation.

        Returns:
            Dictionary with simulation results.
        
        Parameters
        ----------
        """
        self.env = simpy.Environment()

        # Initialize warehouses with per-warehouse capacities from config
        capacities = self.config.network.warehouse_capacities
        self.warehouses = []
        for w_id in range(self.n_warehouses):
            cap = capacities[w_id] if w_id < len(capacities) else self.config.simulation.fallback_warehouse_capacity
            wh = Warehouse(
                self.env, w_id, cap,
                initial_level=cap * self.config.simulation.initial_inventory_fraction,
                replenishment_rate_multiplier=self.config.simulation.replenishment_rate_multiplier,
            )
            self.warehouses.append(wh)

        # Reset tracking
        self.daily_orders = []
        self.daily_fulfilled = []
        self.daily_service_level = []
        self.daily_costs = []
        self.daily_emissions = []
        self.daily_sla_met = []
        self.daily_travel_times = []

        # Start processes
        self.env.process(self._customer_order_process())
        self.env.process(self._replenishment_process())
        self.env.process(self._daily_metrics_process())

        # Apply any registered shocks
        for shock in self.active_shocks:
            self.env.process(shock.apply(self))

        # Run simulation
        total_time = self.sim_days + self.warmup_days
        self.env.run(until=total_time)
        self.total_days_simulated = self.sim_days

        return self._compile_results()

    def _customer_order_process(self):
        """Generate customer orders via Poisson process.

        All orders for a given day are processed sequentially within
        the same simulation step. This time-stepped design means there
        is no yield between checking warehouse level and calling get(),
        preventing SimPy Container race conditions.
        
        Parameters
        ----------
        """
        day = 0
        total_time = self.sim_days + self.warmup_days

        while day < total_time:
            day_orders = 0
            day_fulfilled = 0
            day_cost = 0.0
            day_emission = 0.0
            day_travel_times = []

            # Each customer generates orders independently
            for c_id in range(self.n_customers):
                # Get demand multiplier from active shocks
                demand_mult = self._get_demand_multiplier(c_id)

                # Poisson number of orders per customer per day
                effective_lambda = self.lambda_orders * demand_mult
                n_orders = self.rng.poisson(effective_lambda)

                for _ in range(n_orders):
                    # Order size: LogNormal distribution
                    # With mu=5.5, sigma=0.4 -> mean ~270 kg (realistic per-order)
                    order_size = self.rng.lognormal(
                        self.des_order_size_mu, self.des_order_size_sigma
                    )

                    day_orders += 1

                    # Cascade through warehouses by distance
                    distances = self.dist_matrix[:, c_id]
                    sorted_wh_ids = np.argsort(distances)

                    for w_id in sorted_wh_ids:
                        wh = self.warehouses[int(w_id)]
                        dist_km = distances[int(w_id)]

                        # Check if warehouse can fulfill
                        if wh.level >= order_size:
                            fulfilled_qty, success = wh.fulfill(
                                order_size
                            )
                            if success:
                                day_fulfilled += 1
                                # Cost: round trip distance * cost per km
                                trip_cost = (
                                    2 * dist_km
                                    * self.config.vehicle.hcv_cost_per_km
                                )
                                day_cost += trip_cost
                                # Emission: multi-trip MEET formula (kg CO2)
                                # n_trips = ceil(load / vehicle_capacity)
                                n_trips = np.ceil(
                                    fulfilled_qty
                                    / self.config.vehicle.hcv_capacity
                                )
                                emission = (
                                    (n_trips * self.config.vehicle.hcv_k
                                     + self.config.vehicle.hcv_L
                                     * fulfilled_qty)
                                    * dist_km
                                    + self.config.vehicle.hcv_k
                                    * dist_km * n_trips
                                )
                                day_emission += emission
                                # Travel time: distance / (speed * (1 + noise))
                                noise = self.rng.uniform(
                                    -self.truck_speed_noise_pct,
                                    self.truck_speed_noise_pct,
                                )
                                effective_speed = self.truck_speed_kmh * (1 + noise)
                                travel_time_hours = dist_km / effective_speed
                                day_travel_times.append(travel_time_hours)
                                break
                    # If no warehouse could fulfill, order is a stockout

            # Record metrics only after warmup
            if day >= self.warmup_days:
                self.daily_orders.append(day_orders)
                self.daily_fulfilled.append(day_fulfilled)
                sl = (
                    day_fulfilled / day_orders
                    if day_orders > 0 else 1.0
                )
                self.daily_service_level.append(sl)
                self.daily_costs.append(day_cost)
                self.daily_emissions.append(day_emission)
                # SLA tracking: day meets threshold if service level >= target
                self.daily_sla_met.append(
                    sl >= self.service_level_threshold
                )
                # Travel time tracking: mean travel time for fulfilled orders
                self.daily_travel_times.append(
                    float(np.mean(day_travel_times))
                    if day_travel_times else 0.0
                )

            day += 1
            yield self.env.timeout(1)

    def _replenishment_process(self):
        """Daily warehouse replenishment process.

        Replenishment occurs daily at a rate of capacity * 2.4 / 7 per day.
        Daily delivery prevents inventory from draining completely between
        cycles and maintains steady-state levels against aggregate daily
        demand, yielding approximately 95% service level under no-shock
        conditions.
        
        Parameters
        ----------
        """
        while True:
            yield self.env.timeout(1)
            for wh in self.warehouses:
                # Daily replenishment = weekly rate / 7
                replenish_amount = (
                    wh.replenishment_rate / 7.0 * wh.shock_factor
                )
                space_available = wh.capacity - wh.level
                actual_replenish = min(replenish_amount, space_available)
                if actual_replenish > 0:
                    wh.container.put(actual_replenish)

    def _daily_metrics_process(self):
        """Track daily metrics (placeholder for event-driven hooks).
        Parameters
        ----------
        """
        total_time = self.sim_days + self.warmup_days
        while self.env.now < total_time:
            yield self.env.timeout(1)

    def _get_demand_multiplier(self, customer_id):
        """Get effective demand multiplier for a customer.

        Args:
            customer_id: Customer index.

        Returns:
            Float multiplier (1.0 = normal).
        
        Parameters
        ----------
        """
        multiplier = 1.0
        current_day = int(self.env.now)
        for shock in self.active_shocks:
            mult = shock.get_demand_multiplier(
                customer_id, current_day
            )
            multiplier *= mult
        return multiplier

    def _compile_results(self):
        """Compile simulation results into a dictionary.

        Returns:
            Dictionary with all tracked metrics including SLA compliance
            and travel time statistics.
        
        Parameters
        ----------
        """
        sla_compliance = (
            float(np.mean(self.daily_sla_met))
            if self.daily_sla_met else 0.0
        )

        travel_times = np.array(self.daily_travel_times)
        mean_travel_time = (
            float(np.mean(travel_times[travel_times > 0]))
            if len(travel_times) > 0 and np.any(travel_times > 0)
            else 0.0
        )

        return {
            "daily_orders": np.array(self.daily_orders),
            "daily_fulfilled": np.array(self.daily_fulfilled),
            "daily_service_level": np.array(self.daily_service_level),
            "daily_costs": np.array(self.daily_costs),
            "daily_emissions": np.array(self.daily_emissions),
            "daily_sla_met": np.array(self.daily_sla_met),
            "daily_travel_times": travel_times,
            "mean_service_level": float(
                np.mean(self.daily_service_level)
            ) if self.daily_service_level else 0.0,
            "sla_compliance_rate": sla_compliance,
            "service_level_threshold": self.service_level_threshold,
            "mean_travel_time_hours": mean_travel_time,
            "total_cost": float(np.sum(self.daily_costs)),
            "total_emissions": float(np.sum(self.daily_emissions)),
            "sim_days": self.sim_days,
            "warmup_days": self.warmup_days,
        }

    def add_shock(self, shock):
        """Register a shock to be applied during simulation.

        Parameters
        ----------
        shock : DemandShock or SupplyShock
            A shock object with ``apply(env, ...)`` and
            ``get_demand_multiplier(...)`` methods.

        Returns
        -------
        None
            The shock is appended to the active-shock list in
            place.
        """
        self.active_shocks.append(shock)
