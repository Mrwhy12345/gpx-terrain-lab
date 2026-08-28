#!/usr/bin/env python3
"""Audit whether a binary-STL insert still behaves like a narrow linear feature."""

from __future__ import annotations

import argparse
import json
import math
import struct
import xml.etree.ElementTree as ET
from pathlib import Path


def read_stl(path: Path):
    data = path.read_bytes()
    if len(data) < 84:
        raise ValueError(f"Invalid STL: {path}")
    count = struct.unpack_from("<I", data, 80)[0]
    if len(data) != 84 + count * 50:
        raise ValueError(f"Only binary STL is supported: {path}")
    triangles = []
    offset = 84
    for _ in range(count):
        values = struct.unpack_from("<12fH", data, offset)
        triangles.append((values[3:6], values[6:9], values[9:12]))
        offset += 50
    return triangles


def gpx_points(path: Path):
    root = ET.parse(path).getroot()
    points = []
    for element in root.iter():
        if element.tag.rsplit("}", 1)[-1] == "trkpt":
            points.append((math.radians(float(element.attrib["lat"])), math.radians(float(element.attrib["lon"]))))
    if len(points) < 2:
        raise ValueError("GPX must contain at least two track points")
    return points


def model_length_mm(points, object_size_mm):
    mean_lat = sum(lat for lat, _ in points) / len(points)
    radius = 6_371_008.8
    xy = [(radius * lon * math.cos(mean_lat), radius * lat) for lat, lon in points]
    xs = [x for x, _ in xy]; ys = [y for _, y in xy]
    span = max(max(xs) - min(xs), max(ys) - min(ys))
    scale = object_size_mm / span
    return sum(math.hypot(x2 - x1, y2 - y1) for (x1, y1), (x2, y2) in zip(xy, xy[1:])) * scale


def projected_area_and_bounds(triangles):
    area2 = 0.0
    xs = []; ys = []; zs = []
    for triangle in triangles:
        for x, y, z in triangle:
            xs.append(x); ys.append(y); zs.append(z)
        (x1, y1, _), (x2, y2, _), (x3, y3, _) = triangle
        area2 += abs((x2 - x1) * (y3 - y1) - (x3 - x1) * (y2 - y1)) / 2
    # A closed narrow solid normally contributes top and bottom projection.
    return area2 / 2, {"x": [min(xs), max(xs)], "y": [min(ys), max(ys)], "z": [min(zs), max(zs)]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("gpx", type=Path)
    parser.add_argument("stl", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--object-size-mm", type=float, default=100.0)
    parser.add_argument("--nominal-width-mm", type=float, default=1.6)
    parser.add_argument("--max-area-ratio", type=float, default=2.5)
    args = parser.parse_args()
    triangles = read_stl(args.stl)
    route_length = model_length_mm(gpx_points(args.gpx), args.object_size_mm)
    projected_area, bounds = projected_area_and_bounds(triangles)
    expected_area = route_length * args.nominal_width_mm
    ratio = projected_area / expected_area if expected_area else math.inf
    report = {
        "method": "binary STL XY projected-area versus scaled GPX length x nominal width",
        "gpx": str(args.gpx), "stl": str(args.stl),
        "triangle_count": len(triangles), "bounds_mm": bounds,
        "scaled_gpx_length_mm": round(route_length, 3),
        "nominal_width_mm": args.nominal_width_mm,
        "expected_linear_area_mm2": round(expected_area, 3),
        "stl_projected_footprint_mm2": round(projected_area, 3),
        "footprint_area_ratio": round(ratio, 3),
        "threshold_max_ratio": args.max_area_ratio,
        "status": "PASS" if ratio <= args.max_area_ratio else "FAIL",
        "limitations": "Area is a conservative mesh projection metric; visual/slot homology QA remains separately required.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    raise SystemExit(0 if report["status"] == "PASS" else 2)


if __name__ == "__main__":
    main()
