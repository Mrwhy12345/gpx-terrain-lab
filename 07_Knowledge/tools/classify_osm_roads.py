#!/usr/bin/env python3
"""Classify OSM roads into printable candidate groups."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
INPUT = (
    ROOT
    / "06_Experiment/S02_ColorTest/data/road_candidates/roads_all.geojson"
)
OUTPUT_DIR = INPUT.parent

GROUPS = {
    "major": {"motorway", "motorway_link", "trunk", "trunk_link", "tertiary"},
    "local": {"unclassified", "residential", "service"},
    "minor": {"track", "path", "footway", "cycleway", "steps"},
}


def main() -> None:
    data = json.loads(INPUT.read_text(encoding="utf-8"))
    grouped = {name: [] for name in GROUPS}
    unhandled = Counter()
    for feature in data["features"]:
        properties = feature["properties"]
        # Normalize the fields needed downstream.  GeoJSON/OGR otherwise
        # infers its schema from early features and can drop a later `name`
        # or `ref` that was absent from the first road.
        properties["name"] = properties.get("name")
        properties["ref"] = properties.get("ref")
        properties["access"] = properties.get("access")
        properties["bridge"] = properties.get("bridge")
        properties["tunnel"] = properties.get("tunnel")
        highway = properties.get("highway", "unknown")
        matched = False
        for name, highway_types in GROUPS.items():
            if highway in highway_types:
                feature["properties"]["road_group"] = name
                grouped[name].append(feature)
                matched = True
                break
        if not matched:
            unhandled[highway] += 1

    summary = {"groups": {}, "unhandled": dict(unhandled)}
    for name, features in grouped.items():
        path = OUTPUT_DIR / f"roads_{name}.geojson"
        path.write_text(
            json.dumps(
                {
                    "type": "FeatureCollection",
                    "name": f"xingxi_roads_{name}",
                    "features": features,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        summary["groups"][name] = {
            "feature_count": len(features),
            "file": str(path),
        }
    (OUTPUT_DIR / "classification_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
