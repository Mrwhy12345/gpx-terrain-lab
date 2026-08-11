#!/usr/bin/env python3
"""Build a three-band printable terrain model without rescaling tested elevation."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import bmesh
import bpy


VERTICAL_FACTOR = 1.00
BROWN_START = 0.52
GRAY_START = 0.74


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


def world_bounds(obj):
    points = [obj.matrix_world @ vertex.co for vertex in obj.data.vertices]
    if not points:
        raise RuntimeError(f"Cannot measure empty mesh: {obj.name}")
    return {
        axis: [min(point[i] for point in points), max(point[i] for point in points)]
        for i, axis in enumerate(("x", "y", "z"))
    }


def recalculate_normals(obj):
    editable = bmesh.new()
    editable.from_mesh(obj.data)
    bmesh.ops.recalc_face_normals(editable, faces=editable.faces)
    editable.to_mesh(obj.data)
    editable.free()


def assign_material(obj, name, color):
    material = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    material.diffuse_color = (*color, 1.0)
    obj.data.materials.clear()
    obj.data.materials.append(material)


def intersection_box(name, bounds, min_z, max_z):
    center_x = sum(bounds["x"]) / 2
    center_y = sum(bounds["y"]) / 2
    width = bounds["x"][1] - bounds["x"][0] + 4
    height = bounds["y"][1] - bounds["y"][0] + 4
    depth = max_z - min_z
    bpy.ops.mesh.primitive_cube_add(
        location=(center_x, center_y, (min_z + max_z) / 2)
    )
    box = bpy.context.object
    box.name = name
    box.dimensions = (width, height, depth)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    return box


def intersect_copy(source, name, tag, min_z, max_z, color):
    result = source.copy()
    result.data = source.data.copy()
    result.name = name
    bpy.context.scene.collection.objects.link(result)
    bounds = world_bounds(source)
    box = intersection_box(name + "_Cutter", bounds, min_z, max_z)
    modifier = result.modifiers.new("Elevation band intersection", "BOOLEAN")
    modifier.operation = "INTERSECT"
    modifier.solver = "MANIFOLD"
    modifier.object = box
    bpy.context.view_layer.objects.active = result
    result.select_set(True)
    bpy.ops.object.modifier_apply(modifier=modifier.name)
    result.select_set(False)
    bpy.data.objects.remove(box, do_unlink=True)
    recalculate_normals(result)
    if not result.data.vertices:
        raise RuntimeError(f"Elevation band {name} is empty after intersection")
    result["Object type"] = tag
    result["S06_geometry"] = tag.lower()
    result["Vertical factor"] = VERTICAL_FACTOR
    assign_material(result, name + "_Material", color)
    return result


def main():
    args = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    if len(args) != 2:
        raise SystemExit(
            "Usage: blender INPUT.blend --python script.py -- OUTPUT.blend REPORT.json"
        )
    output_blend, report_path = map(Path, args)
    terrain = next(
        obj for obj in bpy.context.scene.objects if obj.get("Object type") == "MAP"
    )

    roads = [
        obj
        for obj in list(bpy.context.scene.objects)
        if obj.get("S03_geometry") == "roads_printable"
    ]
    removed_roads = [obj.name for obj in roads]
    for road in roads:
        bpy.data.objects.remove(road, do_unlink=True)

    scaled_objects = [
        obj
        for obj in bpy.context.scene.objects
        if obj.type == "MESH"
        and (
            obj == terrain
            or obj.get("Object type") in {"TRAIL", "TRAIL_INSERT"}
            or obj.get("Object type") in {"WATER", "OCEAN"}
            or obj.get("S02_geometry") in {"stream_ribbon", "water_area"}
            or obj.get("S04_geometry") == "residential_areas_printable"
        )
    ]
    for obj in scaled_objects:
        for vertex in obj.data.vertices:
            vertex.co.z *= VERTICAL_FACTOR
        obj.data.update()

    bounds = world_bounds(terrain)
    min_z, max_z = bounds["z"]
    brown_z = min_z + (max_z - min_z) * BROWN_START
    gray_z = min_z + (max_z - min_z) * GRAY_START
    epsilon = 0.001
    low = intersect_copy(
        terrain,
        "S06_Terrain_Low_Green",
        "TERRAIN_LOW_GREEN",
        min_z - 1,
        brown_z,
        (0.28, 0.43, 0.10),
    )
    middle = intersect_copy(
        terrain,
        "S06_Terrain_Middle_Brown",
        "TERRAIN_MIDDLE_BROWN",
        brown_z - epsilon,
        gray_z,
        (0.43, 0.26, 0.10),
    )
    high = intersect_copy(
        terrain,
        "S06_Terrain_High_Gray",
        "TERRAIN_HIGH_GRAY",
        gray_z - epsilon,
        max_z + 1,
        (0.47, 0.51, 0.54),
    )
    bpy.data.objects.remove(terrain, do_unlink=True)

    bands = [low, middle, high]
    report = {
        "source_blend": bpy.data.filepath,
        "output_blend": str(output_blend),
        "vertical_factor": VERTICAL_FACTOR,
        "roads_removed": removed_roads,
        "thresholds": {
            "brown_fraction": BROWN_START,
            "brown_z_mm": brown_z,
            "gray_fraction": GRAY_START,
            "gray_z_mm": gray_z,
        },
        "bands": [
            {
                "name": obj.name,
                "bounds": world_bounds(obj),
                "quality": quality(obj),
            }
            for obj in bands
        ],
        "scaled_objects": [obj.name for obj in scaled_objects if obj != terrain],
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    bpy.ops.wm.save_as_mainfile(filepath=str(output_blend))
    print("THREE_BAND_PRINT_MODEL=" + json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
