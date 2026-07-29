#!/usr/bin/env python3
"""Export the selected road-free, three-band terrain as aligned print parts."""

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


def select_only(objects):
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]


def export_selected(path):
    bpy.ops.wm.stl_export(
        filepath=str(path), export_selected_objects=True, ascii_format=False
    )


def world_bounds(obj):
    points = [obj.matrix_world @ vertex.co for vertex in obj.data.vertices]
    return (
        min(point.x for point in points),
        max(point.x for point in points),
        min(point.y for point in points),
        max(point.y for point in points),
        min(point.z for point in points),
        max(point.z for point in points),
    )


def main():
    args = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    if len(args) != 2:
        raise SystemExit(
            "Usage: blender FILE.blend --python script.py -- OUTPUT_DIR REPORT.json"
        )
    output_dir, report_path = map(Path, args)
    output_dir.mkdir(parents=True, exist_ok=True)

    tags = {
        "low": "TERRAIN_LOW_GREEN",
        "middle": "TERRAIN_MIDDLE_BROWN",
        "high": "TERRAIN_HIGH_GRAY",
    }
    bands = {
        key: next(obj for obj in bpy.context.scene.objects if obj.get("Object type") == tag)
        for key, tag in tags.items()
    }
    trail = next(
        obj for obj in bpy.context.scene.objects if obj.get("S03_geometry") == "trail_insert"
    )
    waters = [
        obj
        for obj in bpy.context.scene.objects
        if obj.get("S02_geometry") in {"stream_ribbon", "water_area"}
    ]
    village = next(
        obj
        for obj in bpy.context.scene.objects
        if obj.get("S04_geometry") == "residential_areas_printable"
    )
    display_base = next(
        obj
        for obj in bpy.context.scene.objects
        if obj.get("S05_geometry") == "display_base"
    )
    display_title = next(
        obj
        for obj in bpy.context.scene.objects
        if obj.get("S05_geometry") == "display_title"
    )

    standalone_trail = trail.copy()
    standalone_trail.data = trail.data.copy()
    standalone_trail.name = "S06_Trail_Red_Standalone"
    bpy.context.scene.collection.objects.link(standalone_trail)

    center_x, center_y = bands["low"].location.x, bands["low"].location.y
    aligned = [*bands.values(), trail, *waters, village, display_base, display_title]
    for obj in aligned:
        obj.location.x -= center_x
        obj.location.y -= center_y

    green_path = output_dir / "01_Terrain_Low_Green.stl"
    select_only([bands["low"]])
    export_selected(green_path)

    brown_path = output_dir / "02_Terrain_Villages_Title_Brown.stl"
    select_only([bands["middle"], village, display_title])
    bpy.ops.object.join()
    brown = bpy.context.view_layer.objects.active
    brown.name = "S06_Terrain_Villages_Title_Brown"
    export_selected(brown_path)

    gray_path = output_dir / "03_Terrain_And_Magnetic_Base_Gray.stl"
    select_only([bands["high"], display_base])
    bpy.ops.object.join()
    gray = bpy.context.view_layer.objects.active
    gray.name = "S06_Terrain_And_Magnetic_Base_Gray"
    export_selected(gray_path)

    water_path = output_dir / "04_Water_Blue.stl"
    select_only(waters)
    bpy.ops.object.join()
    water = bpy.context.view_layer.objects.active
    water.name = "S06_Water_Blue"
    export_selected(water_path)

    aligned_trail_path = output_dir / "05_Trail_Red_Insert_Aligned.stl"
    select_only([trail])
    export_selected(aligned_trail_path)

    min_x, max_x, min_y, max_y, min_z, _ = world_bounds(standalone_trail)
    standalone_trail.location.x -= (min_x + max_x) / 2
    standalone_trail.location.y -= (min_y + max_y) / 2
    standalone_trail.location.z -= min_z
    standalone_path = output_dir / "06_Trail_Red_Insert_SeparatePrint.stl"
    select_only([standalone_trail])
    export_selected(standalone_path)

    parts = [
        ("Terrain_Low_Green", green_path, bands["low"]),
        ("Terrain_Villages_Title_Brown", brown_path, brown),
        ("Terrain_And_Magnetic_Base_Gray", gray_path, gray),
        ("Water_Blue", water_path, water),
        ("Trail_Red_Aligned", aligned_trail_path, trail),
        ("Trail_Red_SeparatePrint", standalone_path, standalone_trail),
    ]
    report = {
        "source_blend": bpy.data.filepath,
        "base_assembly_parts": [str(path) for _, path, _ in parts[:4]],
        "trail_instruction": (
            "Print 06 separately with its flat bottom on the plate, then fit it "
            "into the aligned terrain groove. 05 is an assembly reference only."
        ),
        "parts": [
            {"name": name, "file": str(path), "quality": quality(obj)}
            for name, path, obj in parts
        ],
    }
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print("THREE_BAND_EXPORT=" + json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
