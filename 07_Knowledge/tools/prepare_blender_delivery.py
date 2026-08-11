#!/usr/bin/env python3
"""Save a clean, centered Blender delivery scene with a useful default view."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector


def bounds(obj):
    points = [obj.matrix_world @ v.co for v in obj.data.vertices]
    return [[min(p[i] for p in points), max(p[i] for p in points)] for i in range(3)]


def point_camera(camera, target):
    camera.rotation_euler = (Vector(target) - camera.location).to_track_quat("-Z", "Y").to_euler()


def main():
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if len(args) != 3:
        raise SystemExit("Expected OUTPUT.blend REPORT.json PREVIEW.png")
    output, report_path, preview = map(Path, args)
    visible = []
    hidden_outliers = []
    for obj in bpy.context.scene.objects:
        if obj.type != "MESH" or not obj.data.vertices:
            continue
        item_bounds = bounds(obj)
        center = [sum(axis) / 2 for axis in item_bounds]
        if abs(center[0]) > 500 or abs(center[1]) > 500:
            obj.hide_viewport = True
            obj.hide_render = True
            hidden_outliers.append(obj.name)
        elif not obj.hide_render:
            visible.append(obj)
    if not visible:
        raise RuntimeError("No centered visible delivery meshes")

    for obj in list(bpy.context.scene.objects):
        if obj.type in {"CAMERA", "LIGHT"}:
            bpy.data.objects.remove(obj, do_unlink=True)
    bpy.ops.object.camera_add(location=(125, -145, 115))
    camera = bpy.context.object
    camera.name = "交付默认视角"
    camera.data.lens = 58
    camera.data.clip_start = 0.1
    camera.data.clip_end = 1000
    point_camera(camera, (0, 0, 4))
    bpy.context.scene.camera = camera

    # Save an immediately useful viewport instead of the GIS-scale generation view.
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type != "VIEW_3D":
                continue
            space = area.spaces.active
            space.clip_start = 0.1
            space.clip_end = 1000
            region = space.region_3d
            region.view_location = (0, 0, 4)
            region.view_distance = 145
            region.view_perspective = "CAMERA"

    scene = bpy.context.scene
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.light = "STUDIO"
    scene.display.shading.color_type = "MATERIAL"
    scene.display.shading.show_cavity = True
    scene.render.resolution_x = 1200
    scene.render.resolution_y = 900
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = str(preview)
    bpy.ops.render.render(write_still=True)
    scene["交付提示"] = "打开即为相机视图；按小键盘0返回，Home查看全部可见模型。"
    report = {
        "visible_meshes": [obj.name for obj in visible],
        "hidden_outliers": hidden_outliers,
        "visible_bounds": {
            "x": [min(bounds(o)[0][0] for o in visible), max(bounds(o)[0][1] for o in visible)],
            "y": [min(bounds(o)[1][0] for o in visible), max(bounds(o)[1][1] for o in visible)],
            "z": [min(bounds(o)[2][0] for o in visible), max(bounds(o)[2][1] for o in visible)],
        },
        "camera": list(camera.location),
        "default_view": "camera",
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    bpy.ops.wm.save_as_mainfile(filepath=str(output))
    print("BLENDER_DELIVERY=" + json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
