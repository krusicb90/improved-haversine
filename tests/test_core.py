import math

import pytest

from improved_haversine import band_index, cell_key, haversine_km


def test_haversine_matches_a_known_distance():
    # Hartford, CT to New Haven, CT.
    assert haversine_km(41.7658, -72.6734, 41.3083, -72.9279) == pytest.approx(55.1, abs=0.3)


def test_haversine_of_a_point_to_itself_is_zero():
    assert haversine_km(41.5, -72.7, 41.5, -72.7) == 0


def test_haversine_is_symmetric():
    there = haversine_km(41.0, -73.5, 42.0, -72.0)
    back = haversine_km(42.0, -72.0, 41.0, -73.5)
    assert there == pytest.approx(back)


def test_one_degree_of_latitude_is_about_111_km():
    assert haversine_km(41.0, -72.0, 42.0, -72.0) == pytest.approx(111.2, abs=0.1)


def test_antipodal_points_do_not_break_the_formula():
    assert haversine_km(0, 0, 0, 180) == pytest.approx(math.pi * 6371.0088)


@pytest.mark.parametrize(
    ("lat", "lon", "expected"),
    [
        (41.60, -72.70, "166:-291"),
        (41.50, -72.75, "166:-291"),  # lower-left corner belongs to the cell
        (41.49, -72.76, "165:-292"),
        (-0.10, 0.10, "-1:0"),  # negative coordinates round down, not toward zero
    ],
)
def test_cell_key(lat, lon, expected):
    assert cell_key(lat, lon, 0.25) == expected


@pytest.mark.parametrize(
    ("distance", "expected"),
    [(0.5, 0), (10, 0), (10.1, 1), (50, 1), (120, 2), (200, 2), (900, 2)],
)
def test_band_index(distance, expected):
    assert band_index(distance, [10, 50, 200]) == expected
