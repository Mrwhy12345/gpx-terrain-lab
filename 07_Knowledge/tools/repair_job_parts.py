#!/usr/bin/env python3
"""Audit canonical STLs without rewriting them.

Blender's STL importer removes duplicate/degenerate triangles during import, so its
post-import edge count is not a safe reason to mutate a print mesh.  The production
gate therefore records the imported metrics and preserves the exact source bytes;
final 3MF/Bambu validation decides release readiness.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import bmesh
import bpy

NAMES = (
    "01_Terrain_Low_Green_Grooved.stl",
    "02_Terrain_And_Villages_Brown_Grooved.stl",
    "03_Terrain_High_Gray_Grooved.stl",
    "07_Base_Gray.stl",
    "08_Labels_Logo_Brown.stl",
    "10_Trail_Red_SeparatePrint.stl",
    "05_Water_Blue_SeparatePrint.stl",
)


def quality(obj):
    mesh = bmesh.new(); mesh.from_mesh(obj.data)
    result = {"vertices":len(mesh.verts),"faces":len(mesh.faces),"non_manifold_edges":sum(not edge.is_manifold for edge in mesh.edges)}
    mesh.free(); return result


def main():
    args=sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else []
    if len(args)!=3: raise SystemExit("Expected SOURCE_DIR OUTPUT_DIR REPORT.json")
    source,output,report=map(Path,args); output.mkdir(parents=True,exist_ok=True); records=[]
    for name in NAMES:
        src=source/name; dst=output/name
        if not src.is_file(): raise FileNotFoundError(src)
        bpy.ops.object.select_all(action="SELECT"); bpy.ops.object.delete(use_global=False)
        bpy.ops.wm.stl_import(filepath=str(src)); obj=bpy.context.object; imported=quality(obj)
        shutil.copy2(src,dst)
        records.append({"name":name,"imported_metrics":imported,"action":"byte_preserved_copy"})
    result={"status":"AUDIT_RECORDED","policy":"Do not mutate STL from Blender import metrics; validate packaged 3MF for release.","parts":records}; report.parent.mkdir(parents=True,exist_ok=True); report.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("JOB_PART_REPAIR="+json.dumps(result,ensure_ascii=False))


if __name__=="__main__": main()
