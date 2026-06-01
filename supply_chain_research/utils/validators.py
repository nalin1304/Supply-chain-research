"""Validation helper functions."""

import numpy as np


def validate_distance_matrix(matrix: np.ndarray, n_nodes: int) -> bool:
    """Validate a distance matrix has correct shape and non-negative values.

    Parameters
    ----------
    matrix : np.ndarray of shape (n_nodes, n_nodes)
        Distance matrix to validate.
    n_nodes : int
        Expected number of nodes (rows and columns).

    Returns
    -------
    bool
        True if the matrix is square with the expected shape, all values
        are non-negative, and the diagonal is zero.
    """
    if matrix.shape != (n_nodes, n_nodes):
        return False
    if np.any(matrix < 0):
        return False
    if not np.allclose(np.diag(matrix), 0):
        return False
    return True


def validate_allocation(
    allocation: np.ndarray,
    n_warehouses: int,
    n_customers: int,
    n_vehicle_types: int
) -> bool:
    """Validate allocation matrix dimensions.

    Parameters
    ----------
    allocation : np.ndarray
        Allocation array to validate.
    n_warehouses : int
        Expected number of warehouses (first dimension).
    n_customers : int
        Expected number of customers (second dimension).
    n_vehicle_types : int
        Expected number of vehicle types (third dimension).

    Returns
    -------
    bool
        True if the allocation shape matches
        (n_warehouses, n_customers, n_vehicle_types).
    """
    expected_shape = (n_warehouses, n_customers, n_vehicle_types)
    return allocation.shape == expected_shape


def validate_positive(value: float, name: str = "value") -> float:
    """Validate that a value is positive.

    Parameters
    ----------
    value : float
        The value to check.
    name : str, optional
        Name of the parameter for error messages, by default "value".

    Returns
    -------
    float
        The validated value (unchanged).

    Raises
    ------
    ValueError
        If value is less than or equal to zero.
    """
    if value <= 0:
        raise ValueError(f"{name} must be positive, got {value}")
    return value


def is_non_dominated(front: np.ndarray, atol: float = 1e-9) -> bool:
    """Verify every point in `front` is non-dominated by every other.

    A point a dominates b iff (a <= b in all objectives) AND
    (a < b in at least one objective). Both are minimization.

    Parameters
    ----------
    front : np.ndarray
        Array of shape (n_solutions, n_objectives).
    atol : float
        Absolute tolerance for "less than" comparisons.

    Returns
    -------
    bool
        True if no solution dominates any other.

    Complexity
    ----------
    O(n^2 * m). For n=1000, m=2 → ~2M comparisons, ~2 ms.
    """
    if front is None or len(front) < 2:
        return True
    arr = np.asarray(front, dtype=float)
    n = arr.shape[0]
    # Pairwise: a_i dominates a_j iff all-leq AND some-lt
    # Vectorized: cross-shape (n, n, m)
    a = arr[:, None, :]   # (n, 1, m)
    b = arr[None, :, :]   # (1, n, m)
    leq = (a <= b + atol).all(axis=-1)              # (n, n)
    lt = (a < b - atol).any(axis=-1)                # (n, n)
    dominates = leq & lt
    np.fill_diagonal(dominates, False)
    # If anything dominates anything, the front is not non-dominated
    return not dominates.any()


def assert_non_dominated(
    front: np.ndarray, name: str = "Pareto front",
) -> None:
    """Raise AssertionError with a human-readable message if dominated.

    Use this in test fixtures to gate optimization solver outputs.

    Parameters
    ----------
    front : np.ndarray
        Two-dimensional array of objective vectors of shape
        ``(n_solutions, n_objectives)``.
    name : str, optional
        Display name used in the AssertionError message.

    Returns
    -------
    None
        Returns nothing on success.

    Raises
    ------
    AssertionError
        If any element of ``front`` is dominated by another.
    """
    if not is_non_dominated(front):
        raise AssertionError(
            f"{name} contains dominated solutions; "
            f"shape={None if front is None else front.shape}."
        )
