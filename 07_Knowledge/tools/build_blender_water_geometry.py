#!/usr/bin/env python3
"""Build printable water objects on an existing TrailPrint3D terrain."""

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
from shapely.ops import triangulate


EARTH_RADIUS_KM = 6371.0
LINE_RADIUS_MM = 0.45
LINE_SAMPLE_STEP_MM = 0.6
WATER_TOP_ABOVE_TERRAIN_MM = 0.36
WATER_BOTTOM_BELOW_TERRAIN_MM = 0.18


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
        dx = end[0] - start[0]
        dy = end[1] - start[1]
        distance = math.hypot(dx, dy)
        divisions = max(1, math.ceil(distance / step))
        sampled.extend(
            (
                start[0] + dx * index / divisions,
                start[1] + dy * index / divisions,
            )
            for index in range(1, divisions + 1)
        )
    return sampled


def ensure_blue_material():
    material = bpy.data.materials.get("Water_Blue")
    if material is None:
        material = bpy.data.materials.new("Water_Blue")
    material.diffuse_color = (0.02, 0.35, 0.95, 1.0)
    return material


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
            "LINES.geojson POLYGONS.geojson OUTPUT.blend REPORT.json"
        )
    line_path, polygon_path, output_blend, report_path = map(Path, arguments)

    map_objects = [
        obj
        for obj in bpy.context.scene.objects
        if obj.type == "MESH" and obj.get("Object type") == "MAP"
    ]
    if len(map_objects) != 1:
        raise SystemExit(f"Expected one TrailPrint3D MAP, found {len(map_objects)}")
    terrain = map_objects[0]
    horizontal_scale = float(terrain["Horizontal Scale"])
    terrain_footprint = MultiPoint(
        [
            (
                (terrain.matrix_world @ vertex.co).x,
                (terrain.matrix_world @ vertex.co).y,
            )
            for vertex in terrain.data.vertices
        ]
    ).convex_hull.buffer(-0.001)
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

    old_collection = bpy.data.collections.get("S02_Water")
    if old_collection is not None:
        for obj in list(old_collection.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.collections.remove(old_collection)
    collection = bpy.data.collections.new("S02_Water")
    bpy.context.scene.collection.children.link(collection)
    material = ensure_blue_material()
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
                (world_x, world_y, z + WATER_TOP_ABOVE_TERRAIN_MM)
            )
        if not top_vertices:
            return None
        bottom_vertices = [
            (
                x,
                y,
                z - WATER_TOP_ABOVE_TERRAIN_MM - WATER_BOTTOM_BELOW_TERRAIN_MM,
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

    line_features = load(line_path)["features"]
    for feature_index, feature in enumerate(line_features, start=1):
        geometry = shape(feature["geometry"])
        for part_index, line in enumerate(iter_lines(geometry), start=1):
            xy = [
                geo_to_world(lon, lat, horizontal_scale)
                for lon, lat in line.coords
            ]
            sampled = sample_xy(xy, LINE_SAMPLE_STEP_MM)
            ribbon = LineString(sampled).buffer(
                LINE_RADIUS_MM,
                cap_style="flat",
                join_style="mitre",
            ).intersection(terrain_footprint)
            for ribbon_part_index, ribbon_part in enumerate(
                iter_polygons(ribbon), start=1
            ):
                mesh = build_surface_prism(
                    ribbon_part,
                    (
                        f"Water_Stream_{feature_index:02d}_{part_index:02d}"
                        f"_{ribbon_part_index:02d}_Mesh"
                    ),
                )
                if mesh is None:
                    continue
                obj = bpy.data.objects.new(
                    (
                        f"Water_Stream_{feature_index:02d}_{part_index:02d}"
                        f"_{ribbon_part_index:02d}"
                        f"_OSM_{feature['properties']['osm_id']}"
                    ),
                    mesh,
                )
                collection.objects.link(obj)
                obj.data.materials.append(material)
                obj["S02_geometry"] = "stream_ribbon"
                obj["OSM_ID"] = feature["properties"]["osm_id"]
                created.append(obj)

    polygon_features = load(polygon_path)["features"]
    for feature_index, feature in enumerate(polygon_features, start=1):
        source_geometry = shape(feature["geometry"])
        for part_index, polygon in enumerate(iter_polygons(source_geometry), start=1):
            world_polygon = type(polygon)(
                [
                    geo_to_world(lon, lat, horizontal_scale)
                    for lon, lat in polygon.exterior.coords
                ]
            )
            mesh = build_surface_prism(
                world_polygon,
                f"Water_Area_{feature_index:02d}_{part_index:02d}_Mesh",
            )
            if mesh is None:
                continue
            obj = bpy.data.objects.new(
                (
                    f"Water_Area_{feature_index:02d}_{part_index:02d}"
                    f"_OSM_{feature['properties']['osm_id']}"
                ),
                mesh,
            )
            collection.objects.link(obj)
            obj.data.materials.append(material)
            obj["S02_geometry"] = "water_area"
            obj["OSM_ID"] = feature["properties"]["osm_id"]
            created.append(obj)

    report = {
        "source_blend": bpy.data.filepath,
        "output_blend": str(output_blend),
        "terrain_object": terrain.name,
        "horizontal_scale": horizontal_scale,
        "settings_mm": {
            "stream_width": LINE_RADIUS_MM * 2,
            "water_top_above_terrain": WATER_TOP_ABOVE_TERRAIN_MM,
            "water_bottom_below_terrain": WATER_BOTTOM_BELOW_TERRAIN_MM,
        },
        "created_objects": [
            {
                "name": obj.name,
                "kind": obj.get("S02_geometry"),
                "osm_id": obj.get("OSM_ID"),
                "dimensions": [round(value, 4) for value in obj.dimensions],
                "mesh_quality": mesh_quality(obj),
            }
            for obj in created
        ],
        "created_count": len(created),
        "ray_miss_count": len(ray_misses),
        "ray_miss_samples": ray_misses[:10],
        "validation_status": "geometry_preview_requires_slice_review",
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    output_blend.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(output_blend))
    print("BLENDER_WATER_REPORT=" + json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
