#!/usr/bin/env python3
"""Fetch OSM settlement, residential land-use, and building candidates."""

from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = (
    ROOT
    / "06_Experiment"
    / "S02_ColorTest"
    / "data"
    / "settlement_candidates"
)
BBOX = (23.694705566958227, 113.82066482908353, 23.737276790705554, 113.87435665531095)
ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]


def query_text() -> str:
    south, west, north, east = BBOX
    box = f"{south},{west},{north},{east}"
    return f"""
[out:json][timeout:90];
(
  nwr["landuse"="residential"]({box});
  nwr["place"~"^(village|hamlet|neighbourhood|isolated_dwelling)$"]({box});
  way["building"]({box});
);
out tags geom;
""".strip()


def fetch() -> tuple[dict, str]:
    payload = urllib.parse.urlencode({"data": query_text()}).encode()
    last_error: Exception | None = None
    for endpoint in ENDPOINTS:
        for attempt in range(2):
            try:
                request = urllib.request.Request(
                    endpoint,
                    data=payload,
                    headers={"User-Agent": "GPX-Terrain-Lab/1.0 settlement-probe"},
                )
                with urllib.request.urlopen(request, timeout=120) as response:
                    return json.load(response), endpoint
            except Exception as error:
                last_error = error
                time.sleep(2 + attempt * 2)
    raise RuntimeError(f"All Overpass endpoints failed: {last_error}")


def geometry(element: dict) -> dict | None:
    if element["type"] == "node":
        return {"type": "Point", "coordinates": [element["lon"], element["lat"]]}
    points = element.get("geometry") or []
    coordinates = [[point["lon"], point["lat"]] for point in points]
    if len(coordinates) < 2:
        return None
    if len(coordinates) >= 4 and coordinates[0] == coordinates[-1]:
        return {"type": "Polygon", "coordinates": [coordinates]}
    return {"type": "LineString", "coordinates": coordinates}


def category(tags: dict) -> str:
    if tags.get("landuse") == "residential":
        return "residential_area"
    if tags.get("place"):
        return "place"
    if tags.get("building"):
        return "building"
    return "other"


def main() -> None:
    data, endpoint = fetch()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "settlements_raw.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    features = []
    for element in data.get("elements", []):
        shape = geometry(element)
        if not shape:
            continue
        tags = element.get("tags", {})
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "osm_type": element["type"],
                    "osm_id": element["id"],
                    "category": category(tags),
                    "name": tags.get("name"),
                    "place": tags.get("place"),
                    "landuse": tags.get("landuse"),
                    "building": tags.get("building"),
                    "building_levels": tags.get("building:levels"),
                },
                "geometry": shape,
            }
        )

    collection = {
        "type": "FeatureCollection",
        "name": "xingxi_settlement_candidates",
        "features": features,
    }
    (OUTPUT / "settlements_all.geojson").write_text(
        json.dumps(collection, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    categories = Counter(f["properties"]["category"] for f in features)
    places = Counter(
        f["properties"]["place"]
        for f in features
        if f["properties"].get("place")
    )
    summary = {
        "endpoint": endpoint,
        "bbox_wgs84": BBOX,
        "feature_count": len(features),
        "categories": dict(categories),
        "place_types": dict(places),
        "named_features": sum(bool(f["properties"].get("name")) for f in features),
    }
    (OUTPUT / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
