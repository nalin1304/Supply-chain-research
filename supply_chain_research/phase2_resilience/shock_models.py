"""Shock injection models for resilience testing.

Implements supply and demand shocks that can be injected into
the DES environment to test system resilience.

Default values for ``severity``, ``multiplier``, ``duration_range``,
DBSCAN parameters, and the post-warmup random-start offset are
sourced from ``MasterConfig.shock`` (see clause 1.10). Per-call
overrides are still accepted; passing ``None`` means "use the
config default".
"""

import numpy as np

from supply_chain_research.config import CFG


class SupplyShock:
    """Supply-side shock: capacity reduction at a warehouse.

    Models disruption events such as natural disasters, strikes,
    or equipment failures that reduce warehouse capacity.

    Attributes:
        warehouse_id: Target warehouse (None = random selection).
        severity: Capacity reduction factor (0.5 = 50% reduction).
        duration_days: How long the shock lasts.
        start_day: Day the shock begins (after warmup).
    
    Parameters
    ----------
    """

    def __init__(
        self,
        warehouse_id=None,
        severity=0.5,
        duration_range=(14, 60),
        start_day=None,
        seed=42,
        config=None,
    ):
        """Initialize supply shock.

        The literal defaults (``severity=0.5``, ``duration_range=(14, 60)``)
        mirror :pyattr:`ShockConfig.supply_severity`,
        :pyattr:`ShockConfig.duration_min_days`, and
        :pyattr:`ShockConfig.duration_max_days` so that
        ``inspect.signature`` matches the C3.12 baseline. Passing
        ``None`` explicitly is still accepted and routes through the
        config fallback below.

        Args:
            warehouse_id: Target warehouse index. If None, randomly
                selected during apply().
            severity: Fraction of capacity remaining (0.5 = 50%
                reduction). Default ``0.5`` mirrors
                ``ShockConfig.supply_severity``; ``None`` is also
                accepted and routes through the config fallback.
            duration_range: Tuple (min_days, max_days) for shock
                duration. Default ``(14, 60)`` mirrors
                ``(ShockConfig.duration_min_days,
                ShockConfig.duration_max_days)``; ``None`` is also
                accepted and routes through the config fallback.
            start_day: Day to inject shock. If None, randomly chosen
                after warmup.
            seed: Random seed for reproducibility.
            config: Optional MasterConfig override; defaults to the
                module-level singleton ``CFG``.
        
        Parameters
        ----------
        """
        cfg = config if config is not None else CFG
        if severity is None:
            severity = cfg.shock.supply_severity
        if duration_range is None:
            duration_range = (
                cfg.shock.duration_min_days,
                cfg.shock.duration_max_days,
            )

        self._cfg = cfg
        self.warehouse_id = warehouse_id
        self.severity = severity
        self.duration_range = duration_range
        self.start_day = start_day
        self.rng = np.random.default_rng(seed)
        self._actual_start = None
        self._actual_end = None
        self._actual_warehouse = None
        self._duration = None

    def apply(self, des_env):
        """SimPy process to apply shock during simulation.

        Parameters
        ----------
        des_env : DESEnvironment
            The active DES environment whose warehouse / demand
            state will be perturbed.

        Yields
        ------
        simpy.events.Timeout
            Timeout events scheduled by the SimPy process loop.

        Returns
        -------
        None
            The shock side-effects ``des_env`` and yields control
            back to SimPy until the duration window expires.
        """
        warmup = des_env.warmup_days

        # Determine start day
        if self.start_day is not None:
            actual_start = self.start_day + warmup
        else:
            offset = self._cfg.shock.random_start_min_offset_days
            max_start = warmup + des_env.sim_days // 2
            if max_start <= warmup + offset:
                actual_start = warmup + offset
            else:
                actual_start = int(
                    self.rng.integers(warmup + offset, max_start)
                )

        # Determine duration
        self._duration = int(
            self.rng.integers(
                self.duration_range[0], self.duration_range[1] + 1
            )
        )

        # Determine target warehouse
        if self.warehouse_id is not None:
            target_wh = self.warehouse_id
        else:
            target_wh = int(
                self.rng.integers(0, des_env.n_warehouses)
            )

        self._actual_start = actual_start - warmup
        self._actual_end = self._actual_start + self._duration
        self._actual_warehouse = target_wh

        # Wait until shock start
        yield des_env.env.timeout(actual_start)

        # Apply shock: reduce warehouse capacity factor
        des_env.warehouses[target_wh].shock_factor = self.severity

        # Drain inventory above new effective capacity per spec
        wh = des_env.warehouses[target_wh]
        effective_capacity = wh.capacity * self.severity
        if wh.level > effective_capacity:
            excess = wh.level - effective_capacity
            yield wh.container.get(excess)

        # Wait for shock duration
        yield des_env.env.timeout(self._duration)

        # Restore normal operations
        des_env.warehouses[target_wh].shock_factor = 1.0

    def get_demand_multiplier(self, customer_id, current_day):
        """Supply shocks do not affect demand.

        Args:
            customer_id: Customer index.
            current_day: Current simulation day.

        Returns:
            Always 1.0 (no demand effect).
        
        Parameters
        ----------
        """
        return 1.0

    @property
    def shock_start(self):
        """Actual shock start day (relative to post-warmup).
        Parameters
        ----------
        """
        return self._actual_start

    @property
    def shock_end(self):
        """Actual shock end day (relative to post-warmup).
        Parameters
        ----------
        """
        return self._actual_end

    @property
    def duration(self):
        """Actual shock duration in days.
        Parameters
        ----------
        """
        return self._duration


class DemandShock:
    """Demand-side shock: multiplied demand on clustered customers.

    Models surge events such as seasonal demand spikes, panic
    buying, or promotional events affecting customer clusters.

    Per specification, affected customers are identified via DBSCAN
    spatial clustering (eps=1.5 degrees). When customer_locations are
    not provided, falls back to sequential index selection as an
    approximation.

    Attributes:
        customer_ids: Set of affected customer indices.
        multiplier: Demand multiplication factor (3.0 = 3x demand).
        duration_days: How long the shock lasts.
        start_day: Day the shock begins (after warmup).
    
    Parameters
    ----------
    """

    def __init__(
        self,
        customer_ids=None,
        multiplier=3.0,
        duration_range=(14, 60),
        start_day=None,
        n_affected=None,
        customer_locations=None,
        seed=42,
        config=None,
    ):
        """Initialize demand shock.

        The literal defaults (``multiplier=3.0``,
        ``duration_range=(14, 60)``) mirror
        :pyattr:`ShockConfig.demand_multiplier` and the duration bounds
        so that ``inspect.signature`` matches the C3.12 baseline.
        Passing ``None`` explicitly is still accepted and routes
        through the config fallback below.

        Args:
            customer_ids: List of affected customer indices. If None,
                selects a cluster using DBSCAN (if customer_locations
                provided) or sequential fallback.
            multiplier: Demand multiplication factor. Default ``3.0``
                mirrors ``ShockConfig.demand_multiplier``; ``None`` is
                also accepted and routes through the config fallback.
            duration_range: Tuple (min_days, max_days). Default
                ``(14, 60)`` mirrors
                ``(ShockConfig.duration_min_days,
                ShockConfig.duration_max_days)``; ``None`` is also
                accepted and routes through the config fallback.
            start_day: Day to inject shock (post-warmup). If None,
                randomly chosen.
            n_affected: Number of customers affected if customer_ids
                is None. Defaults to
                ``config.shock.sequential_default_fraction`` of total.
            customer_locations: Array of shape (n_customers, 2) with
                (lat, lon) coordinates. When provided, DBSCAN
                clustering is used to identify a spatially coherent
                cluster of affected customers (eps and min_samples
                from ``config.shock``).
            seed: Random seed for reproducibility.
            config: Optional MasterConfig override; defaults to the
                module-level singleton ``CFG``.
        
        Parameters
        ----------
        """
        cfg = config if config is not None else CFG
        if multiplier is None:
            multiplier = cfg.shock.demand_multiplier
        if duration_range is None:
            duration_range = (
                cfg.shock.duration_min_days,
                cfg.shock.duration_max_days,
            )

        self._cfg = cfg
        self.customer_ids = customer_ids
        self.multiplier = multiplier
        self.duration_range = duration_range
        self.start_day = start_day
        self.n_affected = n_affected
        self.customer_locations = customer_locations
        self.rng = np.random.default_rng(seed)
        self._actual_start = None
        self._actual_end = None
        self._affected_customers = None
        self._duration = None
        self._active = False

    @classmethod
    def from_dbscan_cluster(
        cls,
        customer_locations,
        multiplier=3.0,
        duration_range=(14, 60),
        start_day=None,
        eps=1.5,
        min_samples=3,
        seed=42,
        config=None,
    ):
        """Create a DemandShock targeting a DBSCAN-identified cluster.

        Uses ``sklearn.cluster.DBSCAN`` to identify spatially coherent
        customer clusters, then selects one cluster at random as the
        affected group. Default ``eps`` and ``min_samples`` mirror
        :pyattr:`ShockConfig.dbscan_eps_degrees` and
        :pyattr:`ShockConfig.dbscan_min_samples` so that
        ``inspect.signature`` matches the C3.12 baseline. Passing
        ``None`` for any of ``multiplier``, ``duration_range``,
        ``eps`` or ``min_samples`` is still accepted and routes
        through the corresponding config fallback inside the
        ``DemandShock`` ``__init__`` / ``_select_cluster_dbscan``
        helpers.

        Args:
            customer_locations: Array of shape (n_customers, 2) with
                (lat, lon) coordinates.
            multiplier: Demand multiplication factor. Default ``3.0``
                mirrors ``ShockConfig.demand_multiplier``.
            duration_range: Tuple (min_days, max_days). Default
                ``(14, 60)`` mirrors the ``ShockConfig.duration_*`` bounds.
            start_day: Day to inject shock (post-warmup).
            eps: DBSCAN epsilon in degrees. Default ``1.5`` mirrors
                ``ShockConfig.dbscan_eps_degrees``.
            min_samples: DBSCAN minimum samples. Default ``3`` mirrors
                ``ShockConfig.dbscan_min_samples``.
            seed: Random seed.
            config: Optional MasterConfig override.

        Returns:
            DemandShock instance with customer_locations set for
            DBSCAN-based cluster selection during apply().
        
        Parameters
        ----------
        """
        cfg = config if config is not None else CFG
        # Honour explicit overrides for ``eps`` / ``min_samples`` by
        # routing them through a one-shot copy of ``cfg.shock`` so the
        # downstream clustering helper picks them up. ``None`` is
        # treated as "use the cfg default" for backward compatibility.
        if eps is not None or min_samples is not None:
            cfg = cfg.model_copy(deep=True)
            if eps is not None:
                cfg.shock.dbscan_eps_degrees = float(eps)
            if min_samples is not None:
                cfg.shock.dbscan_min_samples = int(min_samples)
        return cls(
            customer_ids=None,
            multiplier=multiplier,
            duration_range=duration_range,
            start_day=start_day,
            n_affected=None,
            customer_locations=np.asarray(customer_locations),
            seed=seed,
            config=cfg,
        )

    def _select_cluster_dbscan(self, n_customers):
        """Select affected customers using DBSCAN spatial clustering.

        DBSCAN ``eps`` and ``min_samples`` are sourced from
        ``MasterConfig.shock`` (defaults preserve original
        ``eps=1.5``, ``min_samples=3`` behavior).

        Args:
            n_customers: Total number of customers.

        Returns:
            Set of affected customer indices.
        
        Parameters
        ----------
        """
        from sklearn.cluster import DBSCAN

        locations = np.asarray(self.customer_locations)
        clustering = DBSCAN(
            eps=self._cfg.shock.dbscan_eps_degrees,
            min_samples=self._cfg.shock.dbscan_min_samples,
        ).fit(locations)
        labels = clustering.labels_

        # Find all valid clusters (label != -1)
        unique_labels = set(labels)
        unique_labels.discard(-1)

        if not unique_labels:
            # No clusters found, fall back to sequential selection
            return self._select_sequential(n_customers)

        # Select a random cluster
        selected_label = int(self.rng.choice(list(unique_labels)))
        cluster_indices = set(
            int(i) for i, lbl in enumerate(labels)
            if lbl == selected_label
        )
        return cluster_indices

    def _select_sequential(self, n_customers):
        """Select a sequential block of customers (fallback).

        ``n_affected`` defaults to
        ``config.shock.sequential_default_fraction`` (20%) of total
        customers when not explicitly specified.

        Args:
            n_customers: Total number of customers.

        Returns:
            Set of affected customer indices.
        
        Parameters
        ----------
        """
        # Preserve original `n_affected or default` semantics:
        # falsy n_affected (None, 0) falls through to the default.
        if self.n_affected:
            n_affected = self.n_affected
        else:
            n_affected = max(
                1,
                int(n_customers * self._cfg.shock.sequential_default_fraction),
            )
        start_idx = int(
            self.rng.integers(0, n_customers - n_affected + 1)
        )
        return set(range(start_idx, start_idx + n_affected))

    def apply(self, des_env):
        """SimPy process to apply demand shock.

        Parameters
        ----------
        des_env : DESEnvironment
            The active DES environment whose customer demand will
            be temporarily multiplied for the affected cluster.

        Yields
        ------
        simpy.events.Timeout
            Timeout events scheduled by the SimPy process loop.

        Returns
        -------
        None
            The shock side-effects ``des_env`` until the duration
            window expires.
        """
        warmup = des_env.warmup_days

        # Determine affected customers
        if self.customer_ids is not None:
            self._affected_customers = set(self.customer_ids)
        elif self.customer_locations is not None:
            self._affected_customers = self._select_cluster_dbscan(
                des_env.n_customers
            )
        else:
            self._affected_customers = self._select_sequential(
                des_env.n_customers
            )

        # Determine start day
        if self.start_day is not None:
            actual_start = self.start_day + warmup
        else:
            offset = self._cfg.shock.random_start_min_offset_days
            max_start = warmup + des_env.sim_days // 2
            if max_start <= warmup + offset:
                actual_start = warmup + offset
            else:
                actual_start = int(
                    self.rng.integers(warmup + offset, max_start)
                )

        # Determine duration
        self._duration = int(
            self.rng.integers(
                self.duration_range[0], self.duration_range[1] + 1
            )
        )

        self._actual_start = actual_start - warmup
        self._actual_end = self._actual_start + self._duration

        # Wait until shock start
        yield des_env.env.timeout(actual_start)
        self._active = True

        # Wait for shock duration
        yield des_env.env.timeout(self._duration)
        self._active = False

    def get_demand_multiplier(self, customer_id, current_day):
        """Get demand multiplier for a customer at current time.

        Args:
            customer_id: Customer index.
            current_day: Current simulation day (absolute, including
                warmup).

        Returns:
            Multiplier float (1.0 if not affected or not active).
        
        Parameters
        ----------
        """
        if not self._active:
            return 1.0
        if self._affected_customers is None:
            return 1.0
        if customer_id in self._affected_customers:
            return self.multiplier
        return 1.0

    @property
    def shock_start(self):
        """Actual shock start day (relative to post-warmup).
        Parameters
        ----------
        """
        return self._actual_start

    @property
    def shock_end(self):
        """Actual shock end day (relative to post-warmup).
        Parameters
        ----------
        """
        return self._actual_end

    @property
    def duration(self):
        """Actual shock duration in days.
        Parameters
        ----------
        """
        return self._duration


class Cyberattack:
    """Cyberattack shock model: IT system outage, Weibull recovery.

    Simulates a targeted or system-wide cyberattack that halts operations
    at target warehouses during detection_time, followed by a gradual
    Weibull-modeled recovery phase.
    
    Parameters
    ----------
    
            Parameters
            ----------
            warehouse_ids : type
                Description of warehouse_ids.
            severity : type
                Description of severity.
            detection_time : type
                Description of detection_time.
            recovery_time : type
                Description of recovery_time.
            start_day : type
                Description of start_day.
            seed : type
                Description of seed.
            config : type
                Description of config.
        """

    def __init__(
        self,
        warehouse_ids=None,
        severity=0.8,
        detection_time=5,
        recovery_time=15,
        start_day=None,
        seed=42,
        config=None,
    ):
        """
        Parameters
        ----------
        """
        cfg = config if config is not None else CFG
        self._cfg = cfg
        self.warehouse_ids = warehouse_ids
        self.severity = severity
        self.detection_time = detection_time
        self.recovery_time = recovery_time
        self.start_day = start_day
        self.rng = np.random.default_rng(seed)
        self._actual_start = None
        self._actual_end = None
        self._duration = detection_time + recovery_time
        self._target_warehouses = None
        self._active = False

    def apply(self, des_env):
        """
        Parameters
        ----------
        """
        warmup = des_env.warmup_days
        if self.start_day is not None:
            actual_start = self.start_day + warmup
        else:
            offset = self._cfg.shock.random_start_min_offset_days
            max_start = warmup + des_env.sim_days // 2
            if max_start <= warmup + offset:
                actual_start = warmup + offset
            else:
                actual_start = int(self.rng.integers(warmup + offset, max_start))

        self._actual_start = actual_start - warmup
        self._actual_end = self._actual_start + self._duration

        if self.warehouse_ids is not None:
            self._target_warehouses = self.warehouse_ids
        else:
            n_wh = des_env.n_warehouses
            self._target_warehouses = list(self.rng.choice(range(n_wh), size=max(1, n_wh // 2), replace=False))

        yield des_env.env.timeout(actual_start)
        self._active = True

        # Stage 1: Detection Time (Total Outage: capacity shock factor is zero)
        for w_id in self._target_warehouses:
            des_env.warehouses[w_id].shock_factor = 0.0

        yield des_env.env.timeout(self.detection_time)

        # Stage 2: Recovery Time (Weibull recovery CDF)
        for t in range(self.recovery_time):
            scale = self.recovery_time / 2.0
            shape = 2.0
            factor = 1.0 - np.exp(-((t + 1) / scale) ** shape)
            current_factor = 1.0 - (1.0 - factor) * self.severity
            for w_id in self._target_warehouses:
                des_env.warehouses[w_id].shock_factor = float(current_factor)
            yield des_env.env.timeout(1)

        # Restore completely
        for w_id in self._target_warehouses:
            des_env.warehouses[w_id].shock_factor = 1.0
        self._active = False

    def get_demand_multiplier(self, customer_id, current_day):
        """
        Parameters
        ----------
        """
        return 1.0

    @property
    def shock_start(self):
        """
        Parameters
        ----------
        """
        return self._actual_start

    @property
    def shock_end(self):
        """
        Parameters
        ----------
        """
        return self._actual_end

    @property
    def duration(self):
        """
        Parameters
        ----------
        """
        return self._duration


class LaborStrike:
    """LaborStrike shock model: gradual capacity reduction.

    Simulates labor strike that scales down warehouse capacity gradually
    in first 3 days, followed by a flat strike period and negotiation recovery.
    
    Parameters
    ----------
    
            Parameters
            ----------
            warehouse_ids : type
                Description of warehouse_ids.
            severity : type
                Description of severity.
            strike_prob : type
                Description of strike_prob.
            duration_range : type
                Description of duration_range.
            negotiation_rate : type
                Description of negotiation_rate.
            start_day : type
                Description of start_day.
            seed : type
                Description of seed.
            config : type
                Description of config.
        """

    def __init__(
        self,
        warehouse_ids=None,
        severity=0.7,
        strike_prob=0.05,
        duration_range=(10, 30),
        negotiation_rate=0.1,
        start_day=None,
        seed=42,
        config=None,
    ):
        """
        Parameters
        ----------
        """
        cfg = config if config is not None else CFG
        self._cfg = cfg
        self.warehouse_ids = warehouse_ids
        self.severity = severity
        self.strike_prob = strike_prob
        self.duration_range = duration_range
        self.negotiation_rate = negotiation_rate
        self.start_day = start_day
        self.rng = np.random.default_rng(seed)
        self._actual_start = None
        self._actual_end = None
        self._duration = None
        self._target_warehouses = None
        self._active = False

    def apply(self, des_env):
        """
        Parameters
        ----------
        """
        warmup = des_env.warmup_days
        if self.start_day is not None:
            actual_start = self.start_day + warmup
        else:
            offset = self._cfg.shock.random_start_min_offset_days
            max_start = warmup + des_env.sim_days // 2
            if max_start <= warmup + offset:
                actual_start = warmup + offset
            else:
                actual_start = int(self.rng.integers(warmup + offset, max_start))

        self._duration = int(self.rng.integers(self.duration_range[0], self.duration_range[1] + 1))
        self._actual_start = actual_start - warmup
        self._actual_end = self._actual_start + self._duration

        if self.warehouse_ids is not None:
            self._target_warehouses = self.warehouse_ids
        else:
            n_wh = des_env.n_warehouses
            self._target_warehouses = list(self.rng.choice(range(n_wh), size=max(1, n_wh // 2), replace=False))

        yield des_env.env.timeout(actual_start)
        self._active = True

        for day in range(self._duration):
            if day < 3:
                # Gradual drop
                factor = 1.0 - (day + 1) / 3.0 * self.severity
            elif day >= self._duration - 5:
                # Negotiation resolution recovery in last 5 days
                resolved_day = day - (self._duration - 5) + 1
                factor = (1.0 - self.severity) + resolved_day / 5.0 * self.severity
            else:
                factor = 1.0 - self.severity

            for w_id in self._target_warehouses:
                des_env.warehouses[w_id].shock_factor = float(factor)
            yield des_env.env.timeout(1)

        for w_id in self._target_warehouses:
            des_env.warehouses[w_id].shock_factor = 1.0
        self._active = False

    def get_demand_multiplier(self, customer_id, current_day):
        """
        Parameters
        ----------
        """
        return 1.0

    @property
    def shock_start(self):
        """
        Parameters
        ----------
        """
        return self._actual_start

    @property
    def shock_end(self):
        """
        Parameters
        ----------
        """
        return self._actual_end

    @property
    def duration(self):
        """
        Parameters
        ----------
        """
        return self._duration


class RawMaterialShortage:
    """RawMaterialShortage shock model: supply constraint + price spike.

    Reduces replenishment rates of all warehouses and spikes shipping cost
    by price_multiplier during shortage. Shortage severity is halved if substitute is available.
    
    Parameters
    ----------
    
            Parameters
            ----------
            shortage_severity : type
                Description of shortage_severity.
            price_multiplier : type
                Description of price_multiplier.
            substitute_available : type
                Description of substitute_available.
            duration_range : type
                Description of duration_range.
            start_day : type
                Description of start_day.
            seed : type
                Description of seed.
            config : type
                Description of config.
        """

    def __init__(
        self,
        shortage_severity=0.6,
        price_multiplier=1.5,
        substitute_available=False,
        duration_range=(14, 45),
        start_day=None,
        seed=42,
        config=None,
    ):
        """
        Parameters
        ----------
        """
        cfg = config if config is not None else CFG
        self._cfg = cfg
        self.shortage_severity = shortage_severity
        self.price_multiplier = price_multiplier
        self.substitute_available = substitute_available
        self.duration_range = duration_range
        self.start_day = start_day
        self.rng = np.random.default_rng(seed)
        self._actual_start = None
        self._actual_end = None
        self._duration = None
        self._active = False

    def apply(self, des_env):
        """
        Parameters
        ----------
        """
        warmup = des_env.warmup_days
        if self.start_day is not None:
            actual_start = self.start_day + warmup
        else:
            offset = self._cfg.shock.random_start_min_offset_days
            max_start = warmup + des_env.sim_days // 2
            if max_start <= warmup + offset:
                actual_start = warmup + offset
            else:
                actual_start = int(self.rng.integers(warmup + offset, max_start))

        self._duration = int(self.rng.integers(self.duration_range[0], self.duration_range[1] + 1))
        self._actual_start = actual_start - warmup
        self._actual_end = self._actual_start + self._duration

        yield des_env.env.timeout(actual_start)
        self._active = True

        orig_cost = des_env.config.vehicle.hcv_cost_per_km
        des_env.config.vehicle.hcv_cost_per_km = orig_cost * self.price_multiplier

        effective_severity = self.shortage_severity * 0.5 if self.substitute_available else self.shortage_severity

        for day in range(self._duration):
            for wh in des_env.warehouses:
                wh.shock_factor = 1.0 - effective_severity
            yield des_env.env.timeout(1)

        des_env.config.vehicle.hcv_cost_per_km = orig_cost
        for wh in des_env.warehouses:
            wh.shock_factor = 1.0
        self._active = False

    def get_demand_multiplier(self, customer_id, current_day):
        """
        Parameters
        ----------
        """
        return 1.0

    @property
    def shock_start(self):
        """
        Parameters
        ----------
        """
        return self._actual_start

    @property
    def shock_end(self):
        """
        Parameters
        ----------
        """
        return self._actual_end

    @property
    def duration(self):
        """
        Parameters
        ----------
        """
        return self._duration


class TransportInfrastructure:
    """TransportInfrastructure shock model: link failures, detours.

    Spikes distance matrix by detour_factor to simulate infrastructure closures/reroutes,
    leading to longer travel times, higher costs, and increased emissions.
    
    Parameters
    ----------
    
            Parameters
            ----------
            link_failure_prob : type
                Description of link_failure_prob.
            detour_factor : type
                Description of detour_factor.
            repair_time : type
                Description of repair_time.
            start_day : type
                Description of start_day.
            seed : type
                Description of seed.
            config : type
                Description of config.
        """

    def __init__(
        self,
        link_failure_prob=0.1,
        detour_factor=1.3,
        repair_time=14,
        start_day=None,
        seed=42,
        config=None,
    ):
        """
        Parameters
        ----------
        """
        cfg = config if config is not None else CFG
        self._cfg = cfg
        self.link_failure_prob = link_failure_prob
        self.detour_factor = detour_factor
        self.repair_time = repair_time
        self.start_day = start_day
        self.rng = np.random.default_rng(seed)
        self._actual_start = None
        self._actual_end = None
        self._duration = repair_time
        self._active = False

    def apply(self, des_env):
        """
        Parameters
        ----------
        """
        warmup = des_env.warmup_days
        if self.start_day is not None:
            actual_start = self.start_day + warmup
        else:
            offset = self._cfg.shock.random_start_min_offset_days
            max_start = warmup + des_env.sim_days // 2
            if max_start <= warmup + offset:
                actual_start = warmup + offset
            else:
                actual_start = int(self.rng.integers(warmup + offset, max_start))

        self._actual_start = actual_start - warmup
        self._actual_end = self._actual_start + self._duration

        yield des_env.env.timeout(actual_start)
        self._active = True

        orig_matrix = des_env.dist_matrix.copy()
        des_env.dist_matrix = orig_matrix * self.detour_factor

        yield des_env.env.timeout(self.repair_time)

        des_env.dist_matrix = orig_matrix
        self._active = False

    def get_demand_multiplier(self, customer_id, current_day):
        """
        Parameters
        ----------
        """
        return 1.0

    @property
    def shock_start(self):
        """
        Parameters
        ----------
        """
        return self._actual_start

    @property
    def shock_end(self):
        """
        Parameters
        ----------
        """
        return self._actual_end

    @property
    def duration(self):
        """
        Parameters
        ----------
        """
        return self._duration


class RegulatoryChange:
    """RegulatoryChange shock model: compliance capacity impact and daily compliance costs.

    Simulates regulatory adjustments by charging a daily compliance_cost and,
    after implementation_lead_time, lowering vehicle cargo carrying capacities by 10%.
    
    Parameters
    ----------
    
            Parameters
            ----------
            compliance_cost : type
                Description of compliance_cost.
            implementation_lead_time : type
                Description of implementation_lead_time.
            duration_range : type
                Description of duration_range.
            start_day : type
                Description of start_day.
            seed : type
                Description of seed.
            config : type
                Description of config.
        """

    def __init__(
        self,
        compliance_cost=5000.0,
        implementation_lead_time=5,
        duration_range=(15, 30),
        start_day=None,
        seed=42,
        config=None,
    ):
        """
        Parameters
        ----------
        """
        cfg = config if config is not None else CFG
        self._cfg = cfg
        self.compliance_cost = compliance_cost
        self.implementation_lead_time = implementation_lead_time
        self.duration_range = duration_range
        self.start_day = start_day
        self.rng = np.random.default_rng(seed)
        self._actual_start = None
        self._actual_end = None
        self._duration = None
        self._active = False

    def apply(self, des_env):
        """
        Parameters
        ----------
        """
        warmup = des_env.warmup_days
        if self.start_day is not None:
            actual_start = self.start_day + warmup
        else:
            offset = self._cfg.shock.random_start_min_offset_days
            max_start = warmup + des_env.sim_days // 2
            if max_start <= warmup + offset:
                actual_start = warmup + offset
            else:
                actual_start = int(self.rng.integers(warmup + offset, max_start))

        self._duration = int(self.rng.integers(self.duration_range[0], self.duration_range[1] + 1))
        self._actual_start = actual_start - warmup
        self._actual_end = self._actual_start + self._duration

        yield des_env.env.timeout(actual_start)
        self._active = True

        orig_capacity = des_env.config.vehicle.hcv_capacity

        for day in range(self._duration):
            current_idx = int(des_env.env.now) - warmup - 1
            if 0 <= current_idx < len(des_env.daily_costs):
                des_env.daily_costs[current_idx] += self.compliance_cost

            if day >= self.implementation_lead_time:
                des_env.config.vehicle.hcv_capacity = orig_capacity * 0.9

            yield des_env.env.timeout(1)

        des_env.config.vehicle.hcv_capacity = orig_capacity
        self._active = False

    def get_demand_multiplier(self, customer_id, current_day):
        """
        Parameters
        ----------
        """
        return 1.0

    @property
    def shock_start(self):
        """
        Parameters
        ----------
        """
        return self._actual_start

    @property
    def shock_end(self):
        """
        Parameters
        ----------
        """
        return self._actual_end

    @property
    def duration(self):
        """
        Parameters
        ----------
        """
        return self._duration


class PowerOutage:
    """PowerOutage shock model: cold chain impact.

    Simulates regional electricity outages. Warehouses without backup power (backup_power_prob)
    suffer inventory spoilage (spoilage_rate fraction drained daily) and operational capacity degradation (0.2).
    
    Parameters
    ----------
    
            Parameters
            ----------
            outage_duration : type
                Description of outage_duration.
            spoilage_rate : type
                Description of spoilage_rate.
            backup_power_prob : type
                Description of backup_power_prob.
            start_day : type
                Description of start_day.
            seed : type
                Description of seed.
            config : type
                Description of config.
        """

    def __init__(
        self,
        outage_duration=3,
        spoilage_rate=0.15,
        backup_power_prob=0.3,
        start_day=None,
        seed=42,
        config=None,
    ):
        """
        Parameters
        ----------
        """
        cfg = config if config is not None else CFG
        self._cfg = cfg
        self.outage_duration = outage_duration
        self.spoilage_rate = spoilage_rate
        self.backup_power_prob = backup_power_prob
        self.start_day = start_day
        self.rng = np.random.default_rng(seed)
        self._actual_start = None
        self._actual_end = None
        self._duration = outage_duration
        self._active = False

    def apply(self, des_env):
        """
        Parameters
        ----------
        """
        warmup = des_env.warmup_days
        if self.start_day is not None:
            actual_start = self.start_day + warmup
        else:
            offset = self._cfg.shock.random_start_min_offset_days
            max_start = warmup + des_env.sim_days // 2
            if max_start <= warmup + offset:
                actual_start = warmup + offset
            else:
                actual_start = int(self.rng.integers(warmup + offset, max_start))

        self._actual_start = actual_start - warmup
        self._actual_end = self._actual_start + self._duration

        yield des_env.env.timeout(actual_start)
        self._active = True

        affected = []
        for wh in des_env.warehouses:
            if self.rng.random() >= self.backup_power_prob:
                affected.append(wh.warehouse_id)

        for day in range(self.outage_duration):
            for w_id in affected:
                wh = des_env.warehouses[w_id]
                wh.shock_factor = 0.2
                lvl = wh.level
                if lvl > 0:
                    spoil = lvl * self.spoilage_rate
                    if spoil > 1e-3:
                        yield wh.container.get(spoil)
            yield des_env.env.timeout(1)

        for wh in des_env.warehouses:
            wh.shock_factor = 1.0
        self._active = False

    def get_demand_multiplier(self, customer_id, current_day):
        """
        Parameters
        ----------
        """
        return 1.0

    @property
    def shock_start(self):
        """
        Parameters
        ----------
        """
        return self._actual_start

    @property
    def shock_end(self):
        """
        Parameters
        ----------
        """
        return self._actual_end

    @property
    def duration(self):
        """
        Parameters
        ----------
        """
        return self._duration
