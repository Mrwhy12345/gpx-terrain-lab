#!/usr/bin/env python3
"""Set the display colours of filament slots in a Bambu Studio 3MF."""

from __future__ import annotations

import argparse
import json
import shutil
import tempfile
import zipfile
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input_3mf", type=Path)
    parser.add_argument("output_3mf", type=Path)
    parser.add_argument(
        "--colors",
        nargs="+",
        default=["#D8B27C", "#E84B3C", "#27AEE4"],
        help="Hex colours in extruder order.",
    )
    args = parser.parse_args()

    with tempfile.TemporaryDirectory() as tmp_dir:
        unpacked = Path(tmp_dir) / "unpacked"
        unpacked.mkdir()

        with zipfile.ZipFile(args.input_3mf) as archive:
            archive.extractall(unpacked)

        settings_path = unpacked / "Metadata" / "project_settings.config"
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
        settings["filament_colour"] = args.colors
        settings["default_filament_colour"] = args.colors
        settings_path.write_text(
            json.dumps(settings, ensure_ascii=False, indent=4) + "\n",
            encoding="utf-8",
        )

        args.output_3mf.parent.mkdir(parents=True, exist_ok=True)
        archive_base = Path(tmp_dir) / "patched"
        zip_path = Path(
            shutil.make_archive(str(archive_base), "zip", root_dir=unpacked)
        )
        shutil.move(zip_path, args.output_3mf)


if __name__ == "__main__":
    main()
