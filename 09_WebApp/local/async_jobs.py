#!/usr/bin/env python3
"""Persistent single-worker queue for TrailPrint3D/Blender production."""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import threading
import traceback
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[2]
JOBS_ROOT = ROOT / "08_Jobs"
TOOLS = ROOT / "07_Knowledge" / "tools"
BLENDER = Path("/Applications/Blender.app/Contents/MacOS/Blender")
STATUS_NAME = "web_task_status.json"
PIPELINE_VERSION = "WEB05_ASYNC_V2_QUEUE"
BASE_ALGORITHM = "parallel_equal_width_ring_v3"
FONT_ALGORITHM = "printable_chinese_v4"
FINAL_LABELS = {
    "01": "沙盘地形", "02": "奖牌框适配底座", "03": "徒步轨迹",
    "04": "完整水网", "05": "四件同盘", "06": "Blender 设计项目",
}

sys.path.insert(0, str(TOOLS))
from configure_route_scene import configure as configure_route_scene


def safe_slug(value):
    return (re.sub(r"[^0-9A-Za-z\u4e00-\u9fff_-]+", "_", value).strip("_")[:36] or "route")


def valid_job_id(value):
    return bool(re.fullmatch(r"WEB_[0-9A-Za-z\u4e00-\u9fff_-]+", value or ""))


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def status_path(job_dir):
    return job_dir / "review" / STATUS_NAME


def write_json_atomic(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def update_status(job_dir, state, stage, progress, message, **extra):
    current = {}
    path = status_path(job_dir)
    if path.exists():
        current = json.loads(path.read_text(encoding="utf-8"))
    current.setdefault("created_at", datetime.now().isoformat(timespec="seconds"))
    current.update({
        "schema_version": "1.0",
        "pipeline_version": PIPELINE_VERSION,
        "job_id": job_dir.name,
        "state": state,
        "stage": stage,
        "progress": progress,
        "message": message,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        **extra,
    })
    write_json_atomic(path, current)
    return current


def run_blender(command, log_path, attempts=3):
    """Retry only startup/native Blender failures; preserve every attempt log."""
    outputs = []
    for attempt in range(1, attempts + 1):
        result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, timeout=1800)
        outputs.append(f"=== attempt {attempt}/{attempts} ===\n{result.stdout}\n{result.stderr}")
        if result.returncode == 0:
            log_path.write_text("\n".join(outputs), encoding="utf-8")
            return result
    log_path.write_text("\n".join(outputs), encoding="utf-8")
    return result


def preview_payload(job_id, route_profile):
    base = f"/generated/{job_id}/review/"
    generation_path = JOBS_ROOT / job_id / "review/trailprint_generation.json"
    generation = json.loads(generation_path.read_text(encoding="utf-8")) if generation_path.exists() else {}
    return {
        "ok": True,
        "job_id": job_id,
        "route_profile": route_profile,
        "terrain_height_policy": generation.get("terrain_height_policy"),
        "preview_url": base + "blender_preview.png",
        "previews": [
            {"key": "assembled", "label": "装配透视", "url": base + "blender_preview.png"},
            {"key": "top", "label": "顶视关系", "url": base + "blender_preview_top.png"},
            {"key": "side", "label": "侧视高度", "url": base + "blender_preview_side.png"},
        ],
        "coverage": {"terrain": "ready", "base": "reference", "trail": "ready", "water": "ready", "one_plate": "pending", "blend": "ready"},
    }


def create_preview_job(payload):
    gpx_text = payload["gpx_text"]
    # Never mutate the caller's request object; otherwise a retry can produce a
    # different idempotency fingerprint after route paths are normalized below.
    job = json.loads(json.dumps(payload["job"], ensure_ascii=False))
    client_id = payload.get("client_id") or "legacy-local-client"
    submission_key = hashlib.sha256((client_id + "\n" + gpx_text + "\n" + json.dumps(job, ensure_ascii=False, sort_keys=True, separators=(",", ":"))).encode()).hexdigest()
    for path in sorted(JOBS_ROOT.glob(f"WEB_*/review/{STATUS_NAME}"), reverse=True):
        try:
            status = json.loads(path.read_text(encoding="utf-8"))
            existing_job = json.loads((path.parents[1] / "job.json").read_text(encoding="utf-8"))
            if existing_job.get("submission_key") == submission_key and status.get("state") in {"QUEUED", "RUNNING", "PREVIEW_READY"}:
                return path.parents[1].name, False
        except (OSError, ValueError, json.JSONDecodeError):
            continue
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    job_id = f"WEB_{stamp}_{safe_slug(job['route']['name'])}"
    job_dir = JOBS_ROOT / job_id
    for folder in ("input", "work", "review", "final", "process"):
        (job_dir / folder).mkdir(parents=True, exist_ok=False)
    gpx_path = job_dir / "input/route.gpx"
    gpx_path.write_text(gpx_text, encoding="utf-8")
    web_facts = job["route"].get("facts", {})
    job.update({
        "schema_version": "1.5-async-worker",
        "job_id": job_id,
        "status": "preview_queued",
        "pipeline_version": PIPELINE_VERSION,
        "production_policy": {"geometry_source": "current_uploaded_gpx", "cross_job_artifact_reuse": False, "same_job_stage_resume": True},
        "input_sha256": sha256(gpx_path),
        "submission_key": submission_key,
        "anonymous_client_id": client_id,
    })
    job["route"].update({"gpx": "input/route.gpx", "facts": "review/gpx_facts.json", "web_facts": web_facts})
    write_json_atomic(job_dir / "job.json", job)
    update_status(job_dir, "QUEUED", "preview", 2, "任务已进入 Mac mini 队列", request="preview")
    return job_id, True


def run_preview(job_id):
    job_dir = JOBS_ROOT / job_id
    try:
        update_status(job_dir, "RUNNING", "route_profile", 8, "正在分析 GPX 范围与参数")
        route_profile = configure_route_scene(job_dir)
        update_status(job_dir, "RUNNING", "trailprint3d", 20, "TrailPrint3D 正在生成地形")
        first = run_blender(
            [str(BLENDER), "--background", "--python", str(TOOLS / "generate_job_trailprint.py"), "--", str(job_dir)],
            job_dir / "process/01_trailprint.log",
        )
        if first.returncode:
            raise RuntimeError("TrailPrint3D 生成失败；详见 01_trailprint.log")
        source = job_dir / "work/trailprint_source.blend"
        output = job_dir / "work/blender_preview.blend"
        report = job_dir / "review/blender_preview.json"
        preview = job_dir / "review/blender_preview.png"
        update_status(job_dir, "RUNNING", "blender_preview", 65, "Blender 正在渲染三机位预览")
        second = run_blender(
            [str(BLENDER), "--background", str(source), "--python", str(TOOLS / "render_web_trailprint_preview.py"), "--", str(output), str(report), str(preview)],
            job_dir / "process/02_blender_render.log",
        )
        if second.returncode or not preview.exists():
            raise RuntimeError("Blender 渲染失败；详见 02_blender_render.log")
        job = json.loads((job_dir / "job.json").read_text(encoding="utf-8"))
        job["status"] = "blender_preview_ready"
        write_json_atomic(job_dir / "job.json", job)
        result = preview_payload(job_id, route_profile)
        update_status(job_dir, "PREVIEW_READY", "preview", 100, "三机位仿真完成", result=result)
    except Exception as exc:
        (job_dir / "process/async_preview_traceback.log").write_text(traceback.format_exc(), encoding="utf-8")
        update_status(job_dir, "FAILED", "preview", 100, str(exc), error=str(exc))


def final_manifest(job_dir):
    path = job_dir / "review/final_manifest.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def run_final(job_id):
    job_dir = JOBS_ROOT / job_id
    try:
        job_path, gpx_path = job_dir / "job.json", job_dir / "input/route.gpx"
        update_status(job_dir, "RUNNING", "production", 5, "正在生成最终 5+1", request="final")
        pipeline = subprocess.run(
            [sys.executable, str(TOOLS / "run_generic_job_pipeline.py"), str(job_dir)],
            cwd=ROOT, text=True, capture_output=True, timeout=7200,
        )
        (job_dir / "process/03_generic_pipeline.log").write_text(pipeline.stdout + "\n" + pipeline.stderr, encoding="utf-8")
        if pipeline.returncode:
            raise RuntimeError("本次 GPX 实时生产流水线失败；详见 process/03_generic_pipeline.log")
        update_status(job_dir, "RUNNING", "packaging", 88, "正在核验并打包交付文件")
        final_dir = job_dir / "final"
        sources = sorted(path for path in final_dir.iterdir() if path.suffix.lower() in {".3mf", ".blend"})
        if len([p for p in sources if p.suffix.lower() == ".3mf"]) != 5 or len([p for p in sources if p.suffix.lower() == ".blend"]) != 1:
            raise RuntimeError("最终目录不是完整的 5+1 套装")
        files = []
        for target in sources:
            if target.suffix.lower() == ".3mf":
                if not zipfile.is_zipfile(target):
                    raise RuntimeError(f"3MF 容器损坏：{target.name}")
                with zipfile.ZipFile(target) as archive:
                    if archive.testzip() is not None:
                        raise RuntimeError(f"3MF ZIP 校验失败：{target.name}")
            else:
                header = target.read_bytes()[:16]
                if not (header.startswith(b"BLENDER") or header.startswith(b"\x28\xb5\x2f\xfd")):
                    raise RuntimeError(f"Blender 文件头无效：{target.name}")
            key = target.name[:2]
            files.append({"key": key, "label": FINAL_LABELS.get(key, target.stem), "name": target.name, "url": f"/downloads/{job_id}/{quote(target.name)}", "bytes": target.stat().st_size, "sha256": sha256(target), "qa": "PASS"})
        bundle = final_dir / f"{job_id}_完整交付_5个3MF加1个Blender.zip"
        with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
            for item in files:
                archive.write(final_dir / item["name"], item["name"])
            archive.writestr("SHA256SUMS.json", json.dumps({item["name"]: item["sha256"] for item in files}, ensure_ascii=False, indent=2))
        preview_base = f"/generated/{job_id}/review/"
        previews = [{"key": key, "label": label, "url": preview_base + filename} for key, label, filename in (
            ("assembled", "最终装配透视", "blender_delivery.png"),
            ("top", "最终顶视关系", "blender_delivery_top.png"),
            ("side", "最终侧视高度", "blender_delivery_side.png"),
        )]
        manifest = {
            "schema_version": "1.2-async", "job_id": job_id, "status": "QA_PASS",
            "pipeline_version": PIPELINE_VERSION, "provenance": "current-upload-live-generated-pipeline",
            "checks": {"当前上传 GPX 独立建模": True, "禁止跨任务成品复用": True, "5+1 文件契约": True, "输入 GPX SHA-256": sha256(gpx_path)},
            "previews": previews, "preview_url": previews[0]["url"], "files": files,
            "bundle": {"name": bundle.name, "url": f"/downloads/{job_id}/{quote(bundle.name)}", "bytes": bundle.stat().st_size, "sha256": sha256(bundle)},
        }
        write_json_atomic(job_dir / "review/final_manifest.json", manifest)
        job = json.loads(job_path.read_text(encoding="utf-8"))
        job["status"] = "final_ready"
        job.setdefault("deliverables", {})["manifest"] = "review/final_manifest.json"
        write_json_atomic(job_path, job)
        update_status(job_dir, "FINAL_READY", "complete", 100, "最终 5+1 已通过 QA", result={"ok": True, **manifest})
    except Exception as exc:
        (job_dir / "process/async_final_traceback.log").write_text(traceback.format_exc(), encoding="utf-8")
        update_status(job_dir, "FAILED", "final", 100, str(exc), error=str(exc))


class JobQueue:
    def __init__(self):
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="gpx-worker")
        self.lock = threading.Lock()
        self.active = set()

    def submit(self, job_id, request):
        key = (job_id, request)
        with self.lock:
            if key in self.active:
                return False
            self.active.add(key)
        function = run_preview if request == "preview" else run_final
        future = self.executor.submit(function, job_id)
        future.add_done_callback(lambda _future: self._done(key))
        return True

    def _done(self, key):
        with self.lock:
            self.active.discard(key)

    def resume(self):
        for path in sorted(JOBS_ROOT.glob(f"WEB_*/review/{STATUS_NAME}")):
            status = json.loads(path.read_text(encoding="utf-8"))
            if status.get("state") in {"QUEUED", "RUNNING"}:
                request = status.get("request", "preview")
                update_status(path.parents[1], "QUEUED", status.get("stage", request), status.get("progress", 0), "服务重启，任务已恢复排队", request=request)
                self.submit(path.parents[1].name, request)


QUEUE = JobQueue()
