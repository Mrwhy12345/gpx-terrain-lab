#!/usr/bin/env python3
"""Release gate for a generic 5×3MF + 1×Blend Web job."""

from __future__ import annotations

import json
import subprocess
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

CORE="{http://schemas.microsoft.com/3dmanufacturing/core/2015/02}"


def mesh_connected_components(project):
    with zipfile.ZipFile(project) as archive:
        root=ET.fromstring(archive.read("3D/Objects/object_1.model"))
    counts=[]
    for obj in root.findall(f".//{CORE}object"):
        mesh=obj.find(f"{CORE}mesh")
        if mesh is None: continue
        vertices=mesh.find(f"{CORE}vertices"); triangles=mesh.find(f"{CORE}triangles"); parent=list(range(len(vertices)))
        def find(value):
            while parent[value]!=value: parent[value]=parent[parent[value]]; value=parent[value]
            return value
        def union(left,right):
            left,right=find(left),find(right)
            if left!=right: parent[right]=left
        used=set()
        for triangle in triangles:
            ids=[int(triangle.get(key)) for key in ("v1","v2","v3")]; used.update(ids); union(ids[0],ids[1]); union(ids[1],ids[2])
        counts.append(len({find(value) for value in used}))
    return counts


def mesh_component_vertex_counts(project):
    with zipfile.ZipFile(project) as archive:
        root=ET.fromstring(archive.read("3D/Objects/object_1.model"))
    results=[]
    for obj in root.findall(f".//{CORE}object"):
        mesh=obj.find(f"{CORE}mesh")
        if mesh is None: continue
        vertices=mesh.find(f"{CORE}vertices"); triangles=mesh.find(f"{CORE}triangles"); parent=list(range(len(vertices))); used=set()
        def find(value):
            while parent[value]!=value: parent[value]=parent[parent[value]]; value=parent[value]
            return value
        def union(left,right):
            left,right=find(left),find(right)
            if left!=right: parent[right]=left
        for triangle in triangles:
            ids=[int(triangle.get(key)) for key in ("v1","v2","v3")]; used.update(ids); union(ids[0],ids[1]); union(ids[1],ids[2])
        sizes={}
        for value in used: sizes[find(value)]=sizes.get(find(value),0)+1
        results.append(sorted(sizes.values(),reverse=True))
    return results


def build_plate_contact_ratio(project, tolerance=0.05):
    with zipfile.ZipFile(project) as archive:
        root=ET.fromstring(archive.read("3D/Objects/object_1.model"))
    z_values=[]
    for vertex in root.findall(f".//{CORE}mesh/{CORE}vertices/{CORE}vertex"):
        z_values.append(float(vertex.get("z")))
    if not z_values: return 0.0, 0, 0
    minimum=min(z_values); contact=sum(value <= minimum+tolerance for value in z_values)
    return contact/len(z_values), contact, len(z_values)


def main():
    if len(sys.argv) != 3:
        raise SystemExit("Expected FINAL_DIR REPORT.json")
    final, report = map(Path, sys.argv[1:])
    projects = sorted(final.glob("*.3mf")); blends = sorted(final.glob("*.blend"))
    checks = []
    if len(projects) != 5 or len(blends) != 1:
        raise RuntimeError(f"Expected 5 3MF + 1 Blend, got {len(projects)} + {len(blends)}")
    tools = Path(__file__).resolve().parent
    for project in projects:
        with zipfile.ZipFile(project) as archive:
            bad = archive.testzip()
            if bad: raise RuntimeError(f"Corrupt 3MF member: {project.name}:{bad}")
        result = subprocess.run(
            [sys.executable, str(tools / "validate_bambu_3mf_build_bounds.py"), str(project)],
            text=True, capture_output=True,
        )
        if result.returncode: raise RuntimeError(result.stdout + result.stderr)
        checks.append(result.stdout.strip())
        if project.name.startswith("03_"):
            geometry_components=mesh_connected_components(project)
            if geometry_components != [1]:
                raise RuntimeError(f"Trail must be one connected body, got {geometry_components}: {project.name}")
            checks.append(f"PASS {project.name}: geometric_connected_components=1")
            contact_ratio, contact_vertices, total_vertices=build_plate_contact_ratio(project)
            if contact_ratio < 0.01:
                raise RuntimeError(f"Trail build-plate contact too small: {contact_vertices}/{total_vertices}={contact_ratio:.4%}: {project.name}")
            checks.append(f"PASS {project.name}: build_plate_contact={contact_ratio:.2%}")
        if project.name.startswith("01_"):
            component_sizes=mesh_component_vertex_counts(project)
            tiny=[size for sizes in component_sizes for size in sizes if size < 500]
            if tiny:
                raise RuntimeError(f"Terrain contains boolean crumbs under 500 vertices: {tiny}: {project.name}")
            checks.append(f"PASS {project.name}: no_tiny_terrain_components sizes={component_sizes}")
        if project.name.startswith("05_"):
            hierarchy = subprocess.run(
                [sys.executable, str(tools / "validate_bambu_four_object_plate.py"), str(project)],
                text=True, capture_output=True,
            )
            if hierarchy.returncode: raise RuntimeError(hierarchy.stdout + hierarchy.stderr)
            checks.append(f"PASS {project.name}: four_top_level_objects")
    result = subprocess.run(
        [sys.executable, str(tools / "validate_bambu_3mf_z.py"), *map(str, projects)],
        text=True, capture_output=True,
    )
    if result.returncode: raise RuntimeError(result.stdout + result.stderr)
    checks.extend(line for line in result.stdout.splitlines() if line.strip())
    header = blends[0].read_bytes()[:7]
    if not (header.startswith(b"BLENDER") or header.startswith(b"\x28\xb5\x2f\xfd")):
        raise RuntimeError(f"Unexpected Blender header: {header!r}")
    payload = {"status":"PASS","contract":"5x3MF+1xBlend","zip_test":"PASS","build_and_z_checks":checks}
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    main()
