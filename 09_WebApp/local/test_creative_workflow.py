#!/usr/bin/env python3
"""Regression tests for the post-engineering creative confirmation gate."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "07_Knowledge" / "tools"))

from build_creative_choices import (  # noqa: E402
    attach_bottom_render,
    choose_logo,
    choose_title,
    confirm_creative,
    initialize_creative,
    load_creative,
)
from medal_frame_spec import (  # noqa: E402
    SPEC_VERSION,
    TARGET_DESIGN_OUTER_BOUNDS_MM,
    TARGET_PRINTED_MESH_OUTER_BOUNDS_MM,
    TARGET_VISIBLE_RING_WIDTH_MM,
)


class CreativeWorkflowTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="gpx-creative-")
        self.job_dir = Path(self.temp.name) / "WEB_TEST_星溪竹林"
        for folder in ("input", "work", "review", "final", "process"):
            (self.job_dir / folder).mkdir(parents=True)
        self.gpx = self.job_dir / "input" / "route.gpx"
        self.gpx.write_text(
            "<?xml version='1.0' encoding='UTF-8'?>"
            "<gpx version='1.1' xmlns='http://www.topografix.com/GPX/1/1'>"
            "<trk><name>星溪竹林</name><trkseg>"
            "<trkpt lat='23.7000' lon='113.5000'/><trkpt lat='23.7050' lon='113.5070'/>"
            "<trkpt lat='23.7100' lon='113.5020'/><trkpt lat='23.7160' lon='113.5120'/>"
            "</trkseg></trk></gpx>",
            encoding="utf-8",
        )
        self.original_gpx = self.gpx.read_bytes()
        (self.job_dir / "job.json").write_text(
            json.dumps(
                {
                    "job_id": self.job_dir.name,
                    "route": {
                        "name": "2025-02-23 从化星溪线",
                        "gpx": "input/route.gpx",
                        "web_facts": {"distance_km": 9.52, "points": 878},
                    },
                    "customer_input": {
                        "title": "星溪竹林",
                        "display_date": "2026-07-12",
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_four_by_four_confirmation_and_same_source_proof(self) -> None:
        creative = initialize_creative(self.job_dir)
        self.assertEqual("TITLE_SELECTION", creative["stage"])
        self.assertEqual(4, len(creative["title_candidates"]))
        self.assertTrue(all(item["fit"] == "PASS" for item in creative["title_candidates"]))

        with self.assertRaisesRegex(ValueError, "标题、Logo"):
            confirm_creative(self.job_dir)

        creative = choose_title(self.job_dir, candidate_id="A", display_date="2026-07-12")
        self.assertEqual("LOGO_SELECTION", creative["stage"])
        self.assertEqual(4, len(creative["logo_candidates"]))
        for item in creative["logo_candidates"]:
            self.assertEqual("PASS", item["qa"])
            self.assertTrue((self.job_dir / item["source"]).is_file())

        creative = choose_logo(self.job_dir, "D", display_date="2026-07-12")
        proof = creative["proof"]
        self.assertEqual("CONFIRMATION", creative["stage"])
        self.assertEqual("PASS", proof["qa"])
        self.assertEqual(SPEC_VERSION, proof["dimensions"]["frame_spec"])
        self.assertEqual(list(TARGET_DESIGN_OUTER_BOUNDS_MM), proof["dimensions"]["design_outer_mm"])
        self.assertEqual(list(TARGET_PRINTED_MESH_OUTER_BOUNDS_MM), proof["dimensions"]["printed_mesh_outer_mm"])
        self.assertEqual(TARGET_VISIBLE_RING_WIDTH_MM, proof["dimensions"]["visible_ring_width_mm"])
        self.assertTrue(proof["checks"]["logo_source_same_as_production"])
        self.assertTrue(proof["checks"]["frame_dimensions_from_locked_spec"])
        self.assertTrue(proof["checks"]["label_order_matches_production"])
        self.assertEqual("9.5 KM", proof["content"]["distance"])
        self.assertTrue((self.job_dir / proof["source"]).is_file())

        render = self.job_dir / "work/creative/bottom_render.png"
        render.parent.mkdir(parents=True, exist_ok=True)
        render.write_bytes(b"PNG" + b"0" * 2048)
        creative = attach_bottom_render(self.job_dir)
        self.assertEqual("PASS", creative["proof"]["render_qa"])
        self.assertTrue(creative["proof"]["render_url"].endswith("bottom_render.png"))

        creative = confirm_creative(self.job_dir)
        self.assertTrue(creative["confirmed"])
        self.assertEqual("CONFIRMED", creative["stage"])
        job = json.loads((self.job_dir / "job.json").read_text(encoding="utf-8"))
        self.assertTrue(job["creative"]["confirmed"])
        self.assertEqual(SPEC_VERSION, job["creative"]["frame_spec"])
        selected = next(item for item in creative["logo_candidates"] if item["id"] == "D")
        self.assertEqual(selected["source"], job["creative"]["logo_svg"])
        self.assertEqual(self.original_gpx, self.gpx.read_bytes(), "creative workflow must not mutate GPX input")
        self.assertEqual(creative, load_creative(self.job_dir))

    def test_custom_title_is_cleaned_and_print_limited(self) -> None:
        initialize_creative(self.job_dir)
        creative = choose_title(
            self.job_dir,
            custom_title="  2026-08-25_星溪竹林超长徒步纪念标题测试  ",
        )
        self.assertEqual("CUSTOM", creative["selected_title_id"])
        self.assertLessEqual(len(creative["selected_title"]), 14)
        self.assertNotIn("2026", creative["selected_title"])

    def test_dashboard_reserves_bottom_logo_view_and_readable_route_strip(self) -> None:
        app_js = (ROOT / "09_WebApp/local/app.js").read_text(encoding="utf-8")
        index_html = (ROOT / "09_WebApp/local/index.html").read_text(encoding="utf-8")
        dashboard_css = (ROOT / "09_WebApp/local/dashboard.css").read_text(encoding="utf-8")

        self.assertIn("{label:'底部视图'", app_js)
        self.assertIn("const PREVIEW_REQUIRED_VIEWS=3", app_js)
        self.assertIn("data-creative-proof", app_js)
        self.assertIn("第 4 视角确认底面 Logo", index_html)
        self.assertIn('id="preview-count">0 / 4', index_html)
        self.assertIn("#preview-gallery{grid-template-columns:repeat(4,minmax(0,1fr))}", dashboard_css)
        self.assertIn("grid-template-rows:auto 150px minmax(0,1fr) auto auto", dashboard_css)
        self.assertIn("grid-template-rows:auto 150px minmax(0,1fr) auto auto", dashboard_css)


if __name__ == "__main__":
    unittest.main()
