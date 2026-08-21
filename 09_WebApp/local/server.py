#!/usr/bin/env python3
"""Async API/asset server; combined static mode remains available for rollback."""
from __future__ import annotations
import json, mimetypes, os, re, traceback
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlsplit
from async_jobs import (BASE_ALGORITHM, BLENDER, FONT_ALGORITHM, JOBS_ROOT,
    PIPELINE_VERSION, QUEUE, create_preview_job, status_path, update_status)

WEB_ROOT=Path(__file__).resolve().parent
SERVER_ROLE=os.getenv("GPX_SERVER_ROLE","combined")
HOST=os.getenv("GPX_BACKEND_HOST","127.0.0.1")
PORT=int(os.getenv("GPX_BACKEND_PORT","4174" if SERVER_ROLE=="backend" else "4173"))
ALLOWED_ORIGINS={v.strip() for v in os.getenv("GPX_ALLOWED_ORIGINS","http://127.0.0.1:4173,http://localhost:4173").split(",") if v.strip()}
def valid_job_id(value): return bool(re.fullmatch(r"WEB_[0-9A-Za-z\u4e00-\u9fff_-]+",value or ""))
def valid_client_id(value): return bool(re.fullmatch(r"[0-9a-f-]{36}",value or ""))
def owns_job(job_id,client_id):
    if not valid_job_id(job_id) or not valid_client_id(client_id): return False
    try:
        job=json.loads((JOBS_ROOT/job_id/"job.json").read_text(encoding="utf-8"))
        return job.get("anonymous_client_id")==client_id
    except (OSError,ValueError,json.JSONDecodeError): return False
def queue_snapshot(job_id=None,current=None):
    pending=[]
    for path in JOBS_ROOT.glob("WEB_*/review/web_task_status.json"):
        try:
            item=json.loads(path.read_text(encoding="utf-8"))
            if item.get("state") in {"QUEUED","RUNNING"}: pending.append(item)
        except (OSError,ValueError,json.JSONDecodeError): pass
    pending.sort(key=lambda item:(item.get("created_at",item.get("updated_at","")),item.get("job_id","")))
    running=[item for item in pending if item.get("state")=="RUNNING"]
    queued=[item for item in pending if item.get("state")=="QUEUED"]
    stage_counts={}
    for item in pending:
        stage=item.get("stage") or "unknown"
        stage_counts[stage]=stage_counts.get(stage,0)+1
    result={"worker_capacity":1,"running_count":len(running),"queued_count":len(queued),"stage_counts":stage_counts}
    if job_id and current:
        ahead=sum(1 for item in pending if item.get("job_id")!=job_id and (item.get("state")=="RUNNING" or pending.index(item)<next((i for i,x in enumerate(pending) if x.get("job_id")==job_id),len(pending))))
        result.update({"ahead":ahead,"position":0 if current.get("state")=="RUNNING" else ahead+1})
        preview_steps=[("route_profile","A1 GPX 分析"),("trailprint3d","A2 地形与水系"),("blender_preview","A3 三机位仿真"),("preview","A 工程确认")]
        final_steps=[("preview","A 工程仿真"),("production","B1 最终制造"),("packaging","B2 Bambu QA"),("complete","B 交付完成")]
        steps=final_steps if current.get("request")=="final" else preview_steps
        order=[key for key,_ in steps]; active=current.get("stage"); active_index=order.index(active) if active in order else -1
        result["steps"]=[{"key":key,"label":label,"state":"done" if i<active_index or current.get("state") in {"PREVIEW_READY","FINAL_READY"} else "active" if i==active_index else "pending"} for i,(key,label) in enumerate(steps)]
    return result

class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*args,**kwargs): super().__init__(*args,directory=str(WEB_ROOT),**kwargs)
    def cors(self):
        origin=self.headers.get("Origin")
        if origin in ALLOWED_ORIGINS:
            self.send_header("Access-Control-Allow-Origin",origin); self.send_header("Vary","Origin")
    def send_json(self,status,payload):
        data=json.dumps(payload,ensure_ascii=False).encode(); self.send_response(status)
        self.send_header("Content-Type","application/json; charset=utf-8"); self.send_header("Content-Length",str(len(data))); self.cors(); self.end_headers(); self.wfile.write(data)
    def send_file(self,target,download=False):
        self.send_response(200); self.send_header("Content-Type",mimetypes.guess_type(target.name)[0] or "application/octet-stream"); self.send_header("Content-Length",str(target.stat().st_size))
        if download: self.send_header("Content-Disposition",f"attachment; filename*=UTF-8''{quote(target.name)}")
        self.cors(); self.end_headers()
        with target.open("rb") as stream:
            while chunk:=stream.read(1024*1024): self.wfile.write(chunk)
    def read_json(self):
        length=int(self.headers.get("Content-Length","0"))
        if length<=0 or length>30_000_000: raise ValueError("请求大小无效")
        return json.loads(self.rfile.read(length))
    def do_OPTIONS(self):
        self.send_response(204); self.cors(); self.send_header("Access-Control-Allow-Headers","Content-Type"); self.send_header("Access-Control-Allow-Methods","GET, POST, OPTIONS"); self.end_headers()
    def do_GET(self):
        request_url=urlsplit(self.path); path=unquote(request_url.path); query=parse_qs(request_url.query)
        if path=="/api/health":
            self.send_json(200,{"ok":True,"blender":BLENDER.exists(),"mode":"async-worker","pipeline_version":PIPELINE_VERSION,"base_algorithm":BASE_ALGORITHM,"font_algorithm":FONT_ALGORITHM}); return
        if path=="/api/queue":
            self.send_json(200,{"ok":True,**queue_snapshot()}); return
        match=re.fullmatch(r"/api/anonymous-clients/([0-9a-f-]{36})/jobs",path)
        if match:
            jobs=[]
            for job_path in JOBS_ROOT.glob("WEB_*/job.json"):
                try:
                    job=json.loads(job_path.read_text(encoding="utf-8"))
                    if job.get("anonymous_client_id")!=match.group(1): continue
                    status_file=status_path(job_path.parent)
                    if not status_file.is_file(): continue
                    status=json.loads(status_file.read_text(encoding="utf-8"))
                    jobs.append({"job_id":job_path.parent.name,"title":job.get("route",{}).get("name","未命名路线"),"state":status.get("state"),"stage":status.get("stage"),"progress":status.get("progress",0),"message":status.get("message"),"created_at":status.get("created_at"),"updated_at":status.get("updated_at"),"request":status.get("request","preview"),"queue":queue_snapshot(job_path.parent.name,status)})
                except (OSError,ValueError,json.JSONDecodeError): pass
            jobs.sort(key=lambda item:item.get("created_at") or "",reverse=True)
            self.send_json(200,{"ok":True,"jobs":jobs[:50],"queue":queue_snapshot()}); return
        match=re.fullmatch(r"/api/jobs/(WEB_[0-9A-Za-z\u4e00-\u9fff_-]+)",path)
        if match:
            client_id=(query.get("client_id") or [""])[0]
            if not owns_job(match.group(1),client_id): self.send_json(404,{"ok":False,"error":"任务不存在或不属于当前匿名客户"}); return
            target=status_path(JOBS_ROOT/match.group(1))
            if not target.is_file(): self.send_json(404,{"ok":False,"error":"任务不存在"}); return
            current=json.loads(target.read_text(encoding="utf-8"))
            self.send_json(200,{"ok":True,**current,"queue":queue_snapshot(match.group(1),current)}); return
        if path=="/api/latest-final":
            client_id=(query.get("client_id") or [""])[0]
            if not valid_client_id(client_id): self.send_json(400,{"ok":False,"error":"缺少匿名客户标识"}); return
            for job_dir in sorted((p for p in JOBS_ROOT.glob("WEB_*") if p.is_dir()),reverse=True):
                manifest=job_dir/"review/final_manifest.json"
                job_file=job_dir/"job.json"
                if manifest.is_file() and job_file.is_file():
                    job=json.loads(job_file.read_text(encoding="utf-8"))
                    if job.get("anonymous_client_id")==client_id: self.send_json(200,{"ok":True,**json.loads(manifest.read_text(encoding="utf-8"))}); return
            self.send_json(404,{"ok":False,"error":"还没有可恢复的最终交付"}); return
        match=re.fullmatch(r"/generated/(WEB_[0-9A-Za-z\u4e00-\u9fff_-]+)/review/(blender_(?:preview|delivery)(?:_top|_side)?\.png)",path)
        if match:
            client_id=(query.get("client_id") or [""])[0]
            if not owns_job(match.group(1),client_id): self.send_error(404); return
            target=JOBS_ROOT/match.group(1)/"review"/match.group(2)
            if target.is_file(): self.send_file(target); return
            self.send_error(404); return
        match=re.fullmatch(r"/downloads/(WEB_[0-9A-Za-z\u4e00-\u9fff_-]+)/([^/]+)",path)
        if match and valid_job_id(match.group(1)):
            client_id=(query.get("client_id") or [""])[0]
            if not owns_job(match.group(1),client_id): self.send_error(404); return
            target=JOBS_ROOT/match.group(1)/"final"/Path(match.group(2)).name
            if target.is_file(): self.send_file(target,download=True); return
            self.send_error(404); return
        if SERVER_ROLE=="backend": self.send_error(404)
        else: super().do_GET()
    def do_POST(self):
        route=urlsplit(self.path).path
        if route not in {"/api/generate-preview","/api/finalize-job"}: self.send_error(404); return
        try:
            payload=self.read_json()
            if route=="/api/generate-preview":
                if not valid_client_id(payload.get("client_id")): self.send_json(400,{"ok":False,"error":"匿名客户标识无效"}); return
                job_id,created=create_preview_job(payload)
                if created: QUEUE.submit(job_id,"preview")
                else:
                    current=json.loads(status_path(JOBS_ROOT/job_id).read_text(encoding="utf-8"))
                    self.send_json(200,{"ok":True,"deduplicated":True,"job_id":job_id,"state":current.get("state"),"status_url":f"/api/jobs/{job_id}"}); return
            else:
                job_id=payload.get("job_id",""); client_id=payload.get("client_id",""); job_dir=JOBS_ROOT/job_id
                if not owns_job(job_id,client_id): self.send_json(404,{"ok":False,"error":"任务不存在或不属于当前匿名客户"}); return
                path=status_path(job_dir); current=json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
                if current.get("state")=="FINAL_READY": self.send_json(200,{"ok":True,**current}); return
                if current.get("request")=="final" and current.get("state") in {"QUEUED","RUNNING"}:
                    self.send_json(202,{"ok":True,"job_id":job_id,"state":current.get("state","QUEUED"),"status_url":f"/api/jobs/{job_id}"}); return
                update_status(job_dir,"QUEUED","final",1,"最终 5+1 已进入 Mac mini 队列",request="final")
                QUEUE.submit(job_id,"final")
            self.send_json(202,{"ok":True,"job_id":job_id,"state":"QUEUED","status_url":f"/api/jobs/{job_id}"})
        except Exception as exc:
            traceback.print_exc(); self.send_json(500,{"ok":False,"error":str(exc)})

if __name__=="__main__":
    QUEUE.resume(); print(f"GPX Terrain Lab {SERVER_ROLE}: http://{HOST}:{PORT}/")
    ThreadingHTTPServer((HOST,PORT),Handler).serve_forever()
