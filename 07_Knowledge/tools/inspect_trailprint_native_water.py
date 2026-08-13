#!/usr/bin/env python3
"""Report TrailPrint3D-native water objects after generation."""

import json
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector


def main():
    args = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    if len(args) != 1:
        raise SystemExit("Expected REPORT.json")
    report_path = Path(args[0])
    objects = []
    for obj in bpy.context.scene.objects:
        if obj.type != "MESH" or not obj.data.vertices:
            continue
        marker = " ".join(
            str(value) for value in (
                obj.name,
                obj.get("Object type", ""),
                obj.get("Element type", ""),
            )
        ).upper()
        if "WATER" not in marker and "OCEAN" not in marker:
            continue
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
        objects.append({
            "name": obj.name,
            "object_type": obj.get("Object type"),
            "element_type": obj.get("Element type"),
            "vertices": len(bm.verts),
            "faces": len(bm.faces),
            "non_manifold_edges": sum(not edge.is_manifold for edge in bm.edges),
            "bounds": {
                "x": [min(p.x for p in corners), max(p.x for p in corners)],
                "y": [min(p.y for p in corners), max(p.y for p in corners)],
                "z": [min(p.z for p in corners), max(p.z for p in corners)],
            },
        })
        bm.free()
    result = {"blend": bpy.data.filepath, "water_object_count": len(objects), "objects": objects}
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("NATIVE_WATER=" + json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
