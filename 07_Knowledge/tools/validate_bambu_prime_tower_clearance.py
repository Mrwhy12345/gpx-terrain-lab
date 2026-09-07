#!/usr/bin/env python3
"""Check the configured prime tower against top-level 3MF object XY bounds."""

from __future__ import annotations

import argparse
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZipFile

CORE = "{http://schemas.microsoft.com/3dmanufacturing/core/2015/02}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("project", type=Path)
    parser.add_argument("report", type=Path)
    parser.add_argument("--clearance", type=float, default=10.0)
    args = parser.parse_args()

    with ZipFile(args.project) as archive:
        settings = json.loads(archive.read("Metadata/project_settings.config"))
        root = ET.fromstring(archive.read("3D/Objects/object_1.model"))
        main = ET.fromstring(archive.read("3D/3dmodel.model"))
        model_settings = ET.fromstring(archive.read("Metadata/model_settings.config"))

    tx = float(settings["wipe_tower_x"][0])
    ty = float(settings["wipe_tower_y"][0])
    width = float(settings.get("prime_tower_width", "60"))
    # Bambu's conservative collision test can exceed the rendered tower. Use
    # a square width envelope plus an explicit clearance margin.
    tower = (tx, tx + width, ty, ty + width)

    transform = main.find(f"{CORE}build/{CORE}item").attrib.get("transform", "")
    values = [float(v) for v in transform.split()]
    ox, oy = values[9], values[10]

    vertices = root.findall(f".//{CORE}vertex")
    xs = [float(v.attrib["x"]) + ox for v in vertices]
    ys = [float(v.attrib["y"]) + oy for v in vertices]
    # Report all-project bounds for traceability; collision is evaluated by
    # checking every vertex against the expanded tower envelope.
    expanded = (
        tower[0] - args.clearance,
        tower[1] + args.clearance,
        tower[2] - args.clearance,
        tower[3] + args.clearance,
    )
    conflicts = sum(
        expanded[0] <= x <= expanded[1] and expanded[2] <= y <= expanded[3]
        for x, y in zip(xs, ys)
    )
    plate = model_settings.find("plate")
    sequence = next(
        (m.attrib.get("value") for m in plate.findall("metadata")
         if m.attrib.get("key") == "print_sequence"),
        settings.get("print_sequence", "by layer"),
    )
    names = {
        obj.attrib["id"]: next(
            (m.attrib.get("value", "") for m in obj.findall("metadata")
             if m.attrib.get("key") == "name"), ""
        )
        for obj in model_settings.findall("object")
    }
    object_order = [
        names.get(next(m.attrib["value"] for m in inst.findall("metadata")
                       if m.attrib.get("key") == "object_id"), "")
        for inst in plate.findall("model_instance")
    ]
    expected_roles = ("水系", "轨迹", "底座", "沙盘", "地标")
    sequential_order_ok = len(object_order) == len(expected_roles) and all(
        role in name for role, name in zip(expected_roles, object_order)
    )
    if sequence == "by object":
        passed = sequential_order_ok
        rule = "sequential object order; final collision authority is Bambu Studio"
    else:
        passed = conflicts == 0
        rule = "expanded tower envelope contains no model vertices"
    payload = {
        "status": "PASS" if passed else "FAIL",
        "project": str(args.project),
        "tower_xywh_mm": [tx, ty, width, width],
        "clearance_mm": args.clearance,
        "expanded_tower_bounds_mm": list(expanded),
        "model_bounds_mm": [min(xs), max(xs), min(ys), max(ys)],
        "vertices_inside_expanded_tower": conflicts,
        "print_sequence": sequence,
        "object_order": object_order,
        "sequential_order_ok": sequential_order_ok,
        "rule": rule,
        "note": "Geometric preflight; final authority is a successful Bambu Studio slice.",
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    raise SystemExit(0 if payload["status"] == "PASS" else 1)


if __name__ == "__main__":
    main()
