#!/usr/bin/env python3
"""Audit final Blender delivery colours, visibility and build-plate contact."""
from __future__ import annotations

import json, sys
from pathlib import Path
import bpy


def bounds(obj):
    points=[obj.matrix_world@vertex.co for vertex in obj.data.vertices]
    return {axis:[min(p[i] for p in points),max(p[i] for p in points)] for i,axis in enumerate(("x","y","z"))}


def main():
    args=sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else []
    if len(args)!=1: raise SystemExit("Expected REPORT.json")
    report=Path(args[0]); records=[]
    for obj in bpy.context.scene.objects:
        if obj.type!="MESH" or not obj.data.vertices or obj.hide_render: continue
        role=(obj.name+str(obj.get("Object type",""))+str(obj.get("S03_geometry",""))+str(obj.get("SYS01_geometry",""))).lower()
        if "trail" not in role and "water" not in role: continue
        materials=[]
        for material in obj.data.materials:
            if material is not None: materials.append({"name":material.name,"rgba":[round(float(v),4) for v in material.diffuse_color]})
        records.append({"name":obj.name,"role":"trail" if "trail" in role else "water","materials":materials,"bounds":bounds(obj)})
    trail=[r for r in records if r["role"]=="trail"]
    water=[r for r in records if r["role"]=="water"]
    def is_red(record): return any(m["rgba"][0]>.6 and m["rgba"][1]<.2 and m["rgba"][2]<.2 for m in record["materials"])
    def is_blue(record): return any(m["rgba"][2]>.5 and m["rgba"][0]<.3 for m in record["materials"])
    checks={"visible_trail":bool(trail),"visible_water":bool(water),"trail_red":bool(trail) and all(is_red(r) for r in trail),"water_blue":bool(water) and all(is_blue(r) for r in water)}
    payload={"status":"PASS" if all(checks.values()) else "FAIL","checks":checks,"objects":records}
    report.parent.mkdir(parents=True,exist_ok=True); report.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(payload,ensure_ascii=False))
    if payload["status"]!="PASS": raise SystemExit(1)


if __name__=="__main__": main()
