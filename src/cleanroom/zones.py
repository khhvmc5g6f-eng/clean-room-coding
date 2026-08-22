"""Parts V-VII: the three-zone clean-room model and its technical information barrier.

Honesty about what this enforces: cleanroom cannot sandbox an arbitrary
external editor or agent harness that ignores it entirely -- that requires
OS-level containers/worktrees/credentials, which projects should layer on
top (see docs/architecture.md#technical-isolation). What cleanroom *does*
guarantee is that every read performed through its own APIs -- which is how
the CLI, the Skill's scripts, and any orchestration built on this library
touch files -- is checked against the agent's permitted-directory list
before the bytes are returned, and every denial is written to the evidence
ledger. That is a real, testable barrier for anything built on this
library; it is not a claim that no process on the machine could ever read
Zone R.
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


def run_isolation_test(zone_r: Path, zone_h: Path, zone_i: Path) -> tuple[bool, str]:
    """Part LXXV Isolation Test: an implementation-scoped agent must be DENIED reading Zone R."""
    scope = AgentZoneScope(agent_id="isolation-test-agent", role="implementation", permitted_zones=frozenset({"H", "I"}))
    guard = PathGuard(scope, zone_r, zone_h, zone_i)
    probe = zone_r / "__isolation_probe__.txt"
    try:
        guard.check(probe)
        return False, "FAIL: implementation-scoped agent was NOT denied access to Zone R"
    except ZoneAccessDenied:
        return True, "DENIED (expected)"
