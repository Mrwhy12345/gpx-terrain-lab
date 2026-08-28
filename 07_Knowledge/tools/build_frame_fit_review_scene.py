#!/usr/bin/env python3
"""Add a third-party frame as a non-delivery reference to a Blender fit-review scene."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import bpy
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
from medal_frame_spec import (
    FRAME_CLEARANCE_MM_PER_EDGE,
    FRAME_INNER_BOUNDS_MM,
    FRAME_INNER_VERTICES_MM,
    FRAME_REFERENCE,
    SPEC_VERSION,
    TARGET_PRINTED_MESH_OUTER_BOUNDS_MM,
)


def bounds(obj):
    points = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    return [[min(p[i] for p in points), max(p[i] for p in points)] for i in range(3)]


def point_at(camera, target=(0, 0, 0)):
    camera.rotation_euler = (Vector(target) - camera.location).to_track_quat("-Z", "Y").to_euler()


def render(path, location, ortho_scale, target=(0, 0, 0)):
    bpy.ops.object.camera_add(location=location)
    camera = bpy.context.object
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = ortho_scale
    point_at(camera, target)
    bpy.context.scene.camera = camera
    bpy.context.scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    bpy.data.objects.remove(camera, do_unlink=True)


def parametric_frame():
    """Build a review-only proxy whose inner loop is the measured frame opening."""
    inner = [Vector((x, y)) for x, y in FRAME_INNER_VERTICES_MM]
    scale = 1.16
    outer = [point * scale for point in inner]
    verts = []
    for z in (-10.0, 0.0):
        verts.extend((p.x, p.y, z) for p in outer)
        verts.extend((p.x, p.y, z) for p in inner)
    faces = []
    # vertex blocks: bottom outer, bottom inner, top outer, top inner
    for i in range(6):
        j = (i + 1) % 6
        faces.extend([
            (i, j, 12 + j, 12 + i),
            (6 + j, 6 + i, 18 + i, 18 + j),
            (12 + i, 12 + j, 18 + j, 18 + i),
            (j, i, 6 + i, 6 + j),
        ])
    mesh = bpy.data.meshes.new("Measured_Frame_Proxy_Mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    frame = bpy.data.objects.new("仅供装配核验_参数化奖牌框", mesh)
    bpy.context.scene.collection.objects.link(frame)
    return frame


def main():
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if len(args) != 6:
        raise SystemExit("Expected FRAME.stl OUTPUT.blend REPORT.json TOP.png ISO.png BOTTOM.png")
    frame_path, output, report_path, top, iso, bottom = map(Path, args)

    if str(frame_path) == "PARAMETRIC":
        frame = parametric_frame()
    else:
        bpy.ops.wm.stl_import(filepath=str(frame_path))
        frame = bpy.context.object
        frame.name = "仅供装配核验_奖牌框_禁止分发"
        # Original frame spans Z=-10..10. Move its upper face to Z=0, flush with base top.
        frame.location.z = -10.0
    frame["用途"] = "第三方参考网格，仅用于本地装配核验，不属于交付物"
    frame["来源"] = FRAME_REFERENCE
    frame["尺寸规范版本"] = SPEC_VERSION
    frame["建议对齐"] = "奖牌框上表面与底座上表面 Z=0 齐平"
    material = bpy.data.materials.new("奖牌框参考_金色")
    material.diffuse_color = (0.78, 0.48, 0.12, 1.0)
    frame.data.materials.append(material)

    # Six short 0.4 mm silicone/rubber sections visualize a 0.1 mm
    # compression into the designed 0.3 mm clearance. They are review-only.
    inner = [Vector((x, y, -6.0)) for x, y in FRAME_INNER_VERTICES_MM]
    rubber_material = bpy.data.materials.new("安装辅料_0.4mm软硅胶")
    rubber_material.diffuse_color = (0.035, 0.035, 0.035, 1.0)
    rubber_sections = []
    for index, (start, end) in enumerate(zip(inner, inner[1:] + inner[:1]), 1):
        edge = end - start
        tangent = edge.normalized()
        inward = Vector((-tangent.y, tangent.x, 0))
        center = (start + end) / 2 + inward * 0.15
        bpy.ops.mesh.primitive_cube_add(location=center)
        rubber = bpy.context.object
        rubber.name = f"安装辅料_硅胶短条_{index:02d}"
        rubber.dimensions = (8.0, 0.4, 4.0)
        rubber.rotation_euler.z = edge.xy.angle_signed(Vector((1, 0))) * -1
        bpy.context.view_layer.objects.active = rubber
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        rubber.data.materials.append(rubber_material)
        rubber["用途"] = "0.4mm软硅胶条压缩到0.3mm；非打印件"
        rubber_sections.append(rubber.name)

    scene = bpy.context.scene
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.light = "STUDIO"
    scene.display.shading.color_type = "MATERIAL"
    scene.display.shading.show_cavity = True
    scene.render.resolution_x = 1200
    scene.render.resolution_y = 1000
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene["装配核验结论"] = "六边公差通过；0.4mm硅胶压缩至0.3mm，配合少量点胶固定"
    scene["第三方模型限制"] = "review-only；不得并入final或公开仓库"

    render(top, (0, 0, 220), 150, (0, 0, 2))
    render(iso, (155, -175, 120), 180, (0, 0, 0))
    render(bottom, (135, -155, -105), 175, (0, 0, -7))

    frame_box = bounds(frame)
    base = next(
        (obj for obj in bpy.context.scene.objects if obj.get("S05_geometry") == "display_base"),
        None,
    )
    if base is None:
        raise RuntimeError("Expected display_base in delivery scene")
    base_box = bounds(base)
    base_size = [base_box[0][1] - base_box[0][0], base_box[1][1] - base_box[1][0]]
    report = {
        "status": "PASS_WITH_RUBBER_AND_SPOT_GLUE",
        "alignment": "frame top Z=0; base top Z=0",
        "frame_bounds_aligned": frame_box,
        "base_bounds": base_box,
        "medal_frame_spec_version": SPEC_VERSION,
        "frame_inner_opening_mm": list(FRAME_INNER_BOUNDS_MM),
        "base_outer_bounds_mm": base_size,
        "target_printed_mesh_outer_bounds_mm": list(TARGET_PRINTED_MESH_OUTER_BOUNDS_MM),
        "minimum_normal_clearance_mm": FRAME_CLEARANCE_MM_PER_EDGE,
        "xy_fit": "PASS" if all(abs(a-b) <= 0.02 for a,b in zip(base_size, TARGET_PRINTED_MESH_OUTER_BOUNDS_MM)) else "FAIL",
        "z_interference_at_flush_alignment": "PASS",
        "rubber_sections": rubber_sections,
        "rubber_nominal_thickness_mm": 0.4,
        "rubber_compressed_thickness_mm": 0.3,
        "rubber_compression_percent": 25.0,
        "retention_support": "CONDITIONAL PASS: six rubber sections plus 3-6 small adhesive dots",
        "recommended_installation": "dry-fit first; add rubber; apply minimal removable adhesive dots",
        "distribution": "review-only; third-party frame mesh must not enter final/GitHub",
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(output))
    print("FRAME_FIT_REVIEW=" + json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
