#!/usr/bin/env python3
"""Release gate for a generic 5×3MF + 1×Blend Web job."""

from __future__ import annotations

import json
import subprocess
import sys
import zipfile
from pathlib import Path


def main():
    if len(sys.argv) != 3:
        raise SystemExit("Expected FINAL_DIR REPORT.json")
    final, report = map(Path, sys.argv[1:])
    projects = sorted(final.glob("*.3mf")); blends = sorted(final.glob("*.blend"))
    checks = []
    if len(projects) != 5 or len(blends) != 1:
        raise RuntimeError(f"Expected 5 3MF + 1 Blend, got {len(projects)} + {len(blends)}")
    tools = Path(__file__).resolve().parent
    for project in projects:
        with zipfile.ZipFile(project) as archive:
            bad = archive.testzip()
            if bad: raise RuntimeError(f"Corrupt 3MF member: {project.name}:{bad}")
        result = subprocess.run(
            [sys.executable, str(tools / "validate_bambu_3mf_build_bounds.py"), str(project)],
            text=True, capture_output=True,
        )
        if result.returncode: raise RuntimeError(result.stdout + result.stderr)
        checks.append(result.stdout.strip())
    result = subprocess.run(
        [sys.executable, str(tools / "validate_bambu_3mf_z.py"), *map(str, projects)],
        text=True, capture_output=True,
    )
    if result.returncode: raise RuntimeError(result.stdout + result.stderr)
    checks.extend(line for line in result.stdout.splitlines() if line.strip())
    header = blends[0].read_bytes()[:7]
    if not (header.startswith(b"BLENDER") or header.startswith(b"\x28\xb5\x2f\xfd")):
        raise RuntimeError(f"Unexpected Blender header: {header!r}")
    payload = {"status":"PASS","contract":"5x3MF+1xBlend","zip_test":"PASS","build_and_z_checks":checks}
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    main()
