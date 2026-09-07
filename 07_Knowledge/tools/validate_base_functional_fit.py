#!/usr/bin/env python3
"""Independently report magnet retention and medal-frame fit from base evidence."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from medal_frame_spec import FRAME_CLEARANCE_MM_PER_EDGE, SPEC_VERSION


def point_segment_distance(point, start, end):
    x, y = point
    ax, ay = start
    bx, by = end
    dx, dy = bx - ax, by - ay
    scale = dx * dx + dy * dy
    t = 0.0 if scale == 0 else max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / scale))
    return math.hypot(x - (ax + t * dx), y - (ay + t * dy))


def inside_convex(point, polygon, tolerance=1e-6):
    signs = []
    for index, start in enumerate(polygon):
        end = polygon[(index + 1) % len(polygon)]
        cross = (end[0] - start[0]) * (point[1] - start[1]) - (end[1] - start[1]) * (point[0] - start[0])
        if abs(cross) > tolerance:
            signs.append(cross > 0)
    return not signs or all(sign == signs[0] for sign in signs)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("base_report", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    base = json.loads(args.base_report.read_text(encoding="utf-8"))

    magnet = base.get("magnet_pockets", {})
    magnet_digital_pass = not magnet and base.get("quality", {}).get("non_manifold_edges") == 0

    frame = base.get("frame_inner_vertices", [])
    outer = base.get("base_outer_vertices", [])
    contained = len(frame) >= 3 and len(outer) >= 3 and all(inside_convex(point, frame) for point in outer)
    clearances = [
        min(point_segment_distance(point, frame[index], frame[(index + 1) % len(frame)]) for index in range(len(frame)))
        for point in outer
    ] if contained else []
    minimum_clearance = min(clearances) if clearances else None
    frame_digital_pass = (
        contained
        and base.get("medal_frame_spec_version") == SPEC_VERSION
        and abs(float(base.get("clearance_mm_per_edge", -1)) - FRAME_CLEARANCE_MM_PER_EDGE) <= 1e-6
        and minimum_clearance is not None
        and minimum_clearance >= FRAME_CLEARANCE_MM_PER_EDGE
    )

    result = {
        "schema_version": "BASE-FUNCTIONAL-1.0",
        "overall_digital_status": "PASS" if magnet_digital_pass and frame_digital_pass else "FAIL",
        "magnet_no_glue": {
            "digital_status": "PASS" if magnet_digital_pass else "FAIL",
            "physical_status": "ROLLED_BACK_TO_POCKET_ONLY",
            "evidence": magnet,
            "physical_test_required": "Magnet retention is intentionally not claimed in this rollback; use the separate magnet-design task.",
        },
        "medal_frame_fit": {
            "digital_status": "PASS" if frame_digital_pass else "FAIL",
            "physical_status": "NEEDS_TEST",
            "frame_spec_version": base.get("medal_frame_spec_version"),
            "all_base_vertices_inside_frame": contained,
            "nominal_clearance_mm_per_edge": base.get("clearance_mm_per_edge"),
            "minimum_vertex_to_frame_edge_clearance_mm": round(minimum_clearance, 6) if minimum_clearance is not None else None,
            "base_design_outer_bounds_mm": base.get("base_outer_bounds_mm"),
            "physical_test_required": "Print on the target calibrated printer and insert into the actual medal frame; confirm full seating without force or visible looseness.",
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    raise SystemExit(0 if result["overall_digital_status"] == "PASS" else 1)


if __name__ == "__main__":
    main()
