"""Re-fetch a recruited Zone R reference and diff it against what was
actually recruited (`cleanroom diff-reference`).

Before this existed, checking whether an already-recruited Zone R reference
had newer upstream commits -- and what changed -- required a human/agent to
manually re-clone the source and hand-diff it against the checkout under
`zone-r/`, entirely outside any evidence trail. This module makes that
deterministic and auditable.

Design notes (read before changing the approach):

- The "registered reference source" is read from the existing recruited
  checkout's own git `origin` remote, not from a new manifest field. Every
  real project observed so far (see `projects/xcvario-meshtastic-recheck/`)
  recruits Zone R material by `git clone`-ing it straight into `zone-r/`, so
  the checkout already carries its own provenance (`git remote get-url
  origin`, `git rev-parse HEAD`) -- duplicating that into a second,
  hand-maintained manifest would just be one more thing to fall out of sync
  with reality. A reference recruited some other way (an unpacked archive
  with no `.git`) has no such record, and per the "never fabricate a
  conclusion" rule (AGENTS.md item c) this deliberately refuses to guess a
  source for it rather than inventing one.
- The re-fetch clones into a throwaway temp directory and never touches
  `zone-r/` itself -- no `git fetch`/`git pull` is run against the recruited
  checkout in place. That keeps this read-only from the recruited project's
  point of view (a repeated `diff-reference` run is idempotent and leaves no
  trace on zone_r) and sidesteps any question of whether updating zone_r's
  `.git` objects in place would itself need re-running intake/licence/
  similarity against the new content before anyone treats it as recruited.
- The diff is computed by content hash (`cleanroom.util.hash_tree`, which
  already excludes `.git`), not `git diff`, so it works even if the fresh
  clone's history doesn't cleanly extend the recruited commit (a force-push
  upstream, or the recruited checkout being a shallow clone). A commit-log
  summary is included as a best-effort addition when the baseline commit is
  still reachable from the fresh clone's history; its absence doesn't block
  the file-level diff.
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from typing import Any

from cleanroom.util import hash_tree


class ReferenceDiffError(Exception):
    """Raised for a diff-reference precondition that isn't met (no git
    checkout, no origin remote, clone/network failure). Never raised to
    coerce a partial result into a tidy answer -- see the module docstring
    and AGENTS.md item c."""


def _run_git(args: list[str], *, cwd: Path | None = None, timeout: int) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            ["git", *args], cwd=cwd, capture_output=True, text=True, timeout=timeout, check=False,
        )
    except FileNotFoundError as e:
        raise ReferenceDiffError("git is not installed or not on PATH (see 'cleanroom doctor').") from e
    except subprocess.TimeoutExpired as e:
        raise ReferenceDiffError(f"git {' '.join(args)} timed out after {timeout}s.") from e


def registered_origin_url(zone_r: Path, *, timeout: int = 30) -> str | None:
    """The git remote 'origin' URL of the recruited Zone R checkout, or None
    if zone_r isn't a git checkout (no `.git`) or has no origin remote --
    both mean there is no known upstream to re-fetch."""
    if not (zone_r / ".git").exists():
        return None
    result = _run_git(["remote", "get-url", "origin"], cwd=zone_r, timeout=timeout)
    if result.returncode != 0:
        return None
    url = result.stdout.strip()
    return url or None


def current_commit(repo_root: Path, *, timeout: int = 30) -> str | None:
    if not (repo_root / ".git").exists():
        return None
    result = _run_git(["rev-parse", "HEAD"], cwd=repo_root, timeout=timeout)
    if result.returncode != 0:
        return None
    sha = result.stdout.strip()
    return sha or None


def _commit_log(repo_with_history: Path, old_sha: str, new_sha: str, *, timeout: int) -> list[str] | None:
    """Best-effort: `old_sha..new_sha` one-line commit summaries, or None if
    the range can't be resolved (old_sha not reachable in this history --
    e.g. a shallow recruited clone, or an upstream force-push). None here is
    an honest "not available", not an error."""
    if old_sha == new_sha:
        return []
    result = _run_git(["log", "--oneline", f"{old_sha}..{new_sha}"], cwd=repo_with_history, timeout=timeout)
    if result.returncode != 0:
        return None
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    return lines


def _matching_stems(root: Path | None, stems: set[str]) -> list[str]:
    """Files under `root` whose stem matches a changed reference file's
    stem -- a deterministic, language-agnostic (and therefore necessarily
    approximate) signal that a Zone H/I artifact MIGHT reference material
    that just changed upstream. Basename matching only; never claims more
    precision than that."""
    if root is None or not root.exists() or not stems:
        return []
    matches = []
    for p in sorted(root.rglob("*")):
        if p.is_file() and p.stem in stems:
            matches.append(str(p.relative_to(root)))
    return matches


def diff_reference(
    zone_r: Path,
    *,
    zone_h: Path | None = None,
    zone_i: Path | None = None,
    clone_timeout: int = 300,
    git_timeout: int = 30,
) -> dict[str, Any]:
    """Re-clone the same reference source registered at recruitment time
    into a throwaway temp directory, and diff it against the actually-
    recruited `zone_r` checkout. Raises ReferenceDiffError if `zone_r` isn't
    a git checkout with a resolvable origin, or if the re-clone fails --
    never returns a fabricated/partial diff for either case.

    `zone_h`/`zone_i`, if given, are searched (by filename stem only, best-
    effort) for artifacts that might reference a changed file -- surfaced as
    `possibly_stale_refs`, never as a firm claim of staleness.
    """
    origin_url = registered_origin_url(zone_r, timeout=git_timeout)
    if origin_url is None:
        raise ReferenceDiffError(
            f"{zone_r} is not a git checkout with a resolvable 'origin' remote -- diff-reference only "
            "supports a reference recruited via 'git clone' (the pattern every recruited project observed "
            "so far actually uses), so there is a known, git-verifiable upstream to re-fetch and diff "
            "against. Refusing to guess a source rather than fabricating a comparison."
        )
    baseline_commit = current_commit(zone_r, timeout=git_timeout)
    baseline_tree, baseline_skipped = hash_tree(zone_r)

    with tempfile.TemporaryDirectory(prefix="cleanroom-diff-reference-") as tmp_dir:
        fresh_clone = Path(tmp_dir) / "fresh"
        clone_result = _run_git(["clone", "--quiet", origin_url, str(fresh_clone)], timeout=clone_timeout)
        if clone_result.returncode != 0:
            raise ReferenceDiffError(
                f"re-clone of the registered reference source ({origin_url}) failed: "
                f"{clone_result.stderr.strip() or clone_result.stdout.strip() or 'unknown git error'}"
            )
        latest_commit = current_commit(fresh_clone, timeout=git_timeout)
        latest_tree, latest_skipped = hash_tree(fresh_clone)

        commit_log: list[str] | None = None
        if baseline_commit and latest_commit:
            commit_log = _commit_log(fresh_clone, baseline_commit, latest_commit, timeout=git_timeout)

    baseline_files = set(baseline_tree)
    latest_files = set(latest_tree)
    new_files = sorted(latest_files - baseline_files)
    deleted_files = sorted(baseline_files - latest_files)
    modified_files = sorted(f for f in (baseline_files & latest_files) if baseline_tree[f] != latest_tree[f])
    unchanged_count = len(baseline_files & latest_files) - len(modified_files)

    changed_stems = {Path(f).stem for f in (*new_files, *deleted_files, *modified_files)}
    possibly_stale_refs = {
        "zone_h": _matching_stems(zone_h, changed_stems),
        "zone_i": _matching_stems(zone_i, changed_stems),
    }

    return {
        "reference_source": origin_url,
        "baseline_commit": baseline_commit,
        "latest_commit": latest_commit,
        "up_to_date": bool(baseline_commit and latest_commit and baseline_commit == latest_commit),
        "commit_log": commit_log,  # None means "not resolvable", not "no commits"
        "new_files": new_files,
        "modified_files": modified_files,
        "deleted_files": deleted_files,
        "unchanged_file_count": unchanged_count,
        "possibly_stale_refs": possibly_stale_refs,
        "baseline_skipped": baseline_skipped,
        "latest_skipped": latest_skipped,
    }
