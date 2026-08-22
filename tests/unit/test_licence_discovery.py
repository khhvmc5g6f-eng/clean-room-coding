from pathlib import Path

from cleanroom.licence.discovery import discover


def test_discovers_mit_from_licence_file(tmp_path: Path):
    (tmp_path / "LICENSE").write_text(
        "MIT License\n\nCopyright (c) 2020 Example\n\n"
        'Permission is hereby granted, free of charge, to any person obtaining a copy\n',
        encoding="utf-8",
    )
    findings = discover(tmp_path)
    assert any(f.concluded == "MIT" and f.confidence == "high" for f in findings)


def test_discovers_spdx_header(tmp_path: Path):
    # REUSE-IgnoreStart -- fixture data for the scanner under test, not a
    # real SPDX header for this file.
    (tmp_path / "main.py").write_text("# SPDX-License-Identifier: Apache-2.0\nprint('hi')\n", encoding="utf-8")
    # REUSE-IgnoreEnd
    findings = discover(tmp_path)
    header_findings = [f for f in findings if f.path == "main.py"]
    assert header_findings and header_findings[0].concluded == "Apache-2.0"


def test_package_json_declared_licence(tmp_path: Path):
    (tmp_path / "package.json").write_text('{"name": "x", "license": "MIT"}', encoding="utf-8")
    findings = discover(tmp_path)
    assert any(f.declared == "MIT" for f in findings)


def test_conflicting_licence_texts_are_flagged_not_silently_resolved(tmp_path: Path):
    # A LICENSE file containing fragments of two fingerprints should be
    # low-confidence/conflicting, never silently picked as one or the other.
    (tmp_path / "LICENSE").write_text(
        "MIT License\n\nPermission is hereby granted, free of charge, to any person obtaining a copy\n\n"
        "-- also see below --\n\nApache License\nVersion 2.0\n",
        encoding="utf-8",
    )
    findings = discover(tmp_path)
    licence_file_finding = [f for f in findings if f.path == "LICENSE"][0]
    assert licence_file_finding.conflicting_evidence is True
    assert licence_file_finding.confidence == "low"
