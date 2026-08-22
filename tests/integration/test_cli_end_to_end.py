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

    _run(runner, ["--project", str(project_dir), "init", "--name", "Demo", "--id", "demo", "--target-language", "python"])
    assert (project_dir / ".cleanroom.yml").is_file()

    (project_dir / "zone-r" / "lib").mkdir(parents=True)
    (project_dir / "zone-r" / "lib" / "LICENSE").write_text(
        "MIT License\n\nPermission is hereby granted, free of charge, to any person obtaining a copy\n",
        encoding="utf-8",
    )

    inspect_result = _run(runner, ["--project", str(project_dir), "--json", "inspect", str(project_dir / "zone-r")])
    inspect_payload = json.loads(inspect_result.output)
    # zone-r/.gitkeep (from `init`) + zone-r/lib/LICENSE (just added) = 2 files.
    assert inspect_payload["file_count"] == 2
    assert inspect_payload["extensions"] == {"(none)": 2}

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


def _computed_level(runner: CliRunner, project_dir: Path) -> dict:
    result = _run(runner, ["--project", str(project_dir), "--json", "status"])
    return json.loads(result.output)["computed_maturity"]


def test_computed_maturity_level_advances_with_real_project_state(tmp_path: Path):
    """`cleanroom status`'s computed_maturity is meant to be derived purely
    from on-disk project state, not the declared .cleanroom.yml value --
    drive a project through CR1 -> CR2 -> CR3 -> CR4 and confirm the
    computed level actually advances at each real milestone, and that CR5
    (adversarial legal review by qualified counsel) never auto-grants."""
    runner = CliRunner()
    project_dir = tmp_path / "proj"
    project_dir.mkdir()

    _run(runner, ["--project", str(project_dir), "init", "--name", "Demo", "--id", "demo", "--target-language", "python"])
    assert _computed_level(runner, project_dir)["computed_level"] == "CR1"

    (project_dir / "zone-r" / "lib").mkdir(parents=True)
    (project_dir / "zone-r" / "lib" / "LICENSE").write_text("MIT License\n\nPermission is hereby granted...\n", encoding="utf-8")
    _run(runner, ["--project", str(project_dir), "intake", "--source", "lib", "--access-authority", "public"])
    _run(runner, ["--project", str(project_dir), "jurisdiction"])

    (project_dir / "zone-h" / "spec.md").write_text("GIVEN a list\nWHEN sorted\nTHEN it is ordered\n", encoding="utf-8")
    _run(runner, ["--project", str(project_dir), "sanitise", str(project_dir / "zone-h" / "spec.md")])
    _run(runner, ["--project", str(project_dir), "handoff", "--specification-version", "v1", "--all-c0"])
    _run(runner, ["--project", str(project_dir), "build", "--role", "Implementation Team"])
    assert _computed_level(runner, project_dir)["computed_level"] == "CR2"

    (project_dir / "zone-i").mkdir(exist_ok=True)
    (project_dir / "zone-i" / "requirements.txt").write_text("click==8.1.7\n", encoding="utf-8")
    _run(runner, ["--project", str(project_dir), "provenance"])
    assert _computed_level(runner, project_dir)["computed_level"] == "CR3"

    (project_dir / "zone-r" / "sort.py").write_text("def sort_ref(x):\n    return sorted(x)\n", encoding="utf-8")
    (project_dir / "zone-i" / "sort.py").write_text("def totally_different_impl(y):\n    result = []\n    return result\n", encoding="utf-8")
    similarity_result = _run(runner, ["--project", str(project_dir), "similarity", str(project_dir / "zone-r"), str(project_dir / "zone-i")])
    assert json.loads(similarity_result.output)["comparisons_skipped"] == 0
    _run(runner, ["--project", str(project_dir), "legal", "--access-authority", "public"])

    final = _computed_level(runner, project_dir)
    assert final["computed_level"] == "CR4"
    assert final["declared_level"] == "CR2"  # default_config()'s declaration, never silently changed
    assert final["matches_declared"] is False

    cr5 = next(level for level in final["levels"] if level["level"] == "CR5")
    assert cr5["satisfied"] is False
    counsel_criterion = next(c for c in cr5["criteria"] if "counsel" in c["description"])
    assert counsel_criterion["met"] is False  # never auto-granted, even though CR4 is fully satisfied


def test_provenance_resolve_transitive_is_opt_in_and_writes_evidence(tmp_path: Path, monkeypatch):
    """--resolve-transitive must be opt-in (plain `cleanroom provenance`
    stays offline, no transitive-dependencies.json) and, when passed,
    actually wire discovered direct dependencies through to
    resolve_transitive() and persist the result."""
    from cleanroom.provenance import transitive as transitive_module

    runner = CliRunner()
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    _run(runner, ["--project", str(project_dir), "init", "--name", "Demo", "--id", "demo", "--target-language", "python"])
    (project_dir / "zone-i" / "requirements.txt").write_text("click==8.1.7\n", encoding="utf-8")

    plain_result = _run(runner, ["--project", str(project_dir), "--json", "provenance"])
    assert "transitive" not in json.loads(plain_result.output)
    assert not (project_dir / "evidence" / "sbom" / "transitive-dependencies.json").is_file()

    monkeypatch.setattr(transitive_module, "_pypi_lookup", lambda name, version: (version or "8.1.7", [], "BSD-3-Clause"))
    resolved_result = _run(runner, ["--project", str(project_dir), "--json", "provenance", "--resolve-transitive"])
    payload = json.loads(resolved_result.output)
    assert payload["transitive"] == {
        "resolved": 1, "unresolved": 0,
        "path": str(project_dir / "evidence" / "sbom" / "transitive-dependencies.json"),
    }
    written = json.loads((project_dir / "evidence" / "sbom" / "transitive-dependencies.json").read_text(encoding="utf-8"))
    assert written["resolved"][0]["name"] == "click"
    assert written["resolved"][0]["licence"] == "BSD-3-Clause"


def test_verify_export_in_toto_links_is_opt_in_and_writes_one_file_per_event(tmp_path: Path):
    runner = CliRunner()
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    _run(runner, ["--project", str(project_dir), "init", "--name", "Demo", "--id", "demo", "--target-language", "python"])

    plain_result = _run(runner, ["--project", str(project_dir), "--json", "verify"])
    assert "in_toto_links" not in json.loads(plain_result.output)
    assert not (project_dir / "evidence" / "in-toto-links").is_dir()

    exported_result = _run(runner, ["--project", str(project_dir), "--json", "verify", "--export-in-toto-links"])
    payload = json.loads(exported_result.output)
    assert payload["in_toto_links"]["count"] == 1  # just the "cleanroom init" event so far
    link_dir = project_dir / "evidence" / "in-toto-links"
    files = sorted(link_dir.glob("*.link.json"))
    assert len(files) == 1
    statement = json.loads(files[0].read_text(encoding="utf-8"))
    assert statement["_type"] == "https://in-toto.io/Statement/v1"
    assert statement["predicate"]["name"] == "cleanroom init"
    assert statement["unsigned"] is True


def test_legal_picks_up_similarity_and_requirement_graph_facts(tmp_path: Path):
    """Regression test: `cleanroom legal` previously never loaded
    evidence/similarity-findings.json or requirements.json into the
    CaseBundle it builds, so 'copying'/'substantiality' and
    'derivative_work_question' always reported UNKNOWN even after
    `cleanroom similarity`/`cleanroom specify` had produced real facts.
    Both must now be reflected in the legal findings."""
    runner = CliRunner()
    project_dir = tmp_path / "proj"
    project_dir.mkdir()

    _run(runner, ["--project", str(project_dir), "init", "--name", "Demo", "--id", "demo", "--target-language", "python"])

    (project_dir / "evidence").mkdir(parents=True, exist_ok=True)
    (project_dir / "evidence" / "similarity-findings.json").write_text(
        json.dumps([
            {"id": "SIM-STRUCT-00000", "method": "structural", "reference_ref": "a.py", "implementation_ref": "a.py",
             "classification": "suspicious", "requires_finding": True, "score": 0.9, "threshold": 0.15},
        ]),
        encoding="utf-8",
    )

    _run(runner, [
        "--project", str(project_dir), "specify", "add-requirement",
        "--id", "CR-REQ-000001", "--kind", "requirement",
        "--statement", "sorts ascending", "--classification", "source_implementation_detail",
    ])

    legal_result = _run(runner, ["--project", str(project_dir), "--json", "legal", "--access-authority", "public"])
    findings = {f["issue"]: f for f in json.loads(legal_result.output)["findings"]}
    assert findings["copying"]["decision_state"] == "AMBER"
    assert findings["copying"]["confidence"] != "insufficient_evidence"
    assert findings["derivative_work_question"]["decision_state"] == "AMBER"
