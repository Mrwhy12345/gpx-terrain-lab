#!/usr/bin/env python3
"""Regression check for concurrent job metadata reads and writes."""
from __future__ import annotations

import importlib.util
import json
import tempfile
import threading
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CONFIGURE_ROUTE_SCENE = ROOT / "07_Knowledge/tools/configure_route_scene.py"


def load_configure_module():
    spec = importlib.util.spec_from_file_location("configure_route_scene", CONFIGURE_ROUTE_SCENE)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {CONFIGURE_ROUTE_SCENE}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AtomicJobMetadataTest(unittest.TestCase):
    def test_readers_never_observe_partial_json(self):
        module = load_configure_module()
        errors: list[Exception] = []
        finished = threading.Event()

        with tempfile.TemporaryDirectory(prefix="gpx_job_atomic_") as temporary_dir:
            job_path = Path(temporary_dir) / "job.json"
            module.write_json_atomic(job_path, {"sequence": 0})

            def read_repeatedly():
                while not finished.is_set():
                    try:
                        json.loads(job_path.read_text(encoding="utf-8"))
                    except Exception as exc:  # pragma: no cover - assertion payload
                        errors.append(exc)
                        finished.set()

            reader = threading.Thread(target=read_repeatedly)
            reader.start()
            for sequence in range(1_000):
                module.write_json_atomic(
                    job_path,
                    {"sequence": sequence, "title": "星溪竹林" * 20},
                )
            finished.set()
            reader.join(timeout=2)

            self.assertFalse(errors, errors)
            self.assertEqual(
                json.loads(job_path.read_text(encoding="utf-8"))["sequence"],
                999,
            )


if __name__ == "__main__":
    unittest.main()
