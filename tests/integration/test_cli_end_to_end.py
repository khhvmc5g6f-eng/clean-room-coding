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

    _run(runner, [
        "--project", str(project_dir), "specify", "add-requirement",
        "--id", "CR-REQ-000001", "--kind", "requirement",
        "--statement", "sorts ascending", "--classification", "observable_requirement",
    ])

    (project_dir / "zone-h" / "spec.md").write_text(
        "GIVEN a list\nWHEN sorted ascending\nTHEN alphabetical order is returned\n", encoding="utf-8"
    )
    _run(runner, ["--project", str(project_dir), "sanitise", str(project_dir / "zone-h" / "spec.md")])
    gate_result = _run(runner, ["--project", str(project_dir), "--json", "gate",
        "--specification-version", "v1", "--decision", "pass",
        "--reviewer", "Test Reviewer", "--notes", "Sufficient for independent implementation.",
    ])
    gate_payload = json.loads(gate_result.output)
    assert gate_payload["automated_signal"] == "sufficient"
    assert gate_payload["overrode_automated_signal"] is False
    _run(runner, ["--project", str(project_dir), "handoff", "--specification-version", "v1", "--all-c0"])
    assert (project_dir / "zone-h" / "HANDOFF_MANIFEST.json").is_file()

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

    _run(runner, [
        "--project", str(project_dir), "specify", "add-requirement",
        "--id", "CR-REQ-000001", "--kind", "requirement",
        "--statement", "sorts ascending", "--classification", "observable_requirement",
    ])
    (project_dir / "zone-h" / "spec.md").write_text("GIVEN a list\nWHEN sorted\nTHEN it is ordered\n", encoding="utf-8")
    _run(runner, ["--project", str(project_dir), "sanitise", str(project_dir / "zone-h" / "spec.md")])
    _run(runner, ["--project", str(project_dir), "gate", "--specification-version", "v1", "--decision", "pass",
        "--reviewer", "Test Reviewer", "--notes", "Sufficient for independent implementation.",
    ])
    _run(runner, ["--project", str(project_dir), "handoff", "--specification-version", "v1", "--all-c0"])
    _run(runner, ["--project", str(project_dir), "build", "--role", "Implementation Team"])
    assert _computed_level(runner, project_dir)["computed_level"] == "CR2"

    (project_dir / "zone-i").mkdir(exist_ok=True)
    (project_dir / "zone-i" / "requirements.txt").write_text("click==8.1.7\n", encoding="utf-8")
    _run(runner, ["--project", str(project_dir), "provenance"])
    assert _computed_level(runner, project_dir)["computed_level"] == "CR3"

    (project_dir / "zone-r" / "sort.py").write_text("def sort_ref(x):\n    return sorted(x)\n", encoding="utf-8")
    (project_dir / "zone-i" / "sort.py").write_text("def totally_different_impl(y):\n    result = []\n    return result\n", encoding="utf-8")

    # 'cleanroom build' above registered a Zone-H+I-only implementation
    # agent for this project, so (per the fail-closed zone gating feature)
    # zone-scoped commands now REQUIRE --agent-id. This test isn't about
    # zone separation -- register a comparison-role agent with both R and
    # I access directly via AgentRegistry (there's no CLI role that grants
    # both; 'recruit' is Zone-R-only by design) purely so the similarity
    # call below can proceed ungated by this feature.
    from cleanroom.orchestration.agents import AgentRegistry
    comparison_agent = AgentRegistry(project_dir / "evidence").register(role="Similarity Reviewer", permitted_zones=["R", "I"])

    similarity_result = _run(runner, [
        "--project", str(project_dir), "--agent-id", comparison_agent.agent_id,
        "similarity", str(project_dir / "zone-r"), str(project_dir / "zone-i"),
    ])
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

    def fake_lookup(name, version):
        if name == "click":
            return (version or "8.1.7", ["colorama"], "BSD-3-Clause", None)
        return ("0.4.6", [], "BSD-3-Clause", "sha256:" + "d" * 64)

    monkeypatch.setattr(transitive_module, "_pypi_lookup", fake_lookup)
    resolved_result = _run(runner, ["--project", str(project_dir), "--json", "provenance", "--resolve-transitive"])
    payload = json.loads(resolved_result.output)
    assert payload["transitive"] == {
        "resolved": 2, "unresolved": 0,
        "path": str(project_dir / "evidence" / "sbom" / "transitive-dependencies.json"),
    }
    written = json.loads((project_dir / "evidence" / "sbom" / "transitive-dependencies.json").read_text(encoding="utf-8"))
    assert {d["name"] for d in written["resolved"]} == {"click", "colorama"}

    # The transitive dependency (colorama, resolved via --resolve-transitive
    # above) must also be merged into the actual SPDX/CycloneDX documents,
    # not just the separate transitive-dependencies.json artefact.
    spdx_doc = json.loads(Path(payload["spdx"]).read_text(encoding="utf-8"))
    assert {p["name"] for p in spdx_doc["packages"]} == {"demo", "click", "colorama"}
    cdx_doc = json.loads(Path(payload["cyclonedx"]).read_text(encoding="utf-8"))
    assert {c["name"] for c in cdx_doc["components"]} == {"click", "colorama"}
    assert written["resolved"][0]["licence"] == "BSD-3-Clause"

    # colorama's real registry-derived digest (see fake_lookup above) must
    # be carried through into the actual SPDX/CycloneDX documents, not just
    # the separate transitive-dependencies.json artefact.
    colorama_pkg = next(p for p in spdx_doc["packages"] if p["name"] == "colorama")
    assert colorama_pkg["checksums"] == [{"algorithm": "SHA256", "checksumValue": "d" * 64}]
    colorama_component = next(c for c in cdx_doc["components"] if c["name"] == "colorama")
    assert colorama_component["hashes"] == [{"alg": "SHA-256", "content": "d" * 64}]


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


def test_verify_signer_produces_a_real_signature_on_exported_links(tmp_path: Path, monkeypatch):
    """--signer wires through to intoto.sign_statement() for real -- with
    gpg mocked as available and successful, every exported statement must
    come out unsigned:false with a real signature block."""
    import cleanroom.provenance.intoto as intoto_module

    runner = CliRunner()
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    _run(runner, ["--project", str(project_dir), "init", "--name", "Demo", "--id", "demo", "--target-language", "python"])

    fake_result = type("R", (), {"returncode": 0, "stdout": b"-----BEGIN PGP SIGNATURE-----\nfake\n-----END PGP SIGNATURE-----\n"})()
    monkeypatch.setattr(intoto_module.shutil, "which", lambda name: "/usr/bin/gpg")
    monkeypatch.setattr(intoto_module.subprocess, "run", lambda *a, **k: fake_result)

    result = _run(runner, ["--project", str(project_dir), "--json", "verify", "--export-in-toto-links", "--signer", "ABCDEF1234567890"])
    payload = json.loads(result.output)
    assert payload["in_toto_links"]["signed_count"] == 1
    assert payload["in_toto_links"]["unsigned_count"] == 0

    link_dir = project_dir / "evidence" / "in-toto-links"
    statement = json.loads(next(link_dir.glob("*.link.json")).read_text(encoding="utf-8"))
    assert statement["unsigned"] is False
    assert statement["signature"]["signer_identity"] == "ABCDEF1234567890"


def test_verify_signer_falls_back_to_unsigned_without_real_gpg(tmp_path: Path):
    """No mocking here -- this environment genuinely has no gpg installed
    (or the key id is bogus), so --signer must not crash or fabricate a
    signature; every statement stays honestly unsigned."""
    runner = CliRunner()
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    _run(runner, ["--project", str(project_dir), "init", "--name", "Demo", "--id", "demo", "--target-language", "python"])

    result = _run(runner, ["--project", str(project_dir), "--json", "verify", "--export-in-toto-links", "--signer", "not-a-real-key-id"])
    payload = json.loads(result.output)
    assert payload["in_toto_links"]["signed_count"] == 0
    assert payload["in_toto_links"]["unsigned_count"] == 1


def test_heartbeat_detects_looping_agent_and_updates_registry(tmp_path: Path):
    """End-to-end proof that heartbeat.py -- 0% covered and unreachable
    from any CLI command before this -- is now real: register an agent,
    feed it identical-action ticks via `cleanroom heartbeat`, and confirm
    both the diagnosis and the actual registry status update."""
    runner = CliRunner()
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    _run(runner, ["--project", str(project_dir), "init", "--name", "Demo", "--id", "demo", "--target-language", "python"])
    build_result = _run(runner, ["--project", str(project_dir), "--json", "build", "--role", "Implementation Team"])
    agent_id = json.loads(build_result.output)["agent_id"]

    for _ in range(2):
        result = _run(runner, [
            "--project", str(project_dir), "--json", "heartbeat", agent_id,
            "--action-signature", "edit:same-file.py", "--files-modified", "1",
        ])
        assert json.loads(result.output)["status"] == "ACTIVE"

    looping_result = _run(runner, [
        "--project", str(project_dir), "--json", "heartbeat", agent_id,
        "--action-signature", "edit:same-file.py", "--files-modified", "1",
    ])
    payload = json.loads(looping_result.output)
    assert payload["status"] == "LOOPING"
    assert payload["tick_count"] == 3
    assert "Terminate" in payload["recommended_action"]

    status_result = _run(runner, ["--project", str(project_dir), "--json", "status"])
    status_payload = json.loads(status_result.output)
    assert status_payload["orphaned_agents"] == [agent_id]
    matching_agent = next(a for a in status_payload["agents"] if a["agent_id"] == agent_id)
    assert matching_agent["status"] == "LOOPING"


def test_heartbeat_reports_real_elapsed_time_between_ticks(tmp_path: Path):
    """`cleanroom heartbeat` now stamps every tick with a real timestamp
    at the moment it's called and surfaces a genuine efficiency summary --
    not a fabricated score, an honest measurement of actual elapsed time
    between real CLI invocations."""
    import time

    runner = CliRunner()
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    _run(runner, ["--project", str(project_dir), "init", "--name", "Demo", "--id", "demo", "--target-language", "python"])
    build_result = _run(runner, ["--project", str(project_dir), "--json", "build", "--role", "Implementation Team"])
    agent_id = json.loads(build_result.output)["agent_id"]

    first = _run(runner, ["--project", str(project_dir), "--json", "heartbeat", agent_id, "--action-signature", "edit:a.py", "--files-modified", "1"])
    first_efficiency = json.loads(first.output)["efficiency"]
    assert first_efficiency["stamped_ticks"] == 1
    assert first_efficiency["average_tick_interval_seconds"] is None  # only one stamped tick so far -- honestly None, not 0

    time.sleep(1.05)
    second = _run(runner, ["--project", str(project_dir), "--json", "heartbeat", agent_id, "--action-signature", "edit:b.py", "--files-modified", "1"])
    second_efficiency = json.loads(second.output)["efficiency"]
    assert second_efficiency["stamped_ticks"] == 2
    assert second_efficiency["average_tick_interval_seconds"] >= 1.0


def test_heartbeat_rejects_unregistered_agent_id(tmp_path: Path):
    runner = CliRunner()
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    _run(runner, ["--project", str(project_dir), "init", "--name", "Demo", "--id", "demo", "--target-language", "python"])
    result = runner.invoke(main, ["--project", str(project_dir), "heartbeat", "not-a-real-agent-id", "--action-signature", "x"])
    assert result.exit_code != 0
    assert "No agent registered" in str(result.exception) or "No agent registered" in result.output


def test_benchmark_command_does_not_require_a_cleanroom_project():
    """`cleanroom benchmark` evaluates the tool itself against its own
    fixture corpus, like `cleanroom doctor` -- no .cleanroom.yml/--project
    needed, unlike every other command in this file."""
    runner = CliRunner()
    result = runner.invoke(main, ["--json", "benchmark"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["case_count"] == 8
    assert 0.0 <= payload["precision"] <= 1.0


def test_legal_picks_up_sanitisation_blocked_history(tmp_path: Path):
    """Regression test: `cleanroom legal` never populated
    CaseBundle.sanitisation_blocked at all (always None), so the
    'confidentiality' heuristic could never distinguish a clean
    sanitisation history from one that actually caught something. A
    denied `cleanroom sanitise` run must now surface as
    sanitisation_blocked=True and drive 'confidentiality' to RED when
    access is contractual."""
    runner = CliRunner()
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    _run(runner, ["--project", str(project_dir), "init", "--name", "Demo", "--id", "demo", "--target-language", "python"])

    blocking_doc = project_dir / "zone-h" / "secret.md"
    blocking_doc.write_text("api_key = 'sk-thisisadefinitelyrealsecretlookingvalue123456'\n", encoding="utf-8")
    sanitise_result = runner.invoke(main, ["--project", str(project_dir), "sanitise", str(blocking_doc)])
    assert sanitise_result.exit_code != 0  # blocked, as intended

    legal_result = _run(runner, ["--project", str(project_dir), "--json", "legal", "--access-authority", "contractual"])
    findings = {f["issue"]: f for f in json.loads(legal_result.output)["findings"]}
    assert findings["confidentiality"]["decision_state"] == "RED"


def _setup_project_through_judge(runner: CliRunner, project_dir: Path) -> None:
    _run(runner, ["--project", str(project_dir), "init", "--name", "Demo", "--id", "demo", "--target-language", "python"])
    _run(runner, ["--project", str(project_dir), "jurisdiction"])
    _run(runner, ["--project", str(project_dir), "legal", "--access-authority", "public"])
    _run(runner, ["--project", str(project_dir), "judge"])


def test_judge_adjudicate_merges_answer_into_matching_finding(tmp_path: Path):
    """cleanroom judge previously only ever WROTE prompts -- there was no
    command anywhere that read a completed judicial-review answer back
    into the system, even though legal-finding.schema.json already has
    for_release_argument/against_release_argument/adjudication/reviewer
    fields clearly meant for exactly this. judge-adjudicate closes that
    loop: ingest one panel member's answer and merge it into the matching
    finding(s), matched by issue + the jurisdiction pack's real markets
    (not the pack id itself, which is a different string from what
    findings' own `jurisdiction` field holds -- see COUNTRY_TO_PACK)."""
    runner = CliRunner()
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    _setup_project_through_judge(runner, project_dir)

    answer_file = project_dir / "answer.json"
    answer_file.write_text(json.dumps([
        {"issue": "lawful_access", "decision_state": "GREEN_WITH_CONDITIONS", "adjudication": "Panel agrees."},
    ]), encoding="utf-8")

    result = _run(runner, [
        "--project", str(project_dir), "--json", "judge-adjudicate", "england-wales", str(answer_file),
        "--panel-member", "member-1",
    ])
    payload = json.loads(result.output)
    assert payload["issues_updated"] == ["lawful_access"]

    findings = json.loads((project_dir / "evidence" / "legal-findings.json").read_text(encoding="utf-8"))
    gb_lawful_access = next(f for f in findings if f["issue"] == "lawful_access" and f["jurisdiction"] == "gb")
    assert gb_lawful_access["reviewer"] == "simulated-england-wales-judicial-panel"
    assert gb_lawful_access["adjudication"] == "Panel agrees."
    assert len(gb_lawful_access["panel_adjudications"]) == 1
    # A market mapped to a DIFFERENT pack (US, not England & Wales) must
    # not be touched by this pack's adjudication.
    us_lawful_access = next(f for f in findings if f["issue"] == "lawful_access" and f["jurisdiction"] == "us")
    assert "panel_adjudications" not in us_lawful_access


def test_judge_adjudicate_worst_wins_across_disagreeing_panel_members(tmp_path: Path):
    """Part LIV: a single dissenting panel member's worse decision_state
    must never be smoothed over by another member's more favourable view,
    regardless of submission order."""
    runner = CliRunner()
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    _setup_project_through_judge(runner, project_dir)

    red_answer = project_dir / "red.json"
    red_answer.write_text(json.dumps([{"issue": "copying", "decision_state": "RED", "adjudication": "Dissents."}]), encoding="utf-8")
    green_answer = project_dir / "green.json"
    green_answer.write_text(json.dumps([{"issue": "copying", "decision_state": "GREEN_WITH_CONDITIONS", "adjudication": "No issue."}]), encoding="utf-8")

    _run(runner, ["--project", str(project_dir), "judge-adjudicate", "england-wales", str(red_answer), "--panel-member", "member-1"])
    _run(runner, ["--project", str(project_dir), "judge-adjudicate", "england-wales", str(green_answer), "--panel-member", "member-2"])

    findings = json.loads((project_dir / "evidence" / "legal-findings.json").read_text(encoding="utf-8"))
    gb_copying = next(f for f in findings if f["issue"] == "copying" and f["jurisdiction"] == "gb")
    assert gb_copying["decision_state"] == "RED"  # member-1's dissent wins, not averaged/overwritten
    assert len(gb_copying["panel_adjudications"]) == 2


def test_judge_adjudicate_resubmission_by_same_member_replaces_not_duplicates(tmp_path: Path):
    runner = CliRunner()
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    _setup_project_through_judge(runner, project_dir)

    first = project_dir / "first.json"
    first.write_text(json.dumps([{"issue": "copying", "decision_state": "RED", "adjudication": "Initial."}]), encoding="utf-8")
    revised = project_dir / "revised.json"
    revised.write_text(json.dumps([{"issue": "copying", "decision_state": "AMBER", "adjudication": "Revised down."}]), encoding="utf-8")

    _run(runner, ["--project", str(project_dir), "judge-adjudicate", "england-wales", str(first), "--panel-member", "member-1"])
    _run(runner, ["--project", str(project_dir), "judge-adjudicate", "england-wales", str(revised), "--panel-member", "member-1"])

    findings = json.loads((project_dir / "evidence" / "legal-findings.json").read_text(encoding="utf-8"))
    gb_copying = next(f for f in findings if f["issue"] == "copying" and f["jurisdiction"] == "gb")
    assert len(gb_copying["panel_adjudications"]) == 1  # replaced, not appended as a second entry
    assert gb_copying["decision_state"] == "AMBER"


def test_judge_adjudicate_reports_diversity_and_panel_size_completeness(tmp_path: Path):
    runner = CliRunner()
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    _setup_project_through_judge(runner, project_dir)

    answer_file = project_dir / "answer.json"
    answer_file.write_text(json.dumps([{"issue": "lawful_access", "decision_state": "GREEN_WITH_CONDITIONS"}]), encoding="utf-8")

    result = _run(runner, [
        "--project", str(project_dir), "--json", "judge-adjudicate", "england-wales", str(answer_file),
        "--panel-member", "member-1", "--model-provider", "anthropic",
    ])
    completeness = json.loads(result.output)["panel_completeness"]
    # Default config: panel_size=1, panel_diversity_required=False.
    assert completeness["panel_size_satisfied"] is True
    assert completeness["diversity_satisfied"] is True
    assert completeness["distinct_providers_recorded"] == ["anthropic"]


def test_release_panel_diversity_gate_blocks_then_passes_once_satisfied(tmp_path: Path):
    """End-to-end proof that `require_panel_diversity_gate` is real: judge-
    adjudicate already computed panel_size/diversity satisfaction per
    call, but before this gate existed nothing at release time ever read
    it back -- a project could configure panel_size=2,
    panel_diversity_required=true and have it silently ignored. With the
    gate opted into via .cleanroom.yml, `cleanroom release` must actually
    block while only one (same-provider) panel member has adjudicated,
    and actually pass once a second, different-provider member has."""
    import yaml

    from cleanroom.exit_codes import ExitCode

    runner = CliRunner()
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    _setup_project_through_judge(runner, project_dir)

    config_path = project_dir / ".cleanroom.yml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["providers"]["panel_size"] = 2
    config["providers"]["panel_diversity_required"] = True
    config["release_policy"]["require_panel_diversity_gate"] = True
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")

    answer_file = project_dir / "answer.json"
    answer_file.write_text(json.dumps([{"issue": "lawful_access", "decision_state": "GREEN_WITH_CONDITIONS"}]), encoding="utf-8")
    _run(runner, [
        "--project", str(project_dir), "--json", "judge-adjudicate", "england-wales", str(answer_file),
        "--panel-member", "member-1", "--model-provider", "anthropic",
    ])

    (project_dir / "zone-i").mkdir(exist_ok=True)
    _run(runner, ["--project", str(project_dir), "provenance"])
    _run(runner, ["--project", str(project_dir), "report", "--version", "0.1.0"])

    blocked = runner.invoke(main, ["--project", str(project_dir), "--json", "release"])
    blocked_payload = json.loads(blocked.output)
    assert blocked_payload["release_allowed"] is False
    assert blocked_payload["panel_diversity"]["satisfied"] is False
    assert any("lawful_access" in r for r in blocked_payload["reasons"])
    assert blocked.exit_code == int(ExitCode.POLICY_FAILURE)

    _run(runner, [
        "--project", str(project_dir), "--json", "judge-adjudicate", "england-wales", str(answer_file),
        "--panel-member", "member-2", "--model-provider", "openai",
    ])
    _run(runner, ["--project", str(project_dir), "report", "--version", "0.1.0"])

    passed = runner.invoke(main, ["--project", str(project_dir), "--json", "release"])
    passed_payload = json.loads(passed.output)
    assert passed_payload["panel_diversity"]["satisfied"] is True
    assert passed_payload["release_allowed"] is True


def test_release_panel_diversity_gate_is_opt_in_and_ignored_by_default(tmp_path: Path):
    """`panel_size`/`panel_diversity_required` (providers config) can be
    genuinely unsatisfied -- panel_completeness_across_findings correctly
    reports satisfied=False -- while `release_policy.require_panel_
    diversity_gate` stays at its default False (every project created
    before this gate existed). Release must still proceed: computing and
    reporting the unsatisfied state is not the same as enforcing it."""
    import yaml

    runner = CliRunner()
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    _setup_project_through_judge(runner, project_dir)

    config_path = project_dir / ".cleanroom.yml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["providers"]["panel_size"] = 2
    config["providers"]["panel_diversity_required"] = True
    # Deliberately NOT setting release_policy.require_panel_diversity_gate.
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")

    answer_file = project_dir / "answer.json"
    answer_file.write_text(json.dumps([{"issue": "lawful_access", "decision_state": "GREEN_WITH_CONDITIONS"}]), encoding="utf-8")
    _run(runner, [
        "--project", str(project_dir), "--json", "judge-adjudicate", "england-wales", str(answer_file),
        "--panel-member", "member-1", "--model-provider", "anthropic",
    ])

    (project_dir / "zone-i").mkdir(exist_ok=True)
    _run(runner, ["--project", str(project_dir), "provenance"])
    _run(runner, ["--project", str(project_dir), "report", "--version", "0.1.0"])

    result = runner.invoke(main, ["--project", str(project_dir), "--json", "release"])
    payload = json.loads(result.output)
    assert payload["panel_diversity"]["satisfied"] is False
    assert payload["panel_diversity"]["enforced"] is False
    assert payload["release_allowed"] is True


def test_judge_adjudicate_rejects_unmatched_issue(tmp_path: Path):
    runner = CliRunner()
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    _setup_project_through_judge(runner, project_dir)

    bad_answer = project_dir / "bad.json"
    bad_answer.write_text(json.dumps([{"issue": "not_a_real_issue", "decision_state": "GREEN_WITH_CONDITIONS"}]), encoding="utf-8")

    result = runner.invoke(main, ["--project", str(project_dir), "judge-adjudicate", "england-wales", str(bad_answer), "--panel-member", "member-1"])
    assert result.exit_code != 0


def test_agent_id_denies_implementation_scoped_agent_zone_r_access(tmp_path: Path):
    """`--agent-id` closes the real (not just unit-tested-in-isolation)
    gap docs/zones.py's own docstring named: cli.py's commands previously
    never routed a real file read through PathGuard per invocation. A
    Zone-H+I-only agent (registered via `cleanroom build`) must now be
    genuinely denied `cleanroom licence zone-r`, not just fail the
    self-test in isolation."""
    from cleanroom.cli import main

    runner = CliRunner()
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    _run(runner, ["--project", str(project_dir), "init", "--name", "Demo", "--id", "demo", "--target-language", "python"])
    (project_dir / "zone-r" / "lib").mkdir(parents=True)
    (project_dir / "zone-r" / "lib" / "LICENSE").write_text("MIT License\n", encoding="utf-8")

    # Before any implementation agent has been registered, --agent-id
    # remains optional -- this call succeeds (licence discovery runs;
    # whether findings pass policy is a separate matter this test doesn't
    # care about).
    unrestricted = runner.invoke(main, ["--project", str(project_dir), "licence", str(project_dir / "zone-r")])
    assert "PathGuard" not in unrestricted.output
    assert "--agent-id is required" not in unrestricted.output

    build_result = _run(runner, ["--project", str(project_dir), "--json", "build", "--role", "Backend Team"])
    agent_id = json.loads(build_result.output)["agent_id"]

    denied = runner.invoke(main, ["--agent-id", agent_id, "--project", str(project_dir), "--json", "licence", str(project_dir / "zone-r")])
    assert denied.exit_code == 4  # ContaminationFailure
    assert "PathGuard denied" in json.loads(denied.output)["error"]


def test_agent_id_allows_r_scoped_agent_zone_r_access(tmp_path: Path):
    """The allow path, not just the deny path: an agent actually
    registered WITH Zone R access must pass straight through with no
    PathGuard denial at all. Registered via 'cleanroom recruit', the real
    CLI path into AgentRegistry for a Reference-side agent (added
    alongside 'cleanroom build' for Implementation-side agents -- before
    this command existed, an R-scoped agent could only be registered by
    calling AgentRegistry directly in Python)."""
    from cleanroom.cli import main

    runner = CliRunner()
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    _run(runner, ["--project", str(project_dir), "init", "--name", "Demo", "--id", "demo", "--target-language", "python"])
    (project_dir / "zone-r" / "lib").mkdir(parents=True)
    (project_dir / "zone-r" / "lib" / "LICENSE").write_text("MIT License\n", encoding="utf-8")

    recruit_result = _run(runner, ["--project", str(project_dir), "--json", "recruit", "--role", "Analyst"])
    agent_id = json.loads(recruit_result.output)["agent_id"]

    result = runner.invoke(main, ["--agent-id", agent_id, "--project", str(project_dir), "--json", "licence", str(project_dir / "zone-r")])
    assert "PathGuard" not in result.output


def test_recruit_registers_an_r_scoped_agent_explicitly_denied_zone_h_and_i(tmp_path: Path):
    """'cleanroom recruit' is the Reference-side counterpart to 'cleanroom
    build' -- it must register an agent scoped to Zone R only, with Zone
    H and Zone I both explicitly prohibited (the same belt-and-suspenders
    pattern 'build' uses for Zone R), not just omitted from
    permitted_zones."""
    from cleanroom.cli import main

    runner = CliRunner()
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    _run(runner, ["--project", str(project_dir), "init", "--name", "Demo", "--id", "demo", "--target-language", "python"])

    recruit_result = _run(runner, ["--project", str(project_dir), "--json", "recruit", "--role", "Analyst", "--tool", "ast-grep", "--tool", "grep"])
    record = json.loads(recruit_result.output)
    assert record["permitted_zones"] == ["R"]
    assert str(project_dir / "zone-h") in record["prohibited_paths"]
    assert str(project_dir / "zone-i") in record["prohibited_paths"]
    assert record["tools"] == ["ast-grep", "grep"]

    denied = runner.invoke(main, ["--agent-id", record["agent_id"], "--project", str(project_dir), "--json", "sanitise", str(project_dir / "zone-h" / ".gitkeep")])
    assert denied.exit_code == 4  # ContaminationFailure
    assert "PathGuard denied" in json.loads(denied.output)["error"]


def test_diff_reference_denies_implementation_scoped_agent(tmp_path: Path):
    """'cleanroom diff-reference' reads the full content of zone-r/ to
    compute the baseline side of its diff, so it must be gated by the same
    opt-in --agent-id PathGuard check as 'inspect'/'licence' -- a
    Zone-H+I-only agent must be denied exactly as it would be from
    'cleanroom licence zone-r'."""
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    runner = CliRunner()
    _run(runner, ["--project", str(project_dir), "init", "--name", "Demo", "--id", "demo", "--target-language", "python"])
    (project_dir / "zone-r").mkdir(exist_ok=True)
    (project_dir / "zone-r" / "notes.txt").write_text("not a git checkout\n", encoding="utf-8")

    build_result = _run(runner, ["--project", str(project_dir), "--json", "build", "--role", "Backend Team"])
    agent_id = json.loads(build_result.output)["agent_id"]

    denied = runner.invoke(main, ["--agent-id", agent_id, "--project", str(project_dir), "--json", "diff-reference"])
    assert denied.exit_code == 4  # ContaminationFailure
    assert "PathGuard denied" in json.loads(denied.output)["error"]


def test_diff_reference_reports_a_clear_error_for_a_non_git_zone_r(tmp_path: Path):
    """Never fabricate a comparison against an unknown source (AGENTS.md
    item c): a zone-r/ that isn't a git checkout with a resolvable origin
    must fail with an explicit message, not a silent/empty diff."""
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    runner = CliRunner()
    _run(runner, ["--project", str(project_dir), "init", "--name", "Demo", "--id", "demo", "--target-language", "python"])
    (project_dir / "zone-r").mkdir(exist_ok=True)
    (project_dir / "zone-r" / "notes.txt").write_text("not a git checkout\n", encoding="utf-8")

    result = runner.invoke(main, ["--project", str(project_dir), "diff-reference"])
    assert result.exit_code != 0
    assert "not a git checkout" in result.output


def test_diff_reference_up_to_date_against_a_real_local_git_reference(tmp_path: Path):
    """End-to-end through the actual CLI (not just the reference_diff unit):
    recruit a reference by git-cloning a local 'upstream' repo into zone-r/
    (the same pattern every real recruited project uses), then confirm
    diff-reference reports it up to date and writes an evidence event."""
    import subprocess

    upstream = tmp_path / "upstream"
    upstream.mkdir()
    subprocess.run(["git", "init", "--quiet", "-b", "main"], cwd=upstream, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=upstream, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=upstream, check=True)
    (upstream / "schema.proto").write_text("message M {}\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=upstream, check=True)
    subprocess.run(["git", "commit", "--quiet", "-m", "initial"], cwd=upstream, check=True)

    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    runner = CliRunner()
    _run(runner, ["--project", str(project_dir), "init", "--name", "Demo", "--id", "demo", "--target-language", "python"])
    import shutil

    shutil.rmtree(project_dir / "zone-r")  # created by init (with a .gitkeep); git clone needs to create it fresh
    subprocess.run(["git", "clone", "--quiet", str(upstream), str(project_dir / "zone-r")], check=True, capture_output=True, text=True)

    result = runner.invoke(main, ["--project", str(project_dir), "--json", "diff-reference"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["up_to_date"] is True
    assert payload["reference_source"] == str(upstream)

    ledger_events = json.loads(_run(runner, ["--project", str(project_dir), "--json", "status"]).output)
    assert ledger_events["ledger_events"] >= 1


def test_build_registers_tools_on_the_agent_record(tmp_path: Path):
    """AgentRecord.tools existed as a dataclass field with no writer
    anywhere in the codebase before this -- 'cleanroom build --tool' is
    the first real path that actually populates it."""
    from cleanroom.cli import main

    runner = CliRunner()
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    _run(runner, ["--project", str(project_dir), "init", "--name", "Demo", "--id", "demo", "--target-language", "python"])

    build_result = _run(runner, ["--project", str(project_dir), "--json", "build", "--role", "Backend Team", "--tool", "pytest", "--tool", "ruff"])
    record = json.loads(build_result.output)
    assert record["tools"] == ["pytest", "ruff"]

    status_result = _run(runner, ["--project", str(project_dir), "--json", "status"])
    status_agents = json.loads(status_result.output)["agents"]
    assert any(a["tools"] == ["pytest", "ruff"] for a in status_agents)


def _setup_project_with_a_red_legal_finding(runner: CliRunner, project_dir: Path) -> None:
    """A real, reproducible RED finding: AGPL-3.0-only reference material
    plus a configured SaaS distribution model triggers
    saas_network_provision RED (AGPL-3.0 s.13) in every convened
    jurisdiction -- used to exercise the pre-build remediation panel."""
    import yaml

    project_dir.mkdir(exist_ok=True)
    _run(runner, ["--project", str(project_dir), "init", "--name", "Demo", "--id", "demo", "--target-language", "python"])
    (project_dir / "zone-r" / "lib").mkdir(parents=True)
    (project_dir / "zone-r" / "lib" / "package.json").write_text('{"name": "agpl-lib", "license": "AGPL-3.0-only"}', encoding="utf-8")

    config_path = project_dir / ".cleanroom.yml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["implementation"]["distribution_model"] = ["saas"]
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")

    runner.invoke(main, ["--project", str(project_dir), "--json", "licence", str(project_dir / "zone-r")])
    _run(runner, ["--project", str(project_dir), "intake", "--source", "lib", "--access-authority", "public"])
    _run(runner, ["--project", str(project_dir), "--json", "legal", "--access-authority", "public"])


def test_build_refuses_without_acknowledgment_when_a_blocking_concern_is_open(tmp_path: Path):
    """'cleanroom build' is the pre-build gate the whole methodology needs:
    a RED legal finding must be routed to REMEDIATION_TASKS.json (assigned
    to the implementation team) automatically, and must refuse to
    register a new implementation agent without an explicit human
    decision -- no silent 'the audit found a RED but nobody noticed
    before coding started'."""
    runner = CliRunner()
    project_dir = tmp_path / "proj"
    _setup_project_with_a_red_legal_finding(runner, project_dir)

    result = runner.invoke(main, ["--project", str(project_dir), "--json", "build", "--role", "Backend Team"])
    assert result.exit_code != 0
    assert "blocking remediation concern" in result.output

    tasks = json.loads((project_dir / "REMEDIATION_TASKS.json").read_text(encoding="utf-8"))
    blocking = [t for t in tasks if t["severity"] == "blocking" and t["status"] == "open"]
    assert blocking and all(t["assigned_to"] == "implementation-team" for t in blocking)
    assert any("saas_network_provision" in t["source_ref"] for t in blocking)

    assert not (project_dir / "evidence" / "agents.json").is_file()  # no agent was registered


def test_build_proceeds_with_explicit_acknowledge_flag(tmp_path: Path):
    """The non-interactive escape hatch for CI/scripted use, mirroring
    ai-suggest's --want-ai/--no-ai pattern."""
    runner = CliRunner()
    project_dir = tmp_path / "proj"
    _setup_project_with_a_red_legal_finding(runner, project_dir)

    result = _run(runner, ["--project", str(project_dir), "--json", "build", "--role", "Backend Team", "--acknowledge-open-concerns"])
    payload = json.loads(result.output)
    assert payload["open_remediation_concerns"]["blocking"] >= 1
    assert payload["agent_id"]


def test_build_interactive_panel_lists_concerns_and_honours_the_answer(tmp_path: Path):
    """The actual 'panel': without --acknowledge-open-concerns and outside
    --json mode, build must print every open concern and ask before
    proceeding -- answering yes registers the agent, answering no (or no
    input at all, e.g. a closed stdin in a forgotten script) refuses,
    cleanly, never with a raw traceback."""
    runner = CliRunner()
    project_dir = tmp_path / "proj"
    _setup_project_with_a_red_legal_finding(runner, project_dir)

    declined = runner.invoke(main, ["--project", str(project_dir), "build", "--role", "Backend Team"], input="n\n")
    assert declined.exit_code != 0
    assert "BLOCKING and" in declined.output
    assert "saas_network_provision" in declined.output

    no_input_at_all = runner.invoke(main, ["--project", str(project_dir), "build", "--role", "Backend Team"], input="")
    assert no_input_at_all.exit_code != 0
    assert "Traceback" not in no_input_at_all.output

    accepted = runner.invoke(main, ["--project", str(project_dir), "build", "--role", "Backend Team"], input="y\n")
    assert accepted.exit_code == 0
    agents = json.loads((project_dir / "evidence" / "agents.json").read_text(encoding="utf-8"))["agents"]
    assert len(agents) == 1


def test_build_surfaces_but_does_not_block_on_review_required_only_concerns(tmp_path: Path):
    """AMBER/UNKNOWN concerns alone (no RED, no material similarity) must
    never hard-block -- matching every other gate in this project, where
    AMBER is advisory, not blocking. Uses a plain MIT reference with no
    distribution model configured, which still yields several
    review_required (UNKNOWN) concerns (protected_expression, copying/
    substantiality with no similarity run, etc.) but zero blocking ones."""
    runner = CliRunner()
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    _run(runner, ["--project", str(project_dir), "init", "--name", "Demo", "--id", "demo", "--target-language", "python"])
    (project_dir / "zone-r" / "lib").mkdir(parents=True)
    (project_dir / "zone-r" / "lib" / "LICENSE").write_text("MIT License\n", encoding="utf-8")
    runner.invoke(main, ["--project", str(project_dir), "--json", "licence", str(project_dir / "zone-r")])
    _run(runner, ["--project", str(project_dir), "intake", "--source", "lib", "--access-authority", "public"])
    _run(runner, ["--project", str(project_dir), "--json", "legal", "--access-authority", "public"])

    result = _run(runner, ["--project", str(project_dir), "--json", "build", "--role", "Backend Team"])
    payload = json.loads(result.output)
    assert payload["open_remediation_concerns"]["blocking"] == 0
    assert payload["open_remediation_concerns"]["review_required"] > 0
    assert payload["agent_id"]  # registered without any acknowledgment needed


def _setup_project_ready_for_gate(runner: CliRunner, project_dir: Path) -> None:
    """A project with one handoff-eligible requirement node and a clean
    (non-blocked) sanitised Zone H document -- the automated signal
    `cleanroom gate` computes from this reads 'sufficient'."""
    project_dir.mkdir(exist_ok=True)
    _run(runner, ["--project", str(project_dir), "init", "--name", "Demo", "--id", "demo", "--target-language", "python"])
    _run(runner, [
        "--project", str(project_dir), "specify", "add-requirement",
        "--id", "CR-REQ-000001", "--kind", "requirement",
        "--statement", "sorts ascending", "--classification", "observable_requirement",
    ])
    (project_dir / "zone-h" / "spec.md").write_text(
        "GIVEN a list\nWHEN sorted ascending\nTHEN alphabetical order is returned\n", encoding="utf-8"
    )
    _run(runner, ["--project", str(project_dir), "sanitise", str(project_dir / "zone-h" / "spec.md")])


def test_handoff_refuses_without_a_gate_decision(tmp_path: Path):
    """The Clean-Room Gate is mechanically enforced, not just documented:
    'cleanroom handoff' must refuse to build a manifest for a
    specification version that has no recorded PASS decision -- no silent
    'sanitisation passed so handoff just proceeds'."""
    runner = CliRunner()
    project_dir = tmp_path / "proj"
    _setup_project_ready_for_gate(runner, project_dir)

    result = runner.invoke(main, ["--project", str(project_dir), "--json", "handoff", "--specification-version", "v1", "--all-c0"])
    assert result.exit_code == 3
    assert "Clean-Room Gate" in json.loads(result.output)["error"]
    assert not (project_dir / "zone-h" / "HANDOFF_MANIFEST.json").is_file()


def test_gate_fail_is_recorded_and_still_blocks_handoff(tmp_path: Path):
    """A FAIL decision is real evidence, not a no-op -- it's saved to
    GATE_DECISIONS.json (so the loop back to Team A has something to
    reference) and it does not unblock handoff for that version."""
    runner = CliRunner()
    project_dir = tmp_path / "proj"
    _setup_project_ready_for_gate(runner, project_dir)

    gate_result = runner.invoke(main, ["--project", str(project_dir), "--json", "gate",
        "--specification-version", "v1", "--decision", "fail",
        "--reviewer", "Jane Reviewer", "--notes", "Missing acceptance criteria for the descending-sort case.",
    ])
    assert gate_result.exit_code == 3
    decisions = json.loads((project_dir / "GATE_DECISIONS.json").read_text(encoding="utf-8"))
    assert decisions[0]["decision"] == "fail"
    assert decisions[0]["reviewer"] == "Jane Reviewer"

    handoff_result = runner.invoke(main, ["--project", str(project_dir), "--json", "handoff", "--specification-version", "v1", "--all-c0"])
    assert handoff_result.exit_code == 3


def test_gate_pass_unblocks_handoff_for_that_specification_version_only(tmp_path: Path):
    runner = CliRunner()
    project_dir = tmp_path / "proj"
    _setup_project_ready_for_gate(runner, project_dir)

    gate_result = _run(runner, ["--project", str(project_dir), "--json", "gate",
        "--specification-version", "v1", "--decision", "pass",
        "--reviewer", "Jane Reviewer", "--notes", "Coverage looks complete.",
    ])
    payload = json.loads(gate_result.output)
    assert payload["automated_signal"] == "sufficient"
    assert payload["overrode_automated_signal"] is False

    _run(runner, ["--project", str(project_dir), "handoff", "--specification-version", "v1", "--all-c0"])
    assert (project_dir / "zone-h" / "HANDOFF_MANIFEST.json").is_file()

    # v2 was never gated -- the PASS above does not carry over to a different version.
    other_version = runner.invoke(main, ["--project", str(project_dir), "--json", "handoff", "--specification-version", "v2", "--all-c0"])
    assert other_version.exit_code == 3


def test_gate_pass_despite_insufficient_signal_requires_explicit_acknowledgment(tmp_path: Path):
    """Recording PASS over an 'insufficient' automated signal is a real
    human override the tool must never let through silently -- refuses
    without acknowledgment (interactively or via the flag), and always
    records overrode_automated_signal=true when it does go through."""
    runner = CliRunner()
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    _run(runner, ["--project", str(project_dir), "init", "--name", "Demo", "--id", "demo", "--target-language", "python"])
    # No requirement nodes and no sanitisation reports at all -- automated_signal is 'insufficient'.

    no_input = runner.invoke(main, ["--project", str(project_dir), "gate",
        "--specification-version", "v1", "--decision", "pass",
        "--reviewer", "Jane Reviewer", "--notes", "Small feature, judged sufficient by inspection.",
    ], input="")
    assert no_input.exit_code != 0
    assert "Traceback" not in no_input.output
    assert not (project_dir / "GATE_DECISIONS.json").is_file()

    declined = runner.invoke(main, ["--project", str(project_dir), "gate",
        "--specification-version", "v1", "--decision", "pass",
        "--reviewer", "Jane Reviewer", "--notes", "x",
    ], input="n\n")
    assert declined.exit_code != 0
    assert "INSUFFICIENT" in declined.output

    accepted = _run(runner, ["--project", str(project_dir), "--json", "gate",
        "--specification-version", "v1", "--decision", "pass",
        "--reviewer", "Jane Reviewer", "--notes", "x", "--acknowledge-automated-signal",
    ])
    payload = json.loads(accepted.output)
    assert payload["automated_signal"] == "insufficient"
    assert payload["overrode_automated_signal"] is True


def test_agent_id_rejects_unregistered_id(tmp_path: Path):
    from cleanroom.cli import main

    runner = CliRunner()
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    _run(runner, ["--project", str(project_dir), "init", "--name", "Demo", "--id", "demo", "--target-language", "python"])

    result = runner.invoke(main, ["--agent-id", "never-registered", "--project", str(project_dir), "licence", str(project_dir / "zone-r")])
    assert result.exit_code != 0


def test_agent_id_denies_r_scoped_agent_sanitise_of_zone_h_document(tmp_path: Path):
    """`sanitise` reads a candidate handoff document out of Zone H -- the
    exact boundary-crossing point PathGuard exists to police -- but, like
    every other zone-touching command before this pass, never routed its
    file read through PathGuard per invocation. An R-only agent must now be
    genuinely denied `cleanroom sanitise` of a Zone H document, not just
    fail the self-test in isolation."""
    from cleanroom.cli import main
    from cleanroom.orchestration.agents import AgentRegistry

    runner = CliRunner()
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    _run(runner, ["--project", str(project_dir), "init", "--name", "Demo", "--id", "demo", "--target-language", "python"])
    (project_dir / "zone-h" / "spec.md").write_text("GIVEN a list\nWHEN sorted\nTHEN it is ordered\n", encoding="utf-8")

    registry = AgentRegistry(project_dir / "evidence")
    r_only = registry.register(role="Analyst", permitted_zones=["R"])
    h_scoped = registry.register(role="Handoff Reviewer", permitted_zones=["H"])

    denied = runner.invoke(main, ["--agent-id", r_only.agent_id, "--project", str(project_dir), "--json", "sanitise", str(project_dir / "zone-h" / "spec.md")])
    assert denied.exit_code == 4  # ContaminationFailure
    assert "PathGuard denied" in json.loads(denied.output)["error"]

    allowed = runner.invoke(main, ["--agent-id", h_scoped.agent_id, "--project", str(project_dir), "--json", "sanitise", str(project_dir / "zone-h" / "spec.md")])
    assert "PathGuard" not in allowed.output


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


def test_legal_surfaces_eupl_compatible_licence_overlap_from_config(tmp_path: Path):
    """`.cleanroom.yml`'s `implementation.output_licence` must reach the
    legal engine's `_distribution`/`_linking` heuristics: a project whose
    reference material concludes as EUPL-1.2 and whose OWN configured
    output licence is one of EUPL-1.2's Article 5 Compatible Licences
    must get that specific overlap named in the finding, not just a
    generic copyleft warning."""
    import yaml

    runner = CliRunner()
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    _run(runner, ["--project", str(project_dir), "init", "--name", "Demo", "--id", "demo", "--target-language", "python"])
    (project_dir / "zone-r" / "lib").mkdir(parents=True)
    (project_dir / "zone-r" / "lib" / "package.json").write_text('{"name": "eu-lib", "license": "EUPL-1.2"}', encoding="utf-8")

    config_path = project_dir / ".cleanroom.yml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config.setdefault("implementation", {})["distribution_model"] = ["binary"]
    config["implementation"]["output_licence"] = "MPL-2.0"
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")

    runner.invoke(main, ["--project", str(project_dir), "--json", "licence", str(project_dir / "zone-r")])
    _run(runner, ["--project", str(project_dir), "intake", "--source", "lib", "--access-authority", "public"])

    legal_result = _run(runner, ["--project", str(project_dir), "--json", "legal", "--access-authority", "public"])
    findings = {f["issue"]: f for f in json.loads(legal_result.output)["findings"] if f["jurisdiction"] == "gb"}
    assert findings["distribution"]["decision_state"] == "AMBER"
    assert "MPL-2.0" in findings["distribution"]["alternative_explanation"]
    assert "compatible licence" in findings["distribution"]["alternative_explanation"]


# --------------------------------------------------------------------------- fail-closed zone gating


def test_zone_scoped_command_fails_closed_without_agent_id_once_implementation_agent_registered(tmp_path: Path):
    """The footgun this feature closes: once a project has at least one
    registered Zone-I (implementation) agent (`cleanroom build` has run at
    least once), omitting the global `--agent-id` on a zone-scoped command
    must no longer silently run ungated -- it must refuse outright with a
    clear error, for every command `enforce_zone_access` gates: inspect,
    licence, similarity, sanitise, diff-reference."""
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    runner = CliRunner()
    _run(runner, ["--project", str(project_dir), "init", "--name", "Demo", "--id", "demo", "--target-language", "python"])
    (project_dir / "zone-r" / "lib").mkdir(parents=True)
    (project_dir / "zone-r" / "lib" / "LICENSE").write_text("MIT License\n", encoding="utf-8")
    (project_dir / "zone-h" / "spec.md").write_text("GIVEN a list\nWHEN sorted\nTHEN it is ordered\n", encoding="utf-8")

    _run(runner, ["--project", str(project_dir), "--json", "build", "--role", "Backend Team"])

    for args in (
        ["licence", str(project_dir / "zone-r")],
        ["inspect", str(project_dir / "zone-r")],
        ["sanitise", str(project_dir / "zone-h" / "spec.md")],
        ["diff-reference"],
        ["similarity", str(project_dir / "zone-r"), str(project_dir / "zone-i")],
    ):
        result = runner.invoke(main, ["--project", str(project_dir), "--json"] + args)
        assert result.exit_code != 0, f"expected failure without --agent-id for {args!r}, got {result.output!r}"
        assert "--agent-id is required" in result.output, result.output


def test_zone_scoped_command_still_ungated_without_any_registered_implementation_agent(tmp_path: Path):
    """Before any implementation agent has ever been registered for a
    project (fresh `init`, or a project that only ever used `recruit` for
    Reference-side agents), there is no Reference/Implementation separation
    yet to protect -- `--agent-id` must remain optional and omitting it
    must behave exactly as before this feature existed (no PathGuard
    denial, no fail-closed error)."""
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    runner = CliRunner()
    _run(runner, ["--project", str(project_dir), "init", "--name", "Demo", "--id", "demo", "--target-language", "python"])
    (project_dir / "zone-r" / "lib").mkdir(parents=True)
    (project_dir / "zone-r" / "lib" / "LICENSE").write_text("MIT License\n", encoding="utf-8")

    # No 'cleanroom build' has ever run for this project -- only 'recruit',
    # which registers Zone-R-only (not Zone-I) agents.
    _run(runner, ["--project", str(project_dir), "--json", "recruit", "--role", "Analyst"])

    result = runner.invoke(main, ["--project", str(project_dir), "--json", "licence", str(project_dir / "zone-r")])
    assert "--agent-id is required" not in result.output
    assert "PathGuard" not in result.output


def _init_gated_ready_for_handoff(runner: CliRunner, project_dir: Path, spec_version: str = "v1") -> None:
    """Shared setup: a project past `cleanroom gate --decision pass`, ready
    for `cleanroom handoff`."""
    project_dir.mkdir(exist_ok=True)
    _run(runner, ["--project", str(project_dir), "init", "--name", "Demo", "--id", "demo", "--target-language", "python"])
    _run(runner, [
        "--project", str(project_dir), "specify", "add-requirement",
        "--id", "CR-REQ-000001", "--kind", "requirement",
        "--statement", "sorts ascending", "--classification", "observable_requirement",
    ])
    (project_dir / "zone-h" / "spec.md").write_text(
        "GIVEN a list\nWHEN sorted ascending\nTHEN alphabetical order is returned\n", encoding="utf-8"
    )
    _run(runner, ["--project", str(project_dir), "sanitise", str(project_dir / "zone-h" / "spec.md")])
    _run(runner, [
        "--project", str(project_dir), "gate",
        "--specification-version", spec_version, "--decision", "pass",
        "--reviewer", "Test Reviewer", "--notes", "Sufficient for independent implementation.",
    ])


def test_handoff_format_facts_json_writes_a_validated_facts_document(tmp_path: Path):
    """The new structured, schema-validated Zone H handoff format: a
    conforming facts-only document passed via --facts-file must validate,
    be written into Zone H as CLEAN_ROOM_HANDOFF_FACTS.json, and have its
    hash recorded in HANDOFF_MANIFEST.json -- a real smoke test of
    'cleanroom handoff --format facts-json', not just the underlying
    Python functions."""
    import cleanroom.handoff.manifest as handoff_manifest

    runner = CliRunner()
    project_dir = tmp_path / "proj"
    _init_gated_ready_for_handoff(runner, project_dir)

    facts_file = tmp_path / "facts.json"
    facts_file.write_text(json.dumps({
        "schema_version": "1.0.0",
        "facts": [
            {"kind": "enum_value", "container": "HardwareModel", "name": "SEEED_WIO_TRACKER_L1_PRO_1W", "value": 144},
            {
                "kind": "field", "container": "EnvironmentMetrics", "name": "lightning_strike_count_1h",
                "number": 40, "type": "uint32", "optional": True,
            },
        ],
    }), encoding="utf-8")

    result = _run(runner, [
        "--project", str(project_dir), "--json", "handoff",
        "--specification-version", "v1", "--all-c0",
        "--format", "facts-json", "--facts-file", str(facts_file),
    ])
    payload = json.loads(result.output)
    assert payload["doc"] is None  # markdown handoff doc was NOT produced for this format
    assert payload["facts_doc"] is not None

    facts_doc_path = project_dir / "zone-h" / handoff_manifest.FACTS_DOC_FILENAME
    assert facts_doc_path.is_file()
    manifest = json.loads((project_dir / "zone-h" / "HANDOFF_MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest["facts_document"]["path"] == handoff_manifest.FACTS_DOC_FILENAME
    assert len(manifest["facts_document"]["sha256"]) == 64
    # The facts document is a distinct, separately-tracked artefact --
    # never double-counted as a regular handoff-eligible spec file.
    assert all(f["path"] != handoff_manifest.FACTS_DOC_FILENAME for f in manifest["files"])


def test_handoff_format_both_writes_markdown_and_facts_documents(tmp_path: Path):
    import cleanroom.handoff.manifest as handoff_manifest

    runner = CliRunner()
    project_dir = tmp_path / "proj"
    _init_gated_ready_for_handoff(runner, project_dir)

    facts_file = tmp_path / "facts.json"
    facts_file.write_text(json.dumps({
        "schema_version": "1.0.0",
        "facts": [{"kind": "constant", "container": "Limits", "name": "MAX_PACKET_SIZE", "value": 237}],
    }), encoding="utf-8")

    result = _run(runner, [
        "--project", str(project_dir), "--json", "handoff",
        "--specification-version", "v1", "--all-c0",
        "--format", "both", "--facts-file", str(facts_file),
    ])
    payload = json.loads(result.output)
    assert payload["doc"] is not None
    assert payload["facts_doc"] is not None
    assert (project_dir / "zone-h" / handoff_manifest.HANDOFF_DOC_FILENAME).is_file()
    assert (project_dir / "zone-h" / handoff_manifest.FACTS_DOC_FILENAME).is_file()


def test_handoff_format_facts_json_rejects_malformed_facts_file(tmp_path: Path):
    """A facts document that leaks prose/commentary through an unexpected
    key must be rejected with a clear error, and must NOT produce a
    handoff manifest at all -- a rejected facts-json handoff is a refusal,
    not a partial success."""
    runner = CliRunner()
    project_dir = tmp_path / "proj"
    _init_gated_ready_for_handoff(runner, project_dir)

    facts_file = tmp_path / "facts.json"
    facts_file.write_text(json.dumps({
        "schema_version": "1.0.0",
        "facts": [
            {
                "kind": "field", "container": "EnvironmentMetrics", "name": "lightning_strike_count_1h",
                "number": 40, "type": "uint32",
                "commentary": "The reference implementation computes this using a sliding window that also...",
            },
        ],
    }), encoding="utf-8")

    result = runner.invoke(main, [
        "--project", str(project_dir), "--json", "handoff",
        "--specification-version", "v1", "--all-c0",
        "--format", "facts-json", "--facts-file", str(facts_file),
    ])
    assert result.exit_code != 0
    assert "handoff-facts.schema.json" in result.output
    assert not (project_dir / "zone-h" / "HANDOFF_MANIFEST.json").is_file()


def test_handoff_format_facts_json_requires_facts_file(tmp_path: Path):
    runner = CliRunner()
    project_dir = tmp_path / "proj"
    _init_gated_ready_for_handoff(runner, project_dir)

    result = runner.invoke(main, [
        "--project", str(project_dir), "handoff",
        "--specification-version", "v1", "--all-c0", "--format", "facts-json",
    ])
    assert result.exit_code != 0
    assert "--facts-file" in result.output


def test_agent_registry_has_registered_implementation_agent(tmp_path: Path):
    """Unit-level check of the new state query itself: false with no
    agents or only Zone-R agents registered, true as soon as any Zone-I
    agent (regardless of its current status) has been registered."""
    from cleanroom.orchestration.agents import AgentRegistry

    evidence_dir = tmp_path / "evidence"
    registry = AgentRegistry(evidence_dir)
    assert registry.has_registered_implementation_agent() is False

    registry.register(role="Analyst", permitted_zones=["R"])
    assert registry.has_registered_implementation_agent() is False

    record = registry.register(role="Backend Team", permitted_zones=["H", "I"])
    assert registry.has_registered_implementation_agent() is True

    # Still true even if that agent's status later changes -- registration,
    # not liveness, is what the fail-closed gate cares about.
    registry.set_status(record.agent_id, "TERMINATED")
    assert registry.has_registered_implementation_agent() is True
