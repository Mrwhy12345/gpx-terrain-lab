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


PATH_THICKNESS_MM = 1.6
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


def flatten_bottom(obj):
    """Create a common printable underside while preserving the terrain top."""
    editable = bmesh.new(); editable.from_mesh(obj.data); editable.normal_update()
    bottom_vertices = {vertex for face in editable.faces if face.normal.z < -0.35 for vertex in face.verts}
    if not bottom_vertices:
        editable.free(); raise RuntimeError(f"Recovered trail has no downward faces: {obj.name}")
    bottom_z = min(vertex.co.z for vertex in bottom_vertices)
    for vertex in bottom_vertices: vertex.co.z = bottom_z
    bmesh.ops.remove_doubles(editable, verts=editable.verts, dist=1e-6)
    bmesh.ops.dissolve_degenerate(editable, edges=editable.edges, dist=1e-6)
    bmesh.ops.recalc_face_normals(editable, faces=editable.faces)
    editable.to_mesh(obj.data); editable.free(); obj.data.update()
    return bottom_z, len(bottom_vertices)


def expanded_copy(source, name, clearance):
    result=source.copy(); result.data=source.data.copy(); result.name=name; bpy.context.scene.collection.objects.link(result)
    editable=bmesh.new(); editable.from_mesh(result.data); editable.normal_update()
    for vertex in editable.verts: vertex.co += vertex.normal * clearance
    bmesh.ops.recalc_face_normals(editable, faces=editable.faces)
    editable.to_mesh(result.data); editable.free(); result.data.update(); return result


def main():
    arguments = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    if len(arguments) not in {2, 3}:
        raise SystemExit(
            "Usage: blender INPUT.blend --python script.py -- "
            "OUTPUT.blend REPORT.json [JOB.json]"
        )
    output_blend, report_path = map(Path, arguments[:2])
    path_thickness = PATH_THICKNESS_MM
    side_tolerance = SIDE_TOLERANCE_MM
    if len(arguments) == 3:
        job = json.loads(Path(arguments[2]).read_text(encoding="utf-8"))
        engineering = job.get("engineering", {})
        path_thickness = float(engineering.get("path_thickness_mm", path_thickness))
        side_tolerance = float(engineering.get("trail_slot_clearance_mm", side_tolerance))

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
        if (
            obj.get("Object type") in {"WATER", "OCEAN"}
            or obj.get("S02_geometry") in {"stream_ribbon", "water_area"}
        )
    ]
    roads = [
        obj
        for obj in bpy.context.scene.objects
        if obj.get("S03_geometry") == "roads_printable"
    ]

    scene_props = bpy.context.scene.tp3d
    scene_props.pathThickness = path_thickness
    scene_props.tolerance = side_tolerance

    # Preserve a narrow continuous core before TrailPrint3D converts the curve
    # into terrain-following shells.  The conversion can split one spline at
    # steep/degenerate projection locations; this core follows the original
    # spline and remains entirely inside the visible 1.6 mm trail.
    continuity_core = trail.copy()
    continuity_core.data = trail.data.copy()
    continuity_core.name = "Trail_Continuity_Core"
    # The core is a structural spine, not merely a topology bridge.  The
    # previous 0.42 mm radius produced a printable one-piece route but the
    # 0.84 mm neck fractured during real installation.  Keep most of the
    # verified 1.60 mm QGIS/TrailPrint visual width as load-bearing material.
    continuity_core.data.bevel_depth = min(path_thickness * 0.425, 0.68)
    continuity_core.data.bevel_resolution = 2
    continuity_core.data.resolution_u = max(2, continuity_core.data.resolution_u)
    continuity_core.data.use_fill_caps = True
    continuity_core["S03_geometry"] = "trail_continuity_core"
    continuity_core["print_role"] = "hidden_inside_trail"
    bpy.context.scene.collection.objects.link(continuity_core)

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
    conversion_returned_none = result is None
    recovery_bottom = None
    if result is None:
        # Regional routes can collapse during TrailPrint's voxel/boolean step
        # even though the preserved GPX-following spine is valid. Recover from
        # that spine and derive the slot from the exact recovered insert.
        trail_insert = continuity_core.copy()
        trail_insert.data = continuity_core.data.copy()
        bpy.context.scene.collection.objects.link(trail_insert)
        groove_cutter = None
    else:
        trail_insert, groove_cutter = result
        if groove_cutter is None:
            raise RuntimeError("TrailPrint3D did not return a groove cutter")

    # TrailPrint3D can return a nominal object whose projected shell has
    # collapsed to one vertex on some valid single-segment GPX routes.  Treat
    # that as a failed conversion and recover from the preserved route-following
    # structural spine.  This follows the GPX exactly and never adds a straight
    # cross-terrain bridge; the TrailPrint3D groove cutter remains authoritative.
    recovered_from_core = conversion_returned_none or len(trail_insert.data.vertices) < 3 or len(trail_insert.data.polygons) == 0
    if recovered_from_core:
        bpy.data.objects.remove(trail_insert, do_unlink=True)
        trail_insert = continuity_core.copy()
        trail_insert.data = continuity_core.data.copy()
        bpy.context.scene.collection.objects.link(trail_insert)
        bpy.ops.object.select_all(action="DESELECT")
        trail_insert.select_set(True)
        bpy.context.view_layer.objects.active = trail_insert
        bpy.ops.object.convert(target="MESH")
        recovery_bottom = flatten_bottom(trail_insert)
        # The recovered insert is deeper than TrailPrint3D's collapsed shell;
        # derive a new groove from the final printable geometry and recut the
        # terrain so print part and receiving slot remain exactly homologous.
        if groove_cutter is not None:
            bpy.data.objects.remove(groove_cutter, do_unlink=True)
        groove_cutter = expanded_copy(trail_insert, "Recovered_Trail_Groove_Cutter", side_tolerance)
        boolean_operation(terrain, groove_cutter, "DIFFERENCE")

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
            "path_thickness_mm": path_thickness,
            "side_tolerance_mm_each_side": side_tolerance,
            "cut_depth_mm": CUT_DEPTH_MM,
            "insert_print_orientation": "flat bottom on build plate",
        },
        "terrain": quality(terrain),
        "trail_insert": quality(trail_insert),
        "groove_cutter": quality(groove_cutter),
        "continuity_core": {
            "name": continuity_core.name,
            "type": continuity_core.type,
            "splines": len(continuity_core.data.splines),
            "bevel_depth_mm": continuity_core.data.bevel_depth,
        },
        "trailprint_shell_recovery": {
            "used": recovered_from_core,
            "conversion_returned_none": conversion_returned_none,
            "method": "preserved_route_following_structural_spine",
            "straight_cross_terrain_bridges": 0,
            "common_bottom_z": recovery_bottom[0] if recovery_bottom else None,
            "bottom_vertex_count": recovery_bottom[1] if recovery_bottom else None,
            "slot_rebuilt_from_final_insert": recovered_from_core,
        },
        "additional_cut_targets": cut_targets,
    }
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print("S03_TRAIL_INSERT_REPORT=" + json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
