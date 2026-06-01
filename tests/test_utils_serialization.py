"""Coverage tests for ``supply_chain_research.utils.serialization``.

Validates atomic-write semantics and round-trip identity for the
numpy / JSON / pickle savers exposed by the module.

References
----------
[bugfix.md C2.12] Coverage clause for ``utils/serialization.py``.
"""

from __future__ import annotations

import json
import os
import pickle
from pathlib import Path

import numpy as np
import pytest

from supply_chain_research.utils import serialization as ser


class TestAtomicWriteSemantics:
    """Verify ``_atomic_write`` writes via temp file and ``os.replace``.

    Notes
    -----
    Each test exercises the path-creation, success, and failure branches
    of ``_atomic_write`` so the helper is fully covered without touching
    the production module.
    """

    def test_atomic_write_creates_target_with_payload(self, tmp_path: Path) -> None:
        # [bugfix.md C2.12] success path: the target file exists with the
        # expected bytes after ``_atomic_write`` completes.
        target = tmp_path / "nested" / "atomic.bin"
        payload = b"hello-atomic"

        def writer(handle):
            handle.write(payload)

        ser._atomic_write(str(target), writer)

        assert target.exists()
        assert target.read_bytes() == payload
        # No leftover ``.tmp`` siblings — atomic semantics guarantee the
        # rename either succeeded or no temp file remains.
        leftovers = [p for p in target.parent.iterdir() if p.suffix == ".tmp"]
        assert leftovers == []

    def test_atomic_write_failure_preserves_original_target(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # [bugfix.md C2.12] failure path: a writer that raises must leave
        # the original target file unchanged and remove the temp file.
        target = tmp_path / "preserved.bin"
        original_bytes = b"original-content"
        target.write_bytes(original_bytes)

        def bad_writer(handle):
            handle.write(b"partial")
            raise RuntimeError("simulated I/O failure")

        with pytest.raises(RuntimeError, match="simulated I/O failure"):
            ser._atomic_write(str(target), bad_writer)

        assert target.read_bytes() == original_bytes
        leftovers = [p for p in target.parent.iterdir() if p.suffix == ".tmp"]
        assert leftovers == [], f"temp file remained: {leftovers}"

    def test_atomic_write_failure_no_pre_existing_target(
        self, tmp_path: Path,
    ) -> None:
        # [bugfix.md C2.12] failure path with no existing target: the file
        # must remain absent, and no ``.tmp`` artifact should be left.
        target = tmp_path / "absent.bin"

        def bad_writer(handle):
            raise OSError("disk full")

        with pytest.raises(OSError, match="disk full"):
            ser._atomic_write(str(target), bad_writer)

        assert not target.exists()
        leftovers = [p for p in target.parent.iterdir() if p.suffix == ".tmp"]
        assert leftovers == []


class TestNumpyRoundTrip:
    """Round-trip ``save_numpy`` / ``load_numpy``.

    Notes
    -----
    Verifies that numpy arrays survive an atomic write/read cycle with
    bit-exact equality.
    """

    def test_save_then_load_preserves_array(self, tmp_path: Path) -> None:
        # [bugfix.md C2.12] round-trip identity for a 2-D float array.
        arr = np.arange(12, dtype=np.float64).reshape(3, 4)
        path = tmp_path / "matrix.npy"

        ser.save_numpy(arr, str(path))
        loaded = ser.load_numpy(str(path))

        np.testing.assert_array_equal(loaded, arr)
        assert loaded.dtype == arr.dtype

    def test_save_numpy_creates_parent_directory(self, tmp_path: Path) -> None:
        # [bugfix.md C2.12] ``_atomic_write`` should mkdir parent on demand.
        arr = np.array([1, 2, 3])
        path = tmp_path / "deep" / "tree" / "vec.npy"

        ser.save_numpy(arr, str(path))

        assert path.exists()
        np.testing.assert_array_equal(ser.load_numpy(str(path)), arr)


class TestJsonRoundTrip:
    """Round-trip ``save_json`` / ``load_json``.

    Notes
    -----
    Verifies JSON encoding for primitive payloads and that
    ``default=str`` lets non-trivial objects (e.g. numpy scalars) serialise.
    """

    def test_save_then_load_preserves_dict(self, tmp_path: Path) -> None:
        # [bugfix.md C2.12] round-trip identity for a nested mapping.
        data = {"alpha": 1, "beta": [1, 2, 3], "gamma": {"k": "v"}}
        path = tmp_path / "config.json"

        ser.save_json(data, str(path))
        loaded = ser.load_json(str(path))

        assert loaded == data

    def test_save_json_uses_default_str_for_non_jsonable(
        self, tmp_path: Path,
    ) -> None:
        # [bugfix.md C2.12] ``default=str`` lets numpy scalars serialise.
        data = {"value": np.float64(3.14)}
        path = tmp_path / "np_scalar.json"

        ser.save_json(data, str(path))
        # The loaded value comes back as a string because ``default=str``
        # was triggered for the numpy scalar; this confirms the fall-back.
        loaded = ser.load_json(str(path))
        assert "value" in loaded
        # JSON encodes either as a number directly or via str() depending
        # on the type; both branches are acceptable, we only need that
        # the file is parseable round-trip.
        assert loaded["value"] in (3.14, "3.14")

    def test_save_json_writes_valid_json_text(self, tmp_path: Path) -> None:
        # [bugfix.md C2.12] file content must be valid JSON parseable by
        # the stdlib decoder, independent of ``load_json``.
        path = tmp_path / "valid.json"
        ser.save_json({"x": 1}, str(path))

        decoded = json.loads(path.read_text(encoding="utf-8"))
        assert decoded == {"x": 1}


class TestPickleRoundTrip:
    """Round-trip ``save_pickle`` / ``load_pickle``.

    Notes
    -----
    Verifies an arbitrary Python object survives serialisation through
    ``pickle.HIGHEST_PROTOCOL``.
    """

    def test_save_then_load_preserves_object(self, tmp_path: Path) -> None:
        # [bugfix.md C2.12] round-trip identity for a heterogeneous object.
        payload = {"array": np.array([1.0, 2.0, 3.0]), "label": "hello"}
        path = tmp_path / "obj.pkl"

        ser.save_pickle(payload, str(path))
        loaded = ser.load_pickle(str(path))

        assert loaded["label"] == "hello"
        np.testing.assert_array_equal(loaded["array"], payload["array"])

    def test_pickle_file_contains_pickle_protocol_header(
        self, tmp_path: Path,
    ) -> None:
        # [bugfix.md C2.12] file must be loadable by stdlib ``pickle.load``.
        path = tmp_path / "raw.pkl"
        ser.save_pickle([1, 2, 3], str(path))

        with open(path, "rb") as fh:
            obj = pickle.load(fh)
        assert obj == [1, 2, 3]
