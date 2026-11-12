"""Compute and evaluate the factor table of one region.

    python -m pipeline.run --region us-ct --osrm-url http://localhost:5000

Needs a running OSRM server that was built from the OpenStreetMap extract of
the region. Writes the factor table into the package and the evaluation next
to it under ``evaluation/``.
"""

from __future__ import annotations

import argparse
import json
import random
from datetime import datetime, timezone
from pathlib import Path

from improved_haversine.table import FactorTable
from pipeline.evaluate import evaluate
from pipeline.factors import build_table, sample_trips
from pipeline.osrm import OsrmRouter

ROOT = Path(__file__).resolve().parent.parent
REGIONS = json.loads((ROOT / "pipeline" / "regions.json").read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--region", required=True, choices=sorted(REGIONS))
    parser.add_argument("--osrm-url", required=True)
    parser.add_argument(
        "--extract-date", default="", help="date of the OpenStreetMap extract, for the record"
    )
    parser.add_argument("--cell-size-deg", type=float, default=0.25)
    parser.add_argument("--bands-km", type=float, nargs="+", default=[5, 20, 60, 150])
    parser.add_argument("--origins-per-cell", type=int, default=60)
    parser.add_argument("--destinations-per-band", type=int, default=6)
    parser.add_argument("--min-samples", type=int, default=30)
    parser.add_argument("--seed", type=int, default=20261112)
    parser.add_argument("--table-dir", type=Path, default=ROOT / "src" / "improved_haversine" / "data")
    parser.add_argument("--evaluation-dir", type=Path, default=ROOT / "evaluation")
    args = parser.parse_args(argv)

    region = REGIONS[args.region]
    bbox = tuple(region["bbox"])
    router = OsrmRouter(args.osrm_url)

    def sample(seed: int, origins_per_cell: int):
        return sample_trips(
            router,
            bbox,
            args.cell_size_deg,
            args.bands_km,
            origins_per_cell,
            args.destinations_per_band,
            random.Random(seed),
        )

    training = sample(args.seed, args.origins_per_cell)
    print(f"sampled {len(training)} trips to build the table")
    table = build_table(
        training,
        region=args.region,
        bbox=bbox,
        cell_size_deg=args.cell_size_deg,
        bands_km=args.bands_km,
        min_samples=args.min_samples,
        metadata={
            "name": region["name"],
            "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "source": {
                "data": "OpenStreetMap contributors, ODbL 1.0",
                "extract": f"https://download.geofabrik.de/{region['geofabrik']}-latest.osm.pbf",
                "extract_date": args.extract_date,
                "router": "OSRM, car profile",
            },
            "seed": args.seed,
        },
    )
    args.table_dir.mkdir(parents=True, exist_ok=True)
    table_path = args.table_dir / f"{args.region}.json"
    table_path.write_text(json.dumps(table, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {table_path} with {len(table['cells'])} cells")

    # Different seed, so none of these trips took part in building the table.
    held_out = sample(args.seed + 1, max(args.origins_per_cell // 3, 10))
    result = evaluate(held_out, FactorTable(table))
    args.evaluation_dir.mkdir(parents=True, exist_ok=True)
    evaluation_path = args.evaluation_dir / f"{args.region}.json"
    evaluation_path.write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    print(f"evaluated on {result['trips']} held-out trips, wrote {evaluation_path}")
    for name, errors in result["methods"].items():
        median, p90 = errors["median_error_pct"], errors["p90_error_pct"]
        print(f"  {name:14} median error {median:6.2f}%   p90 {p90:6.2f}%")


if __name__ == "__main__":
    main()
