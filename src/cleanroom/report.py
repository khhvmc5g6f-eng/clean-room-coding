"""Parts LVI, LXXXV, XCIII: the release policy engine, CLEAN_ROOM_CERTIFICATE.json,
and the human-readable final report.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cleanroom.schema_registry import validate
from cleanroom.util import sha256_json, utc_now_iso

CERTIFICATE_DISCLAIMER = (
    "This certificate records process completion within the Clean Room Coding tool. "
    "It is not a legal opinion, a warranty of non-infringement, or certification by any "
    "accredited body. Findings from simulated legal/judicial panels are AI-generated "
    "heuristics for engineering triage and require qualified human legal review before "
    "any release decision with real legal consequence."
)


def release_allowed(
    *,
    technical_gate: bool,
    provenance_gate: bool,
    contamination_gate: bool,
    global_decision: str,
    require_technical_gate: bool,
    require_provenance_gate: bool,
    require_contamination_gate: bool,
    block_on_red_required_jurisdiction: bool,
) -> tuple[bool, list[str]]:
    """Part LVI. Every requested gate must PASS; a RED in a required
    jurisdiction blocks release even if every technical gate is green
    (Part LV: do not average jurisdiction results)."""
    reasons = []
    if require_technical_gate and not technical_gate:
        reasons.append("technical_gate did not pass")
    if require_provenance_gate and not provenance_gate:
        reasons.append("provenance_gate did not pass")
    if require_contamination_gate and not contamination_gate:
        reasons.append("contamination_gate did not pass")
    if block_on_red_required_jurisdiction and global_decision == "RED":
        reasons.append("global legal decision is RED in a required jurisdiction")
    return (len(reasons) == 0), reasons


def build_certificate(
    *,
    project: str,
    version: str,
    reference: str | None,
    clean_room_level: str,
    tests: dict[str, int],
    requirement_traceability_percent: float,
    provenance_status: str,
    similarity_result: str,
    jurisdictions: list[dict[str, Any]],
    global_decision: str,
    outstanding_issues: list[str],
    evidence_bundle_location: str,
) -> dict[str, Any]:
    body = {
        "schema_version": "1.0.0",
        "project": project,
        "version": version,
        "clean_room_level": clean_room_level,
        "tests": tests,
        "requirement_traceability_percent": requirement_traceability_percent,
        "provenance_status": provenance_status,
        "similarity_result": similarity_result,
        "jurisdictions": jurisdictions,
        "global_decision": global_decision,
        "outstanding_issues": outstanding_issues,
        "evidence_bundle_location": evidence_bundle_location,
        "generated_utc": utc_now_iso(),
        "disclaimer": CERTIFICATE_DISCLAIMER,
    }
    if reference:
        body["reference"] = reference
    body["evidence_bundle_hash"] = sha256_json({k: v for k, v in body.items() if k != "evidence_bundle_hash"})

    errors = validate(body, "clean-room-certificate.schema.json")
    if errors:
        raise ValueError(f"Built an invalid certificate: {errors}")
    return body


def save_certificate(certificate: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(certificate, f, indent=2, sort_keys=True)


def render_final_report(certificate: dict[str, Any]) -> str:
    lines = [
        "# Clean Room Coding -- Final Report",
        "",
        f"**Project:** {certificate['project']}  ",
        f"**Version:** {certificate['version']}  ",
        f"**Reference:** {certificate.get('reference', '(not recorded)')}  ",
        f"**Clean-room level:** {certificate['clean_room_level']}  ",
        f"**Generated (UTC):** {certificate['generated_utc']}",
        "",
        "## Functional coverage",
        f"- Requirement traceability: {certificate['requirement_traceability_percent']}%",
        f"- Tests: {certificate['tests']}",
        "",
        "## Provenance & similarity",
        f"- Provenance status: {certificate['provenance_status']}",
        f"- Similarity result: {certificate['similarity_result']}",
        "",
        "## Jurisdictions",
        "",
        "| Jurisdiction | Decision | Required market |",
        "|---|---|---|",
    ]
    for j in certificate["jurisdictions"]:
        lines.append(f"| {j['jurisdiction']} | {j['decision_state']} | {j.get('required_market', False)} |")
    lines += [
        "",
        f"## Global decision: {certificate['global_decision']}",
        "",
        "## Outstanding issues",
    ]
    if certificate["outstanding_issues"]:
        lines += [f"- {issue}" for issue in certificate["outstanding_issues"]]
    else:
        lines.append("- None recorded.")
    lines += [
        "",
        f"**Evidence bundle:** `{certificate['evidence_bundle_hash']}` at {certificate['evidence_bundle_location']}",
        "",
        "---",
        "",
        f"> {certificate['disclaimer']}",
        "",
    ]
    return "\n".join(lines)
