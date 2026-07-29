#!/usr/bin/env python3
"""Clip accepted water GeoJSON to an extracted TrailPrint3D boundary."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from shapely.geometry import mapping, shape


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def clip_collection(source: dict, boundary) -> dict:
    output = []
    for feature in source["features"]:
        clipped = shape(feature["geometry"]).intersection(boundary)
        if clipped.is_empty:
            continue
        properties = dict(feature.get("properties") or {})
        properties["clip_status"] = "clipped_to_S01_TrailPrint_boundary"
        output.append(
            {
                "type": "Feature",
                "properties": properties,
                "geometry": mapping(clipped),
            }
        )
    return {"type": "FeatureCollection", "features": output}


def main() -> None:
    arguments = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    if len(arguments) != 5:
        raise SystemExit(
            "Usage: blender --background --python script.py -- "
            "BOUNDARY LINES POLYGONS OUTPUT_DIR SUMMARY"
        )
    boundary_path, lines_path, polygons_path, output_dir, summary_path = map(
        Path, arguments
    )
    boundary = shape(load(boundary_path)["features"][0]["geometry"])
    clipped_lines = clip_collection(load(lines_path), boundary)
    clipped_polygons = clip_collection(load(polygons_path), boundary)
    combined = {
        "type": "FeatureCollection",
        "features": clipped_lines["features"] + clipped_polygons["features"],
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    line_output = output_dir / "S02_Xingxi_Water_Clipped_Lines.geojson"
    polygon_output = output_dir / "S02_Xingxi_Water_Clipped_Polygons.geojson"
    combined_output = output_dir / "S02_Xingxi_Water_Clipped_All.geojson"
    write(line_output, clipped_lines)
    write(polygon_output, clipped_polygons)
    write(combined_output, combined)

    summary = {
        "boundary": str(boundary_path),
        "input_line_count": len(load(lines_path)["features"]),
        "input_polygon_count": len(load(polygons_path)["features"]),
        "clipped_line_count": len(clipped_lines["features"]),
        "clipped_polygon_count": len(clipped_polygons["features"]),
        "clipped_total": len(combined["features"]),
        "outputs": [str(line_output), str(polygon_output), str(combined_output)],
        "next_gate": "Inspect clipped layers in QGIS, then convert to Blender geometry.",
    }
    write(summary_path, summary)
    print("WATER_CLIP_SUMMARY=" + json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
