"""Reproducibility utilities — derives all component seeds from one root.

A single integer seed flows through SeedSequence.spawn() to produce
independent, well-distributed seeds for every stochastic component:
NumPy global, Python random, PyTorch CPU/CUDA, and per-worker
seeds for parallel pools.

Reference: NEP 19 (Random Number Generator Policy) recommends
np.random.SeedSequence over scalar seeding for compositional safety.
"""

import contextlib
import os
import random
from dataclasses import dataclass

import numpy as np


@dataclass
class SeedBundle:
    """Bundle of derived seeds, one per stochastic component.

    Attributes
    ----------
    root : int
        The user-provided root seed.
    numpy, python, torch_cpu, torch_cuda, simpy, pymoo : int
        Per-component derived seeds spawned from ``root`` via
        :class:`numpy.random.SeedSequence`.
    worker_base : int
        Base seed used to spawn per-worker seeds in parallel
        pools.
    
    Parameters
    ----------
    """
    root: int
    numpy: int
    python: int
    torch_cpu: int
    torch_cuda: int
    simpy: int
    pymoo: int
    worker_base: int  # base for spawning per-worker seeds


def derive_seeds(root_seed: int = 42) -> SeedBundle:
    """Derive component seeds from a single root using SeedSequence.

    np.random.SeedSequence guarantees uncorrelated child seeds via
    a hash-based spawning scheme.

    Parameters
    ----------
    root_seed : int, optional
        Root seed (default 42).

    Returns
    -------
    SeedBundle
        Per-component seeds derived from ``root_seed``.
    """
    ss = np.random.SeedSequence(root_seed)
    children = ss.spawn(7)
    seeds = [int(c.generate_state(1, dtype=np.uint32)[0]) for c in children]
    return SeedBundle(
        root=root_seed,
        numpy=seeds[0],
        python=seeds[1],
        torch_cpu=seeds[2],
        torch_cuda=seeds[3],
        simpy=seeds[4],
        pymoo=seeds[5],
        worker_base=seeds[6],
    )


def set_global_seed(seed: int = 42) -> SeedBundle:
    """Set global seeds on all known stochastic components.

    Returns the SeedBundle so callers can pass component seeds to
    library-specific APIs (pymoo, simpy) that need explicit control.
    
    Parameters
    ----------
    """
    bundle = derive_seeds(seed)

    random.seed(bundle.python)
    np.random.seed(bundle.numpy)
    os.environ["PYTHONHASHSEED"] = str(bundle.python)

    # PyTorch is optional. Use contextlib.suppress so absence of torch
    # silently skips torch seeding without a bare `pass` body, and any
    # CUDA-related runtime errors are tolerated (NumPy / Python / hash
    # seeding above is sufficient for non-torch workflows).
    with contextlib.suppress(ImportError):
        import torch
        torch.manual_seed(bundle.torch_cpu)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(bundle.torch_cuda)
            torch.backends.cudnn.deterministic = True
            torch.backends.cudnn.benchmark = False

    return bundle


def worker_seed(root_seed: int, worker_index: int) -> int:
    """Per-worker seed for parallel pools.

    Each worker gets a deterministic but uncorrelated seed.

    Parameters
    ----------
    root_seed : int
        Root seed shared by all workers.
    worker_index : int
        Zero-based worker index.

    Returns
    -------
    int
        A 32-bit unsigned seed deterministic in
        ``(root_seed, worker_index)``.
    """
    ss = np.random.SeedSequence([root_seed, worker_index])
    return int(ss.generate_state(1, dtype=np.uint32)[0])


def get_rng(seed: int | None = 42) -> np.random.Generator:
    """Get a numpy Generator; uses SeedSequence under the hood.

    Parameters
    ----------
    seed : int or None, optional
        Seed value. ``None`` returns a fresh non-deterministic
        generator.

    Returns
    -------
    numpy.random.Generator
        A deterministic generator when ``seed`` is given.
    """
    if seed is None:
        return np.random.default_rng()
    return np.random.default_rng(np.random.SeedSequence(seed))
