#!/usr/bin/env python3
"""Render a strict top view for three-edge label centering QA."""

from __future__ import annotations

import sys
from pathlib import Path

import bpy
from mathutils import Vector


def material(name, color):
    result = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    result.diffuse_color = (*color, 1.0)
    return result


def assign(obj, value):
    obj.data.materials.clear()
    obj.data.materials.append(value)


def main():
    args = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    if len(args) != 1:
        raise SystemExit("Expected OUTPUT.png")
    output = Path(args[0])
    output.parent.mkdir(parents=True, exist_ok=True)
    base = next(o for o in bpy.context.scene.objects if o.get("S05_geometry") == "display_base")
    labels = next(o for o in bpy.context.scene.objects if o.get("S05_geometry") == "display_title")
    terrain = next(o for o in bpy.context.scene.objects if o.get("Object type") == "TERRAIN_LOW_GREEN")
    assign(base, material("QA_Base", (0.32, 0.34, 0.37)))
    assign(labels, material("QA_Labels", (0.85, 0.48, 0.08)))

    for obj in bpy.context.scene.objects:
        if obj.type == "MESH" and obj not in {base, labels}:
            obj.hide_render = True

    camera_data = bpy.data.cameras.new("Label_Center_QA_Camera")
    camera = bpy.data.objects.new("Label_Center_QA_Camera", camera_data)
    bpy.context.scene.collection.objects.link(camera)
    camera.location = (terrain.location.x, terrain.location.y, 80)
    camera.rotation_euler = (0, 0, 0)
    camera_data.type = "ORTHO"
    camera_data.ortho_scale = 142
    bpy.context.scene.camera = camera

    scene = bpy.context.scene
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.light = "FLAT"
    scene.display.shading.color_type = "MATERIAL"
    scene.display.shading.show_shadows = False
    scene.display.shading.show_cavity = True
    scene.render.resolution_x = 1400
    scene.render.resolution_y = 1100
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = str(output)
    scene.world.color = (0.025, 0.025, 0.025)
    bpy.ops.render.render(write_still=True)
    print(f"THREE_EDGE_LABEL_QA={output}")


if __name__ == "__main__":
    main()
