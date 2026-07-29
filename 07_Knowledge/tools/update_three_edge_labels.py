#!/usr/bin/env python3
"""Place route title, date, and distance on three display-base edges."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import bmesh
import bpy


# Hiragino Sans GB has complete Simplified Chinese glyph outlines and produces
# clean, relatively heavy strokes at small printed sizes.
FONT = Path("/System/Library/Fonts/Hiragino Sans GB.ttc")
RAISE_MM = 0.6
EDGE_INSET_MM = 11.5
LABELS = (
    ("星溪徒步", 0.0, (0.0, 1.0), 32.0, 4.2),
    ("2026.07.12", math.radians(-58.24), (-0.85, -0.526), 31.0, 3.8),
    ("9.5 KM", math.radians(58.24), (0.85, -0.526), 24.0, 4.2),
)


def world_bounds(obj):
    points = [obj.matrix_world @ vertex.co for vertex in obj.data.vertices]
    return [
        [min(point[i] for point in points), max(point[i] for point in points)]
        for i in range(3)
    ]


def quality(obj):
    mesh = bmesh.new()
    mesh.from_mesh(obj.data)
    result = {
        "vertices": len(mesh.verts),
        "faces": len(mesh.faces),
        "non_manifold_edges": sum(not edge.is_manifold for edge in mesh.edges),
    }
    mesh.free()
    return result


def world_xy(obj):
    return [(obj.matrix_world @ vertex.co).xy for vertex in obj.data.vertices]


def normalized(vector):
    length = math.hypot(*vector)
    return (vector[0] / length, vector[1] / length)


def edge_band_center(base, scene_center, rotation, outward):
    """Return the printable band center on a base edge.

    The position is derived from the final base mesh rather than hard-coded
    offsets.  Near-support vertices establish the actual tangent midpoint.
    """
    outward = normalized(outward)
    tangent = (math.cos(rotation), math.sin(rotation))
    points = [
        (point.x - scene_center[0], point.y - scene_center[1])
        for point in world_xy(base)
    ]
    support = max(point[0] * outward[0] + point[1] * outward[1] for point in points)
    near = [
        point
        for point in points
        if support - (point[0] * outward[0] + point[1] * outward[1]) <= 0.8
    ]
    tangent_values = [point[0] * tangent[0] + point[1] * tangent[1] for point in near]
    tangent_midpoint = (min(tangent_values) + max(tangent_values)) / 2
    normal_position = support - EDGE_INSET_MM
    return (
        scene_center[0] + tangent_midpoint * tangent[0] + normal_position * outward[0],
        scene_center[1] + tangent_midpoint * tangent[1] + normal_position * outward[1],
    )


def oriented_bounds_center(obj, rotation):
    tangent = (math.cos(rotation), math.sin(rotation))
    normal = (-math.sin(rotation), math.cos(rotation))
    points = world_xy(obj)
    tangent_values = [point.x * tangent[0] + point.y * tangent[1] for point in points]
    normal_values = [point.x * normal[0] + point.y * normal[1] for point in points]
    tangent_center = (min(tangent_values) + max(tangent_values)) / 2
    normal_center = (min(normal_values) + max(normal_values)) / 2
    return (
        tangent_center * tangent[0] + normal_center * normal[0],
        tangent_center * tangent[1] + normal_center * normal[1],
    )


def create_label(text, target, rotation, max_width, max_height):
    curve = bpy.data.curves.new(f"Label_{text}", "FONT")
    curve.body = text
    curve.align_x = "CENTER"
    curve.align_y = "CENTER"
    curve.size = 6.0
    curve.extrude = 0.3
    # Slight outline expansion preserves Chinese strokes at a 0.4 mm nozzle.
    curve.offset = 0.12
    curve.resolution_u = 8
    curve.font = bpy.data.fonts.load(str(FONT))
    obj = bpy.data.objects.new(f"Label_{text}", curve)
    bpy.context.scene.collection.objects.link(obj)
    obj.location = (target[0], target[1], 0.0)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.convert(target="MESH")
    bounds = world_bounds(obj)
    width = bounds[0][1] - bounds[0][0]
    height = bounds[1][1] - bounds[1][0]
    scale = min(max_width / width, max_height / height)
    obj.scale.x *= scale
    obj.scale.y *= scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    bounds = world_bounds(obj)
    depth = bounds[2][1] - bounds[2][0]
    obj.scale.z *= RAISE_MM / depth
    obj.rotation_euler.z = rotation
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    bounds = world_bounds(obj)
    obj.location.z -= bounds[2][0]
    obj.data.remesh_voxel_size = 0.08
    obj.data.remesh_voxel_adaptivity = 0.0
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.voxel_remesh()
    # Voxel remesh and glyph asymmetry can shift the final visual bounds.
    # Recenter the finished mesh, not merely the pre-conversion font origin.
    actual_center = oriented_bounds_center(obj, rotation)
    obj.location.x += target[0] - actual_center[0]
    obj.location.y += target[1] - actual_center[1]
    bpy.context.view_layer.update()
    corrected_center = oriented_bounds_center(obj, rotation)
    return obj, {
        "text": text,
        "rotation_deg": round(math.degrees(rotation), 4),
        "target_center": [round(target[0], 6), round(target[1], 6)],
        "actual_center": [round(corrected_center[0], 6), round(corrected_center[1], 6)],
        "centering_error_mm": round(math.dist(target, corrected_center), 6),
    }


def main():
    args = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    if len(args) != 3:
        raise SystemExit("Expected OUTPUT.blend REPORT.json TITLE.stl")
    output_blend, report_path, title_stl = map(Path, args)
    terrain = next(
        obj for obj in bpy.context.scene.objects
        if obj.get("Object type") == "TERRAIN_LOW_GREEN"
    )
    center_x, center_y = terrain.location.x, terrain.location.y
    base = next(
        obj
        for obj in bpy.context.scene.objects
        if obj.get("S05_geometry") == "display_base"
    )
    for obj in list(bpy.context.scene.objects):
        if obj.get("S05_geometry") == "display_title":
            bpy.data.objects.remove(obj, do_unlink=True)
    created = []
    for text, rotation, outward, width, height in LABELS:
        target = edge_band_center(
            base, (center_x, center_y), rotation, outward
        )
        created.append(create_label(text, target, rotation, width, height))
    labels = [item[0] for item in created]
    placements = [item[1] for item in created]
    bpy.ops.object.select_all(action="DESELECT")
    for obj in labels:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = labels[0]
    bpy.ops.object.join()
    title = bpy.context.object
    title.name = "S10_Three_Edge_Labels_Brown"
    title["S05_geometry"] = "display_title"
    title["S10_geometry"] = "three_edge_labels"
    material = bpy.data.materials.get("S10_Label_Brown") or bpy.data.materials.new(
        "S10_Label_Brown"
    )
    material.diffuse_color = (0.43, 0.26, 0.10, 1.0)
    title.data.materials.append(material)
    report = {
        "labels": [label[0] for label in LABELS],
        "font": str(FONT),
        "font_format": "Hiragino Sans GB TTC",
        "outline_offset_mm_before_scaling": 0.12,
        "placement_method": "base_mesh_support_edge_and_final_mesh_bounds",
        "edge_inset_mm": EDGE_INSET_MM,
        "placements": placements,
        "bounds": world_bounds(title),
        "quality": quality(title),
    }
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    bpy.ops.wm.save_as_mainfile(filepath=str(output_blend))
    original_location = title.location.copy()
    title.location.x -= center_x
    title.location.y -= center_y
    bpy.ops.object.select_all(action="DESELECT")
    title.select_set(True)
    bpy.context.view_layer.objects.active = title
    bpy.ops.wm.stl_export(
        filepath=str(title_stl), export_selected_objects=True, ascii_format=False
    )
    title.location = original_location
    print("THREE_EDGE_LABELS=" + json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
