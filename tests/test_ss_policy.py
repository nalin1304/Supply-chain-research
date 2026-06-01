"""Coverage tests for ``supply_chain_research.phase3_ai.ss_policy``.

Validates the (s, S) reorder-point baseline policy against a small
``SupplyChainEnv`` instance. The (s, S) formulae are documented in
[Zipkin-2000 §5] (continuous-review base-stock) and
[Silver-2017 §5.4] (reorder point and order-up-to level).

References
----------
[bugfix.md C2.12] Coverage clause for ``phase3_ai/ss_policy.py``.
"""

from __future__ import annotations

import numpy as np
import pytest

from supply_chain_research.config import MasterConfig
from supply_chain_research.phase3_ai.gym_environment import SupplyChainEnv
from supply_chain_research.phase3_ai.ss_policy import (
    SSPolicy,
    evaluate_ss_policy,
)


class TestSSPolicyInit:
    """Verify ``SSPolicy.__init__`` configures s and S correctly.

    Notes
    -----
    ``s`` and ``S`` must be elementwise scalings of the per-warehouse
    capacity (Silver-2017 §5.4 base-stock formula).
    """

    def test_default_capacities_when_none_provided(self) -> None:
        # [bugfix.md C2.12] ``warehouse_capacities=None`` falls back to the
        # documented 50000 kg per warehouse.  # [Silver-2017 §5.4]
        policy = SSPolicy(n_warehouses=3, n_customers=10)

        np.testing.assert_array_equal(
            policy.warehouse_capacities, np.full(3, 50000.0),
        )
        np.testing.assert_allclose(policy.s, 0.3 * 50000.0)
        np.testing.assert_allclose(policy.S, 0.9 * 50000.0)

    def test_custom_capacities_propagate_to_s_and_S(self) -> None:
        # [bugfix.md C2.12] explicit per-warehouse capacities scale s and S
        # elementwise.  # [Zipkin-2000 §5]
        caps = np.array([60000.0, 55000.0, 50000.0])
        policy = SSPolicy(
            n_warehouses=3,
            n_customers=10,
            reorder_point_fraction=0.25,
            order_up_to_fraction=0.85,
            warehouse_capacities=caps,
        )

        np.testing.assert_allclose(policy.s, 0.25 * caps)
        np.testing.assert_allclose(policy.S, 0.85 * caps)
        assert policy.n_warehouses == 3
        assert policy.n_customers == 10


class TestSSPolicyGetAction:
    """Verify ``get_action`` reorder triggers and action bounds.

    Notes
    -----
    Action values must lie in [-1, 1] (matching the gym continuous
    action space). Reorders are triggered iff inventory falls below
    the reorder point ``s`` (Silver-2017 §5.4).
    """

    def test_action_in_unit_box(self) -> None:
        # [bugfix.md C2.12] action values are clipped to [0, 1] for the
        # SupplyChainEnv action space.
        policy = SSPolicy(n_warehouses=2, n_customers=3)
        # Inventory at 50% capacity in both warehouses; obs first n_w
        # entries are normalised levels in [0, 1].
        obs = np.zeros(20)
        obs[:2] = 0.5

        action = policy.get_action(obs)

        assert action.shape == (2 * 3,)
        assert np.all(action >= 0.0)
        assert np.all(action <= 1.0)

    def test_low_inventory_triggers_reorder(self) -> None:
        # [bugfix.md C2.12] when inventory < s, the corresponding action
        # entries become non-zero (reorder is placed).  # [Zipkin-2000 §5]
        policy = SSPolicy(n_warehouses=2, n_customers=3)
        obs = np.zeros(20)
        obs[:2] = 0.05  # well below 30 % reorder point

        action = policy.get_action(obs)

        # At least one allocation entry is non-zero (reorder placed for
        # at least one customer-warehouse pair).
        assert np.any(action != 0.0)

    def test_high_inventory_no_reorder(self) -> None:
        # [bugfix.md C2.12] when inventory >= s, no reorder is triggered;
        # the policy returns the zeroed action vector.
        policy = SSPolicy(n_warehouses=2, n_customers=3)
        obs = np.zeros(20)
        obs[:2] = 0.95  # above the 30 % reorder point

        action = policy.get_action(obs)

        np.testing.assert_array_equal(action, np.zeros(2 * 3))


class TestEvaluateSSPolicy:
    """Verify ``evaluate_ss_policy`` integrates with ``SupplyChainEnv``.

    Notes
    -----
    Uses ``n_episodes=2`` and a small environment so the test stays
    inside the per-suite time budget.
    """

    def test_evaluate_returns_documented_dict_shape(self) -> None:
        # [bugfix.md C2.12] returned dict carries every documented field
        # with the documented numeric type.
        cfg = MasterConfig()
        env = SupplyChainEnv(
            n_customers=4,
            n_warehouses=2,
            episode_length=8,
            warehouse_capacities=[60000.0, 50000.0],
            config=cfg,
        )

        results = evaluate_ss_policy(
            env,
            n_warehouses=2,
            n_customers=4,
            n_episodes=2,
            seed=7,
        )

        for key in (
            "mean_reward", "std_reward", "min_reward", "max_reward",
            "median_reward", "n_episodes", "mean_episode_length",
            "policy_params", "episode_rewards",
        ):
            assert key in results

        assert results["n_episodes"] == 2
        assert isinstance(results["mean_reward"], float)
        assert np.isfinite(results["mean_reward"])
        assert isinstance(results["episode_rewards"], list)
        assert len(results["episode_rewards"]) == 2
        assert results["policy_params"]["reorder_point_fraction"] == 0.3
        assert results["policy_params"]["order_up_to_fraction"] == 0.9
