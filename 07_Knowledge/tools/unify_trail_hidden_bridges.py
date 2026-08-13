#!/usr/bin/env python3
"""Make a trail insert one body using its preserved route-following inner core."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector
from mathutils.kdtree import KDTree

RAIL_WIDTH_MM = 1.35
RAIL_HEIGHT_MM = 0.55
CLEARANCE_MM = 0.20
REMESH_VOXEL_MM = 0.055
MAX_LOCAL_ENDPOINT_BRIDGE_MM = 2.0


def connected_groups(obj):
    mesh=bmesh.new(); mesh.from_mesh(obj.data); remaining=set(mesh.verts); groups=[]
    while remaining:
        seed=remaining.pop(); group={seed}; queue=[seed]
        while queue:
            vertex=queue.pop()
            for edge in vertex.link_edges:
                other=edge.other_vert(vertex)
                if other in remaining: remaining.remove(other); group.add(other); queue.append(other)
        groups.append(group)
    result=[]
    for group in groups:
        points=[obj.matrix_world@v.co for v in group]
        bottom=min(p.z for p in points)
        candidates=[p for p in points if p.z <= bottom+0.08]
        center=Vector((sum(p.x for p in candidates)/len(candidates),sum(p.y for p in candidates)/len(candidates),bottom))
        anchor=min(candidates,key=lambda p:(p.x-center.x)**2+(p.y-center.y)**2)
        result.append({"vertices":len(group),"anchor":Vector((anchor.x,anchor.y,bottom)),"points":points})
    mesh.free(); return result


def mst(nodes):
    connected={0}; edges=[]
    while len(connected)<len(nodes):
        best=None
        for left in connected:
            for right in range(len(nodes)):
                if right in connected: continue
                distance=(nodes[left]["anchor"].xy-nodes[right]["anchor"].xy).length
                if best is None or distance<best[0]: best=(distance,left,right)
        edges.append(best); connected.add(best[2])
    return edges


def nearest_surface_tree(nodes):
    """Prim tree using actual shell-to-shell nearest points, not centroids."""
    connected={0}; edges=[]
    while len(connected)<len(nodes):
        best=None
        for left in connected:
            tree=KDTree(len(nodes[left]["points"]))
            for index,point in enumerate(nodes[left]["points"]): tree.insert(point,index)
            tree.balance()
            for right in range(len(nodes)):
                if right in connected: continue
                for point in nodes[right]["points"]:
                    nearest,_,distance=tree.find(point)
                    if best is None or distance<best[0]: best=(distance,left,right,nearest.copy(),point.copy())
        edges.append(best); connected.add(best[2])
    return edges


def rail(name,start,end,width=RAIL_WIDTH_MM,height=RAIL_HEIGHT_MM):
    midpoint=(start+end)/2; length=(end.xy-start.xy).length
    z0=min(start.z,end.z)-0.02; z1=z0+height
    bpy.ops.mesh.primitive_cube_add(location=(midpoint.x,midpoint.y,(z0+z1)/2))
    obj=bpy.context.object; obj.name=name; obj.dimensions=(length+width*1.8,width,z1-z0)
    obj.rotation_euler.z=math.atan2(end.y-start.y,end.x-start.x)
    bpy.ops.object.transform_apply(location=False,rotation=False,scale=True); return obj


def pad(name,point):
    z0=point.z-0.02
    bpy.ops.mesh.primitive_cylinder_add(vertices=24,radius=RAIL_WIDTH_MM,depth=RAIL_HEIGHT_MM,location=(point.x,point.y,z0+RAIL_HEIGHT_MM/2))
    obj=bpy.context.object; obj.name=name; return obj


def join(objects,name):
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects: obj.select_set(True)
    bpy.context.view_layer.objects.active=objects[0]; bpy.ops.object.join(); result=bpy.context.object; result.name=name; return result


def voxel_union(obj):
    bpy.ops.object.select_all(action="DESELECT"); obj.select_set(True); bpy.context.view_layer.objects.active=obj
    obj.data.remesh_voxel_size=REMESH_VOXEL_MM; obj.data.remesh_voxel_adaptivity=0.0; obj.data.use_remesh_fix_poles=True
    bpy.ops.object.voxel_remesh()


def expanded(source):
    result=source.copy(); result.data=source.data.copy(); bpy.context.scene.collection.objects.link(result)
    mesh=bmesh.new(); mesh.from_mesh(result.data); mesh.normal_update()
    for vertex in mesh.verts: vertex.co += vertex.normal*CLEARANCE_MM
    bmesh.ops.recalc_face_normals(mesh,faces=mesh.faces); mesh.to_mesh(result.data); mesh.free(); result.data.update(); return result


def cut(target,cutter):
    modifier=target.modifiers.new("Trail hidden bridge groove","BOOLEAN"); modifier.operation="DIFFERENCE"; modifier.solver="MANIFOLD"; modifier.object=cutter
    bpy.context.view_layer.objects.active=target; target.select_set(True); bpy.ops.object.modifier_apply(modifier=modifier.name); target.select_set(False)


def count(obj): return len(connected_groups(obj))


def main():
    args=sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else []
    if len(args)!=2: raise SystemExit("Expected OUTPUT.blend REPORT.json")
    output,report=map(Path,args)
    trail=next(o for o in bpy.context.scene.objects if o.get("S03_geometry")=="trail_insert")
    terrain=next(o for o in bpy.context.scene.objects if o.get("Object type")=="MAP")
    waters=[o for o in bpy.context.scene.objects if o.get("Object type") in {"WATER","OCEAN"} or o.get("S02_geometry") in {"stream_ribbon","water_area"}]
    nodes=connected_groups(trail); edges=mst(nodes) if len(nodes)>1 else []
    core=next((o for o in bpy.context.scene.objects if o.get("S03_geometry")=="trail_continuity_core"),None)
    if core is None:
        raise RuntimeError("Missing preserved trail continuity core; refuse long straight bridge fallback")
    source_core_name=core.name
    source_core_radius=round(float(core.data.bevel_depth),3)
    bpy.context.view_layer.objects.active=core; core.select_set(True); bpy.ops.object.convert(target="MESH"); core=bpy.context.object
    core.name="Trail_Continuity_Core_Mesh"
    unified=join([trail,core],"Trail_Red_OnePiece_RouteCore")
    voxel_union(unified)
    after=count(unified)
    local_bridge_lengths=[]
    if after>1:
        remaining=connected_groups(unified); local_edges=nearest_surface_tree(remaining)
        if any(edge[0]>MAX_LOCAL_ENDPOINT_BRIDGE_MM for edge in local_edges):
            raise RuntimeError(f"Route core left non-local gaps: {[round(item[0],3) for item in local_edges]}")
        local_rails=[rail(f"EndpointLocalBridge_{i:02d}",start,end,width=RAIL_WIDTH_MM,height=RAIL_HEIGHT_MM) for i,(distance,a,b,start,end) in enumerate(local_edges,1)]
        local_pads=[pad(f"EndpointLocalPad_{i:02d}_{side}",point) for i,edge in enumerate(local_edges,1) for side,point in enumerate(edge[3:],1)]
        unified=join([unified,*local_rails,*local_pads],"Trail_Red_OnePiece_RouteCore_Endpoints")
        voxel_union(unified); after=count(unified); local_bridge_lengths=[round(item[0],3) for item in local_edges]
    if after!=1: raise RuntimeError(f"Trail remains disconnected: {after}")
    unified["S03_geometry"]="trail_insert"; unified["continuity_method"]="preserved_route_following_inner_core"
    payload={"status":"PASS","components_before":len(nodes),"components_after":after,"method":"preserved_route_following_structural_spine","straight_cross_terrain_bridges":0,"endpoint_local_bridges_mm":local_bridge_lengths,"source_core":source_core_name,"parameters_mm":{"core_radius":source_core_radius,"core_diameter":round(source_core_radius*2,3),"local_bridge_width":RAIL_WIDTH_MM,"local_bridge_height":RAIL_HEIGHT_MM,"voxel":REMESH_VOXEL_MM,"max_endpoint_local_bridge":MAX_LOCAL_ENDPOINT_BRIDGE_MM}}
    output.parent.mkdir(parents=True,exist_ok=True); report.parent.mkdir(parents=True,exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(output)); report.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("TRAIL_UNIFY="+json.dumps(payload,ensure_ascii=False))


if __name__=="__main__": main()
