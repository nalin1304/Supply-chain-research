"""Data engineering module for supply chain network generation.

Generates customer locations clustered around Indian cities,
defines warehouse locations, and computes road distance matrices
using OSRM Table API with on-disk caching and OpenRouteService fallback.

OSRM public demo server (router.project-osrm.org):
  - No official SLA; community-maintained, best-effort availability.
  - Usage policy requests max 1 req/s for heavy use (GitHub wiki, 2020).
  - Table API limited to ~100 coordinates per request.
  Reference: https://github.com/Project-OSRM/osrm-backend/wiki/Api-usage-policy
  Verified: 2024-2025 — endpoint remains community-maintained, demo only.

OpenRouteService (api.openrouteservice.org):
  - Free tier (2024-2025): 40 req/min, 2500 req/day, max 50x50 matrix.
  - Requires API key (sign up at https://openrouteservice.org/dev/).
  Reference: https://openrouteservice.org/restrictions/

FIX-007 (clause C1.3 → C2.3) — this module implements:
  1. Module-load OSRM endpoint health check (cached, opt-in via env var).
  2. On-disk caching of computed distance/duration matrices keyed by a
     SHA-256 hash of the coordinate set + profile, so repeat invocations
     are deterministic and offline-capable.
  3. OpenRouteService Matrix API fallback path that triggers when OSRM
     returns 4xx/5xx or raises ``requests.RequestException``.
"""

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import requests
from loguru import logger

from supply_chain_research.config import CFG, MasterConfig


# ---------------------------------------------------------------------------
# OSRM / ORS endpoint health check
# ---------------------------------------------------------------------------
# Module-level cache so the health probe runs at most once per process. The
# probe is gated behind ``SCR_OSRM_HEALTHCHECK=1`` because CI / offline test
# runs MUST NOT hit the network (clause C3.1: existing tests must continue
# to pass without external dependencies).
_OSRM_HEALTH_CACHE: Dict[str, bool] = {}


def check_osrm_health(
    config: Optional[MasterConfig] = None,
    timeout: float = 5.0,
) -> bool:
    """Probe the configured OSRM endpoint and report availability.

    Sends a single ``/nearest`` request against the configured OSRM base
    URL using a known-good Indian coordinate (Mumbai) so callers can
    decide whether to hit OSRM or fall back to OpenRouteService.

    Parameters
    ----------
    config : MasterConfig, optional
        Configuration. Uses :data:`CFG` if ``None``.
    timeout : float, optional
        HTTP timeout in seconds. Default 5.0.

    Returns
    -------
    bool
        ``True`` if OSRM responded with HTTP 200 and ``code == "Ok"``.

    References
    ----------
    .. [1] Project OSRM API usage policy (2020+),
           https://github.com/Project-OSRM/osrm-backend/wiki/Api-usage-policy
    """
    if config is None:
        config = CFG
    base = config.network.osrm_base_url
    if base in _OSRM_HEALTH_CACHE:
        return _OSRM_HEALTH_CACHE[base]
    url = f"{base}/nearest/v1/driving/72.8777,19.0760"
    try:
        resp = requests.get(url, timeout=timeout)
        ok = resp.status_code == 200 and resp.json().get("code") == "Ok"
    except requests.exceptions.RequestException as exc:
        logger.warning(f"OSRM health probe failed for {base}: {exc}")
        ok = False
    _OSRM_HEALTH_CACHE[base] = ok
    return ok


def check_ors_health(
    config: Optional[MasterConfig] = None,
    timeout: float = 5.0,
) -> bool:
    """Probe the configured OpenRouteService endpoint and report availability.

    Parameters
    ----------
    config : MasterConfig, optional
        Configuration. Uses :data:`CFG` if ``None``.
    timeout : float, optional
        HTTP timeout in seconds. Default 5.0.

    Returns
    -------
    bool
        ``True`` if ORS responded with HTTP 200 to a 2x2 probe.

    References
    ----------
    .. [1] OpenRouteService Restrictions (2024-2025),
           https://openrouteservice.org/restrictions/
    """
    if config is None:
        config = CFG
    api_key = config.network.ors_api_key or os.environ.get("ORS_API_KEY", "")
    if not api_key:
        return False
    headers = {"Authorization": api_key, "Content-Type": "application/json"}
    payload = {
        "locations": [[72.8777, 19.0760], [77.1025, 28.7041]],
        "metrics": ["distance"],
        "units": "m",
    }
    try:
        resp = requests.post(
            config.network.ors_base_url,
            json=payload,
            headers=headers,
            timeout=timeout,
        )
        return resp.status_code == 200
    except requests.exceptions.RequestException as exc:
        logger.warning(f"ORS health probe failed: {exc}")
        return False


# Run the health check at module load only when explicitly enabled, so the
# default offline test path remains deterministic (clause C3.1).
if os.environ.get("SCR_OSRM_HEALTHCHECK") == "1":
    try:
        _ok = check_osrm_health()
        logger.info(f"OSRM health check at module load: {'OK' if _ok else 'DOWN'}")
    except Exception as _exc:  # pragma: no cover - defensive
        logger.warning(f"OSRM health check raised at module load: {_exc}")


def generate_customer_locations(
    config: MasterConfig,
    rng: np.random.Generator = None,
) -> np.ndarray:
    """Generate customer locations clustered around Indian cities.

    Uses Gaussian perturbation around city centers to create
    realistic clustered demand points.

    Args:
        config: Master configuration.
        rng: Numpy random generator for reproducibility.

    Returns:
        Array of shape (n_customers, 2) with (latitude, longitude).
    """
    if rng is None:
        rng = np.random.default_rng(config.random_seed)

    n_customers = config.network.n_customers
    cities = config.network.cities
    n_cities = len(cities)

    # Assign customers to cities roughly equally
    customers_per_city = n_customers // n_cities
    remainder = n_customers % n_cities

    location_std = config.network.customer_location_std

    locations = []
    for i, (name, lat, lon) in enumerate(cities):
        n = customers_per_city + (1 if i < remainder else 0)
        # Gaussian perturbation: ~0.8 degree std (~89 km) per specification
        lat_perturb = rng.normal(0, location_std, size=n)
        lon_perturb = rng.normal(0, location_std, size=n)
        for j in range(n):
            locations.append((lat + lat_perturb[j], lon + lon_perturb[j]))

    return np.array(locations[:n_customers])


def get_warehouse_locations(config: MasterConfig) -> np.ndarray:
    """Get warehouse locations from config.

    Args:
        config: Master configuration.

    Returns:
        Array of shape (n_warehouses, 2) with (latitude, longitude).
    """
    warehouses = []
    for name, lat, lon in config.network.warehouse_locations:
        warehouses.append((lat, lon))
    return np.array(warehouses)


def _cache_key(coords: list) -> str:
    """Compute stable hash of coordinate list for cache filename.

    Parameters
    ----------
    coords : list of tuple
        List of (lat, lon) or (lon, lat) coordinate tuples.

    Returns
    -------
    str
        16-character hex hash string.
    """
    payload = json.dumps(sorted(coords), sort_keys=True).encode()
    return hashlib.sha256(payload).hexdigest()[:16]


def get_or_compute_matrices(
    all_coords: list,
    cache_key: str,
    config: MasterConfig = None,
    force_recompute: bool = False,
) -> Tuple[np.ndarray, np.ndarray]:
    """Return (distance_km, duration_min) matrices, using disk cache if available.

    Parameters
    ----------
    all_coords : list of tuple
        Node coordinates as (lon, lat) tuples (OSRM format).
    cache_key : str
        Unique identifier for this coordinate set.
    config : MasterConfig, optional
        Configuration. Uses global CFG if None.
    force_recompute : bool, optional
        If True, bypass cache and call API. Default False.

    Returns
    -------
    distance_km : np.ndarray of shape (n, n)
        Road distance matrix in kilometers.
    duration_min : np.ndarray of shape (n, n)
        Travel duration matrix in minutes.
    """
    if config is None:
        config = CFG

    cache_dir = Path(config.network.cache_dir)
    dist_cache_path = cache_dir / f"distance_km_{cache_key}.npy"
    dur_cache_path = cache_dir / f"duration_min_{cache_key}.npy"

    # Check cache
    if not force_recompute and dist_cache_path.exists() and dur_cache_path.exists():
        logger.info(f"Cache hit for key={cache_key}, loading from {cache_dir}")
        distance_km = np.load(str(dist_cache_path))
        duration_min = np.load(str(dur_cache_path))
        return distance_km, duration_min

    # Compute via OSRM (with ORS fallback handled inside _osrm_table_request)
    logger.info(f"Cache miss for key={cache_key}, computing via routing API")
    n_nodes = len(all_coords)

    distance_matrix = np.zeros((n_nodes, n_nodes))
    duration_matrix = np.zeros((n_nodes, n_nodes))

    batch_size = config.network.osrm_batch_size

    if n_nodes <= batch_size:
        data = _osrm_table_request(
            all_coords,
            max_retries=config.network.osrm_retry_max,
            base_delay=config.network.osrm_retry_backoff,
            config=config,
        )
        distance_matrix = np.array(data["distances"])
        duration_matrix = np.array(data["durations"])
    else:
        # Batch strategy for large coordinate sets. Ensure that the combined size of
        # any source and destination batch pair (src_indices + dst_indices) does not
        # exceed the OSRM maximum allowed coordinates in a single table call.
        effective_batch_size = max(5, batch_size // 2)
        n_batches = (n_nodes + effective_batch_size - 1) // effective_batch_size
        for src_batch_idx in range(n_batches):
            src_start = src_batch_idx * effective_batch_size
            src_end = min(src_start + effective_batch_size, n_nodes)
            src_indices = list(range(src_start, src_end))

            for dst_batch_idx in range(n_batches):
                dst_start = dst_batch_idx * effective_batch_size
                dst_end = min(dst_start + effective_batch_size, n_nodes)
                dst_indices = list(range(dst_start, dst_end))

                all_indices = sorted(set(src_indices + dst_indices))
                batch_coords = [all_coords[i] for i in all_indices]

                data = _osrm_table_request(
                    batch_coords,
                    max_retries=config.network.osrm_retry_max,
                    base_delay=config.network.osrm_retry_backoff,
                    config=config,
                )

                # Map original indices to batch indices
                idx_map = {orig: batch for batch, orig in enumerate(all_indices)}
                src_batch_mapped = [idx_map[i] for i in src_indices]
                dst_batch_mapped = [idx_map[i] for i in dst_indices]

                distances = np.array(data["distances"])
                durations = np.array(data["durations"])

                for si, src_orig in enumerate(src_indices):
                    for di, dst_orig in enumerate(dst_indices):
                        distance_matrix[src_orig, dst_orig] = distances[
                            src_batch_mapped[si], dst_batch_mapped[di]
                        ]
                        duration_matrix[src_orig, dst_orig] = durations[
                            src_batch_mapped[si], dst_batch_mapped[di]
                        ]

                # Rate limiting
                time.sleep(0.5)

    # Convert: distance meters → km, duration seconds → minutes
    distance_km = distance_matrix / 1000.0
    duration_min = duration_matrix / 60.0

    # Persist to cache
    cache_dir.mkdir(parents=True, exist_ok=True)
    np.save(str(dist_cache_path), distance_km)
    np.save(str(dur_cache_path), duration_min)
    logger.info(f"Cached matrices to {cache_dir} with key={cache_key}")

    return distance_km, duration_min


def _ors_table_request(
    coordinates: List[Tuple[float, float]],
    config: MasterConfig,
) -> Optional[dict]:
    """Call OpenRouteService Matrix API as fallback.

    Parameters
    ----------
    coordinates : list of tuple
        List of (longitude, latitude) tuples.
    config : MasterConfig
        Configuration containing ORS settings.

    Returns
    -------
    dict or None
        Response dict with 'distances' and 'durations' keys matching
        OSRM format, or None if ORS is not configured or fails.
    """
    api_key = config.network.ors_api_key or os.environ.get("ORS_API_KEY", "")
    if not api_key:
        return None

    ors_url = config.network.ors_base_url
    headers = {
        "Authorization": api_key,
        "Content-Type": "application/json",
    }

    # ORS expects locations as [[lon, lat], [lon, lat], ...]
    locations = [[lon, lat] for lon, lat in coordinates]

    payload = {
        "locations": locations,
        "metrics": ["distance", "duration"],
        "units": "m",
    }

    try:
        response = requests.post(ors_url, json=payload, headers=headers, timeout=120)
        if response.status_code == 200:
            data = response.json()
            # ORS returns 'distances' and 'durations' directly
            return {
                "distances": data.get("distances", []),
                "durations": data.get("durations", []),
                "code": "Ok",
            }
        else:
            logger.warning(
                f"ORS fallback HTTP {response.status_code}: "
                f"{response.text[:200]}"
            )
    except requests.exceptions.RequestException as e:
        logger.warning(f"ORS fallback request failed: {e}")

    return None


def _osrm_table_request(
    coordinates: List[Tuple[float, float]],
    max_retries: int = 5,
    base_delay: float = 1.0,
    config: MasterConfig = None,
) -> dict:
    """Call OSRM Table API with exponential backoff retry and ORS fallback.

    Attempts the OSRM public demo server first. If all retries are exhausted
    and an OpenRouteService API key is configured, falls back to ORS.

    Parameters
    ----------
    coordinates : list of tuple
        List of (longitude, latitude) tuples.
    max_retries : int, optional
        Maximum number of retry attempts for OSRM. Default 5.
    base_delay : float, optional
        Base delay for exponential backoff in seconds. Default 1.0.
    config : MasterConfig, optional
        Configuration. Uses global CFG if None.

    Returns
    -------
    dict
        JSON response with 'distances' and 'durations' keys.

    Raises
    ------
    RuntimeError
        If both OSRM and ORS fallback fail.
    """
    if config is None:
        config = CFG

    # Build coordinate string: lon,lat;lon,lat;...
    coord_str = ";".join(
        f"{lon:.6f},{lat:.6f}" for lon, lat in coordinates
    )
    osrm_base = config.network.osrm_base_url
    url = (
        f"{osrm_base}/table/v1/driving/{coord_str}"
        f"?annotations=distance,duration"
    )

    for attempt in range(max_retries):
        try:
            response = requests.get(url, timeout=120)
            if response.status_code == 200:
                data = response.json()
                if data.get("code") == "Ok":
                    return data
                else:
                    logger.warning(
                        f"OSRM returned code: {data.get('code')}, "
                        f"attempt {attempt + 1}/{max_retries}"
                    )
            else:
                logger.warning(
                    f"OSRM HTTP {response.status_code}, "
                    f"attempt {attempt + 1}/{max_retries}"
                )
        except requests.exceptions.RequestException as e:
            logger.warning(
                f"OSRM request failed: {e}, "
                f"attempt {attempt + 1}/{max_retries}"
            )

        if attempt < max_retries - 1:
            delay = base_delay * (2 ** attempt)
            logger.info(f"Retrying in {delay:.1f}s...")
            time.sleep(delay)

    # OSRM exhausted — try ORS fallback
    logger.warning("OSRM failed after all retries, attempting ORS fallback...")
    ors_result = _ors_table_request(coordinates, config)
    if ors_result is not None:
        logger.info("ORS fallback succeeded")
        return ors_result

    raise RuntimeError(
        f"OSRM API failed after {max_retries} attempts and ORS fallback "
        f"unavailable (no API key configured or ORS request failed)"
    )


def compute_distance_matrix(
    config: MasterConfig,
    customer_locations: np.ndarray = None,
    batch_size: int = 50,
) -> Tuple[np.ndarray, np.ndarray]:
    """Compute road distance and duration matrices using OSRM with caching.

    Combines warehouse and customer locations and delegates to
    :func:`get_or_compute_matrices`, which provides on-disk caching keyed
    by a SHA-256 hash of the coordinate set and an OpenRouteService
    fallback path triggered on OSRM 4xx/5xx or
    :class:`requests.RequestException`.

    Parameters
    ----------
    config : MasterConfig
        Master configuration.
    customer_locations : np.ndarray, optional
        Customer coordinates as ``(lat, lon)``. If ``None``, generates
        them via :func:`generate_customer_locations`.
    batch_size : int, optional
        Max nodes per OSRM request. Default 50.

    Returns
    -------
    distance_matrix_km : np.ndarray
        Road distance matrix in kilometers, shape ``(n_nodes, n_nodes)``.
    duration_matrix_s : np.ndarray
        Travel-duration matrix in **seconds** (legacy unit), shape
        ``(n_nodes, n_nodes)``.

    Notes
    -----
    The returned ``duration`` array is in seconds for backwards
    compatibility with prior call sites. ``get_or_compute_matrices`` returns
    minutes; this wrapper multiplies by 60 to recover seconds.
    """
    if customer_locations is None:
        customer_locations = generate_customer_locations(config)

    warehouse_locations = get_warehouse_locations(config)

    # Combine: warehouses first, then customers
    all_locations = np.vstack([warehouse_locations, customer_locations])
    n_nodes = len(all_locations)

    # Validate coordinates are within India bounds (lat 8-37, lon 68-97)
    lat_bounds = config.network.india_lat_bounds
    lon_bounds = config.network.india_lon_bounds
    for idx, (lat, lon) in enumerate(all_locations):
        if not (lat_bounds[0] <= lat <= lat_bounds[1]):
            logger.warning(
                f"Node {idx} latitude {lat:.4f} outside India bounds "
                f"{lat_bounds}"
            )
        if not (lon_bounds[0] <= lon <= lon_bounds[1]):
            logger.warning(
                f"Node {idx} longitude {lon:.4f} outside India bounds "
                f"{lon_bounds}"
            )

    # Convert from (latitude, longitude) to (longitude, latitude) for OSRM.
    # OSRM API expects coordinates in (lon, lat) order, but our internal
    # representation stores locations as (lat, lon).
    all_coords = [
        (float(row[1]), float(row[0])) for row in all_locations
    ]

    logger.info(
        f"Computing {n_nodes}x{n_nodes} distance matrix "
        f"with batch_size={batch_size} via cached routing layer"
    )

    # Honour the caller-supplied batch_size (legacy API) by overriding the
    # NetworkConfig default for the duration of this call. Cache key is a
    # deterministic hash of the coordinate set so repeated invocations are
    # offline-capable.
    cfg = config.network
    saved_batch = cfg.osrm_batch_size
    cfg.osrm_batch_size = batch_size
    try:
        cache_key = _cache_key(all_coords)
        distance_km, duration_min = get_or_compute_matrices(
            all_coords, cache_key, config=config
        )
    finally:
        cfg.osrm_batch_size = saved_batch

    # Legacy contract: duration in seconds.
    duration_matrix_s = duration_min * 60.0

    return distance_km, duration_matrix_s


def generate_network_data(
    config: MasterConfig,
    rng: np.random.Generator = None,
) -> Dict[str, np.ndarray]:
    """Generate the full Phase-1 network artifact bundle.

    Single-call helper used by the cloud-training scaffold and the Phase-4
    complexity-analysis profiler. Builds customer locations and demand,
    fetches warehouse locations, and computes the distance / duration
    matrices through the cached routing layer.

    Parameters
    ----------
    config : MasterConfig
        Master configuration.
    rng : numpy.random.Generator, optional
        RNG used for customer placement and demand sampling. If ``None``,
        a generator is created from :attr:`config.random_seed` so the
        result is fully deterministic.

    Returns
    -------
    dict
        Keys:

        - ``"customer_locations"`` : ndarray, ``(n_customers, 2)``,
          ``(lat, lon)``.
        - ``"warehouse_locations"`` : ndarray, ``(n_warehouses, 2)``,
          ``(lat, lon)``.
        - ``"distance_matrix"`` : ndarray, ``(n_nodes, n_nodes)``,
          kilometres.
        - ``"duration_matrix"`` : ndarray, ``(n_nodes, n_nodes)``,
          seconds.
        - ``"demand"`` : ndarray, ``(n_customers,)``, kilograms.

    References
    ----------
    .. [1] Project OSRM API usage policy,
           https://github.com/Project-OSRM/osrm-backend/wiki/Api-usage-policy
    .. [2] OpenRouteService Restrictions (2024-2025),
           https://openrouteservice.org/restrictions/
    """
    if rng is None:
        rng = np.random.default_rng(config.random_seed)

    customer_locations = generate_customer_locations(config, rng=rng)
    warehouse_locations = get_warehouse_locations(config)
    demand = generate_demand(config, rng=rng)
    distance_matrix, duration_matrix = compute_distance_matrix(
        config,
        customer_locations=customer_locations,
        batch_size=config.network.osrm_batch_size,
    )

    return {
        "customer_locations": customer_locations,
        "warehouse_locations": warehouse_locations,
        "distance_matrix": distance_matrix,
        "duration_matrix": duration_matrix,
        "demand": demand,
    }


def generate_demand(
    config: MasterConfig,
    rng: np.random.Generator = None,
) -> np.ndarray:
    """Generate demand for each customer.

    Uses a LogNormal distribution whose location and scale parameters
    are read from
    :pyattr:`SimulationConfig.order_size_mu` and
    :pyattr:`SimulationConfig.order_size_sigma`. Defaults
    (``mu=6.44``, ``sigma=0.97``) are calibrated against the DataCo
    Smart Supply Chain dataset (Constante et al., 2019; ~180k orders,
    ~20k customers) and produce a per-customer median of
    ``exp(6.44) ~ 626`` kg with a thick right tail.

    Parameters
    ----------
    config : MasterConfig
        Master configuration.
    rng : numpy.random.Generator, optional
        Numpy random generator. Uses ``default_rng(config.random_seed)``
        when ``None``.

    Returns
    -------
    numpy.ndarray
        Array of shape ``(n_customers,)`` with demand in kg, clipped
        to ``[demand_clip_min, demand_clip_max]`` per
        :class:`NetworkConfig`.
    """
    if rng is None:
        rng = np.random.default_rng(config.random_seed)

    n_customers = config.network.n_customers
    # LogNormal demand with DataCo-calibrated (mu, sigma) parameters
    # [Constante et al. 2019 — DataCo Smart Supply Chain Big Data
    #  dataset; FIX-002 centralisation].
    demand = rng.lognormal(
        mean=config.simulation.order_size_mu,
        sigma=config.simulation.order_size_sigma,
        size=n_customers,
    )
    # Clip to sanity bounds (no arbitrary scaling needed)
    demand = np.clip(
        demand,
        config.network.demand_clip_min,
        config.network.demand_clip_max,
    )
    return demand


def save_data(
    distance_matrix: np.ndarray,
    duration_matrix: np.ndarray,
    customer_locations: np.ndarray,
    warehouse_locations: np.ndarray,
    demand: np.ndarray,
    output_dir: str = "data/processed",
) -> None:
    """Save all generated data to disk.

    Parameters
    ----------
    distance_matrix : np.ndarray
        Distance matrix in km, shape ``(n_warehouses, n_customers)``.
    duration_matrix : np.ndarray
        Duration matrix in seconds, same shape as ``distance_matrix``.
    customer_locations : np.ndarray
        Array of customer ``(lat, lon)`` coordinates,
        shape ``(n_customers, 2)``.
    warehouse_locations : np.ndarray
        Array of warehouse ``(lat, lon)`` coordinates,
        shape ``(n_warehouses, 2)``.
    demand : np.ndarray
        Per-customer demand (kg), shape ``(n_customers,)``.
    output_dir : str, optional
        Output directory path. Defaults to ``"data/processed"``.

    Returns
    -------
    None
        Writes ``.npy`` files to ``output_dir`` in place.
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    np.save(str(output_path / "distance_matrix_km.npy"), distance_matrix)
    np.save(str(output_path / "duration_matrix_s.npy"), duration_matrix)
    np.save(
        str(output_path / "customer_locations.npy"), customer_locations
    )
    np.save(
        str(output_path / "warehouse_locations.npy"), warehouse_locations
    )
    np.save(str(output_path / "demand_kg.npy"), demand)

    logger.info(f"Data saved to {output_path}")
