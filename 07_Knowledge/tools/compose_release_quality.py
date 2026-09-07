#!/usr/bin/env python3
"""Compose independent creative, engineering, and interface release gates."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


def read_json(path: Path, default=None):
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else default


def sha256(path: Path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def gate(status, evidence, standard):
    return {"status": status, "evidence": evidence, "standard": standard}


def main():
    if len(sys.argv) != 3:
        raise SystemExit("Expected JOB_DIR REPORT.json")
    job_dir, report_path = Path(sys.argv[1]), Path(sys.argv[2])
    job = read_json(job_dir / "job.json", {})
    engineering_report = read_json(job_dir / "review/generic_release_qa.json", {})
    logo_report = read_json(job_dir / "review/logo.json", {})
    approval = read_json(job_dir / "review/creative_final_approval.json", {})
    creative = job.get("creative", {})
    source = job_dir / creative.get("logo_svg", "missing")
    production = job_dir / "work/route_logo.svg"
    render = job_dir / "review/logo.png"
    source_hash = sha256(source) if source.is_file() else None
    production_hash = sha256(production) if production.is_file() else None
    render_hash = sha256(render) if render.is_file() else None
    geometry_ok = bool(logo_report.get("logo_parts")) and all(
        part.get("non_manifold_edges") == 0 for part in logo_report.get("logo_quality", [])
    )
    approval_ok = (
        approval.get("status") == "PASS"
        and approval.get("approved_source_sha256") == source_hash
        and approval.get("approved_final_render_sha256") == render_hash
        and approval.get("visual_fidelity") == "PASS"
    )
    creative_checks = {
        "C1_identity_and_provenance": gate(
            "PASS" if creative.get("confirmed") and source.is_file() else "FAIL",
            {"logo_id": creative.get("logo_id"), "source": str(source), "source_sha256": source_hash},
            "Logo identity and source must be named, persisted, and confirmed.",
        ),
        "C2_content_contract": gate(
            "PASS" if creative.get("selected_title") and job.get("customer_input", {}).get("display_date") else "FAIL",
            {"title": creative.get("selected_title"), "date": job.get("customer_input", {}).get("display_date")},
            "Confirmed title/date/route facts must be present.",
        ),
        "C3_visual_fidelity": gate(
            "PASS" if approval_ok else "NOT_TESTED",
            {"approval": approval or None, "final_render": str(render), "final_render_sha256": render_hash},
            "The final bottom render must be compared with the named reference and explicitly approved; geometry validity is not visual fidelity.",
        ),
        "C4_print_adaptation": gate(
            "PASS" if geometry_ok else "FAIL",
            {"parts": logo_report.get("logo_parts"), "quality": logo_report.get("logo_quality")},
            "Adapted mark must use closed printable bodies with zero non-manifold edges.",
        ),
    }
    engineering_checks = {
        "E1_release_contract": gate(
            "PASS" if engineering_report.get("status") == "PASS" else "FAIL",
            {"report": "review/generic_release_qa.json", "status": engineering_report.get("status")},
            "5x3MF+1xBlend, dimensions, topology, Z, materials and assembly gates must pass.",
        )
    }
    interface_checks = {
        "I1_approved_source_reaches_production": gate(
            "PASS" if source_hash and source_hash == production_hash else "FAIL",
            {"approved_source_sha256": source_hash, "production_source_sha256": production_hash},
            "Production must consume the exact confirmed SVG bytes.",
        ),
        "I2_creative_geometry_preserves_engineering": gate(
            "PASS" if logo_report.get("flush_with_bottom") and logo_report.get("base_quality", {}).get("non_manifold_edges") == 0 else "FAIL",
            {"flush_with_bottom": logo_report.get("flush_with_bottom"), "base_quality": logo_report.get("base_quality")},
            "Creative geometry must remain flush and must not break the base mesh.",
        ),
    }
    statuses = [item["status"] for group in (creative_checks, engineering_checks, interface_checks) for item in group.values()]
    if "FAIL" in statuses:
        overall = "FAIL"
    elif "NOT_TESTED" in statuses:
        overall = "NEEDS_CREATIVE_REVIEW"
    else:
        overall = "PASS"
    payload = {
        "schema_version": "QMS-2.0",
        "overall_status": overall,
        "creative": {"status": "PASS" if all(x["status"] == "PASS" for x in creative_checks.values()) else "NEEDS_REVIEW", "checks": creative_checks},
        "engineering": {"status": engineering_checks["E1_release_contract"]["status"], "checks": engineering_checks},
        "interface": {"status": "PASS" if all(x["status"] == "PASS" for x in interface_checks.values()) else "FAIL", "checks": interface_checks},
        "rule": "Creative, engineering, and interface gates are independent; overall PASS requires all three PASS.",
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    main()
