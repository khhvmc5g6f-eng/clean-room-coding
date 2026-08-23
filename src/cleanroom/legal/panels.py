"""Parts XLV-LI: jurisdiction-specific legal panels, adversarial counsel and
judicial review -- as PROMPT TEMPLATES and DETERMINISTIC AGGREGATION, not as
an LLM implementation baked into this library.

*** SIMULATED ROLES, NOT REAL LAWYERS OR JUDGES. *** Every prompt this
module builds must be answered by whatever LLM orchestration the caller
uses (Claude Code, another agent harness, or a human reading it directly);
this module never calls an LLM itself (Part LXV: provider abstraction --
Claude is the primary target, but nothing here is hard-wired to it).
`orchestration/harness.py` is the first real implementation of "whatever
LLM orchestration the caller uses" -- it calls a real, pluggable
`AgentBackend` and feeds the response back through `merge_panel_answers`
below, the same merge `cli.py`'s `judge-adjudicate` command performs by
hand. What IS implemented deterministically here is
`aggregate_jurisdiction_decision`, which combines whatever findings exist
into a single decision_state using a fixed, auditable rule (Part LIV)
that can never round UNKNOWN or AMBER findings up to an unconditional
GREEN.
"""

from __future__ import annotations

from typing import Any

from cleanroom import schema_registry
from cleanroom.jurisdiction import resolver as jurisdiction_resolver
from cleanroom.util import utc_now_iso

DECISION_RANK = {"RED": 3, "AMBER": 2, "UNKNOWN": 2, "GREEN_WITH_CONDITIONS": 1, "GREEN": 0}


def build_applicant_brief_prompt(jurisdiction_pack: dict[str, Any], findings: list[dict[str, Any]]) -> str:
    return (
        "You are Applicant Counsel in a simulated review (Part XLIX). You are not a real "
        "lawyer and must say so if asked. Construct the STRONGEST PLAUSIBLE argument that this "
        "implementation is independently created and licence-compliant, using ONLY the evidence "
        "below. Do not invent facts not present in the evidence.\n\n"
        f"Jurisdiction: {jurisdiction_pack.get('jurisdiction_id')}\n"
        f"Governing statutes: {[s['name'] for s in jurisdiction_pack.get('governing_statutes', [])]}\n"
        f"Leading case law: {[c['citation'] for c in jurisdiction_pack.get('leading_case_law', [])]}\n\n"
        f"Evidence (legal-finding records):\n{findings}\n\n"
        "Output: a structured brief citing which findings and which authorities from the "
        "jurisdiction pack support independence/compliance, and explicitly flag any evidence "
        "that cuts against your own position (you must not omit unfavourable evidence)."
    )


def build_challenger_brief_prompt(jurisdiction_pack: dict[str, Any], findings: list[dict[str, Any]]) -> str:
    return (
        "You are Challenger Counsel, instructed as though by the ORIGINAL RIGHTS HOLDER (Part "
        "XLIX-L). You are not a real lawyer and must say so if asked. Identify the strongest "
        "reasonable allegations of copying, licence avoidance, contamination, derivative-work "
        "status, breach of contract, or IP infringement, using ONLY the evidence below plus "
        "what a rights holder's own counsel could reasonably infer from it. Do not invent facts.\n\n"
        f"Jurisdiction: {jurisdiction_pack.get('jurisdiction_id')}\n"
        f"Governing statutes: {[s['name'] for s in jurisdiction_pack.get('governing_statutes', [])]}\n"
        f"Leading case law: {[c['citation'] for c in jurisdiction_pack.get('leading_case_law', [])]}\n\n"
        f"Evidence (legal-finding records):\n{findings}\n\n"
        "Output: a structured brief citing which findings and which authorities from the "
        "jurisdiction pack support your challenge, ranked by strength, and what ADDITIONAL "
        "evidence you would seek (Part L: rights-holder evidential stress test)."
    )


def build_judicial_review_prompt(
    jurisdiction_pack: dict[str, Any],
    applicant_brief: str,
    challenger_brief: str,
    findings: list[dict[str, Any]],
) -> str:
    role_title = jurisdiction_pack.get("court_terminology", {}).get(
        "simulated_judicial_role_title", "Simulated Judicial Reviewer"
    )
    return (
        f"You are acting as a {role_title} (Part XLVI) -- a SIMULATION for engineering triage, "
        "NOT a real judge, and you must say so if asked. Your task is to identify weaknesses, "
        "not to approve release (Part XLVIII). You are not sycophantic: you must actively "
        "challenge both briefs below.\n\n"
        f"--- APPLICANT COUNSEL BRIEF ---\n{applicant_brief}\n\n"
        f"--- CHALLENGER COUNSEL BRIEF ---\n{challenger_brief}\n\n"
        f"--- UNDERLYING EVIDENCE (legal-finding records) ---\n{findings}\n\n"
        "Produce, for each issue: applicable jurisdiction and legal framework, facts established "
        "vs. uncertain, an assessment of the similarities and their explanations, outstanding "
        "rights questions, and a decision_state (GREEN | GREEN_WITH_CONDITIONS | AMBER | RED | "
        "UNKNOWN) per Part LIV, with your reasoning. State plainly wherever the correct answer "
        "requires qualified human legal counsel rather than this simulation (Part LI)."
    )


def _normalise(state: str) -> str:
    """Part LIV only defines four jurisdiction/global-level decision states
    (GREEN, GREEN_WITH_CONDITIONS, AMBER, RED). A per-finding UNKNOWN
    (insufficient evidence) is real uncertainty, which is exactly what
    AMBER means at the jurisdiction level -- so UNKNOWN folds into AMBER
    here, and a bare GREEN is never produced by automated aggregation
    (only an explicit human sign-off may record an unconditional GREEN)."""
    if state in ("UNKNOWN", "GREEN"):
        return "AMBER" if state == "UNKNOWN" else "GREEN_WITH_CONDITIONS"
    return state


def aggregate_jurisdiction_decision(findings: list[dict[str, Any]]) -> str:
    """Part LIV/LV: the worst decision_state among the findings wins."""
    if not findings:
        return "AMBER"
    worst = max(findings, key=lambda f: DECISION_RANK.get(f["decision_state"], 2))
    return _normalise(worst["decision_state"])


def aggregate_panel_decision(panel_adjudications: list[dict[str, Any]]) -> str:
    """Parts XLV-LI, LIV: when `panel_size` > 1, a single finding can carry
    more than one independent judicial-review panel member's adjudication
    (`panel_adjudications`, see legal-finding.schema.json). The SAME
    worst-wins, never-round-up rule `aggregate_jurisdiction_decision`
    already applies across findings is applied here across panel members
    -- a single dissenting RED/AMBER panel member is never smoothed over
    by other members' more favourable view, matching this project's
    standing rule against turning disagreement into a tidy consensus."""
    if not panel_adjudications:
        return "AMBER"
    worst = max(panel_adjudications, key=lambda a: DECISION_RANK.get(a["decision_state"], 2))
    return _normalise(worst["decision_state"])


def panel_completeness_across_findings(
    findings: list[dict[str, Any]], *, panel_size_required: int, diversity_required: bool,
) -> tuple[bool, list[str]]:
    """`judge_adjudicate` (cli.py) already computes panel_size/diversity
    satisfaction per CALL, for whichever finding(s) that one submission
    touched -- this is the same check applied project-wide, across every
    finding that has EVER had a panel_adjudication recorded, so a release
    gate can ask "is the judicial panel actually complete everywhere it
    was used" in one pass.

    Deliberately narrow scope: a finding with NO panel_adjudications at
    all is not judged here -- this does not make judicial review itself
    mandatory (that stays a separate workflow choice via `cleanroom
    judge`/`judge-adjudicate`), it only checks that wherever panel review
    WAS used, it's genuinely complete rather than left half-finished.

    Returns (satisfied, reasons) -- reasons names each finding that falls
    short and why, never just a bare boolean with no way to act on it."""
    reasons: list[str] = []
    for finding in findings:
        adjudications = finding.get("panel_adjudications") or []
        if not adjudications:
            continue
        member_ids = {a["panel_member_id"] for a in adjudications}
        if len(member_ids) < panel_size_required:
            reasons.append(
                f"{finding['issue']} ({finding.get('jurisdiction')}): {len(member_ids)} panel member(s) recorded, "
                f"{panel_size_required} required"
            )
            continue
        if diversity_required:
            providers = {a.get("model_provider") for a in adjudications} - {None}
            if len(providers) <= 1:
                reasons.append(
                    f"{finding['issue']} ({finding.get('jurisdiction')}): panel_diversity_required is set but only "
                    f"{len(providers)} distinct model_provider(s) recorded across its panel_adjudications"
                )
    return (len(reasons) == 0), reasons


def global_decision(jurisdiction_decisions: dict[str, str], required_markets: list[str]) -> str:
    """Part LV: do not average jurisdictions. A RED in a required market
    cannot be smoothed over by GREEN elsewhere. A required market with no
    recorded decision at all is treated as AMBER (unresolved), not GREEN."""
    required_states = [jurisdiction_decisions.get(m, "AMBER") for m in required_markets] or list(
        jurisdiction_decisions.values()
    ) or ["AMBER"]
    worst = max(required_states, key=lambda s: DECISION_RANK.get(s, 2))
    return _normalise(worst)


def merge_panel_answers(
    findings: list[dict[str, Any]], pack_id: str, panel_member_id: str, answers: list[dict[str, Any]],
    *, model_provider: str | None = None, model_id: str | None = None, submitted_utc: str | None = None,
) -> list[str]:
    """The exact merge `cli.py`'s `judge-adjudicate` command has always
    performed by hand, extracted here so `orchestration/harness.py`'s
    real LLM-backed Council shares one tested implementation with the
    CLI's own manual path, rather than two copies that could drift.
    Mutates `findings` in place (matching prior behaviour) and returns
    the list of issues actually updated.

    No CLI dependency: raises `ValueError` (not `click.ClickException`)
    on an unknown pack id, an answer whose issue matches no finding for
    that pack's markets, or a resulting finding that fails schema
    validation -- callers translate these into whatever error-reporting
    mechanism fits (a `click.ClickException` for the CLI, an honest
    failure entry in the harness's own report for `harness.py`)."""
    markets_for_pack = {
        market for market, mapped_pack_id in jurisdiction_resolver.COUNTRY_TO_PACK.items() if mapped_pack_id == pack_id
    }
    if not markets_for_pack:
        raise ValueError(f"'{pack_id}' is not a known jurisdiction pack id (see jurisdiction/resolver.py's COUNTRY_TO_PACK).")

    now = submitted_utc or utc_now_iso()
    updated_issues: list[str] = []
    for answer in answers:
        matched = False
        for finding in findings:
            if finding["issue"] != answer["issue"] or (finding.get("jurisdiction") or "").lower() not in markets_for_pack:
                continue
            matched = True
            entry = {
                "panel_member_id": panel_member_id,
                "decision_state": answer["decision_state"],
                "reviewer": f"simulated-{pack_id}-judicial-panel",
                "submitted_utc": now,
            }
            for key in ("for_release_argument", "against_release_argument", "adjudication"):
                if answer.get(key):
                    entry[key] = answer[key]
            if model_provider:
                entry["model_provider"] = model_provider
            if model_id:
                entry["model_id"] = model_id
            finding.setdefault("panel_adjudications", [])
            finding["panel_adjudications"] = [
                a for a in finding["panel_adjudications"] if a.get("panel_member_id") != panel_member_id
            ] + [entry]

            worst_state = aggregate_panel_decision(finding["panel_adjudications"])
            worst_entry = max(finding["panel_adjudications"], key=lambda a: DECISION_RANK.get(a["decision_state"], 2))
            finding["decision_state"] = worst_state
            finding["reviewer"] = worst_entry["reviewer"]
            for key in ("for_release_argument", "against_release_argument", "adjudication"):
                if worst_entry.get(key):
                    finding[key] = worst_entry[key]
            updated_issues.append(answer["issue"])
        if not matched:
            raise ValueError(
                f"No legal finding matches issue '{answer['issue']}' for pack '{pack_id}' (checked markets "
                f"{sorted(markets_for_pack)}) -- run 'cleanroom legal' with this project's actual configured markets first."
            )

    for finding in findings:
        errors = schema_registry.validate(finding, "legal-finding.schema.json")
        if errors:
            raise ValueError(f"Refusing to save: adjudicated finding fails schema validation: {errors}")

    return updated_issues


def panel_completeness_for_call(
    findings: list[dict[str, Any]], updated_issues: list[str], *, panel_size_required: int, diversity_required: bool,
) -> dict[str, Any]:
    """The panel_size/diversity satisfaction summary `judge-adjudicate` has
    always reported for the specific issues one call just touched --
    extracted the same way as `merge_panel_answers` so `harness.py` gets
    identical semantics to the CLI, not a re-derived approximation. (See
    `panel_completeness_across_findings` above for the project-wide,
    every-finding-ever-adjudicated version this is NOT -- that one is used
    by `cleanroom release`'s opt-in gate.)"""
    member_ids = {a["panel_member_id"] for f in findings for a in f.get("panel_adjudications", []) if f["issue"] in updated_issues}
    providers_seen = {
        a.get("model_provider") for f in findings for a in f.get("panel_adjudications", []) if f["issue"] in updated_issues
    } - {None}
    diversity_satisfied = (not diversity_required) or len(providers_seen) > 1
    return {
        "panel_size_required": panel_size_required, "panel_members_recorded": len(member_ids),
        "panel_size_satisfied": len(member_ids) >= panel_size_required,
        "diversity_required": diversity_required, "distinct_providers_recorded": sorted(p for p in providers_seen if p),
        "diversity_satisfied": diversity_satisfied,
    }
