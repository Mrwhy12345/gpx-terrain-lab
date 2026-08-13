#!/usr/bin/env python3
"""Export aligned and Z-normalized trail STLs from the endpoint-relief blend."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import bpy


def bounds(obj):
    points = [obj.matrix_world @ vertex.co for vertex in obj.data.vertices]
    return (
        min(p.x for p in points), max(p.x for p in points),
        min(p.y for p in points), max(p.y for p in points),
        min(p.z for p in points), max(p.z for p in points),
    )


def export(obj, path):
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    path.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.stl_export(filepath=str(path), export_selected_objects=True)


def main():
    args = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    if len(args) != 2:
        raise SystemExit("Expected OUTPUT_DIR REPORT.json")
    output_dir, report_path = map(Path, args)
    trail = next(
        obj for obj in bpy.context.scene.objects
        if obj.get("S03_geometry") == "trail_insert"
    )
    aligned_path = output_dir / "01_Trail_Red_Aligned_StartArrow_FinishTarget.stl"
    export(trail, aligned_path)

    standalone = trail.copy()
    standalone.data = trail.data.copy()
    bpy.context.scene.collection.objects.link(standalone)
    min_x, max_x, min_y, max_y, min_z, _ = bounds(standalone)
    standalone.location.x -= (min_x + max_x) / 2
    standalone.location.y -= (min_y + max_y) / 2
    standalone.location.z -= min_z
    separate_path = output_dir / "02_Trail_Red_SeparatePrint_StartArrow_FinishTarget.stl"
    export(standalone, separate_path)

    result = {
        "source_blend": bpy.data.filepath,
        "aligned": str(aligned_path),
        "separate_print": str(separate_path),
        "separate_bounds": bounds(standalone),
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("TRAIL_RELIEF_EXPORT=" + json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
