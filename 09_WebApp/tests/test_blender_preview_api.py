#!/usr/bin/env python3
"""End-to-end acceptance probe for the local Web -> Blender preview API."""
import json
import sys
import urllib.request
from pathlib import Path

gpx=Path(sys.argv[1])
payload={"gpx_text":gpx.read_text(encoding="utf-8"),"job":{"route":{"name":gpx.stem,"gpx":gpx.name,"facts":{}},"customer_input":{"display_date":"2026-07-12","title":gpx.stem},"engineering":{"source":"TrailPrint3D","shape":"HEXAGON","object_size_mm":100,"terrain_resolution":8,"elevation_scale":1.8,"path_thickness_mm":1.6,"path_scale":0.8,"single_color_trail":True,"element_mode":"SINGLECOLORMODE_REMESH","trailprint_water":{"water":True,"big_rivers":True,"small_rivers":True,"include_ocean":True,"river_width":1,"water_threshold":1,"min_island_area":2,"coastline_simplify":0.1,"merge_into_trailprint_terrain":True},"trailprint_elements":{"forests":False,"forest_threshold":10,"city_boundaries":False,"city_threshold":1}},"deliverables":{"three_mf_count":5,"blend_count":1,"final_dir":"final"}}}
request=urllib.request.Request("http://127.0.0.1:4173/api/generate-preview",data=json.dumps(payload,ensure_ascii=False).encode("utf-8"),headers={"Content-Type":"application/json"},method="POST")
with urllib.request.urlopen(request,timeout=2700) as response:
    result=json.load(response)
print(json.dumps(result,ensure_ascii=False,indent=2))
