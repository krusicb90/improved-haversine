"""Measure how far each way of estimating road distance is from the truth."""

from __future__ import annotations

import statistics
from collections.abc import Callable, Sequence
from typing import Any

from improved_haversine.core import band_index
from improved_haversine.table import FactorTable
from pipeline.factors import Trip

FIXED_FACTOR = 1.25


def _errors(trips: Sequence[Trip], estimate: Callable[[Trip], float]) -> dict[str, float]:
    """Absolute error of an estimate, as a percentage of the real road distance."""
    errors = sorted(abs(estimate(trip) - trip.road_km) / trip.road_km * 100 for trip in trips)
    return {
        "median_error_pct": round(statistics.median(errors), 2),
        "p90_error_pct": round(errors[min(len(errors) - 1, int(len(errors) * 0.9))], 2),
        "mean_error_pct": round(statistics.fmean(errors), 2),
    }


def evaluate(trips: Sequence[Trip], table: FactorTable) -> dict[str, Any]:
    """Compare five estimates on trips that were not used to build the table.

    haversine      the straight line, used as if it were the road distance
    fixed          the straight line times 1.25, a common rule of thumb
    single_factor  the straight line times one factor measured for the whole region
    band_factor    one factor per distance band, the same everywhere in the region
    improved       this library: a factor per grid cell and distance band

    band_factor is there to show how much of the gain comes from the distance
    and how much from the location.
    """
    if not trips:
        raise ValueError("no trips to evaluate on")
    single_factor = float(table.metadata["single_factor"])

    def band_factor(trip: Trip) -> float:
        return table.region_factor(band_index(trip.straight_km, table.bands_km)) or single_factor

    methods: dict[str, Callable[[Trip], float]] = {
        "haversine": lambda trip: trip.straight_km,
        "fixed": lambda trip: trip.straight_km * FIXED_FACTOR,
        "single_factor": lambda trip: trip.straight_km * single_factor,
        "band_factor": lambda trip: trip.straight_km * band_factor(trip),
        "improved": lambda trip: table.estimate(trip.lat1, trip.lon1, trip.lat2, trip.lon2).distance_km,
    }

    by_band: list[dict[str, Any]] = []
    lower = 0.0
    for index, upper in enumerate(table.bands_km):
        in_band = [trip for trip in trips if band_index(trip.straight_km, table.bands_km) == index]
        if in_band:
            by_band.append(
                {
                    "from_km": lower,
                    "to_km": upper,
                    "trips": len(in_band),
                    **{
                        name: _errors(in_band, method)["median_error_pct"] for name, method in methods.items()
                    },
                }
            )
        lower = upper

    sources = [table.estimate(trip.lat1, trip.lon1, trip.lat2, trip.lon2).source for trip in trips]
    return {
        "region": table.region,
        "trips": len(trips),
        "fixed_factor": FIXED_FACTOR,
        "single_factor": single_factor,
        "methods": {name: _errors(trips, method) for name, method in methods.items()},
        "median_error_pct_by_band": by_band,
        "improved_factor_source": {source: sources.count(source) for source in sorted(set(sources))},
    }
