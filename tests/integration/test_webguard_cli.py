"""CLI-level coverage for `cleanroom exclude-source` / `cleanroom check-url`
(Part XCV, the web-lookup exclusion guard). See tests/unit/test_webguard.py
for the underlying engine's coverage; this file only proves the CLI
plumbing (project discovery, evidence writes, exit codes) works end to
end."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from click.testing import CliRunner

from cleanroom.cli import main


def _git(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)


def _setup_project_with_recruited_reference(runner: CliRunner, project_dir: Path, tmp_path: Path) -> None:
    result = runner.invoke(
        main, ["--project", str(project_dir), "init", "--name", "Demo", "--id", "demo", "--target-language", "python"]
    )
    assert result.exit_code == 0, result.output

    upstream = tmp_path / "upstream"
    upstream.mkdir()
    _git(["init", "--quiet", "-b", "main"], cwd=upstream)
    _git(["config", "user.email", "test@example.com"], cwd=upstream)
    _git(["config", "user.name", "Test"], cwd=upstream)
    (upstream / "mesh.proto").write_text('syntax = "proto3";\n', encoding="utf-8")
    _git(["add", "-A"], cwd=upstream)
    _git(["commit", "--quiet", "-m", "initial"], cwd=upstream)

    zone_r = project_dir / "zone-r"
    shutil.rmtree(zone_r)
    _git(["clone", "--quiet", str(upstream), str(zone_r)], cwd=project_dir)
    _git(["remote", "set-url", "origin", "https://github.com/meshtastic/protobufs.git"], cwd=zone_r)


def test_check_url_blocks_reference_and_allows_unrelated(tmp_path: Path):
    runner = CliRunner()
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    _setup_project_with_recruited_reference(runner, project_dir, tmp_path)

    blocked = runner.invoke(
        main,
        [
            "--project", str(project_dir), "--json", "check-url",
            "https://github.com/meshtastic/protobufs/blob/master/meshtastic/mesh.proto",
        ],
    )
    assert blocked.exit_code == 3  # POLICY_FAILURE -- see exit_codes.py
    data = json.loads(blocked.output)
    assert data["blocked"] is True

    allowed = runner.invoke(
        main, ["--project", str(project_dir), "--json", "check-url", "https://en.wikipedia.org/wiki/CRC-16"]
    )
    assert allowed.exit_code == 0
    assert json.loads(allowed.output)["blocked"] is False


def test_exclude_source_then_check_url_blocks_the_manual_pattern(tmp_path: Path):
    runner = CliRunner()
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    _setup_project_with_recruited_reference(runner, project_dir, tmp_path)

    mirror_url = "https://gitclone.example/vendor/meshtastic-proto-mirror/mesh.proto"
    pre = runner.invoke(main, ["--project", str(project_dir), "--json", "check-url", mirror_url])
    assert pre.exit_code == 0
    assert json.loads(pre.output)["blocked"] is False

    add = runner.invoke(
        main,
        [
            "--project", str(project_dir), "--json", "exclude-source",
            "gitclone.example/vendor/meshtastic-proto-mirror",
            "--note", "known unofficial mirror",
        ],
    )
    assert add.exit_code == 0, add.output

    post = runner.invoke(main, ["--project", str(project_dir), "--json", "check-url", mirror_url])
    assert post.exit_code == 3
    assert json.loads(post.output)["blocked"] is True


def test_check_url_events_land_in_the_evidence_ledger(tmp_path: Path):
    runner = CliRunner()
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    _setup_project_with_recruited_reference(runner, project_dir, tmp_path)

    runner.invoke(main, ["--project", str(project_dir), "--json", "check-url", "https://en.wikipedia.org/wiki/CRC-16"])
    ledger_path = project_dir / "evidence" / "ledger.jsonl"
    assert ledger_path.is_file()
    events = [json.loads(line) for line in ledger_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert any(e["action"] == "cleanroom webguard check-url" for e in events)
