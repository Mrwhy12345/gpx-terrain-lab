#!/usr/bin/env python3
"""Measure true intersection volume at selected bottom-load positions."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import bmesh
import bpy


def mesh_volume(obj):
    if not obj.data.polygons:
        return 0.0
    mesh = bmesh.new()
    mesh.from_mesh(obj.data)
    volume = abs(mesh.calc_volume(signed=True))
    mesh.free()
    return volume


def main():
    args = sys.argv[sys.argv.index("--") + 1 :]
    output = Path(args[0])
    offsets = [float(value) for value in args[1:]]
    water = next(
        obj
        for obj in bpy.context.scene.objects
        if obj.get("SYS01_geometry") == "unified_water_underpass"
    )
    terrain = [
        obj
        for obj in bpy.context.scene.objects
        if obj.get("Object type")
        in {"TERRAIN_LOW_GREEN", "TERRAIN_MIDDLE_BROWN", "TERRAIN_HIGH_GRAY"}
    ]
    results = []
    for offset in offsets:
        total = 0.0
        layers = []
        for target in terrain:
            probe = water.copy()
            probe.data = water.data.copy()
            bpy.context.scene.collection.objects.link(probe)
            probe.location.z += offset
            modifier = probe.modifiers.new("V009_Intersection", "BOOLEAN")
            modifier.operation = "INTERSECT"
            modifier.solver = "EXACT"
            modifier.object = target
            bpy.context.view_layer.objects.active = probe
            probe.select_set(True)
            bpy.ops.object.modifier_apply(modifier=modifier.name)
            volume = mesh_volume(probe)
            layers.append({"terrain": target.name, "volume_mm3": volume})
            total += volume
            bpy.data.objects.remove(probe, do_unlink=True)
        results.append(
            {
                "water_z_offset_mm": offset,
                "intersection_volume_mm3": total,
                "collision_free": total < 0.001,
                "layers": layers,
            }
        )
    report = {"method": "Blender exact boolean intersection volume", "results": results}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print("V009_VOLUME_QA=" + json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
