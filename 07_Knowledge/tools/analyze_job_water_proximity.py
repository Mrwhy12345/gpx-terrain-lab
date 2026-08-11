#!/usr/bin/env python3
"""Rank route-neutral OSM water candidates by distance to a job's GPX track."""

from __future__ import annotations

import argparse
import json
import math
import xml.etree.ElementTree as ET
from pathlib import Path

EARTH_M = 6371008.8


def project(lon, lat, lon0, lat0):
    return (
        math.radians(lon - lon0) * EARTH_M * math.cos(math.radians(lat0)),
        math.radians(lat - lat0) * EARTH_M,
    )


def point_segment_distance(point, start, end):
    dx, dy = end[0] - start[0], end[1] - start[1]
    if dx == 0 and dy == 0:
        return math.dist(point, start)
    value = max(
        0.0,
        min(
            1.0,
            ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy)
            / (dx * dx + dy * dy),
        ),
    )
    return math.dist(point, (start[0] + value * dx, start[1] + value * dy))


def coordinates(geometry):
    if geometry["type"] == "LineString":
        return geometry["coordinates"]
    if geometry["type"] == "Polygon":
        return geometry["coordinates"][0]
    return []


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("job_dir", type=Path)
    args = parser.parse_args()
    job = json.loads((args.job_dir / "job.json").read_text())
    engineering = job.get("engineering", {})
    keep_distance_m = float(engineering.get("water_keep_distance_m", 30))
    simplify_distance_m = float(
        engineering.get("water_simplify_distance_m", 120)
    )
    root = ET.parse(args.job_dir / "input/route.gpx").getroot()
    track_lonlat = [
        (float(point.attrib["lon"]), float(point.attrib["lat"]))
        for point in root.iter()
        if point.tag.rsplit("}", 1)[-1] == "trkpt"
    ]
    lon0 = sum(point[0] for point in track_lonlat) / len(track_lonlat)
    lat0 = sum(point[1] for point in track_lonlat) / len(track_lonlat)
    track = [project(*point, lon0, lat0) for point in track_lonlat]
    segments = list(zip(track, track[1:]))
    features = []
    for filename in ("water_lines.geojson", "water_polygons.geojson"):
        collection = json.loads(
            (args.job_dir / "work/osm_water" / filename).read_text()
        )
        features.extend(collection["features"])
    ranked = []
    for feature in features:
        source_coordinates = coordinates(feature["geometry"])
        points = [project(*point, lon0, lat0) for point in source_coordinates]
        if not points:
            continue
        minimum = min(
            point_segment_distance(point, start, end)
            for point in points
            for start, end in segments
        )
        properties = dict(feature.get("properties", {}))
        properties["distance_to_route_m"] = round(minimum, 2)
        properties["point_count"] = len(points)
        properties["print_decision"] = (
            "keep"
            if minimum <= keep_distance_m
            else "simplify"
            if minimum <= simplify_distance_m
            else "exclude"
        )
        feature["properties"] = properties
        ranked.append(feature)
    ranked.sort(key=lambda item: item["properties"]["distance_to_route_m"])
    report = {
        "projection": "local equirectangular distance approximation",
        "keep_distance_m": keep_distance_m,
        "simplify_distance_m": simplify_distance_m,
        "candidate_count": len(ranked),
        "decision_counts": {
            decision: sum(
                item["properties"]["print_decision"] == decision
                for item in ranked
            )
            for decision in ("keep", "simplify", "exclude")
        },
        "candidates": [
            {
                "osm_id": item["properties"].get("osm_id"),
                "name": item["properties"].get("name"),
                "type": item["geometry"]["type"],
                "waterway": item["properties"].get("waterway"),
                "water": item["properties"].get("water"),
                "distance_to_route_m": item["properties"]["distance_to_route_m"],
                "decision": item["properties"]["print_decision"],
            }
            for item in ranked
        ],
    }
    output = args.job_dir / "review/water_candidates_ranked.geojson"
    output.write_text(
        json.dumps(
            {"type": "FeatureCollection", "features": ranked},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (args.job_dir / "review/water_proximity_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
