#!/usr/bin/env python3
"""Create a closed, route-shaped SVG emblem from a GPX track."""

from __future__ import annotations

import argparse
import math
import xml.etree.ElementTree as ET
from pathlib import Path


def points_from_gpx(path):
    root = ET.parse(path).getroot()
    return [
        (float(node.attrib["lon"]), float(node.attrib["lat"]))
        for node in root.iter()
        if node.tag.rsplit("}", 1)[-1] in {"trkpt", "rtept"}
    ]


def polygon_path(points):
    return "M " + " L ".join(f"{x:.3f} {y:.3f}" for x, y in points) + " Z"


def diamond(point, radius):
    x, y = point
    return [(x, y-radius), (x+radius, y), (x, y+radius), (x-radius, y)]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("gpx", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    source = points_from_gpx(args.gpx)
    if len(source) < 2: raise SystemExit("GPX must contain at least two track points")
    west, east = min(x for x, _ in source), max(x for x, _ in source)
    south, north = min(y for _, y in source), max(y for _, y in source)
    span_x, span_y = max(east - west, 1e-9), max(north - south, 1e-9)
    scale = min(82 / span_x, 58 / span_y)
    normalized = [((x - (west + east) / 2) * scale + 50, 35 - (y - (south + north) / 2) * scale) for x, y in source]
    # A dotted route emblem stays manifold even when a GPX crosses itself many
    # times (horse drawings and urban loops are common). Distinct waymarks also
    # communicate hiking more clearly than a self-intersecting filled ribbon.
    marks = [normalized[0]]
    for point in normalized[1:-1]:
        if math.dist(point, marks[-1]) >= 5.0 and math.dist(point, normalized[-1]) >= 4.0:
            marks.append(point)
        if len(marks) >= 18: break
    paths = [polygon_path(diamond(point, 1.45)) for point in marks[1:]]
    start = normalized[0]; finish = normalized[-1]
    paths.insert(0, polygon_path([(start[0],start[1]-2.4),(start[0]+2.2,start[1]+1.8),(start[0]-2.2,start[1]+1.8)]))
    paths.append(polygon_path(diamond(finish, 2.35)))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 70">'+''.join(f'<path d="{data}"/>' for data in paths)+'</svg>\n', encoding="utf-8")
    print(args.output)


if __name__ == "__main__": main()
