#!/usr/bin/env python3
"""Apply conservative Blender mesh cleanup to one STL and report topology."""

import json
import sys
from pathlib import Path

import bmesh
import bpy


def quality(mesh):
    bm = bmesh.new()
    bm.from_mesh(mesh)
    result = {
        "vertices": len(bm.verts),
        "edges": len(bm.edges),
        "faces": len(bm.faces),
        "non_manifold_edges": sum(not edge.is_manifold for edge in bm.edges),
    }
    bm.free()
    return result


def main():
    args = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    if len(args) != 3:
        raise SystemExit("Expected INPUT.stl OUTPUT.stl REPORT.json")
    source, output, report = map(Path, args)
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    bpy.ops.wm.stl_import(filepath=str(source))
    obj = bpy.context.object
    before = quality(obj.data)
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.0001)
    bmesh.ops.dissolve_degenerate(bm, edges=bm.edges, dist=0.0001)
    # STL joins occasionally leave one edge shared by three coplanar faces.
    # Remove only surplus faces at such edges, then close the resulting hole.
    surplus_faces = set()
    for edge in bm.edges:
        if len(edge.link_faces) > 2:
            ordered = sorted(edge.link_faces, key=lambda face: face.calc_area())
            surplus_faces.update(ordered[: len(edge.link_faces) - 2])
    if surplus_faces:
        bmesh.ops.delete(bm, geom=list(surplus_faces), context="FACES")
    boundary = [edge for edge in bm.edges if edge.is_boundary]
    if boundary:
        bmesh.ops.holes_fill(bm, edges=boundary, sides=0)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.validate(clean_customdata=False)
    obj.data.update()
    after = quality(obj.data)
    output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.wm.stl_export(
        filepath=str(output), export_selected_objects=True, ascii_format=False
    )
    result = {"source": str(source), "output": str(output), "before": before, "after": after}
    report.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print("REPAIR_STL=" + json.dumps(result))


if __name__ == "__main__":
    main()
