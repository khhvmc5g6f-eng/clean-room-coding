"""Part XLIV: the legal issue engine.

*** THIS MODULE DOES NOT GIVE LEGAL ADVICE. *** See docs/legal-disclaimer.md.

It separates "Is this legal?" into the 18 distinct questions Part XLIV
lists, and answers each ONLY from facts the rest of the engine has already
computed deterministically (licence findings, sanitisation results, the
isolation test, similarity findings, jurisdiction tiers). Where no such
fact exists, the finding is UNKNOWN with confidence "insufficient_evidence"
-- never coerced to GREEN for a tidy report (Part LXVIII).

Every finding is a heuristic triage signal for a human legal reviewer, not
a conclusion. `reviewer` is always a simulated-panel identifier unless a
human has overridden it via `human_override`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

ISSUES = [
    "lawful_access",
    "contractual_permissions",
    "copyright_subsistence",
    "protected_expression",
    "copying",
    "substantiality",
    "permitted_acts",
    "interoperability_provisions",
    "licence_obligations",
    "derivative_work_question",
    "linking",
    "distribution",
    "saas_network_provision",
    "patent_risk",
    "trademark_risk",
    "database_rights",
    "confidentiality",
    "trade_secrets",
]


@dataclass
class CaseBundle:
    """Deterministic facts gathered by the rest of the engine, passed into
    the legal issue engine. Every field is Optional -- absence means "not
    yet established", not "no".
    """

    access_authority: str | None = None  # public | licensed | contractual | unknown
    licence_findings: list[dict[str, Any]] | None = None
    sanitisation_blocked: bool | None = None
    isolation_test_passed: bool | None = None
    similarity_findings: list[dict[str, Any]] | None = None
    output_distribution_model: list[str] | None = None
    reference_licence_ids: list[str] | None = None
    jurisdiction: str = "unspecified"


def _finding(
    issue: str,
    jurisdiction: str,
    decision_state: str,
    finding: str,
    evidence: list[str],
    confidence: str,
    *,
    alternative_explanation: str = "",
) -> dict[str, Any]:
    return {
        "issue": issue,
        "jurisdiction": jurisdiction,
        "decision_state": decision_state,
        "finding": finding,
        "evidence": evidence,
        "confidence": confidence,
        "alternative_explanation": alternative_explanation,
        "reviewer": "simulated-legal-issue-engine-v0.1",
    }


def _lawful_access(bundle: CaseBundle) -> dict[str, Any]:
    if bundle.access_authority is None or bundle.access_authority == "unknown":
        return _finding(
            "lawful_access", bundle.jurisdiction, "UNKNOWN",
            "Access authority for the reference material has not been established.",
            [], "insufficient_evidence",
            alternative_explanation="Run 'cleanroom intake' and complete the ACCESS_AND_AUTHORITY_REPORT.",
        )
    if bundle.access_authority == "public":
        return _finding(
            "lawful_access", bundle.jurisdiction, "GREEN_WITH_CONDITIONS",
            "Reference material was declared publicly accessible.",
            ["intake.access_authority = public"], "medium",
            alternative_explanation="Public accessibility does not by itself grant contractual permission to reverse engineer or benchmark -- see 'contractual_permissions'.",
        )
    return _finding(
        "lawful_access", bundle.jurisdiction, "AMBER",
        f"Access authority declared as '{bundle.access_authority}'; underlying terms have not been independently verified by this tool.",
        [f"intake.access_authority = {bundle.access_authority}"], "low",
    )


def _copyright_subsistence(bundle: CaseBundle) -> dict[str, Any]:
    if not bundle.licence_findings:
        return _finding(
            "copyright_subsistence", bundle.jurisdiction, "UNKNOWN",
            "No licence discovery has been run against the reference material.",
            [], "insufficient_evidence",
        )
    concluded = [f for f in bundle.licence_findings if f.get("concluded")]
    if concluded:
        return _finding(
            "copyright_subsistence", bundle.jurisdiction, "GREEN_WITH_CONDITIONS",
            "Reference material carries at least one concluded licence, implying an asserted copyright interest exists.",
            [f"{len(concluded)} of {len(bundle.licence_findings)} scanned locations have a concluded licence"],
            "medium",
        )
    return _finding(
        "copyright_subsistence", bundle.jurisdiction, "AMBER",
        "Licence discovery ran but reached no concluded licence for any scanned location.",
        [f"{len(bundle.licence_findings)} locations scanned, 0 concluded"], "low",
        alternative_explanation="Absence of a declared licence does not mean absence of copyright; most jurisdictions grant copyright automatically on creation.",
    )


def _permitted_acts(bundle: CaseBundle) -> dict[str, Any]:
    if bundle.isolation_test_passed is None:
        return _finding(
            "permitted_acts", bundle.jurisdiction, "UNKNOWN",
            "The technical isolation self-test has not been run.",
            [], "insufficient_evidence",
        )
    if bundle.isolation_test_passed:
        return _finding(
            "permitted_acts", bundle.jurisdiction, "GREEN_WITH_CONDITIONS",
            "Technical isolation between Zone R and implementation-scoped agents was verified (DENIED as expected).",
            ["isolation_test_passed = true"], "medium",
        )
    return _finding(
        "permitted_acts", bundle.jurisdiction, "RED",
        "The technical isolation self-test FAILED: an implementation-scoped agent was not denied access to Zone R.",
        ["isolation_test_passed = false"], "high",
    )


def _copying_and_substantiality(bundle: CaseBundle) -> list[dict[str, Any]]:
    if bundle.similarity_findings is None:
        return [
            _finding("copying", bundle.jurisdiction, "UNKNOWN", "Similarity analysis has not been run.", [], "insufficient_evidence"),
            _finding("substantiality", bundle.jurisdiction, "UNKNOWN", "Similarity analysis has not been run.", [], "insufficient_evidence"),
        ]
    material = [f for f in bundle.similarity_findings if f.get("classification") == "material"]
    suspicious = [f for f in bundle.similarity_findings if f.get("classification") == "suspicious"]
    if material:
        copying = _finding(
            "copying", bundle.jurisdiction, "RED",
            f"{len(material)} similarity finding(s) classified MATERIAL by human/panel review.",
            [f["id"] for f in material], "high",
        )
    elif suspicious:
        copying = _finding(
            "copying", bundle.jurisdiction, "AMBER",
            f"{len(suspicious)} similarity finding(s) classified SUSPICIOUS and not yet reviewed.",
            [f["id"] for f in suspicious], "medium",
            alternative_explanation="Suspicious findings require human/panel review to rule in or out before this can move to GREEN or RED.",
        )
    else:
        copying = _finding(
            "copying", bundle.jurisdiction, "GREEN_WITH_CONDITIONS",
            "No suspicious or material similarity findings are open.",
            [f["id"] for f in bundle.similarity_findings], "medium",
        )
    substantiality = _finding(
        "substantiality", bundle.jurisdiction, copying["decision_state"],
        "Substantiality is assessed alongside copying pending qualified review of what, specifically, was allegedly reproduced.",
        copying["evidence"], copying["confidence"],
    )
    return [copying, substantiality]


def _saas_network_provision(bundle: CaseBundle) -> dict[str, Any]:
    if bundle.output_distribution_model is None:
        return _finding(
            "saas_network_provision", bundle.jurisdiction, "UNKNOWN",
            "Intended distribution model is not configured.",
            [], "insufficient_evidence",
        )
    is_saas = "saas" in bundle.output_distribution_model
    reference_has_agpl = any(
        "agpl" in (rid or "").lower() for rid in (bundle.reference_licence_ids or [])
    )
    if is_saas and reference_has_agpl:
        return _finding(
            "saas_network_provision", bundle.jurisdiction, "RED",
            "Output is distributed as SaaS and a reference/dependency licence includes AGPL, which specifically triggers obligations on network use (AGPL-3.0 s.13).",
            ["distribution_model includes saas", "reference_licence_ids includes an AGPL identifier"], "high",
        )
    if is_saas:
        return _finding(
            "saas_network_provision", bundle.jurisdiction, "GREEN_WITH_CONDITIONS",
            "Output is distributed as SaaS; no AGPL reference/dependency licence detected.",
            ["distribution_model includes saas"], "medium",
        )
    return _finding(
        "saas_network_provision", bundle.jurisdiction, "GREEN_WITH_CONDITIONS",
        "Output is not distributed as SaaS; network-copyleft triggers are not engaged.",
        ["distribution_model does not include saas"], "medium",
    )


# Issues not yet backed by a specific heuristic in v0.1 (patents, trademarks,
# database_rights, confidentiality, trade_secrets, linking, licence_obligations,
# derivative_work_question, contractual_permissions, distribution,
# interoperability_provisions, protected_expression) are honestly reported
# UNKNOWN rather than simulated with a fake heuristic. See ROADMAP.md.
_HEURISTICS: dict[str, Callable[[CaseBundle], list[dict[str, Any]]]] = {
    "lawful_access": lambda b: [_lawful_access(b)],
    "copyright_subsistence": lambda b: [_copyright_subsistence(b)],
    "permitted_acts": lambda b: [_permitted_acts(b)],
    "copying": _copying_and_substantiality,
    "saas_network_provision": lambda b: [_saas_network_provision(b)],
}


def run(bundle: CaseBundle) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    covered: set[str] = set()
    for issue, fn in _HEURISTICS.items():
        results = fn(bundle)
        for r in results:
            covered.add(r["issue"])
            findings.append(r)
    for issue in ISSUES:
        if issue in covered:
            continue
        findings.append(
            _finding(
                issue, bundle.jurisdiction, "UNKNOWN",
                "No deterministic heuristic is implemented for this issue in v0.1 -- requires qualified legal review.",
                [], "insufficient_evidence",
            )
        )
    return findings
