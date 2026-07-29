#!/usr/bin/env python3
"""Build browser-ready WGS84 road data for AMap satellite validation."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
S02 = ROOT / "06_Experiment" / "S02_ColorTest"
GPX = S02 / "input" / "2025-02-23 从化星溪线.gpx"
ROADS = S02 / "data" / "road_candidates"
OUTPUT = S02 / "validation" / "amap_satellite" / "roads" / "validation-data.js"


def route_points() -> list[list[float]]:
    root = ET.parse(GPX).getroot()
    return [
        [float(point.attrib["lon"]), float(point.attrib["lat"])]
        for point in root.iter()
        if point.tag.endswith("trkpt")
    ]


def candidates(path: Path, group: str) -> list[dict]:
    features = json.loads(path.read_text(encoding="utf-8"))["features"]
    result = []
    for feature in features:
        properties = feature.get("properties", {})
        osm_id = properties.get("osm_id")
        highway = properties.get("highway") or "unknown"
        name = properties.get("name")
        ref = properties.get("ref")
        title = name or ref or f"未命名 {highway}"
        result.append(
            {
                "id": f"{group}-{osm_id}",
                "osm_id": osm_id,
                "group": group,
                "highway": highway,
                "name": name,
                "ref": ref,
                "label": title,
                "distance_m": properties.get("distance_to_gpx_m"),
                "selection_reason": properties.get("selection_reason"),
                "geometry": feature["geometry"],
            }
        )
    return result


def main() -> None:
    roads = [
        *candidates(ROADS / "roads_major_clipped_v2.geojson", "major"),
        *candidates(ROADS / "roads_local_relevant_v2.geojson", "local"),
    ]
    data = {
        "project": "星溪竹林徒步地形模型",
        "validation_target": "最终进入多色模型的OSM道路",
        "coordinate_system": "WGS84",
        "route": route_points(),
        "candidates": roads,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        "window.XINGXI_ROAD_VALIDATION_DATA = "
        + json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        + ";\n",
        encoding="utf-8",
    )
    print(f"Wrote {len(roads)} roads to {OUTPUT}")


if __name__ == "__main__":
    main()
