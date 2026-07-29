#!/usr/bin/env python3
"""Archive the user's decision to provisionally accept all final roads as A."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
S02 = ROOT / "06_Experiment" / "S02_ColorTest"
ROAD_DIR = S02 / "data" / "road_candidates"
OUTPUT = S02 / "review" / "S02_Xingxi_AMap_Road_Validation_Default_A.json"


def read_features(name: str, group: str) -> list[dict]:
    data = json.loads((ROAD_DIR / name).read_text(encoding="utf-8"))
    result = []
    for feature in data["features"]:
        properties = feature.get("properties", {})
        result.append(
            {
                "id": f"{group}-{properties.get('osm_id')}",
                "osm_id": properties.get("osm_id"),
                "group": group,
                "highway": properties.get("highway"),
                "name": properties.get("name"),
                "ref": properties.get("ref"),
                "distance_m": properties.get("distance_to_gpx_m"),
                "grade": "A",
                "note": "用户决定本轮默认接受；正式版仍可按卫星图逐条降级。",
            }
        )
    return result


def main() -> None:
    candidates = [
        *read_features("roads_major_clipped_v2.geojson", "major"),
        *read_features("roads_local_relevant_v2.geojson", "local"),
    ]
    payload = {
        "project": "星溪竹林徒步地形模型",
        "validation_target": "最终进入S02多色模型的OSM道路",
        "validation_source": "用户默认评级决定；高德卫星验收页面可继续修订",
        "validation_status": "provisional_default_A",
        "coordinate_method": "浏览器本地WGS84 → GCJ-02转换",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "candidates": candidates,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {len(candidates)} provisional A reviews to {OUTPUT}")


if __name__ == "__main__":
    main()
