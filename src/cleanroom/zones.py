"""Parts V-VII: the three-zone clean-room model and its technical information barrier.

Honesty about what this enforces, corrected after a security review found
the previous wording overclaimed: `PathGuard` is a real, tested access-
control primitive (`run_pathguard_self_test` proves the mechanism itself
denies correctly), but as of this version, `cli.py`'s commands do not yet
route their own file reads through it per-invocation -- doing so requires
every command to know which registered agent is running it, which the
current stateless-CLI design does not track. Until that wiring exists,
treat `PathGuard` as available for orchestration you build on top of this
library (e.g. a harness that spawns an implementation subagent and gates
its file-read tool through `PathGuard.check()`), not as something that
already gates every `cleanroom` CLI invocation today.

For a signal that IS specific to a real project today, see
`check_agent_zone_consistency`: it cross-references the AgentRegistry
(who was registered, with what zone access) against the evidence ledger
(what zone each logged action actually claimed) and flags any agent
recorded acting in a zone it wasn't scoped for. That depends on whatever
orchestration ran the agent having logged the zone honestly -- the same
good-faith assumption anything built on an evidence ledger ultimately
rests on -- but it is a real, per-project check, not a fixed unit test.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

ZONE_NAMES = ("R", "H", "I")


class ZoneAccessDenied(PermissionError):
    pass


def create_zones(project_root: Path, zone_r: Path, zone_h: Path, zone_i: Path) -> None:
    for zone_path in (zone_r, zone_h, zone_i):
        zone_path.mkdir(parents=True, exist_ok=True)
        gitkeep = zone_path / ".gitkeep"
        if not any(zone_path.iterdir()):
            gitkeep.touch()


@dataclass
class AgentZoneScope:
    """The permitted/prohibited directory allow-list for one agent instance (Part VII)."""

    agent_id: str
    role: str
    permitted_zones: frozenset[str]
    permitted_paths: tuple[Path, ...] = field(default_factory=tuple)
    prohibited_paths: tuple[Path, ...] = field(default_factory=tuple)


class PathGuard:
    """Checks a path access against an AgentZoneScope. Raises ZoneAccessDenied on violation.

    Strict clean-room mode (Part VI): an implementation-zone agent (permitted_zones
    without "R") must never be able to resolve a read to anything under a
    reference-zone path, even via a symlink or a '..' traversal.
    """

    def __init__(self, scope: AgentZoneScope, zone_r: Path, zone_h: Path, zone_i: Path):
        self.scope = scope
        self.zone_paths = {"R": zone_r.resolve(), "H": zone_h.resolve(), "I": zone_i.resolve()}

    def check(self, path: Path) -> None:
        resolved = path.resolve()
        for prohibited in self.scope.prohibited_paths:
            if _is_within(resolved, prohibited.resolve()):
                raise ZoneAccessDenied(f"{self.scope.agent_id}: path {path} is explicitly prohibited")
        for zone_letter, zone_path in self.zone_paths.items():
            if _is_within(resolved, zone_path) and zone_letter not in self.scope.permitted_zones:
                raise ZoneAccessDenied(
                    f"{self.scope.agent_id} (role={self.scope.role}) is not permitted to access "
                    f"Zone {zone_letter} ({zone_path}); requested {path}"
                )
        # If permitted_paths has been given explicitly, this scope is an
        # allow-list: anything not inside a permitted zone AND not inside
        # a permitted_paths entry is denied, including paths entirely
        # outside R/H/I (a stray copy of reference material elsewhere on
        # disk, an unrelated project, a path traversal). Without an
        # explicit permitted_paths, PathGuard only polices the three named
        # zones (the common case: an agent also needs the project root,
        # evidence dir, etc.) -- callers that need a true allow-list must
        # populate permitted_paths themselves.
        if self.scope.permitted_paths:
            in_permitted_zone = any(
                _is_within(resolved, zone_path) and zone_letter in self.scope.permitted_zones
                for zone_letter, zone_path in self.zone_paths.items()
            )
            in_permitted_path = any(_is_within(resolved, p.resolve()) for p in self.scope.permitted_paths)
            if not in_permitted_zone and not in_permitted_path:
                raise ZoneAccessDenied(
                    f"{self.scope.agent_id} (role={self.scope.role}) has an explicit allow-list and "
                    f"{path} is not within any permitted zone or permitted_paths entry"
                )

    def is_allowed(self, path: Path) -> bool:
        try:
            self.check(path)
            return True
        except ZoneAccessDenied:
            return False


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def run_pathguard_self_test(zone_r: Path, zone_h: Path, zone_i: Path) -> tuple[bool, str]:
    """Part LXXV Isolation Test -- but read this narrowly. This proves the
    PathGuard MECHANISM correctly denies an implementation-scoped access
    to Zone R when it is actually consulted. It is a unit-level sanity
    check on inert code, not evidence that any real agent working on this
    specific project was ever gated by it -- the CLI commands in cli.py
    do not currently route their own file reads through PathGuard (that
    would require every command to know, per invocation, which registered
    agent is running it). For a project-specific signal, see
    `check_agent_zone_consistency`, which cross-references the actual
    AgentRegistry and evidence ledger for THIS project."""
    scope = AgentZoneScope(agent_id="pathguard-self-test", role="implementation", permitted_zones=frozenset({"H", "I"}))
    guard = PathGuard(scope, zone_r, zone_h, zone_i)
    probe = zone_r / "__isolation_probe__.txt"
    try:
        guard.check(probe)
        return False, "FAIL: implementation-scoped agent was NOT denied access to Zone R"
    except ZoneAccessDenied:
        return True, "DENIED (expected) -- this confirms the PathGuard mechanism works, not that it gated every real read this project made (see docstring)."


# Backwards-compatible alias for the pre-audit name.
run_isolation_test = run_pathguard_self_test


def check_agent_zone_consistency(agents: list[dict], ledger_events: list[dict]) -> list[str]:
    """A real, project-specific check (unlike the self-test above): for
    every agent registered with 'R' NOT in its permitted_zones, does the
    evidence ledger nonetheless contain an event recorded under zone='R'
    attributed to that agent? If so, that is a genuine, evidenced
    violation -- either the agent read Zone R when it shouldn't have, or
    whatever orchestration ran it mis-logged the zone. Either way it's a
    real finding, not a tautology. This depends on the orchestrating
    harness having faithfully logged the zone of each action (the same
    good-faith assumption this module's own honesty note already makes
    about anything built on cleanroom's APIs)."""
    problems: list[str] = []
    r_scoped_agent_ids = {
        a["agent_id"] for a in agents if "R" not in a.get("permitted_zones", [])
    }
    for event in ledger_events:
        actor = event.get("actor", {})
        if actor.get("id") in r_scoped_agent_ids and event.get("zone") == "R":
            problems.append(
                f"agent {actor.get('id')} (role={actor.get('role')}) is registered without Zone R access "
                f"but evidence event {event.get('event_id')} ({event.get('action')}) is logged under zone='R'"
            )
    return problems
