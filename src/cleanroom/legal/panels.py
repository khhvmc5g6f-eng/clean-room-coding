"""Parts XLV-LI: jurisdiction-specific legal panels, adversarial counsel and
judicial review -- as PROMPT TEMPLATES and DETERMINISTIC AGGREGATION, not as
an LLM implementation baked into this library.

*** SIMULATED ROLES, NOT REAL LAWYERS OR JUDGES. *** Every prompt this
module builds must be answered by whatever LLM orchestration the caller
uses (Claude Code, another agent harness, or a human reading it directly);
this module never calls an LLM itself (Part LXV: provider abstraction --
Claude is the primary target, but nothing here is hard-wired to it). What
IS implemented deterministically here is `aggregate_jurisdiction_decision`,
which combines whatever findings exist into a single decision_state using a
fixed, auditable rule (Part LIV) that can never round UNKNOWN or AMBER
findings up to an unconditional GREEN.
"""

from __future__ import annotations

from typing import Any

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


def global_decision(jurisdiction_decisions: dict[str, str], required_markets: list[str]) -> str:
    """Part LV: do not average jurisdictions. A RED in a required market
    cannot be smoothed over by GREEN elsewhere. A required market with no
    recorded decision at all is treated as AMBER (unresolved), not GREEN."""
    required_states = [jurisdiction_decisions.get(m, "AMBER") for m in required_markets] or list(
        jurisdiction_decisions.values()
    ) or ["AMBER"]
    worst = max(required_states, key=lambda s: DECISION_RANK.get(s, 2))
    return _normalise(worst)
