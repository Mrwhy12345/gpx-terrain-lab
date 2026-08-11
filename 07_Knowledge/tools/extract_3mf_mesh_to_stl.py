#!/usr/bin/env python3
"""Extract the first raw mesh from a Bambu-style 3MF as binary STL."""

from __future__ import annotations

import argparse
import struct
import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZipFile


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("project", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    with ZipFile(args.project) as archive:
        root = ET.fromstring(archive.read("3D/Objects/object_1.model"))
    vertices = [
        (float(v.get("x")), float(v.get("y")), float(v.get("z")))
        for v in root.iter()
        if v.tag.rsplit("}", 1)[-1] == "vertex"
    ]
    triangles = [
        (int(t.get("v1")), int(t.get("v2")), int(t.get("v3")))
        for t in root.iter()
        if t.tag.rsplit("}", 1)[-1] == "triangle"
    ]
    args.destination.parent.mkdir(parents=True, exist_ok=True)
    with args.destination.open("wb") as handle:
        handle.write(b"Extracted from 3MF".ljust(80, b"\0"))
        handle.write(struct.pack("<I", len(triangles)))
        for tri in triangles:
            handle.write(struct.pack("<3f", 0.0, 0.0, 0.0))
            for index in tri:
                handle.write(struct.pack("<3f", *vertices[index]))
            handle.write(struct.pack("<H", 0))
    print(f"vertices={len(vertices)} triangles={len(triangles)} {args.destination}")


if __name__ == "__main__":
    main()
