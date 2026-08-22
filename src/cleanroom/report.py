"""Parts LVI, LXXXV, XCIII: the release policy engine, CLEAN_ROOM_CERTIFICATE.json,
and the human-readable final report (Markdown + colour-coded HTML).
"""

from __future__ import annotations

import html
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

_DECISION_ORDER = {"RED": 0, "AMBER": 1, "UNKNOWN": 1, "GREEN_WITH_CONDITIONS": 2, "GREEN": 3}
_DECISION_COLOUR = {
    "RED": "#c0392b", "AMBER": "#b8860b", "UNKNOWN": "#7f8c8d",
    "GREEN_WITH_CONDITIONS": "#2f855a", "GREEN": "#1e7d32",
}


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
    open_blocking_remediation: int = 0,
    panel_diversity_gate: bool = True,
    require_panel_diversity_gate: bool = False,
    panel_diversity_reasons: list[str] | None = None,
) -> tuple[bool, list[str]]:
    """Part LVI. Every requested gate must PASS; a RED in a required
    jurisdiction blocks release even if every technical gate is green
    (Part LV: do not average jurisdiction results). An open blocking
    remediation task (a RED legal finding or a material/suspicious
    similarity finding routed back to the implementation team via
    `cleanroom remediate`) blocks release unconditionally -- there is no
    config flag to disable this one, since it is the actual enforcement
    point for "does a flagged concern get sent back to be recoded".

    `panel_diversity_gate`/`require_panel_diversity_gate` are opt-in
    (default `require_panel_diversity_gate=False`, matching every finding
    that has EVER had a panel_adjudication recorded before this option
    existed): `judge-adjudicate` already computed and reported whether
    the configured `panel_size`/`panel_diversity_required` were satisfied,
    but nothing previously read that back at release time -- a project
    could configure real panel requirements and have them silently
    ignored. Set only when a caller actually wants that enforced."""
    reasons = []
    if require_technical_gate and not technical_gate:
        reasons.append("technical_gate did not pass")
    if require_provenance_gate and not provenance_gate:
        reasons.append("provenance_gate did not pass")
    if require_contamination_gate and not contamination_gate:
        reasons.append("contamination_gate did not pass")
    if block_on_red_required_jurisdiction and global_decision == "RED":
        reasons.append("global legal decision is RED in a required jurisdiction")
    if open_blocking_remediation > 0:
        reasons.append(
            f"{open_blocking_remediation} blocking remediation task(s) are still open -- "
            "run 'cleanroom remediate' after fixing them, or override with sign-off"
        )
    if require_panel_diversity_gate and not panel_diversity_gate:
        detail = f": {'; '.join(panel_diversity_reasons)}" if panel_diversity_reasons else ""
        reasons.append(f"panel_diversity_gate did not pass{detail}")
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
    remediation: dict[str, int] | None = None,
    project_summary: dict[str, Any] | None = None,
    phases_completed: list[str] | None = None,
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
    if remediation:
        body["remediation"] = remediation
    if project_summary:
        body["project_summary"] = project_summary
    if phases_completed:
        body["phases_completed"] = phases_completed
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
    ]
    summary = certificate.get("project_summary") or {}
    if summary:
        lines += ["## What it started with", ""]
        if summary.get("reference_summary"):
            lines.append(f"- Reference: {summary['reference_summary']}")
        if summary.get("intended_output_licence"):
            lines.append(f"- Intended output licence: {summary['intended_output_licence']}")
        if summary.get("distribution_model"):
            lines.append(f"- Distribution model: {', '.join(summary['distribution_model'])}")
        if summary.get("target_markets"):
            lines.append(f"- Target markets: {', '.join(summary['target_markets'])}")
        lines.append("")

    if certificate.get("phases_completed"):
        lines += ["## What it did", "", ", ".join(certificate["phases_completed"]), ""]

    lines += [
        "## Functional coverage",
        f"- Requirement traceability: {certificate['requirement_traceability_percent']}%",
        f"- Tests: {certificate['tests']}",
        "",
        "## Provenance & similarity",
        f"- Provenance status: {certificate['provenance_status']}",
        f"- Similarity result: {certificate['similarity_result']}",
        "",
    ]

    remediation = certificate.get("remediation")
    if remediation:
        lines += [
            "## Remediation (legal/similarity findings sent back for recoding)",
            f"- Open, blocking release: {remediation.get('open_blocking', 0)}",
            f"- Open, review required: {remediation.get('open_review_required', 0)}",
            f"- Resolved by re-scan (actually fixed): {remediation.get('resolved_by_rescan', 0)}",
            f"- Resolved by human override (risk accepted, not fixed): {remediation.get('resolved_by_override', 0)}",
            "",
        ]

    lines += [
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


def _chip(state: str) -> str:
    colour = _DECISION_COLOUR.get(state, "#7f8c8d")
    return f'<span class="chip" style="background:{colour}">{html.escape(state)}</span>'


def render_html_report(certificate: dict[str, Any]) -> str:
    """A self-contained, colour-coded HTML report -- no external assets, no
    JS required to read it. Works as a standalone file (`cleanroom report
    --html`) and is the basis for the Artifact preview. Colour is
    supplementary to text, never the only signal (the state name is always
    printed alongside the chip colour)."""
    c = certificate
    summary = c.get("project_summary") or {}
    remediation = c.get("remediation") or {}

    rows_jurisdiction = "\n".join(
        f"<tr><td>{html.escape(j['jurisdiction'])}</td><td>{_chip(j['decision_state'])}</td>"
        f"<td>{'Yes' if j.get('required_market') else 'No'}</td></tr>"
        for j in c["jurisdictions"]
    ) or '<tr><td colspan="3">No jurisdictions resolved yet.</td></tr>'

    outstanding = "".join(f"<li>{html.escape(i)}</li>" for i in c["outstanding_issues"]) or "<li>None recorded.</li>"

    phases = "".join(f"<span class='phase-pill'>{html.escape(p)}</span>" for p in c.get("phases_completed", [])) or "<em>none recorded</em>"

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Clean Room Report — {html.escape(c['project'])}</title>
<style>
  :root {{
    --bg: #ffffff; --fg: #1a1a1a; --muted: #5b5b5b; --card: #f6f6f7; --border: #e2e2e2;
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{ --bg: #14161a; --fg: #eef0f2; --muted: #a2a8b1; --card: #1d2025; --border: #2c3036; }}
  }}
  body {{ background: var(--bg); color: var(--fg); font-family: -apple-system, Segoe UI, Roboto, sans-serif; margin: 0; padding: 2rem; line-height: 1.5; }}
  .container {{ max-width: 880px; margin: 0 auto; }}
  h1 {{ font-size: 1.6rem; margin-bottom: 0.2rem; }}
  .meta {{ color: var(--muted); font-size: 0.9rem; margin-bottom: 1.5rem; }}
  .card {{ background: var(--card); border: 1px solid var(--border); border-radius: 10px; padding: 1.1rem 1.3rem; margin-bottom: 1.2rem; }}
  .card h2 {{ font-size: 1.05rem; margin: 0 0 0.6rem 0; }}
  table {{ width: 100%; border-collapse: collapse; }}
  th, td {{ text-align: left; padding: 0.4rem 0.5rem; border-bottom: 1px solid var(--border); font-size: 0.92rem; }}
  .chip {{ display: inline-block; color: white; font-weight: 600; font-size: 0.78rem; padding: 0.15rem 0.55rem; border-radius: 999px; letter-spacing: 0.02em; }}
  .global-decision {{ font-size: 1.4rem; margin: 0.3rem 0; }}
  .phase-pill {{ display: inline-block; background: var(--border); border-radius: 6px; padding: 0.15rem 0.5rem; margin: 0.15rem 0.25rem 0.15rem 0; font-size: 0.82rem; }}
  .disclaimer {{ font-size: 0.82rem; color: var(--muted); border-top: 1px solid var(--border); padding-top: 1rem; margin-top: 1.5rem; }}
  ul {{ margin: 0.3rem 0 0 0; padding-left: 1.2rem; }}
</style>
</head>
<body>
<div class="container">
  <h1>Clean Room Coding — Final Report</h1>
  <div class="meta">{html.escape(c['project'])} · v{html.escape(c['version'])} · clean-room level {html.escape(c['clean_room_level'])} · generated {html.escape(c['generated_utc'])}</div>

  <div class="card">
    <h2>Global decision</h2>
    <div class="global-decision">{_chip(c['global_decision'])}</div>
  </div>

  <div class="card">
    <h2>What it started with</h2>
    <ul>
      <li>Reference: {html.escape(summary.get('reference_summary', '(not recorded)'))}</li>
      <li>Intended output licence: {html.escape(summary.get('intended_output_licence', '(not recorded)'))}</li>
      <li>Distribution model: {html.escape(', '.join(summary.get('distribution_model', [])) or '(not recorded)')}</li>
      <li>Target markets: {html.escape(', '.join(summary.get('target_markets', [])) or '(not recorded)')}</li>
    </ul>
  </div>

  <div class="card">
    <h2>What it did</h2>
    {phases}
  </div>

  <div class="card">
    <h2>Functional coverage &amp; testing</h2>
    <ul>
      <li>Requirement traceability: {c['requirement_traceability_percent']}%</li>
      <li>Tests: {html.escape(str(c['tests']))}</li>
      <li>Provenance status: {html.escape(c['provenance_status'])}</li>
      <li>Similarity result: {html.escape(c['similarity_result'])}</li>
    </ul>
  </div>

  <div class="card">
    <h2>Remediation (findings sent back to be recoded)</h2>
    <ul>
      <li>Open, blocking release: <strong>{remediation.get('open_blocking', 0)}</strong></li>
      <li>Open, review required: {remediation.get('open_review_required', 0)}</li>
      <li>Resolved by re-scan (actually fixed): {remediation.get('resolved_by_rescan', 0)}</li>
      <li>Resolved by human override (risk knowingly accepted): {remediation.get('resolved_by_override', 0)}</li>
    </ul>
  </div>

  <div class="card">
    <h2>Jurisdictions</h2>
    <table>
      <tr><th>Jurisdiction</th><th>Decision</th><th>Required market</th></tr>
      {rows_jurisdiction}
    </table>
  </div>

  <div class="card">
    <h2>Outstanding issues</h2>
    <ul>{outstanding}</ul>
  </div>

  <div class="card">
    <h2>Evidence bundle</h2>
    <code>{html.escape(c['evidence_bundle_hash'])}</code><br>
    <span style="color:var(--muted)">{html.escape(c['evidence_bundle_location'])}</span>
  </div>

  <div class="disclaimer">{html.escape(c['disclaimer'])}</div>
</div>
</body>
</html>
"""
