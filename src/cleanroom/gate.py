"""Part XCIV: the Clean-Room Gate.

A recorded, evidence-backed PASS/FAIL decision on whether a specification
version is sufficient for independent implementation and free of restricted
material -- sitting between Sanitise and Handoff. `cleanroom handoff`
refuses to build a manifest for a specification version without a matching
PASS decision here (see `cli.py::handoff`); this module supplies the real
mechanical signal a human reviewer's `--decision` is checked against, but
never substitutes for that decision. See SKILL.md's "Mandatory stage: Team
A / Team B implementation handover" and `references/clean-room-gate.md`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cleanroom.schema_registry import validate
from cleanroom.specification.graph import RequirementGraph
from cleanroom.util import utc_now_iso

DECISIONS_FILENAME = "GATE_DECISIONS.json"


def compute_signal(graph: RequirementGraph, sanitisation_reports_dir: Path) -> dict[str, Any]:
    """Deterministic sufficiency/cleanliness check -- never itself the
    decision. 'sufficient' means: at least one observable_requirement node
    is actually handoff-eligible, AND no sanitisation report on file for a
    candidate Zone H document is blocked. Either failing makes it
    'insufficient' -- this is intentionally a low bar (real coverage
    judgement is a human task; see `cleanroom specify report` for the
    fuller traceability picture), not a claim that the spec is *good*,
    only that it isn't obviously empty or contaminated."""
    eligible = graph.handoff_eligible_nodes()
    blocking_reports: list[str] = []
    if sanitisation_reports_dir.is_dir():
        for path in sorted(sanitisation_reports_dir.glob("*.json")):
            report = json.loads(path.read_text(encoding="utf-8"))
            if report.get("blocked"):
                blocking_reports.append(path.name)
    sufficiency = {
        "handoff_eligible_nodes": len(eligible),
        "total_requirement_nodes": len(graph.nodes),
        "source_implementation_details_excluded": len(graph.source_implementation_details()),
    }
    automated_signal = "sufficient" if (eligible and not blocking_reports) else "insufficient"
    return {
        "automated_signal": automated_signal,
        "sufficiency": sufficiency,
        "blocking_sanitisation_reports": blocking_reports,
    }


def build_decision(
    *,
    project_id: str,
    specification_version: str,
    decision: str,
    reviewer: str,
    notes: str,
    signal: dict[str, Any],
    sequence: int,
) -> dict[str, Any]:
    """`sequence` is the 1-based position of this decision among every gate
    decision this project has ever recorded (across all specification
    versions) -- the caller derives it from the existing decisions list, the
    same pattern `cleanroom remediate`'s CR-REM-###### ids use, so an id
    stays stable across repeated runs regardless of how many decisions
    exist for other versions."""
    overrode = decision == "pass" and signal["automated_signal"] == "insufficient"
    record = {
        "id": f"CR-GATE-{sequence:06d}",
        "project_id": project_id,
        "specification_version": specification_version,
        "decision": decision,
        "reviewer": reviewer,
        "notes": notes,
        "reviewed_utc": utc_now_iso(),
        "automated_signal": signal["automated_signal"],
        "overrode_automated_signal": overrode,
        "sufficiency": signal["sufficiency"],
        "blocking_sanitisation_reports": signal["blocking_sanitisation_reports"],
    }
    errors = validate(record, "gate-decision.schema.json")
    if errors:
        raise ValueError(f"Built an invalid gate decision: {errors}")
    return record


def load_decisions(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def save_decisions(path: Path, decisions: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(decisions, f, indent=2, sort_keys=True)


def latest_decision(decisions: list[dict[str, Any]], specification_version: str) -> dict[str, Any] | None:
    """The most recent decision recorded for this exact specification
    version -- a version amended after a FAIL (or after the validation
    loop sends discrepancies back) gets a fresh, distinct
    specification_version per `cleanroom handoff --specification-version`,
    so this never needs to reconcile two decisions for the same version;
    it only needs the latest one if a version was ever re-gated."""
    matching = [d for d in decisions if d["specification_version"] == specification_version]
    return matching[-1] if matching else None
