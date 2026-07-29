#!/usr/bin/env python3
"""Keep selected mesh parts inside one Bambu Studio 3MF assembly."""

from __future__ import annotations

import argparse
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


ROOT_MODEL = "3D/3dmodel.model"
MODEL_SETTINGS = "Metadata/model_settings.config"
CORE = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"
PRODUCTION = "http://schemas.microsoft.com/3dmanufacturing/production/2015/06"


def xml_bytes(root, namespace=None):
    if namespace:
        ET.register_namespace("", namespace)
    ET.register_namespace("p", PRODUCTION)
    ET.indent(root, space=" ")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--object-id", required=True)
    parser.add_argument("--keep-part-ids", nargs="+", required=True)
    args = parser.parse_args()
    keep = set(args.keep_part_ids)
    if args.source.resolve() == args.destination.resolve():
        raise ValueError("Source and destination must be different")

    with ZipFile(args.source) as archive:
        members = {name: archive.read(name) for name in archive.namelist()}

    root = ET.fromstring(members[ROOT_MODEL])
    wrapper = root.find(
        f"./{{{CORE}}}resources/{{{CORE}}}object[@id='{args.object_id}']"
    )
    if wrapper is None:
        raise ValueError(f"Top-level object {args.object_id} not found")
    components = wrapper.find(f"{{{CORE}}}components")
    if components is None:
        raise ValueError("Selected object has no components")
    paths = set()
    for component in list(components):
        if component.get("objectid") not in keep:
            components.remove(component)
        else:
            path = component.get(f"{{{PRODUCTION}}}path")
            if path:
                paths.add(path.lstrip("/"))
    if len(paths) != 1:
        raise ValueError(f"Expected one object model path, found {sorted(paths)}")
    object_model_path = next(iter(paths))
    members[ROOT_MODEL] = xml_bytes(root, CORE)

    object_model = ET.fromstring(members[object_model_path])
    resources = object_model.find(f"{{{CORE}}}resources")
    found = set()
    for obj in list(resources.findall(f"{{{CORE}}}object")):
        if obj.get("id") not in keep:
            resources.remove(obj)
        else:
            found.add(obj.get("id"))
    missing = keep - found
    if missing:
        raise ValueError(f"Part IDs not found in mesh model: {sorted(missing)}")
    members[object_model_path] = xml_bytes(object_model, CORE)

    settings = ET.fromstring(members[MODEL_SETTINGS])
    config_object = settings.find(f"./object[@id='{args.object_id}']")
    if config_object is None:
        raise ValueError("Object missing from Bambu settings")
    for part in list(config_object.findall("part")):
        if part.get("id") not in keep:
            config_object.remove(part)
    face_total = sum(
        int(part.find("mesh_stat").get("face_count", "0"))
        for part in config_object.findall("part")
    )
    face_metadata = next(
        node for node in config_object.findall("metadata")
        if node.get("face_count") is not None
    )
    face_metadata.set("face_count", str(face_total))
    members[MODEL_SETTINGS] = xml_bytes(settings)

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

    print(
        {
            "source": str(args.source),
            "destination": str(args.destination),
            "object_id": args.object_id,
            "kept_part_ids": sorted(keep),
            "face_count": face_total,
        }
    )


if __name__ == "__main__":
    main()
