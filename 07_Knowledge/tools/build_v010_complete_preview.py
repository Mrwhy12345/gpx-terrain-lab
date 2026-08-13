#!/usr/bin/env python3
"""Replace V007 terrain/water with the V010 selected-water geometry."""

from __future__ import annotations

import sys
from pathlib import Path

import bpy
from mathutils import Vector


def material(name, fallback):
    existing = bpy.data.materials.get(name)
    if existing:
        existing.diffuse_color = (*fallback, 1.0)
        return existing
    result = bpy.data.materials.new(name)
    result.diffuse_color = (*fallback, 1.0)
    return result


def main():
    args = sys.argv[sys.argv.index("--") + 1 :]
    if len(args) != 4:
        raise SystemExit("Expected PARTS_DIR OUTPUT.blend TOP.png UNDERSIDE.png")
    parts_dir, output, top_preview, underside_preview = map(Path, args)

    for obj in list(bpy.context.scene.objects):
        if (
            obj.get("Object type")
            in {"TERRAIN_LOW_GREEN", "TERRAIN_MIDDLE_BROWN", "TERRAIN_HIGH_GRAY"}
            or obj.get("S02_geometry") in {"stream_ribbon", "water_area"}
            or obj.name == "SYS01_Water_Blue_SeparatePrint"
        ):
            bpy.data.objects.remove(obj, do_unlink=True)

    specs = (
        ("01_Terrain_Low_Green_Grooved.stl", "V010_沙盘低层_绿色", "TERRAIN_LOW_GREEN", material("Terrain_Low_Green", (0.18, 0.52, 0.12))),
        ("02_Terrain_And_Villages_Brown_Grooved.stl", "V010_沙盘中层与村落_棕色", "TERRAIN_MIDDLE_BROWN", material("Terrain_Middle_Brown", (0.45, 0.27, 0.10))),
        ("03_Terrain_High_Gray_Grooved.stl", "V010_沙盘高层_灰色", "TERRAIN_HIGH_GRAY", material("Terrain_High_Gray", (0.52, 0.56, 0.58))),
        ("04_Water_Blue_Aligned_Reference.stl", "V010_溯溪精选五件_蓝色", None, material("Water_Blue", (0.02, 0.32, 0.82))),
    )
    for filename, name, object_type, mat in specs:
        bpy.ops.wm.stl_import(filepath=str(parts_dir / filename))
        obj = bpy.context.object
        obj.name = name
        if object_type:
            obj["Object type"] = object_type
        else:
            obj["SYS01_geometry"] = "selected_water_five_parts"
        obj.data.materials.clear()
        obj.data.materials.append(mat)
        for polygon in obj.data.polygons:
            polygon.material_index = 0

    trail = next(
        (
            obj
            for obj in bpy.context.scene.objects
            if (
                obj.get("S03_geometry") == "trail_insert"
                or obj.get("S02_geometry") == "trail_ribbon"
                or "trail" in obj.name.lower()
                or "轨迹" in obj.name
            )
        ),
        None,
    )
    if trail:
        for collection in list(trail.users_collection):
            collection.objects.unlink(trail)
        scene_root = bpy.context.scene.collection
        scene_root.objects.link(trail)
        trail.hide_set(False)
        trail.hide_viewport = False
        trail.hide_render = False
        trail.data.materials.clear()
        trail.data.materials.append(material("Trail_Red", (0.82, 0.025, 0.035)))
        for polygon in trail.data.polygons:
            polygon.material_index = 0

    scene = bpy.context.scene
    scene["版本"] = "SYS01_V010"
    scene["水体策略"] = "保留五个最大水系组件，无人工连接桥，顶部安装"
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.light = "STUDIO"
    scene.display.shading.color_type = "MATERIAL"
    scene.display.shading.show_cavity = True
    scene.render.resolution_x = 1200
    scene.render.resolution_y = 1000
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"

    camera = scene.camera
    if camera is None:
        bpy.ops.object.camera_add()
        camera = bpy.context.object
        scene.camera = camera
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = 125
    for location, target in (
        ((0, -120, 150), top_preview),
        ((0, -120, -115), underside_preview),
    ):
        camera.location = location
        direction = Vector((0, 0, 4)) - camera.location
        camera.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
        scene.render.filepath = str(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        bpy.ops.render.render(write_still=True)

    output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(output))
    print(output)


if __name__ == "__main__":
    main()
