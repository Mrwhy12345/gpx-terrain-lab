#!/usr/bin/env python3
"""Export base, terrain assembly, and trail as three physical print groups."""

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
    base_dir = output_dir / "01_Base"
    terrain_dir = output_dir / "02_Terrain"
    trail_dir = output_dir / "03_Trail"
    for directory in (base_dir, terrain_dir, trail_dir):
        directory.mkdir(parents=True, exist_ok=True)

    low = next(
        obj
        for obj in bpy.context.scene.objects
        if obj.get("Object type") == "TERRAIN_LOW_GREEN"
    )
    middle = next(
        obj
        for obj in bpy.context.scene.objects
        if obj.get("Object type") == "TERRAIN_MIDDLE_BROWN"
    )
    high = next(
        obj
        for obj in bpy.context.scene.objects
        if obj.get("Object type") == "TERRAIN_HIGH_GRAY"
    )
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
    base = next(
        obj
        for obj in bpy.context.scene.objects
        if obj.get("S05_geometry") == "display_base"
    )
    title = next(
        obj
        for obj in bpy.context.scene.objects
        if obj.get("S05_geometry") == "display_title"
    )

    standalone_trail = trail.copy()
    standalone_trail.data = trail.data.copy()
    standalone_trail.name = "S07_Trail_Red_Standalone"
    bpy.context.scene.collection.objects.link(standalone_trail)

    center_x, center_y = low.location.x, low.location.y
    aligned = [low, middle, high, trail, *waters, village, base, title]
    for obj in aligned:
        obj.location.x -= center_x
        obj.location.y -= center_y

    exports = []

    base_gray_path = base_dir / "01_Base_Gray.stl"
    select_only([base])
    export_selected(base_gray_path)
    exports.append(("Base_Gray", base_gray_path, base))

    base_title_path = base_dir / "02_Title_Brown.stl"
    select_only([title])
    export_selected(base_title_path)
    exports.append(("Title_Brown", base_title_path, title))

    terrain_green_path = terrain_dir / "01_Terrain_Low_Green.stl"
    select_only([low])
    export_selected(terrain_green_path)
    exports.append(("Terrain_Low_Green", terrain_green_path, low))

    terrain_brown_path = terrain_dir / "02_Terrain_And_Villages_Brown.stl"
    select_only([middle, village])
    bpy.ops.object.join()
    brown = bpy.context.view_layer.objects.active
    brown.name = "S07_Terrain_And_Villages_Brown"
    export_selected(terrain_brown_path)
    exports.append(("Terrain_And_Villages_Brown", terrain_brown_path, brown))

    terrain_gray_path = terrain_dir / "03_Terrain_High_Gray.stl"
    select_only([high])
    export_selected(terrain_gray_path)
    exports.append(("Terrain_High_Gray", terrain_gray_path, high))

    water_path = terrain_dir / "04_Water_Blue.stl"
    select_only(waters)
    bpy.ops.object.join()
    water = bpy.context.view_layer.objects.active
    water.name = "S07_Water_Blue"
    export_selected(water_path)
    exports.append(("Water_Blue", water_path, water))

    aligned_trail_path = trail_dir / "01_Trail_Red_Aligned_Reference.stl"
    select_only([trail])
    export_selected(aligned_trail_path)
    exports.append(("Trail_Red_Aligned_Reference", aligned_trail_path, trail))

    min_x, max_x, min_y, max_y, min_z, _ = world_bounds(standalone_trail)
    standalone_trail.location.x -= (min_x + max_x) / 2
    standalone_trail.location.y -= (min_y + max_y) / 2
    standalone_trail.location.z -= min_z
    trail_path = trail_dir / "02_Trail_Red_SeparatePrint.stl"
    select_only([standalone_trail])
    export_selected(trail_path)
    exports.append(("Trail_Red_SeparatePrint", trail_path, standalone_trail))

    report = {
        "source_blend": bpy.data.filepath,
        "physical_pieces": {
            "1_base": [str(base_gray_path), str(base_title_path)],
            "2_terrain": [
                str(terrain_green_path),
                str(terrain_brown_path),
                str(terrain_gray_path),
                str(water_path),
            ],
            "3_trail": str(trail_path),
        },
        "assembly": [
            "Print piece 1 as a two-color object: gray magnetic base plus brown title.",
            "Print piece 2 as a four-color object: green, brown, gray and blue.",
            "Center and glue piece 2 onto piece 1.",
            "Press-fit or glue piece 3 into the terrain groove.",
        ],
        "parts": [
            {"name": name, "file": str(path), "quality": quality(obj)}
            for name, path, obj in exports
        ],
    }
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print("THREE_PHYSICAL_PIECES=" + json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
