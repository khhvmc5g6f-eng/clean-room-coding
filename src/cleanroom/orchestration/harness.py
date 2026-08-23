"""Part LXV, for real: a working orchestration harness.

Every prompt-building module in this project (`legal/panels.py`) has
always deferred to "whatever LLM orchestration the caller uses" -- this
module is the first real implementation of that caller, for the
`AgentBackend` this project actually ships one working implementation of
(`orchestration/backends.py::AnthropicBackend`). It reuses every existing
mechanism rather than reinventing any of it: `AgentRegistry` for identity,
`legal/panels.py`'s prompt templates and `merge_panel_answers` for the
judicial review, the requirement graph and Zone H's own sanitised
documents for what an implementation agent is allowed to see.

Real and cost-incurring (a real LLM API call per prompt) -- never invoked
implicitly by any other command; always an explicit `cleanroom council`/
`cleanroom implement` call.

*** SIMULATED ROLES, NOT REAL LAWYERS, JUDGES, OR ENGINEERS. *** Everything
`run_council_review` produces is exactly as advisory as a human manually
completing `cleanroom judge`'s prompts and submitting them via
`judge-adjudicate` -- this module does not change what those findings mean
or how much weight they carry, only who's answering the prompts.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cleanroom.legal import panels as legal_panels
from cleanroom.orchestration.backends import AgentBackend
from cleanroom.project import Project
from cleanroom.specification.graph import RequirementGraph

_JUDICIAL_OUTPUT_CONTRACT = (
    "\n\n--- OUTPUT FORMAT (required) ---\n"
    "Respond with ONLY a JSON array, no other text before or after it. One object per issue you "
    "actually assessed above, each with exactly these keys:\n"
    '  "issue": the issue name exactly as it appears in the evidence above\n'
    '  "decision_state": one of "GREEN", "GREEN_WITH_CONDITIONS", "AMBER", "RED", "UNKNOWN"\n'
    '  "for_release_argument": your strongest argument favouring release, or ""\n'
    '  "against_release_argument": your strongest argument against release, or ""\n'
    '  "adjudication": your reasoning for the decision_state you chose\n'
)

_IMPLEMENTATION_OUTPUT_CONTRACT = (
    "\n\n--- OUTPUT FORMAT (required) ---\n"
    "Respond with ONLY a JSON array, no other text before or after it. One object per file to "
    "create, each with exactly these keys:\n"
    '  "path": a relative file path (e.g. "sort.py") -- never absolute, never containing "..".\n'
    '  "content": the complete file content as a string.\n'
)


class HarnessError(Exception):
    """A real failure in the harness's own machinery (a malformed/
    unparseable LLM response, an unsafe file path, a merge that failed
    schema validation) -- never silently swallowed or worked around with
    a guessed fallback."""


def _parse_json_array(raw: str, *, what: str) -> list[dict[str, Any]]:
    text = raw.strip()
    # Models frequently wrap JSON in a ```json ... ``` fence despite being
    # told not to -- strip one matching pair if present rather than
    # failing on the single most common real deviation from the contract.
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        if text.rstrip().endswith("```"):
            text = text.rstrip()[: -3]
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as e:
        raise HarnessError(f"Could not parse the model's {what} response as JSON: {e}. Raw response: {raw[:500]!r}") from e
    if not isinstance(parsed, list):
        raise HarnessError(f"The model's {what} response was valid JSON but not a JSON array: {raw[:500]!r}")
    return parsed


def run_council_review(
    project: Project, backend: AgentBackend, *, panel_member_id: str,
    model_provider: str | None = None, model_id: str | None = None,
) -> dict[str, Any]:
    """Real Parts XLV-LI: for every jurisdiction pack convened in
    JURISDICTION_MATRIX.json, build the applicant/challenger/judicial-
    review prompts `legal/panels.py` already defines, send each to a real
    `backend`, and merge the parsed judicial review back into
    evidence/legal-findings.json via the exact same
    `legal_panels.merge_panel_answers` the CLI's `judge-adjudicate`
    command uses by hand.

    Raises `HarnessError` (never fabricates a result) if required
    project state is missing, or if a jurisdiction pack's judicial
    review response can't be parsed/merged -- a partial run's per-pack
    results are still returned in `packs` so a caller can see exactly
    how far it got."""
    from cleanroom.jurisdiction import resolver as jurisdiction_resolver
    from cleanroom.util import utc_now_iso

    matrix_path = project.root / "JURISDICTION_MATRIX.json"
    findings_path = project.root / "evidence" / "legal-findings.json"
    if not matrix_path.is_file() or not findings_path.is_file():
        raise HarnessError("Run 'cleanroom jurisdiction' and 'cleanroom legal' first.")
    matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
    findings = json.loads(findings_path.read_text(encoding="utf-8"))

    packs_result: dict[str, Any] = {}
    for pack_id in matrix["legal_panels_convened"]:
        pack = jurisdiction_resolver.load_pack(pack_id)
        if not pack:
            packs_result[pack_id] = {"error": "no jurisdiction pack found for this id"}
            continue
        pack_findings = [f for f in findings if (f.get("jurisdiction") or "").lower() in {
            m for m, p in jurisdiction_resolver.COUNTRY_TO_PACK.items() if p == pack_id
        }]

        applicant_prompt = legal_panels.build_applicant_brief_prompt(pack, pack_findings)
        applicant_response = backend.complete(system="You are Applicant Counsel in a simulated review.", prompt=applicant_prompt)

        challenger_prompt = legal_panels.build_challenger_brief_prompt(pack, pack_findings)
        challenger_response = backend.complete(system="You are Challenger Counsel in a simulated review.", prompt=challenger_prompt)

        judicial_prompt = legal_panels.build_judicial_review_prompt(pack, applicant_response, challenger_response, pack_findings)
        judicial_response = backend.complete(
            system="You are a simulated judicial reviewer. Follow the required output format exactly.",
            prompt=judicial_prompt + _JUDICIAL_OUTPUT_CONTRACT,
        )

        try:
            answers = _parse_json_array(judicial_response, what=f"judicial review ({pack_id})")
            updated_issues = legal_panels.merge_panel_answers(
                findings, pack_id, panel_member_id, answers, model_provider=model_provider, model_id=model_id,
                submitted_utc=utc_now_iso(),
            )
        except (HarnessError, ValueError) as e:
            packs_result[pack_id] = {
                "error": str(e), "applicant_brief": applicant_response, "challenger_brief": challenger_response,
                "raw_judicial_response": judicial_response,
            }
            continue

        packs_result[pack_id] = {
            "issues_updated": updated_issues, "applicant_brief": applicant_response,
            "challenger_brief": challenger_response,
        }

    findings_path.write_text(json.dumps(findings, indent=2, sort_keys=True), encoding="utf-8")
    return {"panel_member_id": panel_member_id, "packs": packs_result}


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def run_implementation(
    project: Project, backend: AgentBackend, *, agent_id: str,
) -> dict[str, Any]:
    """Real Part XXVI: given a registered implementation agent (already
    created via `cleanroom build`, so it's already been through the
    remediation panel), send it Zone H's real sanitised documents plus
    the requirement graph's real handoff-eligible statements -- NEVER
    anything from Zone R -- and ask it to actually write an
    implementation, source-blind by construction (it is given no
    reference-zone content to have read in the first place, not merely
    blocked from re-reading it).

    Every returned file path is resolved and checked to stay within Zone
    I before anything is written -- a response that tries to escape the
    implementation directory (absolute path, `..` traversal) is rejected
    entirely (`HarnessError`), not silently clamped or partially
    applied."""
    graph = RequirementGraph.load(project.root / "requirements.json")
    eligible = graph.handoff_eligible_nodes()
    if not eligible:
        raise HarnessError("No handoff-eligible requirements found -- run 'cleanroom specify add-requirement' first.")

    zone_h = project.zone_h
    documents = "\n\n".join(
        f"--- {p.relative_to(zone_h)} ---\n{p.read_text(encoding='utf-8', errors='replace')}"
        for p in sorted(zone_h.rglob("*")) if p.is_file() and p.name != "HANDOFF_MANIFEST.json"
    )
    requirements_text = "\n".join(f"- {n['id']}: {n['statement']}" for n in eligible)

    prompt = (
        "Implement the following observable requirements. You have not seen, and must never reference, any "
        "original reference implementation -- work only from the specification below.\n\n"
        f"Requirements:\n{requirements_text}\n\n"
        f"Sanitised specification documents:\n{documents}\n"
        + _IMPLEMENTATION_OUTPUT_CONTRACT
    )
    response = backend.complete(
        system="You are a source-blind implementation engineer. Follow the required output format exactly.",
        prompt=prompt,
    )
    files = _parse_json_array(response, what="implementation")

    zone_i = project.zone_i.resolve()
    written: list[str] = []
    for entry in files:
        rel_path = entry.get("path")
        content = entry.get("content")
        if not isinstance(rel_path, str) or not isinstance(content, str):
            raise HarnessError(f"Malformed file entry from the model (expected string path/content): {entry!r}")
        target = (zone_i / rel_path).resolve()
        if not _is_within(target, zone_i):
            raise HarnessError(f"Refusing to write outside Zone I: model returned path {rel_path!r} -> {target}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        written.append(str(target.relative_to(zone_i)))

    return {"agent_id": agent_id, "files_written": written, "requirements_addressed": [n["id"] for n in eligible]}
