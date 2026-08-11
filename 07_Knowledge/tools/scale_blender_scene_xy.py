#!/usr/bin/env python3
"""Scale centered delivery meshes uniformly in XY while preserving every Z value."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import bpy
from mathutils import Vector


def world_bounds(obj):
    points = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    return [[min(p[i] for p in points), max(p[i] for p in points)] for i in range(3)]


def combined_bounds(objects):
    boxes = [world_bounds(obj) for obj in objects]
    return {
        axis: [min(box[i][0] for box in boxes), max(box[i][1] for box in boxes)]
        for i, axis in enumerate(("x", "y", "z"))
    }


def main():
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if len(args) != 3:
        raise SystemExit("Expected XY_SCALE OUTPUT.blend REPORT.json")
    factor = float(args[0])
    output = Path(args[1])
    report_path = Path(args[2])
    meshes = []
    skipped = []
    for obj in bpy.context.scene.objects:
        if obj.type != "MESH" or not obj.data.vertices:
            continue
        box = world_bounds(obj)
        center = [(axis[0] + axis[1]) / 2 for axis in box]
        if abs(center[0]) > 500 or abs(center[1]) > 500:
            skipped.append(obj.name)
            continue
        meshes.append(obj)
    if not meshes:
        raise RuntimeError("No centered meshes found")
    before = combined_bounds(meshes)
    for obj in meshes:
        obj.location.x *= factor
        obj.location.y *= factor
        obj.scale.x *= factor
        obj.scale.y *= factor
    bpy.context.view_layer.update()
    after = combined_bounds(meshes)
    output.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "xy_scale": factor,
        "z_scale": 1.0,
        "scaled_meshes": [obj.name for obj in meshes],
        "skipped_outliers": skipped,
        "bounds_before": before,
        "bounds_after": after,
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    bpy.context.scene["奖牌框XY缩放"] = factor
    bpy.context.scene["Z保持不变"] = True
    bpy.ops.wm.save_as_mainfile(filepath=str(output))
    print("XY_SCALE=" + json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
