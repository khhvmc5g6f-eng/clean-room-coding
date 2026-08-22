from pathlib import Path

import pytest

from cleanroom.exit_codes import ContaminationFailure
from cleanroom.handoff.manifest import build_manifest, verify_manifest, write_manifest


def test_build_manifest_hashes_all_files(tmp_path: Path):
    zone_h = tmp_path / "zone-h"
    zone_h.mkdir()
    (zone_h / "spec.md").write_text("GIVEN/WHEN/THEN", encoding="utf-8")
    manifest = build_manifest(
        project_id="demo", specification_version="v1", zone_h=zone_h,
        file_contamination={"spec.md": "C0"}, sanitisation_report_hash="0" * 64,
    )
    assert len(manifest["files"]) == 1
    assert manifest["files"][0]["path"] == "spec.md"
    assert len(manifest["manifest_hash"]) == 64


def test_non_c0_file_blocks_handoff(tmp_path: Path):
    zone_h = tmp_path / "zone-h"
    zone_h.mkdir()
    (zone_h / "leaked.py").write_text("source code", encoding="utf-8")
    with pytest.raises(ContaminationFailure):
        build_manifest(
            project_id="demo", specification_version="v1", zone_h=zone_h,
            file_contamination={"leaked.py": "C3"}, sanitisation_report_hash="0" * 64,
        )


def test_verify_manifest_detects_modified_file(tmp_path: Path):
    zone_h = tmp_path / "zone-h"
    zone_h.mkdir()
    (zone_h / "spec.md").write_text("original", encoding="utf-8")
    manifest = build_manifest(
        project_id="demo", specification_version="v1", zone_h=zone_h,
        file_contamination={"spec.md": "C0"}, sanitisation_report_hash="0" * 64,
    )
    write_manifest(manifest, zone_h)
    assert verify_manifest(manifest, zone_h) == []

    (zone_h / "spec.md").write_text("modified after handoff", encoding="utf-8")
    problems = verify_manifest(manifest, zone_h)
    assert problems and "hash mismatch" in problems[0]
