"""Real end-to-end tests for orchestration/harness.py -- FakeBackend
stands in for a real LLM call (never presented as one), proving the
harness's OWN logic (prompt routing, JSON parsing, merging back through
legal_panels.merge_panel_answers, safe file writes) is correct. The real
AnthropicBackend integration itself is covered separately in
test_orchestration_backends.py (mocking only the network call) -- no
ANTHROPIC_API_KEY is available in CI or this environment to make a real
API call.
"""

import json
from pathlib import Path

from click.testing import CliRunner

from cleanroom.cli import main
from cleanroom.orchestration.backends import FakeBackend
from cleanroom.orchestration.harness import HarnessError, run_council_review, run_implementation
from cleanroom.project import Project


def _run(runner: CliRunner, args: list[str], **kwargs):
    result = runner.invoke(main, args, **kwargs)
    assert result.exit_code in (0, None), f"{args} failed ({result.exit_code}): {result.output}\n{result.exception}"
    return result


def _setup_project_through_legal(project_dir: Path) -> None:
    runner = CliRunner()
    _run(runner, ["--project", str(project_dir), "init", "--name", "Demo", "--id", "demo", "--target-language", "python"])
    (project_dir / "zone-r" / "lib").mkdir(parents=True)
    (project_dir / "zone-r" / "lib" / "LICENSE").write_text("MIT License\n", encoding="utf-8")
    runner.invoke(main, ["--project", str(project_dir), "--json", "licence", str(project_dir / "zone-r")])
    _run(runner, ["--project", str(project_dir), "intake", "--source", "lib", "--access-authority", "public"])
    _run(runner, ["--project", str(project_dir), "jurisdiction"])
    _run(runner, ["--project", str(project_dir), "--json", "legal", "--access-authority", "public"])


_JUDICIAL_ANSWER = json.dumps([
    {"issue": "lawful_access", "decision_state": "GREEN_WITH_CONDITIONS", "adjudication": "Council agrees: publicly accessible."},
])


def test_run_council_review_merges_a_real_backend_response_into_legal_findings(tmp_path: Path):
    """Proves the actual mechanism end-to-end: real prompts built from
    legal/panels.py, a (fake) backend answers them, the judicial review
    response is parsed as the required JSON contract and merged into
    evidence/legal-findings.json via the exact same merge_panel_answers
    the CLI's judge-adjudicate command uses."""
    project_dir = tmp_path / "proj"
    _setup_project_through_legal(project_dir)
    project = Project.discover(project_dir)

    matrix = json.loads((project_dir / "JURISDICTION_MATRIX.json").read_text(encoding="utf-8"))
    num_packs = len(matrix["legal_panels_convened"])
    # 3 real backend calls per convened pack: applicant brief, challenger brief, judicial review.
    backend = FakeBackend(["applicant brief text", "challenger brief text", _JUDICIAL_ANSWER] * num_packs)

    result = run_council_review(project, backend, panel_member_id="council-member-1", model_provider="anthropic")

    assert set(result["packs"].keys()) == set(matrix["legal_panels_convened"])
    for pack_result in result["packs"].values():
        assert pack_result["issues_updated"] == ["lawful_access"]

    findings = json.loads((project_dir / "evidence" / "legal-findings.json").read_text(encoding="utf-8"))
    gb_finding = next(f for f in findings if f["issue"] == "lawful_access" and f["jurisdiction"] == "gb")
    assert gb_finding["panel_adjudications"][0]["panel_member_id"] == "council-member-1"
    assert gb_finding["panel_adjudications"][0]["model_provider"] == "anthropic"
    assert gb_finding["adjudication"] == "Council agrees: publicly accessible."

    # The real prompts sent to the backend actually came from legal/panels.py,
    # not placeholder text -- confirm real jurisdiction/statute content appears.
    first_prompt = backend.calls[0][1]
    assert "Applicant Counsel" in first_prompt


def test_run_council_review_records_a_parse_failure_per_pack_without_crashing_the_whole_run(tmp_path: Path):
    """A model that ignores the output-format contract must produce an
    honest, recorded error for that pack -- never a fabricated finding,
    and never an exception that loses every other pack's real progress."""
    project_dir = tmp_path / "proj"
    _setup_project_through_legal(project_dir)
    project = Project.discover(project_dir)
    matrix = json.loads((project_dir / "JURISDICTION_MATRIX.json").read_text(encoding="utf-8"))
    num_packs = len(matrix["legal_panels_convened"])

    backend = FakeBackend(["applicant text", "challenger text", "not valid json at all"] * num_packs)
    result = run_council_review(project, backend, panel_member_id="council-member-1")

    for pack_result in result["packs"].values():
        assert "error" in pack_result
        assert "not valid json" in pack_result["raw_judicial_response"]


def test_run_council_review_strips_a_markdown_code_fence_before_parsing(tmp_path: Path):
    """A model that wraps its JSON in ```json ... ``` (the single most
    common real deviation from an explicit 'no other text' instruction)
    must still parse correctly."""
    project_dir = tmp_path / "proj"
    _setup_project_through_legal(project_dir)
    project = Project.discover(project_dir)
    matrix = json.loads((project_dir / "JURISDICTION_MATRIX.json").read_text(encoding="utf-8"))
    num_packs = len(matrix["legal_panels_convened"])

    fenced = f"```json\n{_JUDICIAL_ANSWER}\n```"
    backend = FakeBackend(["applicant text", "challenger text", fenced] * num_packs)
    result = run_council_review(project, backend, panel_member_id="council-member-1")

    for pack_result in result["packs"].values():
        assert pack_result.get("issues_updated") == ["lawful_access"]


def _setup_project_with_a_requirement(project_dir: Path) -> str:
    runner = CliRunner()
    _run(runner, ["--project", str(project_dir), "init", "--name", "Demo", "--id", "demo", "--target-language", "python"])
    (project_dir / "zone-h" / "spec.md").write_text("GIVEN a list\nWHEN sorted ascending\nTHEN alphabetical order is returned\n", encoding="utf-8")
    _run(runner, [
        "--project", str(project_dir), "specify", "add-requirement",
        "--id", "CR-REQ-000001", "--kind", "requirement",
        "--statement", "sorts a list of strings ascending", "--classification", "observable_requirement",
    ])
    build_result = _run(runner, ["--project", str(project_dir), "--json", "build", "--role", "Backend Team"])
    return json.loads(build_result.output)["agent_id"]


_IMPLEMENTATION_ANSWER = json.dumps([{"path": "sort.py", "content": "def sort_ascending(items):\n    return sorted(items)\n"}])


def test_run_implementation_writes_real_files_into_zone_i(tmp_path: Path):
    project_dir = tmp_path / "proj"
    agent_id = _setup_project_with_a_requirement(project_dir)
    project = Project.discover(project_dir)

    backend = FakeBackend([_IMPLEMENTATION_ANSWER])
    result = run_implementation(project, backend, agent_id=agent_id)

    assert result["files_written"] == ["sort.py"]
    assert result["requirements_addressed"] == ["CR-REQ-000001"]
    written = (project.zone_i / "sort.py").read_text(encoding="utf-8")
    assert "def sort_ascending" in written

    # The prompt sent to the backend must include the real sanitised spec
    # text and requirement statement -- never raw Zone R content (there is
    # none in this fixture at all, by construction: source-blind by not
    # being given anything to read, not merely blocked from re-reading it).
    prompt = backend.calls[0][1]
    assert "sorts a list of strings ascending" in prompt
    assert "alphabetical order is returned" in prompt


def test_run_implementation_refuses_a_path_traversal_attempt(tmp_path: Path):
    project_dir = tmp_path / "proj"
    agent_id = _setup_project_with_a_requirement(project_dir)
    project = Project.discover(project_dir)

    malicious = json.dumps([{"path": "../../etc/evil.py", "content": "pwned = True\n"}])
    backend = FakeBackend([malicious])

    try:
        run_implementation(project, backend, agent_id=agent_id)
        assert False, "expected HarnessError"
    except HarnessError as e:
        assert "outside Zone I" in str(e)
    assert not (project.zone_i.parent.parent / "etc" / "evil.py").exists()


def test_run_implementation_rejects_a_malformed_file_entry(tmp_path: Path):
    project_dir = tmp_path / "proj"
    agent_id = _setup_project_with_a_requirement(project_dir)
    project = Project.discover(project_dir)

    backend = FakeBackend([json.dumps([{"path": "sort.py"}])])  # missing "content"
    try:
        run_implementation(project, backend, agent_id=agent_id)
        assert False, "expected HarnessError"
    except HarnessError as e:
        assert "Malformed file entry" in str(e)


def test_run_implementation_requires_at_least_one_handoff_eligible_requirement(tmp_path: Path):
    project_dir = tmp_path / "proj"
    runner = CliRunner()
    _run(runner, ["--project", str(project_dir), "init", "--name", "Demo", "--id", "demo", "--target-language", "python"])
    build_result = _run(runner, ["--project", str(project_dir), "--json", "build", "--role", "Backend Team"])
    agent_id = json.loads(build_result.output)["agent_id"]
    project = Project.discover(project_dir)

    backend = FakeBackend([])
    try:
        run_implementation(project, backend, agent_id=agent_id)
        assert False, "expected HarnessError"
    except HarnessError as e:
        assert "No handoff-eligible requirements" in str(e)
    assert backend.calls == []  # never called the backend at all with nothing to implement


def test_cli_council_requires_agent_id(tmp_path: Path):
    project_dir = tmp_path / "proj"
    runner = CliRunner()
    _run(runner, ["--project", str(project_dir), "init", "--name", "Demo", "--id", "demo", "--target-language", "python"])
    result = runner.invoke(main, ["--project", str(project_dir), "council"])
    assert result.exit_code != 0
    assert "--agent-id is required" in result.output


def test_cli_implement_requires_agent_id(tmp_path: Path):
    project_dir = tmp_path / "proj"
    runner = CliRunner()
    _run(runner, ["--project", str(project_dir), "init", "--name", "Demo", "--id", "demo", "--target-language", "python"])
    result = runner.invoke(main, ["--project", str(project_dir), "implement"])
    assert result.exit_code != 0
    assert "--agent-id is required" in result.output


def test_cli_implement_rejects_an_r_scoped_agent(tmp_path: Path):
    """A Council member (recruit, Zone R only) must never be usable as
    the implement command's agent -- the whole point of the clean line
    is that the same identity can't be on both sides."""
    project_dir = tmp_path / "proj"
    runner = CliRunner()
    _run(runner, ["--project", str(project_dir), "init", "--name", "Demo", "--id", "demo", "--target-language", "python"])
    recruit_result = _run(runner, ["--project", str(project_dir), "--json", "recruit", "--role", "Analyst"])
    agent_id = json.loads(recruit_result.output)["agent_id"]

    result = runner.invoke(main, ["--agent-id", agent_id, "--project", str(project_dir), "implement"])
    assert result.exit_code != 0
    assert "not Zone-I-scoped" in result.output


def test_cli_implement_with_no_credentials_fails_cleanly_not_with_a_traceback(tmp_path: Path, monkeypatch):
    """Real end-to-end reproduction of the no-ANTHROPIC_API_KEY path
    through the actual CLI command, not just the backend unit test."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    project_dir = tmp_path / "proj"
    runner = CliRunner()
    _run(runner, ["--project", str(project_dir), "init", "--name", "Demo", "--id", "demo", "--target-language", "python"])
    _run(runner, [
        "--project", str(project_dir), "specify", "add-requirement",
        "--id", "CR-REQ-000001", "--kind", "requirement", "--statement", "sorts ascending", "--classification", "observable_requirement",
    ])
    build_result = _run(runner, ["--project", str(project_dir), "--json", "build", "--role", "Backend Team"])
    agent_id = json.loads(build_result.output)["agent_id"]

    result = runner.invoke(main, ["--agent-id", agent_id, "--project", str(project_dir), "implement"])
    assert result.exit_code != 0
    assert "Traceback" not in result.output
    assert "ANTHROPIC_API_KEY" in result.output


def _mock_anthropic_text_response(text: str):
    from unittest.mock import MagicMock

    block = MagicMock()
    block.type = "text"
    block.text = text
    message = MagicMock()
    message.content = [block]
    client = MagicMock()
    client.messages.create.return_value = message
    return client


def test_cli_implement_records_the_real_default_model_when_model_id_is_omitted(tmp_path: Path):
    """Regression: implement's evidence entry used to record whatever
    (if anything) `cleanroom build` happened to be given for
    --model-provider/--model-id -- None whenever the user didn't ALSO
    pass matching flags there, even though a real, specific model
    (DEFAULT_IMPLEMENTATION_MODEL) had just actually written the code.
    The evidence ledger must reflect the model that really did the work,
    not a field nobody happened to fill in."""
    from unittest.mock import patch

    from cleanroom.orchestration.backends import DEFAULT_IMPLEMENTATION_MODEL

    project_dir = tmp_path / "proj"
    runner = CliRunner()
    _run(runner, ["--project", str(project_dir), "init", "--name", "Demo", "--id", "demo", "--target-language", "python"])
    _run(runner, [
        "--project", str(project_dir), "specify", "add-requirement",
        "--id", "CR-REQ-000001", "--kind", "requirement", "--statement", "sorts ascending", "--classification", "observable_requirement",
    ])
    # Deliberately no --model-provider/--model-id here -- the exact
    # under-specified case that used to lose provenance.
    build_result = _run(runner, ["--project", str(project_dir), "--json", "build", "--role", "Backend Team"])
    agent_id = json.loads(build_result.output)["agent_id"]
    assert json.loads(build_result.output)["model_provider"] is None  # confirms the setup: build really was given nothing

    mock_client = _mock_anthropic_text_response(json.dumps([{"path": "sort.py", "content": "def f(x): return sorted(x)\n"}]))
    with patch("anthropic.Anthropic", return_value=mock_client):
        result = _run(runner, ["--project", str(project_dir), "--json", "--agent-id", agent_id, "implement"])

    payload = json.loads(result.output)
    assert payload["model_provider"] == "anthropic"
    assert payload["model_id"] == DEFAULT_IMPLEMENTATION_MODEL
    mock_client.messages.create.assert_called_once()
    assert mock_client.messages.create.call_args.kwargs["model"] == DEFAULT_IMPLEMENTATION_MODEL

    last_event = json.loads((project_dir / "evidence" / "ledger.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert last_event["actor"]["model_provider"] == "anthropic"
    assert last_event["actor"]["model_id"] == DEFAULT_IMPLEMENTATION_MODEL


def test_cli_council_records_the_real_default_model_when_model_id_is_omitted(tmp_path: Path):
    """Same regression, for council -- the Council's default is
    DEFAULT_COUNCIL_MODEL specifically (a genuinely different, real
    default from the implementation team's), and that specific default
    must be what's actually recorded, not the None a caller who trusted
    the default would otherwise leave behind."""
    from unittest.mock import patch

    from cleanroom.orchestration.backends import DEFAULT_COUNCIL_MODEL

    project_dir = tmp_path / "proj"
    runner = CliRunner()
    _run(runner, ["--project", str(project_dir), "init", "--name", "Demo", "--id", "demo", "--target-language", "python"])
    (project_dir / "zone-r" / "lib").mkdir(parents=True)
    (project_dir / "zone-r" / "lib" / "LICENSE").write_text("MIT License\n", encoding="utf-8")
    runner.invoke(main, ["--project", str(project_dir), "--json", "licence", str(project_dir / "zone-r")])
    _run(runner, ["--project", str(project_dir), "intake", "--source", "lib", "--access-authority", "public"])
    _run(runner, ["--project", str(project_dir), "jurisdiction"])
    _run(runner, ["--project", str(project_dir), "--json", "legal", "--access-authority", "public"])
    recruit_result = _run(runner, ["--project", str(project_dir), "--json", "recruit", "--role", "Analyst"])
    agent_id = json.loads(recruit_result.output)["agent_id"]

    matrix = json.loads((project_dir / "JURISDICTION_MATRIX.json").read_text(encoding="utf-8"))
    num_calls = len(matrix["legal_panels_convened"]) * 3
    mock_client = _mock_anthropic_text_response(json.dumps([{"issue": "lawful_access", "decision_state": "GREEN_WITH_CONDITIONS", "adjudication": "fine"}]))

    with patch("anthropic.Anthropic", return_value=mock_client):
        result = _run(runner, ["--project", str(project_dir), "--json", "--agent-id", agent_id, "council"])

    payload = json.loads(result.output)
    assert payload["model_id"] == DEFAULT_COUNCIL_MODEL
    assert mock_client.messages.create.call_count == num_calls
    assert mock_client.messages.create.call_args.kwargs["model"] == DEFAULT_COUNCIL_MODEL

    findings = json.loads((project_dir / "evidence" / "legal-findings.json").read_text(encoding="utf-8"))
    gb_finding = next(f for f in findings if f["issue"] == "lawful_access" and f["jurisdiction"] == "gb")
    assert gb_finding["panel_adjudications"][0]["model_id"] == DEFAULT_COUNCIL_MODEL
