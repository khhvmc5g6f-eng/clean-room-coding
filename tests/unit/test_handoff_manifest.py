from pathlib import Path

import pytest

from cleanroom.exit_codes import ContaminationFailure
from cleanroom.handoff.manifest import (
    FACTS_DOC_FILENAME,
    build_manifest,
    validate_facts_document,
    verify_manifest,
    write_facts_doc,
    write_manifest,
)


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


# --------------------------------------------------------------------------- facts-only (facts-json) handoff format


def _valid_facts_doc() -> dict:
    return {
        "schema_version": "1.0.0",
        "facts": [
            {"kind": "enum_value", "container": "HardwareModel", "name": "SEEED_WIO_TRACKER_L1_PRO_1W", "value": 144},
            {
                "kind": "field", "container": "EnvironmentMetrics", "name": "lightning_strike_count_1h",
                "number": 40, "type": "uint32", "optional": True,
            },
        ],
    }


def test_validate_facts_document_accepts_conforming_document():
    assert validate_facts_document(_valid_facts_doc()) == []


def test_validate_facts_document_rejects_unknown_top_level_key():
    doc = _valid_facts_doc()
    doc["notes"] = "This is a paragraph of free-form commentary about the protocol that should not be here."
    errors = validate_facts_document(doc)
    assert errors  # additionalProperties: false at the top level rejects this


def test_validate_facts_document_rejects_extra_keys_on_a_fact():
    doc = _valid_facts_doc()
    doc["facts"][0]["explanation"] = "The reference implementation handles this enum value specially because..."
    errors = validate_facts_document(doc)
    assert errors  # additionalProperties: false on the fact object rejects the extra key


def test_validate_facts_document_rejects_prose_length_note():
    doc = _valid_facts_doc()
    doc["facts"][0]["notes"] = (
        "This note is deliberately far longer than the eighty character limit permitted for a short annotation "
        "and reads like copied commentary rather than a bare fact, which is exactly what this schema exists to catch."
    )
    errors = validate_facts_document(doc)
    assert errors


def test_validate_facts_document_rejects_multiline_note():
    doc = _valid_facts_doc()
    doc["facts"][0]["notes"] = "short first line\nbut then a second line sneaks in"
    errors = validate_facts_document(doc)
    assert errors  # the short_note pattern forbids newlines even under the length cap


def test_validate_facts_document_rejects_prose_shaped_value():
    doc = _valid_facts_doc()
    doc["facts"][0]["value"] = "this looks like a sentence of copied commentary not a bare literal"
    errors = validate_facts_document(doc)
    assert errors
    assert any("value" in e for e in errors)


def test_validate_facts_document_rejects_unknown_kind():
    doc = _valid_facts_doc()
    doc["facts"][0]["kind"] = "prose_summary"
    errors = validate_facts_document(doc)
    assert errors  # kind is a closed enum, not a free-text tag


def test_validate_facts_document_rejects_non_object_root():
    assert validate_facts_document(["not", "an", "object"]) != []


def test_write_facts_doc_persists_into_zone_h(tmp_path: Path):
    zone_h = tmp_path / "zone-h"
    zone_h.mkdir()
    doc = _valid_facts_doc()
    assert validate_facts_document(doc) == []
    path = write_facts_doc(doc, zone_h)
    assert path == zone_h / FACTS_DOC_FILENAME
    assert path.is_file()


def test_build_manifest_records_facts_document_reference(tmp_path: Path):
    """When a facts document has been validated and written, build_manifest
    must record its path+hash in the manifest (facts_document field) so
    the handoff is provably tied to that exact facts document, the same
    way every other Zone H file is hashed."""
    zone_h = tmp_path / "zone-h"
    zone_h.mkdir()
    (zone_h / "spec.md").write_text("GIVEN/WHEN/THEN", encoding="utf-8")
    doc = _valid_facts_doc()
    assert validate_facts_document(doc) == []
    facts_path = write_facts_doc(doc, zone_h)

    from cleanroom.util import sha256_file

    manifest = build_manifest(
        project_id="demo", specification_version="v1", zone_h=zone_h,
        file_contamination={"spec.md": "C0"}, sanitisation_report_hash="0" * 64,
        facts_document={"path": FACTS_DOC_FILENAME, "sha256": sha256_file(facts_path)},
    )
    assert manifest["facts_document"]["path"] == FACTS_DOC_FILENAME
    assert len(manifest["facts_document"]["sha256"]) == 64
    # The facts document itself must never show up as a regular handoff
    # file entry (it's a distinct, separately-tracked artefact type).
    assert all(f["path"] != FACTS_DOC_FILENAME for f in manifest["files"])
