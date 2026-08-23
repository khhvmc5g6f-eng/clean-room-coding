"""Unit tests for cleanroom.reference_diff -- the `cleanroom diff-reference`
engine. Uses local git repos only (no network): an "upstream" repo plays the
role of the real reference source, and zone_r is a real `git clone` of it,
exactly like a recruited reference in a real project
(projects/xcvario-meshtastic-recheck/zone-r/ is a live example of this
pattern: a straight `git clone` with its origin remote intact)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from cleanroom.reference_diff import ReferenceDiffError, diff_reference


def _git(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)


def _init_upstream(path: Path) -> Path:
    path.mkdir(parents=True)
    _git(["init", "--quiet", "-b", "main"], cwd=path)
    _git(["config", "user.email", "test@example.com"], cwd=path)
    _git(["config", "user.name", "Test"], cwd=path)
    (path / "schema.proto").write_text('syntax = "proto3";\nmessage M { uint32 id = 1; }\n', encoding="utf-8")
    (path / "keep.proto").write_text("message Keep {}\n", encoding="utf-8")
    _git(["add", "-A"], cwd=path)
    _git(["commit", "--quiet", "-m", "initial"], cwd=path)
    return path


def _recruit(upstream: Path, zone_r: Path) -> None:
    subprocess.run(["git", "clone", "--quiet", str(upstream), str(zone_r)], check=True, capture_output=True, text=True)


def test_rejects_a_zone_r_that_is_not_a_git_checkout(tmp_path: Path):
    zone_r = tmp_path / "zone-r"
    zone_r.mkdir()
    (zone_r / "schema.proto").write_text("message M {}\n", encoding="utf-8")

    with pytest.raises(ReferenceDiffError, match="not a git checkout"):
        diff_reference(zone_r)


def test_up_to_date_when_upstream_has_not_changed(tmp_path: Path):
    upstream = _init_upstream(tmp_path / "upstream")
    zone_r = tmp_path / "zone-r"
    _recruit(upstream, zone_r)

    result = diff_reference(zone_r)
    assert result["up_to_date"] is True
    assert result["baseline_commit"] == result["latest_commit"]
    assert result["new_files"] == result["modified_files"] == result["deleted_files"] == []
    assert result["commit_log"] == []


def test_detects_new_modified_and_deleted_files(tmp_path: Path):
    upstream = _init_upstream(tmp_path / "upstream")
    zone_r = tmp_path / "zone-r"
    _recruit(upstream, zone_r)

    # Upstream moves on after the reference was recruited.
    (upstream / "schema.proto").write_text('syntax = "proto3";\nmessage M { uint32 id = 1; string name = 2; }\n', encoding="utf-8")
    (upstream / "new_feature.proto").write_text("message NewFeature {}\n", encoding="utf-8")
    (upstream / "keep.proto").unlink()
    _git(["add", "-A"], cwd=upstream)
    _git(["commit", "--quiet", "-m", "add field, add new schema, remove keep"], cwd=upstream)

    result = diff_reference(zone_r)
    assert result["up_to_date"] is False
    assert result["baseline_commit"] != result["latest_commit"]
    assert result["new_files"] == ["new_feature.proto"]
    assert result["modified_files"] == ["schema.proto"]
    assert result["deleted_files"] == ["keep.proto"]
    assert result["commit_log"] is not None
    assert len(result["commit_log"]) == 1

    # zone_r itself must be completely untouched by running the diff.
    assert (zone_r / "keep.proto").is_file()
    assert "name = 2" not in (zone_r / "schema.proto").read_text(encoding="utf-8")


def test_possibly_stale_refs_matches_by_filename_stem(tmp_path: Path):
    upstream = _init_upstream(tmp_path / "upstream")
    zone_r = tmp_path / "zone-r"
    _recruit(upstream, zone_r)

    (upstream / "schema.proto").write_text("message M { uint32 id = 1; uint32 extra = 2; }\n", encoding="utf-8")
    _git(["add", "-A"], cwd=upstream)
    _git(["commit", "--quiet", "-m", "change schema"], cwd=upstream)

    zone_i = tmp_path / "zone-i"
    zone_i.mkdir()
    (zone_i / "schema.dart").write_text("class M { int id; }\n", encoding="utf-8")
    (zone_i / "unrelated.dart").write_text("class Unrelated {}\n", encoding="utf-8")
    zone_h = tmp_path / "zone-h"
    zone_h.mkdir()

    result = diff_reference(zone_r, zone_h=zone_h, zone_i=zone_i)
    assert result["possibly_stale_refs"]["zone_i"] == ["schema.dart"]
    assert result["possibly_stale_refs"]["zone_h"] == []


def test_possibly_stale_refs_skipped_when_not_requested(tmp_path: Path):
    upstream = _init_upstream(tmp_path / "upstream")
    zone_r = tmp_path / "zone-r"
    _recruit(upstream, zone_r)

    result = diff_reference(zone_r)  # zone_h/zone_i omitted
    assert result["possibly_stale_refs"] == {"zone_h": [], "zone_i": []}
