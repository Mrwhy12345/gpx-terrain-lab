#!/usr/bin/env python3
"""Replace the display base with a thicker version and a terrain locating recess."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import bmesh
import bpy


BASE_WIDTH_MM = 130.0
BASE_HEIGHT_MM = 105.0
BASE_THICKNESS_MM = 8.0
BASE_EDGE_BEVEL_MM = 1.2
MAGNET_DIAMETER_MM = 5.3
MAGNET_POCKET_DEPTH_MM = 3.2
RECESS_DEPTH_MM = 0.8
RECESS_CLEARANCE_MM = 0.30


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


def recalculate_normals(obj):
    editable = bmesh.new()
    editable.from_mesh(obj.data)
    bmesh.ops.recalc_face_normals(editable, faces=editable.faces)
    editable.to_mesh(obj.data)
    editable.free()


def boolean_difference(target, cutter, label):
    modifier = target.modifiers.new(label, "BOOLEAN")
    modifier.operation = "DIFFERENCE"
    modifier.solver = "EXACT"
    modifier.object = cutter
    bpy.context.view_layer.objects.active = target
    bpy.ops.object.modifier_apply(modifier=modifier.name)
    bpy.data.objects.remove(cutter, do_unlink=True)


def hex_prism(name, center_x, center_y, width, height, z_min, z_max):
    half_width = width / 2
    half_height = height / 2
    lower_width = width / 4
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
        for z in (z_min, z_max)
        for x, y in outline
    ]
    faces = [
        tuple(reversed(range(6))),
        tuple(range(6, 12)),
        *((i, (i + 1) % 6, 6 + (i + 1) % 6, 6 + i) for i in range(6)),
    ]
    mesh = bpy.data.meshes.new(name + "_Mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    recalculate_normals(obj)
    return obj


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
    old_base = next(
        obj
        for obj in bpy.context.scene.objects
        if obj.get("S05_geometry") == "display_base"
    )
    terrain_bounds = bounds(terrain)
    center_x = sum(terrain_bounds["x"]) / 2
    center_y = sum(terrain_bounds["y"]) / 2

    material = old_base.data.materials[0] if old_base.data.materials else None
    bpy.data.objects.remove(old_base, do_unlink=True)

    base = hex_prism(
        "S08_Display_Base_With_Terrain_Recess",
        center_x,
        center_y,
        BASE_WIDTH_MM,
        BASE_HEIGHT_MM,
        -BASE_THICKNESS_MM,
        0.0,
    )
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
    # Keep the six pockets accessible from the underside. The thicker base
    # leaves a robust roof below the terrain recess without requiring a print
    # pause to embed the magnets.
    pocket_center_z = (
        -BASE_THICKNESS_MM + MAGNET_POCKET_DEPTH_MM / 2 - 0.05
    )
    for index, (x, y) in enumerate(magnet_centers, start=1):
        bpy.ops.mesh.primitive_cylinder_add(
            vertices=48,
            radius=MAGNET_DIAMETER_MM / 2,
            depth=MAGNET_POCKET_DEPTH_MM + 0.1,
            location=(x, y, pocket_center_z),
        )
        boolean_difference(base, bpy.context.object, f"Magnet pocket {index}")

    terrain_width = terrain_bounds["x"][1] - terrain_bounds["x"][0]
    terrain_height = terrain_bounds["y"][1] - terrain_bounds["y"][0]
    recess = hex_prism(
        "S08_Terrain_Seat_Recess_Cutter",
        center_x,
        center_y,
        terrain_width + 2 * RECESS_CLEARANCE_MM,
        terrain_height + 2 * RECESS_CLEARANCE_MM,
        -RECESS_DEPTH_MM,
        0.1,
    )
    boolean_difference(base, recess, "Terrain locating recess")
    recalculate_normals(base)

    if material is not None:
        base.data.materials.append(material)
    base["S05_geometry"] = "display_base"
    base["S08_geometry"] = "terrain_seat_recess"
    base["Base thickness mm"] = BASE_THICKNESS_MM
    base["Terrain recess depth mm"] = RECESS_DEPTH_MM
    base["Terrain recess XY clearance mm"] = RECESS_CLEARANCE_MM
    base["Magnet specification"] = "6 pockets for 5x3 mm round magnets"
    base["Magnet pocket diameter mm"] = MAGNET_DIAMETER_MM
    base["Magnet pocket depth mm"] = MAGNET_POCKET_DEPTH_MM
    base["Magnet installation"] = "insert from underside after printing"

    report = {
        "source_blend": bpy.data.filepath,
        "output_blend": str(output_blend),
        "base": {
            "external_size_mm": [BASE_WIDTH_MM, BASE_HEIGHT_MM],
            "thickness_mm": BASE_THICKNESS_MM,
            "bounds": bounds(base),
            "quality": quality(base),
        },
        "terrain_seat": {
            "terrain_footprint_mm": [terrain_width, terrain_height],
            "recess_footprint_mm": [
                terrain_width + 2 * RECESS_CLEARANCE_MM,
                terrain_height + 2 * RECESS_CLEARANCE_MM,
            ],
            "depth_mm": RECESS_DEPTH_MM,
            "clearance_each_side_mm": RECESS_CLEARANCE_MM,
        },
        "magnet_pockets": {
            "count": len(magnet_centers),
            "diameter_mm": MAGNET_DIAMETER_MM,
            "depth_mm": MAGNET_POCKET_DEPTH_MM,
            "material_between_pocket_and_recess_mm": (
                BASE_THICKNESS_MM
                - MAGNET_POCKET_DEPTH_MM
                - RECESS_DEPTH_MM
            ),
            "installation": "insert from underside after printing; glue recommended",
        },
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    bpy.ops.wm.save_as_mainfile(filepath=str(output_blend))
    print("TERRAIN_SEAT_RECESS=" + json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
