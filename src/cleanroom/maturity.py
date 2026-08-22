"""Automatic clean-room maturity level (CR0-CR5) computation from project
state (see docs/clean-room-levels.md for the human-readable rubric this
mirrors).

`.cleanroom.yml`'s `clean_room_level` is a project owner's DECLARATION of
their target/claimed level, not something this module overrides -- Part
XI: never silently turn a declaration into a verified fact, or a verified
fact into a declaration. `compute_level()` independently derives the
highest level the project's current, on-disk state actually demonstrates;
callers (`cleanroom status`) show both side by side so any mismatch stays
visible rather than being silently reconciled in either direction.

Levels are cumulative -- CR3 requires CR1+CR2's criteria to still hold, not
just CR3's own. Climbing stops at the first level with an unmet criterion,
but every level's criteria are still evaluated and reported, so a project
stuck below CR3 can still see exactly which CR4 criteria it would also
need once CR3 is reached.

CR5's "adversarial legal review... reviewed by qualified counsel"
criterion has no fact this tool can check deterministically -- whether a
human lawyer actually read and endorsed `cleanroom judge`'s prompts isn't
observable from project files. It is always reported unmet, with a note
explaining why, rather than silently skipped or auto-granted -- so the
computed level can never automatically reach CR5.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from cleanroom.orchestration.agents import AgentRegistry
from cleanroom.zones import run_pathguard_self_test

if TYPE_CHECKING:
    from cleanroom.project import Project

LEVELS = ["CR0", "CR1", "CR2", "CR3", "CR4", "CR5"]


@dataclass
class Criterion:
    description: str
    met: bool
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"description": self.description, "met": self.met}
        if self.note:
            d["note"] = self.note
        return d


@dataclass
class LevelResult:
    level: str
    criteria: list[Criterion]

    @property
    def satisfied(self) -> bool:
        return all(c.met for c in self.criteria)

    def to_dict(self) -> dict[str, Any]:
        return {"level": self.level, "satisfied": self.satisfied, "criteria": [c.to_dict() for c in self.criteria]}


def _cr1_criteria(project: "Project") -> list[Criterion]:
    ledger_events = project.evidence.read_all()
    zones_exist = project.zone_r.is_dir() and project.zone_h.is_dir() and project.zone_i.is_dir()
    return [
        Criterion("Evidence ledger has at least one recorded event", bool(ledger_events)),
        Criterion("Zone R/H/I directories all exist", zones_exist),
    ]


def _cr2_criteria(project: "Project") -> list[Criterion]:
    manifest_exists = (project.zone_h / "HANDOFF_MANIFEST.json").is_file()
    registry = AgentRegistry(project.root / "evidence")
    has_r_blind_agent = any("R" not in a.permitted_zones for a in registry.all())
    return [
        Criterion("A handoff manifest has been built from sanitised material (cleanroom handoff)", manifest_exists),
        Criterion(
            "At least one implementation agent is registered without Zone R access (cleanroom build)",
            has_r_blind_agent,
        ),
    ]


def _cr3_criteria(project: "Project") -> list[Criterion]:
    isolation_ok, isolation_detail = run_pathguard_self_test(project.zone_r, project.zone_h, project.zone_i)
    sbom_exists = (project.root / "evidence" / "sbom" / "sbom.spdx.json").is_file()
    return [
        Criterion(
            "PathGuard technical isolation self-test passes (cleanroom audit)",
            isolation_ok,
            "" if isolation_ok else isolation_detail,
        ),
        Criterion("SBOM/provenance has been generated (cleanroom provenance)", sbom_exists),
    ]


def _cr4_criteria(project: "Project") -> list[Criterion]:
    similarity_exists = (project.root / "evidence" / "similarity-findings.json").is_file()
    ledger_problems = project.evidence.verify_chain()

    matrix_path = project.root / "JURISDICTION_MATRIX.json"
    matrix_ok = False
    matrix_note = "cleanroom jurisdiction has not been run"
    if matrix_path.is_file():
        matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
        required = set(project.config.required_markets())
        tiers: dict[str, str] = {}
        for issue in matrix.get("issues", []):
            for j in issue.get("jurisdictions", []):
                tiers[j["jurisdiction"]] = j["tier"]
        unresolved = sorted(m for m in required if tiers.get(m) in (None, "unknown"))
        matrix_ok = not unresolved
        matrix_note = "" if matrix_ok else f"no jurisdiction pack for required market(s): {unresolved}"

    legal_findings_exist = (project.root / "evidence" / "legal-findings.json").is_file()
    return [
        Criterion("Similarity review has been run against the implementation (cleanroom similarity)", similarity_exists),
        Criterion("Evidence ledger hash chain is intact (cleanroom verify)", not ledger_problems, "; ".join(ledger_problems)),
        Criterion("Every required market has a real jurisdiction pack (cleanroom jurisdiction)", matrix_ok, matrix_note),
        Criterion("The legal issue engine has been run for required markets (cleanroom legal)", legal_findings_exist),
    ]


def _cr5_criteria(project: "Project") -> list[Criterion]:
    manifest_path = project.zone_h / "HANDOFF_MANIFEST.json"
    signed = False
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        signed = bool(manifest.get("signature"))
    return [
        Criterion("The handoff manifest is cryptographically signed (cleanroom handoff --signer ...)", signed),
        Criterion(
            "Adversarial legal review has been completed and reviewed by qualified counsel",
            False,
            "Not verifiable from project files -- this tool cannot confirm a human lawyer reviewed "
            "cleanroom judge's prompts. Requires an explicit human declaration; never auto-granted.",
        ),
    ]


_CRITERIA_FNS = {
    "CR1": _cr1_criteria,
    "CR2": _cr2_criteria,
    "CR3": _cr3_criteria,
    "CR4": _cr4_criteria,
    "CR5": _cr5_criteria,
}


def compute_level(project: "Project") -> dict[str, Any]:
    """Returns {"computed_level", "declared_level", "matches_declared", "levels"}.
    `levels` lists every CR1-CR5 level's criteria and whether each was met,
    even past the point climbing stopped, so a project can see what it
    would still need once its current blocker is fixed."""
    results: list[LevelResult] = []
    highest_satisfied = "CR0"
    still_climbing = True
    for level in LEVELS[1:]:
        result = LevelResult(level=level, criteria=_CRITERIA_FNS[level](project))
        results.append(result)
        if still_climbing and result.satisfied:
            highest_satisfied = level
        else:
            still_climbing = False

    declared = project.config.clean_room_level
    return {
        "computed_level": highest_satisfied,
        "declared_level": declared,
        "matches_declared": highest_satisfied == declared,
        "levels": [r.to_dict() for r in results],
    }
