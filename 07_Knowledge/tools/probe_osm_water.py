#!/usr/bin/env python3
"""Probe OSM water coverage for a known control area and the target trail.

This is a data-source availability test, not a model-generation script.
It distinguishes:
1. API/server failure;
2. a working API with no matching data in the target area.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


AREAS = {
    # Central Guangzhou / Pearl River: positive control with obvious water data.
    "guangzhou_pearl_river": (23.095, 113.245, 23.125, 113.285),
    # Exact GPX bounds recorded in S02.
    "xingxi_trail": (23.702296, 113.832099, 23.729689, 113.862918),
}

SERVERS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]

OUTPUT_DIR = (
    Path(__file__).resolve().parents[2]
    / "06_Experiment"
    / "S02_ColorTest"
    / "data"
    / "osm_probe"
)


def build_query(bbox: tuple[float, float, float, float]) -> str:
    south, west, north, east = bbox
    box = f"{south},{west},{north},{east}"
    return f"""
[out:json][timeout:45];
(
  nwr["waterway"]({box});
  nwr["natural"="water"]({box});
  nwr["water"]({box});
  nwr["landuse"="reservoir"]({box});
);
out tags center geom;
""".strip()


def request_overpass(query: str) -> tuple[str, dict]:
    payload = urllib.parse.urlencode({"data": query}).encode("utf-8")
    errors = []

    for server in SERVERS:
        request = urllib.request.Request(
            server,
            data=payload,
            headers={
                "User-Agent": "GPX-Terrain-Lab/1.0 water-source-probe",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                body = response.read()
                return server, json.loads(body)
        except (
            urllib.error.HTTPError,
            urllib.error.URLError,
            TimeoutError,
            json.JSONDecodeError,
        ) as exc:
            errors.append(f"{server}: {type(exc).__name__}: {exc}")
            time.sleep(1)

    raise RuntimeError("All Overpass servers failed:\n" + "\n".join(errors))


def summarize(data: dict) -> dict:
    elements = data.get("elements", [])
    element_types = Counter(item.get("type", "unknown") for item in elements)
    tag_groups: Counter[str] = Counter()

    for item in elements:
        tags = item.get("tags", {})
        if "waterway" in tags:
            tag_groups[f"waterway={tags['waterway']}"] += 1
        if tags.get("natural") == "water":
            tag_groups["natural=water"] += 1
        if "water" in tags:
            tag_groups[f"water={tags['water']}"] += 1
        if tags.get("landuse") == "reservoir":
            tag_groups["landuse=reservoir"] += 1

    return {
        "element_count": len(elements),
        "element_types": dict(element_types.most_common()),
        "water_tags": dict(tag_groups.most_common()),
    }


def geojson_features(data: dict) -> tuple[list[dict], list[dict]]:
    """Convert Overpass way geometries to simple line/polygon GeoJSON.

    Relations are kept in the raw response for later full multipolygon handling.
    This first probe only exports ways whose geometry is already explicit.
    """
    lines = []
    polygons = []

    for item in data.get("elements", []):
        if item.get("type") != "way":
            continue
        geometry = item.get("geometry", [])
        coordinates = [
            [point["lon"], point["lat"]]
            for point in geometry
            if "lon" in point and "lat" in point
        ]
        if len(coordinates) < 2:
            continue

        tags = item.get("tags", {})
        properties = {
            "osm_type": "way",
            "osm_id": item.get("id"),
            **tags,
        }
        is_area = (
            len(coordinates) >= 4
            and coordinates[0] == coordinates[-1]
            and (
                tags.get("natural") == "water"
                or "water" in tags
                or tags.get("landuse") == "reservoir"
            )
        )
        if is_area:
            polygons.append(
                {
                    "type": "Feature",
                    "properties": properties,
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [coordinates],
                    },
                }
            )
        else:
            lines.append(
                {
                    "type": "Feature",
                    "properties": properties,
                    "geometry": {
                        "type": "LineString",
                        "coordinates": coordinates,
                    },
                }
            )

    return lines, polygons


def write_geojson(path: Path, features: list[dict]) -> None:
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
    report = {
        "tested_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": "OpenStreetMap via Overpass API",
        "areas": {},
    }

    for name, bbox in AREAS.items():
        print(f"Testing {name} ...", flush=True)
        query = build_query(bbox)
        try:
            server, data = request_overpass(query)
            summary = summarize(data)
            report["areas"][name] = {
                "bbox_south_west_north_east": bbox,
                "status": "ok",
                "server": server,
                **summary,
            }
            (OUTPUT_DIR / f"{name}_raw.json").write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            lines, polygons = geojson_features(data)
            write_geojson(OUTPUT_DIR / f"{name}_water_lines.geojson", lines)
            write_geojson(
                OUTPUT_DIR / f"{name}_water_polygons.geojson",
                polygons,
            )
            report["areas"][name]["geojson_line_features"] = len(lines)
            report["areas"][name]["geojson_polygon_features"] = len(polygons)
            report["areas"][name]["relations_pending_full_conversion"] = (
                summary["element_types"].get("relation", 0)
            )
            print(
                f"  OK: {summary['element_count']} elements "
                f"({len(lines)} lines, {len(polygons)} polygons) via {server}",
                flush=True,
            )
        except RuntimeError as exc:
            report["areas"][name] = {
                "bbox_south_west_north_east": bbox,
                "status": "failed",
                "error": str(exc),
            }
            print(f"  FAILED: {exc}", flush=True)

    report_path = OUTPUT_DIR / "report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Report: {report_path}")

    control = report["areas"]["guangzhou_pearl_river"]
    target = report["areas"]["xingxi_trail"]
    if control.get("status") != "ok":
        print("Conclusion: interface availability is NOT established.")
        return 2
    if target.get("status") != "ok":
        print("Conclusion: interface works, but the target query failed.")
        return 3
    if target.get("element_count", 0) == 0:
        print("Conclusion: interface works; no matching OSM water data at Xingxi.")
    else:
        print("Conclusion: interface works and Xingxi has matching OSM water data.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
