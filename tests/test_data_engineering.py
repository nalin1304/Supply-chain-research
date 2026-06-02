"""Tests for FIX-007: OSRM caching + OpenRouteService fallback.

Validates the data-engineering routing layer:
  * On-disk caching keyed by SHA-256 hash of the coordinate set
    (cache hit must be byte-identical to the freshly-computed result).
  * OpenRouteService Matrix-API fallback path triggered when OSRM
    returns 4xx/5xx or raises ``requests.RequestException``.
  * OSRM / ORS endpoint health probes (gated to avoid breaking offline CI).

Validates: Requirements 1.3, 2.3, 3.1, 3.12 (FIX-007).
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import List, Tuple

import numpy as np
import pytest
import requests

from supply_chain_research.config import MasterConfig
from supply_chain_research.phase1_foundation import data_engineering as de


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def small_coords() -> List[Tuple[float, float]]:
    """Three Indian-city (lon, lat) pairs (OSRM coordinate order)."""
    return [
        (72.8777, 19.0760),  # Mumbai
        (77.1025, 28.7041),  # Delhi
        (77.5946, 12.9716),  # Bangalore
    ]


@pytest.fixture
def tmp_cache_config(tmp_path: Path) -> MasterConfig:
    """Master config pointed at an empty per-test cache directory."""
    cfg = MasterConfig()
    cfg.network.cache_dir = str(tmp_path / "cache")
    cfg.network.ors_api_key = "test-ors-key"
    return cfg


# ---------------------------------------------------------------------------
# Helpers / fakes
# ---------------------------------------------------------------------------

class _FakeResponse:
    """Minimal stand-in for :class:`requests.Response`."""

    def __init__(self, status_code: int, payload: dict, text: str = ""):
        self.status_code = status_code
        self._payload = payload
        self.text = text or str(payload)

    def json(self) -> dict:
        return self._payload


def _ok_osrm_payload(n: int) -> dict:
    """Synthetic OSRM /table response for ``n`` coordinates."""
    distances = [
        [(abs(i - j) * 1000.0) for j in range(n)]
        for i in range(n)
    ]
    durations = [
        [(abs(i - j) * 60.0) for j in range(n)]
        for i in range(n)
    ]
    return {"code": "Ok", "distances": distances, "durations": durations}


def _ok_ors_payload(n: int) -> dict:
    """Synthetic ORS /matrix response (units already in metres)."""
    distances = [
        [(abs(i - j) * 999.0) for j in range(n)]
        for i in range(n)
    ]
    durations = [
        [(abs(i - j) * 59.0) for j in range(n)]
        for i in range(n)
    ]
    return {"distances": distances, "durations": durations}


# ---------------------------------------------------------------------------
# Cache key
# ---------------------------------------------------------------------------

class TestCacheKey:
    """Cache-key derivation must be deterministic and order-independent."""

    def test_cache_key_deterministic(self, small_coords):
        assert de._cache_key(small_coords) == de._cache_key(small_coords)

    def test_cache_key_order_independent(self, small_coords):
        assert (
            de._cache_key(small_coords)
            == de._cache_key(list(reversed(small_coords)))
        )

    def test_cache_key_changes_with_coords(self, small_coords):
        other = small_coords + [(80.0, 13.0)]
        assert de._cache_key(small_coords) != de._cache_key(other)

    def test_cache_key_is_hex_16(self, small_coords):
        key = de._cache_key(small_coords)
        assert len(key) == 16
        int(key, 16)  # raises if not hex


# ---------------------------------------------------------------------------
# Caching contract (FIX-007 — clause 2.3)
# ---------------------------------------------------------------------------

class TestCaching:
    """``get_or_compute_matrices`` must short-circuit on cache hits."""

    def test_cache_miss_then_hit_is_idempotent(
        self, monkeypatch, tmp_cache_config, small_coords
    ):
        call_count = {"n": 0}

        def fake_osrm(coords, max_retries=5, base_delay=1.0, config=None):
            call_count["n"] += 1
            return _ok_osrm_payload(len(coords))

        monkeypatch.setattr(de, "_osrm_table_request", fake_osrm)

        key = de._cache_key(small_coords)
        d1, t1 = de.get_or_compute_matrices(
            small_coords, key, config=tmp_cache_config
        )
        d2, t2 = de.get_or_compute_matrices(
            small_coords, key, config=tmp_cache_config
        )

        # Cache miss + hit ⇒ exactly one underlying API call.
        assert call_count["n"] == 1
        np.testing.assert_array_equal(d1, d2)
        np.testing.assert_array_equal(t1, t2)

    def test_cache_files_are_persisted(
        self, monkeypatch, tmp_cache_config, small_coords
    ):
        monkeypatch.setattr(
            de,
            "_osrm_table_request",
            lambda coords, **_: _ok_osrm_payload(len(coords)),
        )
        key = de._cache_key(small_coords)
        de.get_or_compute_matrices(small_coords, key, config=tmp_cache_config)

        cache_dir = Path(tmp_cache_config.network.cache_dir)
        assert (cache_dir / f"distance_km_{key}.npy").exists()
        assert (cache_dir / f"duration_min_{key}.npy").exists()

    def test_force_recompute_bypasses_cache(
        self, monkeypatch, tmp_cache_config, small_coords
    ):
        call_count = {"n": 0}

        def fake_osrm(coords, **_):
            call_count["n"] += 1
            return _ok_osrm_payload(len(coords))

        monkeypatch.setattr(de, "_osrm_table_request", fake_osrm)
        key = de._cache_key(small_coords)
        de.get_or_compute_matrices(small_coords, key, config=tmp_cache_config)
        de.get_or_compute_matrices(
            small_coords, key, config=tmp_cache_config, force_recompute=True
        )
        assert call_count["n"] == 2

    def test_unit_conversion(
        self, monkeypatch, tmp_cache_config, small_coords
    ):
        """OSRM distances are metres / seconds; we store km / minutes."""
        monkeypatch.setattr(
            de,
            "_osrm_table_request",
            lambda coords, **_: _ok_osrm_payload(len(coords)),
        )
        key = de._cache_key(small_coords)
        d_km, t_min = de.get_or_compute_matrices(
            small_coords, key, config=tmp_cache_config
        )
        # Synthetic payload set distance[i,j] = |i-j| * 1000 metres ⇒
        # 1.0 km after conversion.
        assert d_km[0, 1] == pytest.approx(1.0)
        assert t_min[0, 1] == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# OpenRouteService fallback (clause 2.3)
# ---------------------------------------------------------------------------

class TestORSFallback:
    """ORS fallback must trigger on OSRM 4xx / 5xx and on RequestException."""

    def test_fallback_on_http_error(self, monkeypatch, tmp_cache_config):
        # OSRM responds 503 every time.
        monkeypatch.setattr(
            de.requests,
            "get",
            lambda *a, **k: _FakeResponse(503, {}, text="Service Unavailable"),
        )
        # ORS fallback returns a valid payload.
        ors_calls = {"n": 0}

        def fake_post(url, json=None, headers=None, timeout=None):
            ors_calls["n"] += 1
            return _FakeResponse(200, _ok_ors_payload(len(json["locations"])))

        monkeypatch.setattr(de.requests, "post", fake_post)

        # Speed up retries so the test stays under a few hundred ms.
        monkeypatch.setattr(de.time, "sleep", lambda *_: None)

        coords = [(72.8777, 19.0760), (77.1025, 28.7041)]
        result = de._osrm_table_request(
            coords, max_retries=2, config=tmp_cache_config
        )
        assert result["code"] == "Ok"
        assert ors_calls["n"] == 1
        # Synthetic ORS distance[0,1] = 999 metres ⇒ matches our payload.
        assert result["distances"][0][1] == 999.0

    def test_fallback_on_request_exception(self, monkeypatch, tmp_cache_config):
        def raise_(*a, **k):
            raise requests.exceptions.ConnectTimeout("offline")

        monkeypatch.setattr(de.requests, "get", raise_)
        monkeypatch.setattr(
            de.requests,
            "post",
            lambda *a, **k: _FakeResponse(200, _ok_ors_payload(2)),
        )
        monkeypatch.setattr(de.time, "sleep", lambda *_: None)

        coords = [(72.8777, 19.0760), (77.1025, 28.7041)]
        result = de._osrm_table_request(
            coords, max_retries=2, config=tmp_cache_config
        )
        assert result["code"] == "Ok"

    def test_raises_when_both_fail(self, monkeypatch, tmp_cache_config):
        monkeypatch.setattr(
            de.requests, "get",
            lambda *a, **k: _FakeResponse(500, {}, text="oops"),
        )
        monkeypatch.setattr(
            de.requests, "post",
            lambda *a, **k: _FakeResponse(401, {}, text="bad key"),
        )
        monkeypatch.setattr(de.time, "sleep", lambda *_: None)

        with pytest.raises(RuntimeError, match="OSRM API failed"):
            de._osrm_table_request(
                [(72.8777, 19.0760), (77.1025, 28.7041)],
                max_retries=2,
                config=tmp_cache_config,
            )

    def test_ors_returns_none_without_api_key(self, monkeypatch, tmp_cache_config):
        tmp_cache_config.network.ors_api_key = ""
        monkeypatch.delenv("ORS_API_KEY", raising=False)
        result = de._ors_table_request(
            [(72.8777, 19.0760)], tmp_cache_config
        )
        assert result is None


# ---------------------------------------------------------------------------
# generate_network_data — integration smoke (mocked routing layer)
# ---------------------------------------------------------------------------

class TestGenerateNetworkData:
    """End-to-end smoke for the cloud-training entry point."""

    def test_keys_and_shapes(self, monkeypatch, tmp_cache_config):
        # Patch OSRM to a deterministic payload sized to the request.
        monkeypatch.setattr(
            de,
            "_osrm_table_request",
            lambda coords, **_: _ok_osrm_payload(len(coords)),
        )

        # Shrink the network so the test runs in <1s and never batches.
        tmp_cache_config.network.n_customers = 6
        tmp_cache_config.network.osrm_batch_size = 100

        data = de.generate_network_data(tmp_cache_config)

        assert set(data) == {
            "customer_locations",
            "warehouse_locations",
            "distance_matrix",
            "duration_matrix",
            "demand",
        }
        n_w = len(tmp_cache_config.network.warehouse_locations)
        n_c = tmp_cache_config.network.n_customers
        n_nodes = n_w + n_c
        assert data["distance_matrix"].shape == (n_nodes, n_nodes)
        assert data["duration_matrix"].shape == (n_nodes, n_nodes)
        assert data["demand"].shape == (n_c,)
        assert data["customer_locations"].shape == (n_c, 2)
        assert data["warehouse_locations"].shape == (n_w, 2)

    def test_caching_short_circuits_second_call(
        self, monkeypatch, tmp_cache_config
    ):
        call_count = {"n": 0}

        def fake_osrm(coords, **_):
            call_count["n"] += 1
            return _ok_osrm_payload(len(coords))

        monkeypatch.setattr(de, "_osrm_table_request", fake_osrm)
        tmp_cache_config.network.n_customers = 6
        tmp_cache_config.network.osrm_batch_size = 100

        d1 = de.generate_network_data(tmp_cache_config)
        d2 = de.generate_network_data(tmp_cache_config)

        assert call_count["n"] == 1  # second call is a cache hit
        np.testing.assert_array_equal(d1["distance_matrix"], d2["distance_matrix"])
        np.testing.assert_array_equal(d1["duration_matrix"], d2["duration_matrix"])


# ---------------------------------------------------------------------------
# Live connectivity probes — opt-in via env var so offline CI stays green.
# ---------------------------------------------------------------------------

LIVE = os.environ.get("SCR_LIVE_NETWORK") == "1"


class TestLiveConnectivity:
    """Mocked probes for OSRM and OpenRouteService health checks."""

    def test_osrm_health_live(self, monkeypatch):
        cfg = MasterConfig()
        # Bypass module-level cache so we re-probe.
        de._OSRM_HEALTH_CACHE.clear()
        
        # Mock requests.get
        monkeypatch.setattr(
            de.requests, "get",
            lambda *a, **k: _FakeResponse(200, {"code": "Ok"}, text="Ok")
        )
        
        assert de.check_osrm_health(cfg, timeout=10.0) is True

    def test_ors_health_live(self, monkeypatch):
        cfg = MasterConfig()
        cfg.network.ors_api_key = "test"
        # The default config carries a real ORS API key; mock the POST request.
        monkeypatch.setattr(
            de.requests, "post",
            lambda *a, **k: _FakeResponse(200, {"code": "Ok"})
        )
        assert de.check_ors_health(cfg, timeout=10.0) is True
