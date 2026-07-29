#!/usr/bin/env python3
"""Translate SYS01 STL parts into a safe four-piece, one-plate layout."""

from __future__ import annotations

import struct
from pathlib import Path


ROOT = Path("06_Experiment/SYS01_TerrainPackagingPrototype")
OUTPUT = ROOT / "data/V006_one_plate_parts"
TERRAIN_TEMPLATE_OUTPUT = ROOT / "data/V006_terrain_template_additions"

PARTS = (
    (
        ROOT / "data/V002_parts/01_Terrain_Low_Green_Grooved.stl",
        "01_Terrain_Low_Green.stl",
        (65.0, 60.0, 0.0),
    ),
    (
        ROOT / "data/V002_parts/02_Terrain_And_Villages_Brown_Grooved.stl",
        "02_Terrain_Middle_Brown.stl",
        (65.0, 60.0, 0.0),
    ),
    (
        ROOT / "data/V002_parts/03_Terrain_High_Gray_Grooved.stl",
        "03_Terrain_High_Gray.stl",
        (65.0, 60.0, 0.0),
    ),
    (
        ROOT / "data/V007_parts/01_Base_Gray_SVGLogoRecess.stl",
        "04_Base_Gray.stl",
        (-75.0, 60.0, 8.0),
    ),
    (
        ROOT / "data/V007_parts/02_Labels_HiraginoSansGB_And_SVGLogo_Brown.stl",
        "05_Base_Labels_Logo_Brown.stl",
        (-75.0, 60.0, 8.0),
    ),
    (
        Path(
            "06_Experiment/S02_ColorTest/result/"
            "three_physical_pieces_1.50_recessed/03_Trail/"
            "02_Trail_Red_SeparatePrint.stl"
        ),
        "06_Trail_Red.stl",
        (-65.0, -40.0, 0.0),
    ),
    (
        ROOT / "data/V002_parts/05_Water_Blue_SeparatePrint.stl",
        "07_Water_Blue.stl",
        (55.0, -45.0, 0.0),
    ),
)

TERRAIN_TEMPLATE_PARTS = (
    (
        ROOT / "data/V007_parts/01_Base_Gray_SVGLogoRecess.stl",
        "04_Base_Gray.stl",
        (-115.0, 30.0, 8.0),
    ),
    (
        ROOT / "data/V007_parts/02_Labels_HiraginoSansGB_And_SVGLogo_Brown.stl",
        "05_Base_Labels_Logo_Brown.stl",
        (-115.0, 30.0, 8.0),
    ),
    (
        Path(
            "06_Experiment/S02_ColorTest/result/"
            "three_physical_pieces_1.50_recessed/03_Trail/"
            "02_Trail_Red_SeparatePrint.stl"
        ),
        "06_Trail_Red.stl",
        (-60.0, -75.0, 0.0),
    ),
    (
        ROOT / "data/V002_parts/05_Water_Blue_SeparatePrint.stl",
        "07_Water_Blue.stl",
        (45.0, -75.0, 0.0),
    ),
)


def translate_binary_stl(source, destination, offset):
    data = bytearray(source.read_bytes())
    triangle_count = struct.unpack_from("<I", data, 80)[0]
    for triangle in range(triangle_count):
        start = 84 + triangle * 50 + 12
        for vertex in range(3):
            position = start + vertex * 12
            values = list(struct.unpack_from("<fff", data, position))
            values = [values[axis] + offset[axis] for axis in range(3)]
            struct.pack_into("<fff", data, position, *values)
    destination.write_bytes(data)


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for source, filename, offset in PARTS:
        destination = OUTPUT / filename
        translate_binary_stl(source, destination, offset)
        print(f"{filename}: offset={offset}")
    TERRAIN_TEMPLATE_OUTPUT.mkdir(parents=True, exist_ok=True)
    for source, filename, offset in TERRAIN_TEMPLATE_PARTS:
        destination = TERRAIN_TEMPLATE_OUTPUT / filename
        translate_binary_stl(source, destination, offset)
        print(f"template+{filename}: offset={offset}")


if __name__ == "__main__":
    main()
