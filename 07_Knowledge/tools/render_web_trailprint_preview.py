#!/usr/bin/env python3
"""Render multi-angle TrailPrint3D Web previews with a reference base."""
import json, math, sys
from pathlib import Path
import bpy
from mathutils import Vector

args=sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else []
if len(args)!=3: raise SystemExit("Expected OUTPUT.blend REPORT.json PREVIEW.png")
output,report_path,preview=map(Path,args)

def points(obj):
    if obj.type=="MESH": return [obj.matrix_world@v.co for v in obj.data.vertices]
    if obj.type=="CURVE": return [obj.matrix_world@p.co.xyz for spline in obj.data.splines for p in spline.points]
    return []

objects=[]
for obj in list(bpy.context.scene.objects):
    if obj.type in {"CAMERA","LIGHT"} or obj.name=="Cube": bpy.data.objects.remove(obj,do_unlink=True); continue
    if obj.type in {"MESH","CURVE"} and points(obj): objects.append(obj)
if not objects: raise RuntimeError("TrailPrint3D scene has no renderable model")

all_points=[p for obj in objects for p in points(obj)]
lo=Vector((min(p.x for p in all_points),min(p.y for p in all_points),min(p.z for p in all_points))); hi=Vector((max(p.x for p in all_points),max(p.y for p in all_points),max(p.z for p in all_points)))
offset=Vector((-(lo.x+hi.x)/2,-(lo.y+hi.y)/2,-lo.z))
for obj in objects: obj.location+=offset
bpy.context.view_layer.update()

for obj in objects:
    role=(obj.name+str(obj.get("Object type",""))).lower()
    obj.color=(0.145,0.38,0.75,1) if "water" in role else ((0.83,0.045,0.025,1) if "trail" in role else (0.25,0.50,0.20,1))

# Reference-only base envelope: useful for assembly visualization, not exported as a final print part.
bpy.ops.mesh.primitive_cylinder_add(vertices=6,radius=55.0,depth=6.0,location=(0,0,-3.0),rotation=(0,0,math.pi/6))
base=bpy.context.object; base.name="WEB_BASE_REFERENCE_NOT_PRINT_FINAL"; base.color=(0.34,0.37,0.39,1); base["preview_role"]="reference_base_envelope"; objects.append(base)
bpy.ops.mesh.primitive_cylinder_add(vertices=6,radius=51.5,depth=.6,location=(0,0,-.3),rotation=(0,0,math.pi/6))
rim=bpy.context.object; rim.name="WEB_BASE_BROWN_INSET_REFERENCE"; rim.color=(0.42,0.25,0.12,1); rim["preview_role"]="reference_brown_detail"; objects.append(rim)
bpy.context.view_layer.update()

# Top-ring text uses the same Chinese-safe font strategy as the printable base.
job_path=output.parents[1]/"job.json"; job=json.loads(job_path.read_text(encoding="utf-8")) if job_path.exists() else {}
font_path=Path("/System/Library/Fonts/Hiragino Sans GB.ttc")
font=bpy.data.fonts.load(str(font_path)) if font_path.exists() else None
title=str(job.get("customer_input",{}).get("title") or job.get("route",{}).get("name") or "徒步纪念")
date=str(job.get("customer_input",{}).get("display_date") or "").replace("-",".")
route_facts=job.get("route",{}).get("web_facts",{}); distance=float(route_facts.get("distance_km",9.5)) if isinstance(route_facts,dict) else 9.5; distance_text=f"{distance:.1f} KM"

def add_label(name,body,location,rotation_z,size=2.35):
    bpy.ops.object.text_add(location=location,rotation=(0,0,rotation_z)); obj=bpy.context.object; obj.name=name; obj.data.body=body; obj.data.align_x="CENTER"; obj.data.align_y="CENTER"; obj.data.size=size; obj.data.extrude=.12; obj.data.bevel_depth=.025; obj.color=(0.42,0.25,0.12,1)
    if font: obj.data.font=font
    obj["preview_role"]="reference_base_text"; return obj

labels=[add_label("WEB_LABEL_TITLE_REFERENCE",title[:8],(0,-45.47,.10),0,2.2),add_label("WEB_LABEL_DATE_REFERENCE",date,(-39.38,-22.74,.10),-math.pi/3,1.75),add_label("WEB_LABEL_DISTANCE_REFERENCE",distance_text,(39.38,-22.74,.10),math.pi/3,1.80)]
bpy.context.view_layer.update()

model_points=[p for obj in objects for p in points(obj)]; lo2=Vector((min(p.x for p in model_points),min(p.y for p in model_points),min(p.z for p in model_points))); hi2=Vector((max(p.x for p in model_points),max(p.y for p in model_points),max(p.z for p in model_points))); center=(lo2+hi2)/2; span=max(hi2.x-lo2.x,hi2.y-lo2.y,1)
bpy.ops.object.camera_add(); camera=bpy.context.object; camera.name="Web多机位预览"; camera.data.type="ORTHO"; bpy.context.scene.camera=camera

scene=bpy.context.scene; scene.render.engine="BLENDER_WORKBENCH"; scene.display.shading.light="STUDIO"; scene.display.shading.color_type="OBJECT"; scene.display.shading.show_cavity=True; scene.display.shading.cavity_type="WORLD"; scene.render.resolution_x=1200; scene.render.resolution_y=900; scene.render.resolution_percentage=100; scene.render.image_settings.file_format="PNG"; scene.render.film_transparent=False; scene.world.color=(0.035,0.055,0.042)

def render(path,location,target,scale):
    camera.location=location; camera.data.ortho_scale=scale; camera.rotation_euler=(Vector(target)-camera.location).to_track_quat("-Z","Y").to_euler(); scene.render.filepath=str(path); bpy.ops.render.render(write_still=True)

preview.parent.mkdir(parents=True,exist_ok=True)
top=preview.with_name(preview.stem+"_top.png"); side=preview.with_name(preview.stem+"_side.png")
render(preview,(span*1.10,-span*1.30,span*.92+hi2.z),center,span*1.55)
render(top,(0,0,span*2.2+hi2.z),(0,0,center.z),span*1.28)
render(side,(0,-span*2.0,span*.38),(0,0,center.z*.65),span*1.38)

output.parent.mkdir(parents=True,exist_ok=True); bpy.ops.wm.save_as_mainfile(filepath=str(output))
report={"objects":[o.name for o in objects]+[o.name for o in labels],"source_bounds":{"min":list(lo),"max":list(hi)},"centering_offset":list(offset),"preview_bounds":{"min":list(lo2),"max":list(hi2)},"base":{"type":"reference_envelope","reference_text":[title[:8],date,distance_text],"placement_method":"parallel_edge_midband","final_logo":False},"views":{"assembled":"blender_preview.png","top":"blender_preview_top.png","side":"blender_preview_side.png"},"coverage":{"terrain":"geometry","base":"reference_with_text","trail":"geometry","water":"geometry","one_plate":"pending_full_pipeline","blend":"preview_ready"}}
report_path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8"); print("WEB_PREVIEW="+json.dumps(report,ensure_ascii=False))
