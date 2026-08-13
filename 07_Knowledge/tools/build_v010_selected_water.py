#!/usr/bin/env python3
"""Keep the five largest meaningful water components, then build clean grooves."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import bmesh
import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_water_inserts_and_grooves as builder


MAX_WATER_COMPONENTS = 5


def clean_mesh(obj):
    mesh = bmesh.new()
    mesh.from_mesh(obj.data)
    bmesh.ops.remove_doubles(mesh, verts=mesh.verts, dist=1e-6)
    bmesh.ops.dissolve_degenerate(mesh, edges=mesh.edges, dist=1e-6)
    bmesh.ops.recalc_face_normals(mesh, faces=mesh.faces)
    mesh.to_mesh(obj.data)
    mesh.free()
    obj.data.update()


def separate_loose_parts(obj):
    before = set(bpy.context.scene.objects)
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.separate(type="LOOSE")
    bpy.ops.object.mode_set(mode="OBJECT")
    created = list(set(bpy.context.scene.objects) - before)
    parts = [obj, *created]
    source_name = obj.name.split(".")[0]
    source_osm = obj.get("OSM_ID")
    source_geometry = obj.get("S02_geometry")
    for index, part in enumerate(parts, start=1):
        part.name = f"{source_name}_V010_Part_{index:02d}"
        part["V010_source_name"] = source_name
        part["OSM_ID"] = source_osm
        part["S02_geometry"] = source_geometry
    return parts


def main():
    args = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    if len(args) != 3:
        raise SystemExit("Expected OUTPUT.blend OUTPUT_DIR REPORT.json")
    report_path = Path(args[2])

    waters = [
        obj
        for obj in list(bpy.context.scene.objects)
        if obj.get("S02_geometry") in {"stream_ribbon", "water_area"}
    ]
    pieces = []
    for water in waters:
        pieces.extend(separate_loose_parts(water))
    ranked = sorted(pieces, key=lambda obj: len(obj.data.vertices), reverse=True)
    kept = ranked[:MAX_WATER_COMPONENTS]
    excluded = ranked[MAX_WATER_COMPONENTS:]
    selection = {
        "strategy": "five largest loose water components; no artificial connectors",
        "maximum_installation_components": MAX_WATER_COMPONENTS,
        "kept": [
            {
                "name": obj.name,
                "source": obj.get("V010_source_name"),
                "osm_id": obj.get("OSM_ID"),
                "vertices": len(obj.data.vertices),
            }
            for obj in kept
        ],
        "excluded": [
            {
                "name": obj.name,
                "source": obj.get("V010_source_name"),
                "osm_id": obj.get("OSM_ID"),
                "vertices": len(obj.data.vertices),
            }
            for obj in excluded
        ],
        "retained_vertex_ratio": sum(len(obj.data.vertices) for obj in kept)
        / sum(len(obj.data.vertices) for obj in ranked),
    }
    for obj in excluded:
        bpy.data.objects.remove(obj, do_unlink=True)
    for obj in kept:
        clean_mesh(obj)

    builder.REPAIR_AFTER_FLATTEN = True
    builder.main()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["V010_selection"] = selection
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print("V010_SELECTION=" + json.dumps(selection, ensure_ascii=False))


if __name__ == "__main__":
    main()
