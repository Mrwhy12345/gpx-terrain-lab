#!/usr/bin/env python3
"""Render the selected bottom artwork in the same visual system as A1-A3.

The exact manufacturing proof remains ``bottom_proof.svg``.  This script only
creates a user-facing Blender view from the same title, labels and closed logo
polygons, so visual polish never changes the production source of truth.
"""
from __future__ import annotations

import json
import math
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "07_Knowledge/tools"))
from medal_frame_spec import TARGET_DESIGN_OUTER_BOUNDS_MM, TARGET_VISIBLE_RING_WIDTH_MM


def material(name, color):
    item = bpy.data.materials.new(name)
    item.diffuse_color = (*color, 1.0)
    return item


def prism(name, points, z0, z1, mat, bevel=0.0):
    count = len(points)
    vertices = [(x, y, z0) for x, y in points] + [(x, y, z1) for x, y in points]
    faces = [tuple(range(count - 1, -1, -1)), tuple(range(count, count * 2))]
    faces += [(i, (i + 1) % count, (i + 1) % count + count, i + count) for i in range(count)]
    mesh = bpy.data.meshes.new(name + "Mesh")
    mesh.from_pydata(vertices, [], faces); mesh.materials.append(mat)
    obj = bpy.data.objects.new(name, mesh); bpy.context.collection.objects.link(obj)
    if bevel:
        mod = obj.modifiers.new("Soft printable edges", "BEVEL"); mod.width = bevel; mod.segments = 2
    return obj


def hex_points(width, height):
    return [(-width/4,-height/2),(width/4,-height/2),(width/2,0),
            (width/4,height/2),(-width/4,height/2),(-width/2,0)]


def svg_polygons(path):
    root = ET.parse(path).getroot(); result = []
    number = r"[-+]?(?:\d*\.\d+|\d+)"
    for node in root.iter():
        if node.tag.rsplit("}", 1)[-1] != "path": continue
        pairs = re.findall(rf"({number})\s+({number})", node.attrib.get("d", ""))
        points = [((float(x)-50)*0.43, (35-float(y))*0.43) for x, y in pairs]
        if len(points) >= 3: result.append(points)
    return result


def text_object(name, body, location, size, mat, align="CENTER"):
    curve = bpy.data.curves.new(name + "Curve", "FONT"); curve.body = body
    curve.align_x = align; curve.align_y = "CENTER"; curve.size = size
    curve.extrude = 0.22; curve.bevel_depth = 0.035; curve.materials.append(mat)
    font = Path("/System/Library/Fonts/Hiragino Sans GB.ttc")
    if font.exists(): curve.font = bpy.data.fonts.load(str(font))
    obj = bpy.data.objects.new(name, curve); bpy.context.collection.objects.link(obj)
    obj.location = location
    return obj


def main(job_dir: Path, output: Path):
    state = json.loads((job_dir / "review/creative_state.json").read_text(encoding="utf-8"))
    job = json.loads((job_dir / "job.json").read_text(encoding="utf-8"))
    selected = next(x for x in state["logo_candidates"] if x["id"] == state["selected_logo_id"])
    content = state["proof"]["content"]
    bpy.ops.object.select_all(action="SELECT"); bpy.ops.object.delete(use_global=False)
    grey = material("Frame grey", (0.32,0.35,0.37)); face = material("Inset face", (0.66,0.69,0.67))
    brown = material("Creative brown", (0.36,0.16,0.055))
    width, height = TARGET_DESIGN_OUTER_BOUNDS_MM
    prism("Locked medal-frame base", hex_points(width, height), 0, 3.2, grey, 1.0)
    ratio = 1 - 2 * TARGET_VISIBLE_RING_WIDTH_MM / height
    prism("Bottom inlay field", [(x*ratio,y*ratio) for x,y in hex_points(width,height)], 3.18, 3.52, face, .35)
    for index, points in enumerate(svg_polygons(job_dir / selected["source"])):
        prism(f"Logo_{index:02d}", points, 3.50, 4.15, brown, .12)
    text_object("Title", content["title"], (0, 38.5, 3.51), 4.1, brown)
    left = text_object("Date", content["date"], (-34,-31,3.51), 3.25, brown)
    left.rotation_euler[2] = math.radians(-30)
    right = text_object("Distance", content["distance"], (34,-31,3.51), 3.25, brown)
    right.rotation_euler[2] = math.radians(30)
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_WORKBENCH"; scene.render.resolution_x = 1200; scene.render.resolution_y = 900
    scene.render.resolution_percentage = 100; scene.render.film_transparent = False
    scene.display.shading.light = "STUDIO"; scene.display.shading.color_type = "MATERIAL"
    scene.display.shading.show_shadows = True; scene.display.shading.show_cavity = True
    scene.display.shading.cavity_type = "WORLD"; scene.world.color = (0.035,0.055,0.042)
    camera_data = bpy.data.cameras.new("Bottom view camera"); camera_data.type = "ORTHO"; camera_data.ortho_scale = 127
    camera = bpy.data.objects.new("Bottom view camera", camera_data); bpy.context.collection.objects.link(camera)
    camera.location = (0,0,180); camera.rotation_euler = (0,0,0); scene.camera = camera
    output.parent.mkdir(parents=True, exist_ok=True); scene.render.filepath = str(output)
    bpy.ops.wm.save_as_mainfile(filepath=str(job_dir / "work/creative/bottom_preview.blend"))
    bpy.ops.render.render(write_still=True)


if __name__ == "__main__":
    args = sys.argv[sys.argv.index("--") + 1:]
    main(Path(args[0]).resolve(), Path(args[1]).resolve())
