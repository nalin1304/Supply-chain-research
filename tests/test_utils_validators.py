"""Coverage tests for ``supply_chain_research.utils.validators``.

Validates ``validate_distance_matrix``, ``validate_allocation``,
``validate_positive``, ``is_non_dominated``, ``assert_non_dominated``.

References
----------
[bugfix.md C2.12] Coverage clause for ``utils/validators.py``.
"""

from __future__ import annotations

import numpy as np
import pytest

from supply_chain_research.utils.validators import (
    assert_non_dominated,
    is_non_dominated,
    validate_allocation,
    validate_distance_matrix,
    validate_positive,
)


class TestValidateDistanceMatrix:
    """Verify shape, non-negativity, and zero-diagonal invariants.

    Notes
    -----
    Distance matrices in routing problems must satisfy these three
    invariants for downstream solvers (NSGA-II, OR-Tools) to behave
    correctly.
    """

    def test_valid_matrix_returns_true(self) -> None:
        # [bugfix.md C2.12] symmetric, non-negative, zero-diagonal -> True.
        m = np.array([[0.0, 5.0, 7.0], [5.0, 0.0, 3.0], [7.0, 3.0, 0.0]])
        assert validate_distance_matrix(m, n_nodes=3) is True

    def test_wrong_shape_returns_false(self) -> None:
        # [bugfix.md C2.12] non-square / wrong-size matrices fail.
        m = np.zeros((3, 4))
        assert validate_distance_matrix(m, n_nodes=3) is False

    def test_negative_entries_return_false(self) -> None:
        # [bugfix.md C2.12] negative distances are rejected.
        m = np.array([[0.0, -1.0], [1.0, 0.0]])
        assert validate_distance_matrix(m, n_nodes=2) is False

    def test_non_zero_diagonal_returns_false(self) -> None:
        # [bugfix.md C2.12] non-zero diagonal entries are rejected
        # (self-distance must be exactly zero).
        m = np.array([[1e-3, 5.0], [5.0, 0.0]])
        assert validate_distance_matrix(m, n_nodes=2) is False


class TestValidateAllocation:
    """Verify shape constraints on allocation tensors.

    Notes
    -----
    ``allocation`` is a (warehouses, customers, vehicle_types) tensor.
    """

    def test_correct_shape_returns_true(self) -> None:
        # [bugfix.md C2.12] exact shape match -> True.
        alloc = np.zeros((3, 5, 2))
        assert validate_allocation(alloc, 3, 5, 2) is True

    def test_wrong_shape_returns_false(self) -> None:
        # [bugfix.md C2.12] mismatched shape -> False.
        alloc = np.zeros((3, 5, 1))
        assert validate_allocation(alloc, 3, 5, 2) is False
        # Wrong rank also rejected.
        assert validate_allocation(np.zeros((3, 5)), 3, 5, 2) is False


class TestValidatePositive:
    """Verify positivity check raises with descriptive message.

    Notes
    -----
    The helper is used to gate physical quantities (distance, capacity)
    that must be strictly greater than zero.
    """

    def test_positive_value_returns_value(self) -> None:
        # [bugfix.md C2.12] strictly positive value is returned unchanged.
        assert validate_positive(1.5) == pytest.approx(1.5)

    def test_zero_raises_valueerror(self) -> None:
        # [bugfix.md C2.12] zero is rejected (strict positivity).
        with pytest.raises(ValueError, match="must be positive"):
            validate_positive(0.0)

    def test_negative_raises_valueerror_with_name(self) -> None:
        # [bugfix.md C2.12] negative value is rejected; message embeds the
        # caller-supplied ``name``.
        with pytest.raises(ValueError, match="capacity must be positive"):
            validate_positive(-3.2, name="capacity")


class TestIsNonDominated:
    """Verify the Pareto-front non-domination check.

    Notes
    -----
    A "front" is non-dominated iff no point dominates another. We
    cover the empty/single trivially-true cases and a known-dominated
    front where one solution is strictly worse than another in every
    objective.
    """

    def test_empty_input_is_trivially_non_dominated(self) -> None:
        # [bugfix.md C2.12] empty front -> True (no pairs to compare).
        assert is_non_dominated(np.empty((0, 2))) is True

    def test_none_input_is_trivially_non_dominated(self) -> None:
        # [bugfix.md C2.12] ``None`` is a valid no-op input.
        assert is_non_dominated(None) is True

    def test_single_point_is_trivially_non_dominated(self) -> None:
        # [bugfix.md C2.12] single point cannot dominate itself.
        assert is_non_dominated(np.array([[1.0, 2.0]])) is True

    def test_pareto_front_returns_true(self) -> None:
        # [bugfix.md C2.12] known non-dominated 2-D front (each point
        # trades cost for carbon).
        front = np.array([
            [1.0, 5.0],
            [2.0, 4.0],
            [3.0, 3.0],
            [4.0, 2.0],
            [5.0, 1.0],
        ])
        assert is_non_dominated(front) is True

    def test_dominated_solutions_return_false(self) -> None:
        # [bugfix.md C2.12] a strictly worse point ([5, 5]) is dominated
        # by every other point in the front.
        front = np.array([
            [1.0, 1.0],   # dominates everything else
            [2.0, 2.0],
            [5.0, 5.0],
        ])
        assert is_non_dominated(front) is False


class TestAssertNonDominated:
    """Verify the assertion wrapper raises only on dominated fronts.

    Notes
    -----
    The wrapper is the gate used by NSGA-II solver tests; it must
    surface a human-readable message when the front fails.
    """

    def test_passes_on_valid_front(self) -> None:
        # [bugfix.md C2.12] valid Pareto front: no exception.
        front = np.array([[1.0, 5.0], [3.0, 3.0], [5.0, 1.0]])
        assert_non_dominated(front)

    def test_raises_with_named_message(self) -> None:
        # [bugfix.md C2.12] message includes the supplied ``name`` so a
        # test trace points to the failing solver.
        front = np.array([[1.0, 1.0], [5.0, 5.0]])
        with pytest.raises(AssertionError, match="my front"):
            assert_non_dominated(front, name="my front")
