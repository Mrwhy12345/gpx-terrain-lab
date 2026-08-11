#!/usr/bin/env python3
"""Create canonical individual and one-plate STL layouts for a GPX job."""

from __future__ import annotations

import argparse
import struct
from pathlib import Path


def transform(source, destination, offset=(0, 0, 0), xy_scale=1.0):
    data = bytearray(source.read_bytes())
    count = struct.unpack_from("<I", data, 80)[0]
    if len(data) != 84 + count * 50:
        raise ValueError(f"{source} is not a binary STL")
    for triangle in range(count):
        start = 84 + triangle * 50 + 12
        for vertex in range(3):
            pos = start + vertex * 12
            xyz = list(struct.unpack_from("<fff", data, pos))
            struct.pack_into(
                "<fff", data, pos,
                xyz[0] * xy_scale + offset[0],
                xyz[1] * xy_scale + offset[1],
                xyz[2] + offset[2],
            )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(data)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("individual", type=Path)
    parser.add_argument("plate", type=Path)
    parser.add_argument(
        "--xy-scale", type=float, default=1.0,
        help="Uniform XY scale around the model origin; Z remains unchanged.",
    )
    parser.add_argument("--terrain-center-x", type=float, default=0.0)
    parser.add_argument("--terrain-center-y", type=float, default=0.0)
    args = parser.parse_args()
    mapping = {
        "01_Terrain_Low_Green.stl": "01_Terrain_Low_Green_Grooved.stl",
        "02_Terrain_Middle_Brown.stl": "02_Terrain_And_Villages_Brown_Grooved.stl",
        "03_Terrain_High_Gray.stl": "03_Terrain_High_Gray_Grooved.stl",
        "04_Base_Gray.stl": "07_Base_Gray.stl",
        "05_Base_Labels_Logo_Brown.stl": "08_Labels_Logo_Brown.stl",
        "06_Trail_Red.stl": "10_Trail_Red_SeparatePrint.stl",
        "07_Water_Blue.stl": "05_Water_Blue_SeparatePrint.stl",
    }
    for destination, source in mapping.items():
        src = args.source / source
        dst = args.individual / destination
        if destination.startswith(("01_", "02_", "03_")):
            transform(
                src, dst,
                (-args.terrain_center_x * args.xy_scale,
                 -args.terrain_center_y * args.xy_scale, 0),
                args.xy_scale,
            )
        elif destination.startswith(("04_", "05_")):
            transform(src, dst, (0, 0, 8), args.xy_scale)
        else:
            transform(src, dst, xy_scale=args.xy_scale)
    offsets = {
        "01_Terrain_Low_Green.stl": (65, 60, 0),
        "02_Terrain_Middle_Brown.stl": (65, 60, 0),
        "03_Terrain_High_Gray.stl": (65, 60, 0),
        "04_Base_Gray.stl": (-65, 60, 0),
        "05_Base_Labels_Logo_Brown.stl": (-65, 60, 0),
        "06_Trail_Red.stl": (-65, -48, 0),
        "07_Water_Blue.stl": (55, -48, 0),
    }
    for name, offset in offsets.items():
        transform(args.individual / name, args.plate / name, offset)


if __name__ == "__main__":
    main()
