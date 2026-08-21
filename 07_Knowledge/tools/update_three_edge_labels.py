#!/usr/bin/env python3
"""Place route title, date, and distance on three display-base edges."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import bmesh
import bpy


# Hiragino Sans GB has complete Simplified Chinese glyph outlines and produces
# clean, relatively heavy strokes at small printed sizes.
FONT = Path("/System/Library/Fonts/Hiragino Sans GB.ttc")
RAISE_MM = 0.6
EDGE_INSET_MM = 11.5
MIN_PRINTABLE_LABEL_HEIGHT_MM = 3.20
LABEL_SIDE_QUIET_MM = 0.65
FONT_OUTLINE_OFFSET_MM = 0.20
LABELS = (
    ("星溪徒步", 32.0, 4.2),
    ("2026.07.12", 31.0, 3.8),
    ("9.5 KM", 24.0, 4.2),
)


def world_bounds(obj):
    points = [obj.matrix_world @ vertex.co for vertex in obj.data.vertices]
    return [
        [min(point[i] for point in points), max(point[i] for point in points)]
        for i in range(3)
    ]


def quality(obj):
    mesh = bmesh.new()
    mesh.from_mesh(obj.data)
    result = {
        "vertices": len(mesh.verts),
        "faces": len(mesh.faces),
        "non_manifold_edges": sum(not edge.is_manifold for edge in mesh.edges),
    }
    mesh.free()
    return result


def world_xy(obj):
    return [(obj.matrix_world @ vertex.co).xy for vertex in obj.data.vertices]


def normalized(vector):
    length = math.hypot(*vector)
    return (vector[0] / length, vector[1] / length)


def edge_band_center(base, terrain, scene_center, rotation, outward):
    """Return the printable band center on a base edge.

    The position is derived from the final base mesh rather than hard-coded
    offsets.  Near-support vertices establish the actual tangent midpoint.
    """
    outward = normalized(outward)
    tangent = (math.cos(rotation), math.sin(rotation))
    points = [
        (point.x - scene_center[0], point.y - scene_center[1])
        for point in world_xy(base)
    ]
    support = max(point[0] * outward[0] + point[1] * outward[1] for point in points)
    near = [
        point
        for point in points
        if support - (point[0] * outward[0] + point[1] * outward[1]) <= 0.8
    ]
    tangent_values = [point[0] * tangent[0] + point[1] * tangent[1] for point in near]
    tangent_midpoint = (min(tangent_values) + max(tangent_values)) / 2
    if base.get("Construction method") == "true_parallel_polygon_offset":
        terrain_points = [
            (point.x - scene_center[0], point.y - scene_center[1])
            for point in world_xy(terrain)
        ]
        terrain_support = max(
            point[0] * outward[0] + point[1] * outward[1]
            for point in terrain_points
        )
        recess_support = terrain_support + float(
            base.get("Slot clearance mm", 0.30)
        )
        # The label belongs in the exposed border, halfway between the
        # recess edge and outer edge. It must never occupy the terrain seat.
        normal_position = (support + recess_support) / 2
    else:
        normal_position = support - EDGE_INSET_MM
    return (
        scene_center[0] + tangent_midpoint * tangent[0] + normal_position * outward[0],
        scene_center[1] + tangent_midpoint * tangent[1] + normal_position * outward[1],
    )


def edge_midband_center(base, terrain, outward):
    """Midpoint of a real exposed edge band using support-plane vertices.

    This is robust when the fitted base and terrain have slightly different
    side angles; it does not infer the edge midpoint from the terrain angle.
    """
    outward = normalized(outward)
    tangent = (-outward[1], outward[0])
    base_points = [(p.x, p.y) for p in world_xy(base)]
    terrain_points = [(p.x, p.y) for p in world_xy(terrain)]
    base_support = max(x*outward[0] + y*outward[1] for x, y in base_points)
    terrain_support = max(x*outward[0] + y*outward[1] for x, y in terrain_points)
    near = [
        (x, y) for x, y in base_points
        if base_support - (x*outward[0] + y*outward[1]) <= 0.8
    ]
    tangent_values = [x*tangent[0] + y*tangent[1] for x, y in near]
    tangent_mid = (min(tangent_values) + max(tangent_values)) / 2
    normal_mid = (base_support + terrain_support + float(base.get("Slot clearance mm", .3))) / 2
    return (
        tangent_mid*tangent[0] + normal_mid*outward[0],
        tangent_mid*tangent[1] + normal_mid*outward[1],
    )


def oriented_bounds_center(obj, rotation):
    tangent = (math.cos(rotation), math.sin(rotation))
    normal = (-math.sin(rotation), math.cos(rotation))
    points = world_xy(obj)
    tangent_values = [point.x * tangent[0] + point.y * tangent[1] for point in points]
    normal_values = [point.x * normal[0] + point.y * normal[1] for point in points]
    tangent_center = (min(tangent_values) + max(tangent_values)) / 2
    normal_center = (min(normal_values) + max(normal_values)) / 2
    return (
        tangent_center * tangent[0] + normal_center * normal[0],
        tangent_center * tangent[1] + normal_center * normal[1],
    )


def create_label(text, target, rotation, max_width, max_height):
    curve = bpy.data.curves.new(f"Label_{text}", "FONT")
    curve.body = text
    curve.align_x = "CENTER"
    curve.align_y = "CENTER"
    curve.size = 6.0
    curve.extrude = 0.3
    # Slight outline expansion preserves Chinese strokes at a 0.4 mm nozzle.
    curve.offset = FONT_OUTLINE_OFFSET_MM
    curve.resolution_u = 8
    curve.font = bpy.data.fonts.load(str(FONT))
    obj = bpy.data.objects.new(f"Label_{text}", curve)
    bpy.context.scene.collection.objects.link(obj)
    obj.location = (target[0], target[1], 0.0)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.convert(target="MESH")
    bounds = world_bounds(obj)
    width = bounds[0][1] - bounds[0][0]
    height = bounds[1][1] - bounds[1][0]
    scale = min(max_width / width, max_height / height)
    obj.scale.x *= scale
    obj.scale.y *= scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    bounds = world_bounds(obj)
    depth = bounds[2][1] - bounds[2][0]
    obj.scale.z *= RAISE_MM / depth
    obj.rotation_euler.z = rotation
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    bounds = world_bounds(obj)
    obj.location.z -= bounds[2][0]
    obj.data.remesh_voxel_size = 0.08
    obj.data.remesh_voxel_adaptivity = 0.0
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.voxel_remesh()
    # Voxel remesh and glyph asymmetry can shift the final visual bounds.
    # Recenter the finished mesh, not merely the pre-conversion font origin.
    actual_center = oriented_bounds_center(obj, rotation)
    obj.location.x += target[0] - actual_center[0]
    obj.location.y += target[1] - actual_center[1]
    bpy.context.view_layer.update()
    corrected_center = oriented_bounds_center(obj, rotation)
    return obj, {
        "text": text,
        "rotation_deg": round(math.degrees(rotation), 4),
        "target_center": [round(target[0], 6), round(target[1], 6)],
        "actual_center": [round(corrected_center[0], 6), round(corrected_center[1], 6)],
        "centering_error_mm": round(math.dist(target, corrected_center), 6),
        "max_width_mm": round(max_width, 6),
        "max_height_mm": round(max_height, 6),
    }


def main():
    args = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    if len(args) not in {3, 4}:
        raise SystemExit("Expected OUTPUT.blend REPORT.json TITLE.stl [JOB.json]")
    output_blend, report_path, title_stl = map(Path, args[:3])
    labels_spec = LABELS
    if len(args) == 4:
        job = json.loads(Path(args[3]).read_text(encoding="utf-8"))
        title = (
            job.get("creative", {}).get("selected_title")
            or job.get("customer_input", {}).get("title")
            or job["route"]["name"]
        )
        date = job["customer_input"]["display_date"].replace("-", ".")
        facts_path = Path(args[3]).parent / job["route"]["facts"]
        facts = json.loads(facts_path.read_text(encoding="utf-8"))
        distance = (
            facts.get("distance_km")
            or facts.get("distance_km_raw")
            or facts.get("track", {}).get("distance_km")
        )
        labels_spec = (
            (title, 32.0, 4.2),
            (date, 31.0, 3.8),
            (f"{float(distance):.1f} KM", 24.0, 4.2),
        )
    terrain = next(
        obj for obj in bpy.context.scene.objects
        if obj.get("Object type") == "TERRAIN_LOW_GREEN"
    )
    center_x, center_y = terrain.location.x, terrain.location.y
    terrain_bounds = world_bounds(terrain)
    terrain_width = terrain_bounds[0][1] - terrain_bounds[0][0]
    terrain_height = terrain_bounds[1][1] - terrain_bounds[1][0]
    base = next(
        obj
        for obj in bpy.context.scene.objects
        if obj.get("S05_geometry") == "display_base"
    )
    side_angle = (
        math.radians(float(base.get("Side edge angle deg")))
        if base.get("Side edge angle deg") is not None
        else math.atan2(terrain_height / 2, terrain_width / 4)
    )
    visible_ring_width = float(base.get("Visible ring width mm", 0.0))
    # Keep at least about one stroke-height of quiet space on each side of
    # the text.  This turns the frame constraint into a typography constraint
    # instead of letting legacy 4.2 mm labels overfill a narrower border.
    adaptive_height = None
    if visible_ring_width > 0:
        available_height = visible_ring_width - 2 * LABEL_SIDE_QUIET_MM
        if available_height < MIN_PRINTABLE_LABEL_HEIGHT_MM:
            raise RuntimeError(
                f"Visible ring {visible_ring_width:.3f} mm cannot carry printable "
                f"text: available={available_height:.3f} mm, "
                f"required={MIN_PRINTABLE_LABEL_HEIGHT_MM:.3f} mm"
            )
        adaptive_height = min(3.30, available_height)
    label_geometry = (
        (labels_spec[0][0], 0.0, (0.0, 1.0), labels_spec[0][1], labels_spec[0][2]),
        (
            labels_spec[1][0],
            -side_angle,
            (-math.sin(side_angle), -math.cos(side_angle)),
            labels_spec[1][1],
            labels_spec[1][2],
        ),
        (
            labels_spec[2][0],
            side_angle,
            (math.sin(side_angle), -math.cos(side_angle)),
            labels_spec[2][1],
            labels_spec[2][2],
        ),
    )
    for obj in list(bpy.context.scene.objects):
        if obj.get("S05_geometry") == "display_title":
            bpy.data.objects.remove(obj, do_unlink=True)
    created = []
    for text, rotation, outward, width, height in label_geometry:
        target = (
            edge_midband_center(base, terrain, outward)
            if base.get("Construction method") == "true_parallel_polygon_offset"
            else edge_band_center(base, terrain, (center_x, center_y), rotation, outward)
        )
        created.append(create_label(
            text,
            target,
            rotation,
            width,
            min(height, adaptive_height) if adaptive_height else height,
        ))
    labels = [item[0] for item in created]
    placements = [item[1] for item in created]
    if base.get("Construction method") == "true_parallel_polygon_offset":
        for item_index, (obj, placement) in enumerate(created):
            rotation = math.radians(placement["rotation_deg"])
            outward = (
                (0.0, 1.0)
                if item_index == 0
                else (
                    (-math.sin(side_angle), -math.cos(side_angle))
                    if item_index == 1
                    else (math.sin(side_angle), -math.cos(side_angle))
                )
            )
            terrain_support = max(
                point.x * outward[0] + point.y * outward[1]
                for point in world_xy(terrain)
            )
            label_min_support = min(
                point.x * outward[0] + point.y * outward[1]
                for point in world_xy(obj)
            )
            clearance_to_recess = label_min_support - (
                terrain_support + float(base.get("Slot clearance mm", 0.30))
            )
            placement["clearance_to_recess_mm"] = round(
                clearance_to_recess, 6
            )
            if clearance_to_recess < -1e-4:
                raise RuntimeError(
                    f"{placement['text']} enters terrain recess by "
                    f"{-clearance_to_recess:.3f} mm"
                )
    bpy.ops.object.select_all(action="DESELECT")
    for obj in labels:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = labels[0]
    bpy.ops.object.join()
    title = bpy.context.object
    title.name = "S10_Three_Edge_Labels_Brown"
    title["S05_geometry"] = "display_title"
    title["S10_geometry"] = "three_edge_labels"
    material = bpy.data.materials.get("S10_Label_Brown") or bpy.data.materials.new(
        "S10_Label_Brown"
    )
    material.diffuse_color = (0.43, 0.26, 0.10, 1.0)
    title.data.materials.append(material)
    report = {
        "labels": [label[0] for label in labels_spec],
        "side_edge_angle_deg": math.degrees(side_angle),
        "font": str(FONT),
        "font_format": "Hiragino Sans GB TTC",
        "outline_offset_mm_before_scaling": FONT_OUTLINE_OFFSET_MM,
        "minimum_printable_label_height_mm": MIN_PRINTABLE_LABEL_HEIGHT_MM,
        "label_side_quiet_mm": LABEL_SIDE_QUIET_MM,
        "placement_method": "base_mesh_support_edge_and_final_mesh_bounds",
        "visible_ring_width_mm": visible_ring_width,
        "adaptive_label_height_mm": adaptive_height,
        "edge_inset_mm": EDGE_INSET_MM,
        "placements": placements,
        "bounds": world_bounds(title),
        "quality": quality(title),
    }
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    bpy.ops.wm.save_as_mainfile(filepath=str(output_blend))
    original_location = title.location.copy()
    title.location.x -= center_x
    title.location.y -= center_y
    bpy.ops.object.select_all(action="DESELECT")
    title.select_set(True)
    bpy.context.view_layer.objects.active = title
    bpy.ops.wm.stl_export(
        filepath=str(title_stl), export_selected_objects=True, ascii_format=False
    )
    title.location = original_location
    print("THREE_EDGE_LABELS=" + json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
