#!/usr/bin/env python3
"""Release gate: fail if any 3MF component is below Z=0 or the model floats."""

from __future__ import annotations

import argparse
import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZipFile

CORE = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"
PROD = "http://schemas.microsoft.com/3dmanufacturing/production/2015/06"


def transform_values(value):
    values = [float(item) for item in value.split()] if value else []
    return values if len(values) == 12 else [1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0]


def validate(path: Path, tolerance: float):
    with ZipFile(path) as archive:
        main = ET.fromstring(archive.read("3D/3dmodel.model"))
        objects = ET.fromstring(archive.read("3D/Objects/object_1.model"))
    ns = {"m": CORE, "p": PROD}
    z_bounds = {}
    for obj in objects.findall(".//m:object", ns):
        values = [float(v.get("z")) for v in obj.findall(".//m:vertex", ns)]
        if values:
            z_bounds[obj.get("id")] = (min(values), max(values))
    item = main.find(".//m:build/m:item", ns)
    build_z = transform_values(item.get("transform") if item is not None else "")[11]
    parts = []
    for component in main.findall(".//m:component", ns):
        object_id = component.get("objectid")
        if object_id in z_bounds:
            local_min, local_max = z_bounds[object_id]
            component_z = transform_values(component.get("transform"))[11]
            parts.append((object_id, local_min + component_z + build_z, local_max + component_z + build_z))
    if not parts:
        raise RuntimeError(f"{path}: no printable components")
    global_min = min(part[1] for part in parts)
    below = [part for part in parts if part[1] < -tolerance]
    if below or abs(global_min) > tolerance:
        raise RuntimeError(
            f"{path}: Z gate failed, global_min={global_min:.6f}, below={below}"
        )
    print(f"PASS {path.name}: min_z={global_min:.6f}, components={len(parts)}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--tolerance", type=float, default=0.01)
    args = parser.parse_args()
    for path in args.files:
        validate(path, args.tolerance)


if __name__ == "__main__":
    main()
