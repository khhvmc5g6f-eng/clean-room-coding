"""CLI-level coverage for `cleanroom debug` (Part XCVII, the build-side
debugging suite). See tests/unit/test_debugging.py for the triage
engine's own coverage; this file proves the CLI plumbing -- reading
behavioral_tests.json/requirements.json, writing DEBUG_FINDINGS.json,
and syncing REMEDIATION_TASKS.json + a blocked requirement-graph node
for spec_gap findings -- works end to end."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from cleanroom.cli import main

REQUIREMENTS = {
    "nodes": [
        {
            "id": "CR-REQ-000001", "kind": "requirement",
            "statement": "The export function returns exactly the rows matching the filter, in ascending id order.",
            "classification": "observable_requirement", "status": "handed_off",
        },
        {
            "id": "CR-REQ-000002", "kind": "requirement",
            "statement": "The retry behaviour is implementation-defined and may vary by backend.",
            "classification": "observable_requirement", "status": "handed_off",
        },
    ]
}

BEHAVIORAL_TESTS = {
    "tests": [
        {
            "id": "CR-BEH-000001", "given": "a filtered dataset", "when": "export runs",
            "then": "rows come back in ascending id order", "requirement_ids": ["CR-REQ-000001"],
            "result": "fail",
        },
        {
            "id": "CR-BEH-000002", "given": "a transient failure", "when": "the call is retried",
            "then": "the retry eventually succeeds", "requirement_ids": ["CR-REQ-000002"],
            "result": "fail",
        },
    ]
}


def test_debug_triages_and_syncs_remediation(tmp_path: Path):
    runner = CliRunner()
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    init_result = runner.invoke(
        main, ["--project", str(project_dir), "init", "--name", "Demo", "--id", "demo", "--target-language", "python"]
    )
    assert init_result.exit_code == 0, init_result.output

    (project_dir / "requirements.json").write_text(json.dumps(REQUIREMENTS), encoding="utf-8")
    (project_dir / "behavioral_tests.json").write_text(json.dumps(BEHAVIORAL_TESTS), encoding="utf-8")

    result = runner.invoke(main, ["--project", str(project_dir), "--json", "debug"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)

    assert payload["counts"]["implementation_bug"] == 1
    assert payload["counts"]["spec_gap"] == 1
    assert "CR-BEH-000001" in payload["worksheets"]
    assert "CR-BEH-000002" not in payload["worksheets"]
    assert payload["remediation_tasks_open"] == 1

    findings = json.loads((project_dir / "DEBUG_FINDINGS.json").read_text(encoding="utf-8"))
    assert {f["test_id"]: f["classification"] for f in findings} == {
        "CR-BEH-000001": "implementation_bug",
        "CR-BEH-000002": "spec_gap",
    }

    tasks = json.loads((project_dir / "REMEDIATION_TASKS.json").read_text(encoding="utf-8"))
    debug_tasks = [t for t in tasks if t["source_type"] == "debug_finding"]
    assert len(debug_tasks) == 1
    assert debug_tasks[0]["severity"] == "review_required"
    assert debug_tasks[0]["status"] == "open"
    assert debug_tasks[0]["source_ref"] == "CR-BEH-000002"

    graph = json.loads((project_dir / "requirements.json").read_text(encoding="utf-8"))
    remediation_nodes = [n for n in graph["nodes"] if n["kind"] == "remediation"]
    assert len(remediation_nodes) == 1
    assert remediation_nodes[0]["status"] == "blocked"
    assert remediation_nodes[0]["id"] == debug_tasks[0]["id"]


def test_debug_is_idempotent_and_clears_on_rescan(tmp_path: Path):
    runner = CliRunner()
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    init_result = runner.invoke(
        main, ["--project", str(project_dir), "init", "--name", "Demo", "--id", "demo", "--target-language", "python"]
    )
    assert init_result.exit_code == 0, init_result.output

    (project_dir / "requirements.json").write_text(json.dumps(REQUIREMENTS), encoding="utf-8")
    (project_dir / "behavioral_tests.json").write_text(json.dumps(BEHAVIORAL_TESTS), encoding="utf-8")

    first = runner.invoke(main, ["--project", str(project_dir), "--json", "debug"])
    assert first.exit_code == 0, first.output

    # Team fixed the ambiguous requirement's wording and the retry test now passes.
    tests = json.loads((project_dir / "behavioral_tests.json").read_text(encoding="utf-8"))
    for t in tests["tests"]:
        if t["id"] == "CR-BEH-000002":
            t["result"] = "pass"
    (project_dir / "behavioral_tests.json").write_text(json.dumps(tests), encoding="utf-8")

    second = runner.invoke(main, ["--project", str(project_dir), "--json", "debug"])
    assert second.exit_code == 0, second.output
    payload = json.loads(second.output)
    assert payload["counts"]["spec_gap"] == 0
    assert payload["remediation_tasks_open"] == 0

    tasks = json.loads((project_dir / "REMEDIATION_TASKS.json").read_text(encoding="utf-8"))
    debug_tasks = [t for t in tasks if t["source_type"] == "debug_finding"]
    assert len(debug_tasks) == 1
    assert debug_tasks[0]["status"] == "resolved_by_rescan"
