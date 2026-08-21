#!/usr/bin/env python3
"""Classify a GPX and prepare a derived print-scale GPX for non-local scenes."""
from __future__ import annotations
import json, math, sys, xml.etree.ElementTree as ET
from pathlib import Path

EARTH_KM=6371.0088
def write_json_atomic(path,payload):
    temporary=path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    temporary.replace(path)
def haversine(a,b):
    p1,p2=map(math.radians,(a[0],b[0])); dp=p2-p1; dl=math.radians(b[1]-a[1]); q=math.sin(dp/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2*EARTH_KM*math.asin(math.sqrt(q))
def xy_km(lat,lon,ref_lat): return (EARTH_KM*math.radians(lon)*math.cos(math.radians(ref_lat)),EARTH_KM*math.radians(lat))
def point_line_distance(p,a,b):
    dx,dy=b[0]-a[0],b[1]-a[1]
    if dx==dy==0: return math.hypot(p[0]-a[0],p[1]-a[1])
    t=max(0,min(1,((p[0]-a[0])*dx+(p[1]-a[1])*dy)/(dx*dx+dy*dy)))
    return math.hypot(p[0]-(a[0]+t*dx),p[1]-(a[1]+t*dy))
def rdp_indices(points,tolerance):
    if len(points)<=2:return {0,len(points)-1}
    keep={0,len(points)-1}; stack=[(0,len(points)-1)]
    while stack:
        first,last=stack.pop(); farthest=-1; index=None
        for i in range(first+1,last):
            distance=point_line_distance(points[i],points[first],points[last])
            if distance>farthest:farthest,index=distance,i
        if index is not None and farthest>tolerance:keep.add(index);stack.extend(((first,index),(index,last)))
    return keep
def analyze(root):
    segments=[]
    for segment in root.iter():
        if segment.tag.rsplit('}',1)[-1]=='trkseg':
            points=[p for p in segment if p.tag.rsplit('}',1)[-1]=='trkpt']
            if points:segments.append(points)
    flat=[p for segment in segments for p in segment]
    if len(flat)<2:raise ValueError('GPX must contain at least two track points')
    coords=[(float(p.attrib['lat']),float(p.attrib['lon'])) for p in flat]
    distance=sum(haversine(a,b) for segment in segments for a,b in zip([(float(p.attrib['lat']),float(p.attrib['lon'])) for p in segment],[(float(p.attrib['lat']),float(p.attrib['lon'])) for p in segment][1:]))
    south,north=min(p[0] for p in coords),max(p[0] for p in coords);west,east=min(p[1] for p in coords),max(p[1] for p in coords);mid_lat=(south+north)/2;mid_lon=(west+east)/2
    ew=haversine((mid_lat,west),(mid_lat,east));ns=haversine((south,mid_lon),(north,mid_lon));span=max(ew,ns);aspect=span/max(min(ew,ns),.001)
    return segments,{"points":len(flat),"segments":len(segments),"distance_km":round(distance,3),"span_ew_km":round(ew,3),"span_ns_km":round(ns,3),"max_span_km":round(span,3),"aspect_ratio":round(aspect,3),"bbox_wgs84":{"west":west,"south":south,"east":east,"north":north}}
def classify(facts):
    span,distance=facts['max_span_km'],facts['distance_km']
    if span<=30 and distance<=100:return 'LOCAL_HIKE'
    if span<=100 and distance<=200:return 'LONG_HIKE'
    if span<=500:return 'REGIONAL_OVERVIEW'
    return 'MULTI_TILE_REQUIRED'
def simplify_gpx(root,segments,output,tolerance):
    ref_lat=sum(float(p.attrib['lat']) for s in segments for p in s)/sum(map(len,segments));kept=0
    for segment in segments:
        trackpoints=[p for p in segment if p.tag.rsplit('}',1)[-1]=='trkpt'];projected=[xy_km(float(p.attrib['lat']),float(p.attrib['lon']),ref_lat) for p in trackpoints];keep=rdp_indices(projected,tolerance)
        for index,point in enumerate(trackpoints):
            if index not in keep:segment.remove(point)
        kept+=len(keep)
    ET.ElementTree(root).write(output,encoding='utf-8',xml_declaration=True);return kept
def configure(job_dir:Path):
    job_path=job_dir/'job.json';job=json.loads(job_path.read_text(encoding='utf-8'));source=job_dir/job['route']['gpx'];root=ET.parse(source).getroot();segments,facts=analyze(root);mode=classify(facts)
    profile={"schema_version":"1.0","mode":mode,"facts":facts,"original_parameters_preserved":mode=='LOCAL_HIKE',"model_gpx":job['route']['gpx'],"model_points":facts['points'],"warnings":[]};engineering=job.setdefault('engineering',{})
    if mode!='LOCAL_HIKE':
        target=float(engineering.get('object_size_mm',100));tolerance=max(.02,facts['max_span_km']*.18/target);model=job_dir/'work/model_route.gpx';model.parent.mkdir(parents=True,exist_ok=True)
        profile.update({"model_points":simplify_gpx(root,segments,model,tolerance),"model_gpx":"work/model_route.gpx","simplification_tolerance_km":round(tolerance,4)});job['route']['model_gpx']='work/model_route.gpx'
        if mode=='LONG_HIKE':
            engineering['elevation_scale']=max(float(engineering.get('elevation_scale',1.8)),2.2);engineering['path_thickness_mm']=max(float(engineering.get('path_thickness_mm',1.6)),1.7);engineering.setdefault('trailprint_water',{})['small_rivers']=False
        elif mode=='REGIONAL_OVERVIEW':
            engineering['terrain_resolution']=min(int(engineering.get('terrain_resolution',8)),6);engineering['elevation_scale']=max(float(engineering.get('elevation_scale',1.8)),3.0);engineering['path_thickness_mm']=max(float(engineering.get('path_thickness_mm',1.6)),1.8)
            water=engineering.setdefault('trailprint_water',{});water['small_rivers']=False;water['include_ocean']=False;engineering['water_policy']='regional_route_corridor_major_water';engineering['water_keep_distance_m']=5000;engineering['water_simplify_distance_m']=10000;profile['warnings'].append('区域概览模式沿轨迹走廊获取真实主要水系；小河与海岸线不纳入。')
        else:profile['warnings'].append('跨度超过 500 km，建议分块；本次仅生成单块概览候选。')
    job['route_profile']=profile;write_json_atomic(job_path,job);report=job_dir/'review/route_profile.json';report.parent.mkdir(parents=True,exist_ok=True);write_json_atomic(report,profile);return profile
if __name__=='__main__':print(json.dumps(configure(Path(sys.argv[1]).resolve()),ensure_ascii=False))
