#!/usr/bin/env python3
"""Clip and rank settlement candidates against the TrailPrint boundary and GPX."""

from __future__ import annotations

import json
import math
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from shapely.geometry import LineString, mapping, shape
from shapely.ops import transform


EARTH_RADIUS_M = 6_371_000.0


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    args = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    if len(args) != 5:
        raise SystemExit(
            "Usage: blender --background --python script.py -- "
            "GPX BOUNDARY CANDIDATES OUTPUT REPORT"
        )
    gpx_path, boundary_path, input_path, output_path, report_path = map(Path, args)

    gpx_root = ET.parse(gpx_path).getroot()
    route_points = [
        (float(point.attrib["lon"]), float(point.attrib["lat"]))
        for point in gpx_root.iter()
        if point.tag.rsplit("}", 1)[-1] in {"trkpt", "rtept"}
    ]
    center_lat = sum(lat for _, lat in route_points) / len(route_points)
    cos_lat = math.cos(math.radians(center_lat))

    def project(x, y, z=None):
        return (
            EARTH_RADIUS_M * math.radians(x) * cos_lat,
            EARTH_RADIUS_M * math.radians(y),
        )

    route_metric = transform(project, LineString(route_points))
    boundary = shape(read(boundary_path)["features"][0]["geometry"])
    output_features = []
    rejected = []

    for feature in read(input_path)["features"]:
        geometry = shape(feature["geometry"])
        properties = dict(feature.get("properties") or {})
        category = properties.get("category")
        if category == "place":
            clipped = geometry if boundary.covers(geometry) else None
        else:
            clipped = geometry.intersection(boundary)
        if clipped is None or clipped.is_empty:
            rejected.append(
                {"osm_id": properties.get("osm_id"), "reason": "outside_boundary"}
            )
            continue

        metric_geometry = transform(project, clipped)
        properties["distance_to_gpx_m"] = round(
            metric_geometry.distance(route_metric), 2
        )
        if clipped.geom_type in {"Polygon", "MultiPolygon"}:
            properties["clipped_area_m2"] = round(metric_geometry.area, 1)
        properties["clip_status"] = "inside_or_clipped_to_TrailPrint_boundary"
        output_features.append(
            {
                "type": "Feature",
                "properties": properties,
                "geometry": mapping(clipped),
            }
        )

    output = {
        "type": "FeatureCollection",
        "name": "xingxi_settlements_clipped_ranked",
        "features": output_features,
    }
    write(output_path, output)
    report = {
        "input_count": len(read(input_path)["features"]),
        "accepted_count": len(output_features),
        "rejected_count": len(rejected),
        "accepted_by_category": {
            category: sum(
                feature["properties"].get("category") == category
                for feature in output_features
            )
            for category in ("place", "residential_area", "building")
        },
        "accepted_named": [
            {
                "name": feature["properties"].get("name"),
                "category": feature["properties"].get("category"),
                "distance_to_gpx_m": feature["properties"].get(
                    "distance_to_gpx_m"
                ),
            }
            for feature in output_features
            if feature["properties"].get("name")
        ],
        "rejected": rejected,
    }
    write(report_path, report)
    print("SETTLEMENT_ANALYSIS=" + json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
