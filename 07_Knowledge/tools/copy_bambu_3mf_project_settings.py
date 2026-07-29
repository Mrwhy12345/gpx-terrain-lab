#!/usr/bin/env python3
"""Copy validated printer/process settings from one Bambu 3MF to another."""

from __future__ import annotations

import argparse
import tempfile
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


SETTINGS_PATH = "Metadata/project_settings.config"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("settings_template", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()

    with ZipFile(args.source, "r") as archive:
        members = {name: archive.read(name) for name in archive.namelist()}
    with ZipFile(args.settings_template, "r") as archive:
        members[SETTINGS_PATH] = archive.read(SETTINGS_PATH)

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
