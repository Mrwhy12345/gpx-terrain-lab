#!/usr/bin/env python3
"""Fetch OSM water for any standardized GPX Terrain Lab job."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from probe_osm_water import (  # noqa: E402
    build_query,
    geojson_features,
    request_overpass,
    summarize,
    write_geojson,
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("job_dir", type=Path)
    parser.add_argument("--margin-deg", type=float, default=0.003)
    args = parser.parse_args()
    facts = json.loads((args.job_dir / "review/gpx_facts.json").read_text())
    bounds = facts["bbox_wgs84"]
    bbox = (
        bounds["south"] - args.margin_deg,
        bounds["west"] - args.margin_deg,
        bounds["north"] + args.margin_deg,
        bounds["east"] + args.margin_deg,
    )
    server, data = request_overpass(build_query(bbox))
    output = args.job_dir / "work/osm_water"
    output.mkdir(parents=True, exist_ok=True)
    (output / "raw.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    lines, polygons = geojson_features(data)
    write_geojson(output / "water_lines.geojson", lines)
    write_geojson(output / "water_polygons.geojson", polygons)
    report = {
        "tested_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": "OpenStreetMap via Overpass API",
        "server": server,
        "bbox_south_west_north_east": bbox,
        **summarize(data),
        "geojson_line_features": len(lines),
        "geojson_polygon_features": len(polygons),
    }
    (args.job_dir / "review/osm_water_probe.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
