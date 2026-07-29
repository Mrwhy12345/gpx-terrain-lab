#!/usr/bin/env python3
"""Add a printable display base and raised Chinese title to the S02 terrain."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import bmesh
import bpy
import math


BASE_WIDTH_MM = 130.0
BASE_HEIGHT_MM = 105.0
BASE_THICKNESS_MM = 4.0
BASE_EDGE_BEVEL_MM = 1.2
MAGNET_DIAMETER_MM = 5.3
MAGNET_POCKET_DEPTH_MM = 3.2
MAGNET_ROOF_MM = BASE_THICKNESS_MM - MAGNET_POCKET_DEPTH_MM
TITLE = "7月12日，星溪竹林徒步"
TITLE_MAX_WIDTH_MM = 62.0
TITLE_MAX_HEIGHT_MM = 6.0
TITLE_RAISE_MM = 0.6
TITLE_BAND_CENTER_OFFSET_Y_MM = -47.0
FONT_CANDIDATES = (
    Path("/System/Library/Fonts/STHeiti Medium.ttc"),
    Path("/System/Library/Fonts/STHeiti Light.ttc"),
    Path("/System/Library/Fonts/Supplemental/Songti.ttc"),
)


def mesh_quality(obj):
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
    return {
        axis: [min(point[i] for point in points), max(point[i] for point in points)]
        for i, axis in enumerate(("x", "y", "z"))
    }


def set_material(obj, name, color):
    material = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    material.diffuse_color = (*color, 1.0)
    obj.data.materials.clear()
    obj.data.materials.append(material)


def recalculate_normals(obj):
    editable = bmesh.new()
    editable.from_mesh(obj.data)
    bmesh.ops.recalc_face_normals(editable, faces=editable.faces)
    editable.to_mesh(obj.data)
    editable.free()


def boolean_difference(target, cutter):
    modifier = target.modifiers.new("Magnet pocket", "BOOLEAN")
    modifier.operation = "DIFFERENCE"
    modifier.solver = "EXACT"
    modifier.object = cutter
    bpy.context.view_layer.objects.active = target
    bpy.ops.object.modifier_apply(modifier=modifier.name)


def create_base(center_x, center_y):
    half_width = BASE_WIDTH_MM / 2
    half_height = BASE_HEIGHT_MM / 2
    lower_width = BASE_WIDTH_MM / 4
    outline = [
        (-lower_width, -half_height),
        (lower_width, -half_height),
        (half_width, 0),
        (lower_width, half_height),
        (-lower_width, half_height),
        (-half_width, 0),
    ]
    vertices = [
        (center_x + x, center_y + y, z)
        for z in (-BASE_THICKNESS_MM, 0.0)
        for x, y in outline
    ]
    faces = [
        tuple(reversed(range(6))),
        tuple(range(6, 12)),
        *((i, (i + 1) % 6, 6 + (i + 1) % 6, 6 + i) for i in range(6)),
    ]
    mesh = bpy.data.meshes.new("S02_Display_Base_Mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    base = bpy.data.objects.new("S02_Display_Base_Dark", mesh)
    bpy.context.scene.collection.objects.link(base)
    base.name = "S02_Display_Base_Dark"
    recalculate_normals(base)
    bevel = base.modifiers.new("Printable rounded corners", "BEVEL")
    bevel.width = BASE_EDGE_BEVEL_MM
    bevel.segments = 4
    bevel.affect = "EDGES"
    bpy.context.view_layer.objects.active = base
    bpy.ops.object.modifier_apply(modifier=bevel.name)

    magnet_centers = [
        (center_x - 26.5, center_y - 43.0),
        (center_x + 26.5, center_y - 43.0),
        (center_x + 53.0, center_y),
        (center_x + 26.5, center_y + 43.0),
        (center_x - 26.5, center_y + 43.0),
        (center_x - 53.0, center_y),
    ]
    cutters = []
    pocket_center_z = -BASE_THICKNESS_MM + MAGNET_POCKET_DEPTH_MM / 2 - 0.05
    for index, (x, y) in enumerate(magnet_centers, start=1):
        bpy.ops.mesh.primitive_cylinder_add(
            vertices=48,
            radius=MAGNET_DIAMETER_MM / 2,
            depth=MAGNET_POCKET_DEPTH_MM + 0.1,
            location=(x, y, pocket_center_z),
        )
        cutter = bpy.context.object
        cutter.name = f"S02_Magnet_Pocket_{index:02d}"
        cutters.append(cutter)
        boolean_difference(base, cutter)
        bpy.data.objects.remove(cutter, do_unlink=True)
    recalculate_normals(base)
    base["S05_geometry"] = "display_base"
    base["Magnet specification"] = "6 pockets for 5x3 mm round magnets"
    base["Magnet pocket diameter mm"] = MAGNET_DIAMETER_MM
    base["Magnet pocket depth mm"] = MAGNET_POCKET_DEPTH_MM
    set_material(base, "S05_Dark_Base", (0.025, 0.03, 0.04))
    return base, magnet_centers


def create_title(center_x, center_y):
    font_path = next((path for path in FONT_CANDIDATES if path.exists()), None)
    if font_path is None:
        raise FileNotFoundError("No supported Chinese font found")
    curve = bpy.data.curves.new("S02_Title_Curve", "FONT")
    curve.body = TITLE
    curve.align_x = "CENTER"
    curve.align_y = "CENTER"
    curve.size = 6.0
    curve.extrude = 0.3
    curve.resolution_u = 8
    curve.font = bpy.data.fonts.load(str(font_path))
    title = bpy.data.objects.new("S02_Title_Warm", curve)
    bpy.context.scene.collection.objects.link(title)
    title.location = (
        center_x,
        center_y + TITLE_BAND_CENTER_OFFSET_Y_MM,
        0.0,
    )
    bpy.context.view_layer.objects.active = title
    title.select_set(True)
    bpy.ops.object.convert(target="MESH")

    bounds = world_bounds(title)
    width = bounds["x"][1] - bounds["x"][0]
    height = bounds["y"][1] - bounds["y"][0]
    scale = min(TITLE_MAX_WIDTH_MM / width, TITLE_MAX_HEIGHT_MM / height)
    title.scale.x *= scale
    title.scale.y *= scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

    bounds = world_bounds(title)
    current_depth = bounds["z"][1] - bounds["z"][0]
    title.scale.z *= TITLE_RAISE_MM / current_depth
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    bounds = world_bounds(title)
    title.location.z -= bounds["z"][0]
    bpy.context.view_layer.update()
    # Converted font outlines may contain overlapping caps and open boundaries.
    # A fine voxel remesh turns the complete inscription into closed printable
    # shells while retaining strokes suitable for a 0.4 mm nozzle.
    title.data.remesh_voxel_size = 0.08
    title.data.remesh_voxel_adaptivity = 0.0
    bpy.context.view_layer.objects.active = title
    bpy.ops.object.voxel_remesh()
    bpy.context.view_layer.update()
    title["S05_geometry"] = "display_title"
    title["Title"] = TITLE
    title["Font"] = str(font_path)
    set_material(title, "S05_Warm_Title", (0.88, 0.68, 0.38))
    return title, font_path


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
    center_x, center_y = terrain.location.x, terrain.location.y
    base, magnet_centers = create_base(center_x, center_y)
    title, font_path = create_title(center_x, center_y)
    report = {
        "source_blend": bpy.data.filepath,
        "output_blend": str(output_blend),
        "title": TITLE,
        "font": str(font_path),
        "base": {
            "width_mm": BASE_WIDTH_MM,
            "height_mm": BASE_HEIGHT_MM,
            "thickness_mm": BASE_THICKNESS_MM,
            "edge_bevel_mm": BASE_EDGE_BEVEL_MM,
            "shape": "hexagon compatible with the referenced medal display",
            "bounds": world_bounds(base),
            "quality": mesh_quality(base),
        },
        "magnets": {
            "reference_nominal_size_mm": [5.0, 3.0],
            "pocket_diameter_mm": MAGNET_DIAMETER_MM,
            "pocket_depth_mm": MAGNET_POCKET_DEPTH_MM,
            "remaining_roof_mm": MAGNET_ROOF_MM,
            "count": len(magnet_centers),
            "centers_xy": magnet_centers,
            "installation": "insert from underside; glue is recommended",
        },
        "raised_title": {
            "max_width_mm": TITLE_MAX_WIDTH_MM,
            "max_height_mm": TITLE_MAX_HEIGHT_MM,
            "raise_mm": TITLE_RAISE_MM,
            "bounds": world_bounds(title),
            "quality": mesh_quality(title),
        },
        "filament_reuse": {
            "base": "same dark filament as roads",
            "title": "same warm filament as villages",
        },
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    bpy.ops.wm.save_as_mainfile(filepath=str(output_blend))
    print("DISPLAY_BASE_TITLE=" + json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
