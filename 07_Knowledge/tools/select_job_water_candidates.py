#!/usr/bin/env python3
"""Select up to N ranked water features for a standardized job."""

import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("job_dir", type=Path)
    parser.add_argument("--max-components", type=int, default=5)
    args = parser.parse_args()
    source = json.loads(
        (args.job_dir / "review/water_candidates_ranked.geojson").read_text()
    )
    selected = [
        feature
        for feature in source["features"]
        if feature["properties"]["print_decision"] in {"keep", "simplify"}
    ][: args.max_components]
    output = args.job_dir / "work/water_selected"
    output.mkdir(parents=True, exist_ok=True)
    for geometry_type, filename in (
        ("LineString", "water_lines.geojson"),
        ("Polygon", "water_polygons.geojson"),
    ):
        features = [
            feature for feature in selected
            if feature["geometry"]["type"] == geometry_type
        ]
        (output / filename).write_text(
            json.dumps(
                {"type": "FeatureCollection", "features": features},
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    report = {
        "policy": "keep/simplify by route distance, maximum component budget",
        "max_components": args.max_components,
        "selected_count": len(selected),
        "osm_ids": [feature["properties"].get("osm_id") for feature in selected],
    }
    (args.job_dir / "review/water_selection.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
