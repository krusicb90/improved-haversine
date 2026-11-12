import json

import pytest

from improved_haversine import DEFAULT_FALLBACK_FACTOR, FactorTable, haversine_km

# A small hand-made table. Real tables come from the pipeline.
TABLE = {
    "schema_version": 1,
    "region": "test",
    "cell_size_deg": 0.25,
    "bands_km": [10, 50, 200],
    "bbox": [-73.75, 41.0, -71.75, 42.0],
    "default": [1.40, 1.30, None],
    "cells": {
        "166:-291": [1.50, 1.32, None],  # around 41.6, -72.7
        "165:-292": [1.60, None, None],  # around 41.4, -72.9
    },
}

IN_CELL_A = (41.60, -72.70)
IN_CELL_B = (41.40, -72.90)
IN_REGION_NO_CELL = (41.90, -72.00)
OUTSIDE = (45.00, -80.00)


@pytest.fixture
def table():
    return FactorTable(json.loads(json.dumps(TABLE)))


def test_short_trip_inside_one_cell_uses_that_cell(table):
    estimate = table.estimate(41.60, -72.70, 41.62, -72.68)

    assert estimate.source == "cell"
    assert estimate.factor == 1.50
    assert estimate.distance_km == pytest.approx(estimate.haversine_km * 1.50)


def test_two_measured_cells_are_averaged(table):
    # Both points are close to the shared cell corner, so the trip is in the shortest band.
    estimate = table.estimate(41.51, -72.74, 41.49, -72.76)

    assert estimate.haversine_km < 10
    assert estimate.source == "cell"
    assert estimate.factor == pytest.approx((1.50 + 1.60) / 2)


def test_the_estimate_is_the_same_in_both_directions(table):
    there = table.estimate(*IN_CELL_A, *IN_CELL_B)
    back = table.estimate(*IN_CELL_B, *IN_CELL_A)

    assert there == back


def test_a_cell_without_a_value_for_the_band_is_ignored(table):
    # About 28 km apart: cell A has a factor for this band, cell B does not.
    estimate = table.estimate(*IN_CELL_A, *IN_CELL_B)

    assert 10 < estimate.haversine_km <= 50
    assert estimate.source == "cell"
    assert estimate.factor == 1.32


def test_unmeasured_cells_use_the_region_factor(table):
    estimate = table.estimate(41.90, -72.00, 41.92, -72.02)

    assert estimate.source == "region"
    assert estimate.factor == 1.40


def test_a_band_without_a_region_factor_borrows_from_a_shorter_band(table):
    # About 150 km apart, in a band the region has no factor for.
    estimate = table.estimate(41.90, -72.00, 41.05, -73.50)

    assert estimate.haversine_km > 50
    assert estimate.source == "region"
    assert estimate.factor == 1.30


def test_points_outside_the_region_use_the_fallback(table):
    estimate = table.estimate(*OUTSIDE, 45.1, -80.1)

    assert estimate.source == "fallback"
    assert estimate.factor == DEFAULT_FALLBACK_FACTOR


def test_the_fallback_factor_can_be_chosen(table):
    estimate = table.estimate(*OUTSIDE, 45.1, -80.1, fallback_factor=1.4)

    assert estimate.factor == 1.4


def test_a_trip_that_starts_in_the_region_does_not_use_the_fallback(table):
    # A long trip out of the region: no cell has a factor for that band, the region does.
    estimate = table.estimate(*IN_CELL_A, *OUTSIDE)

    assert estimate.source == "region"
    assert estimate.factor == 1.30


def test_estimate_never_returns_less_than_the_straight_line(table):
    for a, b in [(IN_CELL_A, IN_CELL_B), (IN_REGION_NO_CELL, IN_CELL_A), (OUTSIDE, IN_CELL_B)]:
        estimate = table.estimate(*a, *b)
        assert estimate.distance_km >= haversine_km(*a, *b)


def test_covers(table):
    assert table.covers(*IN_CELL_A)
    assert not table.covers(*OUTSIDE)


def test_tables_load_from_a_file(tmp_path):
    path = tmp_path / "table.json"
    path.write_text(json.dumps(TABLE), encoding="utf-8")

    assert FactorTable.from_file(path).region == "test"


@pytest.mark.parametrize("missing", ["region", "cell_size_deg", "bands_km", "bbox", "default", "cells"])
def test_a_table_with_a_missing_field_is_rejected(missing):
    data = {key: value for key, value in TABLE.items() if key != missing}

    with pytest.raises(ValueError, match=missing):
        FactorTable(data)


def test_an_unknown_schema_version_is_rejected():
    with pytest.raises(ValueError, match="schema_version"):
        FactorTable({**TABLE, "schema_version": 99})


def test_default_must_match_the_bands():
    with pytest.raises(ValueError, match="one factor per distance band"):
        FactorTable({**TABLE, "default": [1.4]})


def test_an_unknown_region_names_the_available_ones():
    with pytest.raises(ValueError, match="no factors for region"):
        FactorTable.load("atlantis")
