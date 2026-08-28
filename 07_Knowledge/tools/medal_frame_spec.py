#!/usr/bin/env python3
"""Single source of truth for the MakerWorld 1283346 medal-frame fit."""

from __future__ import annotations

FRAME_REFERENCE = "MakerWorld 1283346 / 5x3 magnet version"
FRAME_INNER_VERTICES_MM = (
    (-27.13545, -50.0),
    (27.13545, -50.0),
    (57.270935, 0.0),
    (27.13545, 50.0),
    (-27.13545, 50.0),
    (-57.270935, 0.0),
)
FRAME_INNER_BOUNDS_MM = (114.54187, 100.0)

# Physical fit baseline verified by the Xingxi sample.
FRAME_CLEARANCE_MM_PER_EDGE = 0.30
# The mathematical contour is measured before edge beveling. The exported
# mesh bounding box is slightly narrower in X because the six corners are
# rounded; both values are part of the contract and must not be conflated.
TARGET_DESIGN_OUTER_BOUNDS_MM = (111.30249, 96.39078)
TARGET_PRINTED_MESH_OUTER_BOUNDS_MM = (110.6764, 96.3908)
TARGET_VISIBLE_RING_WIDTH_MM = 4.594
BASE_DIMENSION_TOLERANCE_MM = 0.02
MIN_VISIBLE_RING_WIDTH_MM = 4.0

SPEC_VERSION = "MEDAL_FRAME_1283346_V2"
