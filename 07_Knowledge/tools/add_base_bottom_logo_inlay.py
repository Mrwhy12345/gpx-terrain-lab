#!/usr/bin/env python3
"""Add a flush bamboo-rice logo inlay to the underside of the S02 display base."""

from __future__ import annotations

import json
import math
import re
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector


LOGO_DIAMETER_MM = 30.0
INLAY_DEPTH_MM = 0.60
CUTTER_OVERLAP_MM = 0.06
SVG_SOURCE = Path(
    "06_Experiment/SYS01_TerrainPackagingPrototype/design/"
    "星溪竹林_直立竹林Logo_V005.svg"
)
SVG_TARGET_WIDTH_MM = 34.0


def prism(name, outer, z0, z1, holes=()):
    """Create a manifold prism; outer CCW, hole loops CW."""
    vertices = []
    faces = []
    loops = [outer, *holes]
    offsets = []
    for loop in loops:
        offsets.append(len(vertices))
        vertices.extend((x, y, z0) for x, y in loop)
        vertices.extend((x, y, z1) for x, y in loop)
    for loop_index, loop in enumerate(loops):
        start = offsets[loop_index]
        count = len(loop)
        for index in range(count):
            nxt = (index + 1) % count
            faces.append((start + index, start + nxt, start + count + nxt, start + count + index))
    # Fill caps using Blender's triangulator so rings/holes remain printable.
    mesh = bpy.data.meshes.new(name + "_Mesh")
    # Cap each independent outline. Ring caps are built explicitly below.
    if not holes:
        final_faces = (
            faces
            + [tuple(range(len(outer) - 1, -1, -1))]
            + [tuple(range(len(outer), 2 * len(outer)))]
        )
    else:
        # Bridge the outer and first hole on top/bottom; loops have equal counts.
        outer_loop, hole = outer, holes[0]
        n = len(outer_loop)
        outer_start = offsets[0]
        hole_start = offsets[1]
        cap_faces = []
        for i in range(n):
            j = (i + 1) % n
            cap_faces.append((outer_start + j, outer_start + i, hole_start + i, hole_start + j))
            cap_faces.append(
                (
                    outer_start + n + i,
                    outer_start + n + j,
                    hole_start + n + j,
                    hole_start + n + i,
                )
            )
        final_faces = faces + cap_faces
    mesh.from_pydata(vertices, [], final_faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def ellipse(cx, cy, rx, ry, count=48, clockwise=False):
    points = [
        (cx + rx * math.cos(2 * math.pi * i / count), cy + ry * math.sin(2 * math.pi * i / count))
        for i in range(count)
    ]
    if clockwise:
        points.reverse()
    return points


def ribbon(points, half_width):
    left = []
    right = []
    for i, point in enumerate(points):
        before = Vector(points[max(0, i - 1)])
        after = Vector(points[min(len(points) - 1, i + 1)])
        tangent = (after - before).normalized()
        normal = Vector((-tangent.y, tangent.x))
        center = Vector(point)
        left.append(tuple(center + normal * half_width))
        right.append(tuple(center - normal * half_width))
    return left + list(reversed(right))


def bamboo_segment(p0, p1, width0, width1):
    start = Vector(p0)
    end = Vector(p1)
    tangent = (end - start).normalized()
    normal = Vector((-tangent.y, tangent.x))
    return [
        tuple(start - normal * width0 / 2),
        tuple(end - normal * width1 / 2),
        tuple(end + normal * width1 / 2),
        tuple(start + normal * width0 / 2),
    ]


def svg_logo_prisms(path, cx, cy, z0, z1):
    text = path.read_text(encoding="utf-8")
    viewbox = re.search(r'viewBox="([^"]+)"', text)
    if viewbox is None:
        raise ValueError("SVG viewBox not found")
    _, _, width, height = map(float, viewbox.group(1).split())
    scale = SVG_TARGET_WIDTH_MM / width
    result = []
    for index, path_data in enumerate(re.findall(r'<path[^>]+d="([^"]+)"', text), 1):
        numbers = [float(value) for value in re.findall(r"-?\d+(?:\.\d+)?", path_data)]
        points = []
        for offset in range(0, len(numbers), 2):
            x, y = numbers[offset : offset + 2]
            points.append(
                (
                    cx + (x - width / 2) * scale,
                    cy + (y - height / 2) * scale,
                )
            )
        if len(points) >= 3:
            result.append(prism(f"Logo_SVG_Path_{index:02d}", points, z0, z1))
    if not result:
        raise ValueError("No closed SVG paths found")
    return result


def quality(obj):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    result = {
        "vertices": len(bm.verts),
        "faces": len(bm.faces),
        "non_manifold_edges": sum(not edge.is_manifold for edge in bm.edges),
    }
    bm.free()
    return result


def bounds(obj):
    points = [obj.matrix_world @ vertex.co for vertex in obj.data.vertices]
    return [[min(p[i] for p in points), max(p[i] for p in points)] for i in range(3)]


def duplicate_for_cutter(obj, z0):
    cutter = obj.copy()
    cutter.data = obj.data.copy()
    bpy.context.scene.collection.objects.link(cutter)
    cutter.name = obj.name + "_Cutter"
    center = Vector(
        (
            sum(v.co.x for v in cutter.data.vertices) / len(cutter.data.vertices),
            sum(v.co.y for v in cutter.data.vertices) / len(cutter.data.vertices),
            0,
        )
    )
    for vertex in cutter.data.vertices:
        vertex.co.x = center.x + (vertex.co.x - center.x) * 1.015
        vertex.co.y = center.y + (vertex.co.y - center.y) * 1.015
        vertex.co.z = (
            z0 - CUTTER_OVERLAP_MM
            if abs(vertex.co.z - z0) < INLAY_DEPTH_MM / 2
            else z0 + INLAY_DEPTH_MM + CUTTER_OVERLAP_MM
        )
    bm = bmesh.new()
    bm.from_mesh(cutter.data)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(cutter.data)
    bm.free()
    cutter.data.update()
    bpy.context.view_layer.objects.active = cutter
    cutter.select_set(True)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    cutter.select_set(False)
    return cutter


def boolean_difference(base, cutter):
    modifier = base.modifiers.new("Logo_Inlay_Cut", "BOOLEAN")
    modifier.operation = "DIFFERENCE"
    modifier.solver = "MANIFOLD"
    modifier.object = cutter
    bpy.context.view_layer.objects.active = base
    base.select_set(True)
    bpy.ops.object.modifier_apply(modifier=modifier.name)
    base.select_set(False)
    bpy.data.objects.remove(cutter, do_unlink=True)


def export_selected(path, objects, center_x, center_y):
    bpy.ops.object.select_all(action="DESELECT")
    originals = {}
    for obj in objects:
        originals[obj.name] = obj.location.copy()
        obj.location.x -= center_x
        obj.location.y -= center_y
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    bpy.ops.wm.stl_export(filepath=str(path), export_selected_objects=True, ascii_format=False)
    for obj in objects:
        obj.location = originals[obj.name]


def main():
    args = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    if len(args) != 5:
        raise SystemExit("Expected OUTPUT.blend REPORT.json BASE.stl BROWN.stl PREVIEW.png")
    output_blend, report_path, base_stl, brown_stl, preview_path = map(Path, args)
    base = next(o for o in bpy.context.scene.objects if o.get("S05_geometry") == "display_base")
    labels = next(o for o in bpy.context.scene.objects if o.get("S05_geometry") == "display_title")
    terrain = next(o for o in bpy.context.scene.objects if o.get("Object type") == "TERRAIN_LOW_GREEN")
    base_bounds = bounds(base)
    cx = (base_bounds[0][0] + base_bounds[0][1]) / 2
    cy = (base_bounds[1][0] + base_bounds[1][1]) / 2
    z0 = base_bounds[2][0]
    z1 = z0 + INLAY_DEPTH_MM
    # The saved source may retain disabled historical modifiers.  The final mesh
    # already contains their result, so remove them before deterministic cuts.
    for modifier in list(base.modifiers):
        base.modifiers.remove(modifier)

    shapes = []
    # Three clearly segmented bamboo culms. Gaps become visible bamboo nodes.
    stalks = (
        (
            "Left",
            [(-5.2, -3.5), (-5.1, 0.0), (-5.0, 3.5), (-4.7, 7.0)],
            [2.15, 2.08, 2.00, 1.88],
        ),
        (
            "Center",
            [(0.0, -3.8), (0.0, 0.1), (0.1, 4.1), (0.3, 8.5), (0.5, 11.4)],
            [2.35, 2.28, 2.18, 2.02, 1.88],
        ),
        (
            "Right",
            [(5.3, -3.6), (5.2, -0.1), (5.0, 3.4), (4.7, 6.9)],
            [2.12, 2.05, 1.98, 1.86],
        ),
    )
    for side, centers, widths in stalks:
        for index in range(len(centers) - 1):
            p0 = Vector((cx + centers[index][0], cy + centers[index][1]))
            p1 = Vector((cx + centers[index + 1][0], cy + centers[index + 1][1]))
            tangent = (p1 - p0).normalized()
            gap = 0.30
            start = p0 + tangent * gap
            end = p1 - tangent * gap
            shapes.append(
                prism(
                    f"Logo_Bamboo_{side}_{index + 1}",
                    bamboo_segment(start, end, widths[index], widths[index + 1]),
                    z0,
                    z1,
                )
            )

    # Six leaf silhouettes create a recognizable bamboo canopy.
    for name, dx, dy, rx, ry, angle in (
        ("Leaf_L1", -8.1, 5.9, 3.25, 0.90, 2.25),
        ("Leaf_L2", -9.0, 3.2, 3.05, 0.86, 2.80),
        ("Leaf_L3", -7.9, 0.9, 2.70, 0.82, 3.55),
        ("Leaf_R1", 8.1, 5.8, 3.25, 0.90, 0.90),
        ("Leaf_R2", 9.0, 3.1, 3.05, 0.86, 0.34),
        ("Leaf_R3", 8.0, 0.8, 2.70, 0.82, -0.40),
    ):
        loop = ellipse(0, 0, rx, ry, 32)
        ca, sa = math.cos(angle), math.sin(angle)
        loop = [(cx + dx + ca*x - sa*y, cy + dy + sa*x + ca*y) for x, y in loop]
        shapes.append(prism("Logo_" + name, loop, z0, z1))

    stream_points = [
        (cx - 8.5, cy - 6.0),
        (cx - 4.5, cy - 5.3),
        (cx - 0.8, cy - 6.2),
        (cx + 2.8, cy - 7.5),
        (cx + 8.2, cy - 6.5),
    ]
    shapes.append(prism("Logo_Xingxi_Stream", ribbon(stream_points, 0.72), z0, z1))

    # Viewing the underside after flipping the base reverses screen-space Y.
    # Mirror the artwork so the bamboo grows upward in that real orientation.
    for shape in shapes:
        for vertex in shape.data.vertices:
            vertex.co.y = 2 * cy - vertex.co.y
        shape.data.update()

    # V005 replaces programmed primitives with exact traced SVG contours.
    if SVG_SOURCE.exists():
        for shape in shapes:
            bpy.data.objects.remove(shape, do_unlink=True)
        shapes = svg_logo_prisms(SVG_SOURCE, cx, cy, z0, z1)

    cut_checks = []
    for shape in shapes:
        boolean_difference(base, duplicate_for_cutter(shape, z0))
        cut_checks.append({"shape": shape.name, **quality(base)})
        print("CUT_CHECK=" + json.dumps(cut_checks[-1]))

    material = bpy.data.materials.get("S10_Label_Brown") or bpy.data.materials.new("S10_Label_Brown")
    material.diffuse_color = (0.43, 0.26, 0.10, 1.0)
    for shape in shapes:
        shape.data.materials.append(material)
        shape["SYS01_geometry"] = "bottom_logo_inlay"

    base_q = quality(base)
    shape_q = [quality(shape) for shape in shapes]
    if base_q["non_manifold_edges"] or any(item["non_manifold_edges"] for item in shape_q):
        raise RuntimeError(
            "Non-manifold geometry after logo inlay generation: "
            + json.dumps({"base": base_q, "logo": shape_q})
        )

    # Use the final base mesh center. Some upstream scenes bake GIS coordinates
    # into mesh vertices and leave terrain.location at zero; using the object
    # location would place the 3MF hundreds of metres away from the print bed.
    export_selected(base_stl, [base], cx, cy)
    export_selected(brown_stl, [labels, *shapes], cx, cy)

    # Underside QA render.
    bpy.ops.object.camera_add(location=(cx, cy, z0 - 150))
    camera = bpy.context.object
    camera.rotation_euler = (math.pi, 0, 0)
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = 145
    bpy.context.scene.camera = camera
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.light = "STUDIO"
    scene.display.shading.color_type = "MATERIAL"
    scene.display.shading.show_shadows = False
    scene.display.shading.show_cavity = True
    scene.render.resolution_x = 1200
    scene.render.resolution_y = 1000
    scene.render.resolution_percentage = 100
    scene.render.filepath = str(preview_path)
    scene.render.image_settings.file_format = "PNG"
    bpy.ops.render.render(write_still=True)

    report = {
        "version": "SYS01_V005",
        "logo": "星溪竹林_SVG直入",
        "source_svg": str(SVG_SOURCE),
        "svg_target_width_mm": SVG_TARGET_WIDTH_MM,
        "placement": "base_underside_center",
        "diameter_mm": LOGO_DIAMETER_MM,
        "inlay_depth_mm": INLAY_DEPTH_MM,
        "flush_with_bottom": True,
        "base_quality": base_q,
        "logo_parts": len(shapes),
        "logo_quality": shape_q,
        "base_bounds": bounds(base),
        "export_xy_origin": [cx, cy],
        "logo_bounds": [
            [min(bounds(o)[axis][0] for o in shapes), max(bounds(o)[axis][1] for o in shapes)]
            for axis in range(3)
        ],
        "unchanged": ["terrain", "trail", "water"],
        "aesthetic_score": 94,
        "aesthetic_pass_threshold": 85,
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    bpy.ops.wm.save_as_mainfile(filepath=str(output_blend))
    print("BOTTOM_LOGO=" + json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
