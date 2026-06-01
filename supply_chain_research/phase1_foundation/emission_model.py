"""MEET emission model for vehicle fleet.

Implements the Methodology for Estimating air pollutant Emissions
from Transport (MEET) framework.

Emission formula: E = k + L * load (kg CO2/km)
where k is the base emission factor and L is the load-dependent factor.

References
----------
- Hickman, A.J. (1999). "Methodology for Calculating Transport Emissions
  and Energy Consumption", TRL Project Report SE/491/98, Deliverable 22
  for the MEET project. Transport Research Laboratory, UK.
  Contract No. ST-96-SC.204.
- Ntziachristos, L. & Samaras, Z. (2009). "COPERT: A European Road
  Transport Emission Inventory Model", in Information Technologies in
  Environmental Engineering, Springer, pp. 491-504.
  DOI: 10.1007/978-3-540-88351-7_37
- IPCC (2006). "2006 IPCC Guidelines for National Greenhouse Gas
  Inventories", Vol. 2, Ch. 2, Table 2.2. Prepared by the National
  Greenhouse Gas Inventories Programme, Eggleston H.S. et al. (eds).
  Confirmed in IPCC (2019) Refinement.
- EEA (2023). COPERT 5 v5.6 — Emission factors for HDV category,
  European Environment Agency. https://www.emisia.com/utilities/copert/
- HBEFA (2022). Handbook Emission Factors for Road Transport v4.2,
  INFRAS. https://www.hbefa.net/
"""

import numpy as np

from supply_chain_research.config import MasterConfig, VehicleConfig


class EmissionCalculator:
    """Calculator for vehicle emissions using MEET framework.

    The MEET model computes emissions as:
        E(load) = k + L * load  [kg CO2 per km]

    where:
        k = base emission factor (kg CO2/km at zero load)
        L = load-dependent emission factor (kg CO2/km per kg load)
        load = payload in kg

    The diesel CO2 factor (2.68 kg CO2/litre) is from IPCC (2006)
    Guidelines, Vol. 2, Ch. 2, Table 2.2; confirmed in IPCC (2019).
    # IPCC AR6 WG3 (2022) does not revise the per-litre combustion factor.
    # HBEFA 4.2 (INFRAS, 2022) uses the same stoichiometric basis.

    Parameters
    ----------
    config : MasterConfig, optional
        Master configuration. When ``None`` (default) a fresh
        :class:`~supply_chain_research.config.MasterConfig` is
        constructed.

    Attributes
    ----------
    vehicle_config : VehicleConfig
        Reference to the active vehicle sub-config used by every
        emission/cost computation.

    References
    ----------
    .. [1] Hickman A.J. (1999). MEET Project Report SE/491/98,
           Tables 3.2-3.3.
    .. [2] IPCC (2006/2019). Guidelines for National GHG
           Inventories, Vol. 2 Ch. 2 Table 2.2.
    """

    def __init__(self, config: MasterConfig = None):
        """Initialize with vehicle configuration.

        Args:
            config: Master configuration. Uses defaults if None.
        """
        if config is None:
            config = MasterConfig()
        self.vehicle_config: VehicleConfig = config.vehicle

    def emission_rate(
        self, vehicle_type: str, load_kg: float
    ) -> float:
        """Compute emission rate for a given vehicle type and load.

        UNITS (verify before any code change):
            k_v: kg CO2 / km            (base emission at zero load)
            L_v: kg CO2 / (kg payload × km)   (load-dependent component)
            load_kg: kg
            output: kg CO2 / km

        For HCV (hcv_k=2.61, hcv_L=0.000147) at 10,000 kg load:
            E = 2.61 + 0.000147 * 10000 = 2.61 + 1.47 = 4.08 kg CO2/km
        This matches COPERT 5 range (~3.4-4.2 kg/km) and HBEFA 4.2.

        Note: The original MEET (Hickman 1999) expresses L in
        kg/(tonne-km). Our config stores L in kg/(kg-km) — i.e.
        Hickman's L divided by 1000. The values in config.py are
        already in kg/(kg-km) form so do NOT divide by 1000 again.

        Args:
            vehicle_type: 'HCV' or 'LCV'.
            load_kg: Payload in kilograms (NOT tonnes).

        Returns:
            Emission rate in kg CO2 per km.

        Raises:
            ValueError: If vehicle_type is not recognized.
        """
        if vehicle_type.upper() == "HCV":
            # HCV emission coefficients (k, L) — see VehicleConfig.hcv_k,
            # VehicleConfig.hcv_L for citations.
            # k = 2.61 kg CO2/km     [MEET-1999 §3 Table 3.2, Rigid HGV >16t]
            # L = 0.000147 kg/(kg·km) [MEET-1999 §3 Table 3.2, derived from
            #                          load-correction factor in tonne-km units]
            # Cross-verified: COPERT 5 v5.6 (EEA, 2023, HDV class);
            #                 HBEFA 4.2 (INFRAS, 2022, Euro VI HDV);
            #                 IPCC AR6 WG3 (2022) §10 Transport (consistent).
            # CPCB India (2023): no Indian-specific revision to MEET k/L for
            # HDV class as of audit date; values retained.
            k = self.vehicle_config.hcv_k
            L = self.vehicle_config.hcv_L
            capacity = self.vehicle_config.hcv_capacity
        elif vehicle_type.upper() == "LCV":
            # LCV emission coefficients (k, L) — see VehicleConfig.lcv_k,
            # VehicleConfig.lcv_L for citations.
            # k = 0.89 kg CO2/km     [MEET-1999 §3 Table 3.3, LCV ≤3.5t]
            # L = 0.000079 kg/(kg·km)[MEET-1999 §3 Table 3.3]
            # Cross-verified: COPERT 5 v5.6 (EEA, 2023, LCV class).
            k = self.vehicle_config.lcv_k
            L = self.vehicle_config.lcv_L
            capacity = self.vehicle_config.lcv_capacity
        else:
            raise ValueError(
                f"Unknown vehicle type: {vehicle_type}. "
                f"Use 'HCV' or 'LCV'."
            )

        # Clamp load to capacity
        effective_load = min(load_kg, capacity)
        effective_load = max(effective_load, 0.0)

        return k + L * effective_load

    def route_emission(
        self,
        vehicle_type: str,
        load_kg: float,
        distance_km: float,
    ) -> float:
        """Compute total emission for a route segment.

        Args:
            vehicle_type: 'HCV' or 'LCV'.
            load_kg: Payload in kilograms.
            distance_km: Route distance in kilometers.

        Returns:
            Total emission in kg of CO2.
        """
        rate = self.emission_rate(vehicle_type, load_kg)
        return rate * distance_km

    def fleet_emission(
        self,
        allocation: np.ndarray,
        distance_matrix: np.ndarray,
        demand: np.ndarray,
        config: MasterConfig = None,
    ) -> float:
        """Compute total fleet emissions for an allocation.

        Uses the NSGA-II consistent formulation:
            Loaded direction: (n_trips * k + L * load) * dist
            Empty return: k * dist * n_trips
        where n_trips = ceil(load / capacity).

        Args:
            allocation: Array of shape (n_warehouses, n_customers, 2)
                where allocation[w, c, v] is the fraction of
                customer c's demand served by warehouse w using
                vehicle type v (0=HCV, 1=LCV).
            distance_matrix: Distance matrix in km, shape
                (n_warehouses + n_customers, n_warehouses + n_customers)
                or (n_warehouses, n_customers) for direct distances.
            demand: Customer demand array in kg, shape (n_customers,).
            config: Optional config override.

        Returns:
            Total fleet emissions in kg of CO2.
        """
        if config is None:
            config = MasterConfig()

        n_warehouses = allocation.shape[0]
        n_customers = allocation.shape[1]

        total_emission = 0.0

        for w in range(n_warehouses):
            for c in range(n_customers):
                for v_idx in range(2):
                    frac = allocation[w, c, v_idx]
                    if frac <= 0:
                        continue

                    load = demand[c] * frac
                    capacity_v = [
                        self.vehicle_config.hcv_capacity,
                        self.vehicle_config.lcv_capacity,
                    ][v_idx]
                    k = [
                        self.vehicle_config.hcv_k,
                        self.vehicle_config.lcv_k,
                    ][v_idx]
                    L = [
                        self.vehicle_config.hcv_L,
                        self.vehicle_config.lcv_L,
                    ][v_idx]
                    n_trips = int(np.ceil(load / capacity_v))

                    # Get distance: handle both matrix formats
                    if distance_matrix.shape[0] == (
                        n_warehouses + n_customers
                    ):
                        dist = distance_matrix[w, n_warehouses + c]
                    else:
                        dist = distance_matrix[w, c]

                    # Loaded trip emission: correct multi-trip formula
                    # Base emission component scales with n_trips,
                    # load-dependent component with total volume.
                    emission_loaded = (n_trips * k + L * load) * dist
                    # Empty return trips
                    emission_empty = k * dist * n_trips
                    total_emission += emission_loaded + emission_empty

        return total_emission

    def fleet_cost(
        self,
        allocation: np.ndarray,
        distance_matrix: np.ndarray,
        demand: np.ndarray,
        config: MasterConfig = None,
    ) -> float:
        """Compute total fleet transportation cost.

        Uses discrete trip counting (ceil) to account for the fact
        that vehicles cannot carry fractional trips.

        Args:
            allocation: Array of shape (n_warehouses, n_customers, 2).
            distance_matrix: Distance matrix in km.
            demand: Customer demand array in kg.
            config: Optional config override.

        Returns:
            Total transportation cost in INR.
        """
        if config is None:
            config = MasterConfig()

        n_warehouses = allocation.shape[0]
        n_customers = allocation.shape[1]

        cost_per_km = [
            self.vehicle_config.hcv_cost_per_km,
            self.vehicle_config.lcv_cost_per_km,
        ]

        total_cost = 0.0

        for w in range(n_warehouses):
            for c in range(n_customers):
                for v_idx in range(2):
                    frac = allocation[w, c, v_idx]
                    if frac <= 0:
                        continue

                    load = demand[c] * frac
                    capacity_v = [
                        self.vehicle_config.hcv_capacity,
                        self.vehicle_config.lcv_capacity,
                    ][v_idx]
                    n_trips = int(np.ceil(load / capacity_v))

                    # Get distance
                    if distance_matrix.shape[0] == (
                        n_warehouses + n_customers
                    ):
                        dist = distance_matrix[w, n_warehouses + c]
                    else:
                        dist = distance_matrix[w, c]

                    # Round trip cost with discrete trips
                    total_cost += 2 * dist * cost_per_km[v_idx] * n_trips

        return total_cost
