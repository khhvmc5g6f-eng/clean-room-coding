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

    def fake_lookup(name, version):
        if name == "click":
            return (version or "8.1.7", ["colorama"], "BSD-3-Clause")
        return ("0.4.6", [], "BSD-3-Clause")

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
    Zone-H+I-only agent (cleanroom build's only registration path) must
    now be genuinely denied `cleanroom licence zone-r`, not just fail the
    self-test in isolation."""
    from cleanroom.cli import main

    runner = CliRunner()
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    _run(runner, ["--project", str(project_dir), "init", "--name", "Demo", "--id", "demo", "--target-language", "python"])
    (project_dir / "zone-r" / "lib").mkdir(parents=True)
    (project_dir / "zone-r" / "lib" / "LICENSE").write_text("MIT License\n", encoding="utf-8")

    build_result = _run(runner, ["--project", str(project_dir), "--json", "build", "--role", "Backend Team"])
    agent_id = json.loads(build_result.output)["agent_id"]

    # Without --agent-id, behaviour is exactly as before -- this call
    # succeeds (licence discovery runs; whether findings pass policy is a
    # separate matter this test doesn't care about).
    unrestricted = runner.invoke(main, ["--project", str(project_dir), "licence", str(project_dir / "zone-r")])
    assert "PathGuard" not in unrestricted.output

    denied = runner.invoke(main, ["--agent-id", agent_id, "--project", str(project_dir), "--json", "licence", str(project_dir / "zone-r")])
    assert denied.exit_code == 4  # ContaminationFailure
    assert "PathGuard denied" in json.loads(denied.output)["error"]


def test_agent_id_allows_r_scoped_agent_zone_r_access(tmp_path: Path):
    """The allow path, not just the deny path: an agent actually
    registered WITH Zone R access must pass straight through with no
    PathGuard denial at all. (No CLI command registers an R-scoped agent
    today -- 'cleanroom build' only ever registers H+I -- so this uses
    AgentRegistry directly, exactly as an orchestration harness built on
    this library would.)"""
    from cleanroom.cli import main
    from cleanroom.orchestration.agents import AgentRegistry

    runner = CliRunner()
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    _run(runner, ["--project", str(project_dir), "init", "--name", "Demo", "--id", "demo", "--target-language", "python"])
    (project_dir / "zone-r" / "lib").mkdir(parents=True)
    (project_dir / "zone-r" / "lib" / "LICENSE").write_text("MIT License\n", encoding="utf-8")

    registry = AgentRegistry(project_dir / "evidence")
    record = registry.register(role="Analyst", permitted_zones=["R"])

    result = runner.invoke(main, ["--agent-id", record.agent_id, "--project", str(project_dir), "--json", "licence", str(project_dir / "zone-r")])
    assert "PathGuard" not in result.output


def test_agent_id_rejects_unregistered_id(tmp_path: Path):
    from cleanroom.cli import main

    runner = CliRunner()
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    _run(runner, ["--project", str(project_dir), "init", "--name", "Demo", "--id", "demo", "--target-language", "python"])

    result = runner.invoke(main, ["--agent-id", "never-registered", "--project", str(project_dir), "licence", str(project_dir / "zone-r")])
    assert result.exit_code != 0


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
