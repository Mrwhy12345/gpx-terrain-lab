#!/usr/bin/env python3
"""Export terrain, trail, and water as aligned STL parts for Bambu Studio."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import bmesh
import bpy


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


def fill_holes(obj):
    editable = bmesh.new()
    editable.from_mesh(obj.data)
    boundary = [edge for edge in editable.edges if edge.is_boundary]
    if boundary:
        bmesh.ops.holes_fill(editable, edges=boundary, sides=0)
        bmesh.ops.recalc_face_normals(editable, faces=editable.faces)
    editable.to_mesh(obj.data)
    editable.free()


def export_selected(path):
    bpy.ops.wm.stl_export(
        filepath=str(path),
        export_selected_objects=True,
        ascii_format=False,
    )


def select_only(objects):
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]


def main():
    arguments = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    if len(arguments) != 2:
        raise SystemExit(
            "Usage: blender FILE.blend --python script.py -- OUTPUT_DIR REPORT.json"
        )
    output_dir, report_path = map(Path, arguments)
    output_dir.mkdir(parents=True, exist_ok=True)

    terrain = next(
        obj
        for obj in bpy.context.scene.objects
        if obj.get("Object type") == "MAP"
    )
    trail = next(
        obj
        for obj in bpy.context.scene.objects
        if obj.get("Object type") == "TRAIL"
    )
    waters = [
        obj
        for obj in bpy.context.scene.objects
        if obj.get("S02_geometry") in {"stream_ribbon", "water_area"}
    ]
    center_x, center_y = terrain.location.x, terrain.location.y
    export_objects = [terrain, trail, *waters]
    for obj in export_objects:
        obj.location.x -= center_x
        obj.location.y -= center_y

    select_only([terrain])
    terrain_path = output_dir / "01_Terrain.stl"
    export_selected(terrain_path)

    select_only([trail])
    bpy.ops.object.convert(target="MESH")
    trail = bpy.context.view_layer.objects.active
    fill_holes(trail)
    trail_path = output_dir / "02_Trail_Red.stl"
    export_selected(trail_path)

    select_only(waters)
    bpy.ops.object.join()
    water = bpy.context.view_layer.objects.active
    water.name = "S02_Water_Blue"
    water_path = output_dir / "03_Water_Blue.stl"
    export_selected(water_path)

    report = {
        "source_blend": bpy.data.filepath,
        "coordinate_origin_shift": [-center_x, -center_y, 0],
        "import_instruction": (
            "Select all three STL files together and import as one object "
            "with multiple parts. Do not auto-arrange parts separately."
        ),
        "parts": [
            {
                "name": "Terrain",
                "file": str(terrain_path),
                "dimensions_mm": [round(value, 4) for value in terrain.dimensions],
                "mesh_quality": quality(terrain),
            },
            {
                "name": "Trail_Red",
                "file": str(trail_path),
                "dimensions_mm": [round(value, 4) for value in trail.dimensions],
                "mesh_quality": quality(trail),
            },
            {
                "name": "Water_Blue",
                "file": str(water_path),
                "dimensions_mm": [round(value, 4) for value in water.dimensions],
                "mesh_quality": quality(water),
            },
        ],
    }
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print("S02_STL_REPORT=" + json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
