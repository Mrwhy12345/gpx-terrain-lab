#!/usr/bin/env python3
"""Unify disconnected water islands with buried rails below trail crossings."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector


COMMON_BOTTOM_Z = 1.40
RAIL_TOP_Z = 1.90
RAIL_WIDTH_MM = 1.20
CUTTER_CLEARANCE_MM = 0.12
REMESH_VOXEL_MM = 0.08
INSERTION_SWEEP_STEP_MM = 0.50


def bounds(obj):
    points = [obj.matrix_world @ vertex.co for vertex in obj.data.vertices]
    return {
        axis: [min(point[i] for point in points), max(point[i] for point in points)]
        for i, axis in enumerate(("x", "y", "z"))
    }


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


def connected_components(obj):
    mesh = bmesh.new()
    mesh.from_mesh(obj.data)
    remaining = set(mesh.verts)
    count = 0
    while remaining:
        count += 1
        queue = [remaining.pop()]
        while queue:
            vertex = queue.pop()
            for edge in vertex.link_edges:
                other = edge.other_vert(vertex)
                if other in remaining:
                    remaining.remove(other)
                    queue.append(other)
    mesh.free()
    return count


def lower_bottom(obj):
    mesh = bmesh.new()
    mesh.from_mesh(obj.data)
    mesh.normal_update()
    bottom = {
        vertex
        for face in mesh.faces
        if face.normal.z < -0.45
        for vertex in face.verts
    }
    inverse = obj.matrix_world.inverted()
    for vertex in bottom:
        world = obj.matrix_world @ vertex.co
        world.z = COMMON_BOTTOM_Z
        vertex.co = inverse @ world
    bmesh.ops.recalc_face_normals(mesh, faces=mesh.faces)
    mesh.to_mesh(obj.data)
    mesh.free()
    obj.data.update()


def component_nodes(obj):
    mesh = bmesh.new()
    mesh.from_mesh(obj.data)
    remaining = set(mesh.verts)
    nodes = []
    while remaining:
        seed = remaining.pop()
        group = {seed}
        queue = [seed]
        while queue:
            vertex = queue.pop()
            for edge in vertex.link_edges:
                other = edge.other_vert(vertex)
                if other in remaining:
                    remaining.remove(other)
                    group.add(other)
                    queue.append(other)
        bottom = [
            obj.matrix_world @ vertex.co
            for vertex in group
            if abs((obj.matrix_world @ vertex.co).z - COMMON_BOTTOM_Z) < 0.02
        ]
        points = bottom or [obj.matrix_world @ vertex.co for vertex in group]
        center = Vector(
            (
                sum(point.x for point in points) / len(points),
                sum(point.y for point in points) / len(points),
                COMMON_BOTTOM_Z,
            )
        )
        # Anchor at a real bottom vertex so every rail physically intersects.
        anchor = min(points, key=lambda point: (point.x - center.x) ** 2 + (point.y - center.y) ** 2)
        nodes.append(
            {
                "object": obj.name,
                "vertices": len(group),
                "point": Vector((anchor.x, anchor.y, COMMON_BOTTOM_Z)),
            }
        )
    mesh.free()
    return nodes


def minimum_spanning_tree(nodes):
    connected = {0}
    edges = []
    while len(connected) < len(nodes):
        best = None
        for left in connected:
            for right in range(len(nodes)):
                if right in connected:
                    continue
                distance = (nodes[left]["point"].xy - nodes[right]["point"].xy).length
                if best is None or distance < best[0]:
                    best = (distance, left, right)
        edges.append(best)
        connected.add(best[2])
    return edges


def rail_between(name, start, end, width=RAIL_WIDTH_MM, z0=COMMON_BOTTOM_Z, z1=RAIL_TOP_Z):
    midpoint = (start + end) / 2
    length = (end.xy - start.xy).length
    bpy.ops.mesh.primitive_cube_add(location=(midpoint.x, midpoint.y, (z0 + z1) / 2))
    rail = bpy.context.object
    rail.name = name
    rail.dimensions = (length + width, width, z1 - z0)
    rail.rotation_euler.z = math.atan2(end.y - start.y, end.x - start.x)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    return rail


def pad_at(name, point):
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=32,
        radius=RAIL_WIDTH_MM,
        depth=RAIL_TOP_Z - COMMON_BOTTOM_Z,
        location=(point.x, point.y, (RAIL_TOP_Z + COMMON_BOTTOM_Z) / 2),
    )
    pad = bpy.context.object
    pad.name = name
    return pad


def expanded_copy(source):
    result = source.copy()
    result.data = source.data.copy()
    result.name = source.name + "_ClearanceCutter"
    bpy.context.scene.collection.objects.link(result)
    mesh = bmesh.new()
    mesh.from_mesh(result.data)
    mesh.normal_update()
    for vertex in mesh.verts:
        vertex.co += vertex.normal * CUTTER_CLEARANCE_MM
    bmesh.ops.recalc_face_normals(mesh, faces=mesh.faces)
    mesh.to_mesh(result.data)
    mesh.free()
    result.data.update()
    return result


def boolean_difference(target, cutter):
    before = bounds(target)
    modifier = target.modifiers.new("V008_Unified_Water_Groove", "BOOLEAN")
    modifier.operation = "DIFFERENCE"
    modifier.solver = "MANIFOLD"
    modifier.object = cutter
    bpy.context.view_layer.objects.active = target
    target.select_set(True)
    bpy.ops.object.modifier_apply(modifier=modifier.name)
    target.select_set(False)
    after = bounds(target)
    for axis in ("x", "y"):
        if abs(before[axis][0] - after[axis][0]) > 0.05 or abs(before[axis][1] - after[axis][1]) > 0.05:
            raise RuntimeError(
                f"Terrain bounds changed during {cutter.name}: {before} -> {after}"
            )


def join(objects, name):
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    bpy.ops.object.join()
    result = bpy.context.object
    result.name = name
    return result


def voxel_union(obj):
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    obj.data.remesh_voxel_size = REMESH_VOXEL_MM
    obj.data.remesh_voxel_adaptivity = 0.0
    obj.data.use_remesh_fix_poles = True
    bpy.ops.object.voxel_remesh()
    if connected_components(obj) != 1:
        raise RuntimeError("Unified water is still disconnected after voxel union")


def align_bottom(obj, target_z):
    current_min = bounds(obj)["z"][0]
    obj.location.z += target_z - current_min
    bpy.context.view_layer.update()


def export_stl(path, obj, offset_z=0.0):
    original = obj.location.copy()
    obj.location.z += offset_z
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.wm.stl_export(filepath=str(path), export_selected_objects=True, ascii_format=False)
    obj.location = original


def main():
    global COMMON_BOTTOM_Z, RAIL_TOP_Z
    args = sys.argv[sys.argv.index("--") + 1 :]
    if len(args) not in (5, 6):
        raise SystemExit(
            "Expected OUTPUT.blend TERRAIN_LOW.stl WATER.stl REPORT.json "
            "PREVIEW.png [top|bottom]"
        )
    output_blend, terrain_stl, water_stl, report_path, preview_path = map(Path, args[:5])
    install_mode = args[5] if len(args) == 6 else "top"
    if install_mode not in {"top", "bottom"}:
        raise SystemExit("Install mode must be top or bottom")
    if install_mode == "bottom":
        COMMON_BOTTOM_Z = 0.0
        RAIL_TOP_Z = 0.50
    version = "SYS01_V009" if install_mode == "bottom" else "SYS01_V008"
    for path in (output_blend, terrain_stl, water_stl, report_path, preview_path):
        path.parent.mkdir(parents=True, exist_ok=True)

    # Ignore the already packed print-plate copy; use the five aligned inserts.
    waters = [
        obj
        for obj in bpy.context.scene.objects
        if obj.get("S02_geometry") in {"stream_ribbon", "water_area"}
        and obj.name != "SYS01_Water_Blue_SeparatePrint"
    ]
    packed = bpy.data.objects.get("SYS01_Water_Blue_SeparatePrint")
    if packed:
        bpy.data.objects.remove(packed, do_unlink=True)
    low = next(obj for obj in bpy.context.scene.objects if obj.get("Object type") == "TERRAIN_LOW_GREEN")
    trail = next(obj for obj in bpy.context.scene.objects if obj.get("S03_geometry") == "trail_insert")

    for water in waters:
        lower_bottom(water)
    nodes = [node for water in waters for node in component_nodes(water)]
    edges = minimum_spanning_tree(nodes)
    rails = []
    for index, (distance, left, right) in enumerate(edges, start=1):
        rails.append(
            rail_between(
                f"V008_HiddenRail_{index:02d}",
                nodes[left]["point"],
                nodes[right]["point"],
            )
        )
    pads = [pad_at(f"V008_NodePad_{index:02d}", node["point"]) for index, node in enumerate(nodes, 1)]
    # Deepen the five existing water grooves and add only narrow buried rail
    # grooves. Multiple simple booleans are more stable than one huge union.
    cut_sources = [*waters, *rails, *pads]
    for source in cut_sources:
        cutter = expanded_copy(source)
        boolean_difference(low, cutter)
        bpy.data.objects.remove(cutter, do_unlink=True)
    if install_mode == "bottom":
        # A valid bottom-loaded part needs clearance for every intermediate
        # position, not only its final pose. Subtract the complete sampled
        # swept envelope of the visible water bodies from the low terrain.
        for source in waters:
            source_height = bounds(source)["z"][1] - COMMON_BOTTOM_Z
            offset = -INSERTION_SWEEP_STEP_MM
            while offset >= -source_height:
                cutter = expanded_copy(source)
                cutter.location.z += offset
                boolean_difference(low, cutter)
                bpy.data.objects.remove(cutter, do_unlink=True)
                offset -= INSERTION_SWEEP_STEP_MM

    unified = join(
        [*waters, *rails, *pads],
        f"{version}_Water_Blue_Unified_{install_mode.title()}Load",
    )
    voxel_union(unified)
    align_bottom(unified, COMMON_BOTTOM_Z)
    unified["SYS01_geometry"] = "unified_water_underpass"
    unified["island_count_before"] = len(nodes)
    unified["hidden_rail_count"] = len(edges)
    blue = bpy.data.materials.get("Water_Blue")
    if blue:
        unified.data.materials.clear()
        unified.data.materials.append(blue)

    export_stl(terrain_stl, low)
    export_stl(water_stl, unified, offset_z=-COMMON_BOTTOM_Z)

    # Simple QA render from above with the unified water highlighted.
    camera_location = (
        (0, -120, -115) if install_mode == "bottom" else (0, -120, 150)
    )
    bpy.ops.object.camera_add(location=camera_location)
    camera = bpy.context.object
    direction = Vector((0, 0, 4)) - camera.location
    camera.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = 125
    bpy.context.scene.camera = camera
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.light = "STUDIO"
    scene.display.shading.color_type = "MATERIAL"
    scene.display.shading.show_cavity = True
    scene.render.resolution_x = 1200
    scene.render.resolution_y = 1000
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = str(preview_path)
    bpy.ops.render.render(write_still=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(output_blend))

    trail_bounds = bounds(trail)
    report = {
        "version": version,
        "installation": {
            "mode": install_mode,
            "direction": "+Z from terrain underside" if install_mode == "bottom" else "-Z from terrain top",
            "base_captures_water": install_mode == "bottom",
            "connector_flush_with_terrain_bottom": install_mode == "bottom",
        },
        "parameters_mm": {
            "common_water_bottom_z": COMMON_BOTTOM_Z,
            "hidden_rail_top_z": RAIL_TOP_Z,
            "hidden_rail_width": RAIL_WIDTH_MM,
            "cutter_clearance_each_side": CUTTER_CLEARANCE_MM,
            "voxel_union_resolution": REMESH_VOXEL_MM,
            "insertion_sweep_step": (
                INSERTION_SWEEP_STEP_MM if install_mode == "bottom" else None
            ),
        },
        "water_islands_before": len(nodes),
        "hidden_rails": len(edges),
        "rail_total_length_mm": round(sum(edge[0] for edge in edges), 4),
        "trail_original_min_z": trail_bounds["z"][0],
        "underpass_vertical_clearance_mm": round(trail_bounds["z"][0] - RAIL_TOP_Z, 4),
        "nodes": [
            {
                "object": node["object"],
                "vertices": node["vertices"],
                "point": [round(node["point"].x, 4), round(node["point"].y, 4)],
            }
            for node in nodes
        ],
        "edges": [
            {"from": left, "to": right, "length_mm": round(distance, 4)}
            for distance, left, right in edges
        ],
        "terrain_low": {
            "bounds": bounds(low),
            "quality": quality(low),
            "connected_components": connected_components(low),
        },
        "unified_water": {
            "bounds": bounds(unified),
            "quality": quality(unified),
            "connected_components": connected_components(unified),
        },
        "exports": {
            "terrain_low": str(terrain_stl),
            "water_unified": str(water_stl),
            "blend": str(output_blend),
            "preview": str(preview_path),
        },
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("V008_REPORT=" + json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
