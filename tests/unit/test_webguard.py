"""Unit tests for cleanroom.webguard -- the web-lookup exclusion guard an
orchestrating harness runs before letting an implementation-zone agent
actually fetch a URL (Part XCV).

Uses a real local git repo as the "upstream" (playing meshtastic/protobufs)
and a real `git clone` of it as zone_r, exactly like a recruited reference
in a real project (see projects/xcvario-meshtastic-recheck/zone-r/ and
tests/unit/test_reference_diff.py, which use the same pattern)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml

from cleanroom.config import default_config
from cleanroom.project import Project
from cleanroom.webguard import (
    ExclusionStore,
    check_url_against_exclusions,
    parse_owner_repo,
    registered_exclusions,
)


def _git(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)


def _make_upstream(path: Path) -> Path:
    path.mkdir(parents=True)
    _git(["init", "--quiet", "-b", "main"], cwd=path)
    _git(["config", "user.email", "test@example.com"], cwd=path)
    _git(["config", "user.name", "Test"], cwd=path)
    (path / "mesh.proto").write_text('syntax = "proto3";\n', encoding="utf-8")
    _git(["add", "-A"], cwd=path)
    _git(["commit", "--quiet", "-m", "initial"], cwd=path)
    return path


def _make_project(tmp_path: Path, *, origin_url: str) -> Project:
    """A real Project whose zone_r is a git clone of a local upstream, with
    'origin' rewritten to `origin_url` afterwards -- so registered_origin_url
    reports a realistic https://github.com/... URL (as it would for a real
    recruited project) even though the actual clone/fetch happened locally."""
    project_root = tmp_path / "project"
    project_root.mkdir()
    zone_r = project_root / "zone-r"
    upstream = _make_upstream(tmp_path / "upstream")
    _git(["clone", "--quiet", str(upstream), str(zone_r)], cwd=tmp_path)
    _git(["remote", "set-url", "origin", origin_url], cwd=zone_r)
    (project_root / "zone-h").mkdir()
    (project_root / "zone-i").mkdir()

    config = default_config("Demo", "demo-project")
    config_path = project_root / ".cleanroom.yml"
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(config, f)

    return Project.discover(project_root)


# --------------------------------------------------------------------------- parse_owner_repo

@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://github.com/meshtastic/protobufs", ("github.com", "meshtastic", "protobufs")),
        ("https://github.com/meshtastic/protobufs.git", ("github.com", "meshtastic", "protobufs")),
        ("https://www.github.com/meshtastic/protobufs.git", ("github.com", "meshtastic", "protobufs")),
        ("git@github.com:meshtastic/protobufs.git", ("github.com", "meshtastic", "protobufs")),
        ("ssh://git@github.com/meshtastic/protobufs.git", ("github.com", "meshtastic", "protobufs")),
    ],
)
def test_parse_owner_repo_normalises_common_forms(url: str, expected: tuple[str, str, str]):
    assert parse_owner_repo(url) == expected


def test_parse_owner_repo_returns_none_for_unparseable_url():
    assert parse_owner_repo("not a url at all") is None


# --------------------------------------------------------------------------- registered_exclusions

def test_registered_exclusions_empty_when_zone_r_not_a_git_checkout(tmp_path: Path):
    zone_r = tmp_path / "zone-r"
    zone_r.mkdir()
    assert registered_exclusions(zone_r) == []


def test_registered_exclusions_covers_github_and_raw_mirror(tmp_path: Path):
    project = _make_project(tmp_path, origin_url="https://github.com/meshtastic/protobufs.git")
    entries = registered_exclusions(project.zone_r)
    patterns = {e.pattern for e in entries}
    assert "meshtastic/protobufs" in patterns
    assert "raw.githubusercontent.com/meshtastic/protobufs" in patterns


# --------------------------------------------------------------------------- check_url_against_exclusions (the required scenario)

def test_blocks_github_blob_url_from_registered_reference(tmp_path: Path):
    project = _make_project(tmp_path, origin_url="https://github.com/meshtastic/protobufs.git")

    result = check_url_against_exclusions(
        "https://github.com/meshtastic/protobufs/blob/master/meshtastic/mesh.proto", project
    )
    assert result["blocked"] is True
    assert "meshtastic/protobufs" in result["reason"]


def test_blocks_raw_githubusercontent_mirror_of_registered_reference(tmp_path: Path):
    project = _make_project(tmp_path, origin_url="https://github.com/meshtastic/protobufs.git")

    result = check_url_against_exclusions(
        "https://raw.githubusercontent.com/meshtastic/protobufs/master/meshtastic/mesh.proto", project
    )
    assert result["blocked"] is True


def test_allows_unrelated_github_repo(tmp_path: Path):
    project = _make_project(tmp_path, origin_url="https://github.com/meshtastic/protobufs.git")

    result = check_url_against_exclusions(
        "https://github.com/someone-else/completely-unrelated-project", project
    )
    assert result["blocked"] is False
    assert result["reason"] is None


def test_allows_general_documentation(tmp_path: Path):
    project = _make_project(tmp_path, origin_url="https://github.com/meshtastic/protobufs.git")

    result = check_url_against_exclusions("https://en.wikipedia.org/wiki/CRC-16", project)
    assert result["blocked"] is False


def test_manual_exclude_source_blocks_a_mirror_the_heuristic_misses(tmp_path: Path):
    project = _make_project(tmp_path, origin_url="https://github.com/meshtastic/protobufs.git")

    # A rehost under a completely different owner/repo shape -- the
    # automatic heuristic can't identify this on its own.
    fork_url = "https://gitclone.example/vendor/meshtastic-proto-mirror/mesh.proto"
    assert check_url_against_exclusions(fork_url, project)["blocked"] is False

    store = ExclusionStore(project.root / "evidence")
    store.add("gitclone.example/vendor/meshtastic-proto-mirror", note="known unofficial mirror")

    result = check_url_against_exclusions(fork_url, project)
    assert result["blocked"] is True
    assert "manual" in result["matched_source"]


def test_check_writes_to_the_evidence_ledger(tmp_path: Path):
    project = _make_project(tmp_path, origin_url="https://github.com/meshtastic/protobufs.git")

    check_url_against_exclusions("https://en.wikipedia.org/wiki/CRC-16", project)
    check_url_against_exclusions(
        "https://github.com/meshtastic/protobufs/blob/master/meshtastic/mesh.proto", project
    )

    events = project.evidence.read_all()
    webguard_events = [e for e in events if e["action"] == "cleanroom webguard check-url"]
    assert len(webguard_events) == 2
    assert webguard_events[0]["result"] == "success"
    assert webguard_events[1]["result"] == "denied"
    assert project.evidence.verify_chain() == []


def test_exclusion_store_persists_across_instances(tmp_path: Path):
    evidence_dir = tmp_path / "evidence"
    store = ExclusionStore(evidence_dir)
    store.add("example.com/mirror/foo")

    reloaded = ExclusionStore(evidence_dir)
    assert [e.pattern for e in reloaded.all()] == ["example.com/mirror/foo"]
