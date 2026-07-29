#!/usr/bin/env python3
"""Render a clean three-elevation-band terrain preview without road geometry."""

from __future__ import annotations

import sys
from pathlib import Path

import bpy
from mathutils import Vector


def material(name, color):
    result = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    result.diffuse_color = (*color, 1.0)
    return result


def assign_single(obj, mat):
    obj.data.materials.clear()
    obj.data.materials.append(mat)


def look_at(obj, point):
    obj.rotation_euler = (point - obj.location).to_track_quat("-Z", "Y").to_euler()


def main():
    args = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    if len(args) != 4:
        raise SystemExit(
            "Usage: blender FILE.blend --python script.py -- "
            "OUTPUT.png VERTICAL_FACTOR BROWN_START GRAY_START"
        )
    output = Path(args[0])
    factor = float(args[1])
    brown_fraction = float(args[2])
    gray_fraction = float(args[3])
    output.parent.mkdir(parents=True, exist_ok=True)
    if not 0 < brown_fraction < gray_fraction < 1:
        raise ValueError("Expected 0 < BROWN_START < GRAY_START < 1")

    terrain = next(
        obj for obj in bpy.context.scene.objects if obj.get("Object type") == "MAP"
    )
    roads = [
        obj
        for obj in bpy.context.scene.objects
        if obj.get("S03_geometry") == "roads_printable"
    ]
    for road in roads:
        road.hide_render = True
        road.hide_set(True)

    vertically_scaled = [
        obj
        for obj in bpy.context.scene.objects
        if obj.type == "MESH"
        and (
            obj == terrain
            or obj.get("Object type") in {"TRAIL", "TRAIL_INSERT"}
            or obj.get("S02_geometry") in {"stream_ribbon", "water_area"}
            or obj.get("S04_geometry") == "residential_areas_printable"
        )
    ]
    for obj in vertically_scaled:
        for vertex in obj.data.vertices:
            vertex.co.z *= factor

    green = material("STYLE3_Lowland_Green", (0.28, 0.43, 0.10))
    brown = material("STYLE3_Midland_Brown", (0.43, 0.26, 0.10))
    gray = material("STYLE3_Highland_Gray", (0.47, 0.51, 0.54))
    red = material("STYLE3_Trail_Red", (0.92, 0.025, 0.015))
    blue = material("STYLE3_Water_Blue", (0.01, 0.35, 0.95))
    village = material("STYLE3_Village_Warm", (0.82, 0.60, 0.28))
    dark = material("STYLE3_Base_Dark", (0.025, 0.03, 0.04))
    title = material("STYLE3_Title_Warm", (0.88, 0.68, 0.38))

    terrain.data.materials.clear()
    terrain.data.materials.append(green)
    terrain.data.materials.append(brown)
    terrain.data.materials.append(gray)
    z_values = [vertex.co.z for vertex in terrain.data.vertices]
    z_min, z_max = min(z_values), max(z_values)
    brown_z = z_min + (z_max - z_min) * brown_fraction
    gray_z = z_min + (z_max - z_min) * gray_fraction
    for polygon in terrain.data.polygons:
        average_z = sum(terrain.data.vertices[i].co.z for i in polygon.vertices) / len(
            polygon.vertices
        )
        polygon.material_index = 2 if average_z >= gray_z else (
            1 if average_z >= brown_z else 0
        )

    for obj in bpy.context.scene.objects:
        if obj.type != "MESH" or obj == terrain:
            continue
        if obj.get("Object type") in {"TRAIL", "TRAIL_INSERT"}:
            assign_single(obj, red)
        elif obj.get("S02_geometry") in {"stream_ribbon", "water_area"}:
            assign_single(obj, blue)
        elif obj.get("S04_geometry") == "residential_areas_printable":
            assign_single(obj, village)
        elif obj.get("S05_geometry") == "display_base":
            assign_single(obj, dark)
        elif obj.get("S05_geometry") == "display_title":
            assign_single(obj, title)

    center = terrain.matrix_world @ Vector((0, 0, terrain.dimensions.z * 0.38))
    camera_data = bpy.data.cameras.new("ThreeBand_Camera")
    camera = bpy.data.objects.new("ThreeBand_Camera", camera_data)
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
    print(
        f"THREE_BAND_PREVIEW={output} factor={factor} "
        f"brown={brown_fraction}/{brown_z:.3f} gray={gray_fraction}/{gray_z:.3f}"
    )


if __name__ == "__main__":
    main()
