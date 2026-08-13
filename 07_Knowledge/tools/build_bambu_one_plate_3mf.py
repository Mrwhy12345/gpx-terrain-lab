#!/usr/bin/env python3
"""Build a Bambu-compatible multi-part 3MF from pre-positioned binary STLs."""

from __future__ import annotations

import argparse
import json
import struct
import tempfile
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


CORE = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"
PROD = "http://schemas.microsoft.com/3dmanufacturing/production/2015/06"
ET.register_namespace("", CORE)
ET.register_namespace("p", PROD)


def read_binary_stl(path: Path):
    data = path.read_bytes()
    count = struct.unpack_from("<I", data, 80)[0]
    if len(data) != 84 + count * 50:
        raise ValueError(f"{path} is not a binary STL")
    vertices: list[tuple[float, float, float]] = []
    index: dict[tuple[float, float, float], int] = {}
    triangles: list[tuple[int, int, int]] = []
    cursor = 84
    for _ in range(count):
        xyz = struct.unpack_from("<9f", data, cursor + 12)
        tri = []
        for offset in (0, 3, 6):
            point = xyz[offset : offset + 3]
            vertex_id = index.get(point)
            if vertex_id is None:
                vertex_id = len(vertices)
                index[point] = vertex_id
                vertices.append(point)
            tri.append(vertex_id)
        triangles.append(tuple(tri))
        cursor += 50
    return vertices, triangles


def write_object_model(destination: Path, parts):
    model = ET.Element(f"{{{CORE}}}model", {"unit": "millimeter", "xml:lang": "en-US"})
    resources = ET.SubElement(model, f"{{{CORE}}}resources")
    for object_id, path, _extruder in parts:
        vertices, triangles = read_binary_stl(path)
        obj = ET.SubElement(
            resources,
            f"{{{CORE}}}object",
            {"id": str(object_id), "type": "model", f"{{{PROD}}}UUID": str(uuid.uuid4())},
        )
        mesh = ET.SubElement(obj, f"{{{CORE}}}mesh")
        verts_el = ET.SubElement(mesh, f"{{{CORE}}}vertices")
        for x, y, z in vertices:
            ET.SubElement(
                verts_el,
                f"{{{CORE}}}vertex",
                {"x": f"{x:.7g}", "y": f"{y:.7g}", "z": f"{z:.7g}"},
            )
        tris_el = ET.SubElement(mesh, f"{{{CORE}}}triangles")
        for v1, v2, v3 in triangles:
            ET.SubElement(
                tris_el,
                f"{{{CORE}}}triangle",
                {"v1": str(v1), "v2": str(v2), "v3": str(v3)},
            )
    ET.ElementTree(model).write(destination, encoding="utf-8", xml_declaration=True)


GROUPS = (
    ("沙盘", (1, 2, 3)),
    ("底座", (4, 5)),
    ("轨迹", (6,)),
    ("水系", (7,)),
)


def write_main_model(destination: Path, parts, grouped=False):
    model = ET.Element(
        f"{{{CORE}}}model",
        {"unit": "millimeter", "xml:lang": "en-US", "requiredextensions": "p"},
    )
    ET.SubElement(model, f"{{{CORE}}}metadata", {"name": "Application"}).text = (
        "BambuStudio-02.07.01.62"
    )
    ET.SubElement(model, f"{{{CORE}}}metadata", {"name": "BambuStudio:3mfVersion"}).text = "1"
    resources = ET.SubElement(model, f"{{{CORE}}}resources")
    first_group_id = max(item[0] for item in parts) + 1
    groups = GROUPS if grouped else (("模型", tuple(item[0] for item in parts)),)
    group_ids = []
    for offset, (_label, member_ids) in enumerate(groups):
        group_id = first_group_id + offset
        group_ids.append(group_id)
        assembly = ET.SubElement(
            resources, f"{{{CORE}}}object",
            {"id": str(group_id), "type": "model", f"{{{PROD}}}UUID": str(uuid.uuid4())},
        )
        components = ET.SubElement(assembly, f"{{{CORE}}}components")
        for object_id in member_ids:
            ET.SubElement(
                components, f"{{{CORE}}}component",
                {"objectid": str(object_id), f"{{{PROD}}}path": "/3D/Objects/object_1.model", f"{{{PROD}}}UUID": str(uuid.uuid4())},
            )
    build = ET.SubElement(model, f"{{{CORE}}}build", {f"{{{PROD}}}UUID": str(uuid.uuid4())})
    for group_id in group_ids:
        ET.SubElement(
            build, f"{{{CORE}}}item",
            {"objectid": str(group_id), f"{{{PROD}}}UUID": str(uuid.uuid4()), "transform": "1 0 0 0 1 0 0 0 1 175 160 0", "printable": "1"},
        )
    ET.ElementTree(model).write(destination, encoding="utf-8", xml_declaration=True)


def model_settings(parts, project_name="模型", grouped=False):
    first_group_id = max(item[0] for item in parts) + 1
    parts_by_id = {item[0]: item for item in parts}
    root = ET.Element("config")
    groups = GROUPS if grouped else (("", tuple(item[0] for item in parts)),)
    group_ids = []
    for offset, (label, member_ids) in enumerate(groups):
        group_id = first_group_id + offset; group_ids.append(group_id)
        obj = ET.SubElement(root, "object", {"id": str(group_id)})
        object_name = f"{project_name}_{label}" if label else project_name
        ET.SubElement(obj, "metadata", {"key": "name", "value": object_name})
        # Bambu Studio applies the parent object's extruder to singleton groups.
        # Preserve child-part colours for multi-material objects, while assigning
        # trail/water parents to their actual red/blue filament slots.
        parent_extruder = parts_by_id[member_ids[0]][2] if len(member_ids) == 1 else 1
        ET.SubElement(obj, "metadata", {"key": "extruder", "value": str(parent_extruder)})
        for object_id in member_ids:
            _id, path, extruder = parts_by_id[object_id]
            vertices, triangles = read_binary_stl(path); del vertices
            part = ET.SubElement(obj, "part", {"id": str(object_id), "subtype": "normal_part"})
            ET.SubElement(part, "metadata", {"key": "name", "value": path.stem})
            ET.SubElement(part, "metadata", {"key": "source_file", "value": path.name})
            ET.SubElement(part, "metadata", {"key": "extruder", "value": str(extruder)})
            ET.SubElement(part, "mesh_stat", {"face_count": str(len(triangles))})
    plate = ET.SubElement(root, "plate")
    ET.SubElement(plate, "metadata", {"key": "plater_id", "value": "1"})
    ET.SubElement(plate, "metadata", {"key": "plater_name", "value": project_name})
    for instance_id, group_id in enumerate(group_ids):
        instance = ET.SubElement(plate, "model_instance")
        ET.SubElement(instance, "metadata", {"key": "object_id", "value": str(group_id)})
        ET.SubElement(instance, "metadata", {"key": "instance_id", "value": str(instance_id)})
    assemble = ET.SubElement(root, "assemble")
    for instance_id, group_id in enumerate(group_ids):
        ET.SubElement(assemble, "assemble_item", {"object_id": str(group_id), "instance_id": str(instance_id), "transform": "1 0 0 0 1 0 0 0 1 0 0 0", "offset": "0 0 0"})
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source_dir", type=Path)
    parser.add_argument("template_3mf", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--name", default="四件同盘")
    args = parser.parse_args()
    specs = [
        ("01_Terrain_Low_Green.stl", 1),
        ("02_Terrain_Middle_Brown.stl", 2),
        ("03_Terrain_High_Gray.stl", 3),
        ("04_Base_Gray.stl", 3),
        ("05_Base_Labels_Logo_Brown.stl", 2),
        ("06_Trail_Red.stl", 5),
        ("07_Water_Blue.stl", 4),
    ]
    parts = [(index + 1, args.source_dir / name, extruder) for index, (name, extruder) in enumerate(specs)]
    args.destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temp:
        temp_dir = Path(temp)
        object_model = temp_dir / "object_1.model"
        main_model = temp_dir / "3dmodel.model"
        write_object_model(object_model, parts)
        write_main_model(main_model, parts, grouped=True)
        with ZipFile(args.template_3mf) as template:
            settings = json.loads(template.read("Metadata/project_settings.config"))
        settings["print_sequence"] = "by layer"
        palette = [
            "#3F8E43",
            "#6F5034",
            "#858C91",
            "#2563B8",
            "#D93025",
        ]
        settings["filament_colour"] = palette
        settings["default_filament_colour"] = palette
        content_types = b"""<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
 <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
 <Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>
 <Default Extension="config" ContentType="application/octet-stream"/>
</Types>"""
        relationships = b"""<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
 <Relationship Target="/3D/3dmodel.model" Id="rel-1" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>
</Relationships>"""
        model_relationships = b"""<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
 <Relationship Target="/3D/Objects/object_1.model" Id="rel-2" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>
</Relationships>"""
        with ZipFile(args.destination, "w", ZIP_DEFLATED, allowZip64=True) as archive:
            archive.writestr("[Content_Types].xml", content_types)
            archive.writestr("_rels/.rels", relationships)
            archive.write(main_model, "3D/3dmodel.model")
            archive.write(object_model, "3D/Objects/object_1.model")
            archive.writestr("3D/_rels/3dmodel.model.rels", model_relationships)
            archive.writestr("Metadata/model_settings.config", model_settings(parts, args.name, grouped=True))
            archive.writestr(
                "Metadata/project_settings.config",
                json.dumps(settings, ensure_ascii=False, indent=4).encode("utf-8"),
            )
    print(args.destination)


if __name__ == "__main__":
    main()
