"""A small client for the two OSRM services the pipeline needs."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class Snap:
    """A point moved onto the nearest road, and how far it was moved."""

    lat: float
    lon: float
    moved_m: float


class Router(Protocol):
    """What the pipeline needs from a routing engine. Tests supply a fake one."""

    def nearest(self, lat: float, lon: float) -> Snap | None: ...

    def road_distances_km(
        self, origin: tuple[float, float], destinations: list[tuple[float, float]]
    ) -> list[float | None]: ...


class OsrmRouter:
    """Talks to an OSRM server over HTTP."""

    def __init__(
        self, base_url: str, profile: str = "driving", timeout: float = 30, retries: int = 3
    ) -> None:
        if not base_url.startswith(("http://", "https://")):
            raise ValueError("base_url must start with http:// or https://")
        self.base_url = base_url.rstrip("/")
        self.profile = profile
        self.timeout = timeout
        self.retries = retries

    def _get(self, path: str, query: dict[str, str]) -> dict[str, Any]:
        url = f"{self.base_url}{path}?{urllib.parse.urlencode(query, safe=';,')}"
        last_error: Exception | None = None
        for attempt in range(self.retries):
            try:
                # The scheme was checked in __init__.
                with urllib.request.urlopen(url, timeout=self.timeout) as response:  # noqa: S310
                    return json.load(response)
            except urllib.error.HTTPError as error:
                # OSRM answers 400 with a JSON body for "no route" and similar. That is a
                # result, not a failure.
                if error.code == 400:
                    return json.load(error)
                last_error = error
            except (urllib.error.URLError, TimeoutError) as error:
                last_error = error
            time.sleep(0.5 * (attempt + 1))
        raise RuntimeError(f"OSRM request failed after {self.retries} attempts: {url}") from last_error

    def nearest(self, lat: float, lon: float) -> Snap | None:
        body = self._get(f"/nearest/v1/{self.profile}/{lon:.6f},{lat:.6f}", {"number": "1"})
        if body.get("code") != "Ok" or not body.get("waypoints"):
            return None
        waypoint = body["waypoints"][0]
        snapped_lon, snapped_lat = waypoint["location"]
        return Snap(lat=snapped_lat, lon=snapped_lon, moved_m=float(waypoint["distance"]))

    def road_distances_km(
        self, origin: tuple[float, float], destinations: list[tuple[float, float]]
    ) -> list[float | None]:
        if not destinations:
            return []
        points = [origin, *destinations]
        coordinates = ";".join(f"{lon:.6f},{lat:.6f}" for lat, lon in points)
        body = self._get(
            f"/table/v1/{self.profile}/{coordinates}",
            {
                "annotations": "distance",
                "sources": "0",
                "destinations": ";".join(str(index) for index in range(1, len(points))),
            },
        )
        if body.get("code") != "Ok":
            return [None] * len(destinations)
        return [None if metres is None else metres / 1000 for metres in body["distances"][0]]
