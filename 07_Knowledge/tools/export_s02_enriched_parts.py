#!/usr/bin/env python3
"""Export the enriched S02 model and a flat standalone trail insert."""

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
        filepath=str(path),
        export_selected_objects=True,
        ascii_format=False,
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
    arguments = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    if len(arguments) != 2:
        raise SystemExit(
            "Usage: blender FILE.blend --python script.py -- "
            "OUTPUT_DIR REPORT.json"
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
        if obj.get("S03_geometry") == "trail_insert"
    )
    waters = [
        obj
        for obj in bpy.context.scene.objects
        if obj.get("S02_geometry") in {"stream_ribbon", "water_area"}
    ]
    road = next(
        obj
        for obj in bpy.context.scene.objects
        if obj.get("S03_geometry") == "roads_printable"
    )
    village = next(
        (
            obj
            for obj in bpy.context.scene.objects
            if obj.get("S04_geometry") == "residential_areas_printable"
        ),
        None,
    )
    display_base = next(
        (
            obj
            for obj in bpy.context.scene.objects
            if obj.get("S05_geometry") == "display_base"
        ),
        None,
    )
    display_title = next(
        (
            obj
            for obj in bpy.context.scene.objects
            if obj.get("S05_geometry") == "display_title"
        ),
        None,
    )

    # Keep an untouched duplicate for the standalone print layout.
    standalone_trail = trail.copy()
    standalone_trail.data = trail.data.copy()
    standalone_trail.name = "S02_Trail_Red_Insert_Standalone"
    bpy.context.scene.collection.objects.link(standalone_trail)

    center_x, center_y = terrain.location.x, terrain.location.y
    aligned_objects = [terrain, trail, *waters, road]
    if village is not None:
        aligned_objects.append(village)
    if display_base is not None:
        aligned_objects.append(display_base)
    if display_title is not None:
        aligned_objects.append(display_title)
    for obj in aligned_objects:
        obj.location.x -= center_x
        obj.location.y -= center_y

    terrain_path = output_dir / "01_Terrain_Grooved.stl"
    select_only([terrain])
    export_selected(terrain_path)

    trail_aligned_path = output_dir / "02_Trail_Red_Insert_Aligned.stl"
    select_only([trail])
    export_selected(trail_aligned_path)

    select_only(waters)
    bpy.ops.object.join()
    water = bpy.context.view_layer.objects.active
    water.name = "S02_Water_Blue_With_Trail_Clearance"
    water_path = output_dir / "03_Water_Blue.stl"
    export_selected(water_path)

    road_path = output_dir / "04_Roads_And_Base_Dark.stl"
    dark_objects = [road]
    if display_base is not None:
        dark_objects.append(display_base)
    select_only(dark_objects)
    if len(dark_objects) > 1:
        bpy.ops.object.join()
        road = bpy.context.view_layer.objects.active
        road.name = "S02_Roads_And_Display_Base_Dark"
    export_selected(road_path)

    village_path = None
    if village is not None:
        village_path = output_dir / "05_Villages_And_Title_Warm.stl"
        warm_objects = [village]
        if display_title is not None:
            warm_objects.append(display_title)
        select_only(warm_objects)
        if len(warm_objects) > 1:
            bpy.ops.object.join()
            village = bpy.context.view_layer.objects.active
            village.name = "S02_Villages_And_Title_Warm"
        export_selected(village_path)

    # Center the flat-bottom insert independently and place its bottom at Z=0.
    min_x, max_x, min_y, max_y, min_z, _ = world_bounds(standalone_trail)
    standalone_trail.location.x -= (min_x + max_x) / 2
    standalone_trail.location.y -= (min_y + max_y) / 2
    standalone_trail.location.z -= min_z
    standalone_path = output_dir / "06_Trail_Red_Insert_SeparatePrint.stl"
    select_only([standalone_trail])
    export_selected(standalone_path)
    standalone_bounds = world_bounds(standalone_trail)

    report = {
        "source_blend": bpy.data.filepath,
        "assembly_instruction": (
            "Import 01, 03, 04 and optional 05 together as one object with "
            "multiple parts. Do not auto-arrange the parts. Part 02 is only "
            "an aligned assembly reference for the red insert."
        ),
        "separate_trail_instruction": (
            "Print 06 by itself with its flat bottom on the build plate, "
            "then press or glue it into the terrain groove."
        ),
        "parts": [
            {"name": "Terrain_Grooved", "file": str(terrain_path), "quality": quality(terrain)},
            {"name": "Trail_Red_Insert_Aligned", "file": str(trail_aligned_path), "quality": quality(trail)},
            {"name": "Water_Blue", "file": str(water_path), "quality": quality(water)},
            {"name": "Roads_Dark", "file": str(road_path), "quality": quality(road)},
            *(
                [
                    {
                        "name": "Villages_Warm",
                        "file": str(village_path),
                        "quality": quality(village),
                    }
                ]
                if village is not None
                else []
            ),
            {
                "name": "Trail_Red_Insert_SeparatePrint",
                "file": str(standalone_path),
                "quality": quality(standalone_trail),
                "world_bounds_after_layout": [
                    round(value, 4) for value in standalone_bounds
                ],
            },
        ],
    }
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print("S02_ENRICHED_EXPORT=" + json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
