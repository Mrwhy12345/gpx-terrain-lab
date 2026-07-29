#!/usr/bin/env python3
"""Assign Bambu Studio 3MF parts to extruders in their existing order."""

from __future__ import annotations

import argparse
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


CONFIG_PATH = "Metadata/model_settings.config"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--extruders", nargs="+", type=int, required=True)
    args = parser.parse_args()

    with ZipFile(args.source, "r") as archive:
        members = {name: archive.read(name) for name in archive.namelist()}
    root = ET.fromstring(members[CONFIG_PATH])
    parts = root.findall("./object/part")
    if len(parts) != len(args.extruders):
        raise ValueError(
            f"Found {len(parts)} parts but received {len(args.extruders)} extruders"
        )
    for part, extruder in zip(parts, args.extruders):
        metadata = next(
            node for node in part.findall("metadata") if node.get("key") == "extruder"
        )
        metadata.set("value", str(extruder))
    ET.indent(root, space="  ")
    members[CONFIG_PATH] = ET.tostring(
        root, encoding="utf-8", xml_declaration=True
    )

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


if __name__ == "__main__":
    main()
