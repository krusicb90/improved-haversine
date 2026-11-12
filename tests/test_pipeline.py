"""The pipeline, run end to end against a made-up road network.

No routing engine is needed. The fake world has two halves with known
detours, so the tests can check that the pipeline finds them.
"""

import math
import random

import pytest

from improved_haversine import FactorTable, cell_key, haversine_km
from pipeline.evaluate import evaluate
from pipeline.factors import MAX_SNAP_M, MIN_TRIP_KM, Trip, build_table, sample_trips
from pipeline.geometry import cells_in_bbox, destination_point, in_bbox, random_point_in_cell
from pipeline.osrm import Snap

BBOX = (-73.0, 41.0, -72.0, 42.0)  # west, south, east, north
CELL = 0.25
BANDS = [5, 20, 60]
MIDDLE = -72.5
KM_PER_DEGREE = 111.195


class FakeRouter:
    """West of the middle is a street grid, east of it roads are almost straight.

    The southern strip is water: points there are far from any road.
    """

    EAST_DETOUR = 1.10
    WATER_BELOW = 41.05

    def nearest(self, lat, lon):
        if lat < self.WATER_BELOW:
            moved_m = (self.WATER_BELOW - lat) * KM_PER_DEGREE * 1000
            return Snap(lat=self.WATER_BELOW, lon=lon, moved_m=moved_m)
        return Snap(lat=lat, lon=lon, moved_m=0.0)

    def road_distances_km(self, origin, destinations):
        return [self._road_km(origin, destination) for destination in destinations]

    def _road_km(self, a, b):
        if a[1] < MIDDLE and b[1] < MIDDLE:
            # A street grid: go along the latitude, then along the longitude.
            north_south = abs(a[0] - b[0]) * KM_PER_DEGREE
            east_west = abs(a[1] - b[1]) * KM_PER_DEGREE * math.cos(math.radians((a[0] + b[0]) / 2))
            return max(north_south + east_west, haversine_km(*a, *b))
        return haversine_km(*a, *b) * self.EAST_DETOUR


@pytest.fixture(scope="module")
def trips():
    return sample_trips(FakeRouter(), BBOX, CELL, BANDS, 40, 6, random.Random(1))


@pytest.fixture(scope="module")
def table(trips):
    return FactorTable(build_table(trips, "fake", BBOX, CELL, BANDS, min_samples=20))


# --- geometry --------------------------------------------------------------


@pytest.mark.parametrize("bearing", [0, 45, 90, 200, 359])
@pytest.mark.parametrize("distance", [0.5, 12, 150])
def test_destination_point_is_at_the_requested_distance(bearing, distance):
    lat, lon = destination_point(41.5, -72.7, bearing, distance)

    assert haversine_km(41.5, -72.7, lat, lon) == pytest.approx(distance, rel=1e-6)


def test_destination_point_north_keeps_the_longitude():
    lat, lon = destination_point(41.0, -72.0, 0, KM_PER_DEGREE)

    assert lat == pytest.approx(42.0, abs=0.001)
    assert lon == pytest.approx(-72.0, abs=1e-9)


def test_cells_cover_the_bbox_including_negative_longitudes():
    cells = cells_in_bbox((-72.6, 41.1, -72.1, 41.4), 0.25)

    assert (164, -291) in cells and (165, -289) in cells
    assert len(cells) == 2 * 3


def test_random_points_stay_in_their_cell():
    rng = random.Random(7)
    for _ in range(200):
        lat, lon = random_point_in_cell(rng, (166, -291), CELL)
        assert cell_key(lat, lon, CELL) == "166:-291"


def test_in_bbox():
    assert in_bbox(41.5, -72.5, BBOX)
    assert not in_bbox(40.9, -72.5, BBOX)


# --- sampling ---------------------------------------------------------------


def test_sampling_is_reproducible():
    first = sample_trips(FakeRouter(), BBOX, CELL, BANDS, 5, 3, random.Random(3))
    second = sample_trips(FakeRouter(), BBOX, CELL, BANDS, 5, 3, random.Random(3))

    assert first == second and len(first) > 0


def test_trips_stay_inside_the_region_and_on_roads(trips):
    for trip in trips:
        assert in_bbox(trip.lat1, trip.lon1, BBOX) and in_bbox(trip.lat2, trip.lon2, BBOX)
        assert trip.lat1 >= FakeRouter.WATER_BELOW - MAX_SNAP_M / 1000 / KM_PER_DEGREE


def test_no_trip_is_shorter_than_the_minimum_or_than_the_straight_line(trips):
    assert all(trip.straight_km >= MIN_TRIP_KM for trip in trips)
    assert all(trip.road_km >= trip.straight_km * 0.999 for trip in trips)


def test_every_band_is_sampled(trips):
    assert any(trip.straight_km <= 5 for trip in trips)
    assert any(5 < trip.straight_km <= 20 for trip in trips)
    assert any(trip.straight_km > 20 for trip in trips)


def test_points_far_from_any_road_are_not_used():
    class NoRoads(FakeRouter):
        def nearest(self, lat, lon):
            return Snap(lat=lat, lon=lon, moved_m=MAX_SNAP_M + 1)

    assert sample_trips(NoRoads(), BBOX, CELL, BANDS, 5, 3, random.Random(1)) == []


def test_unroutable_destinations_are_skipped():
    class NoRoutes(FakeRouter):
        def road_distances_km(self, origin, destinations):
            return [None] * len(destinations)

    assert sample_trips(NoRoutes(), BBOX, CELL, BANDS, 5, 3, random.Random(1)) == []


# --- the table ------------------------------------------------------------------


def test_the_pipeline_finds_the_two_kinds_of_road_network(table):
    grid_city = table.estimate(41.60, -72.90, 41.62, -72.88)
    open_country = table.estimate(41.60, -72.20, 41.62, -72.18)

    assert grid_city.source == "cell" and open_country.source == "cell"
    assert open_country.factor == pytest.approx(FakeRouter.EAST_DETOUR, abs=0.005)
    # On a street grid the average detour over all directions is 4/pi, about 1.27.
    assert grid_city.factor == pytest.approx(4 / math.pi, abs=0.08)


def test_cells_with_too_few_trips_get_no_factor(trips):
    strict = build_table(trips, "fake", BBOX, CELL, BANDS, min_samples=10**6)

    assert strict["cells"] == {}
    assert strict["default"] == [None, None, None]


def test_the_table_records_how_many_trips_stand_behind_each_factor(trips):
    data = build_table(trips, "fake", BBOX, CELL, BANDS, min_samples=20)

    assert set(data["samples"]) == set(data["cells"])
    for key, factors in data["cells"].items():
        for factor, count in zip(factors, data["samples"][key], strict=True):
            assert (factor is None) == (count < 20)


def test_a_table_cannot_be_built_from_nothing():
    with pytest.raises(ValueError, match="no trips"):
        build_table([], "fake", BBOX, CELL, BANDS, min_samples=20)


def test_a_trip_counts_for_both_of_its_ends():
    west_to_east = Trip(41.6, -72.9, 41.6, -72.1, straight_km=66.5, road_km=80.0)

    data = build_table([west_to_east] * 3, "fake", BBOX, CELL, BANDS, min_samples=3)

    assert set(data["cells"]) == {cell_key(41.6, -72.9, CELL), cell_key(41.6, -72.1, CELL)}


# --- evaluation --------------------------------------------------------------------


def test_the_improved_estimate_beats_every_single_factor(table):
    held_out = sample_trips(FakeRouter(), BBOX, CELL, BANDS, 15, 6, random.Random(2))

    result = evaluate(held_out, table)
    # More than half of the fake world has exactly one detour, so a single factor is exact at the
    # median. The mean shows what it costs in the other half.
    mean = {name: errors["mean_error_pct"] for name, errors in result["methods"].items()}

    assert mean["improved"] < mean["single_factor"]
    assert mean["improved"] < mean["fixed"]
    assert mean["improved"] < mean["haversine"]
    assert result["trips"] == len(held_out)
    assert sum(result["improved_factor_source"].values()) == len(held_out)


def test_evaluation_reports_every_band_that_has_trips(table):
    held_out = sample_trips(FakeRouter(), BBOX, CELL, BANDS, 15, 6, random.Random(2))

    bands = evaluate(held_out, table)["median_error_pct_by_band"]

    assert [band["to_km"] for band in bands] == BANDS
    assert all(band["trips"] > 0 for band in bands)


def test_evaluation_needs_trips(table):
    with pytest.raises(ValueError, match="no trips"):
        evaluate([], table)
