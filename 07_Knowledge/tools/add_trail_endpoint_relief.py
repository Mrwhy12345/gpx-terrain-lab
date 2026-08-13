#!/usr/bin/env python3
"""Add single-colour start-arrow and finish-target relief to an existing trail insert."""

from __future__ import annotations

import json
import math
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import bmesh
import bpy


EARTH_RADIUS_KM = 6371.0
RELIEF_HEIGHT = 0.55
START_RADIUS = 1.80
FINISH_OUTER_RADIUS = 2.10
FINISH_INNER_RADIUS = 1.22
FINISH_DOT_RADIUS = 0.62


def geo_to_world(longitude, latitude, scale):
    return (
        EARTH_RADIUS_KM * math.radians(longitude) * scale,
        EARTH_RADIUS_KM
        * math.log(math.tan(math.pi / 4 + math.radians(latitude) / 2))
        * scale,
    )


def prism(name, center, radius, bottom, top, segments, rotation=0.0):
    vertices = []
    for z in (bottom, top):
        vertices.extend(
            (
                center[0] + radius * math.cos(rotation + 2 * math.pi * i / segments),
                center[1] + radius * math.sin(rotation + 2 * math.pi * i / segments),
                z,
            )
            for i in range(segments)
        )
    faces = [tuple(reversed(range(segments))), tuple(range(segments, 2 * segments))]
    faces.extend(
        (i, (i + 1) % segments, segments + (i + 1) % segments, segments + i)
        for i in range(segments)
    )
    mesh = bpy.data.meshes.new(name + "_Mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def boolean(target, tool, operation):
    modifier = target.modifiers.new(f"EndpointRelief_{operation}", "BOOLEAN")
    modifier.operation = operation
    modifier.solver = "EXACT"
    modifier.object = tool
    bpy.context.view_layer.objects.active = target
    bpy.ops.object.modifier_apply(modifier=modifier.name)


def local_top(trail, xy, radius):
    points = [trail.matrix_world @ vertex.co for vertex in trail.data.vertices]
    nearby = [
        point.z
        for point in points
        if math.hypot(point.x - xy[0], point.y - xy[1]) <= radius
    ]
    return max(nearby) if nearby else max(points, key=lambda p: -math.hypot(p.x-xy[0], p.y-xy[1])).z


def union_and_remove(trail, part):
    if trail.data.materials:
        part.data.materials.append(trail.data.materials[0])
    # Exact boolean UNION can discard a distant connected component on long,
    # winding trail meshes.  Both operands are already closed printable
    # solids, so keep their shells and join them into one exported object; the
    # slicer resolves the tiny intentional overlap without losing the route.
    bpy.ops.object.select_all(action="DESELECT")
    trail.select_set(True)
    part.select_set(True)
    bpy.context.view_layer.objects.active = trail
    bpy.ops.object.join()


def quality(obj):
    mesh = bmesh.new()
    mesh.from_mesh(obj.data)
    result = {
        "vertices": len(mesh.verts),
        "faces": len(mesh.faces),
        "non_manifold_edges": sum(not edge.is_manifold for edge in mesh.edges),
        "min_z": min(v.co.z for v in mesh.verts),
        "max_z": max(v.co.z for v in mesh.verts),
    }
    mesh.free()
    return result


def main():
    args = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    if len(args) != 3:
        raise SystemExit("Expected GPX OUTPUT.blend REPORT.json")
    gpx_path, output_blend, report_path = map(Path, args)

    terrain = next(
        obj for obj in bpy.context.scene.objects
        if obj.get("Object type") in {"MAP", "TERRAIN_LOW_GREEN"}
    )
    trail = next(
        obj for obj in bpy.context.scene.objects
        if obj.get("S03_geometry") == "trail_insert"
    )
    root = ET.parse(gpx_path).getroot()
    lonlat = [
        (float(point.attrib["lon"]), float(point.attrib["lat"]))
        for point in root.iter()
        if point.tag.rsplit("}", 1)[-1] in {"trkpt", "rtept"}
    ]
    scale = float(terrain.get("Horizontal Scale", 16.749693))
    start = geo_to_world(*lonlat[0], scale)
    second = geo_to_world(*lonlat[min(4, len(lonlat) - 1)], scale)
    end = geo_to_world(*lonlat[-1], scale)
    heading = math.atan2(second[1] - start[1], second[0] - start[0])

    # Start: enlarged triangle for 0.4 mm nozzle legibility.  It intentionally
    # overlaps the route body, so it is both a symbol and an endpoint grip pad.
    start_top = local_top(trail, start, 2.4)
    arrow = prism(
        "V011_Start_Arrow_Relief", start, START_RADIUS,
        start_top - 0.05, start_top + RELIEF_HEIGHT, 3, heading
    )
    union_and_remove(trail, arrow)

    # Finish: outer annular ridge plus central dot, attached to the existing
    # diamond pad. The shallow relief is legible despite using only red.
    end_top = local_top(trail, end, 2.8)
    outer = prism("V011_Finish_Target_Outer", end, FINISH_OUTER_RADIUS, end_top - 0.05, end_top + RELIEF_HEIGHT, 48)
    hole = prism("V011_Finish_Target_Hole", end, FINISH_INNER_RADIUS, end_top - 0.15, end_top + RELIEF_HEIGHT + 0.15, 48)
    boolean(outer, hole, "DIFFERENCE")
    bpy.data.objects.remove(hole, do_unlink=True)
    union_and_remove(trail, outer)
    dot = prism("V011_Finish_Target_Dot", end, FINISH_DOT_RADIUS, end_top - 0.05, end_top + RELIEF_HEIGHT, 32)
    union_and_remove(trail, dot)

    trail.name = "S02_Trail_Red_Insert_StartArrow_FinishTarget"
    trail["Endpoint relief"] = "start_arrow_finish_target"
    trail["Relief height mm"] = RELIEF_HEIGHT
    output_blend.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "source_blend": bpy.data.filepath,
        "output_blend": str(output_blend),
        "single_colour": "red",
        "start_symbol": {"shape": "triangle", "radius_mm": START_RADIUS},
        "finish_symbol": {
            "shape": "bullseye",
            "outer_radius_mm": FINISH_OUTER_RADIUS,
            "ring_inner_radius_mm": FINISH_INNER_RADIUS,
            "dot_radius_mm": FINISH_DOT_RADIUS,
        },
        "relief_height_mm": RELIEF_HEIGHT,
        "trail_quality": quality(trail),
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    bpy.ops.wm.save_as_mainfile(filepath=str(output_blend))
    print("ENDPOINT_RELIEF=" + json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
