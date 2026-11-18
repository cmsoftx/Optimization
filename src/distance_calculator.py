"""Distance utilities.

Phase 1 needs only great-circle (Haversine) distance for coordinate screening.
Road-network distances (OSRM) are added in the warehouse-optimisation phase.

IMPORTANT: Haversine distance is a straight-line approximation on a sphere.
It underestimates road travel distance and must be labelled as such wherever
it is reported.
"""
from __future__ import annotations

import numpy as np

EARTH_RADIUS_KM = 6371.0088  # IUGG mean Earth radius


def haversine_km(lat1, lon1, lat2, lon2) -> np.ndarray:
    """Vectorised great-circle distance in kilometres (broadcasts like NumPy)."""
    lat1, lon1, lat2, lon2 = (np.radians(np.asarray(a, dtype=float)) for a in (lat1, lon1, lat2, lon2))
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2.0) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2.0) ** 2
    return 2.0 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))


def haversine_matrix(lat_a, lon_a, lat_b, lon_b) -> np.ndarray:
    """Pairwise Haversine matrix of shape (len(a), len(b)) in kilometres."""
    lat_a = np.asarray(lat_a, dtype=float)[:, None]
    lon_a = np.asarray(lon_a, dtype=float)[:, None]
    lat_b = np.asarray(lat_b, dtype=float)[None, :]
    lon_b = np.asarray(lon_b, dtype=float)[None, :]
    return haversine_km(lat_a, lon_a, lat_b, lon_b)


def road_distance_matrix(lat_a, lon_a, lat_b, lon_b, circuity_factor: float | None = None) -> np.ndarray:
    """Approximate road distance (km) = great-circle distance x circuity factor.

    This is NOT a road-network distance. OSRM was not reachable from the
    execution environment, and sending zone coordinates to an external router
    was avoided for privacy. The circuity factor (default from config) corrects
    the systematic under-estimate of straight-line distance. Every output that
    uses it is labelled ``distance_method = haversine_circuity``.
    """
    if circuity_factor is None:
        from .config import load_config
        circuity_factor = load_config()["optimization"]["distance"]["circuity_factor"]
    return haversine_matrix(lat_a, lon_a, lat_b, lon_b) * float(circuity_factor)


DISTANCE_METHOD_LABEL = "haversine_circuity (approximate road km; not a road-network distance)"
