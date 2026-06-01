"""Serialization utilities with atomic write semantics.

All save functions write to a sibling temp file then os.replace() to
the target. POSIX guarantees rename is atomic, so a process crash
during the write leaves either the previous file or the new file
intact, never a partial file.
"""

import contextlib
import json
import os
import pickle
import tempfile
from pathlib import Path
from typing import Any

import numpy as np


def _atomic_write(filepath: str, write_callback) -> None:
    """Atomic file replacement.

    write_callback receives an open file handle in binary or text mode
    depending on the caller, writes to a temp file in the same
    directory, and the wrapper atomically renames on success.
    """
    path = Path(filepath)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(fd, "wb") as f:
            write_callback(f)
        # os.replace is atomic on POSIX and Windows
        os.replace(tmp_path, str(path))
    except Exception:
        # Clean up temp file on failure. The temp file may already be
        # gone (e.g. if mkstemp succeeded but the write itself failed
        # before a flush), so a missing-file outcome is benign and
        # suppressed via contextlib rather than a bare `pass` body.
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp_path)
        raise


def save_numpy(array: np.ndarray, filepath: str) -> None:
    """Atomic save of a numpy array.

    Parameters
    ----------
    array : np.ndarray
        Array to persist.
    filepath : str
        Destination ``.npy`` path.

    Returns
    -------
    None
        Writes to ``filepath`` atomically (POSIX/Windows
        ``os.replace``).
    """
    def _writer(f):
        np.save(f, array, allow_pickle=False)
    _atomic_write(filepath, _writer)


def load_numpy(filepath: str) -> np.ndarray:
    """Load a numpy array from file.

    Parameters
    ----------
    filepath : str
        Source ``.npy`` path.

    Returns
    -------
    np.ndarray
        The deserialized array.
    """
    return np.load(filepath, allow_pickle=False)


def save_json(data: Any, filepath: str) -> None:
    """Atomic save of JSON-serializable data.

    Parameters
    ----------
    data : Any
        JSON-serializable Python object.
    filepath : str
        Destination ``.json`` path.

    Returns
    -------
    None
        Writes to ``filepath`` atomically.
    """
    def _writer(f):
        f.write(json.dumps(data, indent=2, default=str).encode("utf-8"))
    _atomic_write(filepath, _writer)


def load_json(filepath: str) -> Any:
    """Load data from JSON file.

    Parameters
    ----------
    filepath : str
        Source ``.json`` path.

    Returns
    -------
    Any
        The decoded object.
    """
    with open(filepath, "r") as f:
        return json.load(f)


def save_pickle(obj: Any, filepath: str) -> None:
    """Atomic save of a pickled Python object.

    Parameters
    ----------
    obj : Any
        Picklable Python object.
    filepath : str
        Destination ``.pkl`` path.

    Returns
    -------
    None
        Writes to ``filepath`` atomically.
    """
    def _writer(f):
        pickle.dump(obj, f, protocol=pickle.HIGHEST_PROTOCOL)
    _atomic_write(filepath, _writer)


def load_pickle(filepath: str) -> Any:
    """Load object from pickle file.

    Parameters
    ----------
    filepath : str
        Source ``.pkl`` path.

    Returns
    -------
    Any
        The unpickled object.
    """
    with open(filepath, "rb") as f:
        return pickle.load(f)
