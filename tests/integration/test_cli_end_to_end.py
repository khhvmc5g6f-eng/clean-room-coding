"""Drives the full pipeline through the CLI, mirroring docs/quickstart.md.
This is the project's own end-to-end proof that init -> intake -> licence ->
jurisdiction -> sanitise -> handoff -> specify -> legal -> judge -> report ->
release -> status all interoperate correctly on a fresh project.
"""

import json
from pathlib import Path

from click.testing import CliRunner

from cleanroom.cli import main


def _run(runner: CliRunner, args: list[str], **kwargs):
    result = runner.invoke(main, args, **kwargs)
    assert result.exit_code in (0, None), f"{args} failed ({result.exit_code}): {result.output}\n{result.exception}"
    return result


def test_full_pipeline(tmp_path: Path, monkeypatch):
    runner = CliRunner()
    project_dir = tmp_path / "proj"
    project_dir.mkdir()

    _run(runner, ["--project", str(project_dir), "init", "--name", "Demo", "--id", "demo"])
    assert (project_dir / ".cleanroom.yml").is_file()

    (project_dir / "zone-r" / "lib").mkdir(parents=True)
    (project_dir / "zone-r" / "lib" / "LICENSE").write_text(
        "MIT License\n\nPermission is hereby granted, free of charge, to any person obtaining a copy\n",
        encoding="utf-8",
    )

    result = _run(runner, ["--project", str(project_dir), "--json", "licence", str(project_dir / "zone-r")])
    payload = json.loads(result.output)
    assert payload["blocking"] is False
    assert payload["findings"][0]["concluded"] == "MIT"

    _run(runner, ["--project", str(project_dir), "intake", "--source", "lib", "--access-authority", "public"])
    _run(runner, ["--project", str(project_dir), "jurisdiction"])
    assert (project_dir / "JURISDICTION_MATRIX.json").is_file()

    (project_dir / "zone-h" / "spec.md").write_text(
        "GIVEN a list\nWHEN sorted ascending\nTHEN alphabetical order is returned\n", encoding="utf-8"
    )
    _run(runner, ["--project", str(project_dir), "sanitise", str(project_dir / "zone-h" / "spec.md")])
    _run(runner, ["--project", str(project_dir), "handoff", "--specification-version", "v1", "--all-c0"])
    assert (project_dir / "zone-h" / "HANDOFF_MANIFEST.json").is_file()

    _run(runner, [
        "--project", str(project_dir), "specify", "add-requirement",
        "--id", "CR-REQ-000001", "--kind", "requirement",
        "--statement", "sorts ascending", "--classification", "observable_requirement",
    ])

    (project_dir / "zone-i").mkdir(exist_ok=True)
    (project_dir / "zone-i" / "requirements.txt").write_text("click==8.1.7\n", encoding="utf-8")
    _run(runner, ["--project", str(project_dir), "provenance"])

    _run(runner, ["--project", str(project_dir), "legal", "--access-authority", "public"])
    _run(runner, ["--project", str(project_dir), "judge"])
    assert list((project_dir / "evidence" / "judicial-review").glob("*-judicial-prompt.md"))

    report_result = _run(runner, ["--project", str(project_dir), "report", "--version", "0.1.0"])
    assert "Global decision" in report_result.output
    assert (project_dir / "CLEAN_ROOM_CERTIFICATE.json").is_file()

    release_result = runner.invoke(main, ["--project", str(project_dir), "--json", "release"])
    # AMBER global decision + human sign-off required -> MANUAL_REVIEW_REQUIRED (9), never a silent pass.
    assert release_result.exit_code == 9
    release_payload = json.loads(release_result.output)
    assert release_payload["release_allowed"] is True
    assert release_payload["human_signoff_still_required"] is True

    status_result = _run(runner, ["--project", str(project_dir), "--json", "status"])
    status_payload = json.loads(status_result.output)
    assert status_payload["project"] == "demo"
    assert status_payload["ledger_events"] > 0

    verify_result = _run(runner, ["--project", str(project_dir), "--json", "verify"])
    verify_payload = json.loads(verify_result.output)
    assert verify_payload["ledger_intact"] is True
    assert verify_payload["handoff_manifest_intact"] is True
