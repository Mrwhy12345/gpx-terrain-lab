#!/usr/bin/env python3
"""Create flat-bottom water inserts and carve matching terrain grooves."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils.kdtree import KDTree


# Real installation fractured a three-piece water insert at 0.12 mm/side.
# Water is more fragile than the trail, so give it an independent relaxed fit.
SIDE_CLEARANCE_MM = 0.25
WATER_XY_EXPANSION_MM = 0.15
LOCAL_NECK_WIDTH_MM = 1.35
LOCAL_NECK_HEIGHT_MM = 0.55
MAX_LOCAL_JOIN_GAP_MM = 4.0
TARGET_INSTALL_COMPONENTS = 2
WATER_REMESH_VOXEL_MM = 0.065
PACK_MARGIN_MM = 4.0
PACK_ROW_WIDTH_MM = 210.0
REPAIR_AFTER_FLATTEN = False
REPAIR_VOXEL_MM = 0.04
MIN_TERRAIN_COMPONENT_VERTICES = 500


def quality(obj):
    mesh = bmesh.new()
    mesh.from_mesh(obj.data)
    result = {
        "vertices": len(mesh.verts),
        "edges": len(mesh.edges),
        "faces": len(mesh.faces),
        "non_manifold_edges": sum(not edge.is_manifold for edge in mesh.edges),
    }
    mesh.free()
    return result


def world_bounds(obj):
    points = [obj.matrix_world @ vertex.co for vertex in obj.data.vertices]
    return {
        axis: [min(point[i] for point in points), max(point[i] for point in points)]
        for i, axis in enumerate(("x", "y", "z"))
    }


def recalculate_normals(obj):
    mesh = bmesh.new()
    mesh.from_mesh(obj.data)
    bmesh.ops.recalc_face_normals(mesh, faces=mesh.faces)
    mesh.normal_update()
    mesh.to_mesh(obj.data)
    mesh.free()
    obj.data.update()


def remove_tiny_components(obj, minimum_vertices=MIN_TERRAIN_COMPONENT_VERTICES):
    mesh = bmesh.new(); mesh.from_mesh(obj.data); remaining=set(mesh.verts); groups=[]
    while remaining:
        seed=remaining.pop(); group={seed}; queue=[seed]
        while queue:
            vertex=queue.pop()
            for edge in vertex.link_edges:
                other=edge.other_vert(vertex)
                if other in remaining: remaining.remove(other); group.add(other); queue.append(other)
        groups.append(group)
    removed=[group for group in groups if len(group)<minimum_vertices]
    if removed:
        bmesh.ops.delete(mesh,geom=[vertex for group in removed for vertex in group],context="VERTS")
        mesh.to_mesh(obj.data); obj.data.update()
    payload={"removed_components":len(removed),"removed_vertex_counts":sorted((len(g) for g in removed),reverse=True),"kept_vertex_counts":sorted((len(g) for g in groups if len(g)>=minimum_vertices),reverse=True)}
    mesh.free(); return payload


def widen_xy(obj):
    """Widen narrow water laterally without increasing its visible height."""
    recalculate_normals(obj)
    mesh = bmesh.new()
    mesh.from_mesh(obj.data)
    mesh.normal_update()
    for vertex in mesh.verts:
        normal = vertex.normal.copy()
        normal.z = 0.0
        if normal.length_squared > 1e-10:
            normal.normalize()
            vertex.co += normal * WATER_XY_EXPANSION_MM
    bmesh.ops.recalc_face_normals(mesh, faces=mesh.faces)
    mesh.to_mesh(obj.data)
    mesh.free()
    obj.data.update()


def component_points(obj):
    mesh = bmesh.new(); mesh.from_mesh(obj.data)
    remaining = set(mesh.verts); groups = []
    while remaining:
        seed = remaining.pop(); group = {seed}; queue = [seed]
        while queue:
            vertex = queue.pop()
            for edge in vertex.link_edges:
                other = edge.other_vert(vertex)
                if other in remaining:
                    remaining.remove(other); group.add(other); queue.append(other)
        points = [obj.matrix_world @ vertex.co for vertex in group]
        bottom = min(point.z for point in points)
        groups.append([point for point in points if point.z <= bottom + 0.10])
    mesh.free(); return groups


def nearest_pair(left, right):
    tree = KDTree(len(left))
    for index, point in enumerate(left): tree.insert(point, index)
    tree.balance(); best = None
    for point in right:
        nearest, _, distance = tree.find(point)
        if best is None or distance < best[0]: best = (distance, nearest.copy(), point.copy())
    return best


def local_rail(name, start, end):
    midpoint = (start + end) / 2
    length = (end.xy - start.xy).length
    z0 = min(start.z, end.z) - 0.03
    bpy.ops.mesh.primitive_cube_add(location=(midpoint.x, midpoint.y, z0 + LOCAL_NECK_HEIGHT_MM / 2))
    rail = bpy.context.object; rail.name = name
    rail.dimensions = (length + LOCAL_NECK_WIDTH_MM * 1.8, LOCAL_NECK_WIDTH_MM, LOCAL_NECK_HEIGHT_MM)
    rail.rotation_euler.z = math.atan2(end.y - start.y, end.x - start.x)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    return rail


def local_pad(name, point):
    bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=LOCAL_NECK_WIDTH_MM, depth=LOCAL_NECK_HEIGHT_MM,
        location=(point.x, point.y, point.z - 0.03 + LOCAL_NECK_HEIGHT_MM / 2))
    pad = bpy.context.object; pad.name = name; return pad


def reinforce_nearby_components(water):
    groups = component_points(water)
    candidates = []
    for left in range(len(groups)):
        for right in range(left + 1, len(groups)):
            distance, start, end = nearest_pair(groups[left], groups[right])
            candidates.append((distance, left, right, start, end))
    candidates.sort(key=lambda item: item[0])
    selected = []
    if len(groups) > TARGET_INSTALL_COMPONENTS and candidates and candidates[0][0] <= MAX_LOCAL_JOIN_GAP_MM:
        selected.append(candidates[0])
    if not selected:
        return water, len(groups), len(groups), [], [round(item[0], 3) for item in candidates]
    additions = []
    for index, item in enumerate(selected, 1):
        additions.extend((local_rail(f"WaterLocalRail_{index:02d}", item[3], item[4]),
                          local_pad(f"WaterLocalPad_{index:02d}_A", item[3]),
                          local_pad(f"WaterLocalPad_{index:02d}_B", item[4])))
    select_only([water, *additions]); bpy.ops.object.join(); water = bpy.context.object
    water.name = "route_WATER_Reinforced"
    # TrailPrint vertices use large projected coordinates (~212 km).  Move the
    # mesh origin to its geometry before voxelisation to avoid float precision
    # cracks at 0.065 mm resolution while preserving world placement.
    bpy.ops.object.origin_set(type="ORIGIN_GEOMETRY", center="BOUNDS")
    water.data.remesh_voxel_size = WATER_REMESH_VOXEL_MM
    water.data.remesh_voxel_adaptivity = 0.0
    water.data.use_remesh_fix_poles = True
    bpy.ops.object.voxel_remesh()
    after = len(component_points(water))
    return water, len(groups), after, [round(item[0], 3) for item in selected], [round(item[0], 3) for item in candidates]


def flatten_bottom(obj):
    """Flatten vertices belonging to downward-facing faces."""
    recalculate_normals(obj)
    mesh = bmesh.new()
    mesh.from_mesh(obj.data)
    bottom_vertices = {
        vertex
        for face in mesh.faces
        if face.normal.z < -0.45
        for vertex in face.verts
    }
    if not bottom_vertices:
        mesh.free()
        raise RuntimeError(f"No bottom faces found for {obj.name}")
    bottom_z = min(vertex.co.z for vertex in bottom_vertices)
    for vertex in bottom_vertices:
        vertex.co.z = bottom_z
    # Flattening may collapse pre-existing sliver triangles onto the bottom
    # plane. Remove them before STL export so slicer/import round-trips remain
    # manifold instead of reopening boundary edges.
    bmesh.ops.remove_doubles(mesh, verts=mesh.verts, dist=1e-6)
    bmesh.ops.dissolve_degenerate(mesh, edges=mesh.edges, dist=1e-6)
    bmesh.ops.recalc_face_normals(mesh, faces=mesh.faces)
    mesh.to_mesh(obj.data)
    mesh.free()
    obj.data.update()
    if REPAIR_AFTER_FLATTEN:
        bpy.ops.object.select_all(action="DESELECT")
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        obj.data.remesh_voxel_size = REPAIR_VOXEL_MM
        obj.data.remesh_voxel_adaptivity = 0.0
        bpy.ops.object.voxel_remesh()
        recalculate_normals(obj)
    return bottom_z, len(bottom_vertices)


def expanded_copy(source, name):
    result = source.copy()
    result.data = source.data.copy()
    result.name = name
    bpy.context.scene.collection.objects.link(result)
    recalculate_normals(result)
    mesh = bmesh.new()
    mesh.from_mesh(result.data)
    mesh.normal_update()
    for vertex in mesh.verts:
        vertex.co += vertex.normal * SIDE_CLEARANCE_MM
    bmesh.ops.recalc_face_normals(mesh, faces=mesh.faces)
    mesh.to_mesh(result.data)
    mesh.free()
    result.data.update()
    return result


def boolean_difference(target, cutter):
    before = quality(target)
    modifier = target.modifiers.new(f"Water groove {cutter.name}", "BOOLEAN")
    modifier.operation = "DIFFERENCE"
    modifier.solver = "MANIFOLD"
    modifier.object = cutter
    bpy.context.view_layer.objects.active = target
    target.select_set(True)
    bpy.ops.object.modifier_apply(modifier=modifier.name)
    target.select_set(False)
    recalculate_normals(target)
    return before, quality(target)


def select_only(objects):
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]


def export_stl(path, objects):
    select_only(objects)
    bpy.ops.wm.stl_export(
        filepath=str(path), export_selected_objects=True, ascii_format=False
    )


def main():
    args = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    if len(args) != 3:
        raise SystemExit(
            "Usage: blender INPUT.blend --python script.py -- "
            "OUTPUT.blend OUTPUT_DIR REPORT.json"
        )
    output_blend, output_dir, report_path = map(Path, args)
    output_dir.mkdir(parents=True, exist_ok=True)

    low = next(
        obj for obj in bpy.context.scene.objects
        if obj.get("Object type") == "TERRAIN_LOW_GREEN"
    )
    middle = next(
        obj for obj in bpy.context.scene.objects
        if obj.get("Object type") == "TERRAIN_MIDDLE_BROWN"
    )
    high = next(
        obj for obj in bpy.context.scene.objects
        if obj.get("Object type") == "TERRAIN_HIGH_GRAY"
    )
    villages = [
        obj for obj in bpy.context.scene.objects
        if obj.get("S04_geometry") == "residential_areas_printable"
    ]
    waters = [
        obj for obj in bpy.context.scene.objects
        if (
            obj.get("Object type") in {"WATER", "OCEAN"}
            or obj.get("S02_geometry") in {"stream_ribbon", "water_area"}
        )
    ]
    if not waters:
        raise RuntimeError("No printable water objects found")

    # TrailPrint may provide one mesh with several disconnected waterways.
    # Establish a common printable bottom before reinforcement; otherwise a
    # voxel union can miss a rail whose endpoints sit on different Z levels.
    bottom_records = {}
    for water in waters:
        bottom_records[water.name] = flatten_bottom(water)
    # Widen it, then join only genuinely adjacent endpoints.  Groove
    # cutters are derived from this final reinforced geometry, guaranteeing
    # that the printed water and terrain slot stay matched.
    for water in waters:
        widen_xy(water)
    if len(waters) == 1:
        waters[0], components_before, components_after, local_gaps, all_gaps = reinforce_nearby_components(waters[0])
    else:
        components_before = components_after = len(waters); local_gaps = []; all_gaps = []

    insert_records = []
    cutters = []
    for index, water in enumerate(waters, start=1):
        # Reinforcement can rename the single TrailPrint water object.  Its
        # bottom is already flattened; refresh the bottom vertex accounting
        # after the union without changing the established sequence.
        bottom_z, bottom_vertex_count = flatten_bottom(water)
        water["SYS01_geometry"] = "water_insert"
        water["Water insert bottom Z"] = bottom_z
        cutter = expanded_copy(water, f"SYS01_Water_Cutter_{index:02d}")
        cutter["SYS01_geometry"] = "water_groove_cutter"
        cutters.append(cutter)
        insert_records.append(
            {
                "name": water.name,
                "osm_id": water.get("OSM_ID"),
                "bottom_z": bottom_z,
                "bottom_vertex_count": bottom_vertex_count,
                "quality": quality(water),
                "bounds": world_bounds(water),
                "cutter_bounds": world_bounds(cutter),
            }
        )

    cut_records = []
    targets = [low, middle, high, *villages]
    for target in targets:
        target_record = {"name": target.name, "cuts": []}
        for cutter in cutters:
            before, after = boolean_difference(target, cutter)
            target_record["cuts"].append(
                {
                    "cutter": cutter.name,
                    "vertices_before": before["vertices"],
                    "vertices_after": after["vertices"],
                }
            )
        if target in {low, middle, high}:
            target_record["post_cut_component_cleanup"] = remove_tiny_components(target)
        target_record["quality_after"] = quality(target)
        cut_records.append(target_record)

    for cutter in cutters:
        bpy.data.objects.remove(cutter, do_unlink=True)

    center_x, center_y = low.location.x, low.location.y
    aligned_objects = [low, middle, high, *villages, *waters]
    for obj in aligned_objects:
        obj.location.x -= center_x
        obj.location.y -= center_y

    low_path = output_dir / "01_Terrain_Low_Green_Grooved.stl"
    export_stl(low_path, [low])

    brown_path = output_dir / "02_Terrain_And_Villages_Brown_Grooved.stl"
    select_only([middle, *villages])
    bpy.ops.object.join()
    brown = bpy.context.object
    brown.name = "SYS01_Terrain_And_Villages_Brown_Grooved"
    export_stl(brown_path, [brown])

    high_path = output_dir / "03_Terrain_High_Gray_Grooved.stl"
    export_stl(high_path, [high])

    # Preserve an aligned reference before arranging inserts on the print bed.
    aligned_water_path = output_dir / "04_Water_Blue_Aligned_Reference.stl"
    export_stl(aligned_water_path, waters)

    printable_inserts = []
    for water in waters:
        copy = water.copy()
        copy.data = water.data.copy()
        copy.name = water.name + "_SeparatePrint"
        bpy.context.scene.collection.objects.link(copy)
        printable_inserts.append(copy)

    # Lay every disconnected water object on its own flat bottom and pack rows.
    cursor_x = 0.0
    cursor_y = 0.0
    row_height = 0.0
    placements = []
    for obj in sorted(
        printable_inserts,
        key=lambda item: max(item.dimensions.x, item.dimensions.y),
        reverse=True,
    ):
        bounds = world_bounds(obj)
        width = bounds["x"][1] - bounds["x"][0]
        height = bounds["y"][1] - bounds["y"][0]
        if cursor_x and cursor_x + width > PACK_ROW_WIDTH_MM:
            cursor_x = 0.0
            cursor_y += row_height + PACK_MARGIN_MM
            row_height = 0.0
        obj.location.x += cursor_x - bounds["x"][0]
        obj.location.y += cursor_y - bounds["y"][0]
        obj.location.z -= bounds["z"][0]
        placements.append(
            {
                "name": obj.name,
                "plate_x": cursor_x,
                "plate_y": cursor_y,
                "width": width,
                "height": height,
            }
        )
        cursor_x += width + PACK_MARGIN_MM
        row_height = max(row_height, height)

    select_only(printable_inserts)
    bpy.ops.object.join()
    printable_water = bpy.context.object
    printable_water.name = "SYS01_Water_Blue_SeparatePrint"
    packed_bounds = world_bounds(printable_water)
    printable_water.location.x -= sum(packed_bounds["x"]) / 2
    printable_water.location.y -= sum(packed_bounds["y"]) / 2
    water_path = output_dir / "05_Water_Blue_SeparatePrint.stl"
    export_stl(water_path, [printable_water])

    report = {
        "source_blend": bpy.data.filepath,
        "output_blend": str(output_blend),
        "parameters_mm": {
            "side_clearance_each_side": SIDE_CLEARANCE_MM,
            "water_xy_expansion_each_side": WATER_XY_EXPANSION_MM,
            "nominal_minimum_neck_width": LOCAL_NECK_WIDTH_MM,
            "local_neck_height": LOCAL_NECK_HEIGHT_MM,
            "pack_margin": PACK_MARGIN_MM,
            "pack_row_width": PACK_ROW_WIDTH_MM,
        },
        "connectivity": {
            "components_before": components_before,
            "components_after": components_after,
            "target_install_components": TARGET_INSTALL_COMPONENTS,
            "joined_local_gaps_mm": local_gaps,
            "all_nearest_gaps_mm": all_gaps,
        },
        "water_inserts": insert_records,
        "terrain_cut_records": cut_records,
        "exports": {
            "terrain_low": str(low_path),
            "terrain_brown": str(brown_path),
            "terrain_high": str(high_path),
            "water_aligned_reference": str(aligned_water_path),
            "water_separate_print": str(water_path),
        },
        "packed_water_placements": placements,
        "final_quality": {
            "terrain_low": quality(low),
            "terrain_brown": quality(brown),
            "terrain_high": quality(high),
            "water_separate_print": quality(printable_water),
        },
    }
    output_blend.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(output_blend))
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print("WATER_INSERT_REPORT=" + json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
