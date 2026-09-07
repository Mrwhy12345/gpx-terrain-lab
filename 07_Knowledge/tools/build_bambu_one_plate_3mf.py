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

PLATE_GROUP_CENTERS = {
    "水系": (230.0, 112.0),
    "轨迹": (110.0, 112.0),
    "底座": (110.0, 220.0),
    "沙盘": (240.0, 220.0),
    "地标": (175.0, 40.0),
}


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


def groups_for(parts, city_water_in_terrain=False):
    ids_by_name = {path.name: object_id for object_id, path, _extruder in parts}
    terrain = tuple(ids_by_name[name] for name in (
        "01_Terrain_Low_Green.stl", "02_Terrain_Middle_Brown.stl",
        "03_Terrain_High_Gray.stl", "08_Terrain_City_Terracotta.stl",
        "09_City_Buildings_DarkGray.stl", "10_City_Roads_Sand.stl",
    ) if name in ids_by_name)
    base_parts = [ids_by_name["04_Base_Gray.stl"], ids_by_name["05_Base_Labels_Logo_Brown.stl"]]
    if "12_Base_Medal_Disc_Brown.stl" in ids_by_name:
        base_parts.append(ids_by_name["12_Base_Medal_Disc_Brown.stl"])
    if city_water_in_terrain:
        # Marathon product contract: exactly four top-level physical objects.
        # Water remains an independently coloured material sub-part, but is
        # grouped into the city terrain rather than exposed as a fifth object.
        groups = [
            ("底座", tuple(base_parts)),
            ("轨迹", (ids_by_name["06_Trail_Red.stl"],)),
        ]
        if "11_Landmark_Gold.stl" in ids_by_name:
            groups.append(("地标", (ids_by_name["11_Landmark_Gold.stl"],)))
        groups.append(("沙盘", terrain + (ids_by_name["07_Water_Blue.stl"],)))
    else:
        groups = [
            ("水系", (ids_by_name["07_Water_Blue.stl"],)),
            ("轨迹", (ids_by_name["06_Trail_Red.stl"],)),
            ("底座", tuple(base_parts)),
            ("沙盘", terrain),
        ]
        if "11_Landmark_Gold.stl" in ids_by_name:
            groups.append(("地标", (ids_by_name["11_Landmark_Gold.stl"],)))
    return tuple(groups)


def group_min_z(parts_by_id, member_ids):
    minima = []
    for object_id in member_ids:
        _id, path, _extruder = parts_by_id[object_id]
        vertices, _triangles = read_binary_stl(path)
        minima.append(min(vertex[2] for vertex in vertices))
    return min(minima)


def write_main_model(destination: Path, parts, grouped=False, object_layout=False, city_water_in_terrain=False):
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
    parts_by_id = {item[0]: item for item in parts}
    groups = groups_for(parts, city_water_in_terrain) if grouped else (("模型", tuple(item[0] for item in parts)),)
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
    for group_id, (label, member_ids) in zip(group_ids, groups):
        x, y = PLATE_GROUP_CENTERS[label] if object_layout else (175.0, 160.0)
        z = -group_min_z(parts_by_id, member_ids) if object_layout else 0.0
        ET.SubElement(
            build, f"{{{CORE}}}item",
            {"objectid": str(group_id), f"{{{PROD}}}UUID": str(uuid.uuid4()), "transform": f"1 0 0 0 1 0 0 0 1 {x:g} {y:g} {z:g}", "printable": "1"},
        )
    ET.ElementTree(model).write(destination, encoding="utf-8", xml_declaration=True)


def model_settings(parts, project_name="模型", grouped=False, print_sequence="by object", object_layout=False, city_water_in_terrain=False):
    first_group_id = max(item[0] for item in parts) + 1
    parts_by_id = {item[0]: item for item in parts}
    root = ET.Element("config")
    groups = groups_for(parts, city_water_in_terrain) if grouped else (("", tuple(item[0] for item in parts)),)
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
    ET.SubElement(plate, "metadata", {"key": "print_sequence", "value": print_sequence})
    identify_ids = (254, 232, 204, 158, 126)
    for instance_id, group_id in enumerate(group_ids):
        instance = ET.SubElement(plate, "model_instance")
        ET.SubElement(instance, "metadata", {"key": "object_id", "value": str(group_id)})
        # Keep plate instance ids globally unique and mirror them in assemble.
        # This matches Bambu Studio's native multi-object projects and preserves
        # four independent collision envelopes for sequential auto-arrange.
        ET.SubElement(instance, "metadata", {"key": "instance_id", "value": str(instance_id)})
        ET.SubElement(instance, "metadata", {"key": "identify_id", "value": str(identify_ids[instance_id])})
    assemble = ET.SubElement(root, "assemble")
    for instance_id, (group_id, (label, member_ids)) in enumerate(zip(group_ids, groups)):
        x, y = PLATE_GROUP_CENTERS[label] if object_layout else (0.0, 0.0)
        z = -group_min_z(parts_by_id, member_ids) if object_layout else 0.0
        ET.SubElement(assemble, "assemble_item", {"object_id": str(group_id), "instance_id": str(instance_id), "transform": f"1 0 0 0 1 0 0 0 1 {x:g} {y:g} {z:g}", "offset": "0 0 0"})
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source_dir", type=Path)
    parser.add_argument("template_3mf", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--name", default="四件同盘")
    parser.add_argument(
        "--print-sequence", choices=("by object", "by layer"), default="by layer",
        help="By-object is experimental until a Bambu-native project rewrite passes slicing.",
    )
    parser.add_argument(
        "--object-layout", action="store_true",
        help="Input parts are canonical/local; place top-level objects with 3MF transforms.",
    )
    parser.add_argument(
        "--city-water-in-terrain", action="store_true",
        help="Marathon contract: group coloured water inside the city terrain, yielding four top-level objects.",
    )
    parser.add_argument(
        "--wipe-tower-x", type=float, default=20.0,
        help="Prime/wipe tower X position. The generic four-part layout reserves the lower-left corner.",
    )
    parser.add_argument(
        "--wipe-tower-y", type=float, default=40.0,
        help="Prime/wipe tower Y position. Do not inherit the legacy template position near the base.",
    )
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
    if (args.source_dir / "08_Terrain_City_Terracotta.stl").is_file():
        specs.append(("08_Terrain_City_Terracotta.stl", 6))
    seven_color_city = (args.source_dir / "V7_SEVEN_COLOR.flag").is_file()
    six_color_city = (args.source_dir / "V6_SIX_COLOR.flag").is_file() or seven_color_city
    if (args.source_dir / "09_City_Buildings_DarkGray.stl").is_file():
        specs.append(("09_City_Buildings_DarkGray.stl", 3 if six_color_city else 6))
    if (args.source_dir / "10_City_Roads_Sand.stl").is_file():
        specs.append(("10_City_Roads_Sand.stl", 7 if seven_color_city else (2 if six_color_city else 7)))
    if (args.source_dir / "11_Landmark_Gold.stl").is_file():
        specs.append(("11_Landmark_Gold.stl", 6 if six_color_city else 8))
    if (args.source_dir / "12_Base_Medal_Disc_Brown.stl").is_file():
        specs.append(("12_Base_Medal_Disc_Brown.stl", 2))
    # City-style TrailPrint3D jobs may use one planar terrain carrier instead
    # of the three hiking elevation bands. Package only declared files that
    # exist; groups_for() already treats terrain sublayers as optional.
    specs = [(name, extruder) for name, extruder in specs if (args.source_dir / name).is_file()]
    required = {"01_Terrain_Low_Green.stl", "04_Base_Gray.stl", "05_Base_Labels_Logo_Brown.stl", "06_Trail_Red.stl", "07_Water_Blue.stl"}
    missing = sorted(required - {name for name, _extruder in specs})
    if missing:
        raise FileNotFoundError("Missing required print parts: " + ", ".join(missing))
    parts = [(index + 1, args.source_dir / name, extruder) for index, (name, extruder) in enumerate(specs)]
    args.destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temp:
        temp_dir = Path(temp)
        object_model = temp_dir / "object_1.model"
        main_model = temp_dir / "3dmodel.model"
        write_object_model(object_model, parts)
        write_main_model(
            main_model, parts, grouped=True, object_layout=args.object_layout,
            city_water_in_terrain=args.city_water_in_terrain,
        )
        with ZipFile(args.template_3mf) as template:
            settings = json.loads(template.read("Metadata/project_settings.config"))
        template_colour_count = len(settings.get("filament_colour", []))
        # Bambu Studio stores sequential mode on the plate itself while
        # retaining the project-level fallback as by-layer.  Writing by-object
        # in both places invokes a more conservative global collision rule and
        # rejects the same layout that the GUI-saved project slices correctly.
        settings["print_sequence"] = (
            "by layer" if args.print_sequence == "by object" else args.print_sequence
        )
        split_city = (args.source_dir / "09_City_Buildings_DarkGray.stl").is_file()
        six_color_city = (args.source_dir / "V6_SIX_COLOR.flag").is_file() or seven_color_city
        if seven_color_city:
            palette = ["#3F8E43", "#6F5034", "#858C91", "#2563B8", "#D93025", "#D4A017", "#C9B27C"]
        elif six_color_city:
            palette = ["#3F8E43", "#6F5034", "#858C91", "#2563B8", "#D93025", "#D4A017"]
        else:
            palette = [
                "#3F8E43", "#6F5034", "#858C91", "#2563B8", "#D93025",
                "#454A4F" if split_city else "#C56A3A",
            ]
        if split_city and not six_color_city:
            palette.append("#B8A685")
        if (args.source_dir / "11_Landmark_Gold.stl").is_file() and not six_color_city:
            palette.append("#D4A017")
        colour_count = len(palette)
        # Every per-filament vector must grow with the palette.  Bambu's CLI
        # tolerates mismatched vectors, but the GUI throws a bare "vector"
        # exception and opens an empty plate.  Preserve the template values and
        # extend them deterministically for the added filament.
        if template_colour_count and colour_count > template_colour_count:
            for key, value in list(settings.items()):
                if not isinstance(value, list) or key in {
                    "flush_volumes_matrix", "flush_volumes_vector",
                    "filament_colour", "default_filament_colour",
                }:
                    continue
                if value and len(value) % template_colour_count == 0:
                    block_width = len(value) // template_colour_count
                    # Per-filament H2C fields use one, two, or three values per
                    # material.  Append the final material block for each new
                    # colour so GUI-side vector indexing remains valid.
                    if block_width in (1, 2, 3):
                        block = value[-block_width:]
                        settings[key] = value + block * (colour_count - template_colour_count)
        settings["filament_colour"] = palette
        settings["default_filament_colour"] = palette
        # Keep a native template's purge topology verbatim when the requested
        # palette already has the same size.  H2C's seven displayed colours do
        # not imply a generic 7 x 14 purge matrix: its dual-nozzle routing is
        # encoded by the template's 6-entry nozzle map and 12/72 purge tables.
        # Rebuilding those arrays as 14/98 makes Bambu Studio's GUI throw the
        # otherwise opaque `vector` exception and open an empty plate.
        if colour_count != template_colour_count:
            purge_columns = colour_count * 2
            settings["flush_volumes_vector"] = ["140"] * purge_columns
            settings["flush_volumes_matrix"] = [
                "0" if row == (column % colour_count) else "280"
                for row in range(colour_count)
                for column in range(purge_columns)
            ]
        # The legacy template places the 60 mm prime tower at (40, 220), which
        # intersects the generic base envelope.  Keep the tower in the reserved
        # lower-left area and make the position explicit in every generated 3MF.
        settings["wipe_tower_x"] = [f"{args.wipe_tower_x:g}"]
        settings["wipe_tower_y"] = [f"{args.wipe_tower_y:g}"]
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
            archive.writestr(
                "Metadata/model_settings.config",
                model_settings(
                    parts, args.name, grouped=True,
                    print_sequence=args.print_sequence,
                    object_layout=args.object_layout,
                    city_water_in_terrain=args.city_water_in_terrain,
                ),
            )
            archive.writestr(
                "Metadata/project_settings.config",
                json.dumps(settings, ensure_ascii=False, indent=4).encode("utf-8"),
            )
    print(args.destination)


if __name__ == "__main__":
    main()
