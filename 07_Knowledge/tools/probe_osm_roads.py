#!/usr/bin/env python3
"""Fetch and export OSM roads around the Xingxi TrailPrint3D boundary."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BOUNDARY = (
    ROOT
    / "06_Experiment/S02_ColorTest/result"
    / "S02_Xingxi_TrailPrint_Boundary.geojson"
)
OUTPUT_DIR = (
    ROOT / "06_Experiment/S02_ColorTest/data/road_candidates"
)
SERVERS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]


def bounds_from_geojson(path: Path) -> tuple[float, float, float, float]:
    data = json.loads(path.read_text(encoding="utf-8"))
    points: list[tuple[float, float]] = []

    def collect(value):
        if (
            isinstance(value, list)
            and len(value) >= 2
            and isinstance(value[0], (int, float))
        ):
            points.append((float(value[0]), float(value[1])))
        elif isinstance(value, list):
            for child in value:
                collect(child)

    for feature in data["features"]:
        collect(feature["geometry"]["coordinates"])
    west = min(point[0] for point in points)
    east = max(point[0] for point in points)
    south = min(point[1] for point in points)
    north = max(point[1] for point in points)
    return south, west, north, east


def request_overpass(query: str) -> tuple[str, dict]:
    payload = urllib.parse.urlencode({"data": query}).encode("utf-8")
    errors = []
    for server in SERVERS:
        request = urllib.request.Request(
            server,
            data=payload,
            headers={
                "User-Agent": "GPX-Terrain-Lab/1.0 road-source-probe",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                return server, json.loads(response.read())
        except (
            urllib.error.HTTPError,
            urllib.error.URLError,
            TimeoutError,
            json.JSONDecodeError,
        ) as exc:
            errors.append(f"{server}: {type(exc).__name__}: {exc}")
            time.sleep(1)
    raise RuntimeError("All Overpass servers failed:\n" + "\n".join(errors))


def main() -> None:
    south, west, north, east = bounds_from_geojson(BOUNDARY)
    bbox = f"{south},{west},{north},{east}"
    query = f"""
[out:json][timeout:60];
way["highway"]({bbox});
out tags geom;
""".strip()
    server, data = request_overpass(query)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "roads_raw.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    features = []
    highway_counts: Counter[str] = Counter()
    surface_counts: Counter[str] = Counter()
    for item in data.get("elements", []):
        geometry = item.get("geometry", [])
        coordinates = [
            [point["lon"], point["lat"]]
            for point in geometry
            if "lon" in point and "lat" in point
        ]
        if len(coordinates) < 2:
            continue
        tags = item.get("tags", {})
        highway = tags.get("highway", "unknown")
        highway_counts[highway] += 1
        if "surface" in tags:
            surface_counts[tags["surface"]] += 1
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "osm_type": "way",
                    "osm_id": item.get("id"),
                    **tags,
                },
                "geometry": {
                    "type": "LineString",
                    "coordinates": coordinates,
                },
            }
        )

    geojson = {
        "type": "FeatureCollection",
        "name": "xingxi_road_candidates",
        "features": features,
    }
    (OUTPUT_DIR / "roads_all.geojson").write_text(
        json.dumps(geojson, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    summary = {
        "source": server,
        "query_bbox_south_west_north_east": [south, west, north, east],
        "element_count": len(data.get("elements", [])),
        "exported_line_count": len(features),
        "highway_counts": dict(highway_counts.most_common()),
        "surface_counts": dict(surface_counts.most_common()),
    }
    (OUTPUT_DIR / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
