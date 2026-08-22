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

from cleanroom.licence import policy as licence_policy

_COPYLEFT_LEVELS = {"strong", "weak", "delayed_copyleft"}
_DISTRIBUTION_ACTS = {"source", "binary", "library", "container"}  # "saas" is handled separately below

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
    requirement_classifications: dict[str, int] | None = None
    interoperability_permitted_acts: list[Any] | None = None
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


def _licence_obligations(bundle: CaseBundle) -> dict[str, Any]:
    if not bundle.licence_findings:
        return _finding(
            "licence_obligations", bundle.jurisdiction, "UNKNOWN",
            "No licence discovery has been run against the reference material.",
            [], "insufficient_evidence",
            alternative_explanation="Run 'cleanroom licence' first.",
        )
    concluded = sorted({f["concluded"] for f in bundle.licence_findings if f.get("concluded")})
    if not concluded:
        return _finding(
            "licence_obligations", bundle.jurisdiction, "AMBER",
            "Licence discovery ran but reached no concluded licence for any scanned location, so obligations cannot be enumerated.",
            [f"{len(bundle.licence_findings)} location(s) scanned, 0 concluded"], "low",
            alternative_explanation="Absence of a concluded licence does not mean absence of obligations; consult qualified counsel before treating this as low-risk.",
        )
    known_terms: set[str] = set()
    unknown_terms: set[str] = set()
    copyleft_terms: set[str] = set()
    for expr in concluded:
        for term in licence_policy.split_terms(expr):
            pack = licence_policy.load_pack(term)
            if pack is None:
                unknown_terms.add(term)
                continue
            known_terms.add(term)
            if pack.get("copyleft") in _COPYLEFT_LEVELS:
                copyleft_terms.add(term)
    if copyleft_terms:
        return _finding(
            "licence_obligations", bundle.jurisdiction, "AMBER",
            f"{len(copyleft_terms)} concluded licence(s) carry copyleft obligations that likely require action before distribution: {sorted(copyleft_terms)}.",
            [f"concluded licences: {concluded}"], "medium",
            alternative_explanation="See each licence's policy pack (policies/licences/) for the specific key_obligations; this finding does not itself confirm compliance.",
        )
    if unknown_terms:
        return _finding(
            "licence_obligations", bundle.jurisdiction, "AMBER",
            f"Concluded licence term(s) {sorted(unknown_terms)} have no matching policy pack in this installation -- their obligations are unknown to this tool.",
            [f"concluded licences: {concluded}", f"known non-copyleft terms: {sorted(known_terms) or 'none'}"], "low",
            alternative_explanation="Add a policy pack for this licence (policies/licences/) or consult qualified counsel.",
        )
    return _finding(
        "licence_obligations", bundle.jurisdiction, "GREEN_WITH_CONDITIONS",
        f"Concluded licence(s) {sorted(known_terms)} carry only non-copyleft obligations (e.g. attribution/notice preservation) per their policy packs.",
        [f"concluded licences: {concluded}"], "medium",
    )


def _distribution(bundle: CaseBundle) -> dict[str, Any]:
    if bundle.output_distribution_model is None:
        return _finding(
            "distribution", bundle.jurisdiction, "UNKNOWN",
            "Intended distribution model for the implementation has not been configured.",
            [], "insufficient_evidence",
            alternative_explanation="Configure .cleanroom.yml's implementation.distribution_model (e.g. source, binary, library, container, saas).",
        )
    acts = set(bundle.output_distribution_model) & _DISTRIBUTION_ACTS
    if not acts:
        return _finding(
            "distribution", bundle.jurisdiction, "GREEN_WITH_CONDITIONS",
            "Configured distribution model includes no source/binary/library/container distribution act (network/SaaS provision, if configured, is assessed separately under 'saas_network_provision').",
            [f"output_distribution_model = {bundle.output_distribution_model}"], "medium",
        )
    triggered: set[str] = set()
    for rid in bundle.reference_licence_ids or []:
        for term in licence_policy.split_terms(rid or ""):
            pack = licence_policy.load_pack(term)
            if pack and pack.get("copyleft") in _COPYLEFT_LEVELS and acts & set(pack.get("distribution_triggers", [])):
                triggered.add(term)
    if triggered:
        return _finding(
            "distribution", bundle.jurisdiction, "AMBER",
            f"Configured distribution act(s) {sorted(acts)} overlap with the copyleft distribution triggers of reference/dependency licence(s) {sorted(triggered)}; obligations under those licences may apply to the distributed work.",
            [f"output_distribution_model = {bundle.output_distribution_model}", f"reference_licence_ids = {bundle.reference_licence_ids}"],
            "medium",
            alternative_explanation="This flags an overlap only; whether the distributed work is actually a derivative/combined work under that licence is a separate, human question (see 'derivative_work_question').",
        )
    return _finding(
        "distribution", bundle.jurisdiction, "GREEN_WITH_CONDITIONS",
        f"Configured distribution act(s) {sorted(acts)} do not overlap with any detected reference/dependency licence's copyleft distribution triggers.",
        [f"output_distribution_model = {bundle.output_distribution_model}"], "medium",
    )


def _derivative_work_question(bundle: CaseBundle) -> dict[str, Any]:
    if bundle.requirement_classifications is None:
        return _finding(
            "derivative_work_question", bundle.jurisdiction, "UNKNOWN",
            "Requirement graph classification has not been supplied to the engine.",
            [], "insufficient_evidence",
            alternative_explanation="Run 'cleanroom specify report' and populate the requirement graph before this can be assessed.",
        )
    source_count = bundle.requirement_classifications.get("source_implementation_detail", 0)
    observable_count = bundle.requirement_classifications.get("observable_requirement", 0)
    material_findings = [
        f for f in (bundle.similarity_findings or []) if f.get("classification") == "material"
    ]
    if material_findings:
        return _finding(
            "derivative_work_question", bundle.jurisdiction, "RED",
            "A similarity finding classified MATERIAL is open; the implementation is at meaningful risk of being found a derivative work until that finding is resolved.",
            [f["id"] for f in material_findings], "high",
        )
    if source_count > 0:
        return _finding(
            "derivative_work_question", bundle.jurisdiction, "AMBER",
            f"{source_count} requirement node(s) are still classified 'source_implementation_detail' (excluded from handoff by design) -- until these are resolved into observable requirements or removed, the clean-room record does not yet support an independent-creation position.",
            [f"source_implementation_detail count = {source_count}"], "medium",
            alternative_explanation="This measures process hygiene, not the legal test for a derivative work, which also depends on jurisdiction-specific idea/expression analysis (see 'protected_expression', UNKNOWN in v0.1).",
        )
    if observable_count == 0:
        return _finding(
            "derivative_work_question", bundle.jurisdiction, "UNKNOWN",
            "No requirement nodes have been classified yet.",
            [], "insufficient_evidence",
        )
    return _finding(
        "derivative_work_question", bundle.jurisdiction, "GREEN_WITH_CONDITIONS",
        f"All {observable_count} classified requirement node(s) are 'observable_requirement' (handoff-eligible) and no MATERIAL similarity finding is open -- process evidence is consistent with an independent-creation position, though this does not itself decide the legal question.",
        [f"observable_requirement count = {observable_count}"], "medium",
        alternative_explanation="A full derivative-work determination also requires jurisdiction-specific idea/expression-merger analysis by qualified counsel.",
    )


def _interoperability_provisions(bundle: CaseBundle) -> dict[str, Any]:
    if bundle.interoperability_permitted_acts is None:
        return _finding(
            "interoperability_provisions", bundle.jurisdiction, "UNKNOWN",
            "No jurisdiction pack is available (or was loaded) for this market, so its documented interoperability-permitted-acts are unknown.",
            [], "insufficient_evidence",
        )
    if not bundle.interoperability_permitted_acts:
        return _finding(
            "interoperability_provisions", bundle.jurisdiction, "AMBER",
            "The jurisdiction pack for this market documents no interoperability-permitted-acts entries -- do not assume a statutory interoperability exception exists here.",
            [], "low",
            alternative_explanation="Consult qualified local counsel; absence from this pack is a gap in this tool's data, not proof no exception exists.",
        )
    return _finding(
        "interoperability_provisions", bundle.jurisdiction, "GREEN_WITH_CONDITIONS",
        f"The jurisdiction pack for this market documents {len(bundle.interoperability_permitted_acts)} interoperability-permitted-act(s) to check the specific act performed against.",
        [str(a) for a in bundle.interoperability_permitted_acts], "medium",
        alternative_explanation="Whether the ACTUAL act performed falls within one of these documented exceptions is a human/qualified-counsel determination, not automated here.",
    )


# Issues not yet backed by a specific heuristic in v0.1 (patents, trademarks,
# database_rights, confidentiality, trade_secrets, linking,
# contractual_permissions, protected_expression) are honestly reported
# UNKNOWN rather than simulated with a fake heuristic -- each would require
# facts this tool cannot compute deterministically (contract text analysis,
# registry lookups, idea/expression-merger judgment). See ROADMAP.md.
_HEURISTICS: dict[str, Callable[[CaseBundle], list[dict[str, Any]]]] = {
    "lawful_access": lambda b: [_lawful_access(b)],
    "copyright_subsistence": lambda b: [_copyright_subsistence(b)],
    "permitted_acts": lambda b: [_permitted_acts(b)],
    "copying": _copying_and_substantiality,
    "saas_network_provision": lambda b: [_saas_network_provision(b)],
    "licence_obligations": lambda b: [_licence_obligations(b)],
    "distribution": lambda b: [_distribution(b)],
    "derivative_work_question": lambda b: [_derivative_work_question(b)],
    "interoperability_provisions": lambda b: [_interoperability_provisions(b)],
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
