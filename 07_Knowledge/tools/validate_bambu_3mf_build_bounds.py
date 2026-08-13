#!/usr/bin/env python3
"""Reject 3MF projects whose final model bounds are outside the print plate."""

import argparse
import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZipFile

CORE = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"


def matrix(value):
    values = [float(item) for item in value.split()] if value else []
    return values if len(values) == 12 else [1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("project", type=Path)
    parser.add_argument("--plate-width", type=float, default=350.0)
    parser.add_argument("--plate-depth", type=float, default=320.0)
    args = parser.parse_args()
    with ZipFile(args.project) as archive:
        root = ET.fromstring(archive.read("3D/3dmodel.model"))
        objects = ET.fromstring(archive.read("3D/Objects/object_1.model"))
    ns = {"m": CORE}
    bounds = {}
    for obj in objects.findall(".//m:object", ns):
        vertices = obj.findall(".//m:vertex", ns)
        if vertices:
            bounds[obj.get("id")] = (
                min(float(v.get("x")) for v in vertices),
                max(float(v.get("x")) for v in vertices),
                min(float(v.get("y")) for v in vertices),
                max(float(v.get("y")) for v in vertices),
            )
    components = root.findall(".//m:component", ns)
    build = root.find(".//m:build/m:item", ns)
    build_matrix = matrix(build.get("transform") if build is not None else "")
    final = []
    for component in components:
        if component.get("objectid") not in bounds:
            continue
        x0, x1, y0, y1 = bounds[component.get("objectid")]
        transform = matrix(component.get("transform"))
        final.append((
            x0 + transform[9] + build_matrix[9],
            x1 + transform[9] + build_matrix[9],
            y0 + transform[10] + build_matrix[10],
            y1 + transform[10] + build_matrix[10],
        ))
    if not final:
        raise SystemExit("FAIL: no mesh component bounds")
    result = (
        min(item[0] for item in final), max(item[1] for item in final),
        min(item[2] for item in final), max(item[3] for item in final),
    )
    if result[0] < 0 or result[1] > args.plate_width or result[2] < 0 or result[3] > args.plate_depth:
        raise SystemExit(f"FAIL {args.project.name}: XY bounds={result}")
    print(f"PASS {args.project.name}: XY bounds={result}")


if __name__ == "__main__":
    main()
