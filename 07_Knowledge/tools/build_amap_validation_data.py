#!/usr/bin/env python3
"""Build browser-ready WGS84 data for the local AMap validation viewer."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
GPX_PATH = ROOT / "02_GPX" / "Original" / "2025-02-23 从化星溪线.gpx"
CANDIDATE_DIR = (
    ROOT / "06_Experiment" / "S02_ColorTest" / "data" / "water_candidates"
)
OUTPUT_PATH = (
    ROOT
    / "06_Experiment"
    / "S02_ColorTest"
    / "validation"
    / "amap_satellite"
    / "validation-data.js"
)


def read_gpx_track(path: Path) -> list[list[float]]:
    root = ET.parse(path).getroot()
    return [
        [float(element.attrib["lon"]), float(element.attrib["lat"])]
        for element in root.iter()
        if element.tag.endswith("trkpt")
    ]


def read_features(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))["features"]


def normalize_feature(feature: dict) -> dict:
    properties = feature.get("properties", {})
    return {
        "id": f"osm-{properties.get('osm_id')}",
        "osm_id": properties.get("osm_id"),
        "label": properties.get("water_label", "water=unknown"),
        "distance_m": properties.get("distance_m"),
        "distance_band": properties.get("distance_band"),
        "geometry": feature["geometry"],
    }


def main() -> int:
    data = {
        "project": "星溪竹林徒步地形模型",
        "coordinate_system": "WGS84",
        "route": read_gpx_track(GPX_PATH),
        "candidates": [
            *[
                normalize_feature(feature)
                for feature in read_features(
                    CANDIDATE_DIR / "water_lines_near_150m.geojson"
                )
            ],
            *[
                normalize_feature(feature)
                for feature in read_features(
                    CANDIDATE_DIR / "water_polygons_near_150m.geojson"
                )
            ],
        ],
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        "window.XINGXI_VALIDATION_DATA = "
        + json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        + ";\n",
        encoding="utf-8",
    )
    print(
        f"Wrote {len(data['route'])} route points and "
        f"{len(data['candidates'])} candidates to {OUTPUT_PATH}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
