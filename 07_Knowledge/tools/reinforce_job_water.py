#!/usr/bin/env python3
"""Reinforce a job water insert and join only nearby islands with buried rails."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector
from mathutils.kdtree import KDTree

MIN_NECK_MM = 1.35
RAIL_HEIGHT_MM = 0.55
MAX_LOCAL_GAP_MM = 4.0
TARGET_COMPONENTS = 2
VOXEL_MM = 0.065


def groups(obj):
    mesh=bmesh.new(); mesh.from_mesh(obj.data); remaining=set(mesh.verts); result=[]
    while remaining:
        seed=remaining.pop(); group={seed}; queue=[seed]
        while queue:
            vertex=queue.pop()
            for edge in vertex.link_edges:
                other=edge.other_vert(vertex)
                if other in remaining: remaining.remove(other); group.add(other); queue.append(other)
        result.append([obj.matrix_world@vertex.co for vertex in group])
    mesh.free(); return result


def nearest_pair(left,right):
    tree=KDTree(len(left))
    for index,point in enumerate(left): tree.insert(point,index)
    tree.balance(); best=None
    for point in right:
        nearest,_,distance=tree.find(point)
        if best is None or distance<best[0]: best=(distance,nearest.copy(),point.copy())
    return best


def nearest_edges(components):
    candidates=[]
    for left in range(len(components)):
        for right in range(left+1,len(components)):
            distance,start,end=nearest_pair(components[left],components[right])
            candidates.append((distance,left,right,start,end))
    return sorted(candidates,key=lambda item:item[0])


def rail(name,start,end):
    midpoint=(start+end)/2; length=(end.xy-start.xy).length
    z0=min(start.z,end.z)-0.03; z1=z0+RAIL_HEIGHT_MM
    bpy.ops.mesh.primitive_cube_add(location=(midpoint.x,midpoint.y,(z0+z1)/2))
    obj=bpy.context.object; obj.name=name
    obj.dimensions=(length+MIN_NECK_MM*1.8,MIN_NECK_MM,RAIL_HEIGHT_MM)
    obj.rotation_euler.z=math.atan2(end.y-start.y,end.x-start.x)
    bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    return obj


def pad(name,point):
    bpy.ops.mesh.primitive_cylinder_add(vertices=24,radius=MIN_NECK_MM,depth=RAIL_HEIGHT_MM,location=(point.x,point.y,point.z-0.03+RAIL_HEIGHT_MM/2))
    obj=bpy.context.object; obj.name=name; return obj


def join(items,name):
    bpy.ops.object.select_all(action="DESELECT")
    for item in items: item.select_set(True)
    bpy.context.view_layer.objects.active=items[0]; bpy.ops.object.join()
    obj=bpy.context.object; obj.name=name; return obj


def voxel(obj):
    bpy.context.view_layer.objects.active=obj; obj.select_set(True)
    obj.data.remesh_voxel_size=VOXEL_MM; obj.data.remesh_voxel_adaptivity=0.0
    obj.data.use_remesh_fix_poles=True; bpy.ops.object.voxel_remesh()


def export(path,obj):
    bpy.ops.object.select_all(action="DESELECT"); obj.select_set(True); bpy.context.view_layer.objects.active=obj
    bpy.ops.wm.stl_export(filepath=str(path),export_selected_objects=True,ascii_format=False)


def main():
    args=sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else []
    if len(args)!=3: raise SystemExit("Expected OUTPUT.blend OUTPUT.stl REPORT.json")
    output,stl,report=map(Path,args)
    water=bpy.data.objects.get("SYS01_Water_Blue_SeparatePrint")
    if water is None: raise RuntimeError("Missing separate-print water object")
    before=groups(water); candidates=nearest_edges(before); selected=[]; merged=set()
    # Join only short, physically local gaps.  Stop at two installable pieces;
    # do not create long artificial waterways merely to obtain component=1.
    for distance,left,right,start,end in candidates:
        if len(before)-len(selected)<=TARGET_COMPONENTS: break
        if distance>MAX_LOCAL_GAP_MM: break
        if (left,right) in merged: continue
        selected.append((distance,left,right,start,end)); merged.add((left,right))
    rails=[rail(f"WaterLocalRail_{i:02d}",item[3],item[4]) for i,item in enumerate(selected,1)]
    pads=[pad(f"WaterLocalPad_{i:02d}_{side}",point) for i,item in enumerate(selected,1) for side,point in enumerate(item[3:],1)]
    reinforced=join([water,*rails,*pads],"SYS01_Water_Blue_Reinforced") if rails else water
    if rails: voxel(reinforced)
    after=len(groups(reinforced))
    if after>TARGET_COMPONENTS:
        raise RuntimeError(f"Water remains {after} components; local gaps={[round(x[0],3) for x in candidates]}")
    reinforced["SYS01_geometry"]="reinforced_water_insert"
    output.parent.mkdir(parents=True,exist_ok=True); stl.parent.mkdir(parents=True,exist_ok=True); report.parent.mkdir(parents=True,exist_ok=True)
    export(stl,reinforced); bpy.ops.wm.save_as_mainfile(filepath=str(output))
    payload={"status":"PASS","components_before":len(before),"components_after":after,"strategy":"local_buried_water_corridor_rails","parameters_mm":{"minimum_neck":MIN_NECK_MM,"rail_height":RAIL_HEIGHT_MM,"maximum_local_gap":MAX_LOCAL_GAP_MM,"voxel":VOXEL_MM},"local_connections":[{"gap_mm":round(x[0],3),"from":x[1],"to":x[2]} for x in selected],"all_nearest_gaps_mm":[round(x[0],3) for x in candidates]}
    report.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("WATER_REINFORCE="+json.dumps(payload,ensure_ascii=False))


if __name__=="__main__": main()
