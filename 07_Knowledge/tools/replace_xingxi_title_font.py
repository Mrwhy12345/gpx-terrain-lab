#!/usr/bin/env python3
"""Replace only the 星溪徒步 glyph islands while preserving other labels."""

import json
import sys
from pathlib import Path

import bmesh
import bpy

FONT = Path("/System/Library/Fonts/Hiragino Sans GB.ttc")


def components(mesh):
    remaining = set(mesh.verts)
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
    return groups


args = sys.argv[sys.argv.index("--") + 1 :]
output_blend, report_path, labels_stl = map(Path, args)
old = next(o for o in bpy.context.scene.objects if o.get("S05_geometry") == "display_title")
base = next(o for o in bpy.context.scene.objects if o.get("S05_geometry") == "display_base")
base_points = [base.matrix_world @ v.co for v in base.data.vertices]
center_x = (min(p.x for p in base_points) + max(p.x for p in base_points)) / 2
center_y = (min(p.y for p in base_points) + max(p.y for p in base_points)) / 2

bm = bmesh.new()
bm.from_mesh(old.data)
title_cutoff = center_y + 34.0
remove = [v for v in bm.verts if (old.matrix_world @ v.co).y > title_cutoff]
bmesh.ops.delete(bm, geom=remove, context="VERTS")
bm.to_mesh(old.data)
bm.free()
old.data.update()

curve = bpy.data.curves.new("Label_星溪徒步_HiraginoSansGB", "FONT")
curve.body = "星溪徒步"
curve.align_x = "CENTER"
curve.align_y = "CENTER"
curve.size = 6.0
curve.extrude = 0.3
curve.offset = 0.12
curve.resolution_u = 8
curve.font = bpy.data.fonts.load(str(FONT))
title = bpy.data.objects.new("Label_星溪徒步_HiraginoSansGB", curve)
bpy.context.scene.collection.objects.link(title)
title.location = (center_x, center_y + 47.0, 0)
bpy.context.view_layer.objects.active = title
title.select_set(True)
bpy.ops.object.convert(target="MESH")
width = max(v.co.x for v in title.data.vertices) - min(v.co.x for v in title.data.vertices)
height = max(v.co.y for v in title.data.vertices) - min(v.co.y for v in title.data.vertices)
scale = min(32.0 / width, 4.2 / height)
title.scale = (scale, scale, 1.0)
bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
depth = max(v.co.z for v in title.data.vertices) - min(v.co.z for v in title.data.vertices)
title.scale.z = 0.6 / depth
bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
zmin = min((title.matrix_world @ v.co).z for v in title.data.vertices)
title.location.z -= zmin
title.data.remesh_voxel_size = 0.08
title.data.remesh_voxel_adaptivity = 0
bpy.context.view_layer.objects.active = title
bpy.ops.object.voxel_remesh()

title.data.transform(old.matrix_world.inverted() @ title.matrix_world)
merged = bmesh.new()
merged.from_mesh(old.data)
merged.from_mesh(title.data)
merged.to_mesh(old.data)
merged.free()
bpy.data.objects.remove(title, do_unlink=True)
old.name = "S10_Three_Edge_Labels_Brown"
old["S05_geometry"] = "display_title"
old["title_font"] = str(FONT)

output_blend.parent.mkdir(parents=True, exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=str(output_blend))
original = old.location.copy()
old.location.x -= center_x
old.location.y -= center_y
bpy.ops.object.select_all(action="DESELECT")
old.select_set(True)
bpy.context.view_layer.objects.active = old
bpy.ops.wm.stl_export(filepath=str(labels_stl), export_selected_objects=True, ascii_format=False)
old.location = original
report_path.write_text(
    json.dumps(
        {
            "replaced_text": "星溪徒步",
            "font": str(FONT),
            "outline_offset": 0.12,
            "preserved": ["2026.07.12", "9.5 KM"],
        },
        ensure_ascii=False,
        indent=2,
    )
    + "\n",
    encoding="utf-8",
)
