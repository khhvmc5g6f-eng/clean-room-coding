"""Parts V-VII: the three-zone clean-room model and its technical information barrier.

Honesty about what this enforces, corrected twice now. A security review
first found that `PathGuard` was a real, tested access-control primitive
(`run_pathguard_self_test` proves the mechanism itself denies correctly)
that `cli.py`'s commands didn't route their own file reads through per-
invocation, because doing so requires every command to know which
registered agent is running it -- something the stateless CLI has no way
to track on its own.

That's now solved for a real subset of commands: pass a global
`--agent-id <id>` (an agent registered via `cleanroom build`, or directly
via `AgentRegistry` for any other role) and `inspect`/`licence`/
`similarity`/`sanitise`/`diff-reference` (see `cli.py`'s
`Ctx.enforce_zone_access`) genuinely call `PathGuard.check()` against that
agent's real registered scope before reading the path given -- verified
end-to-end against a real project, not just this module's own self-test,
including both the deny path (a Zone-H+I-only `cleanroom build` agent
denied `zone-r`, and separately an R-only agent denied `cleanroom
sanitise` of a Zone H document -- the actual R-to-H boundary-crossing gate
PathGuard exists to police) and the allow path (an `R`-scoped agent let
through `licence`, an `H`-scoped agent let through `sanitise`).

This used to be purely opt-in: omitting `--agent-id` was a silent no-op
regardless of project state, which meant an orchestrator that simply
forgot the flag got unrestricted, ungated access with no warning -- a
real footgun for a tool whose entire value proposition is provable
separation. It is now fail-closed once there is something real to
protect: as soon as a project has at least one registered Zone-I
(implementation) agent (`AgentRegistry.has_registered_implementation_agent`
-- i.e. `cleanroom build`/`cleanroom implement` has run at least once for
that project), the five commands above REQUIRE `--agent-id` and refuse to
run without it. Before any implementation agent has been registered
(initial `init`/`recruit`/pre-build analysis, when there is no
Reference/Implementation separation yet to protect), `--agent-id` remains
optional and omitting it behaves exactly as before.

**This is still a real, narrower-than-total gap, not "solved":** only
those five commands call `enforce_zone_access`, and the fail-closed
requirement is scoped to "does this project have a registered
implementation agent yet," not "always." Every other command still reads
files directly with no gate --
notably `compare`, which doesn't load a `Project` at all today, so adding
enforcement there would be a real behaviour change (forcing every
invocation to run inside a clean-room project directory), not the
purely-additive pattern used for the other four; and
`similarity --negative-control` paths, which are deliberately meant to
sit *outside* the three zones and so shouldn't be PathGuard-checked at
all. Full coverage (every command, every invocation, mandatory rather
than opt-in) remains future work -- see ROADMAP.md. Building `cleanroom`
into a larger multi-agent orchestration harness can and should call
`Ctx.enforce_zone_access` (or `PathGuard.check()` directly) for every file
read its own subagents perform, the same way these four commands now do.

For a signal that IS specific to a real project regardless of
`--agent-id`, see `check_agent_zone_consistency`: it cross-references the
AgentRegistry (who was registered, with what zone access) against the
evidence ledger (what zone each logged action actually claimed) and flags
any agent recorded acting in a zone it wasn't scoped for. That depends on
whatever orchestration ran the agent having logged the zone honestly --
the same good-faith assumption anything built on an evidence ledger
ultimately rests on -- but it is a real, per-project check, not a fixed
unit test.
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
    to Zone R when it is actually consulted, using a synthetic probe scope,
    not a real registered agent. `cli.py`'s `inspect`/`licence`/`similarity`/
    `sanitise` commands now do route real reads through this same
    mechanism for real registered agents, but only when the caller opts in
    with `--agent-id`
    (see `Ctx.enforce_zone_access` and this module's own docstring) -- every
    other command, and any invocation without `--agent-id`, is still
    unguarded. For a project-specific signal that doesn't depend on
    `--agent-id` at all, see `check_agent_zone_consistency`, which cross-
    references the actual AgentRegistry and evidence ledger for THIS
    project."""
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
