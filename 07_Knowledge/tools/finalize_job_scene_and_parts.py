#!/usr/bin/env python3
"""Normalize a generated job scene and export aligned/printable trail parts."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import bpy


def bounds(obj):
    points = [obj.matrix_world @ vertex.co for vertex in obj.data.vertices]
    return {axis: [min(p[i] for p in points), max(p[i] for p in points)]
            for i, axis in enumerate(("x", "y", "z"))}


def export(path, objects):
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    bpy.ops.wm.stl_export(
        filepath=str(path), export_selected_objects=True, ascii_format=False
    )


def main():
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if len(args) not in {4, 5}:
        raise SystemExit("Expected OUTPUT.blend ALIGNED_TRAIL.stl PRINT_TRAIL.stl REPORT.json [BANDS.json]")
    output, aligned_stl, print_stl, report_path = map(Path, args[:4])
    low = next(o for o in bpy.context.scene.objects
               if o.get("Object type") == "TERRAIN_LOW_GREEN")
    trail = next(o for o in bpy.context.scene.objects
                 if o.get("S03_geometry") == "trail_insert")
    low_bounds = bounds(low)
    trail_before = bounds(trail)
    # Water-groove generation centers terrain and water by moving their object
    # origins. Apply that exact translation to the trail if it still carries
    # GIS-scale coordinates.
    if abs(sum(trail_before["x"]) / 2) > 10000:
        source_center = None
        if len(args) == 5:
            band_report = json.loads(Path(args[4]).read_text(encoding="utf-8"))
            source_bounds = band_report["bands"][0]["bounds"]
            source_center = (
                sum(source_bounds["x"]) / 2,
                sum(source_bounds["y"]) / 2,
            )
        source_center = source_center or (
            sum(trail_before["x"]) / 2,
            sum(trail_before["y"]) / 2,
        )
        trail.location.x -= source_center[0]
        trail.location.y -= source_center[1]
        bpy.context.view_layer.update()
    trail_after = bounds(trail)
    export(aligned_stl, [trail])

    printable = trail.copy()
    printable.data = trail.data.copy()
    printable.name = "Trail_Red_SeparatePrint"
    bpy.context.scene.collection.objects.link(printable)
    printable.location.z -= bounds(printable)["z"][0]
    export(print_stl, [printable])
    printable.hide_viewport = True
    printable.hide_render = True

    for obj in bpy.context.scene.objects:
        if obj.get("SYS01_geometry") == "water_insert":
            obj.hide_render = False
        if obj.name == "SYS01_Water_Blue_SeparatePrint":
            obj.hide_viewport = True
            obj.hide_render = True

    report = {
        "trail_bounds_before": trail_before,
        "trail_bounds_aligned": trail_after,
        "terrain_bounds": low_bounds,
        "aligned_export": str(aligned_stl),
        "separate_print_export": str(print_stl),
        "z_axis_check": {
            "aligned_min_z_nonnegative": trail_after["z"][0] >= -1e-5,
            "print_min_z": bounds(printable)["z"][0],
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(output))
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("FINALIZE_JOB=" + json.dumps(report))


if __name__ == "__main__":
    main()
