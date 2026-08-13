#!/usr/bin/env python3
"""Rebuild the display base from true parallel offsets of the terrain hexagon."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector

SLOT_CLEARANCE_MM = 0.30
BORDER_WIDTH_MM = 8.90
BASE_THICKNESS_MM = 8.0
RECESS_DEPTH_MM = 0.8
BEVEL_MM = 1.2
MAGNET_DIAMETER_MM = 5.3
MAGNET_DEPTH_MM = 3.2


def line_intersection(a, b, c, d):
    ab = b - a
    cd = d - c
    cross = ab.x * cd.y - ab.y * cd.x
    if abs(cross) < 1e-9:
        raise ValueError("Adjacent offset edges are parallel")
    ac = c - a
    t = (ac.x * cd.y - ac.y * cd.x) / cross
    return a + ab * t


def offset_polygon(points, distance):
    """True Euclidean offset for a convex CCW polygon."""
    shifted = []
    for index, start in enumerate(points):
        end = points[(index + 1) % len(points)]
        edge = end - start
        outward = Vector((edge.y, -edge.x)).normalized()
        shifted.append((start + outward * distance, end + outward * distance))
    return [
        line_intersection(
            shifted[index - 1][0], shifted[index - 1][1],
            shifted[index][0], shifted[index][1],
        )
        for index in range(len(points))
    ]


def prism(name, outline, z0, z1):
    count = len(outline)
    vertices = [(p.x, p.y, z) for z in (z0, z1) for p in outline]
    faces = [
        tuple(reversed(range(count))),
        tuple(range(count, 2 * count)),
        *((i, (i + 1) % count, count + (i + 1) % count, count + i) for i in range(count)),
    ]
    mesh = bpy.data.meshes.new(name + "_Mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def difference(target, cutter, label):
    modifier = target.modifiers.new(label, "BOOLEAN")
    modifier.operation = "DIFFERENCE"
    modifier.solver = "EXACT"
    modifier.object = cutter
    bpy.context.view_layer.objects.active = target
    bpy.ops.object.modifier_apply(modifier=modifier.name)
    bpy.data.objects.remove(cutter, do_unlink=True)


def edge_angles(points):
    return [
        math.degrees(math.atan2(
            points[(i + 1) % len(points)].y - points[i].y,
            points[(i + 1) % len(points)].x - points[i].x,
        ))
        for i in range(len(points))
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


def main():
    args = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    if len(args) != 2:
        raise SystemExit("Expected OUTPUT.blend REPORT.json")
    output, report_path = map(Path, args)
    terrain = next(o for o in bpy.context.scene.objects if o.get("Object type") == "TERRAIN_LOW_GREEN")
    world = [terrain.matrix_world @ vertex.co for vertex in terrain.data.vertices]
    xmin, xmax = min(p.x for p in world), max(p.x for p in world)
    ymin, ymax = min(p.y for p in world), max(p.y for p in world)
    cx, cy = (xmin + xmax) / 2, (ymin + ymax) / 2
    width, height = xmax - xmin, ymax - ymin
    terrain_hex = [
        Vector((cx - width / 4, cy - height / 2)),
        Vector((cx + width / 4, cy - height / 2)),
        Vector((cx + width / 2, cy)),
        Vector((cx + width / 4, cy + height / 2)),
        Vector((cx - width / 4, cy + height / 2)),
        Vector((cx - width / 2, cy)),
    ]
    recess_hex = offset_polygon(terrain_hex, SLOT_CLEARANCE_MM)
    outer_hex = offset_polygon(recess_hex, BORDER_WIDTH_MM)

    old_base = next(
        (o for o in bpy.context.scene.objects if o.get("S05_geometry") == "display_base"),
        None,
    )
    material = (
        old_base.data.materials[0]
        if old_base is not None and old_base.data.materials
        else bpy.data.materials.get("Base Gray")
    )
    if material is None:
        material = bpy.data.materials.new("Base Gray")
        material.diffuse_color = (0.35, 0.38, 0.40, 1.0)
    if old_base is not None:
        bpy.data.objects.remove(old_base, do_unlink=True)
    for obj in list(bpy.context.scene.objects):
        if obj.get("SYS01_geometry") == "bottom_logo_inlay":
            bpy.data.objects.remove(obj, do_unlink=True)

    base = prism("V012_Base_TrueParallelOffset", outer_hex, -BASE_THICKNESS_MM, 0)
    bevel = base.modifiers.new("Printable rounded outer edges", "BEVEL")
    bevel.width = BEVEL_MM
    bevel.segments = 4
    bevel.affect = "EDGES"
    bpy.context.view_layer.objects.active = base
    bpy.ops.object.modifier_apply(modifier=bevel.name)
    recess = prism("V012_Terrain_Recess_TrueOffset", recess_hex, -RECESS_DEPTH_MM, 0.1)
    difference(base, recess, "True-offset terrain recess")

    # Preserve the established six-magnet pattern, scaled from the actual outer outline.
    ox = max(p.x for p in outer_hex) - cx
    oy = max(p.y for p in outer_hex) - cy
    centers = [
        (cx - 0.5 * ox, cy - 0.82 * oy), (cx + 0.5 * ox, cy - 0.82 * oy),
        (cx + 0.82 * ox, cy), (cx + 0.5 * ox, cy + 0.82 * oy),
        (cx - 0.5 * ox, cy + 0.82 * oy), (cx - 0.82 * ox, cy),
    ]
    for index, (x, y) in enumerate(centers, 1):
        bpy.ops.mesh.primitive_cylinder_add(
            vertices=48, radius=MAGNET_DIAMETER_MM / 2,
            depth=MAGNET_DEPTH_MM + 0.1,
            location=(x, y, -BASE_THICKNESS_MM + MAGNET_DEPTH_MM / 2 - 0.05),
        )
        difference(base, bpy.context.object, f"Magnet pocket {index}")
    if material:
        base.data.materials.append(material)
    base["S05_geometry"] = "display_base"
    base["S08_geometry"] = "terrain_seat_recess_true_offset"
    base["Construction method"] = "true_parallel_polygon_offset"
    base["Slot clearance mm"] = SLOT_CLEARANCE_MM
    base["Border width mm"] = BORDER_WIDTH_MM

    terrain_angles = edge_angles(terrain_hex)
    recess_angles = edge_angles(recess_hex)
    outer_angles = edge_angles(outer_hex)
    def parallel_difference(left, right):
        return abs((left - right + 90.0) % 180.0 - 90.0)

    deviations = [
        max(
            parallel_difference(terrain_angles[i], recess_angles[i]),
            parallel_difference(recess_angles[i], outer_angles[i]),
        )
        for i in range(6)
    ]
    report = {
        "method": "true_euclidean_convex_polygon_offset",
        "terrain_size_mm": [width, height],
        "slot_clearance_mm": SLOT_CLEARANCE_MM,
        "border_width_mm": BORDER_WIDTH_MM,
        "outer_size_mm": [
            max(p.x for p in outer_hex) - min(p.x for p in outer_hex),
            max(p.y for p in outer_hex) - min(p.y for p in outer_hex),
        ],
        "terrain_edge_angles_deg": terrain_angles,
        "recess_edge_angles_deg": recess_angles,
        "outer_edge_angles_deg": outer_angles,
        "max_parallel_deviation_deg": max(deviations),
        "center": [cx, cy],
        "quality": quality(base),
    }
    if report["max_parallel_deviation_deg"] > 1e-5:
        raise RuntimeError("Parallel-edge validation failed: " + json.dumps(report))
    if report["quality"]["non_manifold_edges"]:
        raise RuntimeError("Base is non-manifold: " + json.dumps(report))
    output.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    bpy.ops.wm.save_as_mainfile(filepath=str(output))
    print("TRUE_OFFSET_BASE=" + json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
