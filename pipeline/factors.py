"""Sample trips on the road network and turn them into a factor table."""

from __future__ import annotations

import random
import statistics
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from improved_haversine.core import band_index, cell_key, haversine_km
from improved_haversine.table import SCHEMA_VERSION
from pipeline.geometry import Bbox, cells_in_bbox, destination_point, in_bbox, random_point_in_cell
from pipeline.osrm import Router

# Below this the ratio says more about where a point was snapped than about the roads.
MIN_TRIP_KM = 0.5
# A sampled point further than this from any road is in water or wilderness. Nobody asks for a
# distance from there, so it must not shape the factor.
MAX_SNAP_M = 500.0
# A road distance many times the straight line is a ferry, a closed bridge or a data error.
MAX_RATIO = 8.0


@dataclass(frozen=True)
class Trip:
    """One sampled trip between two points on the road network."""

    lat1: float
    lon1: float
    lat2: float
    lon2: float
    straight_km: float
    road_km: float

    @property
    def ratio(self) -> float:
        return self.road_km / self.straight_km


def _snap(router: Router, lat: float, lon: float, bbox: Bbox) -> tuple[float, float] | None:
    snap = router.nearest(lat, lon)
    if snap is None or snap.moved_m > MAX_SNAP_M or not in_bbox(snap.lat, snap.lon, bbox):
        return None
    return snap.lat, snap.lon


def sample_trips(
    router: Router,
    bbox: Bbox,
    cell_size_deg: float,
    bands_km: Sequence[float],
    origins_per_cell: int,
    destinations_per_band: int,
    rng: random.Random,
) -> list[Trip]:
    """Sample trips that start in every grid cell and cover every distance band.

    Each origin is a random point in its cell, moved onto the nearest road. For
    every band, destinations are placed at a random bearing and a random
    distance inside the band, then moved onto the road network as well.
    """
    trips: list[Trip] = []
    for cell in cells_in_bbox(bbox, cell_size_deg):
        origins: list[tuple[float, float]] = []
        for _ in range(origins_per_cell * 4):
            if len(origins) == origins_per_cell:
                break
            origin = _snap(router, *random_point_in_cell(rng, cell, cell_size_deg), bbox)
            if origin is not None:
                origins.append(origin)

        for origin in origins:
            lower = MIN_TRIP_KM
            for upper in bands_km:
                destinations: list[tuple[float, float]] = []
                for _ in range(destinations_per_band):
                    target = destination_point(*origin, rng.uniform(0, 360), rng.uniform(lower, upper))
                    if not in_bbox(*target, bbox):
                        continue
                    destination = _snap(router, *target, bbox)
                    if destination is not None:
                        destinations.append(destination)

                for destination, road_km in zip(
                    destinations, router.road_distances_km(origin, destinations), strict=True
                ):
                    straight_km = haversine_km(*origin, *destination)
                    if road_km is None or straight_km < MIN_TRIP_KM:
                        continue
                    trip = Trip(*origin, *destination, straight_km=straight_km, road_km=road_km)
                    # A road cannot be shorter than the straight line. The tolerance covers rounding.
                    if 0.999 <= trip.ratio <= MAX_RATIO:
                        trips.append(trip)
                lower = upper
    return trips


def _median(values: list[float], min_samples: int) -> float | None:
    return round(statistics.median(values), 3) if len(values) >= min_samples else None


def build_table(
    trips: Sequence[Trip],
    region: str,
    bbox: Bbox,
    cell_size_deg: float,
    bands_km: Sequence[float],
    min_samples: int,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Aggregate trips into the factor table the library reads.

    The factor is the median ratio of road distance to straight-line distance.
    A trip counts for the cell it starts in and the cell it ends in, because
    the library averages the factors of both ends.
    """
    if not trips:
        raise ValueError("no trips were sampled, so there is nothing to build a table from")

    by_band: dict[int, list[float]] = defaultdict(list)
    by_cell: dict[str, dict[int, list[float]]] = defaultdict(lambda: defaultdict(list))
    for trip in trips:
        band = band_index(trip.straight_km, bands_km)
        by_band[band].append(trip.ratio)
        for key in {
            cell_key(trip.lat1, trip.lon1, cell_size_deg),
            cell_key(trip.lat2, trip.lon2, cell_size_deg),
        }:
            by_cell[key][band].append(trip.ratio)

    bands = range(len(bands_km))
    cells = {
        key: [_median(by_cell[key][band], min_samples) for band in bands]
        for key in sorted(by_cell)
        if any(len(by_cell[key][band]) >= min_samples for band in bands)
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "region": region,
        **(metadata or {}),
        "bbox": list(bbox),
        "cell_size_deg": cell_size_deg,
        "bands_km": list(bands_km),
        "min_samples": min_samples,
        "trips": len(trips),
        "single_factor": round(statistics.median(trip.ratio for trip in trips), 3),
        "default": [_median(by_band[band], min_samples) for band in bands],
        "cells": cells,
        "samples": {key: [len(by_cell[key][band]) for band in bands] for key in cells},
    }
