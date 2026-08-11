#!/usr/bin/env python3
"""Repair tiny boundary holes exposed by STL import/export round-trips."""

from __future__ import annotations

import sys
from pathlib import Path

import bmesh
import bpy


def main():
    args = sys.argv[sys.argv.index("--") + 1 :]
    if len(args) != 2:
        raise SystemExit("Expected INPUT.stl OUTPUT.stl")
    source, destination = map(Path, args)
    bpy.ops.wm.stl_import(filepath=str(source))
    obj = bpy.context.object
    mesh = bmesh.new()
    mesh.from_mesh(obj.data)
    bmesh.ops.remove_doubles(mesh, verts=mesh.verts, dist=1e-6)
    bmesh.ops.dissolve_degenerate(mesh, edges=mesh.edges, dist=1e-6)
    multi_face_edges = [edge for edge in mesh.edges if len(edge.link_faces) > 2]
    if multi_face_edges:
        damaged_faces = {
            face for edge in multi_face_edges for face in edge.link_faces
        }
        bmesh.ops.delete(mesh, geom=list(damaged_faces), context="FACES")
    boundary = [edge for edge in mesh.edges if edge.is_boundary]
    if boundary:
        # Tiny triangular holes can be removed again by STL import as
        # degenerate faces. Expand the repair region by one face ring, then
        # fill the larger, numerically stable boundary.
        boundary_vertices = {vertex for edge in boundary for vertex in edge.verts}
        nearby_faces = {
            face for vertex in boundary_vertices for face in vertex.link_faces
        }
        if nearby_faces:
            bmesh.ops.delete(mesh, geom=list(nearby_faces), context="FACES")
        boundary = [edge for edge in mesh.edges if edge.is_boundary]
        bmesh.ops.holes_fill(mesh, edges=boundary, sides=0)
    bmesh.ops.recalc_face_normals(mesh, faces=mesh.faces)
    mesh.to_mesh(obj.data)
    mesh.free()
    obj.data.update()
    destination.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.wm.stl_export(
        filepath=str(destination), export_selected_objects=True, ascii_format=False
    )
    print(destination)


if __name__ == "__main__":
    main()
