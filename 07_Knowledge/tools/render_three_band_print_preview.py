#!/usr/bin/env python3
"""Render the finalized printable three-band 1.50x model."""

from __future__ import annotations

import sys
from pathlib import Path

import bpy
from mathutils import Vector


def material(name, color):
    result = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    result.diffuse_color = (*color, 1.0)
    return result


def assign(obj, mat):
    obj.data.materials.clear()
    obj.data.materials.append(mat)


def look_at(obj, point):
    obj.rotation_euler = (point - obj.location).to_track_quat("-Z", "Y").to_euler()


def main():
    args = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    if len(args) != 1:
        raise SystemExit("Usage: blender FILE.blend --python script.py -- OUTPUT.png")
    output = Path(args[0])
    output.parent.mkdir(parents=True, exist_ok=True)
    green = material("FINAL_Green", (0.28, 0.43, 0.10))
    brown = material("FINAL_Brown", (0.43, 0.26, 0.10))
    gray = material("FINAL_Gray", (0.47, 0.51, 0.54))
    blue = material("FINAL_Blue", (0.01, 0.35, 0.95))
    red = material("FINAL_Red", (0.92, 0.025, 0.015))

    low = next(
        obj
        for obj in bpy.context.scene.objects
        if obj.get("Object type") == "TERRAIN_LOW_GREEN"
    )
    for obj in bpy.context.scene.objects:
        if obj.type != "MESH":
            continue
        object_type = obj.get("Object type")
        if object_type == "TERRAIN_LOW_GREEN":
            assign(obj, green)
        elif object_type == "TERRAIN_MIDDLE_BROWN":
            assign(obj, brown)
        elif object_type == "TERRAIN_HIGH_GRAY":
            assign(obj, gray)
        elif obj.get("S02_geometry") in {"stream_ribbon", "water_area"}:
            assign(obj, blue)
        elif obj.get("Object type") in {"TRAIL", "TRAIL_INSERT"}:
            assign(obj, red)
        elif obj.get("S04_geometry") == "residential_areas_printable":
            assign(obj, brown)
        elif obj.get("S05_geometry") == "display_base":
            assign(obj, gray)
        elif obj.get("S05_geometry") == "display_title":
            assign(obj, brown)

    center = low.matrix_world @ Vector((0, 0, low.dimensions.z * 0.7))
    camera_data = bpy.data.cameras.new("Final_ThreeBand_Camera")
    camera = bpy.data.objects.new("Final_ThreeBand_Camera", camera_data)
    bpy.context.scene.collection.objects.link(camera)
    camera.location = center + Vector((76, -100, 78))
    look_at(camera, center)
    camera_data.type = "ORTHO"
    camera_data.ortho_scale = 142
    bpy.context.scene.camera = camera
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.light = "STUDIO"
    scene.display.shading.color_type = "MATERIAL"
    scene.display.shading.show_shadows = True
    scene.display.shading.show_cavity = True
    scene.display.shading.cavity_type = "WORLD"
    scene.render.resolution_x = 1200
    scene.render.resolution_y = 900
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = str(output)
    scene.world.color = (0.022, 0.025, 0.027)
    bpy.ops.render.render(write_still=True)
    print(f"FINAL_THREE_BAND_PREVIEW={output}")


if __name__ == "__main__":
    main()
