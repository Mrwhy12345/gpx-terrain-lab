#!/usr/bin/env python3
"""Reject flattened 3MFs that load but lose Bambu's native object semantics."""

from __future__ import annotations

import argparse
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZipFile

CORE = "{http://schemas.microsoft.com/3dmanufacturing/core/2015/02}"
PROD = "{http://schemas.microsoft.com/3dmanufacturing/production/2015/06}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("project", type=Path)
    parser.add_argument("report", type=Path, nargs="?")
    parser.add_argument("--expected-top-level", type=int)
    args = parser.parse_args()

    failures: list[str] = []
    with ZipFile(args.project) as archive:
        members = set(archive.namelist())
        required = {
            "3D/3dmodel.model",
            "3D/_rels/3dmodel.model.rels",
            "Metadata/model_settings.config",
            "Metadata/project_settings.config",
        }
        failures.extend(f"missing:{name}" for name in sorted(required - members))
        root = ET.fromstring(archive.read("3D/3dmodel.model"))
        config = ET.fromstring(archive.read("Metadata/model_settings.config"))
        object_models: dict[str, ET.Element] = {}
        for name in sorted(members):
            if name.startswith("3D/Objects/") and name.endswith(".model"):
                object_models["/" + name] = ET.fromstring(archive.read(name))

    if not object_models:
        failures.append("no_external_object_models")
    build_items = root.findall(f"{CORE}build/{CORE}item")
    build_ids = {item.get("objectid") for item in build_items}
    root_objects = {
        obj.get("id"): obj for obj in root.findall(f"{CORE}resources/{CORE}object")
        if obj.get("id") in build_ids
    }
    component_count = 0
    for object_id, obj in root_objects.items():
        components = obj.findall(f"{CORE}components/{CORE}component")
        if not components:
            failures.append(f"top_object_{object_id}_has_no_components")
        for component in components:
            component_count += 1
            path = component.get(f"{PROD}path")
            uid = component.get(f"{PROD}UUID")
            if not path:
                failures.append(f"component_{object_id}_{component.get('objectid')}_missing_p:path")
                continue
            if not uid:
                failures.append(f"component_{object_id}_{component.get('objectid')}_missing_p:UUID")
            model = object_models.get(path)
            if model is None:
                failures.append(f"component_path_not_packaged:{path}")
                continue
            leaf = model.find(f"{CORE}resources/{CORE}object[@id='{component.get('objectid')}']")
            if leaf is None:
                failures.append(f"component_object_not_found:{path}#{component.get('objectid')}")
            elif not leaf.get(f"{PROD}UUID"):
                failures.append(f"leaf_{component.get('objectid')}_missing_p:UUID")

    plate = config.find("plate")
    instances = [] if plate is None else plate.findall("model_instance")
    if len(instances) != len(build_items):
        failures.append(f"plate_instance_count_{len(instances)}_ne_build_count_{len(build_items)}")
    if args.expected_top_level is not None and len(build_items) != args.expected_top_level:
        failures.append(f"top_level_{len(build_items)}_ne_expected_{args.expected_top_level}")
    config_ids = {
        obj.get("id") for obj in config.findall("object")
    }
    if config_ids != build_ids:
        failures.append("model_settings_object_ids_do_not_match_build")

    payload = {
        "status": "PASS" if not failures else "FAIL",
        "project": str(args.project),
        "top_level_objects": len(build_items),
        "external_object_models": sorted(object_models),
        "components": component_count,
        "failures": failures,
        "rule": "Bambu print projects must retain root assemblies, external object models, relationships, p:path and UUID metadata",
    }
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    raise SystemExit(0 if payload["status"] == "PASS" else 1)


if __name__ == "__main__":
    main()
