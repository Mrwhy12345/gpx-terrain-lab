#!/usr/bin/env python3
"""Rebuild a base from the measured frame inner contour with uniform glue clearance."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector

FRAME_INNER = [
    Vector((-27.13545, -50.0)), Vector((27.13545, -50.0)),
    Vector((57.270935, 0.0)), Vector((27.13545, 50.0)),
    Vector((-27.13545, 50.0)), Vector((-57.270935, 0.0)),
]
CLEARANCE = 0.30
BASE_THICKNESS = 8.0
RECESS_CLEARANCE = 0.30
RECESS_DEPTH = 0.8
BEVEL = 1.2
MAGNET_DIAMETER = 5.3
MAGNET_DEPTH = 3.2


def line_intersection(a, b, c, d):
    ab, cd, ac = b - a, d - c, c - a
    cross = ab.x * cd.y - ab.y * cd.x
    if abs(cross) < 1e-9:
        raise ValueError("Parallel adjacent polygon edges")
    t = (ac.x * cd.y - ac.y * cd.x) / cross
    return a + ab * t


def offset_polygon(points, distance):
    shifted = []
    for i, start in enumerate(points):
        end = points[(i + 1) % len(points)]
        edge = end - start
        outward = Vector((edge.y, -edge.x)).normalized()
        shifted.append((start + outward * distance, end + outward * distance))
    return [
        line_intersection(shifted[i - 1][0], shifted[i - 1][1], shifted[i][0], shifted[i][1])
        for i in range(len(points))
    ]


def prism(name, outline, z0, z1):
    n = len(outline)
    verts = [(p.x, p.y, z) for z in (z0, z1) for p in outline]
    faces = [tuple(reversed(range(n))), tuple(range(n, 2 * n))]
    faces.extend((i, (i + 1) % n, n + (i + 1) % n, n + i) for i in range(n))
    mesh = bpy.data.meshes.new(name + "_Mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def difference(target, cutter, name):
    mod = target.modifiers.new(name, "BOOLEAN")
    mod.operation = "DIFFERENCE"
    mod.solver = "MANIFOLD"
    mod.object = cutter
    bpy.context.view_layer.objects.active = target
    bpy.ops.object.modifier_apply(modifier=mod.name)
    bpy.data.objects.remove(cutter, do_unlink=True)


def quality(obj):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    result = {
        "vertices": len(bm.verts), "faces": len(bm.faces),
        "non_manifold_edges": sum(not edge.is_manifold for edge in bm.edges),
    }
    bm.free()
    return result


def main():
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if len(args) != 2:
        raise SystemExit("Expected OUTPUT.blend REPORT.json")
    output, report_path = map(Path, args)
    terrain = next(o for o in bpy.context.scene.objects if o.get("Object type") == "TERRAIN_LOW_GREEN")
    pts = [terrain.matrix_world @ v.co for v in terrain.data.vertices]
    xmin, xmax = min(p.x for p in pts), max(p.x for p in pts)
    ymin, ymax = min(p.y for p in pts), max(p.y for p in pts)
    cx, cy = (xmin + xmax) / 2, (ymin + ymax) / 2
    width, height = xmax - xmin, ymax - ymin
    terrain_hex = [
        Vector((cx - width / 4, cy - height / 2)), Vector((cx + width / 4, cy - height / 2)),
        Vector((cx + width / 2, cy)), Vector((cx + width / 4, cy + height / 2)),
        Vector((cx - width / 4, cy + height / 2)), Vector((cx - width / 2, cy)),
    ]
    recess = offset_polygon(terrain_hex, RECESS_CLEARANCE)
    outer = [p + Vector((cx, cy)) for p in offset_polygon(FRAME_INNER, -CLEARANCE)]

    old_base = next(
        (o for o in bpy.context.scene.objects if o.get("S05_geometry") == "display_base"),
        None,
    )
    material = old_base.data.materials[0] if old_base is not None and old_base.data.materials else None
    if old_base is not None:
        bpy.data.objects.remove(old_base, do_unlink=True)
    if material is None:
        material = bpy.data.materials.get("Base Gray") or bpy.data.materials.new("Base Gray")
        material.diffuse_color = (0.35, 0.38, 0.40, 1.0)
    for obj in list(bpy.context.scene.objects):
        if obj.get("SYS01_geometry") == "bottom_logo_inlay":
            bpy.data.objects.remove(obj, do_unlink=True)

    base = prism("V003_Base_FrameParallelGlueFit", outer, -BASE_THICKNESS, 0)
    bevel = base.modifiers.new("Printable rounded edges", "BEVEL")
    bevel.width, bevel.segments, bevel.affect = BEVEL, 4, "EDGES"
    bpy.context.view_layer.objects.active = base
    bpy.ops.object.modifier_apply(modifier=bevel.name)
    difference(base, prism("Terrain_Recess", recess, -RECESS_DEPTH, 0.1), "Terrain seat")

    ox = max(p.x for p in outer) - cx
    oy = max(p.y for p in outer) - cy
    centers = [
        (cx - .5*ox, cy - .82*oy), (cx + .5*ox, cy - .82*oy),
        (cx + .82*ox, cy), (cx + .5*ox, cy + .82*oy),
        (cx - .5*ox, cy + .82*oy), (cx - .82*ox, cy),
    ]
    for i, (x, y) in enumerate(centers, 1):
        bpy.ops.mesh.primitive_cylinder_add(
            vertices=48, radius=MAGNET_DIAMETER/2, depth=MAGNET_DEPTH+.1,
            location=(x, y, -BASE_THICKNESS + MAGNET_DEPTH/2 - .05),
        )
        difference(base, bpy.context.object, f"Magnet pocket {i}")
    if material:
        base.data.materials.append(material)
    base["S05_geometry"] = "display_base"
    # Keep the shared contract used by label placement, while recording the
    # more specific frame-derived method separately.
    base["Construction method"] = "true_parallel_polygon_offset"
    base["Frame fit method"] = "frame_inner_true_parallel_offset"
    base["Frame clearance mm"] = CLEARANCE
    base["Slot clearance mm"] = RECESS_CLEARANCE
    base["Rubber strip recommendation mm"] = "0.3-0.5 soft silicone, discontinuous placement"
    base["Side edge angle deg"] = math.degrees(
        math.atan2(outer[2].y - outer[1].y, outer[2].x - outer[1].x)
    )
    q = quality(base)
    if q["non_manifold_edges"]:
        raise RuntimeError("Non-manifold rebuilt base: " + json.dumps(q))

    edge_lengths = [
        (outer[(i+1)%6] - outer[i]).length for i in range(6)
    ]
    report = {
        "method": "measured_frame_inner_contour_true_parallel_inset",
        "frame_inner_vertices": [[p.x, p.y] for p in FRAME_INNER],
        "clearance_mm_per_edge": CLEARANCE,
        "base_outer_vertices": [[p.x, p.y] for p in outer],
        "base_outer_bounds_mm": [
            max(p.x for p in outer)-min(p.x for p in outer),
            max(p.y for p in outer)-min(p.y for p in outer),
        ],
        "edge_lengths_mm": edge_lengths,
        "terrain_bounds_mm": [width, height],
        "rubber_strip": {"recommended_thickness_mm": [0.3, 0.5], "placement": "3-6 short sections"},
        "quality": q,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    bpy.ops.wm.save_as_mainfile(filepath=str(output))
    print("FRAME_GLUE_FIT_BASE=" + json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
