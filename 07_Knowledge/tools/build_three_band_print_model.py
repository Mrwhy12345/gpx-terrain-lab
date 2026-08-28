#!/usr/bin/env python3
"""Build a three-band printable terrain model without rescaling tested elevation."""

from __future__ import annotations

import hashlib
import json
import struct
import sys
from pathlib import Path

import bmesh
import bpy


VERTICAL_FACTOR = 1.00
BROWN_START = 0.52
GRAY_START = 0.74
MIN_COMPONENT_VERTICES = 500


def quality(obj):
    editable = bmesh.new()
    editable.from_mesh(obj.data)
    result = {
        "vertices": len(editable.verts),
        "faces": len(editable.faces),
        "non_manifold_edges": sum(not edge.is_manifold for edge in editable.edges),
    }
    editable.free()
    return result


def world_bounds(obj):
    points = [obj.matrix_world @ vertex.co for vertex in obj.data.vertices]
    if not points:
        raise RuntimeError(f"Cannot measure empty mesh: {obj.name}")
    return {
        axis: [min(point[i] for point in points), max(point[i] for point in points)]
        for i, axis in enumerate(("x", "y", "z"))
    }


def recalculate_normals(obj):
    editable = bmesh.new()
    editable.from_mesh(obj.data)
    bmesh.ops.recalc_face_normals(editable, faces=editable.faces)
    editable.to_mesh(obj.data)
    editable.free()


def mesh_fingerprint(obj):
    """Fingerprint TrailPrint3D geometry without modifying or resampling it."""
    digest = hashlib.sha256()
    mesh = obj.data
    digest.update(struct.pack("<QQ", len(mesh.vertices), len(mesh.polygons)))
    for vertex in mesh.vertices:
        digest.update(struct.pack("<3d", float(vertex.co.x), float(vertex.co.y), float(vertex.co.z)))
    for polygon in mesh.polygons:
        digest.update(struct.pack("<Q", len(polygon.vertices)))
        for index in polygon.vertices:
            digest.update(struct.pack("<Q", int(index)))
    return digest.hexdigest()


def remove_tiny_components(obj, minimum_vertices=MIN_COMPONENT_VERTICES):
    """Remove boolean crumbs while preserving real disconnected summits."""
    editable = bmesh.new()
    editable.from_mesh(obj.data)
    remaining = set(editable.verts)
    groups = []
    while remaining:
        seed = remaining.pop()
        group = {seed}
        queue = [seed]
        while queue:
            vertex = queue.pop()
            for edge in vertex.link_edges:
                other = edge.other_vert(vertex)
                if other in remaining:
                    remaining.remove(other)
                    group.add(other)
                    queue.append(other)
        groups.append(group)
    removed = [group for group in groups if len(group) < minimum_vertices]
    if removed:
        bmesh.ops.delete(
            editable,
            geom=[vertex for group in removed for vertex in group],
            context="VERTS",
        )
        editable.to_mesh(obj.data)
        obj.data.update()
    kept_sizes = sorted((len(group) for group in groups if len(group) >= minimum_vertices), reverse=True)
    removed_sizes = sorted((len(group) for group in removed), reverse=True)
    editable.free()
    return {"kept_components": len(kept_sizes), "kept_vertex_counts": kept_sizes,
            "removed_components": len(removed_sizes), "removed_vertex_counts": removed_sizes}


def assign_material(obj, name, color):
    material = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    material.diffuse_color = (*color, 1.0)
    obj.data.materials.clear()
    obj.data.materials.append(material)


def prepare_city_terrain_part(terrain):
    """Preserve TrailPrint3D CITY cut-outs as one integrated colour part.

    In single-colour element mode TrailPrint3D extracts each city region from
    the MAP mesh.  CITY is currently contextual land, not a separate customer
    install part, so omitting it leaves a literal hole in the terrain.  Keep
    the complementary geometry in its original position, combine multiple
    city regions into one mesh, and package it as a fourth child of the terrain
    object.  It remains an in-place multicolour print, never a user-installed
    loose part.
    """
    cities = [
        obj for obj in list(bpy.context.scene.objects)
        if obj.type == "MESH" and obj.get("Object type") == "CITY"
    ]
    records = []
    if not cities:
        return None, records
    city_part = cities[0]
    combined = bmesh.new()
    for city in cities:
        record = {
            "name": city.name,
            "bounds": world_bounds(city),
            "quality_before": quality(city),
        }
        city_mesh = city.data.copy()
        city_mesh.transform(city_part.matrix_world.inverted() @ city.matrix_world)
        combined.from_mesh(city_mesh)
        bpy.data.meshes.remove(city_mesh)
        if city != city_part:
            bpy.data.objects.remove(city, do_unlink=True)
        records.append(record)
    combined.to_mesh(city_part.data)
    combined.free()
    city_part.data.update()
    recalculate_normals(city_part)
    city_part.name = "S06_Terrain_City_Terracotta"
    city_part["Object type"] = "TERRAIN_CITY_TERRACOTTA"
    city_part["S06_geometry"] = "terrain_city_terracotta"
    assign_material(city_part, "S06_City_Terracotta_Material", (0.77, 0.42, 0.23))
    return city_part, records


def intersection_box(name, bounds, min_z, max_z):
    center_x = sum(bounds["x"]) / 2
    center_y = sum(bounds["y"]) / 2
    width = bounds["x"][1] - bounds["x"][0] + 4
    height = bounds["y"][1] - bounds["y"][0] + 4
    depth = max_z - min_z
    bpy.ops.mesh.primitive_cube_add(
        location=(center_x, center_y, (min_z + max_z) / 2)
    )
    box = bpy.context.object
    box.name = name
    box.dimensions = (width, height, depth)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    return box


def intersect_copy(source, name, tag, min_z, max_z, color):
    result = source.copy()
    result.data = source.data.copy()
    result.name = name
    bpy.context.scene.collection.objects.link(result)
    bounds = world_bounds(source)
    box = intersection_box(name + "_Cutter", bounds, min_z, max_z)
    modifier = result.modifiers.new("Elevation band intersection", "BOOLEAN")
    modifier.operation = "INTERSECT"
    modifier.solver = "MANIFOLD"
    modifier.object = box
    bpy.context.view_layer.objects.active = result
    result.select_set(True)
    bpy.ops.object.modifier_apply(modifier=modifier.name)
    result.select_set(False)
    bpy.data.objects.remove(box, do_unlink=True)
    recalculate_normals(result)
    if not result.data.vertices:
        raise RuntimeError(f"Elevation band {name} is empty after intersection")
    result["component_cleanup"] = json.dumps(remove_tiny_components(result), ensure_ascii=False)
    result["Object type"] = tag
    result["S06_geometry"] = tag.lower()
    result["Vertical factor"] = VERTICAL_FACTOR
    assign_material(result, name + "_Material", color)
    return result


def main():
    args = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    if len(args) != 2:
        raise SystemExit(
            "Usage: blender INPUT.blend --python script.py -- OUTPUT.blend REPORT.json"
        )
    output_blend, report_path = map(Path, args)
    terrain = next(
        obj for obj in bpy.context.scene.objects if obj.get("Object type") == "MAP"
    )
    terrain_quality_before_city_restore = quality(terrain)
    city_part, city_elements = prepare_city_terrain_part(terrain)
    terrain_quality_after_city_restore = quality(terrain)
    unhandled_city_objects = [
        obj.name for obj in bpy.context.scene.objects
        if obj.type == "MESH" and obj.get("Object type") == "CITY"
    ]
    if unhandled_city_objects:
        raise RuntimeError(f"Unhandled TrailPrint3D CITY objects: {unhandled_city_objects}")

    # The final visible terrain must come directly from TrailPrint3D. Do not
    # smooth, remesh, decimate, resample, or rescale the source surface.
    if abs(VERTICAL_FACTOR - 1.0) > 1e-9:
        raise RuntimeError(
            "TrailPrint3D source-surface-direct policy requires VERTICAL_FACTOR == 1.0"
        )
    source_surface_objects = [terrain] + ([city_part] if city_part else [])
    surface_fidelity = {
        obj.name: {
            "source_fingerprint": mesh_fingerprint(obj),
            "pre_band_fingerprint": None,
            "unchanged": False,
            "quality": quality(obj),
            "bounds": world_bounds(obj),
        }
        for obj in source_surface_objects
    }

    roads = [
        obj
        for obj in list(bpy.context.scene.objects)
        if obj.get("S03_geometry") == "roads_printable"
    ]
    removed_roads = [obj.name for obj in roads]
    for road in roads:
        bpy.data.objects.remove(road, do_unlink=True)

    for obj in source_surface_objects:
        audit = surface_fidelity[obj.name]
        audit["pre_band_fingerprint"] = mesh_fingerprint(obj)
        audit["unchanged"] = (
            audit["source_fingerprint"] == audit["pre_band_fingerprint"]
        )
        if not audit["unchanged"]:
            raise RuntimeError(
                f"TrailPrint3D source mesh changed before band split: {obj.name}"
            )

    bounds = world_bounds(terrain)
    min_z, max_z = bounds["z"]
    brown_z = min_z + (max_z - min_z) * BROWN_START
    gray_z = min_z + (max_z - min_z) * GRAY_START
    epsilon = 0.001
    low = intersect_copy(
        terrain,
        "S06_Terrain_Low_Green",
        "TERRAIN_LOW_GREEN",
        min_z - 1,
        brown_z,
        (0.28, 0.43, 0.10),
    )
    middle = intersect_copy(
        terrain,
        "S06_Terrain_Middle_Brown",
        "TERRAIN_MIDDLE_BROWN",
        brown_z - epsilon,
        gray_z,
        (0.43, 0.26, 0.10),
    )
    high = intersect_copy(
        terrain,
        "S06_Terrain_High_Gray",
        "TERRAIN_HIGH_GRAY",
        gray_z - epsilon,
        max_z + 1,
        (0.47, 0.51, 0.54),
    )
    bpy.data.objects.remove(terrain, do_unlink=True)

    bands = [low, middle, high]
    report = {
        "source_blend": bpy.data.filepath,
        "output_blend": str(output_blend),
        "vertical_factor": VERTICAL_FACTOR,
        "surface_fidelity": {
            "policy": "trailprint_source_surface_direct",
            "source_unchanged_before_band_split": all(
                audit["unchanged"] for audit in surface_fidelity.values()
            ),
            "vertical_factor": VERTICAL_FACTOR,
            "operations": {
                "surface_smoothing": False,
                "surface_remesh": False,
                "surface_decimation": False,
                "source_z_rescale": False,
            },
            "band_method": "z_slab_boolean_intersection_only",
            "objects": surface_fidelity,
        },
        "source_surface_objects": [obj.name for obj in source_surface_objects],
        "city_restore": {
            "input_count": len(city_elements),
            "merged_count": len(city_elements),
            "output_count": 1 if city_part else 0,
            "unhandled": unhandled_city_objects,
            "method": "preserve_city_as_integrated_terracotta_terrain_part",
            "elements": city_elements,
            "city_quality_after": quality(city_part) if city_part else None,
            "terrain_quality_before": terrain_quality_before_city_restore,
            "terrain_quality_after": terrain_quality_after_city_restore,
        },
        "roads_removed": removed_roads,
        "thresholds": {
            "brown_fraction": BROWN_START,
            "brown_z_mm": brown_z,
            "gray_fraction": GRAY_START,
            "gray_z_mm": gray_z,
        },
        "bands": [
            {
                "name": obj.name,
                "bounds": world_bounds(obj),
                "quality": quality(obj),
                "component_cleanup": json.loads(obj["component_cleanup"]),
            }
            for obj in bands
        ],
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    bpy.ops.wm.save_as_mainfile(filepath=str(output_blend))
    print("THREE_BAND_PRINT_MODEL=" + json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
