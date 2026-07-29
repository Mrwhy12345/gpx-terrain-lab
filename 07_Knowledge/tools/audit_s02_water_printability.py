#!/usr/bin/env python3
"""Audit every S02 OSM water feature against the GPX and print boundary.

Only derived files are written.  Source GPX/OSM GeoJSON and previous S02
results are read-only inputs.
"""

from __future__ import annotations

import json
import math
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

from analyze_water_proximity import (
    feature_label,
    line_length,
    line_to_line_distance,
    line_to_polygon_distance,
    point_in_ring,
    polygon_area,
    project,
    read_features,
)


ROOT = Path(__file__).resolve().parents[2]
S02 = ROOT / "06_Experiment" / "S02_ColorTest"
GPX = S02 / "input" / "2025-02-23 从化星溪线.gpx"
PROBE = S02 / "data" / "osm_probe"
BOUNDARY = S02 / "result" / "S02_Xingxi_TrailPrint_Boundary.geojson"
OUT = S02 / "data" / "water_print_audit"
REVIEW = S02 / "review" / "S02_Xingxi_Water_Print_Spatial_Audit.json"

EARTH_RADIUS_M = 6_371_008.8
ROUTE_RELEVANCE_M = 150.0
SIMPLIFY_TOLERANCE_M = 12.0
MIN_MODEL_LENGTH_MM = 1.5
MIN_MODEL_AREA_MM2 = 0.50


def read_gpx(path: Path) -> list[tuple[float, float]]:
    root = ET.parse(path).getroot()
    return [
        (float(node.attrib["lon"]), float(node.attrib["lat"]))
        for node in root.iter()
        if node.tag.endswith("trkpt")
    ]


def pairs(points):
    return zip(points, points[1:])


def point_segment_distance(point, start, end):
    dx, dy = end[0] - start[0], end[1] - start[1]
    if dx == 0 and dy == 0:
        return math.dist(point, start)
    t = max(
        0.0,
        min(
            1.0,
            ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy)
            / (dx * dx + dy * dy),
        ),
    )
    return math.dist(point, (start[0] + t * dx, start[1] + t * dy))


def distance_to_ring(point, ring):
    return min(point_segment_distance(point, a, b) for a, b in pairs(ring))


def geometry_points(geometry):
    if geometry["type"] == "LineString":
        return [tuple(p) for p in geometry["coordinates"]]
    if geometry["type"] == "Polygon":
        return [tuple(p) for p in geometry["coordinates"][0]]
    raise ValueError(geometry["type"])


def consecutive_duplicates(points):
    return sum(a == b for a, b in pairs(points))


def unique_count(points):
    return len(set(points[:-1] if points and points[0] == points[-1] else points))


def perpendicular_distance(point, start, end):
    return point_segment_distance(point, start, end)


def douglas_peucker(points, tolerance):
    if len(points) <= 2:
        return points
    best_distance, best_index = 0.0, 0
    for index, point in enumerate(points[1:-1], start=1):
        distance = perpendicular_distance(point, points[0], points[-1])
        if distance > best_distance:
            best_distance, best_index = distance, index
    if best_distance <= tolerance:
        return [points[0], points[-1]]
    left = douglas_peucker(points[: best_index + 1], tolerance)
    right = douglas_peucker(points[best_index:], tolerance)
    return left[:-1] + right


def orientation(a, b, c):
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def segment_intersection_parameter(a, b, c, d):
    rx, ry = b[0] - a[0], b[1] - a[1]
    sx, sy = d[0] - c[0], d[1] - c[1]
    denominator = rx * sy - ry * sx
    if abs(denominator) < 1e-12:
        return None
    qx, qy = c[0] - a[0], c[1] - a[1]
    t = (qx * sy - qy * sx) / denominator
    u = (qx * ry - qy * rx) / denominator
    if -1e-10 <= t <= 1 + 1e-10 and -1e-10 <= u <= 1 + 1e-10:
        return max(0.0, min(1.0, t))
    return None


def self_intersection_count(points, closed=False):
    segments = list(pairs(points))
    count = 0
    for first_index, (a, b) in enumerate(segments):
        for second_index, (c, d) in enumerate(segments[first_index + 1 :], start=first_index + 1):
            if second_index == first_index + 1:
                continue
            if closed and first_index == 0 and second_index == len(segments) - 1:
                continue
            value = segment_intersection_parameter(a, b, c, d)
            if value is not None:
                count += 1
    return count


def interpolate(a, b, t):
    return (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]))


def clip_line(line, boundary):
    parts, current = [], []
    for a, b in pairs(line):
        cuts = [0.0, 1.0]
        for c, d in pairs(boundary):
            value = segment_intersection_parameter(a, b, c, d)
            if value is not None:
                cuts.append(value)
        cuts = sorted(set(round(value, 12) for value in cuts))
        for start_t, end_t in pairs(cuts):
            midpoint = interpolate(a, b, (start_t + end_t) / 2)
            if point_in_ring(midpoint, boundary):
                start, end = interpolate(a, b, start_t), interpolate(a, b, end_t)
                if not current:
                    current = [start, end]
                elif math.dist(current[-1], start) < 1e-7:
                    current.append(end)
                else:
                    parts.append(current)
                    current = [start, end]
            elif current:
                parts.append(current)
                current = []
    if current:
        parts.append(current)
    return [part for part in parts if len(part) >= 2]


def boundary_is_ccw(ring):
    return sum(a[0] * b[1] - b[0] * a[1] for a, b in pairs(ring)) > 0


def infinite_line_intersection(a, b, c, d):
    rx, ry = b[0] - a[0], b[1] - a[1]
    sx, sy = d[0] - c[0], d[1] - c[1]
    denominator = rx * sy - ry * sx
    if abs(denominator) < 1e-12:
        return b
    qx, qy = c[0] - a[0], c[1] - a[1]
    return interpolate(a, b, (qx * sy - qy * sx) / denominator)


def clip_polygon(subject, boundary):
    output = subject[:-1] if subject and subject[0] == subject[-1] else subject[:]
    ccw = boundary_is_ccw(boundary)
    for clip_a, clip_b in pairs(boundary):
        input_points, output = output, []
        if not input_points:
            break

        def inside(point):
            value = orientation(clip_a, clip_b, point)
            return value >= -1e-10 if ccw else value <= 1e-10

        previous = input_points[-1]
        for current in input_points:
            if inside(current):
                if not inside(previous):
                    output.append(
                        infinite_line_intersection(previous, current, clip_a, clip_b)
                    )
                output.append(current)
            elif inside(previous):
                output.append(
                    infinite_line_intersection(previous, current, clip_a, clip_b)
                )
            previous = current
    if len(output) >= 3:
        output.append(output[0])
    return output


def write_collection(path, features):
    payload = {
        "type": "FeatureCollection",
        "name": path.stem,
        "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}},
        "features": features,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    route = read_gpx(GPX)
    origin = route[0]
    route_xy = [project(point, origin) for point in route]
    boundary_doc = json.loads(BOUNDARY.read_text())
    boundary_ll = [tuple(p) for p in boundary_doc["features"][0]["geometry"]["coordinates"][0]]
    boundary_xy = [project(point, origin) for point in boundary_ll]
    mm_per_m = boundary_doc["features"][0]["properties"]["horizontal_scale"] / 1000.0

    sources = [
        *read_features(PROBE / "xingxi_trail_water_lines.geojson"),
        *read_features(PROBE / "xingxi_trail_water_polygons.geojson"),
    ]
    audited, outputs = [], {"保留": [], "简化": [], "排除": []}

    for rank, feature in enumerate(sources, start=1):
        geometry = feature["geometry"]
        points_ll = geometry_points(geometry)
        points_xy = [project(point, origin) for point in points_ll]
        properties = dict(feature.get("properties") or {})
        geom_type = geometry["type"]
        if geom_type == "LineString":
            route_distance = line_to_line_distance(route_xy, points_xy)
            clipped_parts = clip_line(points_xy, boundary_xy)
            clipped_length = sum(line_length(part) for part in clipped_parts)
            original_measure = line_length(points_xy)
            clipped_measure = clipped_length
            model_measure = clipped_length * mm_per_m
            geometry_valid = len(points_xy) >= 2 and unique_count(points_xy) >= 2
            clipped_geometry = None
            if len(clipped_parts) == 1:
                clipped_geometry = {"type": "LineString", "coordinates": clipped_parts[0]}
            elif clipped_parts:
                clipped_geometry = {"type": "MultiLineString", "coordinates": clipped_parts}
        else:
            route_distance = line_to_polygon_distance(route_xy, points_xy)
            clipped_ring = clip_polygon(points_xy, boundary_xy)
            clipped_area = polygon_area(clipped_ring) if len(clipped_ring) >= 4 else 0.0
            original_measure = polygon_area(points_xy)
            clipped_measure = clipped_area
            model_measure = clipped_area * mm_per_m * mm_per_m
            geometry_valid = (
                len(points_xy) >= 4
                and points_xy[0] == points_xy[-1]
                and unique_count(points_xy) >= 3
                and original_measure > 0
            )
            clipped_geometry = (
                {"type": "Polygon", "coordinates": [clipped_ring]}
                if len(clipped_ring) >= 4
                else None
            )

        inside_count = sum(point_in_ring(point, boundary_xy) for point in points_xy)
        boundary_distance = min(distance_to_ring(point, boundary_xy) for point in points_xy)
        intersects_model = clipped_measure > 0
        fully_inside = inside_count == len(points_xy)
        if not intersects_model:
            boundary_relation = "outside"
        elif fully_inside:
            boundary_relation = "inside"
        else:
            boundary_relation = "crosses_or_clipped"

        issues = []
        duplicates = consecutive_duplicates(points_xy)
        self_intersections = self_intersection_count(
            points_xy, closed=geom_type == "Polygon"
        )
        if duplicates:
            issues.append(f"{duplicates} consecutive duplicate vertices")
        if self_intersections:
            issues.append(f"{self_intersections} self intersections")
            geometry_valid = False
        if not geometry_valid:
            issues.append("invalid_or_degenerate_geometry")
        if intersects_model and clipped_measure < original_measure * 0.999:
            issues.append("extends_beyond_model_boundary")

        if not intersects_model:
            decision, reason = "排除", "不与V009模型边界相交"
        elif route_distance > ROUTE_RELEVANCE_M:
            decision, reason = "排除", f"距GPX {route_distance:.1f} m，超过150 m关联门槛"
        elif not geometry_valid:
            decision, reason = "排除", "几何无效或退化"
        elif geom_type == "Polygon" and model_measure < MIN_MODEL_AREA_MM2:
            decision, reason = "简化", "模型内面积过小，需最小特征补偿或符号化"
            issues.append("below_minimum_print_area")
        elif geom_type == "LineString" and model_measure < MIN_MODEL_LENGTH_MM:
            decision, reason = "简化", "模型内线长过短，需合并或符号化"
            issues.append("below_minimum_print_length")
        elif len(points_xy) > 80 or (intersects_model and clipped_measure < original_measure * 0.999):
            decision, reason = "简化", "空间相关但应先裁边并降低节点密度"
        else:
            decision, reason = "保留", "模型内、距轨迹不超过150 m且达到打印尺度"

        audit_props = {
            **properties,
            "audit_rank": rank,
            "water_label": feature_label(properties),
            "decision": decision,
            "decision_reason": reason,
            "route_distance_m": round(route_distance, 2),
            "model_boundary_relation": boundary_relation,
            "distance_to_boundary_edge_m": round(boundary_distance, 2),
            "geometry_valid": geometry_valid,
            "self_intersection_count": self_intersections,
            "geometry_issues": "; ".join(issues) if issues else "none",
            "source_vertex_count": len(points_xy),
            "inside_vertex_count": inside_count,
            "clip_ratio": round(clipped_measure / original_measure, 6)
            if original_measure
            else 0,
            "model_scale_mm_per_m": round(mm_per_m, 9),
            "model_measure_mm" if geom_type == "LineString" else "model_area_mm2": round(
                model_measure, 4
            ),
            "manual_validation": "provisional_A"
            if properties.get("osm_id")
            in {323929488, 323929492, 324528796, 326182755, 326182759, 326182762}
            else "not_reviewed",
        }
        audited.append(
            {"type": "Feature", "properties": audit_props, "geometry": geometry}
        )

        if decision != "排除" and clipped_geometry:
            if decision == "简化":
                if clipped_geometry["type"] == "LineString":
                    simplified = douglas_peucker(clipped_geometry["coordinates"], SIMPLIFY_TOLERANCE_M)
                    clipped_geometry = {"type": "LineString", "coordinates": simplified}
                elif clipped_geometry["type"] == "MultiLineString":
                    clipped_geometry = {
                        "type": "MultiLineString",
                        "coordinates": [
                            douglas_peucker(part, SIMPLIFY_TOLERANCE_M)
                            for part in clipped_geometry["coordinates"]
                        ],
                    }
            # Convert projected metres back to lon/lat.
            def unproject(p):
                lon = origin[0] + math.degrees(
                    p[0] / (EARTH_RADIUS_M * math.cos(math.radians(origin[1])))
                )
                lat = origin[1] + math.degrees(p[1] / EARTH_RADIUS_M)
                return [lon, lat]

            if clipped_geometry["type"] == "LineString":
                coords = [unproject(p) for p in clipped_geometry["coordinates"]]
            elif clipped_geometry["type"] == "MultiLineString":
                coords = [
                    [unproject(p) for p in part]
                    for part in clipped_geometry["coordinates"]
                ]
            else:
                coords = [[unproject(p) for p in clipped_geometry["coordinates"][0]]]
            outputs[decision].append(
                {
                    "type": "Feature",
                    "properties": audit_props,
                    "geometry": {"type": clipped_geometry["type"], "coordinates": coords},
                }
            )
        elif decision == "排除":
            outputs[decision].append(
                {"type": "Feature", "properties": audit_props, "geometry": geometry}
            )

    write_collection(OUT / "S02_Xingxi_Water_All_Audited.geojson", audited)
    write_collection(OUT / "S02_Xingxi_Water_Print_Keep.geojson", outputs["保留"])
    write_collection(OUT / "S02_Xingxi_Water_Print_Simplify.geojson", outputs["简化"])
    write_collection(OUT / "S02_Xingxi_Water_Print_Exclude.geojson", outputs["排除"])
    write_collection(
        OUT / "S02_Xingxi_Water_Print_Candidates.geojson",
        outputs["保留"] + outputs["简化"],
    )
    review = {
        "project": "S02 ColorTest / V009 print water spatial audit",
        "inputs": {
            "gpx": str(GPX.relative_to(ROOT)),
            "osm_lines": str((PROBE / "xingxi_trail_water_lines.geojson").relative_to(ROOT)),
            "osm_polygons": str((PROBE / "xingxi_trail_water_polygons.geojson").relative_to(ROOT)),
            "model_boundary": str(BOUNDARY.relative_to(ROOT)),
        },
        "facts": {
            "gpx_points": len(route),
            "osm_feature_count": len(sources),
            "model_size_mm": [100.0, 86.6025],
            "model_scale_mm_per_m": mm_per_m,
            "decision_counts": dict(Counter(f["properties"]["decision"] for f in audited)),
            "geometry_valid_count": sum(f["properties"]["geometry_valid"] for f in audited),
            "model_intersection_count": sum(
                f["properties"]["model_boundary_relation"] != "outside" for f in audited
            ),
        },
        "assumptions": {
            "route_relevance_m": ROUTE_RELEVANCE_M,
            "simplify_tolerance_m": SIMPLIFY_TOLERANCE_M,
            "minimum_model_line_length_mm": MIN_MODEL_LENGTH_MM,
            "minimum_model_polygon_area_mm2": MIN_MODEL_AREA_MM2,
            "boundary": "Exact S01 mesh-derived boundary, reused by V009 terrain XY footprint.",
            "manual_validation": "Six previously accepted features remain provisional because all were graded A without detailed inspection.",
            "printing": "Line width/extrusion is assigned later in Blender; this audit tests spatial extent and surviving model-scale size.",
        },
        "features": [feature["properties"] for feature in audited],
        "outputs": [str(path.relative_to(ROOT)) for path in sorted(OUT.glob("*.geojson"))],
    }
    REVIEW.write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(review["facts"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
