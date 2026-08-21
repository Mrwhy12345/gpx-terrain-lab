#!/usr/bin/env python3
import unittest

from terrain_height_policy import resolve_terrain_height_policy


PROFILE = {"facts": {"bbox_wgs84": {"south": 22.9, "north": 23.0}}}


class TerrainHeightPolicyTest(unittest.TestCase):
    def test_scale_one_is_below_15mm_limit(self):
        result = resolve_terrain_height_policy({
            "elevation_scale": 1.0,
            "fixed_elevation_scale_10mm": True,
            "min_terrain_thickness_mm": 2.0,
            "max_terrain_height_mm": 15.0,
        }, PROFILE)
        self.assertFalse(result["height_limited"])
        self.assertLess(result["predicted_terrain_height_mm"], 15.0)

    def test_high_scale_is_capped(self):
        result = resolve_terrain_height_policy({
            "elevation_scale": 1.8,
            "fixed_elevation_scale_10mm": True,
            "min_terrain_thickness_mm": 2.0,
            "max_terrain_height_mm": 15.0,
        }, PROFILE)
        self.assertTrue(result["height_limited"])
        self.assertAlmostEqual(result["predicted_terrain_height_mm"], 15.0)
        self.assertLess(result["effective_elevation_scale"], 1.8)

    def test_legacy_mode_preserves_requested_scale(self):
        result = resolve_terrain_height_policy({
            "elevation_scale": 1.8,
            "fixed_elevation_scale_10mm": False,
            "max_terrain_height_mm": 15.0,
        }, PROFILE)
        self.assertEqual(result["effective_elevation_scale"], 1.8)
        self.assertIsNone(result["predicted_terrain_height_mm"])


if __name__ == "__main__":
    unittest.main()
