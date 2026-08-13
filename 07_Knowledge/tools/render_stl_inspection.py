#!/usr/bin/env python3
"""Render top and isometric inspection images for an STL loaded in Blender."""

from __future__ import annotations

import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector


def point_at(obj, target=(0, 0, 0)):
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat("-Z", "Y").to_euler()


def render(path, location, ortho_scale):
    bpy.ops.object.camera_add(location=location)
    camera = bpy.context.object
    point_at(camera)
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = ortho_scale
    bpy.context.scene.camera = camera
    bpy.context.scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    bpy.data.objects.remove(camera, do_unlink=True)


def main():
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if len(args) != 3:
        raise SystemExit("Expected INPUT.stl TOP.png ISO.png")
    source, top, iso = map(Path, args)
    bpy.ops.wm.stl_import(filepath=str(source))
    obj = bpy.context.object
    material = bpy.data.materials.new("Inspection Gray")
    material.diffuse_color = (0.55, 0.58, 0.62, 1)
    obj.data.materials.append(material)
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.light = "STUDIO"
    scene.display.shading.color_type = "MATERIAL"
    scene.display.shading.show_cavity = True
    scene.render.resolution_x = 1200
    scene.render.resolution_y = 1000
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    render(top, (0, 0, 220), 150)
    render(iso, (150, -170, 130), 175)


if __name__ == "__main__":
    main()
