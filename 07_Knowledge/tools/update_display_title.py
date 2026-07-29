#!/usr/bin/env python3
"""Replace the display-base inscription with a compact two-line title."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import bmesh
import bpy


TITLE = "星溪徒步\n2026年7月12日 · 9.5 km"
TITLE_MAX_WIDTH_MM = 62.0
TITLE_MAX_HEIGHT_MM = 7.2
TITLE_RAISE_MM = 0.6
TITLE_BAND_CENTER_OFFSET_Y_MM = -47.0
FONT_CANDIDATES = (
    Path("/System/Library/Fonts/STHeiti Medium.ttc"),
    Path("/System/Library/Fonts/STHeiti Light.ttc"),
    Path("/System/Library/Fonts/Supplemental/Songti.ttc"),
)


def bounds(obj):
    points = [obj.matrix_world @ vertex.co for vertex in obj.data.vertices]
    return {
        axis: [min(point[i] for point in points), max(point[i] for point in points)]
        for i, axis in enumerate(("x", "y", "z"))
    }


def quality(obj):
    editable = bmesh.new()
    editable.from_mesh(obj.data)
    result = {
        "vertices": len(editable.verts),
        "faces": len(editable.faces),
        "non_manifold_edges": sum(not edge.is_manifold for edge in editable.edges),
    }
    editable.free()
    return result


def main():
    args = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    if len(args) != 2:
        raise SystemExit(
            "Usage: blender INPUT.blend --python script.py -- OUTPUT.blend REPORT.json"
        )
    output_blend, report_path = map(Path, args)

    terrain = next(
        obj
        for obj in bpy.context.scene.objects
        if obj.get("Object type") == "TERRAIN_LOW_GREEN"
    )
    center_x, center_y = terrain.location.x, terrain.location.y
    for obj in list(bpy.context.scene.objects):
        if obj.get("S05_geometry") == "display_title":
            bpy.data.objects.remove(obj, do_unlink=True)

    font_path = next((path for path in FONT_CANDIDATES if path.exists()), None)
    if font_path is None:
        raise FileNotFoundError("No supported Chinese font found")
    curve = bpy.data.curves.new("S09_Title_Curve", "FONT")
    curve.body = TITLE
    curve.align_x = "CENTER"
    curve.align_y = "CENTER"
    curve.space_line = 0.82
    curve.size = 6.0
    curve.extrude = 0.3
    curve.resolution_u = 8
    curve.font = bpy.data.fonts.load(str(font_path))
    title = bpy.data.objects.new("S09_Title_Brown_TwoLine", curve)
    bpy.context.scene.collection.objects.link(title)
    title.location = (
        center_x,
        center_y + TITLE_BAND_CENTER_OFFSET_Y_MM,
        0.0,
    )
    bpy.context.view_layer.objects.active = title
    title.select_set(True)
    bpy.ops.object.convert(target="MESH")

    title_bounds = bounds(title)
    width = title_bounds["x"][1] - title_bounds["x"][0]
    height = title_bounds["y"][1] - title_bounds["y"][0]
    scale = min(TITLE_MAX_WIDTH_MM / width, TITLE_MAX_HEIGHT_MM / height)
    title.scale.x *= scale
    title.scale.y *= scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

    title_bounds = bounds(title)
    current_depth = title_bounds["z"][1] - title_bounds["z"][0]
    title.scale.z *= TITLE_RAISE_MM / current_depth
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    title_bounds = bounds(title)
    title.location.z -= title_bounds["z"][0]
    bpy.context.view_layer.update()

    title.data.remesh_voxel_size = 0.08
    title.data.remesh_voxel_adaptivity = 0.0
    bpy.context.view_layer.objects.active = title
    bpy.ops.object.voxel_remesh()
    bpy.context.view_layer.update()
    title["S05_geometry"] = "display_title"
    title["S09_geometry"] = "two_line_route_title"
    title["Title"] = TITLE
    title["GPX distance km"] = 9.523068
    title["Displayed distance km"] = 9.5
    title["Font"] = str(font_path)
    material = bpy.data.materials.get("S09_Title_Brown")
    if material is None:
        material = bpy.data.materials.new("S09_Title_Brown")
        material.diffuse_color = (0.43, 0.26, 0.10, 1.0)
    title.data.materials.append(material)

    report = {
        "source_blend": bpy.data.filepath,
        "output_blend": str(output_blend),
        "title": TITLE,
        "distance": {
            "source": "02_GPX/Original/2025-02-23 从化星溪线.gpx",
            "track_segments": 1,
            "track_points": 878,
            "calculated_km": 9.523068,
            "displayed_km": 9.5,
            "method": "sum of WGS-84 track-point haversine distances",
        },
        "title_bounds": bounds(title),
        "quality": quality(title),
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    bpy.ops.wm.save_as_mainfile(filepath=str(output_blend))
    print("UPDATED_TITLE=" + json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
