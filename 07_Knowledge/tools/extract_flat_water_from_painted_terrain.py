#!/usr/bin/env python3
"""Convert TrailPrint3D PAINT water faces into a flat printable water solid."""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector
from shapely.geometry import Polygon
from shapely.ops import triangulate

from bl_ext.user_default.trailprint3d.utils import geometry2d
from bl_ext.user_default.trailprint3d.utils.mesh_ops import merge_objects


def quality(obj):
    mesh = bmesh.new()
    mesh.from_mesh(obj.data)
    overconnected = [edge for edge in mesh.edges if len(edge.link_faces) > 2]
    result = {
        "vertices": len(mesh.verts),
        "edges": len(mesh.edges),
        "faces": len(mesh.faces),
        "non_manifold_edges": sum(not edge.is_manifold for edge in mesh.edges),
        "boundary_edges": sum(len(edge.link_faces) == 1 for edge in mesh.edges),
        "overconnected_edges": sum(len(edge.link_faces) > 2 for edge in mesh.edges),
        "loose_edges": sum(len(edge.link_faces) == 0 for edge in mesh.edges),
        "overconnected_samples": [
            {
                "face_count": len(edge.link_faces),
                "a": [round(value, 6) for value in edge.verts[0].co],
                "b": [round(value, 6) for value in edge.verts[1].co],
            }
            for edge in overconnected[:20]
        ],
    }
    mesh.free()
    return result


def polygon_cap(name, polygon):
    """Build caps, separating triangle regions that meet only at a vertex."""
    triangle_keys = []
    key_coords = {}
    for triangle in triangulate(polygon):
        # GEOS triangulates the convex hull; discard triangles in holes/outside.
        if not polygon.covers(triangle):
            continue
        face = []
        for x, y in list(triangle.exterior.coords)[:3]:
            key = (round(float(x), 9), round(float(y), 9))
            key_coords[key] = (float(x), float(y), 0.0)
            face.append(key)
        if len(set(face)) == 3:
            triangle_keys.append(tuple(face))
    if not triangle_keys:
        return []

    # Regions sharing an edge are one surface. Regions sharing only a vertex
    # must keep duplicate vertices or extrusion creates a non-manifold spine.
    parents = list(range(len(triangle_keys)))

    def find(item):
        while parents[item] != item:
            parents[item] = parents[parents[item]]
            item = parents[item]
        return item

    def join(a, b):
        a, b = find(a), find(b)
        if a != b:
            parents[b] = a

    edge_owner = {}
    for face_index, face in enumerate(triangle_keys):
        for a, b in ((face[0], face[1]), (face[1], face[2]), (face[2], face[0])):
            edge = tuple(sorted((a, b)))
            if edge in edge_owner:
                join(face_index, edge_owner[edge])
            else:
                edge_owner[edge] = face_index
    components = {}
    for face_index, face in enumerate(triangle_keys):
        components.setdefault(find(face_index), []).append(face)

    objects = []
    for component_index, component_faces in enumerate(components.values(), start=1):
        component_faces = [list(face) for face in component_faces]
        incident = {}
        for face_index, face in enumerate(component_faces):
            for key in face:
                incident.setdefault(key, []).append(face_index)
        split_serial = 0
        for key, face_indexes in incident.items():
            if len(face_indexes) < 2:
                continue
            local_parent = {face_index: face_index for face_index in face_indexes}

            def local_find(item):
                while local_parent[item] != item:
                    local_parent[item] = local_parent[local_parent[item]]
                    item = local_parent[item]
                return item

            def local_join(a, b):
                a, b = local_find(a), local_find(b)
                if a != b:
                    local_parent[b] = a

            # Around a manifold vertex, adjacent triangles share the vertex and
            # one further vertex. Separate face fans indicate a pinch contact.
            for pos, first_index in enumerate(face_indexes):
                first = set(component_faces[first_index])
                for second_index in face_indexes[pos + 1:]:
                    if len(first.intersection(component_faces[second_index])) >= 2:
                        local_join(first_index, second_index)
            fans = {}
            for face_index in face_indexes:
                fans.setdefault(local_find(face_index), []).append(face_index)
            for fan in list(fans.values())[1:]:
                split_serial += 1
                split_key = (key[0], key[1], "split", split_serial)
                key_coords[split_key] = key_coords[key]
                for face_index in fan:
                    component_faces[face_index] = [
                        split_key if value == key else value
                        for value in component_faces[face_index]
                    ]
        vertex_ids = {}
        vertices = []
        faces = []
        for component_face in component_faces:
            face = []
            for key in component_face:
                if key not in vertex_ids:
                    vertex_ids[key] = len(vertices)
                    vertices.append(key_coords[key])
                face.append(vertex_ids[key])
            faces.append(tuple(face))
        component_name = f"{name}_{component_index:03d}"
        mesh = bpy.data.meshes.new(component_name + "_Mesh")
        mesh.from_pydata(vertices, [], faces)
        mesh.update(calc_edges=True)
        obj = bpy.data.objects.new(component_name, mesh)
        bpy.context.scene.collection.objects.link(obj)
        objects.append(obj)
    return objects


def main():
    args = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    if len(args) != 3:
        raise SystemExit("Expected OUTPUT.blend REPORT.json JOB.json")
    output_blend, report_path, job_path = map(Path, args)
    job = json.loads(job_path.read_text(encoding="utf-8"))
    engineering = job.get("engineering", {})
    terrain = next(
        obj for obj in bpy.context.scene.objects
        if obj.type == "MESH" and obj.get("Object type") == "MAP"
    )
    water_index = next(
        (index for index, material in enumerate(terrain.data.materials)
         if material and material.name.upper() == "WATER"),
        None,
    )
    if water_index is None:
        raise RuntimeError("Terrain has no WATER material slot")

    source_faces = [
        polygon for polygon in terrain.data.polygons
        if polygon.material_index == water_index and polygon.normal.z > 0.45
    ]
    if not source_faces:
        raise RuntimeError("Terrain WATER material contains no upward surface faces")
    source_vertex_ids = sorted({vertex for face in source_faces for vertex in face.vertices})
    source_world_z = [
        (terrain.matrix_world @ terrain.data.vertices[index].co).z
        for index in source_vertex_ids
    ]
    top_z = float(engineering.get("flat_water_top_z_mm", statistics.median(source_world_z)))
    depth = float(engineering.get("flat_water_insert_depth_mm", 0.8))
    if depth <= 0:
        raise ValueError("flat_water_insert_depth_mm must be positive")

    # A painted region can contain triangles that only meet at a point. Welding
    # those raw triangles into one mesh creates pinch vertices and non-manifold
    # edges. Union the triangles in 2D first, then triangulate each valid polygon
    # independently. This turns the visual paint mask into printable footprints.
    source_triangles = []
    for face in source_faces:
        coords = []
        for index in face.vertices:
            world = terrain.matrix_world @ terrain.data.vertices[index].co
            coords.append((world.x, world.y))
        polygon = Polygon(coords)
        if not polygon.is_empty and polygon.area > 1e-10:
            source_triangles.append(polygon)
    footprint = geometry2d.validate(geometry2d.union(source_triangles))
    # Split zero-width point contacts. A printable solid cannot have two water
    # lobes connected by only one mathematical vertex; extrusion would create a
    # four-face vertical edge. The sub-nozzle relief is visually imperceptible.
    pinch_relief = float(engineering.get("flat_water_pinch_relief_mm", 0.0))
    if pinch_relief > 0:
        footprint = geometry2d.validate(footprint.buffer(-pinch_relief, join_style=2))
    min_area = float(engineering.get("flat_water_min_area_mm2", 0.04))
    footprint_parts = list(geometry2d.iter_polygons(footprint, min_area=min_area))
    cap_objects = [
        obj
        for index, polygon in enumerate(footprint_parts, start=1)
        for obj in polygon_cap(f"S07_Flat_Water_Cap_{index:04d}", polygon)
    ]
    if not cap_objects:
        raise RuntimeError("No valid water polygons remained after 2D cleanup")
    water = merge_objects(cap_objects, "S07_Flat_Water_Insert")
    mesh = water.data

    editable = bmesh.new()
    editable.from_mesh(mesh)
    for vertex in editable.verts:
        vertex.co.z = top_z
    bmesh.ops.recalc_face_normals(editable, faces=editable.faces)
    extrusion = bmesh.ops.extrude_face_region(editable, geom=list(editable.faces))
    bottom_vertices = [
        item for item in extrusion["geom"] if isinstance(item, bmesh.types.BMVert)
    ]
    bmesh.ops.translate(editable, verts=bottom_vertices, vec=Vector((0, 0, -depth)))
    bmesh.ops.recalc_face_normals(editable, faces=editable.faces)
    editable.to_mesh(mesh)
    editable.free()
    mesh.update(calc_edges=True)

    material = bpy.data.materials.get("S07_Flat_Water_Blue") or bpy.data.materials.new(
        "S07_Flat_Water_Blue"
    )
    material.diffuse_color = (0.20, 0.46, 0.62, 1.0)
    water.data.materials.append(material)
    water["Object type"] = "WATER"
    water["S02_geometry"] = "water_area"
    water["water_source"] = "TrailPrint3D_PAINT_WATER_material_faces"
    water["flat_top_z_mm"] = top_z
    water["insert_depth_mm"] = depth

    result = {
        "source_blend": bpy.data.filepath,
        "output_blend": str(output_blend),
        "source_water_faces": len(source_faces),
        "source_water_vertices": len(source_vertex_ids),
        "source_triangle_footprints": len(source_triangles),
        "clean_footprint_parts": len(footprint_parts),
        "clean_footprint_area_mm2": footprint.area,
        "minimum_part_area_mm2": min_area,
        "pinch_relief_mm": pinch_relief,
        "source_water_z": {
            "min": min(source_world_z),
            "median": statistics.median(source_world_z),
            "max": max(source_world_z),
        },
        "flat_top_z_mm": top_z,
        "insert_depth_mm": depth,
        "quality": quality(water),
    }
    if result["quality"]["non_manifold_edges"]:
        raise RuntimeError(f"Flat water is non-manifold: {result['quality']}")
    output_blend.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(output_blend))
    report_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("FLAT_WATER=" + json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
