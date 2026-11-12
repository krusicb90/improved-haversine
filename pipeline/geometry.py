"""Sampling helpers: grid cells and points at a given distance."""

from __future__ import annotations

import math
import random

from improved_haversine.core import EARTH_RADIUS_KM

Bbox = tuple[float, float, float, float]  # west, south, east, north


def in_bbox(lat: float, lon: float, bbox: Bbox) -> bool:
    west, south, east, north = bbox
    return south <= lat <= north and west <= lon <= east


def cells_in_bbox(bbox: Bbox, cell_size_deg: float) -> list[tuple[int, int]]:
    """Grid cells that overlap the bounding box, as (latitude index, longitude index)."""
    west, south, east, north = bbox
    lat_range = range(math.floor(south / cell_size_deg), math.floor(north / cell_size_deg) + 1)
    lon_range = range(math.floor(west / cell_size_deg), math.floor(east / cell_size_deg) + 1)
    return [(lat_index, lon_index) for lat_index in lat_range for lon_index in lon_range]


def random_point_in_cell(
    rng: random.Random, cell: tuple[int, int], cell_size_deg: float
) -> tuple[float, float]:
    lat_index, lon_index = cell
    return (
        (lat_index + rng.random()) * cell_size_deg,
        (lon_index + rng.random()) * cell_size_deg,
    )


def destination_point(lat: float, lon: float, bearing_deg: float, distance_km: float) -> tuple[float, float]:
    """The point reached by travelling a distance along a great circle."""
    delta = distance_km / EARTH_RADIUS_KM
    theta = math.radians(bearing_deg)
    phi1, lambda1 = math.radians(lat), math.radians(lon)

    sin_phi2 = math.sin(phi1) * math.cos(delta) + math.cos(phi1) * math.sin(delta) * math.cos(theta)
    phi2 = math.asin(max(-1.0, min(1.0, sin_phi2)))
    lambda2 = lambda1 + math.atan2(
        math.sin(theta) * math.sin(delta) * math.cos(phi1),
        math.cos(delta) - math.sin(phi1) * math.sin(phi2),
    )
    return math.degrees(phi2), (math.degrees(lambda2) + 540) % 360 - 180
