"""Part XCV: a web-lookup exclusion guard for implementation-zone agents.

The three-zone model (AGENTS.md item a) forbids a Zone H+I implementation
agent from ever reading Zone R (the reference material a project exists to
avoid copying). That rule has never said an implementation agent can't
search the web at all -- it has no sanctioned way to do so today, which
just pushes real engineering questions (a public-domain CRC reference, an
official spec, a permissively-licensed helper library) onto the agent's
unaided memory. This module gives an orchestrating harness a real,
deterministic check to run before it lets an implementation agent's
web-fetch/web-search tool actually hit a URL: "does this target match the
Zone R material (or an obvious mirror/fork of it) this project exists to
avoid copying?"

Read `docs/web-lookup-guard.md` before wiring this in -- it documents the
actual integration contract and, just as importantly, what this module
does NOT do: it is a decision function, not a live network interceptor.
This process has no hook into whatever tool/runtime actually performs a
web-fetch inside an orchestrating harness or agent framework; it cannot
block a request happening in that other process. Claiming otherwise would
be exactly the kind of overclaim AGENTS.md item c warns against for
findings -- the same honesty standard applies here to what this tool can
technically do.

Design notes:

- The registered exclusion set for a project is derived the same way
  `cleanroom diff-reference` derives "the registered reference source"
  (see `reference_diff.py`'s module docstring): from the recruited Zone R
  checkout's own git `origin` remote, via `registered_origin_url`. There is
  deliberately no second, hand-maintained "what did we recruit" record to
  fall out of sync with reality.
- If Zone R was not recruited via `git clone` (no `.git`, or no `origin`
  remote), there is nothing to derive automatically -- `registered_exclusions`
  then returns an empty list rather than guessing a pattern, per the
  never-fabricate-a-conclusion rule (AGENTS.md item c). A human can still
  cover that project with `cleanroom exclude-source` entries.
- Matching is deliberately conservative-but-real: a `github.com/OWNER/REPO`
  reference excludes any URL whose path contains OWNER/REPO as two
  *consecutive* path segments (case-insensitive), not a bare substring
  match on OWNER+REPO text. That is what actually catches
  `raw.githubusercontent.com/OWNER/REPO/...`, a bare git remote's
  `.../OWNER/REPO.git`, and most third-party mirror hosts that echo the
  same `OWNER/REPO` path shape (e.g. `some-mirror.example/mirror/OWNER/
  REPO`) -- while NOT blocking an unrelated page that merely mentions the
  project by name (a Wikipedia article, a blog post, an unrelated
  `OWNER/some-other-repo`). See the module docstring in `docs/
  web-lookup-guard.md` for the known limitations of this heuristic (it is
  a path-shape heuristic, not a content-aware one -- a mirror that
  reshuffles the path, e.g. serving the same code under a completely
  different name, will not be caught automatically; use `exclude-source`
  for those once identified).
- Every check -- blocked or allowed -- is appended to the project's
  existing hash-chained evidence ledger (`cleanroom.evidence.EvidenceLedger`,
  the same ledger `cleanroom verify` walks), so there is a real, tamper-
  evident record of what an implementation agent looked up during a
  project, for later human review. This reuses the existing ledger rather
  than inventing a second audit mechanism.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from cleanroom.evidence import Actor, EvidenceLedger
from cleanroom.reference_diff import registered_origin_url
from cleanroom.util import utc_now_iso

EXCLUSIONS_FILENAME = "exclusions.json"


def _strip_dot_git(segment: str) -> str:
    return segment[:-4] if segment.lower().endswith(".git") else segment


_SCP_LIKE = re.compile(r"^(?:[\w.\-]+@)?(?P<host>[\w.\-]+):(?P<path>.+)$")


def parse_owner_repo(url: str) -> tuple[str, str, str] | None:
    """Best-effort (host, owner, repo) extraction from a git remote URL.
    Handles https://host/owner/repo(.git), scp-like git@host:owner/repo(.git)
    and ssh://git@host/owner/repo(.git). Returns None if the URL doesn't
    resolve to a recognisable two-segment owner/repo path -- callers must
    treat that as "cannot derive a structured exclusion", not an error.
    """
    url = url.strip()
    if "://" not in url:
        m = _SCP_LIKE.match(url)
        if not m:
            return None
        host = m.group("host").lower()
        path = _strip_dot_git(m.group("path")).strip("/")
        parts = [p for p in path.split("/") if p]
        if len(parts) < 2:
            return None
        return host, parts[-2], parts[-1]

    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    if not host:
        return None
    path = _strip_dot_git(parsed.path).strip("/")
    parts = [p for p in path.split("/") if p]
    if len(parts) < 2:
        return None
    return host, parts[-2], parts[-1]


@dataclass
class ExclusionEntry:
    """One entry in a project's exclusion list, automatic or manual.

    kind:
      - "path_segment": `pattern` is "OWNER/REPO"; matches any URL whose
        path contains OWNER then REPO as consecutive path segments
        (case-insensitive), regardless of host. This is what catches
        mirror hosts.
      - "host_path_segment": `pattern` is "HOST/OWNER/REPO"; same as above
        but also requires the URL's host to match HOST exactly. Used for
        the specific, named "obvious mirror" domains (e.g.
        raw.githubusercontent.com) so the audit record names them
        explicitly even though the host-agnostic path_segment entry above
        would already catch them.
      - "substring": `pattern` is matched as a plain case-insensitive
        substring of the full URL. Used for manually-added patterns from
        `cleanroom exclude-source` and as the fallback when a registered
        Zone R origin could not be parsed into owner/repo (e.g. no `.git`,
        an unrecognised URL shape) -- covers it as a literal string rather
        than fabricating a structured pattern that isn't there.
    """

    pattern: str
    kind: str
    source: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def registered_exclusions(zone_r: Path, *, git_timeout: int = 30) -> list[ExclusionEntry]:
    """Auto-derived exclusions for a project's recruited Zone R checkout,
    from its git `origin` remote (same source of truth as
    `cleanroom diff-reference` -- see reference_diff.py). Returns an empty
    list, never a guess, if zone_r isn't a git checkout with a resolvable
    origin."""
    origin = registered_origin_url(zone_r, timeout=git_timeout)
    if origin is None:
        return []

    parsed = parse_owner_repo(origin)
    if parsed is None:
        return [
            ExclusionEntry(
                pattern=origin,
                kind="substring",
                source=(
                    f"registered zone-r origin ({origin}) -- could not parse an owner/repo path from "
                    "this URL, so it is excluded as a literal substring rather than a structured pattern"
                ),
            )
        ]

    host, owner, repo = parsed
    owner_repo = f"{owner}/{repo}"
    entries = [
        ExclusionEntry(
            pattern=owner_repo,
            kind="path_segment",
            source=f"registered zone-r origin ({origin}): host-agnostic owner/repo path match",
        ),
        ExclusionEntry(
            pattern=f"{host}/{owner_repo}",
            kind="host_path_segment",
            source=f"registered zone-r origin ({origin}): the origin host itself",
        ),
    ]
    if host == "github.com":
        entries.append(
            ExclusionEntry(
                pattern=f"raw.githubusercontent.com/{owner_repo}",
                kind="host_path_segment",
                source=f"registered zone-r origin ({origin}): known raw-content mirror of a GitHub repo",
            )
        )
    return entries


class ExclusionStore:
    """Persisted, human-maintained additions to a project's exclusion list
    (`cleanroom exclude-source`) -- for known mirrors/forks the automatic
    owner/repo heuristic above can't identify on its own (a rehosted copy
    under an unrelated name, a vendored tarball site, etc). Lives in the
    project's evidence directory, alongside the agent registry and the
    evidence ledger it shares a directory with, rather than inventing a new
    top-level project file."""

    def __init__(self, evidence_dir: Path):
        self.path = evidence_dir / EXCLUSIONS_FILENAME
        self._entries: list[dict[str, Any]] = []
        if self.path.is_file():
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._entries = data.get("exclusions", [])

    def add(self, pattern: str, *, note: str | None = None) -> ExclusionEntry:
        entry = ExclusionEntry(
            pattern=pattern,
            kind="substring",
            source=f"manual (cleanroom exclude-source){f': {note}' if note else ''}",
        )
        record = entry.to_dict()
        record["added_utc"] = utc_now_iso()
        self._entries.append(record)
        self._save()
        return entry

    def all(self) -> list[ExclusionEntry]:
        return [
            ExclusionEntry(pattern=e["pattern"], kind=e["kind"], source=e["source"]) for e in self._entries
        ]

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump({"exclusions": self._entries}, f, indent=2, sort_keys=True)
            f.write("\n")


def _target_path_parts(url: str) -> list[str]:
    parts = [p for p in urlsplit(url).path.split("/") if p]
    return [_strip_dot_git(p) for p in parts]


def _target_host(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def _matches(entry: ExclusionEntry, url: str) -> bool:
    if entry.kind == "substring":
        return entry.pattern.lower() in url.lower()

    if entry.kind == "path_segment":
        owner, _, repo = entry.pattern.partition("/")
        return _has_consecutive_segments(_target_path_parts(url), owner, repo)

    if entry.kind == "host_path_segment":
        host_part, _, owner_repo = entry.pattern.partition("/")
        owner, _, repo = owner_repo.partition("/")
        if _target_host(url) != host_part.lower():
            return False
        return _has_consecutive_segments(_target_path_parts(url), owner, repo)

    return False  # pragma: no cover -- unknown kind, fail safe (never matches -> never wrongly blocks)


def _has_consecutive_segments(parts: list[str], first: str, second: str) -> bool:
    first_l, second_l = first.lower(), second.lower()
    return any(
        parts[i].lower() == first_l and parts[i + 1].lower() == second_l for i in range(len(parts) - 1)
    )


def check_url_against_exclusions(url: str, project: Any) -> dict[str, Any]:
    """The check an orchestrating harness runs BEFORE actually fetching
    `url` on behalf of an implementation-zone agent. `project` is a
    `cleanroom.project.Project` (duck-typed here to avoid a hard import
    cycle; it must expose `.zone_r: Path` and `.evidence: EvidenceLedger`
    and `.root: Path`).

    Returns {"blocked": bool, "reason": str | None, "matched_pattern":
    str | None, "matched_source": str | None}. Every call -- blocked or
    allowed -- is appended to `project.evidence`, so there is a durable
    record of what an implementation agent looked up. See
    docs/web-lookup-guard.md for what the caller is expected to do with a
    blocked result (this module only decides; it cannot itself stop a
    fetch happening in another process)."""
    auto_entries = registered_exclusions(project.zone_r)
    manual_store = ExclusionStore(project.root / "evidence")
    manual_entries = manual_store.all()

    matched: ExclusionEntry | None = None
    for entry in (*auto_entries, *manual_entries):
        if _matches(entry, url):
            matched = entry
            break

    blocked = matched is not None
    result: dict[str, Any] = {
        "blocked": blocked,
        "reason": (
            f"URL matches this project's excluded reference material (pattern '{matched.pattern}', "
            f"{matched.source})"
            if matched
            else None
        ),
        "matched_pattern": matched.pattern if matched else None,
        "matched_source": matched.source if matched else None,
    }

    project.evidence.append(
        actor=Actor(type="tool", id="cleanroom-webguard"),
        action="cleanroom webguard check-url",
        zone="I",
        result="denied" if blocked else "success",
        detail=f"url={url}" + (f" matched_pattern={matched.pattern}" if matched else " matched=none"),
    )
    return result
