#!/usr/bin/env python3
"""Validate Bambu one-plate hierarchy: four install objects, optional city colour."""

from __future__ import annotations

import json
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

CORE = "{http://schemas.microsoft.com/3dmanufacturing/core/2015/02}"
ROLE_TOKENS = (
    ("沙盘", ("城市沙盘", "_沙盘")),
    ("底座", ("一体底座", "底座")),
    ("轨迹", ("红色轨迹", "轨迹")),
    ("地标", ("白色奥体", "奥体", "体育场", "地标")),
    ("水系", ("水系",)),
)


def detect_role(name: str) -> str | None:
    return next((role for role, tokens in ROLE_TOKENS if any(token in name for token in tokens)), None)


def main():
    if len(sys.argv) not in (2, 3): raise SystemExit("Expected PROJECT.3mf [REPORT.json]")
    project = Path(sys.argv[1]); report = Path(sys.argv[2]) if len(sys.argv) == 3 else None
    with zipfile.ZipFile(project) as archive:
        main_root = ET.fromstring(archive.read("3D/3dmodel.model"))
        settings = ET.fromstring(archive.read("Metadata/model_settings.config"))
    build_items = main_root.findall(f"{CORE}build/{CORE}item")
    objects = settings.findall("object")
    records = []
    for obj in objects:
        name = next((m.get("value") for m in obj.findall("metadata") if m.get("key") == "name"), "")
        label = detect_role(name)
        extruder = next((m.get("value") for m in obj.findall("metadata") if m.get("key") == "extruder"), "")
        parts = obj.findall("part")
        part_names = [next((m.get("value") for m in p.findall("metadata") if m.get("key") == "name"), "") for p in parts]
        records.append({"id": int(obj.get("id")), "name": name, "role": label, "parent_extruder": extruder, "material_parts": len(parts), "part_names": part_names})
    roles = {item["role"] for item in records}
    if None in roles:
        raise RuntimeError(f"Unrecognized top-level role: {records}")
    if {"沙盘", "底座", "轨迹", "地标"}.issubset(roles):
        contract = "marathon-four-piece"
        expected_roles = {"沙盘", "底座", "轨迹", "地标"}
    elif {"沙盘", "底座", "轨迹", "水系"}.issubset(roles):
        contract = "hiking-four-piece"
        expected_roles = {"沙盘", "底座", "轨迹", "水系"}
    else:
        raise RuntimeError(f"Unsupported four-piece role contract: {sorted(roles)}")
    expected_top_level = 4
    if len(build_items) != expected_top_level or len(objects) != expected_top_level or roles != expected_roles:
        raise RuntimeError(f"Expected roles {sorted(expected_roles)}, build={len(build_items)}, settings={len(objects)}, actual={sorted(roles)}")
    hierarchy = {item["role"]: item["material_parts"] for item in records}
    terrain = next(item for item in records if item["role"] == "沙盘")
    has_city = any(any(token in name for token in ("City_Terracotta", "城市建筑", "建筑")) for name in terrain["part_names"])
    has_split_city = all(
        any(any(token in name for token in tokens) for name in terrain["part_names"])
        for tokens in (("City_Buildings", "城市建筑", "建筑"), ("City_Roads", "城市道路", "道路"))
    )
    base = next(item for item in records if item["role"] == "底座")
    if base["material_parts"] not in {2, 3}:
        raise RuntimeError(f"Unexpected base hierarchy: {base}")
    expected = {"沙盘": 5 if has_split_city else (4 if has_city else 3), "底座": base["material_parts"], "轨迹": 1}
    expected["地标" if contract.startswith("marathon") else "水系"] = 1
    if hierarchy != expected:
        raise RuntimeError(f"Unexpected object hierarchy: {records}")
    if any(not item["parent_extruder"] for item in records):
        raise RuntimeError(f"Missing parent extruder assignment: {records}")
    material_parts = sum(item["material_parts"] for item in records)
    payload = {"status":"PASS","contract":contract,"top_level_objects":expected_top_level,"material_parts":material_parts,"city_terracotta":has_city,"city_split_in_place":has_split_city,"objects":records}
    if report:
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__": main()
