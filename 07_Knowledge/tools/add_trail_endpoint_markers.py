#!/usr/bin/env python3
"""Add distinct start/end markers to the separate red trail insert and groove."""

from __future__ import annotations

import json
import math
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector


EARTH_RADIUS_KM = 6371.0
START_RADIUS_MM = 1.8
END_RADIUS_MM = 2.0
TOLERANCE_MM = 0.2
TOP_EXTRA_MM = 0.18


def geo_to_world(longitude, latitude, horizontal_scale):
    return (
        EARTH_RADIUS_KM * math.radians(longitude) * horizontal_scale,
        EARTH_RADIUS_KM
        * math.log(math.tan(math.pi / 4 + math.radians(latitude) / 2))
        * horizontal_scale,
    )


def quality(obj):
    editable = bmesh.new()
    editable.from_mesh(obj.data)
    result = {
        "vertices": len(editable.verts),
        "edges": len(editable.edges),
        "faces": len(editable.faces),
        "non_manifold_edges": sum(not edge.is_manifold for edge in editable.edges),
        "min_z": min((obj.matrix_world @ v.co).z for v in editable.verts),
        "max_z": max((obj.matrix_world @ v.co).z for v in editable.verts),
    }
    editable.free()
    return result


def recalculate_normals(obj):
    editable = bmesh.new()
    editable.from_mesh(obj.data)
    bmesh.ops.recalc_face_normals(editable, faces=editable.faces)
    editable.to_mesh(obj.data)
    editable.free()


def voxel_repair(obj, size):
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    obj.data.remesh_voxel_size = size
    obj.data.remesh_voxel_adaptivity = 0.0
    bpy.ops.object.voxel_remesh()
    recalculate_normals(obj)
    obj.select_set(False)


def prism(name, center_xy, radius, bottom_z, top_z, segments, rotation=0.0):
    vertices = []
    for z in (bottom_z, top_z):
        vertices += [
            (
                center_xy[0] + radius * math.cos(rotation + 2 * math.pi * i / segments),
                center_xy[1] + radius * math.sin(rotation + 2 * math.pi * i / segments),
                z,
            )
            for i in range(segments)
        ]
    faces = [
        tuple(reversed(range(segments))),
        tuple(range(segments, 2 * segments)),
    ]
    faces += [
        (i, (i + 1) % segments, segments + (i + 1) % segments, segments + i)
        for i in range(segments)
    ]
    mesh = bpy.data.meshes.new(name + "_Mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    recalculate_normals(obj)
    return obj


def boolean(target, cutter, operation):
    modifier = target.modifiers.new(f"Endpoint_{operation}", "BOOLEAN")
    modifier.operation = operation
    modifier.solver = "EXACT"
    modifier.object = cutter
    bpy.context.view_layer.objects.active = target
    bpy.ops.object.modifier_apply(modifier=modifier.name)


def main():
    args = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    if len(args) != 3:
        raise SystemExit(
            "Usage: blender INPUT.blend --python script.py -- GPX OUTPUT.blend REPORT.json"
        )
    gpx_path, output_blend, report_path = map(Path, args)
    terrain = next(
        obj for obj in bpy.context.scene.objects if obj.get("Object type") == "MAP"
    )
    trail = next(
        obj
        for obj in bpy.context.scene.objects
        if obj.get("Object type") == "TRAIL_INSERT"
    )
    root = ET.parse(gpx_path).getroot()
    points = [
        (float(point.attrib["lon"]), float(point.attrib["lat"]))
        for point in root.iter()
        if point.tag.rsplit("}", 1)[-1] in {"trkpt", "rtept"}
    ]
    waypoint_names = [
        (
            float(point.attrib["lon"]),
            float(point.attrib["lat"]),
            next(
                (
                    (child.text or "").strip()
                    for child in point
                    if child.tag.rsplit("}", 1)[-1] == "name"
                    and (child.text or "").strip()
                ),
                None,
            ),
        )
        for point in root.iter()
        if point.tag.rsplit("}", 1)[-1] == "wpt"
    ]

    def nearest_name(lonlat, fallback):
        named = [item for item in waypoint_names if item[2]]
        if not named:
            return fallback
        nearest = min(
            named,
            key=lambda item: math.hypot(item[0] - lonlat[0], item[1] - lonlat[1]),
        )
        return nearest[2]

    endpoints = {
        "start": {
            "name": nearest_name(points[0], "起点"),
            "lonlat": points[0],
            "xy": geo_to_world(*points[0], float(terrain["Horizontal Scale"])),
        },
        "end": {
            "name": nearest_name(points[-1], "终点"),
            "lonlat": points[-1],
            "xy": geo_to_world(*points[-1], float(terrain["Horizontal Scale"])),
        },
    }
    trail_world_vertices = [trail.matrix_world @ vertex.co for vertex in trail.data.vertices]
    flat_bottom = min(vertex.z for vertex in trail_world_vertices)

    def nearby_top(xy, radius):
        candidates = [
            vertex.z
            for vertex in trail_world_vertices
            if math.hypot(vertex.x - xy[0], vertex.y - xy[1]) <= radius
        ]
        if not candidates:
            closest = min(
                trail_world_vertices,
                key=lambda vertex: math.hypot(vertex.x - xy[0], vertex.y - xy[1]),
            )
            return closest.z
        return max(candidates)

    marker_specs = [
        ("start", START_RADIUS_MM, 32, 0.0),
        ("end", END_RADIUS_MM, 4, math.pi / 4),
    ]
    red_material = trail.data.materials[0] if trail.data.materials else None
    marker_cutters = []
    marker_report = []
    for kind, radius, segments, rotation in marker_specs:
        endpoint = endpoints[kind]
        top = nearby_top(endpoint["xy"], radius + 0.8) + TOP_EXTRA_MM
        marker = prism(
            f"S02_{kind.title()}_Marker",
            endpoint["xy"],
            radius,
            flat_bottom,
            top,
            segments,
            rotation,
        )
        if red_material:
            marker.data.materials.append(red_material)
        boolean(trail, marker, "UNION")
        bpy.data.objects.remove(marker, do_unlink=True)

        cutter = prism(
            f"S02_{kind.title()}_Marker_Cutter",
            endpoint["xy"],
            radius + TOLERANCE_MM,
            flat_bottom - 0.2,
            top + 0.4,
            segments,
            rotation,
        )
        marker_cutters.append(cutter)
        marker_report.append(
            {
                "kind": kind,
                "name": endpoint["name"],
                "gpx_lonlat": endpoint["lonlat"],
                "world_xy": endpoint["xy"],
                "radius_mm": radius,
                "shape": "circle" if segments > 4 else "diamond",
                "bottom_z": flat_bottom,
                "top_z": top,
            }
        )

    bpy.ops.object.select_all(action="DESELECT")
    for cutter in marker_cutters:
        cutter.select_set(True)
    bpy.context.view_layer.objects.active = marker_cutters[0]
    bpy.ops.object.join()
    combined_cutter = bpy.context.view_layer.objects.active
    combined_cutter.name = "S02_Endpoint_Marker_Cutters"

    targets = [
        obj
        for obj in list(bpy.context.scene.objects)
        if obj.type == "MESH"
        and (
            obj.get("Object type") == "MAP"
            or obj.get("S02_geometry") in {"stream_ribbon", "water_area"}
            or obj.get("S03_geometry") == "roads_printable"
            or obj.get("S04_geometry") == "residential_areas_printable"
        )
    ]
    target_results = []
    for target in targets:
        boolean(target, combined_cutter, "DIFFERENCE")
        if len(target.data.vertices) == 0:
            target_results.append({"name": target.name, "removed": True})
            bpy.data.objects.remove(target, do_unlink=True)
            continue
        recalculate_normals(target)
        if quality(target)["non_manifold_edges"]:
            if target.get("S03_geometry") == "roads_printable":
                voxel_repair(target, 0.10)
            elif target.get("S04_geometry") == "residential_areas_printable":
                voxel_repair(target, 0.08)
            elif target.get("S02_geometry") in {"stream_ribbon", "water_area"}:
                voxel_repair(target, 0.08)
        target_results.append({"name": target.name, "removed": False, "quality": quality(target)})

    cutter_collection = bpy.data.collections.get("S02_Cutters")
    if cutter_collection is None:
        cutter_collection = bpy.data.collections.new("S02_Cutters")
        bpy.context.scene.collection.children.link(cutter_collection)
    for collection in list(combined_cutter.users_collection):
        collection.objects.unlink(combined_cutter)
    cutter_collection.objects.link(combined_cutter)
    combined_cutter.hide_render = True
    combined_cutter.hide_set(True)

    trail.name = "S02_Trail_Red_Insert_With_Endpoints"
    trail["Start name"] = endpoints["start"]["name"]
    trail["End name"] = endpoints["end"]["name"]
    recalculate_normals(trail)
    if quality(trail)["non_manifold_edges"]:
        # 0.10 mm preserves a 1.4 mm trail with ample sampling while avoiding
        # an unnecessarily large separate-print STL.
        voxel_repair(trail, 0.10)
    report = {
        "source_blend": bpy.data.filepath,
        "output_blend": str(output_blend),
        "marker_settings": {
            "start_diameter_mm": START_RADIUS_MM * 2,
            "end_diagonal_mm": END_RADIUS_MM * 2,
            "assembly_tolerance_mm": TOLERANCE_MM,
        },
        "markers": marker_report,
        "trail_quality": quality(trail),
        "target_results": target_results,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    bpy.ops.wm.save_as_mainfile(filepath=str(output_blend))
    print("ENDPOINT_MARKERS=" + json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
