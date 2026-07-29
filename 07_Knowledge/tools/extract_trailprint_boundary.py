#!/usr/bin/env python3
"""Extract the exact TrailPrint3D map footprint from the open Blender scene."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import bpy


EARTH_RADIUS_KM = 6371.0


def cross(origin, a, b):
    return (a[0] - origin[0]) * (b[1] - origin[1]) - (
        a[1] - origin[1]
    ) * (b[0] - origin[0])


def convex_hull(points):
    unique = sorted(set(points))
    if len(unique) <= 1:
        return unique
    lower = []
    for point in unique:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], point) <= 0:
            lower.pop()
        lower.append(point)
    upper = []
    for point in reversed(unique):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], point) <= 0:
            upper.pop()
        upper.append(point)
    return lower[:-1] + upper[:-1]


def blender_xy_to_geo(x, y, horizontal_scale):
    longitude = math.degrees(x / (EARTH_RADIUS_KM * horizontal_scale))
    latitude = math.degrees(
        2 * math.atan(math.exp(y / (EARTH_RADIUS_KM * horizontal_scale)))
        - math.pi / 2
    )
    return [longitude, latitude]


def main():
    arguments = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    if len(arguments) != 1:
        raise SystemExit("Usage: blender ... --python script.py -- OUTPUT.geojson")
    output = Path(arguments[0])

    map_objects = [
        obj
        for obj in bpy.context.scene.objects
        if obj.type == "MESH" and obj.get("Object type") == "MAP"
    ]
    if len(map_objects) != 1:
        raise SystemExit(f"Expected one TrailPrint3D MAP, found {len(map_objects)}")
    map_object = map_objects[0]
    horizontal_scale = float(map_object["Horizontal Scale"])

    world_xy = [
        (
            round((map_object.matrix_world @ vertex.co).x, 7),
            round((map_object.matrix_world @ vertex.co).y, 7),
        )
        for vertex in map_object.data.vertices
    ]
    hull_xy = convex_hull(world_xy)
    hull_geo = [
        blender_xy_to_geo(x, y, horizontal_scale) for x, y in hull_xy
    ]
    hull_geo.append(hull_geo[0])

    payload = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "source_blend": bpy.data.filepath,
                    "object_name": map_object.name,
                    "shape": map_object.get("Shape"),
                    "object_width_mm": round(map_object.dimensions.x, 4),
                    "object_height_mm": round(map_object.dimensions.y, 4),
                    "horizontal_scale": horizontal_scale,
                    "path_scale": map_object.get("pathScale"),
                    "map_size_km": map_object.get("sMapInKm"),
                    "center_latitude": map_object.get("latitude"),
                    "center_longitude": map_object.get("longitude"),
                    "boundary_status": "exact_from_blend_mesh_convex_hull",
                },
                "geometry": {"type": "Polygon", "coordinates": [hull_geo]},
            }
        ],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print("TRAILPRINT_BOUNDARY=" + json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    main()
