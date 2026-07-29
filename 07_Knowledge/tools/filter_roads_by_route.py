#!/usr/bin/env python3
"""Keep local roads that are relevant to the GPX route."""

from __future__ import annotations

import json
import math
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from shapely.geometry import LineString, MultiLineString, shape


EARTH_RADIUS_M = 6_371_000.0
MAX_DISTANCE_M = 200.0


def main():
    arguments = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    if len(arguments) != 4:
        raise SystemExit(
            "Usage: blender --background --python script.py -- "
            "GPX INPUT.geojson OUTPUT.geojson REPORT.json"
        )
    gpx_path, input_path, output_path, report_path = map(Path, arguments)

    root = ET.parse(gpx_path).getroot()
    points = []
    for element in root.iter():
        if element.tag.rsplit("}", 1)[-1] in {"trkpt", "rtept"}:
            points.append((float(element.attrib["lon"]), float(element.attrib["lat"])))
    if len(points) < 2:
        raise RuntimeError("No usable GPX route points")

    center_lat = sum(lat for _, lat in points) / len(points)
    cos_lat = math.cos(math.radians(center_lat))

    def metric(coords):
        return [
            (
                EARTH_RADIUS_M * math.radians(lon) * cos_lat,
                EARTH_RADIUS_M * math.radians(lat),
            )
            for lon, lat in coords
        ]

    route = LineString(metric(points))
    data = json.loads(input_path.read_text(encoding="utf-8"))
    accepted = []
    rejected = []
    for feature in data["features"]:
        geometry = shape(feature["geometry"])
        if geometry.geom_type == "LineString":
            road = LineString(metric(list(geometry.coords)))
        elif geometry.geom_type == "MultiLineString":
            road = MultiLineString(
                [metric(list(part.coords)) for part in geometry.geoms]
            )
        else:
            rejected.append(feature)
            continue
        distance = road.distance(route)
        properties = feature["properties"]
        named = bool(properties.get("name") or properties.get("ref"))
        properties["distance_to_gpx_m"] = round(distance, 2)
        properties["selection_reason"] = (
            "named_or_ref" if named else "within_200m_of_gpx"
        )
        if named or distance <= MAX_DISTANCE_M:
            accepted.append(feature)
        else:
            rejected.append(feature)

    output = {
        "type": "FeatureCollection",
        "name": "xingxi_roads_local_relevant",
        "features": accepted,
    }
    output_path.write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    report = {
        "input_count": len(data["features"]),
        "accepted_count": len(accepted),
        "rejected_count": len(rejected),
        "max_distance_m": MAX_DISTANCE_M,
        "accepted_named_or_ref": sum(
            bool(
                feature["properties"].get("name")
                or feature["properties"].get("ref")
            )
            for feature in accepted
        ),
    }
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print("ROAD_RELEVANCE=" + json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
