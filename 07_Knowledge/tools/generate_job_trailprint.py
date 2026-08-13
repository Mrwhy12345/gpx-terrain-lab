#!/usr/bin/env python3
"""Generate a route-neutral TrailPrint3D source blend from a standardized job."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import bpy


def main():
    args = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    if len(args) != 1:
        raise SystemExit("Expected JOB_DIR")
    job_dir = Path(args[0]).resolve()
    job = json.loads((job_dir / "job.json").read_text())
    gpx = job_dir / job["route"]["gpx"]
    export_dir = job_dir / "work/trailprint_export"
    export_dir.mkdir(parents=True, exist_ok=True)
    blend_path = job_dir / "work/trailprint_source.blend"

    if not hasattr(bpy.context.scene, "tp3d"):
        bpy.ops.preferences.addon_enable(
            module="bl_ext.user_default.trailprint3d"
        )
    props = bpy.context.scene.tp3d
    engineering = job.get("engineering", {})
    water = engineering.get("trailprint_water", {})
    elements = engineering.get("trailprint_elements", {})
    props.file_path = str(gpx)
    props.export_path = str(export_dir)
    props.generation_mode = "GENERATION"
    props.shape = "HEXAGON"
    props.objSize = int(engineering.get("object_size_mm", 100))
    props.scaleElevation = float(engineering.get("elevation_scale", 1.8))
    props.num_subdivisions = int(engineering.get("terrain_resolution", 4))
    props.minThickness = 2.0
    props.pathThickness = float(engineering.get("path_thickness_mm", 1.6))
    props.singleColorMode = bool(engineering.get("single_color_trail", True))
    props.scalemode = engineering.get("scale_mode", "FACTOR")
    props.pathScale = float(engineering.get("path_scale", 0.8))
    props.api = "MAPTERHORN"
    props.elementMode = engineering.get("element_mode", "PAINT")
    props.singleColorMode = False
    # Water is built as separate printable inserts later in the pipeline.  Keep
    # TrailPrint's terrain merge disabled unless explicitly requested, while
    # still recording the requested OSM categories in the job configuration.
    props.col_wPondsActive = bool(water.get("water", False)) and bool(
        water.get("merge_into_trailprint_terrain", False)
    )
    props.col_wBigRiversActive = bool(water.get("big_rivers", False)) and bool(
        water.get("merge_into_trailprint_terrain", False)
    )
    props.col_wSmallRiversActive = bool(water.get("small_rivers", False)) and bool(
        water.get("merge_into_trailprint_terrain", False)
    )
    props.col_wStreamWidth = float(water.get("river_width", 1.0))
    props.col_wArea = float(water.get("water_threshold", 1.0))
    props.el_oActive = bool(water.get("include_ocean", False)) and bool(
        water.get("merge_into_trailprint_terrain", False)
    )
    props.el_oMinIslandArea = float(water.get("min_island_area", 2.0))
    props.el_oRdpEpsilon = float(water.get("coastline_simplify", 0.1))
    props.col_fActive = bool(elements.get("forests", False))
    props.col_fArea = float(elements.get("forest_threshold", 10.0))
    props.col_scrActive = bool(elements.get("scree", False))
    props.col_scrArea = float(elements.get("scree_threshold", 1.0))
    props.col_cActive = bool(elements.get("city_boundaries", False))
    props.col_cArea = float(elements.get("city_threshold", 1.0))
    props.col_grActive = bool(elements.get("greenspaces", False))
    props.col_grArea = float(elements.get("greenspace_threshold", 1.0))
    props.col_faActive = bool(elements.get("farmland", False))
    props.col_faArea = float(elements.get("farmland_threshold", 1.0))
    props.col_glActive = bool(elements.get("glaciers", False))
    props.col_glArea = float(elements.get("glacier_threshold", 1.0))
    props.el_bActive = False
    props.el_sBigActive = False
    props.el_sMedActive = False
    props.el_sSmallActive = False
    props.disable_auto_export = True
    props.disable_3mf_export = True

    requested_single_color_trail = props.singleColorMode
    result = bpy.ops.tp3d.run_generation()
    maps = [
        obj for obj in bpy.context.scene.objects
        if obj.get("Object type") in {"MAP", "TERRAIN_LOW_GREEN"}
    ]
    trails = [
        obj for obj in bpy.context.scene.objects
        if obj.get("Object type") in {"TRAIL", "TRAIL_INSERT"}
        or obj.get("S03_geometry") == "trail_insert"
    ]
    if not maps:
        raise RuntimeError(f"TrailPrint3D returned {result}, but no terrain object exists")
    bpy.context.scene["job_id"] = job["job_id"]
    bpy.context.scene["route_name"] = job["route"]["name"]
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
    report = {
        "operator_result": list(result),
        "blend": str(blend_path),
        "terrain_objects": [obj.name for obj in maps],
        "trail_objects": [obj.name for obj in trails],
        "horizontal_scale": maps[0].get("Horizontal Scale"),
        "map_size_km": maps[0].get("Map Size in Km"),
        "terrain_resolution": props.num_subdivisions,
        "object_size_mm": props.objSize,
        "elevation_scale": props.scaleElevation,
        "path_thickness_mm": props.pathThickness,
        "single_color_trail": props.singleColorMode,
        "single_color_trail_requested": requested_single_color_trail,
        "single_color_trail_note": "TrailPrint3D may reset the UI property after SCM generation",
        "scale_mode": props.scalemode,
        "path_scale": props.pathScale,
        "element_mode": props.elementMode,
        "requested_water_settings": water,
        "requested_element_settings": elements,
    }
    (job_dir / "review/trailprint_generation.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print("JOB_TRAILPRINT=" + json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
