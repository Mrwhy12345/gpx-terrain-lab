#!/usr/bin/env python3
"""Validate Bambu one-plate hierarchy: four top-level objects, seven material parts."""

from __future__ import annotations

import json
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

CORE = "{http://schemas.microsoft.com/3dmanufacturing/core/2015/02}"
EXPECTED = {"沙盘": 3, "底座": 2, "轨迹": 1, "水系": 1}
EXPECTED_PARENT_EXTRUDER = {"轨迹": "5", "水系": "4"}


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
        label = next((label for label in EXPECTED if name.endswith("_" + label)), None)
        extruder = next((m.get("value") for m in obj.findall("metadata") if m.get("key") == "extruder"), "")
        parts = obj.findall("part")
        records.append({"id": int(obj.get("id")), "name": name, "role": label, "parent_extruder": extruder, "material_parts": len(parts)})
    if len(build_items) != 4 or len(objects) != 4:
        raise RuntimeError(f"Expected 4 top-level objects, build={len(build_items)}, settings={len(objects)}")
    if {item["role"]: item["material_parts"] for item in records} != EXPECTED:
        raise RuntimeError(f"Unexpected object hierarchy: {records}")
    actual_extruders = {item["role"]: item["parent_extruder"] for item in records if item["role"] in EXPECTED_PARENT_EXTRUDER}
    if actual_extruders != EXPECTED_PARENT_EXTRUDER:
        raise RuntimeError(f"Unexpected trail/water parent extruders: {actual_extruders}")
    payload = {"status":"PASS","top_level_objects":4,"material_parts":7,"objects":records}
    if report:
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__": main()
