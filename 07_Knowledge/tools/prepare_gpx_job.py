#!/usr/bin/env python3
"""Create a route-neutral job.json and sanitized GPX facts from one GPX file."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path


def haversine(a, b):
    radius_km = 6371.0088
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    dlat, dlon = lat2 - lat1, lon2 - lon1
    value = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    )
    return 2 * radius_km * math.asin(math.sqrt(value))


def text(child, name):
    for item in child:
        if item.tag.rsplit("}", 1)[-1] == name:
            return (item.text or "").strip()
    return ""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("gpx", type=Path)
    parser.add_argument("job_dir", type=Path)
    parser.add_argument("--route-name", required=True)
    parser.add_argument("--delivery-date", default=date.today().isoformat())
    parser.add_argument("--job-id", required=True)
    args = parser.parse_args()

    root = ET.parse(args.gpx).getroot()
    segments = []
    waypoints = []
    for element in root.iter():
        tag = element.tag.rsplit("}", 1)[-1]
        if tag == "trkseg":
            points = []
            for point in element:
                if point.tag.rsplit("}", 1)[-1] != "trkpt":
                    continue
                points.append(
                    {
                        "lat": float(point.attrib["lat"]),
                        "lon": float(point.attrib["lon"]),
                        "ele": float(text(point, "ele")) if text(point, "ele") else None,
                        "time": text(point, "time") or None,
                    }
                )
            if points:
                segments.append(points)
        elif tag == "wpt":
            waypoints.append(
                {
                    "name": text(element, "name") or None,
                    "lat": float(element.attrib["lat"]),
                    "lon": float(element.attrib["lon"]),
                    "ele": float(text(element, "ele")) if text(element, "ele") else None,
                }
            )
    points = [point for segment in segments for point in segment]
    if len(points) < 2:
        raise SystemExit("GPX must contain at least two track points")
    distance = sum(
        haversine(
            (segment[index - 1]["lat"], segment[index - 1]["lon"]),
            (segment[index]["lat"], segment[index]["lon"]),
        )
        for segment in segments
        for index in range(1, len(segment))
    )
    elevations = [point["ele"] for point in points if point["ele"] is not None]
    ascent = sum(
        max(0.0, segment[index]["ele"] - segment[index - 1]["ele"])
        for segment in segments
        for index in range(1, len(segment))
        if segment[index]["ele"] is not None and segment[index - 1]["ele"] is not None
    )
    digest = hashlib.sha256(args.gpx.read_bytes()).hexdigest()
    facts = {
        "track_points": len(points),
        "track_segments": len(segments),
        "waypoints": waypoints,
        "distance_km_raw": round(distance, 3),
        "elevation_min_m_raw": round(min(elevations), 1) if elevations else None,
        "elevation_max_m_raw": round(max(elevations), 1) if elevations else None,
        "ascent_m_raw_unsmoothed": round(ascent, 1) if elevations else None,
        "bbox_wgs84": {
            "west": min(point["lon"] for point in points),
            "south": min(point["lat"] for point in points),
            "east": max(point["lon"] for point in points),
            "north": max(point["lat"] for point in points),
        },
        "start": {"lat": points[0]["lat"], "lon": points[0]["lon"]},
        "end": {"lat": points[-1]["lat"], "lon": points[-1]["lon"]},
        "time_start": next((p["time"] for p in points if p["time"]), None),
        "time_end": next((p["time"] for p in reversed(points) if p["time"]), None),
        "source_sha256": digest,
    }
    job = {
        "schema_version": "1.0",
        "job_id": args.job_id,
        "route": {
            "name": args.route_name,
            "gpx": "input/route.gpx",
            "facts": "review/gpx_facts.json",
        },
        "customer_input": {
            "display_date": args.delivery_date,
            "title": None,
            "subtitle": None,
            "logo_theme": None,
        },
        "creative": {
            "mode": "auto",
            "map_context_required": True,
            "title_candidates": 3,
            "logo_candidates": 3,
        },
        "engineering": {
            "target_version": "V012-equivalent",
            "terrain_colors_low_to_high": ["#3F8E43", "#6F5034", "#858C91"],
            "water_color": "#2563B8",
            "trail_color": "#D93025",
            "base_colors": ["#858C91", "#7A4A20"],
            "max_water_components": 5,
            "terrain_seat_clearance_mm": 0.30,
            "water_slot_clearance_mm": 0.12,
            "printer_profile": "Bambu Lab H2C / 0.4 mm",
        },
        "deliverables": {
            "three_mf_count": 5,
            "blend_count": 1,
            "final_dir": "final",
        },
        "privacy": {
            "raw_metadata_export": False,
            "precise_coordinates_public": False,
        },
        "status": "input_validated",
    }
    for folder in ("input", "work", "review", "final", "process"):
        (args.job_dir / folder).mkdir(parents=True, exist_ok=True)
    shutil.copy2(args.gpx, args.job_dir / "input/route.gpx")
    (args.job_dir / "review/gpx_facts.json").write_text(
        json.dumps(facts, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (args.job_dir / "job.json").write_text(
        json.dumps(job, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"job": str(args.job_dir / "job.json"), "facts": facts}, ensure_ascii=False))


if __name__ == "__main__":
    main()
