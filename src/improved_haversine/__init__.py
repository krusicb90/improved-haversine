"""Road distance estimates from coordinates alone.

The Haversine formula gives the distance in a straight line. Roads are longer,
and how much longer depends on where you are and how far you go. This package
multiplies the straight-line distance by a correction factor that was measured
for that area and that distance range on the real road network.
"""

from improved_haversine.core import EARTH_RADIUS_KM, band_index, cell_key, haversine_km
from improved_haversine.table import (
    DEFAULT_FALLBACK_FACTOR,
    Estimate,
    FactorTable,
    available_regions,
    road_distance_km,
)

__all__ = [
    "DEFAULT_FALLBACK_FACTOR",
    "EARTH_RADIUS_KM",
    "Estimate",
    "FactorTable",
    "available_regions",
    "band_index",
    "cell_key",
    "haversine_km",
    "road_distance_km",
]

__version__ = "0.1.0"
