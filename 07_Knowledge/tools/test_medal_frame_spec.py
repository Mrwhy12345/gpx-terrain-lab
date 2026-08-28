#!/usr/bin/env python3

import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from medal_frame_spec import (
    FRAME_CLEARANCE_MM_PER_EDGE,
    FRAME_INNER_BOUNDS_MM,
    FRAME_INNER_VERTICES_MM,
    TARGET_DESIGN_OUTER_BOUNDS_MM,
    TARGET_PRINTED_MESH_OUTER_BOUNDS_MM,
)


class MedalFrameSpecTest(unittest.TestCase):
    def test_measured_bounds(self):
        xs = [p[0] for p in FRAME_INNER_VERTICES_MM]
        ys = [p[1] for p in FRAME_INNER_VERTICES_MM]
        self.assertAlmostEqual(max(xs)-min(xs), FRAME_INNER_BOUNDS_MM[0], places=5)
        self.assertAlmostEqual(max(ys)-min(ys), FRAME_INNER_BOUNDS_MM[1], places=5)

    def test_verified_base_is_inside_opening(self):
        self.assertGreater(FRAME_CLEARANCE_MM_PER_EDGE, 0)
        self.assertLess(TARGET_DESIGN_OUTER_BOUNDS_MM[0], FRAME_INNER_BOUNDS_MM[0])
        self.assertLess(TARGET_DESIGN_OUTER_BOUNDS_MM[1], FRAME_INNER_BOUNDS_MM[1])
        self.assertLessEqual(TARGET_PRINTED_MESH_OUTER_BOUNDS_MM[0], TARGET_DESIGN_OUTER_BOUNDS_MM[0])


if __name__ == "__main__":
    unittest.main()
