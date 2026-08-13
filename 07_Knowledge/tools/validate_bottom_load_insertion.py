#!/usr/bin/env python3
"""Sample the complete +Z insertion path of a bottom-loaded water insert."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree


def world_bmesh(objects, relative_z=0.0):
    mesh = bmesh.new()
    for obj in objects:
        source = bmesh.new()
        source.from_mesh(obj.data)
        transform = Matrix.Translation(Vector((0, 0, relative_z))) @ obj.matrix_world
        source.transform(transform)
        source.to_mesh(temp := bpy.data.meshes.new("V009_QA_Temp"))
        mesh.from_mesh(temp)
        bpy.data.meshes.remove(temp)
        source.free()
    return mesh


def bounds_z(obj):
    values = [(obj.matrix_world @ vertex.co).z for vertex in obj.data.vertices]
    return min(values), max(values)


def main():
    args = sys.argv[sys.argv.index("--") + 1 :]
    if len(args) != 2:
        raise SystemExit("Expected OUTPUT.json STEP_MM")
    output = Path(args[0])
    step = float(args[1])

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
    water_mesh = world_bmesh([water])
    water_bvh = BVHTree.FromBMesh(water_mesh, epsilon=0.0)
    _water_min, water_max = bounds_z(water)
    start = -(water_max + step)
    offsets = []
    current = start
    while current < -1e-8:
        offsets.append(current)
        current += step
    offsets.append(0.0)

    samples = []
    for offset in offsets:
        # Moving water by offset against fixed terrain is equivalent to keeping
        # water fixed and moving terrain by the inverse offset.
        terrain_mesh = world_bmesh(terrain, relative_z=-offset)
        terrain_bvh = BVHTree.FromBMesh(terrain_mesh, epsilon=0.0)
        overlaps = water_bvh.overlap(terrain_bvh)
        samples.append(
            {
                "water_z_offset_mm": round(offset, 4),
                "triangle_overlap_pairs": len(overlaps),
                "collision_free": len(overlaps) == 0,
            }
        )
        terrain_mesh.free()

    water_mesh.free()
    failed = [sample for sample in samples if not sample["collision_free"]]
    report = {
        "method": "BVH triangle-overlap sampling of complete +Z insertion path",
        "step_mm": step,
        "start_offset_mm": round(start, 4),
        "final_offset_mm": 0.0,
        "samples": len(samples),
        "collision_samples": len(failed),
        "pass": not failed,
        "first_collision": failed[0] if failed else None,
        "last_collision": failed[-1] if failed else None,
        "details": samples,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print("V009_INSERTION_QA=" + json.dumps({k: v for k, v in report.items() if k != "details"}))
    if failed:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
