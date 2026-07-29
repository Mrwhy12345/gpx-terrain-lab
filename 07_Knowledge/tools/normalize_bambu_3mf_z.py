#!/usr/bin/env python3
"""Move a Bambu 3MF assembly so its final world-space minimum Z is exactly 0."""

from __future__ import annotations

import argparse
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

CORE = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"
PROD = "http://schemas.microsoft.com/3dmanufacturing/production/2015/06"
ET.register_namespace("", CORE)
ET.register_namespace("p", PROD)


def translation(transform):
    values = [float(value) for value in transform.split()] if transform else []
    return values if len(values) == 12 else [1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()

    with ZipFile(args.source) as archive:
        files = {name: archive.read(name) for name in archive.namelist()}
    main_root = ET.fromstring(files["3D/3dmodel.model"])
    object_root = ET.fromstring(files["3D/Objects/object_1.model"])
    ns = {"m": CORE, "p": PROD}

    mesh_z = {}
    for obj in object_root.findall(".//m:object", ns):
        vertices = obj.findall(".//m:vertex", ns)
        if vertices:
            mesh_z[obj.get("id")] = min(float(vertex.get("z")) for vertex in vertices)

    component_minima = []
    components = []
    for component in main_root.findall(".//m:component", ns):
        object_id = component.get("objectid")
        if object_id in mesh_z:
            matrix = translation(component.get("transform"))
            component_minima.append(mesh_z[object_id] + matrix[11])
            components.append((component, matrix))
    if not component_minima:
        raise RuntimeError("No mesh components found")

    item = main_root.find(".//m:build/m:item", ns)
    if item is None:
        raise RuntimeError("No build item found")
    build_matrix = translation(item.get("transform"))
    current_min_z = min(component_minima) + build_matrix[11]
    # Bake the entire Z correction into every component. Some slicer views and
    # command-line checks ignore the build-item transform, so relying on it can
    # make a correct project still appear below the bed.
    component_shift = build_matrix[11] - current_min_z
    for component, matrix in components:
        matrix[11] += component_shift
        component.set("transform", " ".join(f"{value:.9g}" for value in matrix))
    build_matrix[11] = 0.0
    item.set("transform", " ".join(f"{value:.9g}" for value in build_matrix))
    files["3D/3dmodel.model"] = ET.tostring(
        main_root, encoding="utf-8", xml_declaration=True
    )
    config = ET.fromstring(files["Metadata/model_settings.config"])
    for part in config.findall(".//part"):
        matrix_meta = part.find("metadata[@key='matrix']")
        offset_meta = part.find("metadata[@key='source_offset_z']")
        if matrix_meta is not None:
            matrix_values = [float(value) for value in matrix_meta.get("value").split()]
            if len(matrix_values) == 16:
                matrix_values[11] += component_shift
                matrix_meta.set(
                    "value", " ".join(f"{value:.9g}" for value in matrix_values)
                )
        if offset_meta is not None:
            offset_meta.set(
                "value", f"{float(offset_meta.get('value')) + component_shift:.9g}"
            )
    files["Metadata/model_settings.config"] = ET.tostring(
        config, encoding="utf-8", xml_declaration=True
    )

    args.destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        dir=args.destination.parent, suffix=".3mf", delete=False
    ) as handle:
        temporary = Path(handle.name)
    with ZipFile(temporary, "w", ZIP_DEFLATED, allowZip64=True) as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    temporary.replace(args.destination)
    print(f"previous_min_z={current_min_z:.6f}")
    print(f"applied_component_shift_z={component_shift:.6f}")


if __name__ == "__main__":
    main()
