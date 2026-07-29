#!/usr/bin/env python3
"""Archive an AMap review and build provisionally accepted water layers."""

from __future__ import annotations

import json
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
S02 = ROOT / "06_Experiment" / "S02_ColorTest"
DOWNLOAD = Path.home() / "Downloads" / "S02_Xingxi_AMap_Validation.json"
ARCHIVE = S02 / "review" / "S02_Xingxi_AMap_Validation.json"
LINES = S02 / "data" / "water_candidates" / "water_lines_near_150m.geojson"
POLYGONS = (
    S02 / "data" / "water_candidates" / "water_polygons_near_150m.geojson"
)
RESULT = S02 / "result"


def load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def annotate(source: Path, reviews: dict[int, dict]) -> dict:
    collection = load_json(source)
    accepted = []
    for feature in collection["features"]:
        osm_id = feature["properties"]["osm_id"]
        review = reviews.get(osm_id)
        if not review or review["grade"] not in {"A", "B"}:
            continue
        feature["properties"].update(
            {
                "validation_grade": review["grade"],
                "validation_note": review.get("note", ""),
                "validation_status": "provisional",
                "validation_source": "AMap satellite manual review",
            }
        )
        accepted.append(feature)
    collection["features"] = accepted
    return collection


def main() -> None:
    if not DOWNLOAD.exists():
        raise SystemExit(f"Missing review export: {DOWNLOAD}")

    ARCHIVE.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(DOWNLOAD, ARCHIVE)
    review_payload = load_json(ARCHIVE)
    reviews = {
        item["osm_id"]: item
        for item in review_payload["candidates"]
        if item.get("grade")
    }

    accepted_lines = annotate(LINES, reviews)
    accepted_polygons = annotate(POLYGONS, reviews)
    combined = {
        "type": "FeatureCollection",
        "features": accepted_lines["features"] + accepted_polygons["features"],
    }

    RESULT.mkdir(parents=True, exist_ok=True)
    write_json(RESULT / "S02_Xingxi_Water_Accepted_Lines.geojson", accepted_lines)
    write_json(
        RESULT / "S02_Xingxi_Water_Accepted_Polygons.geojson",
        accepted_polygons,
    )
    write_json(RESULT / "S02_Xingxi_Water_Accepted_All.geojson", combined)

    summary = {
        "review_file": str(ARCHIVE.relative_to(ROOT)),
        "validation_status": "provisional",
        "reason": "All six candidates were graded A without detailed inspection.",
        "accepted_line_count": len(accepted_lines["features"]),
        "accepted_polygon_count": len(accepted_polygons["features"]),
        "accepted_total": len(combined["features"]),
        "next_gate": "Clip to the confirmed TrailPrint3D model boundary.",
    }
    write_json(RESULT / "S02_Xingxi_Water_Accepted_Summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
