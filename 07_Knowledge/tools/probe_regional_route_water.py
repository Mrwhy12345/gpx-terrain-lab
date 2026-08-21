#!/usr/bin/env python3
"""Fetch real major OSM water along a regional GPX corridor and select <=5 features."""
from __future__ import annotations
import argparse, json, math, socket, time, urllib.error, urllib.parse, urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

EARTH_M=6371008.8
SERVERS=("https://overpass-api.de/api/interpreter","https://overpass.kumi.systems/api/interpreter","https://overpass.private.coffee/api/interpreter")
def project(lon,lat,lon0,lat0):return (math.radians(lon-lon0)*EARTH_M*math.cos(math.radians(lat0)),math.radians(lat-lat0)*EARTH_M)
def point_segment_distance(p,a,b):
    dx,dy=b[0]-a[0],b[1]-a[1]
    if dx==dy==0:return math.dist(p,a)
    t=max(0,min(1,((p[0]-a[0])*dx+(p[1]-a[1])*dy)/(dx*dx+dy*dy)))
    return math.dist(p,(a[0]+t*dx,a[1]+t*dy))
def request(query, deadline):
    payload=urllib.parse.urlencode({'data':query}).encode();errors=[]
    for server in SERVERS:
        remaining=deadline-time.monotonic()
        if remaining<=0:break
        req=urllib.request.Request(server,data=payload,headers={'User-Agent':'GPX-Terrain-Lab/1.1 regional-water','Content-Type':'application/x-www-form-urlencoded'},method='POST')
        try:
            with urllib.request.urlopen(req,timeout=max(2,min(10,remaining))) as response:return server,json.loads(response.read())
        except (urllib.error.HTTPError,urllib.error.URLError,TimeoutError,socket.timeout,json.JSONDecodeError) as exc:
            errors.append(f'{server}: {type(exc).__name__}: {exc}');time.sleep(1)
    raise RuntimeError('; '.join(errors))
def feature(item):
    coords=[[p['lon'],p['lat']] for p in item.get('geometry',[]) if 'lon' in p and 'lat' in p]
    if len(coords)<2:return None
    tags=item.get('tags',{});is_area=len(coords)>=4 and coords[0]==coords[-1] and (tags.get('natural')=='water' or 'water' in tags or tags.get('landuse')=='reservoir')
    return {'type':'Feature','properties':{'osm_type':'way','osm_id':item.get('id'),**tags},'geometry':{'type':'Polygon' if is_area else 'LineString','coordinates':[coords] if is_area else coords}}
def main():
    parser=argparse.ArgumentParser();parser.add_argument('job_dir',type=Path);parser.add_argument('--max-components',type=int,default=5);args=parser.parse_args();job_dir=args.job_dir.resolve()
    job=json.loads((job_dir/'job.json').read_text());gpx=job_dir/job['route'].get('model_gpx',job['route']['gpx']);root=ET.parse(gpx).getroot();track=[(float(p.attrib['lon']),float(p.attrib['lat'])) for p in root.iter() if p.tag.rsplit('}',1)[-1]=='trkpt']
    if len(track)<2:raise SystemExit('Regional GPX has fewer than two points')
    # Sequential windows avoid one huge Overpass request. Consecutive windows overlap at endpoints.
    sample_count=min(24,max(8,math.ceil(job['route_profile']['facts']['max_span_km']/18)));step=max(1,math.ceil(len(track)/sample_count));margin=.025
    raw={};requests=[];errors=[];deadline=time.monotonic()+75
    sampled=track[::step]
    if sampled[-1] != track[-1]:sampled.append(track[-1])
    for lon,lat in sampled:
        if time.monotonic()>=deadline:break
        west,east=lon-margin,lon+margin;south,north=lat-margin,lat+margin;box=f'{south},{west},{north},{east}'
        query=f'''[out:json][timeout:35];way["waterway"~"^(river|canal)$"]({box});out tags geom;'''
        try:server,data=request(query,deadline)
        except RuntimeError as exc:
            errors.append(str(exc));continue
        requests.append({'bbox':[south,west,north,east],'server':server,'elements':len(data.get('elements',[]))})
        for item in data.get('elements',[]):raw[(item.get('type'),item.get('id'))]=item
    features=[value for item in raw.values() if (value:=feature(item))]
    lon0=sum(p[0] for p in track)/len(track);lat0=sum(p[1] for p in track)/len(track);route=[project(*p,lon0,lat0) for p in track];segments=list(zip(route,route[1:]));keep=float(job['engineering'].get('water_keep_distance_m',5000));simplify=float(job['engineering'].get('water_simplify_distance_m',10000))
    ranked=[]
    for item in features:
        coords=item['geometry']['coordinates'][0] if item['geometry']['type']=='Polygon' else item['geometry']['coordinates'];points=[project(*p,lon0,lat0) for p in coords];distance,segment_index=min((point_segment_distance(p,a,b),index) for p in points for index,(a,b) in enumerate(segments));item['properties']['distance_to_route_m']=round(distance,1);item['properties']['route_fraction']=round(segment_index/max(1,len(segments)-1),4);item['properties']['print_decision']='keep' if distance<=keep else 'simplify' if distance<=simplify else 'exclude';ranked.append(item)
    ranked.sort(key=lambda x:(x['properties']['distance_to_route_m'],0 if x['geometry']['type']=='LineString' else 1));eligible=[x for x in ranked if x['properties']['print_decision']!='exclude'];selected=[]
    # Prefer one real feature from each fifth of the route, then fill remaining slots by proximity.
    for route_bin in range(args.max_components):
        candidates=[x for x in eligible if min(args.max_components-1,int(x['properties']['route_fraction']*args.max_components))==route_bin]
        if candidates:selected.append(candidates[0])
    for item in eligible:
        if len(selected)>=args.max_components:break
        if item not in selected:selected.append(item)
    coverage_ratio=len(requests)/len(sampled)
    report={'policy':'real OSM major water along adaptive regional route corridor','total_deadline_seconds':75,'sample_window_count':len(sampled),'successful_window_count':len(requests),'window_coverage_ratio':round(coverage_ratio,3),'minimum_release_coverage_ratio':0.5,'requests':requests,'request_error_count':len(errors),'request_error_samples':errors[:3],'raw_unique_count':len(raw),'candidate_count':len(ranked),'selected_count':len(selected),'selected':[{'osm_id':x['properties'].get('osm_id'),'name':x['properties'].get('name'),'kind':x['geometry']['type'],'distance_to_route_m':x['properties']['distance_to_route_m'],'route_fraction':x['properties']['route_fraction']} for x in selected]}
    (job_dir/'review/regional_water.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    if coverage_ratio<0.5:raise RuntimeError('Regional OSM water corridor coverage is below 50%; see review/regional_water.json')
    if not selected:raise RuntimeError('No real major OSM water found within the regional route corridor; see review/regional_water.json')
    output=job_dir/'work/water_selected';output.mkdir(parents=True,exist_ok=True)
    for kind,name in (('LineString','water_lines.geojson'),('Polygon','water_polygons.geojson')):
        (output/name).write_text(json.dumps({'type':'FeatureCollection','features':[x for x in selected if x['geometry']['type']==kind]},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))
if __name__=='__main__':main()
