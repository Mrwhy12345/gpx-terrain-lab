#!/usr/bin/env python3
"""Render isolated top views of the start and finish relief symbols."""

import math
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import bpy

EARTH_RADIUS_KM = 6371.0
SCALE = 16.749693


def world(lon, lat):
    return (
        EARTH_RADIUS_KM * math.radians(lon) * SCALE,
        EARTH_RADIUS_KM * math.log(math.tan(math.pi / 4 + math.radians(lat) / 2)) * SCALE,
    )


def main():
    args = sys.argv[sys.argv.index("--") + 1 :]
    gpx, start_png, finish_png = map(Path, args)
    trail = next(o for o in bpy.context.scene.objects if o.get("S03_geometry") == "trail_insert")
    for obj in bpy.context.scene.objects:
        obj.hide_render = obj != trail and obj.type != "CAMERA"
    material = bpy.data.materials.new("Endpoint_Red")
    material.diffuse_color = (0.85, 0.02, 0.02, 1)
    trail.data.materials.clear()
    trail.data.materials.append(material)
    for polygon in trail.data.polygons:
        polygon.material_index = 0

    points = [
        (float(p.attrib["lon"]), float(p.attrib["lat"]))
        for p in ET.parse(gpx).getroot().iter()
        if p.tag.rsplit("}", 1)[-1] in {"trkpt", "rtept"}
    ]
    camera = bpy.context.scene.camera
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = 6.0
    camera.rotation_euler = (0, 0, 0)
    camera.rotation_euler[0] = 0
    camera.rotation_euler = (0.0, 0.0, 0.0)
    # Cameras look down their local -Z axis.
    camera.rotation_euler = (0, 0, 0)
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.color_type = "MATERIAL"
    scene.display.shading.light = "STUDIO"
    scene.render.resolution_x = 700
    scene.render.resolution_y = 700
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    max_z = max((trail.matrix_world @ v.co).z for v in trail.data.vertices)
    for xy, path in ((world(*points[0]), start_png), (world(*points[-1]), finish_png)):
        camera.location = (xy[0], xy[1], max_z + 30)
        camera.rotation_euler = (0, 0, 0)
        path.parent.mkdir(parents=True, exist_ok=True)
        scene.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)


if __name__ == "__main__":
    main()
