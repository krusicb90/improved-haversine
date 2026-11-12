"""Every factor table that ships with the package must be usable and plausible."""

import pytest

from improved_haversine import FactorTable, available_regions, road_distance_km
from pipeline.factors import MAX_RATIO


@pytest.mark.parametrize("region", available_regions())
def test_shipped_table(region):
    table = FactorTable.load(region)
    west, south, east, north = table.bbox

    assert table.region == region
    assert west < east and south < north
    assert table.cells, "a shipped table needs at least one measured cell"
    assert any(factor is not None for factor in table.default)

    factors = [f for row in [table.default, *table.cells.values()] for f in row if f is not None]
    # A road is never shorter than the straight line.
    assert all(1.0 <= factor <= MAX_RATIO for factor in factors)

    centre = ((south + north) / 2, (west + east) / 2)
    nearby = (centre[0] + 0.05, centre[1] + 0.05)
    assert road_distance_km(*centre, *nearby, region=region) > 0
