#!/usr/bin/env python3
"""Keep selected top-level printable objects in a Bambu Studio 3MF.

The tool updates the root 3MF model, Bambu model settings, plate instances,
assembly entries, production relationships, and removes object model members
that are no longer referenced.  It never edits the source archive in place.
"""

from __future__ import annotations

import argparse
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


ROOT_MODEL = "3D/3dmodel.model"
MODEL_SETTINGS = "Metadata/model_settings.config"
MODEL_RELS = "3D/_rels/3dmodel.model.rels"

CORE = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"
PRODUCTION = "http://schemas.microsoft.com/3dmanufacturing/production/2015/06"
RELATIONSHIPS = "http://schemas.openxmlformats.org/package/2006/relationships"

def production_path(component: ET.Element) -> str | None:
    return component.get(f"{{{PRODUCTION}}}path")


def write_xml(root: ET.Element, default_namespace: str | None = None) -> bytes:
    if default_namespace:
        ET.register_namespace("", default_namespace)
    ET.register_namespace("p", PRODUCTION)
    ET.indent(root, space=" ")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--keep-object-ids", nargs="+", required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    keep_ids = set(args.keep_object_ids)
    if args.source.resolve() == args.destination.resolve():
        raise ValueError("Source and destination must be different")

    with ZipFile(args.source) as archive:
        members = {name: archive.read(name) for name in archive.namelist()}

    root_model = ET.fromstring(members[ROOT_MODEL])
    resources = root_model.find(f"{{{CORE}}}resources")
    build = root_model.find(f"{{{CORE}}}build")
    if resources is None or build is None:
        raise ValueError("Root model has no resources/build")

    removed_ids = []
    for obj in list(resources.findall(f"{{{CORE}}}object")):
        object_id = obj.get("id")
        if object_id not in keep_ids:
            removed_ids.append(object_id)
            resources.remove(obj)
    for item in list(build.findall(f"{{{CORE}}}item")):
        if item.get("objectid") not in keep_ids:
            build.remove(item)

    existing_ids = {
        obj.get("id") for obj in resources.findall(f"{{{CORE}}}object")
    }
    missing = keep_ids - existing_ids
    if missing:
        raise ValueError(f"Requested object IDs not found: {sorted(missing)}")

    referenced_models = {
        production_path(component).lstrip("/")
        for component in resources.findall(f".//{{{CORE}}}component")
        if production_path(component)
    }
    members[ROOT_MODEL] = write_xml(root_model, CORE)

    settings = ET.fromstring(members[MODEL_SETTINGS])
    for obj in list(settings.findall("object")):
        if obj.get("id") not in keep_ids:
            settings.remove(obj)
    plate = settings.find("plate")
    if plate is not None:
        for instance in list(plate.findall("model_instance")):
            object_id = next(
                (
                    node.get("value")
                    for node in instance.findall("metadata")
                    if node.get("key") == "object_id"
                ),
                None,
            )
            if object_id not in keep_ids:
                plate.remove(instance)
    assemble = settings.find("assemble")
    if assemble is not None:
        for item in list(assemble.findall("assemble_item")):
            if item.get("object_id") not in keep_ids:
                assemble.remove(item)
    members[MODEL_SETTINGS] = write_xml(settings)

    relationships = ET.fromstring(members[MODEL_RELS])
    for relation in list(relationships):
        target = (relation.get("Target") or "").lstrip("/")
        if target.startswith("3D/Objects/") and target not in referenced_models:
            relationships.remove(relation)
    members[MODEL_RELS] = write_xml(relationships, RELATIONSHIPS)

    removed_members = []
    for name in list(members):
        if name.startswith("3D/Objects/") and name not in referenced_models:
            removed_members.append(name)
            del members[name]

    args.destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        dir=args.destination.parent, suffix=".3mf", delete=False
    ) as temporary:
        temporary_path = Path(temporary.name)
    try:
        with ZipFile(temporary_path, "w", ZIP_DEFLATED) as archive:
            for name, data in members.items():
                archive.writestr(name, data)
        temporary_path.replace(args.destination)
    finally:
        temporary_path.unlink(missing_ok=True)

    report = {
        "source": str(args.source),
        "destination": str(args.destination),
        "kept_object_ids": sorted(keep_ids),
        "removed_object_ids": sorted(removed_ids),
        "referenced_object_models": sorted(referenced_models),
        "removed_archive_members": sorted(removed_members),
    }
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        import json

        args.report.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print(report)


if __name__ == "__main__":
    main()
