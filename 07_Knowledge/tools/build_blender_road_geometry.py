#!/usr/bin/env python3
"""Build printable major/local road objects on the S02 terrain."""

from __future__ import annotations

import json
import math
import sys
from collections import Counter
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from shapely.geometry import LineString, MultiPoint, shape
from shapely.ops import triangulate, unary_union


EARTH_RADIUS_KM = 6371.0
ROAD_WIDTHS_MM = {"major": 0.9, "local": 0.65}
ROAD_SAMPLE_STEP_MM = 0.6
ROAD_TOP_ABOVE_TERRAIN_MM = 0.24
ROAD_BOTTOM_BELOW_TERRAIN_MM = 0.14


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def geo_to_world(longitude, latitude, horizontal_scale):
    x = EARTH_RADIUS_KM * math.radians(longitude) * horizontal_scale
    y = (
        EARTH_RADIUS_KM
        * math.log(math.tan(math.pi / 4 + math.radians(latitude) / 2))
        * horizontal_scale
    )
    return x, y


def iter_lines(geometry):
    if geometry.geom_type == "LineString":
        yield geometry
    elif geometry.geom_type == "MultiLineString":
        yield from geometry.geoms


def iter_polygons(geometry):
    if geometry.geom_type == "Polygon":
        yield geometry
    elif geometry.geom_type == "MultiPolygon":
        yield from geometry.geoms


def sample_xy(points, step):
    sampled = [points[0]]
    for start, end in zip(points, points[1:]):
        distance = math.hypot(end[0] - start[0], end[1] - start[1])
        divisions = max(1, math.ceil(distance / step))
        sampled.extend(
            (
                start[0] + (end[0] - start[0]) * index / divisions,
                start[1] + (end[1] - start[1]) * index / divisions,
            )
            for index in range(1, divisions + 1)
        )
    return sampled


def material():
    result = bpy.data.materials.get("Road_Dark")
    if result is None:
        result = bpy.data.materials.new("Road_Dark")
    result.diffuse_color = (0.055, 0.065, 0.075, 1.0)
    return result


def recalculate_normals(mesh):
    editable = bmesh.new()
    editable.from_mesh(mesh)
    bmesh.ops.recalc_face_normals(editable, faces=editable.faces)
    editable.to_mesh(mesh)
    editable.free()


def mesh_quality(obj):
    editable = bmesh.new()
    editable.from_mesh(obj.data)
    result = {
        "vertices": len(editable.verts),
        "edges": len(editable.edges),
        "faces": len(editable.faces),
        "non_manifold_edges": sum(not edge.is_manifold for edge in editable.edges),
    }
    editable.free()
    return result


def main():
    arguments = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    if len(arguments) != 4:
        raise SystemExit(
            "Usage: blender INPUT.blend --python script.py -- "
            "MAJOR.geojson LOCAL.geojson OUTPUT.blend REPORT.json"
        )
    major_path, local_path, output_blend, report_path = map(Path, arguments)

    terrain = next(
        obj
        for obj in bpy.context.scene.objects
        if obj.type == "MESH" and obj.get("Object type") == "MAP"
    )
    horizontal_scale = float(terrain["Horizontal Scale"])
    terrain_footprint = MultiPoint(
        [
            (
                (terrain.matrix_world @ vertex.co).x,
                (terrain.matrix_world @ vertex.co).y,
            )
            for vertex in terrain.data.vertices
        ]
    # Keep projected ribbons slightly inside the terrain wall.  OSM roads
    # commonly cross the map boundary, and exact boundary vertices can miss
    # the terrain ray cast because the wall and top share the same XY edge.
    ).convex_hull.buffer(-0.05)
    depsgraph = bpy.context.evaluated_depsgraph_get()
    terrain_bvh = BVHTree.FromObject(terrain, depsgraph)
    world_to_local = terrain.matrix_world.inverted()
    local_to_world = terrain.matrix_world
    ray_misses = []

    def terrain_z(world_x, world_y):
        world_origin = Vector((world_x, world_y, terrain.dimensions.z + 100))
        local_origin = world_to_local @ world_origin
        local_direction = (
            world_to_local.to_3x3() @ Vector((0, 0, -1))
        ).normalized()
        hit, _, _, _ = terrain_bvh.ray_cast(local_origin, local_direction)
        if hit is None:
            ray_misses.append([world_x, world_y])
            return None
        return (local_to_world @ hit).z

    old_collection = bpy.data.collections.get("S03_Roads")
    if old_collection is not None:
        for obj in list(old_collection.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.collections.remove(old_collection)
    collection = bpy.data.collections.new("S03_Roads")
    bpy.context.scene.collection.children.link(collection)
    road_material = material()
    created = []

    def build_surface_prism(polygon, mesh_name):
        triangles = [
            triangle
            for triangle in triangulate(polygon)
            if polygon.covers(triangle.representative_point())
        ]
        xy_to_index = {}
        xy_values = []
        top_faces = []
        edge_counts = Counter()

        def vertex_index(xy):
            key = (round(xy[0], 8), round(xy[1], 8))
            if key not in xy_to_index:
                xy_to_index[key] = len(xy_values)
                xy_values.append(xy)
            return xy_to_index[key]

        for triangle in triangles:
            world_xy = list(triangle.exterior.coords)[:3]
            indices = [vertex_index(xy) for xy in world_xy]
            signed_area = sum(
                world_xy[index][0] * world_xy[(index + 1) % 3][1]
                - world_xy[(index + 1) % 3][0] * world_xy[index][1]
                for index in range(3)
            )
            if signed_area < 0:
                indices.reverse()
            top_faces.append(tuple(indices))
            for a, b in zip(indices, indices[1:] + indices[:1]):
                edge_counts[tuple(sorted((a, b)))] += 1

        top_vertices = []
        for world_x, world_y in xy_values:
            z = terrain_z(world_x, world_y)
            if z is None:
                return None
            top_vertices.append(
                (world_x, world_y, z + ROAD_TOP_ABOVE_TERRAIN_MM)
            )
        bottom_vertices = [
            (
                x,
                y,
                z - ROAD_TOP_ABOVE_TERRAIN_MM
                - ROAD_BOTTOM_BELOW_TERRAIN_MM,
            )
            for x, y, z in top_vertices
        ]
        vertex_count = len(top_vertices)
        faces = list(top_faces)
        faces.extend(
            tuple(vertex_count + index for index in reversed(face))
            for face in top_faces
        )
        for (a, b), count in edge_counts.items():
            if count == 1:
                faces.append((a, b, vertex_count + b, vertex_count + a))
        mesh = bpy.data.meshes.new(mesh_name)
        mesh.from_pydata(top_vertices + bottom_vertices, [], faces)
        mesh.update()
        recalculate_normals(mesh)
        return mesh

    for group, path in (("major", major_path), ("local", local_path)):
        buffered = []
        source_features = load(path)["features"]
        for feature in source_features:
            for line in iter_lines(shape(feature["geometry"])):
                xy = [
                    geo_to_world(lon, lat, horizontal_scale)
                    for lon, lat in line.coords
                ]
                if len(xy) < 2:
                    continue
                sampled = sample_xy(xy, ROAD_SAMPLE_STEP_MM)
                buffered.append(
                    LineString(sampled).buffer(
                        ROAD_WIDTHS_MM[group] / 2,
                        cap_style="flat",
                        join_style="round",
                    )
                )
        merged = unary_union(buffered).intersection(terrain_footprint)
        part_count = 0
        for index, polygon in enumerate(iter_polygons(merged), start=1):
            if polygon.area < 0.025:
                continue
            mesh = build_surface_prism(
                polygon, f"Road_{group.title()}_{index:03d}_Mesh"
            )
            if mesh is None:
                continue
            obj = bpy.data.objects.new(
                f"Road_{group.title()}_{index:03d}", mesh
            )
            collection.objects.link(obj)
            obj.data.materials.append(road_material)
            obj["S03_geometry"] = f"road_{group}"
            created.append(obj)
            part_count += 1
        print(f"ROAD_GROUP={group} SOURCE={len(source_features)} PARTS={part_count}")

    # Merge touching road ribbons and voxel-remesh them into one watertight
    # printable part.  OSM junctions can otherwise leave a few non-manifold
    # pinch edges where several buffered road polygons meet at one point.
    if created:
        bpy.ops.object.select_all(action="DESELECT")
        for obj in created:
            obj.select_set(True)
        bpy.context.view_layer.objects.active = created[0]
        bpy.ops.object.join()
        road_part = bpy.context.view_layer.objects.active
        road_part.name = "S02_Roads_Dark"
        # 0.12 mm keeps a 0.65 mm local road at roughly five voxels wide
        # while avoiding an unnecessarily large slicer file.
        road_part.data.remesh_voxel_size = 0.12
        road_part.data.remesh_voxel_adaptivity = 0.0
        bpy.ops.object.voxel_remesh()
        recalculate_normals(road_part.data)
        road_part["S03_geometry"] = "roads_printable"
        created = [road_part]

    bpy.ops.wm.save_as_mainfile(filepath=str(output_blend))
    report = {
        "source_blend": bpy.data.filepath,
        "major_source_features": len(load(major_path)["features"]),
        "local_source_features": len(load(local_path)["features"]),
        "created_objects": len(created),
        "ray_misses": len(ray_misses),
        "parameters": {
            "widths_mm": ROAD_WIDTHS_MM,
            "top_above_terrain_mm": ROAD_TOP_ABOVE_TERRAIN_MM,
            "bottom_below_terrain_mm": ROAD_BOTTOM_BELOW_TERRAIN_MM,
            "minor_roads_included": False,
        },
        "objects": [
            {"name": obj.name, "quality": mesh_quality(obj)}
            for obj in created
        ],
    }
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print("S03_ROAD_REPORT=" + json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
