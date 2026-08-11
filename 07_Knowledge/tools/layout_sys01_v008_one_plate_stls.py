#!/usr/bin/env python3
"""Lay out the V008 terrain, base, trail, and unified water on one plate."""

from __future__ import annotations

import struct
import sys
from pathlib import Path


ROOT = Path("06_Experiment/SYS01_TerrainPackagingPrototype")


def translate_binary_stl(source: Path, destination: Path, offset):
    data = bytearray(source.read_bytes())
    triangle_count = struct.unpack_from("<I", data, 80)[0]
    if len(data) != 84 + triangle_count * 50:
        raise ValueError(f"{source} is not a binary STL")
    for triangle in range(triangle_count):
        start = 84 + triangle * 50 + 12
        for vertex in range(3):
            position = start + vertex * 12
            values = list(struct.unpack_from("<fff", data, position))
            values = [values[axis] + offset[axis] for axis in range(3)]
            struct.pack_into("<fff", data, position, *values)
    destination.write_bytes(data)


def main():
    version = sys.argv[1] if len(sys.argv) > 1 else "V008"
    if version not in {"V008", "V009", "V010", "V011", "V012"}:
        raise SystemExit("Version must be V008, V009, V010, V011, or V012")
    output = ROOT / f"data/{version}_one_plate_parts"
    if version in {"V010", "V011", "V012"}:
        low = ROOT / "data/V010_parts/01_Terrain_Low_Green_Grooved.stl"
        middle = ROOT / "data/V010_parts/02_Terrain_And_Villages_Brown_Grooved.stl"
        high = ROOT / "data/V010_parts/03_Terrain_High_Gray_Grooved.stl"
        water = ROOT / "data/V010_parts/05_Water_Blue_SeparatePrint.stl"
    else:
        low = (
            ROOT / "data/V009_parts/01_Terrain_Low_BottomLoadWaterGroove.stl"
            if version == "V009"
            else ROOT / "data/V008_parts/01_Terrain_Low_Green_UnifiedWaterGroove.stl"
        )
        middle = ROOT / "data/V002_parts/02_Terrain_And_Villages_Brown_Grooved.stl"
        high = ROOT / "data/V002_parts/03_Terrain_High_Gray_Grooved.stl"
        water = (
            ROOT / "data/V009_parts/05_Water_Blue_BottomLoad_Unified.stl"
            if version == "V009"
            else ROOT / "data/V008_parts/05_Water_Blue_Unified_Underpass.stl"
        )
    parts = (
        (low, "01_Terrain_Low_Green.stl", (65.0, 60.0, 0.0)),
        (middle, "02_Terrain_Middle_Brown.stl", (65.0, 60.0, 0.0)),
        (high, "03_Terrain_High_Gray.stl", (65.0, 60.0, 0.0)),
        (
            ROOT / ("data/V012_base_parts/01_Base_Gray.stl" if version == "V012" else "data/V007_parts/01_Base_Gray_SVGLogoRecess.stl"),
            "04_Base_Gray.stl",
            (-75.0, 60.0, 8.0),
        ),
        (
            ROOT / ("data/V012_base_parts/02_Labels_Logo_Brown.stl" if version == "V012" else "data/V007_parts/02_Labels_HiraginoSansGB_And_SVGLogo_Brown.stl"),
            "05_Base_Labels_Logo_Brown.stl",
            (-75.0, 60.0, 8.0),
        ),
        (
            (
                ROOT / "data/V011_trail_parts/02_Trail_Red_SeparatePrint_StartArrow_FinishTarget.stl"
                if version in {"V011", "V012"}
                else Path("06_Experiment/S02_ColorTest/result/three_physical_pieces_1.50_recessed/03_Trail/02_Trail_Red_SeparatePrint.stl")
            ),
            "06_Trail_Red.stl",
            (-65.0, -40.0, 0.0),
        ),
        (water, "07_Water_Blue.stl", (55.0, -45.0, 0.0)),
    )
    output.mkdir(parents=True, exist_ok=True)
    for source, filename, offset in parts:
        destination = output / filename
        translate_binary_stl(source, destination, offset)
        print(f"{filename}: offset={offset}")


if __name__ == "__main__":
    main()
