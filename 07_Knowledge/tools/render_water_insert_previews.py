#!/usr/bin/env python3
"""Render grooved terrain and separately packed water inserts."""

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


def render(output, visible, center, scale):
    for obj in bpy.context.scene.objects:
        if obj.type == "MESH":
            obj.hide_render = obj not in visible
    camera_data = bpy.data.cameras.new("SYS01_QA_Camera")
    camera = bpy.data.objects.new("SYS01_QA_Camera", camera_data)
    bpy.context.scene.collection.objects.link(camera)
    camera.location = (center.x, center.y, center.z + 100)
    camera.rotation_euler = (0, 0, 0)
    camera_data.type = "ORTHO"
    camera_data.ortho_scale = scale
    bpy.context.scene.camera = camera
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.light = "STUDIO"
    scene.display.shading.color_type = "MATERIAL"
    scene.display.shading.show_shadows = True
    scene.display.shading.show_cavity = True
    scene.render.resolution_x = 1200
    scene.render.resolution_y = 1000
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = str(output)
    scene.world.color = (0.025, 0.025, 0.025)
    bpy.ops.render.render(write_still=True)
    bpy.data.objects.remove(camera, do_unlink=True)


def bounds(objects):
    points = [
        obj.matrix_world @ vertex.co
        for obj in objects
        for vertex in obj.data.vertices
    ]
    low = Vector((min(p.x for p in points), min(p.y for p in points), min(p.z for p in points)))
    high = Vector((max(p.x for p in points), max(p.y for p in points), max(p.z for p in points)))
    return low, high


def main():
    args = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    if len(args) != 2:
        raise SystemExit("Expected TERRAIN.png WATER.png")
    terrain_output, water_output = map(Path, args)
    terrain_output.parent.mkdir(parents=True, exist_ok=True)
    water_output.parent.mkdir(parents=True, exist_ok=True)

    low = next(o for o in bpy.context.scene.objects if o.get("Object type") == "TERRAIN_LOW_GREEN")
    middle = next(o for o in bpy.context.scene.objects if o.get("Object type") == "TERRAIN_MIDDLE_BROWN")
    high = next(o for o in bpy.context.scene.objects if o.get("Object type") == "TERRAIN_HIGH_GRAY")
    villages = [o for o in bpy.context.scene.objects if o.get("S04_geometry") == "residential_areas_printable"]
    packed = next(o for o in bpy.context.scene.objects if o.name == "SYS01_Water_Blue_SeparatePrint")

    assign(low, material("QA_Green", (0.25, 0.46, 0.10)))
    assign(middle, material("QA_Brown", (0.46, 0.27, 0.10)))
    assign(high, material("QA_Gray", (0.52, 0.56, 0.59)))
    for obj in villages:
        assign(obj, material("QA_Village", (0.50, 0.30, 0.12)))
    assign(packed, material("QA_Blue", (0.01, 0.32, 0.95)))

    terrain_objects = [low, middle, high, *villages]
    lo, hi = bounds(terrain_objects)
    render(terrain_output, set(terrain_objects), (lo + hi) / 2, 112)
    lo, hi = bounds([packed])
    scale = max(hi.x - lo.x, hi.y - lo.y) + 12
    render(water_output, {packed}, (lo + hi) / 2, scale)
    print(f"WATER_INSERT_PREVIEWS={terrain_output},{water_output}")


if __name__ == "__main__":
    main()
