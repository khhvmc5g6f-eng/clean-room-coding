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


def test_symlink_out_of_zone_h_is_rejected_not_smuggled(tmp_path: Path):
    """A symlink in Zone H pointing at Zone R content must never be
    silently hashed into the 'authorised for implementation' manifest."""
    zone_h = tmp_path / "zone-h"
    zone_h.mkdir()
    zone_r = tmp_path / "zone-r"
    zone_r.mkdir()
    (zone_r / "proprietary.py").write_text("original reference source", encoding="utf-8")
    (zone_h / "spec.md").write_text("GIVEN/WHEN/THEN", encoding="utf-8")
    (zone_h / "smuggled.py").symlink_to(zone_r / "proprietary.py")

    with pytest.raises(ContaminationFailure) as exc_info:
        build_manifest(
            project_id="demo", specification_version="v1", zone_h=zone_h,
            file_contamination={"spec.md": "C0", "smuggled.py": "C0"},
            sanitisation_report_hash="0" * 64,
        )
    assert "smuggled.py" in str(exc_info.value)
