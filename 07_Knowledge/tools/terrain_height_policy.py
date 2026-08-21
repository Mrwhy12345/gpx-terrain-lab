#!/usr/bin/env python3
"""Resolve TrailPrint3D elevation normalization and print-height limits."""
from __future__ import annotations

import math


def resolve_terrain_height_policy(engineering, route_profile):
    requested_scale = float(engineering.get("elevation_scale", 1.8))
    fixed_range = bool(engineering.get("fixed_elevation_scale_10mm", False))
    minimum_thickness = float(engineering.get("min_terrain_thickness_mm", 2.0))
    maximum_height = float(engineering.get("max_terrain_height_mm", 0.0) or 0.0)
    bbox = route_profile.get("facts", {}).get("bbox_wgs84", {})
    latitude = max(abs(float(bbox.get("south", 0.0))), abs(float(bbox.get("north", 0.0))))
    mercator_factor = 1.0 / max(math.cos(math.radians(latitude)), 1e-6)

    effective_scale = requested_scale
    cap_scale = None
    if fixed_range and maximum_height > minimum_thickness:
        normalized_relief_at_scale_one = 10.0 * mercator_factor
        cap_scale = (maximum_height - minimum_thickness) / normalized_relief_at_scale_one
        effective_scale = min(requested_scale, cap_scale)

    predicted_height = minimum_thickness
    if fixed_range:
        predicted_height += 10.0 * mercator_factor * effective_scale

    return {
        "requested_elevation_scale": requested_scale,
        "effective_elevation_scale": effective_scale,
        "fixed_elevation_scale_10mm": fixed_range,
        "minimum_terrain_thickness_mm": minimum_thickness,
        "max_terrain_height_mm": maximum_height or None,
        "cap_elevation_scale": cap_scale,
        "mercator_factor": mercator_factor,
        "predicted_terrain_height_mm": predicted_height if fixed_range else None,
        "height_limited": effective_scale < requested_scale - 1e-9,
    }
