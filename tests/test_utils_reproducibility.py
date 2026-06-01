"""Coverage tests for ``supply_chain_research.utils.reproducibility``.

Validates that the seeded-RNG plumbing in ``derive_seeds``,
``set_global_seed``, ``worker_seed`` and ``get_rng`` honours
NEP-19 / SeedSequence guarantees.

References
----------
[bugfix.md C2.12] Coverage clause for ``utils/reproducibility.py``.
"""

from __future__ import annotations

import os
import random
from dataclasses import fields

import numpy as np
import pytest

from supply_chain_research.utils import reproducibility as repro
from supply_chain_research.utils.reproducibility import (
    SeedBundle,
    derive_seeds,
    get_rng,
    set_global_seed,
    worker_seed,
)


class TestSeedBundleShape:
    """Verify the dataclass exposes the documented fields.

    Notes
    -----
    A regression here would mean a downstream consumer of the bundle
    silently loses access to a per-component seed.
    """

    def test_seedbundle_has_all_documented_fields(self) -> None:
        # [bugfix.md C2.12] dataclass shape must include every per-component
        # seed plus the worker base.
        names = {f.name for f in fields(SeedBundle)}
        expected = {
            "root", "numpy", "python", "torch_cpu", "torch_cuda",
            "simpy", "pymoo", "worker_base",
        }
        assert expected.issubset(names)


class TestDeriveSeeds:
    """Verify ``derive_seeds`` is deterministic and well-spread.

    Notes
    -----
    Reproducibility is the headline contract; we verify that the same
    root yields the same bundle and that different roots yield
    different bundles.
    """

    def test_derive_seeds_is_deterministic(self) -> None:
        # [bugfix.md C2.12] two calls with the same root return identical
        # bundles (NEP-19 SeedSequence determinism).
        a = derive_seeds(42)
        b = derive_seeds(42)

        assert a == b

    def test_derive_seeds_changes_with_root(self) -> None:
        # [bugfix.md C2.12] different roots yield different per-component
        # seeds (otherwise downstream RNGs would correlate).
        a = derive_seeds(42)
        b = derive_seeds(43)

        assert a.numpy != b.numpy
        assert a.python != b.python
        assert a.worker_base != b.worker_base

    def test_derive_seeds_default_root_is_42(self) -> None:
        # [bugfix.md C2.12] default root matches documentation.
        bundle = derive_seeds()
        assert bundle.root == 42
        # All component seeds must be non-negative 32-bit unsigned ints.
        for f in fields(bundle):
            value = getattr(bundle, f.name)
            assert isinstance(value, int)
            assert 0 <= value <= 0xFFFFFFFF


class TestWorkerSeed:
    """Verify per-worker seeds are deterministic and uncorrelated.

    Notes
    -----
    Per-worker correlation would break parallel-pool reproducibility
    in pymoo / multiprocessing workloads.
    """

    def test_worker_seed_is_deterministic(self) -> None:
        # [bugfix.md C2.12] same (root, worker) pair returns the same seed.
        assert worker_seed(42, 0) == worker_seed(42, 0)
        assert worker_seed(42, 1) == worker_seed(42, 1)

    def test_worker_seed_differs_per_worker(self) -> None:
        # [bugfix.md C2.12] different worker indices yield different seeds.
        assert worker_seed(42, 0) != worker_seed(42, 1)

    def test_worker_seed_differs_per_root(self) -> None:
        # [bugfix.md C2.12] different roots yield different seeds for the
        # same worker index.
        assert worker_seed(42, 0) != worker_seed(43, 0)

    def test_worker_seed_returns_unsigned_int(self) -> None:
        # [bugfix.md C2.12] return value fits in uint32 range.
        seed = worker_seed(42, 7)
        assert isinstance(seed, int)
        assert 0 <= seed <= 0xFFFFFFFF


class TestSetGlobalSeed:
    """Verify ``set_global_seed`` actually wires up Python and NumPy RNGs.

    Notes
    -----
    We verify the RNG state by sampling: two calls with the same seed
    must produce the same first sample.
    """

    def test_set_global_seed_returns_seedbundle(self) -> None:
        # [bugfix.md C2.12] return value carries the derived seeds.
        bundle = set_global_seed(42)
        assert isinstance(bundle, SeedBundle)
        assert bundle.root == 42

    def test_set_global_seed_makes_numpy_deterministic(self) -> None:
        # [bugfix.md C2.12] ``np.random.seed`` is set; sampling from the
        # legacy global state must match across calls.
        set_global_seed(42)
        first = np.random.rand(4)
        set_global_seed(42)
        second = np.random.rand(4)

        np.testing.assert_array_equal(first, second)

    def test_set_global_seed_makes_python_random_deterministic(self) -> None:
        # [bugfix.md C2.12] ``random.seed`` is set; sampling matches.
        set_global_seed(42)
        a = [random.random() for _ in range(4)]
        set_global_seed(42)
        b = [random.random() for _ in range(4)]

        assert a == b

    def test_set_global_seed_sets_pythonhashseed_env(self) -> None:
        # [bugfix.md C2.12] PYTHONHASHSEED is exported as a string.
        set_global_seed(42)
        assert os.environ.get("PYTHONHASHSEED") is not None
        # Value must be a parseable integer.
        int(os.environ["PYTHONHASHSEED"])


class TestGetRng:
    """Verify ``get_rng`` returns deterministic / non-deterministic generators.

    Notes
    -----
    Non-determinism for ``seed=None`` is verified by checking that two
    independent calls produce different first samples (probability of
    a false positive is below 1e-19 for a 64-bit float).
    """

    def test_get_rng_with_seed_is_deterministic(self) -> None:
        # [bugfix.md C2.12] same seed yields the same sample sequence.
        a = get_rng(42).random(8)
        b = get_rng(42).random(8)

        np.testing.assert_array_equal(a, b)

    def test_get_rng_different_seeds_differ(self) -> None:
        # [bugfix.md C2.12] different seeds yield different samples.
        a = get_rng(42).random(8)
        b = get_rng(43).random(8)

        assert not np.array_equal(a, b)

    def test_get_rng_none_returns_nondeterministic_generator(self) -> None:
        # [bugfix.md C2.12] ``seed=None`` returns a fresh OS-seeded RNG
        # whose first sample is overwhelmingly unlikely to repeat.
        a = get_rng(None).random(8)
        b = get_rng(None).random(8)

        # Two 8-element float64 vectors from independent OS-seeded
        # generators have collision probability << 1e-19.
        assert not np.array_equal(a, b)

    def test_get_rng_returns_numpy_generator_instance(self) -> None:
        # [bugfix.md C2.12] return type is ``numpy.random.Generator``.
        rng = get_rng(42)
        assert isinstance(rng, np.random.Generator)
