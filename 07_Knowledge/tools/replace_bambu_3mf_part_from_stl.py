#!/usr/bin/env python3
"""Replace one mesh inside a Bambu Studio 3MF with a binary STL mesh."""

from __future__ import annotations

import argparse
import re
import struct
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


OBJECT_MODEL = "3D/Objects/object_1.model"
ROOT_MODEL = "3D/3dmodel.model"
MODEL_SETTINGS = "Metadata/model_settings.config"


def read_binary_stl(path):
    data = path.read_bytes()
    count = struct.unpack_from("<I", data, 80)[0]
    vertices = []
    triangles = []
    index_by_vertex = {}
    offset = 84
    for _ in range(count):
        offset += 12  # normal
        face = []
        for _ in range(3):
            vertex = struct.unpack_from("<fff", data, offset)
            offset += 12
            key = tuple(round(value, 7) for value in vertex)
            index = index_by_vertex.get(key)
            if index is None:
                index = len(vertices)
                vertices.append(vertex)
                index_by_vertex[key] = index
            face.append(index)
        triangles.append(tuple(face))
        offset += 2
    return vertices, triangles


def mesh_xml(vertices, triangles):
    vertex_lines = "\n".join(
        f'     <vertex x="{x:.7g}" y="{y:.7g}" z="{z:.7g}"/>'
        for x, y, z in vertices
    )
    triangle_lines = "\n".join(
        f'     <triangle v1="{a}" v2="{b}" v3="{c}"/>'
        for a, b, c in triangles
    )
    return (
        "   <mesh>\n"
        "    <vertices>\n"
        f"{vertex_lines}\n"
        "    </vertices>\n"
        "    <triangles>\n"
        f"{triangle_lines}\n"
        "    </triangles>\n"
        "   </mesh>"
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source_3mf", type=Path)
    parser.add_argument("stl", type=Path)
    parser.add_argument("destination_3mf", type=Path)
    parser.add_argument("--part", type=int, default=1)
    parser.add_argument("--z-offset", type=float, default=0.0)
    parser.add_argument("--part-name")
    args = parser.parse_args()

    vertices, triangles = read_binary_stl(args.stl)
    mins = [min(vertex[i] for vertex in vertices) for i in range(3)]
    maxs = [max(vertex[i] for vertex in vertices) for i in range(3)]
    center = [(low + high) / 2 for low, high in zip(mins, maxs)]
    component_center = [center[0], center[1], center[2] + args.z_offset]
    centered = [
        tuple(vertex[i] - center[i] for i in range(3)) for vertex in vertices
    ]

    with ZipFile(args.source_3mf) as archive:
        members = {name: archive.read(name) for name in archive.namelist()}

    model = members[OBJECT_MODEL].decode("utf-8")
    marker = f'<object id="{args.part}"'
    object_start = model.index(marker)
    mesh_start = model.index("   <mesh>", object_start)
    mesh_end = model.index("   </mesh>", mesh_start) + len("   </mesh>")
    model = model[:mesh_start] + mesh_xml(centered, triangles) + model[mesh_end:]
    members[OBJECT_MODEL] = model.encode("utf-8")

    # Bambu stores the same part transform twice: once in
    # model_settings.config and once on the component in 3D/3dmodel.model.
    # Both must be updated or the new mesh can be buried inside another part.
    root_model = members[ROOT_MODEL].decode("utf-8")
    component_pattern = re.compile(
        rf'(<component\b[^>]*\bobjectid="{args.part}"[^>]*\btransform=")([^"]+)(")'
    )
    component_match = component_pattern.search(root_model)
    if component_match is None:
        raise ValueError(f"Root component for part {args.part} not found")
    component_transform = [
        float(value) for value in component_match.group(2).split()
    ]
    if len(component_transform) != 12:
        raise ValueError("Expected a 12-value 3MF component transform")
    component_transform[9:12] = component_center
    replacement_transform = " ".join(
        f"{value:.9g}" for value in component_transform
    )
    root_model = (
        root_model[: component_match.start(2)]
        + replacement_transform
        + root_model[component_match.end(2) :]
    )
    members[ROOT_MODEL] = root_model.encode("utf-8")

    settings = ET.fromstring(members[MODEL_SETTINGS])
    part = settings.find(f"./object/part[@id='{args.part}']")
    if part is None:
        raise ValueError(f"Part {args.part} not found")
    if args.part_name:
        for key in ("name", "source_file"):
            metadata = next(
                node
                for node in part.findall("metadata")
                if node.get("key") == key
            )
            metadata.set("value", args.part_name)
    matrix = next(
        node for node in part.findall("metadata") if node.get("key") == "matrix"
    )
    matrix_values = [float(value) for value in matrix.get("value").split()]
    matrix_values[3], matrix_values[7], matrix_values[11] = component_center
    matrix.set("value", " ".join(f"{value:.9g}" for value in matrix_values))
    for axis, value in zip(("x", "y", "z"), component_center):
        metadata = next(
            node
            for node in part.findall("metadata")
            if node.get("key") == f"source_offset_{axis}"
        )
        metadata.set("value", f"{value:.9g}")
    mesh_stat = part.find("mesh_stat")
    mesh_stat.set("face_count", str(len(triangles)))
    object_node = settings.find("./object")
    total_faces = sum(
        int(node.get("face_count", "0"))
        for node in object_node.findall("./part/mesh_stat")
    )
    object_node.find("metadata[@face_count]").set("face_count", str(total_faces))
    ET.indent(settings, space="  ")
    members[MODEL_SETTINGS] = ET.tostring(
        settings, encoding="utf-8", xml_declaration=True
    )

    args.destination_3mf.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        dir=args.destination_3mf.parent, suffix=".3mf", delete=False
    ) as temporary:
        temporary_path = Path(temporary.name)
    try:
        with ZipFile(temporary_path, "w", ZIP_DEFLATED) as archive:
            for name, data in members.items():
                archive.writestr(name, data)
        temporary_path.replace(args.destination_3mf)
    finally:
        temporary_path.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
