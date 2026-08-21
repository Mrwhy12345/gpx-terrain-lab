#!/usr/bin/env python3
"""Run the route-neutral GPX -> 5x3MF + Blender production pipeline."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOLS = Path(__file__).resolve().parent
BLENDER = Path("/Applications/Blender.app/Contents/MacOS/Blender")
TEMPLATE = ROOT / "08_Jobs/20260810_xingxi_water_rich_res8/final_tested_baseline/05_星溪竹林_四件同盘_TrailPrint真机参数.3mf"


def run(stage, command, outputs, log_dir, cwd=ROOT, timeout=3600):
    if all(path.exists() and path.stat().st_size > 0 for path in outputs):
        return {"stage": stage, "status": "reused", "outputs": [str(p) for p in outputs]}
    result = subprocess.run(command, cwd=cwd, text=True, capture_output=True, timeout=timeout)
    (log_dir / f"pipeline_{stage}.log").write_text(result.stdout + "\n" + result.stderr, encoding="utf-8")
    if result.returncode or "Traceback (most recent call last)" in result.stderr:
        raise RuntimeError(f"{stage} failed; see process/pipeline_{stage}.log")
    missing = [str(path) for path in outputs if not path.exists() or not path.stat().st_size]
    if missing: raise RuntimeError(f"{stage} did not create: {missing}")
    return {"stage": stage, "status": "built", "outputs": [str(p) for p in outputs]}


def blender(input_blend, script, *args):
    command = [str(BLENDER), "--background"]
    if input_blend is not None: command.append(str(input_blend))
    return command + ["--python", str(TOOLS / script), "--", *map(str, args)]


def slug(value):
    return "".join(character if character.isalnum() or character in "_-" else "_" for character in value).strip("_")[:48] or "徒步沙盘"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("job_dir", type=Path)
    args = parser.parse_args()
    job_dir = args.job_dir.resolve(); job_path = job_dir / "job.json"
    job = json.loads(job_path.read_text(encoding="utf-8"))
    if "route_profile" not in job:
        from configure_route_scene import configure
        configure(job_dir); job=json.loads(job_path.read_text(encoding="utf-8"))
    route = job["route"]; engineering = job.get("engineering", {})
    gpx = job_dir / route["gpx"]; work = job_dir / "work"; review = job_dir / "review"; final = job_dir / "final"; process = job_dir / "process"
    for directory in (work, review, final, process): directory.mkdir(parents=True, exist_ok=True)
    # Web jobs already carry browser-derived facts. Materialize the standard facts file for label generation.
    facts_path = job_dir / route["facts"]
    if not facts_path.exists():
        web = route.get("web_facts", {})
        facts_path.write_text(json.dumps({"track_points": web.get("points"), "distance_km_raw": web.get("distance_km"), "source_sha256": hashlib.sha256(gpx.read_bytes()).hexdigest()}, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    title = job.get("customer_input", {}).get("title") or route["name"]
    name = slug(title)
    stages = []
    source = work / "trailprint_source.blend"
    stages.append(run("01_trailprint", blender(None, "generate_job_trailprint.py", job_dir), [source], process, timeout=1800))
    trail = work / "trail_insert.blend"
    stages.append(run("02_trail", blender(source, "build_trail_insert_and_groove.py", trail, review/"trail_insert.json", job_path), [trail, review/"trail_insert.json"], process))
    endpoint = work / "trail_endpoints.blend"
    model_gpx=job_dir/route.get("model_gpx",route["gpx"])
    stages.append(run("03_endpoints", blender(trail, "add_trail_endpoint_relief.py", model_gpx, endpoint, review/"trail_endpoints.json"), [endpoint, review/"trail_endpoints.json"], process))
    unified_trail = work / "trail_one_piece.blend"
    stages.append(run("03b_trail_unify", blender(endpoint, "unify_trail_hidden_bridges.py", unified_trail, review/"trail_one_piece.json"), [unified_trail, review/"trail_one_piece.json"], process))
    bands_source = unified_trail
    if job.get("route_profile", {}).get("mode") == "REGIONAL_OVERVIEW":
        selected_water = work / "water_selected"
        stages.append(run("03c_regional_water", [sys.executable, str(TOOLS/"probe_regional_route_water.py"), str(job_dir)], [selected_water/"water_lines.geojson", selected_water/"water_polygons.geojson", review/"regional_water.json"], process, timeout=1200))
        regional_water_scene = work / "regional_water_source.blend"
        stages.append(run("03d_regional_water_geometry", blender(unified_trail, "build_blender_water_geometry.py", selected_water/"water_lines.geojson", selected_water/"water_polygons.geojson", regional_water_scene, review/"regional_water_geometry.json"), [regional_water_scene, review/"regional_water_geometry.json"], process))
        bands_source = regional_water_scene
    bands = work / "terrain_three_band.blend"; bands_report = review / "terrain_three_band.json"
    stages.append(run("04_bands", blender(bands_source, "build_three_band_print_model.py", bands, bands_report), [bands, bands_report], process))
    parts = work / "parts"; water_scene = work / "terrain_water_grooved.blend"
    stages.append(run("05_water", blender(bands, "build_water_inserts_and_grooves.py", water_scene, parts, review/"water_inserts.json"), [water_scene, parts/"05_Water_Blue_SeparatePrint.stl"], process))
    base = work / "base.blend"
    stages.append(run("06_base", blender(water_scene, "rebuild_base_for_frame_glue_fit.py", base, review/"base.json"), [base, review/"base.json"], process))
    labels = work / "labels.blend"; labels_stl = work / "labels_only.stl"
    stages.append(run("07_labels", blender(base, "update_three_edge_labels.py", labels, review/"labels.json", labels_stl, job_path), [labels, labels_stl], process))
    logo_svg = work / "route_logo.svg"
    stages.append(run("08_logo_svg", [sys.executable, str(TOOLS/"build_route_logo_svg.py"), str(gpx), str(logo_svg)], [logo_svg], process))
    complete = work / "complete.blend"
    stages.append(run("09_logo", blender(labels, "add_base_bottom_logo_inlay.py", complete, review/"logo.json", parts/"07_Base_Gray.stl", parts/"08_Labels_Logo_Brown.stl", review/"logo.png", logo_svg), [complete, parts/"07_Base_Gray.stl", parts/"08_Labels_Logo_Brown.stl"], process))
    final_scene = work / "final_scene.blend"
    stages.append(run("10_finalize", blender(complete, "finalize_job_scene_and_parts.py", final_scene, parts/"09_Trail_Red_Aligned.stl", parts/"10_Trail_Red_SeparatePrint.stl", review/"finalize.json", bands_report), [final_scene, parts/"10_Trail_Red_SeparatePrint.stl"], process))
    repaired = work / "repaired_parts"
    stages.append(run("11_repair", blender(None,"repair_job_parts.py",parts,repaired,review/"part_repair.json"),[repaired/"05_Water_Blue_SeparatePrint.stl",review/"part_repair.json"],process))
    canonical = work / "canonical_parts_v2"; plate = work / "one_plate_parts_v2"
    stages.append(run("12_layout", [sys.executable, str(TOOLS/"layout_job_print_parts.py"), str(repaired), str(canonical), str(plate)], [canonical/"07_Water_Blue.stl", plate/"07_Water_Blue.stl"], process))
    output_specs = [
        ("01", f"01_{name}_沙盘地形.3mf", [(canonical/"01_Terrain_Low_Green.stl",1),(canonical/"02_Terrain_Middle_Brown.stl",2),(canonical/"03_Terrain_High_Gray.stl",3)], "#3F8E43,#6F5034,#858C91"),
        ("02", f"02_{name}_底座.3mf", [(canonical/"04_Base_Gray.stl",1),(canonical/"05_Base_Labels_Logo_Brown.stl",2)], "#858C91,#7A4A20"),
        ("03", f"03_{name}_徒步轨迹.3mf", [(canonical/"06_Trail_Red.stl",1)], "#D93025"),
        ("04", f"04_{name}_河流水体.3mf", [(canonical/"07_Water_Blue.stl",1)], "#2563B8"),
    ]
    for key, filename, parts_spec, colors in output_specs:
        destination = final / filename
        command=[sys.executable,str(TOOLS/"build_bambu_job_3mf.py"),str(TEMPLATE),str(destination),"--name",Path(filename).stem,"--colors",colors]
        for path, extruder in parts_spec: command += ["--part", f"{path}:{extruder}"]
        stages.append(run(f"13_3mf_{key}",command,[destination],process))
    one_plate = final / f"05_{name}_四件同盘.3mf"
    stages.append(run("13_3mf_05",[sys.executable,str(TOOLS/"build_bambu_one_plate_3mf.py"),str(plate),str(TEMPLATE),str(one_plate),"--name",f"{name}_四件同盘"],[one_plate],process))
    stages.append(run("13_3mf_05_hierarchy",[sys.executable,str(TOOLS/"validate_bambu_four_object_plate.py"),str(one_plate),str(review/"one_plate_hierarchy.json")],[review/"one_plate_hierarchy.json"],process))
    blend = final / f"06_{name}_完整设计预览.blend"
    stages.append(run("14_blender",blender(final_scene,"prepare_blender_delivery.py",blend,review/"blender_delivery.json",review/"blender_delivery.png"),[blend,review/"blender_delivery.json"],process))
    release_qa = review / "generic_release_qa.json"
    stages.append(run("15_release_qa",[sys.executable,str(TOOLS/"validate_generic_release.py"),str(final),str(release_qa)],[release_qa],process))
    result={"status":"PIPELINE_PASS","job_id":job["job_id"],"stages":stages,"final":[str(p) for p in sorted(final.iterdir()) if p.suffix.lower() in {".3mf",".blend"}]}
    (review/"generic_pipeline.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(result,ensure_ascii=False))


if __name__ == "__main__": main()
