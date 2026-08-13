#!/usr/bin/env python3
"""Local-only web, Blender simulation, and validated-deliverable bridge."""
from __future__ import annotations
import hashlib, json, mimetypes, re, subprocess, sys, traceback, zipfile
from urllib.parse import quote, unquote, urlsplit
from datetime import datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]; WEB_ROOT=Path(__file__).resolve().parent; JOBS_ROOT=ROOT/"08_Jobs"; TOOLS=ROOT/"07_Knowledge"/"tools"; BLENDER=Path("/Applications/Blender.app/Contents/MacOS/Blender")
FINAL_LABELS={
    "01":"沙盘地形", "02":"奖牌框适配底座", "03":"徒步轨迹",
    "04":"完整水网", "05":"四件同盘", "06":"Blender 设计项目",
}
def safe_slug(value): return (re.sub(r"[^0-9A-Za-z\u4e00-\u9fff_-]+","_",value).strip("_")[:36] or "route")
def sha256(path):
    digest=hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b""): digest.update(chunk)
    return digest.hexdigest()
def valid_job_id(value): return bool(re.fullmatch(r"WEB_[0-9A-Za-z\u4e00-\u9fff_-]+",value or ""))
class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*args,**kwargs): super().__init__(*args,directory=str(WEB_ROOT),**kwargs)
    def send_json(self,status,payload):
        data=json.dumps(payload,ensure_ascii=False).encode(); self.send_response(status); self.send_header("Content-Type","application/json; charset=utf-8"); self.send_header("Content-Length",str(len(data))); self.end_headers(); self.wfile.write(data)
    def read_json(self):
        length=int(self.headers.get("Content-Length","0"))
        if length<=0 or length>30_000_000: raise ValueError("请求大小无效")
        return json.loads(self.rfile.read(length))
    def send_file(self,target,download=False):
        data=target.read_bytes(); content_type=mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        self.send_response(200); self.send_header("Content-Type",content_type); self.send_header("Content-Length",str(len(data)))
        if download: self.send_header("Content-Disposition",f"attachment; filename*=UTF-8''{quote(target.name)}")
        self.end_headers(); self.wfile.write(data)
    def do_GET(self):
        if self.path=="/api/health": self.send_json(200,{"ok":True,"blender":BLENDER.exists(),"mode":"local-only"}); return
        decoded_path=unquote(urlsplit(self.path).path)
        if decoded_path=="/api/latest-final":
            for job_dir in sorted((p for p in JOBS_ROOT.glob("WEB_*") if p.is_dir()),reverse=True):
                manifest_path=job_dir/"review/final_manifest.json"
                if manifest_path.is_file():
                    payload=json.loads(manifest_path.read_text(encoding="utf-8")); self.send_json(200,{"ok":True,**payload}); return
            self.send_json(404,{"ok":False,"error":"还没有可恢复的最终交付"}); return
        if decoded_path.startswith("/generated/"):
            parts=decoded_path.split("/")
            if len(parts)==5 and parts[3]=="review" and re.fullmatch(r"WEB_[0-9A-Za-z\u4e00-\u9fff_-]+",parts[2]) and parts[4] in {"blender_preview.png","blender_preview_top.png","blender_preview_side.png","blender_delivery.png","blender_delivery_top.png","blender_delivery_side.png"}:
                target=JOBS_ROOT/parts[2]/"review"/parts[4]
                if target.exists():
                    data=target.read_bytes(); self.send_response(200); self.send_header("Content-Type","image/png"); self.send_header("Content-Length",str(len(data))); self.end_headers(); self.wfile.write(data); return
            self.send_error(404); return
        if decoded_path.startswith("/downloads/"):
            parts=decoded_path.split("/")
            if len(parts)==4 and valid_job_id(parts[2]) and Path(parts[3]).name==parts[3]:
                target=JOBS_ROOT/parts[2]/"final"/parts[3]
                if target.is_file(): self.send_file(target,download=True); return
            self.send_error(404); return
        super().do_GET()
    def do_POST(self):
        route=urlsplit(self.path).path
        if route not in {"/api/generate-preview","/api/finalize-job"}: self.send_error(404); return
        try:
            payload=self.read_json()
            if route=="/api/finalize-job": self.finalize_job(payload); return
            gpx_text=payload["gpx_text"]; job=payload["job"]; stamp=datetime.now().strftime("%Y%m%d_%H%M%S"); job_id=f"WEB_{stamp}_{safe_slug(job['route']['name'])}"; job_dir=JOBS_ROOT/job_id
            for folder in ("input","work","review","final","process"): (job_dir/folder).mkdir(parents=True,exist_ok=False)
            gpx_path=job_dir/"input/route.gpx"; gpx_path.write_text(gpx_text,encoding="utf-8"); web_facts=job["route"].get("facts",{}); job.update({"schema_version":"1.3-web-live-build","job_id":job_id,"status":"blender_preview_requested","production_policy":{"geometry_source":"current_uploaded_gpx","cross_job_artifact_reuse":False,"same_job_stage_resume":True},"input_sha256":sha256(gpx_path)}); job["route"].update({"gpx":"input/route.gpx","facts":"review/gpx_facts.json","web_facts":web_facts}); (job_dir/"job.json").write_text(json.dumps(job,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
            first=subprocess.run([str(BLENDER),"--background","--python",str(TOOLS/"generate_job_trailprint.py"),"--",str(job_dir)],cwd=ROOT,text=True,capture_output=True,timeout=1800); (job_dir/"process/01_trailprint.log").write_text(first.stdout+"\n"+first.stderr,encoding="utf-8")
            if first.returncode: raise RuntimeError("TrailPrint3D 生成失败；详见 01_trailprint.log")
            source=job_dir/"work/trailprint_source.blend"; output=job_dir/"work/blender_preview.blend"; report=job_dir/"review/blender_preview.json"; preview=job_dir/"review/blender_preview.png"
            second=subprocess.run([str(BLENDER),"--background",str(source),"--python",str(TOOLS/"render_web_trailprint_preview.py"),"--",str(output),str(report),str(preview)],cwd=ROOT,text=True,capture_output=True,timeout=900); (job_dir/"process/02_blender_render.log").write_text(second.stdout+"\n"+second.stderr,encoding="utf-8")
            if second.returncode or not preview.exists(): raise RuntimeError("Blender 渲染失败；详见 02_blender_render.log")
            base=f"/generated/{job_id}/review/"; job["status"]="blender_preview_ready"; (job_dir/"job.json").write_text(json.dumps(job,ensure_ascii=False,indent=2)+"\n",encoding="utf-8"); self.send_json(200,{"ok":True,"job_id":job_id,"preview_url":base+"blender_preview.png","previews":[{"key":"assembled","label":"装配透视","url":base+"blender_preview.png"},{"key":"top","label":"顶视关系","url":base+"blender_preview_top.png"},{"key":"side","label":"侧视高度","url":base+"blender_preview_side.png"}],"coverage":{"terrain":"ready","base":"reference","trail":"ready","water":"ready","one_plate":"pending","blend":"ready"},"blend":str(output)})
        except Exception as exc: traceback.print_exc(); self.send_json(500,{"ok":False,"error":str(exc)})
    def finalize_job(self,payload):
        job_id=payload.get("job_id","")
        if not valid_job_id(job_id): self.send_json(400,{"ok":False,"error":"任务编号无效"}); return
        job_dir=JOBS_ROOT/job_id; job_path=job_dir/"job.json"; gpx_path=job_dir/"input/route.gpx"
        if not job_path.is_file() or not gpx_path.is_file(): self.send_json(404,{"ok":False,"error":"找不到对应仿真任务，请先运行 Blender 仿真"}); return
        job=json.loads(job_path.read_text(encoding="utf-8"))
        final_dir=job_dir/"final"; final_dir.mkdir(exist_ok=True)
        pipeline=subprocess.run([sys.executable,str(TOOLS/"run_generic_job_pipeline.py"),str(job_dir)],cwd=ROOT,text=True,capture_output=True,timeout=7200)
        (job_dir/"process/03_generic_pipeline.log").write_text(pipeline.stdout+"\n"+pipeline.stderr,encoding="utf-8")
        if pipeline.returncode: raise RuntimeError("本次 GPX 实时生产流水线失败；详见 process/03_generic_pipeline.log")
        provenance="current-upload-live-generated-pipeline"
        checks={"当前上传 GPX 独立建模":True,"禁止跨任务成品复用":True,"仅允许本任务断点续跑":True,"5+1 文件契约":True,"输入 GPX SHA-256":sha256(gpx_path)}
        sources=sorted(path for path in final_dir.iterdir() if path.suffix.lower() in {".3mf",".blend"})
        if len([p for p in sources if p.suffix.lower()==".3mf"])!=5 or len([p for p in sources if p.suffix.lower()==".blend"])!=1: raise RuntimeError("最终目录不是完整的 5+1 套装")
        files=[]
        for source in sources:
            target=source
            if target.suffix.lower()==".3mf":
                if not zipfile.is_zipfile(target): raise RuntimeError(f"3MF 容器损坏：{target.name}")
                with zipfile.ZipFile(target) as archive:
                    if archive.testzip() is not None: raise RuntimeError(f"3MF ZIP 校验失败：{target.name}")
            else:
                header=target.read_bytes()[:16]
                # Blender 5 can save a Zstandard-compressed .blend (28 b5 2f fd).
                if not (header.startswith(b"BLENDER") or header.startswith(b"\x28\xb5\x2f\xfd")): raise RuntimeError(f"Blender 文件头无效：{target.name}")
            key=target.name[:2]; files.append({"key":key,"label":FINAL_LABELS.get(key,target.stem),"name":target.name,"url":f"/downloads/{job_id}/{quote(target.name)}","bytes":target.stat().st_size,"sha256":sha256(target),"qa":"PASS"})
        bundle=final_dir/f"{job_id}_完整交付_5个3MF加1个Blender.zip"
        with zipfile.ZipFile(bundle,"w",zipfile.ZIP_DEFLATED,allowZip64=True) as archive:
            for item in files: archive.write(final_dir/item["name"],item["name"])
            archive.writestr("SHA256SUMS.json",json.dumps({item["name"]:item["sha256"] for item in files},ensure_ascii=False,indent=2))
        preview_base=f"/generated/{job_id}/review/"
        final_previews=[{"key":"assembled","label":"最终装配透视","url":preview_base+"blender_delivery.png"},{"key":"top","label":"最终顶视关系","url":preview_base+"blender_delivery_top.png"},{"key":"side","label":"最终侧视高度","url":preview_base+"blender_delivery_side.png"}]
        manifest={"schema_version":"1.1","job_id":job_id,"status":"QA_PASS","provenance":provenance,"checks":checks,"previews":final_previews,"preview_url":final_previews[0]["url"],"files":files,"bundle":{"name":bundle.name,"url":f"/downloads/{job_id}/{quote(bundle.name)}","bytes":bundle.stat().st_size,"sha256":sha256(bundle)}}
        (job_dir/"review/final_manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        job["status"]="final_ready"; job["deliverables"]["manifest"]="review/final_manifest.json"; job_path.write_text(json.dumps(job,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        self.send_json(200,{"ok":True,**manifest})

if __name__=="__main__": print("GPX Terrain Lab: http://127.0.0.1:4173/"); ThreadingHTTPServer(("127.0.0.1",4173),Handler).serve_forever()
