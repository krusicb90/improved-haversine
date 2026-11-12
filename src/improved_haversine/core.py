"""Geometry shared by the library and the pipeline that computes the factors."""

from __future__ import annotations

import math
from collections.abc import Sequence

# Mean Earth radius (IUGG).
EARTH_RADIUS_KM = 6371.0088


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two points, in kilometres."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = phi2 - phi1
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(a)))


def cell_key(lat: float, lon: float, cell_size_deg: float) -> str:
    """Key of the grid cell that contains a point.

    The grid is a plain latitude/longitude grid, so any language can compute
    the key with two divisions and needs no geospatial library.
    """
    return f"{math.floor(lat / cell_size_deg)}:{math.floor(lon / cell_size_deg)}"


def band_index(distance_km: float, bands_km: Sequence[float]) -> int:
    """Index of the distance band a straight-line distance falls into.

    ``bands_km`` holds the upper bound of each band. A distance beyond the last
    bound uses the last band.
    """
    for index, upper in enumerate(bands_km):
        if distance_km <= upper:
            return index
    return len(bands_km) - 1
