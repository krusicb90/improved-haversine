"""Correction factors for one region, and the estimate built on them."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import cache
from importlib import resources
from pathlib import Path
from typing import Any

from improved_haversine.core import band_index, cell_key, haversine_km

SCHEMA_VERSION = 1

# Used when neither point lies in the region the factors were measured for.
DEFAULT_FALLBACK_FACTOR = 1.25


@dataclass(frozen=True)
class Estimate:
    """An estimated road distance and how it was obtained.

    ``source`` says where the factor came from:
      cell      measured for the grid cell of at least one of the points
      region    the region-wide factor for that distance band
      fallback  neither point is inside the region, a fixed factor was used
    """

    distance_km: float
    haversine_km: float
    factor: float
    source: str


class FactorTable:
    """Correction factors of one region, by grid cell and distance band."""

    def __init__(self, data: dict[str, Any]) -> None:
        if data.get("schema_version") != SCHEMA_VERSION:
            raise ValueError(f"unsupported schema_version: {data.get('schema_version')!r}")
        for field in ("region", "cell_size_deg", "bands_km", "bbox", "default", "cells"):
            if field not in data:
                raise ValueError(f"factor table has no {field!r}")
        if len(data["default"]) != len(data["bands_km"]):
            raise ValueError("'default' must have one factor per distance band")

        self.region: str = data["region"]
        self.cell_size_deg: float = float(data["cell_size_deg"])
        self.bands_km: list[float] = [float(bound) for bound in data["bands_km"]]
        self.bbox: tuple[float, float, float, float] = tuple(data["bbox"])  # west, south, east, north
        self.default: list[float | None] = list(data["default"])
        self.cells: dict[str, list[float | None]] = data["cells"]
        self.metadata: dict[str, Any] = {
            key: value for key, value in data.items() if key not in ("cells", "samples")
        }

    @classmethod
    def load(cls, region: str) -> FactorTable:
        """Load the factors of a region shipped with the package, for example ``us-ct``."""
        resource = resources.files("improved_haversine").joinpath("data", f"{region}.json")
        if not resource.is_file():
            raise ValueError(f"no factors for region {region!r}. Available: {', '.join(available_regions())}")
        return cls(json.loads(resource.read_text(encoding="utf-8")))

    @classmethod
    def from_file(cls, path: str | Path) -> FactorTable:
        """Load factors from a JSON file produced by the pipeline."""
        return cls(json.loads(Path(path).read_text(encoding="utf-8")))

    def covers(self, lat: float, lon: float) -> bool:
        """Whether a point lies inside the bounding box of the region."""
        west, south, east, north = self.bbox
        return south <= lat <= north and west <= lon <= east

    def _cell_factor(self, lat: float, lon: float, band: int) -> float | None:
        factors = self.cells.get(cell_key(lat, lon, self.cell_size_deg))
        return factors[band] if factors else None

    def region_factor(self, band: int) -> float | None:
        """The region-wide factor of a distance band.

        A band without enough samples borrows from the nearest shorter band.
        Detours shrink with distance, so this overestimates slightly.
        """
        for index in range(band, -1, -1):
            if self.default[index] is not None:
                return self.default[index]
        return next((factor for factor in self.default if factor is not None), None)

    def estimate(
        self,
        lat1: float,
        lon1: float,
        lat2: float,
        lon2: float,
        fallback_factor: float = DEFAULT_FALLBACK_FACTOR,
    ) -> Estimate:
        """Estimate the road distance between two points.

        The result is the same in both directions.
        """
        straight = haversine_km(lat1, lon1, lat2, lon2)
        band = band_index(straight, self.bands_km)

        measured = [
            factor
            for factor in (self._cell_factor(lat1, lon1, band), self._cell_factor(lat2, lon2, band))
            if factor is not None
        ]
        if measured:
            factor, source = sum(measured) / len(measured), "cell"
        elif (self.covers(lat1, lon1) or self.covers(lat2, lon2)) and self.region_factor(band) is not None:
            factor, source = self.region_factor(band), "region"
        else:
            factor, source = fallback_factor, "fallback"

        return Estimate(distance_km=straight * factor, haversine_km=straight, factor=factor, source=source)


def available_regions() -> list[str]:
    """Regions whose factors ship with the package."""
    data_dir = resources.files("improved_haversine").joinpath("data")
    return sorted(entry.name[: -len(".json")] for entry in data_dir.iterdir() if entry.name.endswith(".json"))


@cache
def _cached_table(region: str) -> FactorTable:
    return FactorTable.load(region)


def road_distance_km(lat1: float, lon1: float, lat2: float, lon2: float, region: str) -> float:
    """Estimated road distance in kilometres, using the factors of ``region``.

    The factor table is read once and kept in memory.
    """
    return _cached_table(region).estimate(lat1, lon1, lat2, lon2).distance_km
