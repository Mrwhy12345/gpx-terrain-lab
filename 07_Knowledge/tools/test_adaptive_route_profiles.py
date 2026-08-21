#!/usr/bin/env python3
"""Regression test: local hiking parameters stay byte-equivalent; regional route adapts."""
from __future__ import annotations
import argparse, json, shutil, tempfile
from pathlib import Path
from configure_route_scene import configure

BASE_ENGINEERING={"object_size_mm":100,"terrain_resolution":8,"elevation_scale":1.8,"path_thickness_mm":1.6,"trailprint_water":{"water":True,"big_rivers":True,"small_rivers":True,"include_ocean":True}}
def run_case(source:Path, expected:str):
    with tempfile.TemporaryDirectory(prefix='gpx_profile_') as temporary:
        job_dir=Path(temporary);(job_dir/'input').mkdir();shutil.copy2(source,job_dir/'input/route.gpx')
        job={"job_id":source.stem,"route":{"gpx":"input/route.gpx"},"engineering":json.loads(json.dumps(BASE_ENGINEERING))};(job_dir/'job.json').write_text(json.dumps(job),encoding='utf-8')
        profile=configure(job_dir);result=json.loads((job_dir/'job.json').read_text());actual=profile['mode'];preserved=result['engineering']==BASE_ENGINEERING if expected=='LOCAL_HIKE' else result['engineering']!=BASE_ENGINEERING
        return {"file":source.name,"expected":expected,"actual":actual,"parameters_check":preserved,"model_points":profile['model_points'],"source_points":profile['facts']['points'],"status":"PASS" if actual==expected and preserved else "FAIL"}
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--local',type=Path,action='append',default=[]);parser.add_argument('--regional',type=Path,action='append',default=[]);parser.add_argument('--report',type=Path);args=parser.parse_args()
    results=[run_case(path,'LOCAL_HIKE') for path in args.local]+[run_case(path,'REGIONAL_OVERVIEW') for path in args.regional];report={"suite":"adaptive route profile compatibility","status":"PASS" if results and all(x['status']=='PASS' for x in results) else "FAIL","cases":results}
    if args.report:args.report.parent.mkdir(parents=True,exist_ok=True);args.report.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False));raise SystemExit(0 if report['status']=='PASS' else 1)
if __name__=='__main__':main()
