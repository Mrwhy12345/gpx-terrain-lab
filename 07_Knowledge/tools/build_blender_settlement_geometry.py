#!/usr/bin/env python3
"""Build printable residential-area overlays on the enriched S02 terrain."""

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
from shapely.geometry import MultiPoint, shape
from shapely.ops import triangulate


EARTH_RADIUS_KM = 6371.0
MIN_AREA_M2 = 1500.0
TOP_ABOVE_TERRAIN_MM = 0.16
BOTTOM_BELOW_TERRAIN_MM = 0.12


def geo_to_world(longitude, latitude, horizontal_scale):
    return (
        EARTH_RADIUS_KM * math.radians(longitude) * horizontal_scale,
        EARTH_RADIUS_KM
        * math.log(math.tan(math.pi / 4 + math.radians(latitude) / 2))
        * horizontal_scale,
    )


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


def iter_polygons(geometry):
    if geometry.geom_type == "Polygon":
        yield geometry
    elif geometry.geom_type == "MultiPolygon":
        yield from geometry.geoms


def main():
    args = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    if len(args) != 3:
        raise SystemExit(
            "Usage: blender INPUT.blend --python script.py -- "
            "SETTLEMENTS.geojson OUTPUT.blend REPORT.json"
        )
    source_path, output_blend, report_path = map(Path, args)
    data = json.loads(source_path.read_text(encoding="utf-8"))
    terrain = next(
        obj for obj in bpy.context.scene.objects if obj.get("Object type") == "MAP"
    )
    horizontal_scale = float(terrain["Horizontal Scale"])
    footprint = MultiPoint(
        [
            (
                (terrain.matrix_world @ vertex.co).x,
                (terrain.matrix_world @ vertex.co).y,
            )
            for vertex in terrain.data.vertices
        ]
    ).convex_hull.buffer(-0.05)
    depsgraph = bpy.context.evaluated_depsgraph_get()
    terrain_bvh = BVHTree.FromObject(terrain, depsgraph)
    world_to_local = terrain.matrix_world.inverted()
    local_to_world = terrain.matrix_world
    ray_misses = []

    def terrain_z(x, y):
        origin = world_to_local @ Vector((x, y, terrain.dimensions.z + 100))
        direction = (
            world_to_local.to_3x3() @ Vector((0, 0, -1))
        ).normalized()
        hit, _, _, _ = terrain_bvh.ray_cast(origin, direction)
        if hit is None:
            ray_misses.append([x, y])
            return None
        return (local_to_world @ hit).z

    old = bpy.data.collections.get("S02_Settlements")
    if old:
        for obj in list(old.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.collections.remove(old)
    collection = bpy.data.collections.new("S02_Settlements")
    bpy.context.scene.collection.children.link(collection)
    mat = bpy.data.materials.get("Village_Warm_Ivory") or bpy.data.materials.new(
        "Village_Warm_Ivory"
    )
    mat.diffuse_color = (0.88, 0.68, 0.38, 1.0)

    def surface_prism(polygon, name):
        triangles = [
            triangle
            for triangle in triangulate(polygon)
            if polygon.covers(triangle.representative_point())
        ]
        xy_to_index, xy_values, top_faces = {}, [], []
        edges = Counter()

        def index(xy):
            key = (round(xy[0], 8), round(xy[1], 8))
            if key not in xy_to_index:
                xy_to_index[key] = len(xy_values)
                xy_values.append(xy)
            return xy_to_index[key]

        for triangle in triangles:
            xy = list(triangle.exterior.coords)[:3]
            indices = [index(point) for point in xy]
            signed = sum(
                xy[i][0] * xy[(i + 1) % 3][1]
                - xy[(i + 1) % 3][0] * xy[i][1]
                for i in range(3)
            )
            if signed < 0:
                indices.reverse()
            top_faces.append(tuple(indices))
            for a, b in zip(indices, indices[1:] + indices[:1]):
                edges[tuple(sorted((a, b)))] += 1

        top = []
        for x, y in xy_values:
            z = terrain_z(x, y)
            if z is None:
                return None
            top.append((x, y, z + TOP_ABOVE_TERRAIN_MM))
        count = len(top)
        bottom = [(x, y, z - TOP_ABOVE_TERRAIN_MM - BOTTOM_BELOW_TERRAIN_MM) for x, y, z in top]
        faces = list(top_faces)
        faces += [tuple(count + i for i in reversed(face)) for face in top_faces]
        for (a, b), edge_count in edges.items():
            if edge_count == 1:
                faces.append((a, b, count + b, count + a))
        mesh = bpy.data.meshes.new(name)
        mesh.from_pydata(top + bottom, [], faces)
        mesh.update()
        recalculate_normals(mesh)
        return mesh

    created, excluded = [], []
    for feature in data["features"]:
        properties = feature["properties"]
        if properties.get("category") != "residential_area":
            continue
        area = float(properties.get("clipped_area_m2") or 0)
        if area < MIN_AREA_M2:
            excluded.append({"osm_id": properties.get("osm_id"), "area_m2": area})
            continue
        geometry = shape(feature["geometry"])
        for part_index, polygon in enumerate(iter_polygons(geometry), start=1):
            world_polygon = type(polygon)(
                [
                    geo_to_world(lon, lat, horizontal_scale)
                    for lon, lat in polygon.exterior.coords
                ]
            ).intersection(footprint)
            if world_polygon.is_empty:
                continue
            for clipped_index, clipped in enumerate(
                iter_polygons(world_polygon), start=1
            ):
                name = (
                    f"Village_Area_OSM_{properties['osm_id']}"
                    f"_{part_index:02d}_{clipped_index:02d}"
                )
                mesh = surface_prism(clipped, name + "_Mesh")
                if mesh is None:
                    continue
                obj = bpy.data.objects.new(name, mesh)
                collection.objects.link(obj)
                obj.data.materials.append(mat)
                obj["S04_geometry"] = "residential_area"
                obj["OSM_ID"] = properties["osm_id"]
                obj["Area_m2"] = area
                created.append(obj)

    cutter = bpy.data.objects.get("S02_Trail_Groove_Cutter")
    if cutter:
        for obj in created:
            modifier = obj.modifiers.new("Trail_Clearance", "BOOLEAN")
            modifier.operation = "DIFFERENCE"
            modifier.solver = "EXACT"
            modifier.object = cutter
            bpy.context.view_layer.objects.active = obj
            bpy.ops.object.modifier_apply(modifier=modifier.name)

    created_source_ids = sorted({obj.get("OSM_ID") for obj in created})
    if created:
        bpy.ops.object.select_all(action="DESELECT")
        for obj in created:
            obj.select_set(True)
        bpy.context.view_layer.objects.active = created[0]
        bpy.ops.object.join()
        village_part = bpy.context.view_layer.objects.active
        village_part.name = "S02_Villages_Warm"
        village_part["S04_geometry"] = "residential_areas_printable"
        village_part.data.remesh_voxel_size = 0.08
        village_part.data.remesh_voxel_adaptivity = 0.0
        bpy.ops.object.voxel_remesh()
        recalculate_normals(village_part.data)
        final_objects = [village_part]
    else:
        final_objects = []

    report = {
        "source_blend": bpy.data.filepath,
        "output_blend": str(output_blend),
        "settings_mm": {
            "minimum_source_area_m2": MIN_AREA_M2,
            "top_above_terrain": TOP_ABOVE_TERRAIN_MM,
            "bottom_below_terrain": BOTTOM_BELOW_TERRAIN_MM,
        },
        "input_residential_count": sum(
            feature["properties"].get("category") == "residential_area"
            for feature in data["features"]
        ),
        "created_source_areas": len(created_source_ids),
        "created_source_osm_ids": created_source_ids,
        "excluded": excluded,
        "ray_miss_count": len(ray_misses),
        "objects": [
            {"name": obj.name, "dimensions": list(obj.dimensions), "quality": mesh_quality(obj)}
            for obj in final_objects
        ],
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    bpy.ops.wm.save_as_mainfile(filepath=str(output_blend))
    print("SETTLEMENT_GEOMETRY=" + json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
