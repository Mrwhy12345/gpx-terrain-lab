#!/usr/bin/env python3
"""Rank OSM water features by proximity to the Xingxi GPX track.

The script intentionally uses only Python's standard library so it can run
without changing the existing QGIS or system Python environments.
"""

from __future__ import annotations

import csv
import json
import math
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[2]
GPX_PATH = ROOT / "02_GPX" / "Original" / "2025-02-23 从化星溪线.gpx"
PROBE_DIR = (
    ROOT / "06_Experiment" / "S02_ColorTest" / "data" / "osm_probe"
)
LINE_PATH = PROBE_DIR / "xingxi_trail_water_lines.geojson"
POLYGON_PATH = PROBE_DIR / "xingxi_trail_water_polygons.geojson"
OUTPUT_DIR = (
    ROOT / "06_Experiment" / "S02_ColorTest" / "data" / "water_candidates"
)

EARTH_RADIUS_M = 6_371_008.8
Point = tuple[float, float]


def read_gpx_points(path: Path) -> list[Point]:
    root = ET.parse(path).getroot()
    points = []
    for element in root.iter():
        if element.tag.endswith("trkpt"):
            points.append((float(element.attrib["lon"]), float(element.attrib["lat"])))
    if len(points) < 2:
        raise ValueError(f"GPX track has fewer than two points: {path}")
    return points


def read_features(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))["features"]


def project(point: Point, origin: Point) -> Point:
    lon, lat = point
    origin_lon, origin_lat = origin
    x = (
        math.radians(lon - origin_lon)
        * EARTH_RADIUS_M
        * math.cos(math.radians(origin_lat))
    )
    y = math.radians(lat - origin_lat) * EARTH_RADIUS_M
    return x, y


def orientation(a: Point, b: Point, c: Point) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (
        c[0] - a[0]
    )


def on_segment(a: Point, b: Point, p: Point, eps: float = 1e-9) -> bool:
    return (
        min(a[0], b[0]) - eps <= p[0] <= max(a[0], b[0]) + eps
        and min(a[1], b[1]) - eps <= p[1] <= max(a[1], b[1]) + eps
        and abs(orientation(a, b, p)) <= eps
    )


def segments_intersect(a: Point, b: Point, c: Point, d: Point) -> bool:
    o1 = orientation(a, b, c)
    o2 = orientation(a, b, d)
    o3 = orientation(c, d, a)
    o4 = orientation(c, d, b)
    if (o1 > 0 > o2 or o2 > 0 > o1) and (o3 > 0 > o4 or o4 > 0 > o3):
        return True
    return (
        on_segment(a, b, c)
        or on_segment(a, b, d)
        or on_segment(c, d, a)
        or on_segment(c, d, b)
    )


def point_segment_distance(point: Point, start: Point, end: Point) -> float:
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    if dx == 0 and dy == 0:
        return math.hypot(point[0] - start[0], point[1] - start[1])
    t = (
        (point[0] - start[0]) * dx + (point[1] - start[1]) * dy
    ) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    nearest = (start[0] + t * dx, start[1] + t * dy)
    return math.hypot(point[0] - nearest[0], point[1] - nearest[1])


def segment_distance(a: Point, b: Point, c: Point, d: Point) -> float:
    if segments_intersect(a, b, c, d):
        return 0.0
    return min(
        point_segment_distance(a, c, d),
        point_segment_distance(b, c, d),
        point_segment_distance(c, a, b),
        point_segment_distance(d, a, b),
    )


def pairwise(points: list[Point]) -> Iterable[tuple[Point, Point]]:
    return zip(points, points[1:])


def point_in_ring(point: Point, ring: list[Point]) -> bool:
    inside = False
    x, y = point
    for a, b in pairwise(ring):
        if (a[1] > y) != (b[1] > y):
            crossing_x = (b[0] - a[0]) * (y - a[1]) / (b[1] - a[1]) + a[0]
            if x < crossing_x:
                inside = not inside
    return inside


def line_to_line_distance(line_a: list[Point], line_b: list[Point]) -> float:
    best = math.inf
    for a, b in pairwise(line_a):
        for c, d in pairwise(line_b):
            best = min(best, segment_distance(a, b, c, d))
            if best == 0:
                return 0.0
    return best


def line_to_polygon_distance(line: list[Point], ring: list[Point]) -> float:
    if any(point_in_ring(point, ring) for point in line):
        return 0.0
    return line_to_line_distance(line, ring)


def line_length(points: list[Point]) -> float:
    return sum(math.dist(a, b) for a, b in pairwise(points))


def polygon_area(ring: list[Point]) -> float:
    return abs(
        sum(a[0] * b[1] - b[0] * a[1] for a, b in pairwise(ring))
    ) / 2


def feature_label(properties: dict) -> str:
    for key in ("waterway", "water", "landuse", "natural"):
        if properties.get(key):
            return f"{key}={properties[key]}"
    return "water=unknown"


def distance_band(distance_m: float) -> str:
    if distance_m <= 50:
        return "A_0-50m"
    if distance_m <= 150:
        return "B_50-150m"
    if distance_m <= 300:
        return "C_150-300m"
    return "D_over-300m"


def add_analysis(
    feature: dict,
    route_xy: list[Point],
    origin: Point,
) -> dict:
    geometry = feature["geometry"]
    properties = dict(feature.get("properties", {}))

    if geometry["type"] == "LineString":
        coordinates = geometry["coordinates"]
        feature_xy = [project(tuple(point), origin) for point in coordinates]
        distance_m = line_to_line_distance(route_xy, feature_xy)
        size_m = line_length(feature_xy)
        size_name = "length_m"
    elif geometry["type"] == "Polygon":
        coordinates = geometry["coordinates"][0]
        feature_xy = [project(tuple(point), origin) for point in coordinates]
        distance_m = line_to_polygon_distance(route_xy, feature_xy)
        size_m = polygon_area(feature_xy)
        size_name = "area_m2"
    else:
        raise ValueError(f"Unsupported geometry: {geometry['type']}")

    properties.update(
        {
            "water_label": feature_label(properties),
            "distance_m": round(distance_m, 1),
            "distance_band": distance_band(distance_m),
            size_name: round(size_m, 1),
        }
    )
    return {
        "type": "Feature",
        "properties": properties,
        "geometry": geometry,
    }


def write_feature_collection(path: Path, features: list[dict]) -> None:
    path.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "name": path.stem,
                "features": features,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    route = read_gpx_points(GPX_PATH)
    origin = route[0]
    route_xy = [project(point, origin) for point in route]

    lines = [
        add_analysis(feature, route_xy, origin)
        for feature in read_features(LINE_PATH)
    ]
    polygons = [
        add_analysis(feature, route_xy, origin)
        for feature in read_features(POLYGON_PATH)
    ]
    all_features = sorted(
        [*lines, *polygons],
        key=lambda feature: (
            feature["properties"]["distance_m"],
            feature["properties"].get("osm_id", 0),
        ),
    )

    write_feature_collection(OUTPUT_DIR / "water_lines_ranked.geojson", lines)
    write_feature_collection(
        OUTPUT_DIR / "water_polygons_ranked.geojson",
        polygons,
    )
    near_lines = [
        feature
        for feature in lines
        if feature["properties"]["distance_m"] <= 150
    ]
    near_polygons = [
        feature
        for feature in polygons
        if feature["properties"]["distance_m"] <= 150
    ]
    write_feature_collection(
        OUTPUT_DIR / "water_lines_near_150m.geojson",
        near_lines,
    )
    write_feature_collection(
        OUTPUT_DIR / "water_polygons_near_150m.geojson",
        near_polygons,
    )

    with (OUTPUT_DIR / "water_candidates.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "rank",
                "osm_id",
                "geometry",
                "water_label",
                "distance_m",
                "distance_band",
                "length_m",
                "area_m2",
            ],
        )
        writer.writeheader()
        for rank, feature in enumerate(all_features, start=1):
            properties = feature["properties"]
            writer.writerow(
                {
                    "rank": rank,
                    "osm_id": properties.get("osm_id"),
                    "geometry": feature["geometry"]["type"],
                    "water_label": properties["water_label"],
                    "distance_m": properties["distance_m"],
                    "distance_band": properties["distance_band"],
                    "length_m": properties.get("length_m", ""),
                    "area_m2": properties.get("area_m2", ""),
                }
            )

    counts = {}
    for feature in all_features:
        band = feature["properties"]["distance_band"]
        counts[band] = counts.get(band, 0) + 1

    summary = {
        "gpx_point_count": len(route),
        "candidate_count": len(all_features),
        "near_150m_count": len(near_lines) + len(near_polygons),
        "distance_band_counts": counts,
        "nearest_candidates": [
            {
                "osm_id": feature["properties"].get("osm_id"),
                "geometry": feature["geometry"]["type"],
                "water_label": feature["properties"]["water_label"],
                "distance_m": feature["properties"]["distance_m"],
            }
            for feature in all_features[:10]
        ],
    }
    (OUTPUT_DIR / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
