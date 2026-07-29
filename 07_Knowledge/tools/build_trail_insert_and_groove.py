#!/usr/bin/env python3
"""Convert the S02 trail to a flat-bottom insert and carve its groove."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import bmesh
import bpy
from bl_ext.user_default.trailprint3d.utils.mesh_ops import (
    boolean_operation,
    single_color_mode_curve,
)


PATH_THICKNESS_MM = 1.4
SIDE_TOLERANCE_MM = 0.2
CUT_DEPTH_MM = 1.0


def quality(obj):
    editable = bmesh.new()
    editable.from_mesh(obj.data)
    result = {
        "vertices": len(editable.verts),
        "edges": len(editable.edges),
        "faces": len(editable.faces),
        "non_manifold_edges": sum(not edge.is_manifold for edge in editable.edges),
        "min_z": min((vertex.co.z for vertex in editable.verts), default=None),
        "max_z": max((vertex.co.z for vertex in editable.verts), default=None),
    }
    editable.free()
    return result


def main():
    arguments = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    if len(arguments) != 2:
        raise SystemExit(
            "Usage: blender INPUT.blend --python script.py -- "
            "OUTPUT.blend REPORT.json"
        )
    output_blend, report_path = map(Path, arguments)

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
    roads = [
        obj
        for obj in bpy.context.scene.objects
        if obj.get("S03_geometry") == "roads_printable"
    ]

    scene_props = bpy.context.scene.tp3d
    scene_props.pathThickness = PATH_THICKNESS_MM
    scene_props.tolerance = SIDE_TOLERANCE_MM

    # The TrailPrint3D SCM helper expects the cursor at the owning map.
    bpy.context.scene.cursor.location = terrain.location

    projection = terrain.copy()
    projection.data = terrain.data.copy()
    projection.name = f"{terrain.name}_Projection_Copy"
    bpy.context.scene.collection.objects.link(projection)

    result = single_color_mode_curve(
        trail,
        terrain,
        keepTolTrail=True,
        cutDepth=CUT_DEPTH_MM,
        projectionObj=projection,
    )
    bpy.data.objects.remove(projection, do_unlink=True)
    if result is None:
        raise RuntimeError("TrailPrint3D single-color trail conversion failed")
    trail_insert, groove_cutter = result
    if groove_cutter is None:
        raise RuntimeError("TrailPrint3D did not return a groove cutter")

    trail_insert.name = "S02_Trail_Red_Insert"
    trail_insert["Object type"] = "TRAIL_INSERT"
    trail_insert["S03_geometry"] = "trail_insert"
    red = bpy.data.materials.get("Trail_Red_Insert")
    if red is None:
        red = bpy.data.materials.new("Trail_Red_Insert")
    red.diffuse_color = (0.9, 0.03, 0.02, 1.0)
    trail_insert.data.materials.clear()
    trail_insert.data.materials.append(red)

    # The route is the highest-priority visual element.  Remove its tolerance
    # volume from water and roads too, so the separately printed insert can
    # seat through every crossing without another coloured part blocking it.
    cut_targets = []
    for obj in [*waters, *roads]:
        before = len(obj.data.vertices)
        boolean_operation(obj, groove_cutter, "DIFFERENCE")
        after = len(obj.data.vertices)
        cut_targets.append(
            {
                "name": obj.name,
                "vertices_before": before,
                "vertices_after": after,
                "removed_as_fully_overlapped": after == 0,
            }
        )
        if after == 0:
            bpy.data.objects.remove(obj, do_unlink=True)

    cutter_collection = bpy.data.collections.get("S03_Cutters")
    if cutter_collection is None:
        cutter_collection = bpy.data.collections.new("S03_Cutters")
        bpy.context.scene.collection.children.link(cutter_collection)
    for collection in list(groove_cutter.users_collection):
        collection.objects.unlink(groove_cutter)
    cutter_collection.objects.link(groove_cutter)
    groove_cutter.name = "S02_Trail_Groove_Cutter"
    groove_cutter.hide_render = True
    groove_cutter.hide_set(True)

    bpy.ops.wm.save_as_mainfile(filepath=str(output_blend))
    report = {
        "source_blend": bpy.data.filepath,
        "parameters": {
            "path_thickness_mm": PATH_THICKNESS_MM,
            "side_tolerance_mm_each_side": SIDE_TOLERANCE_MM,
            "cut_depth_mm": CUT_DEPTH_MM,
            "insert_print_orientation": "flat bottom on build plate",
        },
        "terrain": quality(terrain),
        "trail_insert": quality(trail_insert),
        "groove_cutter": quality(groove_cutter),
        "additional_cut_targets": cut_targets,
    }
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print("S03_TRAIL_INSERT_REPORT=" + json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
