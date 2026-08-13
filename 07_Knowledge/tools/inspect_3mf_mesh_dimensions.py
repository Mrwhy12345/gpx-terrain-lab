#!/usr/bin/env python3
"""Inspect raw mesh bounds and coordinate levels in a Bambu-style 3MF."""

from __future__ import annotations

import argparse
import json
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
from zipfile import ZipFile


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("project", type=Path)
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    with ZipFile(args.project) as archive:
        root = ET.fromstring(archive.read("3D/Objects/object_1.model"))
    vertices = [
        (float(v.get("x")), float(v.get("y")), float(v.get("z")))
        for v in root.iter()
        if v.tag.rsplit("}", 1)[-1] == "vertex"
    ]
    if not vertices:
        raise SystemExit("No vertices")
    axes = list(zip(*vertices))
    counts = {
        axis: Counter(round(value, 3) for value in axes[index]).most_common(40)
        for index, axis in enumerate(("x", "y", "z"))
    }
    z_levels = {}
    for z, count in Counter(round(v[2], 3) for v in vertices).most_common(30):
        points = [v for v in vertices if round(v[2], 3) == z]
        z_levels[str(z)] = {
            "count": count,
            "x": [min(v[0] for v in points), max(v[0] for v in points)],
            "y": [min(v[1] for v in points), max(v[1] for v in points)],
            "x_values": Counter(round(v[0], 3) for v in points).most_common(24),
            "y_values": Counter(round(v[1], 3) for v in points).most_common(24),
        }
    report = {
        "project": str(args.project),
        "vertex_count": len(vertices),
        "bounds": {
            axis: [min(axes[index]), max(axes[index])]
            for index, axis in enumerate(("x", "y", "z"))
        },
        "dimensions": {
            axis: max(axes[index]) - min(axes[index])
            for index, axis in enumerate(("x", "y", "z"))
        },
        "common_coordinates": counts,
        "z_levels": z_levels,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
