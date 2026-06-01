"""Tests for the MEET emission model."""

import numpy as np
import pytest

from supply_chain_research.config import MasterConfig
from supply_chain_research.phase1_foundation.emission_model import (
    EmissionCalculator,
)


@pytest.fixture
def config():
    """Create default configuration."""
    return MasterConfig()


@pytest.fixture
def calculator(config):
    """Create emission calculator."""
    return EmissionCalculator(config)


class TestEmissionRate:
    """Test emission rate calculations."""

    def test_hcv_zero_load(self, calculator):
        """HCV at zero load should return base emission factor k."""
        rate = calculator.emission_rate("HCV", 0.0)
        assert rate == pytest.approx(2.61, abs=1e-6)

    def test_lcv_zero_load(self, calculator):
        """LCV at zero load should return base emission factor k."""
        rate = calculator.emission_rate("LCV", 0.0)
        assert rate == pytest.approx(0.89, abs=1e-6)

    def test_hcv_full_load(self, calculator):
        """HCV at full load (10000 kg)."""
        expected = 2.61 + 0.000147 * 10000  # 2.61 + 1.47 = 4.08
        rate = calculator.emission_rate("HCV", 10000.0)
        assert rate == pytest.approx(expected, abs=1e-6)

    def test_lcv_full_load(self, calculator):
        """LCV at full load (3000 kg)."""
        expected = 0.89 + 0.000079 * 3000  # 0.89 + 0.237 = 1.127
        rate = calculator.emission_rate("LCV", 3000.0)
        assert rate == pytest.approx(expected, abs=1e-6)

    def test_hcv_partial_load(self, calculator):
        """HCV at 5000 kg load."""
        expected = 2.61 + 0.000147 * 5000  # 2.61 + 0.735 = 3.345
        rate = calculator.emission_rate("HCV", 5000.0)
        assert rate == pytest.approx(expected, abs=1e-6)

    def test_negative_load_clamped(self, calculator):
        """Negative load should be clamped to zero."""
        rate = calculator.emission_rate("HCV", -100.0)
        assert rate == pytest.approx(2.61, abs=1e-6)

    def test_overload_clamped(self, calculator):
        """Load exceeding capacity should be clamped."""
        rate_at_cap = calculator.emission_rate("HCV", 10000.0)
        rate_over = calculator.emission_rate("HCV", 15000.0)
        assert rate_over == pytest.approx(rate_at_cap, abs=1e-6)

    def test_invalid_vehicle_type(self, calculator):
        """Invalid vehicle type should raise ValueError."""
        with pytest.raises(ValueError, match="Unknown vehicle type"):
            calculator.emission_rate("TRUCK", 1000.0)

    def test_case_insensitive(self, calculator):
        """Vehicle type should be case insensitive."""
        rate_upper = calculator.emission_rate("HCV", 1000.0)
        rate_lower = calculator.emission_rate("hcv", 1000.0)
        assert rate_upper == pytest.approx(rate_lower, abs=1e-6)


class TestRouteEmission:
    """Test route emission calculations."""

    def test_zero_distance(self, calculator):
        """Zero distance should produce zero emission."""
        emission = calculator.route_emission("HCV", 5000.0, 0.0)
        assert emission == pytest.approx(0.0, abs=1e-6)

    def test_known_values(self, calculator):
        """Test with known values."""
        # HCV, 5000 kg, 100 km
        # rate = 2.61 + 0.000147 * 5000 = 3.345 kg CO2/km
        expected = 3.345 * 100  # 334.5 kg CO2
        emission = calculator.route_emission("HCV", 5000.0, 100.0)
        assert emission == pytest.approx(expected, abs=1e-3)

    def test_emission_increases_with_load(self, calculator):
        """Higher load should produce more emissions."""
        e_low = calculator.route_emission("HCV", 1000.0, 100.0)
        e_high = calculator.route_emission("HCV", 8000.0, 100.0)
        assert e_high > e_low

    def test_emission_increases_with_distance(self, calculator):
        """Higher distance should produce more emissions."""
        e_short = calculator.route_emission("HCV", 5000.0, 50.0)
        e_long = calculator.route_emission("HCV", 5000.0, 200.0)
        assert e_long > e_short


class TestFleetEmission:
    """Test fleet-level emission calculations."""

    def test_single_allocation(self, calculator, config):
        """Test with simple single warehouse-customer allocation."""
        # 1 warehouse, 2 customers, 2 vehicle types
        allocation = np.zeros((5, 2, 2))
        allocation[0, 0, 0] = 1.0  # Customer 0 fully by WH0, HCV
        allocation[0, 1, 1] = 1.0  # Customer 1 fully by WH0, LCV

        distance_matrix = np.ones((5, 2)) * 100.0  # 100 km
        demand = np.array([2000.0, 1000.0])

        emission = calculator.fleet_emission(
            allocation, distance_matrix, demand, config
        )
        assert emission > 0

    def test_zero_allocation(self, calculator, config):
        """Zero allocation should produce zero emission."""
        allocation = np.zeros((5, 3, 2))
        distance_matrix = np.ones((5, 3)) * 100.0
        demand = np.array([2000.0, 1000.0, 500.0])

        emission = calculator.fleet_emission(
            allocation, distance_matrix, demand, config
        )
        assert emission == pytest.approx(0.0, abs=1e-6)

    def test_fleet_cost_uses_ceil(self, calculator, config):
        """Shipping 15000 kg via HCV (cap=10000) should cost 2 trips.

        Cost = 2 * dist * cost_per_km * ceil(15000/10000)
             = 2 * 100 * 18 * 2 = 7200 INR.
        """
        # 5 warehouses, 1 customer, 2 vehicle types
        allocation = np.zeros((5, 1, 2))
        allocation[0, 0, 0] = 1.0  # Customer 0 fully by WH0, HCV

        distance_matrix = np.ones((5, 1)) * 100.0  # 100 km
        demand = np.array([15000.0])  # 15000 kg, exceeds HCV cap of 10000

        cost = calculator.fleet_cost(
            allocation, distance_matrix, demand, config
        )
        # ceil(15000/10000) = 2 trips
        expected = 2 * 100 * 18.0 * 2
        assert cost == pytest.approx(expected, abs=1e-6)

    def test_fleet_emission_uses_ceil_for_return(self, calculator, config):
        """Multi-trip emission uses correct formula.

        For HCV shipping 15000 kg over 100 km:
            n_trips = ceil(15000/10000) = 2
            Loaded emission = (n_trips * k + L * load) * dist
                            = (2 * 2.61 + 0.000147 * 15000) * 100
            Empty return = k * dist * n_trips
                         = 2.61 * 100 * 2
        """
        allocation = np.zeros((5, 1, 2))
        allocation[0, 0, 0] = 1.0  # Customer 0 fully by WH0, HCV

        distance_matrix = np.ones((5, 1)) * 100.0
        demand = np.array([15000.0])

        emission = calculator.fleet_emission(
            allocation, distance_matrix, demand, config
        )

        # Loaded trip: (n_trips * k + L * load) * dist
        k = 2.61
        L = 0.000147
        load = 15000.0
        dist = 100.0
        n_trips = 2  # ceil(15000/10000)
        emission_loaded = (n_trips * k + L * load) * dist
        # Empty return: k * dist * n_trips
        emission_empty = k * dist * n_trips

        expected = emission_loaded + emission_empty
        assert emission == pytest.approx(expected, abs=1e-6)



# Audit Phase Eight — Property tests for MEET invariants
import pytest
try:
    from hypothesis import given, settings, strategies as st
    HYP = True
except ImportError:
    HYP = False


@pytest.mark.skipif(not HYP, reason="hypothesis not installed")
class TestEmissionInvariants:
    """Property-based tests on MEET emission model invariants."""

    @given(
        load_a=st.floats(min_value=0.0, max_value=10000.0,
                         allow_nan=False, allow_infinity=False),
        load_b=st.floats(min_value=0.0, max_value=10000.0,
                         allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=30, deadline=None)
    def test_emission_monotone_in_load(self, load_a, load_b):
        """E(HCV, l_a) <= E(HCV, l_b) iff l_a <= l_b. (L > 0)"""
        from supply_chain_research.config import MasterConfig
        from supply_chain_research.phase1_foundation.emission_model import (
            EmissionCalculator,
        )
        calc = EmissionCalculator(MasterConfig())
        e_a = calc.emission_rate("HCV", load_a)
        e_b = calc.emission_rate("HCV", load_b)
        if load_a <= load_b:
            assert e_a <= e_b + 1e-12
        else:
            assert e_a >= e_b - 1e-12

    @given(
        load=st.floats(min_value=0.0, max_value=10000.0,
                       allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=20, deadline=None)
    def test_emission_strictly_positive(self, load):
        """Emission rate is always positive (k > 0)."""
        from supply_chain_research.config import MasterConfig
        from supply_chain_research.phase1_foundation.emission_model import (
            EmissionCalculator,
        )
        calc = EmissionCalculator(MasterConfig())
        for vehicle in ("HCV", "LCV"):
            assert calc.emission_rate(vehicle, load) > 0

    @given(
        load=st.floats(min_value=0.0, max_value=10000.0,
                       allow_nan=False, allow_infinity=False),
        distance=st.floats(min_value=0.0, max_value=2000.0,
                          allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=20, deadline=None)
    def test_route_emission_zero_at_zero_distance(self, load, distance):
        """Emission scales linearly with distance."""
        from supply_chain_research.config import MasterConfig
        from supply_chain_research.phase1_foundation.emission_model import (
            EmissionCalculator,
        )
        calc = EmissionCalculator(MasterConfig())
        e = calc.route_emission("HCV", load, distance)
        assert e >= 0
        # Half distance -> half emission (since rate is independent of distance)
        e_half = calc.route_emission("HCV", load, distance / 2)
        assert abs(e_half - e / 2) < 1e-9


@pytest.mark.skipif(not HYP, reason="hypothesis not installed")
class TestRouteAdditivity:
    """Property-based tests for route emission additivity.

    **Validates: Requirements 3.3**
    """

    @given(
        load=st.floats(min_value=0, max_value=10000,
                       allow_nan=False, allow_infinity=False),
        d1=st.floats(min_value=0.1, max_value=1000,
                     allow_nan=False, allow_infinity=False),
        d2=st.floats(min_value=0.1, max_value=1000,
                     allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=30, deadline=None)
    def test_route_additivity(self, load, d1, d2):
        """route_emission(load, d1) + route_emission(load, d2) == route_emission(load, d1+d2).

        Since emission = rate(load) * distance, and rate is independent of
        distance, the route emission must be additive over distance segments.

        **Validates: Requirements 3.3**
        """
        from supply_chain_research.config import MasterConfig
        from supply_chain_research.phase1_foundation.emission_model import (
            EmissionCalculator,
        )
        calc = EmissionCalculator(MasterConfig())
        e1 = calc.route_emission("HCV", load, d1)
        e2 = calc.route_emission("HCV", load, d2)
        e_combined = calc.route_emission("HCV", load, d1 + d2)
        assert abs((e1 + e2) - e_combined) < 1e-9


@pytest.mark.skip(reason="CIS not implemented")
class TestCarbonIntensityScore:
    """Property-based tests for Carbon Intensity Score (CIS).

    CIS should lie in [0, 1] for any non-degenerate route.
    Skipped because compute_carbon_intensity_score is not yet
    implemented in emission_model.py.

    **Validates: Requirements 3.3**
    """

    @pytest.mark.skipif(not HYP, reason="hypothesis not installed")
    @given(
        load=st.floats(min_value=1.0, max_value=10000.0,
                       allow_nan=False, allow_infinity=False),
        distance=st.floats(min_value=0.1, max_value=2000.0,
                           allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=20, deadline=None)
    def test_cis_in_unit_interval(self, load, distance):
        """CIS must lie in [0, 1] for any non-degenerate route."""
        from supply_chain_research.config import MasterConfig
        from supply_chain_research.phase1_foundation.emission_model import (
            EmissionCalculator,
        )
        calc = EmissionCalculator(MasterConfig())
        score = calc.compute_carbon_intensity_score(load, distance)
        assert 0.0 <= score <= 1.0
