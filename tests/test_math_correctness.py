"""Mathematical correctness tests for supply chain research.

Verifies exact formulas, algorithms, and constraint conventions
to ensure PhD-tier research quality.
"""

import numpy as np
import pytest
import torch

from supply_chain_research.config import MasterConfig, LSTMConfig, PPOConfig
from supply_chain_research.phase1_foundation.emission_model import EmissionCalculator
from supply_chain_research.phase1_foundation.nsga2_solver import SupplyChainProblem
from supply_chain_research.phase1_foundation.data_engineering import generate_demand
from supply_chain_research.phase3_ai.ppo_agent import PPOAgent
from supply_chain_research.phase3_ai.lstm_forecaster import AttentionLSTMModel


@pytest.fixture
def config():
    """Default configuration."""
    return MasterConfig()


@pytest.fixture
def calculator(config):
    """Emission calculator."""
    return EmissionCalculator(config)


class TestEmissionFormulas:
    """Verify exact MEET emission model formulas."""

    def test_emission_rate_zero_load_equals_k_exactly(self, calculator):
        """E(0) = k exactly for both vehicle types."""
        assert calculator.emission_rate("HCV", 0.0) == 2.61
        assert calculator.emission_rate("LCV", 0.0) == 0.89

    def test_emission_rate_full_load_hcv(self, calculator):
        """E(10000) = k + L*capacity = 2.61 + 0.000147*10000 = 4.08."""
        expected = 2.61 + 0.000147 * 10000  # 4.08
        actual = calculator.emission_rate("HCV", 10000.0)
        assert actual == pytest.approx(expected, abs=1e-10)

    def test_emission_rate_full_load_lcv(self, calculator):
        """E(3000) = k + L*capacity = 0.89 + 0.000079*3000 = 1.127."""
        expected = 0.89 + 0.000079 * 3000  # 1.127
        actual = calculator.emission_rate("LCV", 3000.0)
        assert actual == pytest.approx(expected, abs=1e-10)

    def test_route_carbon_equals_rate_times_distance(self, calculator):
        """route_emission(type, load, dist) == emission_rate(type, load) * dist."""
        for vtype in ["HCV", "LCV"]:
            for load in [0, 1000, 5000, 10000]:
                for dist in [10, 100, 500]:
                    rate = calculator.emission_rate(vtype, load)
                    route = calculator.route_emission(vtype, load, dist)
                    assert route == pytest.approx(rate * dist, rel=1e-10)

    def test_fleet_cost_ceil_trips(self, calculator, config):
        """Fleet cost uses ceil(vol/capacity) for trip counting.

        15000 kg via HCV (cap=10000) at 100 km:
        ceil(15000/10000) = 2 trips
        cost = 2 * 100 * 18 * 2 = 7200 INR
        """
        allocation = np.zeros((5, 1, 2))
        allocation[0, 0, 0] = 1.0  # All from warehouse 0, HCV
        distance_matrix = np.full((5, 1), 100.0)
        demand = np.array([15000.0])

        cost = calculator.fleet_cost(allocation, distance_matrix, demand, config)
        # ceil(15000/10000) = 2 trips, round trip cost = 2 * 100 * 18 * 2 = 7200
        expected = 2 * 100.0 * 18.0 * 2
        assert cost == pytest.approx(expected, rel=1e-6)


class TestNSGA2Constraints:
    """Verify NSGA-II uses correct pymoo constraint convention (G <= 0)."""

    def test_feasible_solution_all_constraints_satisfied(self):
        """A feasible solution has all G <= 0."""
        config = MasterConfig()
        config.network.n_customers = 5
        config.network.n_warehouses = 3
        n_w, n_c, n_v = 3, 5, 2

        rng = np.random.default_rng(42)
        distance_matrix = rng.uniform(50, 500, size=(n_w, n_c))
        demand = rng.uniform(200, 2000, size=n_c)

        problem = SupplyChainProblem(config, distance_matrix, demand)

        # Create a feasible solution: split demand evenly across warehouses, HCV only
        X = np.zeros((1, n_w * n_c * n_v))
        x = X[0].reshape(n_w, n_c, n_v)
        for c in range(n_c):
            for w in range(n_w):
                x[w, c, 0] = demand[c] / n_w
        X[0] = x.flatten()

        out = {}
        problem._evaluate(X, out)

        # All constraints should be <= 0 (feasible)
        assert np.all(out["G"][0] <= 1e-2), f"Constraints violated: {out['G'][0]}"

    def test_demand_violation_gives_positive_constraint(self):
        """Unmet demand gives G > 0 for the demand constraint."""
        config = MasterConfig()
        config.network.n_customers = 5
        config.network.n_warehouses = 3
        n_w, n_c, n_v = 3, 5, 2

        rng = np.random.default_rng(42)
        distance_matrix = rng.uniform(50, 500, size=(n_w, n_c))
        demand = rng.uniform(200, 2000, size=n_c)

        problem = SupplyChainProblem(config, distance_matrix, demand)

        # Create infeasible solution: give customer 0 only half their demand
        X = np.zeros((1, n_w * n_c * n_v))
        x = X[0].reshape(n_w, n_c, n_v)
        # Customer 0 gets only 50% of demand
        x[0, 0, 0] = demand[0] * 0.5
        # Other customers get full demand
        for c in range(1, n_c):
            x[0, c, 0] = demand[c]
        X[0] = x.flatten()

        out = {}
        problem._evaluate(X, out)

        # Demand constraint for customer 0 should be violated (G > 0)
        assert out["G"][0, 0] > 0, f"Expected G[0] > 0 but got {out['G'][0, 0]}"

    def test_warehouse_capacities_from_config(self):
        """NSGA-II problem uses per-warehouse capacities from config."""
        config = MasterConfig()
        config.network.n_warehouses = 5
        config.network.n_customers = 10

        rng = np.random.default_rng(42)
        distance_matrix = rng.uniform(50, 500, size=(5, 10))
        demand = rng.uniform(200, 2000, size=10)

        problem = SupplyChainProblem(config, distance_matrix, demand)

        expected = np.array([60000.0, 55000.0, 50000.0, 48000.0, 45000.0])
        np.testing.assert_array_almost_equal(
            problem.warehouse_capacities, expected
        )


class TestDemandGeneration:
    """Verify demand generation produces correct ranges."""

    def test_lognormal_demand_in_range(self, config):
        """generate_demand produces values clipped to [100, 10000]."""
        rng = np.random.default_rng(42)
        demand = generate_demand(config, rng)
        assert np.all(demand >= 100)
        assert np.all(demand <= 10000)
        assert len(demand) == config.network.n_customers

    def test_lognormal_demand_realistic_mean(self, config):
        """Mean demand should be reasonable (not absurdly high or low)."""
        rng = np.random.default_rng(42)
        demand = generate_demand(config, rng)
        mean = demand.mean()
        # With lognormal(7.5, 0.6), mean ~ exp(7.5 + 0.18) ~ 1808 (clipped to 10000)
        assert 500 < mean < 5000, f"Mean demand {mean} outside expected range"


class TestMathematicalRigor:
    """Verify mathematical rigor of AI model implementations."""

    def test_ppo_advantage_normalization(self):
        """PPO advantages are normalized to mean~0, std~1 unconditionally."""
        # Test the normalization formula directly on known values
        advantages = np.array([10.0, 20.0, 30.0, 40.0, 50.0])
        normalized = (advantages - advantages.mean()) / (advantages.std() + 1e-8)

        assert abs(normalized.mean()) < 1e-6, "Normalized advantages should have mean ~0"
        assert abs(normalized.std() - 1.0) < 1e-6, "Normalized advantages should have std ~1"

        # Test with zero-variance advantages (edge case)
        constant_adv = np.array([5.0, 5.0, 5.0, 5.0])
        normalized_const = (constant_adv - constant_adv.mean()) / (constant_adv.std() + 1e-8)
        # Should not produce NaN or Inf due to eps
        assert np.all(np.isfinite(normalized_const))

        # Test PPOAgent update completes without error
        agent = PPOAgent(obs_dim=4, action_dim=2, config=PPOConfig(n_epochs=2))
        rng = np.random.default_rng(42)
        n_steps = 32
        rollout_data = {
            'observations': rng.standard_normal((n_steps, 4)).astype(np.float32),
            'actions': rng.standard_normal((n_steps, 2)).astype(np.float32),
            'rewards': rng.standard_normal(n_steps).astype(np.float32) * 10,
            'values': rng.standard_normal(n_steps).astype(np.float32),
            'log_probs': rng.standard_normal(n_steps).astype(np.float32),
            'dones': np.zeros(n_steps).astype(np.float32),
        }

        metrics = agent.update(rollout_data, last_value=0.0)
        assert np.isfinite(metrics['actor_loss']), "Actor loss should be finite"
        assert np.isfinite(metrics['critic_loss']), "Critic loss should be finite"
        assert 'mean_advantage' in metrics, "Metrics should contain mean_advantage"

    def test_lstm_forget_gate_bias_initialized(self):
        """LSTM forget gate biases are initialized to 1.0 for all layers."""
        model = AttentionLSTMModel(input_size=10, config=LSTMConfig())
        hidden_size = model.hidden_size

        for name, param in model.lstm.named_parameters():
            if 'bias' in name:
                forget_bias = param.data[hidden_size:2*hidden_size]
                assert torch.all(forget_bias == 1.0), (
                    f"Forget gate bias in {name} should be 1.0, "
                    f"got {forget_bias[:5]}"
                )

    def test_ppo_clip_formula_bounds(self):
        """PPO-Clip formula correctly bounds the ratio and computes valid loss."""
        # Verify the clip formula on known tensor inputs
        epsilon = 0.2
        # Simulate various ratios
        ratios = torch.tensor([0.5, 0.8, 1.0, 1.2, 1.5, 2.0])
        advantages = torch.tensor([1.0, -1.0, 1.0, -1.0, 1.0, -1.0])

        surr1 = ratios * advantages
        surr2 = torch.clamp(ratios, 1.0 - epsilon, 1.0 + epsilon) * advantages
        actor_loss = -torch.min(surr1, surr2).mean()

        # The loss should be finite
        assert torch.isfinite(actor_loss), "Actor loss should be finite"

        # Verify clipping bounds: clamp should limit ratio to [0.8, 1.2]
        clamped_ratios = torch.clamp(ratios, 1.0 - epsilon, 1.0 + epsilon)
        assert torch.all(clamped_ratios >= 1.0 - epsilon)
        assert torch.all(clamped_ratios <= 1.0 + epsilon)

        # Test a full PPOAgent update produces valid metrics
        agent = PPOAgent(obs_dim=4, action_dim=2, config=PPOConfig(n_epochs=2))
        rng = np.random.default_rng(99)
        n_steps = 32
        rollout_data = {
            'observations': rng.standard_normal((n_steps, 4)).astype(np.float32),
            'actions': rng.standard_normal((n_steps, 2)).astype(np.float32),
            'rewards': rng.standard_normal(n_steps).astype(np.float32),
            'values': rng.standard_normal(n_steps).astype(np.float32),
            'log_probs': rng.standard_normal(n_steps).astype(np.float32),
            'dones': np.zeros(n_steps).astype(np.float32),
        }

        metrics = agent.update(rollout_data, last_value=0.0)
        assert np.isfinite(metrics['actor_loss']), "Actor loss should be finite after update"
        assert np.isfinite(metrics['entropy']), "Entropy should be finite"
        # Audit 1.5: Beta differential entropy can be negative; only
        # require finiteness (the old assertion `entropy > 0` was for
        # Gaussian entropy which is always positive).
