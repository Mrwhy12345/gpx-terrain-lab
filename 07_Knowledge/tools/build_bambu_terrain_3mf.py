#!/usr/bin/env python3
"""Build a centered, three-colour terrain 3MF without inherited plate offsets."""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import build_bambu_one_plate_3mf as bambu


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source_dir", type=Path)
    parser.add_argument("template_3mf", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()

    specs = (
        ("01_Terrain_Low_Green.stl", 1),
        ("02_Terrain_Middle_Brown.stl", 2),
        ("03_Terrain_High_Gray.stl", 3),
    )
    parts = [
        (index + 1, args.source_dir / filename, extruder)
        for index, (filename, extruder) in enumerate(specs)
    ]
    args.destination.parent.mkdir(parents=True, exist_ok=True)

    with ZipFile(args.template_3mf) as template:
        members = {name: template.read(name) for name in template.namelist()}

    with tempfile.TemporaryDirectory() as temp:
        temp_dir = Path(temp)
        object_model = temp_dir / "object_1.model"
        root_model = temp_dir / "3dmodel.model"
        bambu.write_object_model(object_model, parts)
        bambu.write_main_model(root_model, parts)
        settings_xml = bambu.model_settings(parts).replace(
            "星溪线_四件同盘".encode(), "星溪线_沙盘地形_一体水系安装槽".encode()
        )

        project = json.loads(members["Metadata/project_settings.config"])
        project["filament_colour"] = ["#3F8E43", "#6F5034", "#858C91"]
        project["default_filament_colour"] = ["#3F8E43", "#6F5034", "#858C91"]
        project["print_sequence"] = "by layer"

        members["3D/Objects/object_1.model"] = object_model.read_bytes()
        members["3D/3dmodel.model"] = root_model.read_bytes()
        members["Metadata/model_settings.config"] = settings_xml
        members["Metadata/project_settings.config"] = json.dumps(
            project, ensure_ascii=False, indent=4
        ).encode()

        with ZipFile(args.destination, "w", ZIP_DEFLATED, allowZip64=True) as archive:
            for name, data in members.items():
                archive.writestr(name, data)
    print(args.destination)


if __name__ == "__main__":
    main()
