#!/usr/bin/env python3
"""Render an angled terrain preview with vertical exaggeration and mountain color."""

from __future__ import annotations

import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector


def material(name: str, color: tuple[float, float, float]):
    result = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    result.diffuse_color = (*color, 1.0)
    return result


def assign_single(obj, mat) -> None:
    if not hasattr(obj.data, "materials"):
        return
    obj.data.materials.clear()
    obj.data.materials.append(mat)


def look_at(obj, point: Vector) -> None:
    obj.rotation_euler = (point - obj.location).to_track_quat("-Z", "Y").to_euler()


def main() -> None:
    args = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    if len(args) != 3:
        raise SystemExit(
            "Usage: blender FILE.blend --python script.py -- "
            "OUTPUT.png VERTICAL_FACTOR MOUNTAIN_THRESHOLD_FRACTION"
        )
    output = Path(args[0])
    factor = float(args[1])
    threshold_fraction = float(args[2])
    output.parent.mkdir(parents=True, exist_ok=True)

    terrain = next(
        obj for obj in bpy.context.scene.objects if obj.get("Object type") == "MAP"
    )
    relevant = [
        obj
        for obj in bpy.context.scene.objects
        if obj.type == "MESH"
        and (
            obj == terrain
            or obj.get("Object type") in {"TRAIL", "TRAIL_INSERT"}
            or obj.get("S02_geometry") in {"stream_ribbon", "water_area"}
            or obj.get("S03_geometry") == "roads_printable"
            or obj.get("S04_geometry") == "residential_areas_printable"
            or obj.get("S05_geometry") in {"display_base", "display_title"}
        )
    ]
    for obj in relevant:
        for vertex in obj.data.vertices:
            vertex.co.z *= factor

    lowland = material("STYLE_Lowland", (0.43, 0.55, 0.12))
    mountain = material("STYLE_Mountain", (0.46, 0.49, 0.52))
    trail = material("STYLE_Trail", (0.92, 0.025, 0.015))
    water = material("STYLE_Water", (0.01, 0.32, 0.95))
    road = material("STYLE_Road", (0.035, 0.04, 0.05))
    village = material("STYLE_Village", (0.88, 0.68, 0.38))

    terrain.data.materials.clear()
    terrain.data.materials.append(lowland)
    terrain.data.materials.append(mountain)
    z_values = [vertex.co.z for vertex in terrain.data.vertices]
    z_min, z_max = min(z_values), max(z_values)
    threshold = z_min + (z_max - z_min) * threshold_fraction
    for polygon in terrain.data.polygons:
        average_z = sum(terrain.data.vertices[i].co.z for i in polygon.vertices) / len(
            polygon.vertices
        )
        polygon.material_index = 1 if average_z >= threshold else 0

    for obj in relevant:
        if obj == terrain:
            continue
        if obj.get("Object type") in {"TRAIL", "TRAIL_INSERT"}:
            assign_single(obj, trail)
        elif obj.get("S02_geometry") in {"stream_ribbon", "water_area"}:
            assign_single(obj, water)
        elif obj.get("S03_geometry") == "roads_printable":
            assign_single(obj, road)
        elif obj.get("S04_geometry") == "residential_areas_printable":
            assign_single(obj, village)
        elif obj.get("S05_geometry") == "display_base":
            assign_single(obj, road)
        elif obj.get("S05_geometry") == "display_title":
            assign_single(obj, village)

    center = terrain.matrix_world @ Vector((0, 0, terrain.dimensions.z * 0.35))
    camera_data = bpy.data.cameras.new("Style_Camera")
    camera = bpy.data.objects.new("Style_Camera", camera_data)
    bpy.context.scene.collection.objects.link(camera)
    camera.location = center + Vector((72, -92, 72))
    look_at(camera, center)
    camera_data.type = "ORTHO"
    camera_data.ortho_scale = 142 if any(
        obj.get("S05_geometry") == "display_base" for obj in relevant
    ) else 126
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
        f"STYLE_PREVIEW={output} factor={factor} threshold_fraction="
        f"{threshold_fraction} threshold_z={threshold:.3f}"
    )


if __name__ == "__main__":
    main()
