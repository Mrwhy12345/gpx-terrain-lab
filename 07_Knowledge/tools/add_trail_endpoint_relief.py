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
FINISH_ENGRAVE_DEPTH = 0.18
ENDPOINT_INSET_MM = 1.25


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


def nearest_trail_anchor(trail, xy):
    """Snap a symbolic endpoint onto one actual projected shell XYZ."""
    points = [trail.matrix_world @ vertex.co for vertex in trail.data.vertices]
    nearest_distance = min(math.hypot(point.x - xy[0], point.y - xy[1]) for point in points)
    # Several vertices can share nearly the same XY on the solid sidewall.
    # Select the highest one so the relief top follows the visible route skin.
    candidates = [
        point for point in points
        if math.hypot(point.x - xy[0], point.y - xy[1]) <= nearest_distance + 0.08
    ]
    return max(candidates, key=lambda point: point.z)


def union_and_remove(trail, part):
    if trail.data.materials:
        part.data.materials.append(trail.data.materials[0])
    # The trail is now the authoritative continuous GPX spine, so endpoint
    # symbols overlap one known solid and can be unioned exactly without the
    # former risk of dropping distant projected-shell components.
    boolean(trail, part, "UNION")
    bpy.data.objects.remove(part, do_unlink=True)


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
    before_end = geo_to_world(*lonlat[max(0, len(lonlat) - 5)], scale)
    heading = math.atan2(second[1] - start[1], second[0] - start[0])

    # The final GPX sample can lie just outside the printable route shell after
    # curve sampling and terrain projection.  Move the target a small distance
    # back along the route so the solid pad has guaranteed physical overlap
    # with the trail instead of merely touching it.
    finish_dx = before_end[0] - end[0]
    finish_dy = before_end[1] - end[1]
    finish_length = math.hypot(finish_dx, finish_dy)
    if finish_length > 1e-6:
        finish_center = (
            end[0] + finish_dx / finish_length * ENDPOINT_INSET_MM,
            end[1] + finish_dy / finish_length * ENDPOINT_INSET_MM,
        )
    else:
        finish_center = end
    requested_finish_center = finish_center
    finish_anchor = nearest_trail_anchor(trail, requested_finish_center)
    finish_center = (finish_anchor.x, finish_anchor.y)

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
    end_top = finish_anchor.z
    outer = prism("V011_Finish_Target_Solid", finish_center, FINISH_OUTER_RADIUS, end_top - 0.40, end_top + RELIEF_HEIGHT, 48)
    union_and_remove(trail, outer)
    # Engrave a shallow annulus into the solid pad. Unlike a through-cut ring
    # plus floating dot, this keeps one continuous printable body.
    engrave_top=end_top+RELIEF_HEIGHT+0.05
    groove=prism("V011_Finish_Target_Engraved_Ring",finish_center,FINISH_INNER_RADIUS,
        engrave_top-FINISH_ENGRAVE_DEPTH,engrave_top,48)
    center_keep=prism("V011_Finish_Target_Engrave_Centre",finish_center,FINISH_DOT_RADIUS,
        engrave_top-FINISH_ENGRAVE_DEPTH-0.05,engrave_top+0.05,32)
    boolean(groove,center_keep,"DIFFERENCE")
    bpy.data.objects.remove(center_keep,do_unlink=True)
    boolean(trail,groove,"DIFFERENCE")
    bpy.data.objects.remove(groove,do_unlink=True)

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
            "engraved_ring_depth_mm": FINISH_ENGRAVE_DEPTH,
            "route_inset_mm": ENDPOINT_INSET_MM,
            "original_endpoint_xy": [round(end[0], 6), round(end[1], 6)],
            "requested_inset_xy": [round(requested_finish_center[0], 6), round(requested_finish_center[1], 6)],
            "symbol_center_xy": [round(finish_center[0], 6), round(finish_center[1], 6)],
            "symbol_anchor_z": round(end_top, 6),
            "solid_overlap_depth_mm": 0.40,
            "snap_distance_mm": round(math.hypot(
                finish_center[0] - requested_finish_center[0],
                finish_center[1] - requested_finish_center[1],
            ), 6),
        },
        "relief_height_mm": RELIEF_HEIGHT,
        "trail_quality": quality(trail),
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    bpy.ops.wm.save_as_mainfile(filepath=str(output_blend))
    print("ENDPOINT_RELIEF=" + json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
