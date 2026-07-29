#!/usr/bin/env python3
"""Create the clean V006 one-plate Blender design preview."""

import bpy
import math
import sys
from pathlib import Path
from mathutils import Vector


def args_after_separator():
    return sys.argv[sys.argv.index("--") + 1 :]


raw_args = args_after_separator()
source_dir, blend_path, render_path = map(Path, raw_args[:3])
version = raw_args[3] if len(raw_args) > 3 else "SYS01_V006"

bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)
for collection in list(bpy.data.collections):
    if collection.name != "Collection":
        bpy.data.collections.remove(collection)

root = bpy.context.scene.collection
default_collection = bpy.data.collections.get("Collection")
if default_collection:
    root.children.unlink(default_collection)
    bpy.data.collections.remove(default_collection)

collections = {}
for name in ("01_沙盘地形", "02_底座", "03_徒步轨迹", "04_河流水体", "辅助_打印盘"):
    collection = bpy.data.collections.new(name)
    root.children.link(collection)
    collections[name] = collection


def material(name, rgba, metallic=0.0, roughness=0.55):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (*rgba, 1.0)
    mat.use_nodes = True
    principled = mat.node_tree.nodes.get("Principled BSDF")
    principled.inputs["Base Color"].default_value = (*rgba, 1.0)
    principled.inputs["Roughness"].default_value = roughness
    principled.inputs["Metallic"].default_value = metallic
    return mat


mats = {
    "green": material("绿色_竹林地形", (0.10, 0.62, 0.14)),
    "brown": material("棕色_土壤与Logo", (0.46, 0.18, 0.045)),
    "gray": material("灰色_山体与底座", (0.55, 0.61, 0.66)),
    "red": material("红色_徒步轨迹", (0.84, 0.035, 0.05), roughness=0.42),
    "blue": material("蓝色_河流水体", (0.025, 0.35, 0.90), roughness=0.35),
    "plate": material("打印盘_深灰", (0.18, 0.22, 0.26), metallic=0.1, roughness=0.65),
}

specs = [
    ("01_Terrain_Low_Green.stl", "01_沙盘_低层绿色", "green", "01_沙盘地形"),
    ("02_Terrain_Middle_Brown.stl", "01_沙盘_中层棕色", "brown", "01_沙盘地形"),
    ("03_Terrain_High_Gray.stl", "01_沙盘_高层灰色", "gray", "01_沙盘地形"),
    ("04_Base_Gray.stl", "02_底座_灰色主体", "gray", "02_底座"),
    ("05_Base_Labels_Logo_Brown.stl", "02_底座_棕色文字与竹林Logo", "brown", "02_底座"),
    ("06_Trail_Red.stl", "03_徒步轨迹_红色安装件", "red", "03_徒步轨迹"),
    ("07_Water_Blue.stl", "04_河流水体_蓝色一体跨轨安装件", "blue", "04_河流水体"),
]

for filename, object_name, mat_name, collection_name in specs:
    bpy.ops.wm.stl_import(filepath=str(source_dir / filename))
    obj = bpy.context.object
    obj.name = object_name
    for owner in list(obj.users_collection):
        owner.objects.unlink(obj)
    collections[collection_name].objects.link(obj)
    obj.data.materials.clear()
    obj.data.materials.append(mats[mat_name])

# H2C plate is shown as a non-printing design aid.
bpy.ops.mesh.primitive_cube_add(location=(0, 0, -1.6), scale=(165, 160, 1.5))
plate = bpy.context.object
plate.name = "辅助_H2C打印盘_330x320mm_不导出"
for owner in list(plate.users_collection):
    owner.objects.unlink(plate)
collections["辅助_打印盘"].objects.link(plate)
plate.data.materials.append(mats["plate"])
plate.display_type = "SOLID"
plate["export_for_print"] = False

# Camera aimed at the center of the four-piece layout.
bpy.ops.object.camera_add(location=(250, -285, 315))
camera = bpy.context.object
camera.name = "相机_四件同盘总览"
root.objects.link(camera) if not camera.users_collection else None
direction = Vector((0, 10, 0)) - camera.location
camera.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
camera.data.type = "ORTHO"
camera.data.ortho_scale = 405
bpy.context.scene.camera = camera

bpy.ops.object.light_add(type="AREA", location=(40, -20, 330))
key = bpy.context.object
key.name = "主光"
key.data.energy = 3500
key.data.shape = "DISK"
key.data.size = 240
bpy.ops.object.light_add(type="AREA", location=(-220, 120, 160))
fill = bpy.context.object
fill.name = "补光"
fill.data.energy = 2200
fill.data.size = 180
fill.rotation_euler = (math.radians(35), 0, math.radians(-120))

scene = bpy.context.scene
scene.render.engine = "BLENDER_EEVEE"
scene.render.resolution_x = 1400
scene.render.resolution_y = 1000
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.render.filepath = str(render_path)
scene.world.use_nodes = True
scene.world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.055, 0.065, 0.08, 1.0)
scene.world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.45
scene.view_settings.look = "AgX - Medium High Contrast"
scene.view_settings.exposure = 2.5
scene.render.film_transparent = False
scene["版本"] = version
scene["用途"] = "第五个3MF对应的四件同盘设计预览"
scene["打印策略"] = "按层打印"
scene["可见颜色"] = "绿、棕、灰、红、蓝"

blend_path.parent.mkdir(parents=True, exist_ok=True)
render_path.parent.mkdir(parents=True, exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
bpy.ops.render.render(write_still=True)
print(blend_path)
print(render_path)
