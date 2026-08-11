#!/usr/bin/env python3
"""Build a centered Bambu Studio 3MF from an explicit STL/extruder manifest."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

sys.path.insert(0, str(Path(__file__).parent))
import build_bambu_one_plate_3mf as bambu


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("template", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--name", required=True)
    parser.add_argument("--colors", required=True, help="Comma-separated #RRGGBB")
    parser.add_argument(
        "--part", action="append", required=True,
        help="STL path followed by :extruder-number",
    )
    args = parser.parse_args()
    parts = []
    for index, value in enumerate(args.part, 1):
        path_text, extruder_text = value.rsplit(":", 1)
        path = Path(path_text)
        if not path.exists():
            raise FileNotFoundError(path)
        parts.append((index, path, int(extruder_text)))

    with ZipFile(args.template) as template:
        members = {name: template.read(name) for name in template.namelist()}
    with tempfile.TemporaryDirectory() as temp:
        temp_dir = Path(temp)
        object_model = temp_dir / "object_1.model"
        root_model = temp_dir / "3dmodel.model"
        bambu.write_object_model(object_model, parts)
        bambu.write_main_model(root_model, parts)
        settings = bambu.model_settings(parts).replace(
            "星溪线_四件同盘".encode(), args.name.encode()
        )
        project = json.loads(members["Metadata/project_settings.config"])
        colors = args.colors.split(",")
        project["filament_colour"] = colors
        project["default_filament_colour"] = colors
        project["print_sequence"] = "by layer"
        members["3D/Objects/object_1.model"] = object_model.read_bytes()
        members["3D/3dmodel.model"] = root_model.read_bytes()
        members["Metadata/model_settings.config"] = settings
        members["Metadata/project_settings.config"] = json.dumps(
            project, ensure_ascii=False, indent=4
        ).encode()
        args.destination.parent.mkdir(parents=True, exist_ok=True)
        with ZipFile(args.destination, "w", ZIP_DEFLATED, allowZip64=True) as output:
            for name, data in members.items():
                output.writestr(name, data)
    print(args.destination)


if __name__ == "__main__":
    main()
