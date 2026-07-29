#!/usr/bin/env python3
"""Add a missing Bambu Studio plate model_instance entry to a 3MF project."""

from __future__ import annotations

import argparse
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


CONFIG_PATH = "Metadata/model_settings.config"


def repair(source: Path, destination: Path) -> None:
    with ZipFile(source, "r") as archive:
        members = {name: archive.read(name) for name in archive.namelist()}

    root = ET.fromstring(members[CONFIG_PATH])
    plate = root.find("plate")
    object_node = root.find("object")
    if plate is None or object_node is None:
        raise ValueError("3MF lacks the expected Bambu object or plate metadata")

    if plate.find("model_instance") is None:
        instance = ET.SubElement(plate, "model_instance")
        ET.SubElement(
            instance,
            "metadata",
            {"key": "object_id", "value": object_node.attrib["id"]},
        )
        ET.SubElement(instance, "metadata", {"key": "instance_id", "value": "0"})
        ET.SubElement(instance, "metadata", {"key": "identify_id", "value": "1"})

    ET.indent(root, space="  ")
    members[CONFIG_PATH] = ET.tostring(
        root, encoding="utf-8", xml_declaration=True
    )

    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        dir=destination.parent, suffix=".3mf", delete=False
    ) as temporary:
        temporary_path = Path(temporary.name)

    try:
        with ZipFile(temporary_path, "w", ZIP_DEFLATED) as archive:
            for name, data in members.items():
                archive.writestr(name, data)
        temporary_path.replace(destination)
    finally:
        temporary_path.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    repair(args.source, args.destination)


if __name__ == "__main__":
    main()
