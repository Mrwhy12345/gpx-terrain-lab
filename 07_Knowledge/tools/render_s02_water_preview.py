#!/usr/bin/env python3
"""Render a top-down QA image of the S02 terrain, trail, and water objects."""

from __future__ import annotations

import math
import sys
from pathlib import Path

import bpy


def material(name, color):
    result = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    result.diffuse_color = (*color, 1.0)
    return result


def assign(obj, mat):
    if not hasattr(obj.data, "materials"):
        return
    obj.data.materials.clear()
    obj.data.materials.append(mat)


def main():
    arguments = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    if len(arguments) != 1:
        raise SystemExit("Usage: blender FILE.blend --python script.py -- OUTPUT.png")
    output = Path(arguments[0])
    output.parent.mkdir(parents=True, exist_ok=True)

    terrain = next(
        obj
        for obj in bpy.context.scene.objects
        if obj.get("Object type") == "MAP"
    )
    terrain_mat = material("QA_Terrain_Green", (0.247, 0.557, 0.263))
    trail_mat = material("QA_Trail", (0.95, 0.05, 0.03))
    water_mat = material("QA_Water", (0.01, 0.28, 1.0))
    road_mat = material("QA_Road", (0.035, 0.04, 0.05))
    assign(terrain, terrain_mat)
    for obj in bpy.context.scene.objects:
        if obj.get("Object type") in {"TRAIL", "TRAIL_INSERT"}:
            assign(obj, trail_mat)
        elif (
            obj.get("Object type") in {"WATER", "OCEAN"}
            or obj.get("S02_geometry") in {"stream_ribbon", "water_area"}
        ):
            assign(obj, water_mat)
        elif obj.get("S03_geometry") == "roads_printable":
            assign(obj, road_mat)

    camera_data = bpy.data.cameras.new("S02_QA_Camera")
    camera = bpy.data.objects.new("S02_QA_Camera", camera_data)
    bpy.context.scene.collection.objects.link(camera)
    camera.location = (
        terrain.location.x,
        terrain.location.y,
        terrain.dimensions.z + 80,
    )
    camera.rotation_euler = (0, 0, 0)
    camera_data.type = "ORTHO"
    camera_data.ortho_scale = 112
    bpy.context.scene.camera = camera

    sun_data = bpy.data.lights.new("S02_QA_Sun", "SUN")
    sun_data.energy = 3.0
    sun = bpy.data.objects.new("S02_QA_Sun", sun_data)
    bpy.context.scene.collection.objects.link(sun)
    sun.rotation_euler = (math.radians(25), math.radians(-20), math.radians(25))

    scene = bpy.context.scene
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.light = "STUDIO"
    scene.display.shading.color_type = "MATERIAL"
    scene.display.shading.show_shadows = True
    scene.display.shading.show_cavity = True
    scene.display.shading.cavity_type = "WORLD"
    scene.render.resolution_x = 1200
    scene.render.resolution_y = 1000
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = str(output)
    scene.world.color = (0.025, 0.025, 0.025)
    bpy.ops.render.render(write_still=True)
    print(f"S02_PREVIEW={output}")


if __name__ == "__main__":
    main()
