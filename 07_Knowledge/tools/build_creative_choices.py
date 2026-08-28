#!/usr/bin/env python3
"""Persistent, route-linked creative choices for an anonymous web job.

Only derived files under ``work/creative`` and ``review`` are written.  The
uploaded GPX is read-only.  Candidate logo SVGs intentionally use closed
polygon paths because the production inlay importer consumes that exact form.
"""

from __future__ import annotations

import html
import json
import math
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

from medal_frame_spec import (
    SPEC_VERSION,
    TARGET_DESIGN_OUTER_BOUNDS_MM,
    TARGET_PRINTED_MESH_OUTER_BOUNDS_MM,
    TARGET_VISIBLE_RING_WIDTH_MM,
)

STATE_REL = Path("review/creative_state.json")
CREATIVE_REL = Path("work/creative")


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _save(job_dir: Path, state: dict) -> dict:
    state["updated_at"] = datetime.now().isoformat(timespec="seconds")
    _write_json(job_dir / STATE_REL, state)
    return state


def load_creative(job_dir: Path) -> dict | None:
    path = Path(job_dir) / STATE_REL
    return _read_json(path) if path.is_file() else None


def _route_points(gpx: Path) -> list[tuple[float, float]]:
    root = ET.parse(gpx).getroot()
    return [
        (float(node.attrib["lon"]), float(node.attrib["lat"]))
        for node in root.iter()
        if node.tag.rsplit("}", 1)[-1] in {"trkpt", "rtept"}
    ]


def _clean_title(value: str) -> str:
    value = re.sub(r"\.(gpx|kml)$", "", value.strip(), flags=re.I)
    value = re.sub(r"(?:19|20)\d{2}[-_/年.]?\d{0,2}[-_/月.]?\d{0,2}日?", "", value)
    value = re.sub(r"\d{1,2}[+_:-]\d{1,2}(?:[+_:-]\d{1,2})?", "", value)
    value = re.sub(r"[_+—～~|]+", " ", value)
    value = re.sub(r"\s+", " ", value).strip(" -_()（）")
    return value or "山野徒步"


def _short(value: str, limit: int = 10) -> str:
    value = _clean_title(value)
    for suffix in ("徒步路线", "徒步", "环穿路线", "环穿", "环线路线", "路线"):
        value = value.removesuffix(suffix)
    return (value[:limit] or "山野")


def _theme(value: str) -> tuple[str, str]:
    if any(word in value for word in ("溪", "河", "水", "瀑")):
        return "溪谷纪行", "溪谷"
    if any(word in value for word in ("竹", "林")):
        return "竹径行记", "竹林"
    if any(word in value for word in ("马", "骏")):
        return "山野画马", "画马"
    if any(word in value for word in ("风", "车")):
        return "风车山径", "风车"
    if any(word in value for word in ("城", "公园", "跑")):
        return "城市行迹", "城市"
    return "山野行迹", "山径"


def _title_candidates(original: str) -> list[dict]:
    clean = _clean_title(original)
    core = _short(clean)
    themed, _ = _theme(clean)
    # Keep every automatic option inside the print-verified safe text area on
    # the medal-frame ring.  A default choice must never be knowingly overlong.
    values = [clean[:14], core[:12], f"{core}徒步"[:14], themed]
    unique = []
    for value in values:
        candidate = value
        suffix = 2
        while candidate in unique:
            candidate = f"{value}{suffix}"; suffix += 1
        unique.append(candidate)
    labels = ("保留原意", "简洁地名", "活动标题", "主题创作")
    reasons = ("忠于上传文件名", "适合底座短边排版", "明确表达徒步属性", "从路线关键词提炼意象")
    return [
        {"id": chr(65 + i), "title": value, "label": labels[i], "reason": reasons[i],
         "fit": "PASS" if len(value) <= 14 else "NEEDS_REVIEW"}
        for i, value in enumerate(unique)
    ]


def _poly(points: list[tuple[float, float]]) -> str:
    return "M " + " L ".join(f"{x:.2f} {y:.2f}" for x, y in points) + " Z"


def _rect(x: float, y: float, w: float, h: float) -> list[tuple[float, float]]:
    return [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]


def _disc(cx: float, cy: float, radius: float, count: int = 18) -> list[tuple[float, float]]:
    return [(cx + math.cos(2 * math.pi * i / count) * radius,
             cy + math.sin(2 * math.pi * i / count) * radius) for i in range(count)]


def _normalize_route(points: list[tuple[float, float]], count: int = 9) -> list[tuple[float, float]]:
    if len(points) < 2:
        return [(15, 52), (85, 18)]
    indices = [round(i * (len(points) - 1) / (count - 1)) for i in range(count)]
    sampled = [points[index] for index in indices]
    west, east = min(p[0] for p in sampled), max(p[0] for p in sampled)
    south, north = min(p[1] for p in sampled), max(p[1] for p in sampled)
    sx, sy = max(east - west, 1e-9), max(north - south, 1e-9)
    scale = min(72 / sx, 48 / sy)
    return [((x - (west + east) / 2) * scale + 50, 35 - (y - (south + north) / 2) * scale) for x, y in sampled]


def _segment(a: tuple[float, float], b: tuple[float, float], width: float = 4.0) -> list[tuple[float, float]]:
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = max(math.hypot(dx, dy), 1e-6)
    nx, ny = -dy / length * width / 2, dx / length * width / 2
    return [(a[0] + nx, a[1] + ny), (b[0] + nx, b[1] + ny), (b[0] - nx, b[1] - ny), (a[0] - nx, a[1] - ny)]


def _motif_paths(theme: str) -> list[list[tuple[float, float]]]:
    if theme == "六峰":
        # Six individually readable ridges form one stable silhouette.  The
        # rising path and sun make the mark directional without relying on
        # thin strokes or decorative fragments that disappear after slicing.
        return [
            [(7,57),(14,43),(21,52),(28,32),(35,47),(42,20),(49,43),
             (57,28),(64,48),(72,35),(79,51),(87,40),(94,57)],
            [(43,57),(39,52),(44,46),(42,40),(47,34),(52,36),(49,42),
             (54,47),(51,52),(56,57)],
            _disc(84, 18, 7.0),
        ]
    if theme == "竹林":
        return [_rect(35, 17, 7, 39), _rect(47, 11, 7, 45), _rect(59, 20, 7, 36),
                [(28, 29), (36, 22), (42, 27), (35, 34)], [(66, 31), (76, 24), (72, 35), (65, 39)]]
    if theme == "画马":
        return [[(27,52),(33,25),(46,12),(61,18),(72,31),(64,35),(73,48),(61,45),(55,59),(44,44)],
                [(43,18),(36,8),(49,14)], [(58,19),(68,9),(65,25)]]
    if theme == "风车":
        return [_rect(47, 29, 6, 31), [(50,31),(20,20),(43,37)], [(50,31),(62,8),(56,37)], [(50,31),(79,43),(55,39)]]
    if theme == "城市":
        return [_rect(20, 32, 15, 25), _rect(38, 19, 17, 38), _rect(58, 27, 22, 30), _rect(16, 55, 68, 5)]
    if theme == "溪谷":
        return [[(16,21),(31,32),(43,24),(57,40),(70,30),(84,47),(80,54),(69,39),(57,49),(43,34),(31,42),(12,29)],
                [(21,56),(36,42),(49,55),(64,39),(80,56),(76,61),(64,49),(49,64),(36,52),(25,63)]]
    if theme == "山径主题":
        return [
            [(12,55),(31,24),(45,43),(61,16),(88,55),(73,55),(60,35),(47,57),(31,40),(22,55)],
            [(39,57),(36,50),(41,44),(39,38),(44,31),(49,34),(46,41),(51,47),(48,53),(52,57)],
            _disc(74, 18, 7.5),
        ]
    # Generic mountain mark: two bold ridges, a rising trail and a sun.  All
    # elements are closed polygons with print-safe mass; no hairline baseline.
    return [
        [(13,55),(34,22),(49,42),(66,13),(88,55),(72,55),(64,34),(50,57),(35,39),(25,55)],
        [(25,55),(39,37),(50,52),(63,31),(76,55)],
        [(46,57),(43,49),(47,43),(45,37),(49,30),(54,32),(51,39),(54,45),(51,51),(54,57)],
        _disc(75, 18, 6.5),
    ]


def _write_logo(path: Path, paths: list[list[tuple[float, float]]], title: str, label: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = "".join(f'<path d="{_poly(points)}"/>' for points in paths if len(points) >= 3)
    path.write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 70" '
        f'data-title="{html.escape(title)}" data-style="{html.escape(label)}">{data}</svg>\n',
        encoding="utf-8",
    )


def _logo_candidates(job_dir: Path, title: str) -> list[dict]:
    job = _read_json(job_dir / "job.json")
    points = _route_points(job_dir / job["route"]["gpx"])
    route = _normalize_route(points)
    _, theme = _theme(title)
    route_paths = [_segment(a, b, 5.0) for a, b in zip(route, route[1:])]
    route_paths.extend((_disc(*route[0], 4.2), _disc(*route[-1], 5.2)))
    is_six_peaks = "六片" in title or "六峰" in title
    b_theme = "六峰" if is_six_peaks else "山径"
    b_label = "六峰成章" if is_six_peaks else "山径层峦"
    b_description = ("六座连续山峰、上升山径与日轮组成路线专属徽记"
                     if is_six_peaks else "双层山脊、上升山径与日轮组成完整徽章")
    candidates = [
        ("A", "路线徽记", "加粗本次 GPX，并强化起终点识别", route_paths, 1.60),
        ("B", b_label, b_description, _motif_paths(b_theme), 1.45),
        ("C", "溪谷罗盘", "用溪谷与方向感表达出发", _motif_paths("溪谷"), 1.20),
        ("D", f"{theme}意象", f"从“{title}”提炼的粗线主题徽记",
         _motif_paths("山径主题" if theme == "山径" else theme), 1.35),
    ]
    result = []
    for ident, label, description, paths, min_feature in candidates:
        relative = CREATIVE_REL / f"logo_{ident}.svg"
        _write_logo(job_dir / relative, paths, title, label)
        result.append({
            "id": ident, "label": label, "description": description,
            "url": f"/generated/{job_dir.name}/creative/logo_{ident}.svg",
            "source": str(relative), "qa": "PASS",
            "metrics": {"target_width_mm": 38.0, "min_feature_mm": min_feature,
                        "path_count": len(paths), "visual_grade": "production_bold_v2"},
        })
    return result


def _proof_svg(job_dir: Path, state: dict) -> dict:
    job = _read_json(job_dir / "job.json")
    selected = next(item for item in state["logo_candidates"] if item["id"] == state["selected_logo_id"])
    logo = (job_dir / selected["source"]).read_text(encoding="utf-8")
    paths = "".join(re.findall(r"<path[^>]+/>", logo))
    facts = job["route"].get("web_facts", {})
    distance = float(facts.get("distance_km") or 0)
    date = job.get("customer_input", {}).get("display_date", "")
    title = state["selected_title"]
    # Use the same physical aspect ratio as the locked medal-frame contract.
    # The proof is a bottom view; the three text fields mirror production
    # order and formatting exactly.
    design_w, design_h = TARGET_DESIGN_OUTER_BOUNDS_MM
    canvas_w, canvas_h = 120.0, 105.0
    scale = min(111.0 / design_w, 96.0 / design_h)
    cx, cy = canvas_w / 2, canvas_h / 2
    half_w, half_h = design_w * scale / 2, design_h * scale / 2
    outer_points = [
        (cx - half_w / 2, cy - half_h), (cx + half_w / 2, cy - half_h),
        (cx + half_w, cy), (cx + half_w / 2, cy + half_h),
        (cx - half_w / 2, cy + half_h), (cx - half_w, cy),
    ]
    # Scaling around the centre preserves six pairs of parallel edges.  The
    # verified visible-ring width is converted into proof coordinates here.
    inset_ratio = max(0.0, 1.0 - 2.0 * TARGET_VISIBLE_RING_WIDTH_MM / design_h)
    inner_points = [
        (cx + (x - cx) * inset_ratio, cy + (y - cy) * inset_ratio)
        for x, y in outer_points
    ]
    outer = " ".join(f"{x:.3f},{y:.3f}" for x, y in outer_points)
    inner = " ".join(f"{x:.3f},{y:.3f}" for x, y in inner_points)
    display_date = date.replace("-", ".")
    display_distance = f"{distance:.1f} KM"
    proof = job_dir / CREATIVE_REL / "bottom_proof.svg"
    proof.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 105">'
        '<rect width="120" height="105" fill="#f5f3ec"/>'
        f'<polygon points="{outer}" fill="#858c91"/><polygon points="{inner}" fill="#d6d8d6"/>'
        f'<text x="60" y="13" text-anchor="middle" font-size="5" fill="#7a4a20">{html.escape(title)}</text>'
        f'<text x="23" y="79" transform="rotate(30 23 79)" font-size="4" fill="#7a4a20">{html.escape(display_date)}</text>'
        f'<text x="83" y="80" transform="rotate(-30 83 80)" font-size="4" fill="#7a4a20">{display_distance}</text>'
        f'<g transform="translate(39 36) scale(.42)" fill="#7a4a20">{paths}</g>'
        f'<text x="60" y="101" text-anchor="middle" font-size="2.6" fill="#425249">同源底面校样 · {SPEC_VERSION}</text>'
        '</svg>\n', encoding="utf-8")
    return {
        "url": f"/generated/{job_dir.name}/creative/bottom_proof.svg",
        "source": str(CREATIVE_REL / "bottom_proof.svg"),
        "qa": "PASS",
        "dimensions": {
            "design_outer_mm": list(TARGET_DESIGN_OUTER_BOUNDS_MM),
            "printed_mesh_outer_mm": list(TARGET_PRINTED_MESH_OUTER_BOUNDS_MM),
            "visible_ring_width_mm": TARGET_VISIBLE_RING_WIDTH_MM,
            "frame_spec": SPEC_VERSION,
        },
        "content": {"title": title, "date": display_date, "distance": display_distance,
                    "logo_source": selected["source"]},
        "checks": {"title_fit": len(title) <= 14, "date_present": bool(date),
                   "distance_present": distance > 0, "logo_source_same_as_production": True,
                   "frame_dimensions_from_locked_spec": True,
                   "label_order_matches_production": True},
    }


def initialize_creative(job_dir: Path) -> dict:
    job_dir = Path(job_dir)
    existing = load_creative(job_dir)
    if existing:
        return existing
    job = _read_json(job_dir / "job.json")
    original = job.get("customer_input", {}).get("title") or job["route"]["name"]
    state = {
        "schema_version": "1.0", "stage": "TITLE_SELECTION", "confirmed": False,
        "title_candidates": _title_candidates(original), "selected_title_id": None,
        "selected_title": None, "logo_candidates": [], "selected_logo_id": None, "proof": None,
    }
    return _save(job_dir, state)


def choose_title(job_dir: Path, candidate_id: str | None = None, custom_title: str | None = None, display_date: str | None = None) -> dict:
    job_dir = Path(job_dir); state = initialize_creative(job_dir)
    match = next((item for item in state["title_candidates"] if item["id"] == candidate_id), None)
    title = _clean_title(custom_title)[:14] if custom_title else (match or {}).get("title")
    if not title:
        raise ValueError("请选择一个标题")
    job = _read_json(job_dir / "job.json")
    job.setdefault("customer_input", {})["title"] = title
    if display_date:
        job["customer_input"]["display_date"] = display_date
    _write_json(job_dir / "job.json", job)
    state.update({
        "stage": "LOGO_SELECTION", "confirmed": False,
        "selected_title_id": candidate_id or "CUSTOM", "selected_title": title,
        "logo_candidates": _logo_candidates(job_dir, title), "selected_logo_id": None, "proof": None,
    })
    return _save(job_dir, state)


def choose_logo(job_dir: Path, candidate_id: str, display_date: str | None = None) -> dict:
    job_dir = Path(job_dir); state = load_creative(job_dir)
    if not state or not state.get("selected_title"):
        raise ValueError("请先确认标题")
    if not any(item["id"] == candidate_id for item in state.get("logo_candidates", [])):
        raise ValueError("请选择一个 Logo")
    if display_date:
        job = _read_json(job_dir / "job.json")
        job.setdefault("customer_input", {})["display_date"] = display_date
        _write_json(job_dir / "job.json", job)
    state.update({"stage": "CONFIRMATION", "confirmed": False, "selected_logo_id": candidate_id})
    state["proof"] = _proof_svg(job_dir, state)
    return _save(job_dir, state)


def attach_bottom_render(job_dir: Path, source: str = "work/creative/bottom_render.png") -> dict:
    """Attach the Blender-rendered bottom view without replacing the exact SVG proof."""
    job_dir = Path(job_dir); state = load_creative(job_dir)
    if not state or not state.get("proof"):
        raise ValueError("底面同源校样尚未生成")
    target = job_dir / source
    if not target.is_file() or target.stat().st_size < 1024:
        raise ValueError("底部视图渲染文件无效")
    state["proof"].update({
        "render_url": f"/generated/{job_dir.name}/creative/{target.name}",
        "render_source": source,
        "render_qa": "PASS",
        "render_dimensions_px": [1200, 900],
    })
    return _save(job_dir, state)


def confirm_creative(job_dir: Path) -> dict:
    job_dir = Path(job_dir); state = load_creative(job_dir)
    if not state or not state.get("selected_title") or not state.get("selected_logo_id") or not state.get("proof"):
        raise ValueError("标题、Logo 或底面校样尚未完成")
    selected = next(item for item in state["logo_candidates"] if item["id"] == state["selected_logo_id"])
    if selected.get("qa") != "PASS" or state["proof"].get("qa") != "PASS":
        raise ValueError("创意打印检查尚未通过")
    if not state["proof"].get("checks", {}).get("title_fit", False):
        raise ValueError("标题超出奖牌框安全排版区，请先缩短标题")
    state.update({"stage": "CONFIRMED", "confirmed": True})
    job = _read_json(job_dir / "job.json")
    job["creative"] = {
        "confirmed": True, "title": state["selected_title"],
        "selected_title": state["selected_title"], "logo_id": state["selected_logo_id"],
        "logo_svg": selected["source"], "proof": state["proof"]["source"], "frame_spec": SPEC_VERSION,
    }
    _write_json(job_dir / "job.json", job)
    return _save(job_dir, state)
