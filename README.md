# improved-haversine

Road distance estimates from coordinates alone.

The Haversine formula gives the distance in a straight line. It is free,
instant and needs no network call. It is also short of the real road distance
by about a third. A routing API gives the real distance and bills for every
pair of points.

This project sits between the two. It multiplies the straight-line distance
by a correction factor that was measured on the real road network, for the
area the trip is in and for how long the trip is. The factors are plain JSON
files. Looking one up takes two divisions and no geospatial library.

## Where it comes from

A store locator has to sort hundreds of stores by driving distance from the
visitor. Asking a routing API for every visitor and every store is exact and
gets expensive fast. Sorting by Haversine is free but ranks a store across a
river above one down the road. The usual patch is to multiply by a constant
such as 1.25. This project measures what that constant should be, and shows
that it should not be a constant.

## Results

Connecticut, USA. Factors built from 24,121 sampled trips, checked against
8,029 other trips that took no part in building them. The error is the
distance between the estimate and the real road distance, as a percentage of
the real road distance.

| Estimate | Median error | 90th percentile |
|----------|-------------:|----------------:|
| Straight line (Haversine) | 30.7% | 54.6% |
| Straight line × 1.25 | 14.0% | 43.2% |
| One factor for the region (× 1.435) | 12.8% | 36.6% |
| One factor per distance band | 11.5% | 36.6% |
| **Factor per cell and distance band** | 11.2% | 36.8% |

By length of trip, median error:

| Straight-line distance | Trips | Straight line | × 1.25 | One factor | Per band | **Per cell and band** |
|------------------------|------:|--------------:|-------:|-----------:|---------:|----------------------:|
| 0.5–5 km | 3,043 | 40.1% | 25.1% | 19.8% | 21.0% | **20.4%** |
| 5–20 km | 2,677 | 31.3% | 14.5% | 10.9% | 11.3% | **11.1%** |
| 20–60 km | 1,847 | 24.9% | 7.3% | 9.8% | 6.6% | **6.4%** |
| 60–150 km | 462 | 21.2% | 5.1% | 13.1% | 5.2% | **4.8%** |

What the numbers say:

- **Distance matters most.** The factor falls from 1.64 for trips under
  5 km to 1.27 for trips over 60 km. A constant can only be right for one
  of them. 1.25 is right for long trips and 25% off for short ones.
- **Location adds a little on top.** Going from one factor per band to one per
  cell and band takes the median error from 11.5% to 11.2%. The cells do
  differ: for short trips their factors range from 1.41 to 1.94. In a region
  the size of Connecticut the gain from that is small.
- **Short trips stay noisy.** Under 5 km the answer depends on which side of a
  highway or a river the two points are, and no factor knows that.

The measured factors for the region as a whole:

| Straight-line distance | Factor |
|------------------------|-------:|
| 0.5–5 km | 1.64 |
| 5–20 km | 1.45 |
| 20–60 km | 1.34 |
| 60–150 km | 1.27 |

## Usage

```sh
pip install git+https://github.com/krusicb90/improved-haversine
```

```python
from improved_haversine import FactorTable, road_distance_km

# One call.
road_distance_km(41.0534, -73.5387, 41.0262, -73.6282, region="us-ct")  # 12.1

# Or keep the table and see how the estimate was made.
table = FactorTable.load("us-ct")
estimate = table.estimate(41.0534, -73.5387, 41.0262, -73.6282)

estimate.haversine_km  # 8.1    straight line
estimate.factor  # 1.495  measured for these cells and this distance
estimate.distance_km  # 12.1   estimated road distance
estimate.source  # "cell"
```

`source` says how the factor was found:

| Source | Meaning |
|--------|---------|
| `cell` | Measured for the grid cell of at least one of the two points. |
| `region` | The cell has too few measurements for this distance, so the regional factor for the distance band is used. |
| `fallback` | Neither point is inside the region. A fixed factor is used, 1.25 unless you pass another. |

The estimate is the same in both directions, and never below the straight
line. The library has no dependencies.

## Using the factors from another language

A factor table is one JSON file, a few kilobytes, under
[src/improved_haversine/data](src/improved_haversine/data). To use it without
this library:

1. Compute the straight-line distance with the Haversine formula.
2. Find the distance band: the first entry of `bands_km` that the distance does
   not exceed.
3. Find the cell of each point. The key is
   `floor(lat / cell_size_deg):floor(lon / cell_size_deg)`.
4. Take `cells[key][band]` for both points and average the values that are not
   null. If both are null, use `default[band]`.
5. Multiply.

## How the factors are computed

1. The OpenStreetMap extract of the region is downloaded from Geofabrik and
   turned into a routing graph with OSRM, using the car profile.
2. For every grid cell, random points are placed in the cell and moved onto
   the nearest road. Points more than 500 m from any road are dropped.
3. From each of those points, destinations are placed at a random bearing and
   a random distance inside each distance band, and moved onto a road too.
4. OSRM routes every trip. The ratio of road distance to straight-line
   distance is recorded.
5. The factor of a cell and band is the median ratio of the trips that start
   or end in that cell. A cell needs 30 trips in a band to get a factor.
6. A second set of trips, from a different random seed, is routed and compared
   with each estimate. That is the table above.

All of it runs in GitHub Actions, in
[.github/workflows/compute.yml](.github/workflows/compute.yml). The seed is
fixed, so the same extract gives the same table.

## Adding a region

Add the region to [pipeline/regions.json](pipeline/regions.json) with its
Geofabrik path and bounding box, then start the "Compute factors" workflow
with the region id. The table and its evaluation appear on the branch
`computed/<region>`.

## Scope

- One region so far: Connecticut.
- Driving distance by car. Travel time is not estimated.
- Sample points are spread evenly over the area, not by where people live.
- An estimate, not a route. Use a routing engine when a single trip has to be
  exact, and this when thousands have to be ranked.

## Tests

```sh
pip install -e . pytest
pytest
```

The tests run the whole pipeline against a made-up road network with known
detours, so they need no routing engine.

## License

The code is under the [MIT license](LICENSE).

The factor tables are derived from OpenStreetMap data, © OpenStreetMap
contributors, and are available under the
[Open Database License](https://opendatacommons.org/licenses/odbl/).
