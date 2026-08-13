#!/usr/bin/env python3
"""Apply the GPX Terrain Lab green/red/blue palette to a derived native-water blend."""

import sys
from pathlib import Path

import bpy


def material(name, hex_color):
    value = hex_color.lstrip("#")
    rgb = tuple(int(value[index:index + 2], 16) / 255 for index in (0, 2, 4))
    result = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    result.diffuse_color = (*rgb, 1.0)
    return result


def assign(obj, mat):
    obj.data.materials.clear()
    obj.data.materials.append(mat)


def main():
    args = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    if len(args) != 1:
        raise SystemExit("Expected OUTPUT.blend")
    output = Path(args[0])
    green = material("Terrain_Low_Green", "#3F8E43")
    red = material("Trail_Red", "#D93025")
    blue = material("Water_Blue", "#2563B8")
    for obj in bpy.context.scene.objects:
        if obj.type != "MESH":
            continue
        object_type = obj.get("Object type")
        if object_type == "MAP":
            assign(obj, green)
        elif object_type in {"TRAIL", "TRAIL_INSERT"}:
            assign(obj, red)
        elif object_type in {"WATER", "OCEAN"}:
            assign(obj, blue)
    bpy.context.scene["palette"] = {
        "terrain": "#3F8E43", "trail": "#D93025", "water": "#2563B8"
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(output))
    print(f"PALETTE_BLEND={output}")


if __name__ == "__main__":
    main()
