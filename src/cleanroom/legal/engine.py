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
_STRONG_COPYLEFT_LEVELS = {"strong", "network-strong"}
_DISTRIBUTION_ACTS = {"source", "binary", "library", "container"}  # "saas" is handled separately below

# Jurisdictions with a confirmed, real sui generis database right (EU
# Database Directive 96/9/EC Art. 7, or a national implementation/
# retained-law equivalent) -- verified per-jurisdiction, not assumed:
# eu/france/germany implement the Directive directly; England & Wales
# (gb/uk) retains its own database right post-Brexit under assimilated
# law (Copyright and Rights in Databases Regulations 1997, SI 1997/3032),
# confirmed against GOV.UK guidance, with qualification narrowed to UK
# persons/businesses for databases made on or after 2021-01-01. Keyed by
# the same raw market-code strings `bundle.jurisdiction` actually holds
# (cli.py's `legal` command sets it from `.cleanroom.yml`'s
# required_markets/informational_markets, e.g. "gb"/"us"/"fr" -- NOT the
# jurisdiction *pack id* like "england-wales"/"usa-federal", which is a
# different string; see jurisdiction/resolver.py's COUNTRY_TO_PACK).
_DATABASE_RIGHT_JURISDICTIONS = {"eu", "gb", "uk", "fr", "de"}
# Confirmed to have NO equivalent sui generis right: US Supreme Court's
# Feist Publications v. Rural Telephone Service (1991) rejected "sweat of
# the brow" database protection; Japan's Copyright Act has no separate
# database right either (only ordinary copyright in a database's
# creative selection/arrangement, Copyright Act Art. 12-2).
_NO_DATABASE_RIGHT_JURISDICTIONS = {"us", "jp"}

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
    known, unknown = _licence_terms_with_packs(bundle.reference_licence_ids or [])
    triggered: set[str] = set()
    for term in known:
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
    if unknown:
        # A term with no matching policy pack must never be silently
        # treated the same as a term confirmed non-copyleft -- whether it
        # carries a copyleft distribution trigger is genuinely unknown to
        # this tool, not "checked and clear" (the same known/unknown split
        # `_patent_risk`/`_trademark_risk` already draw via this same
        # helper; this heuristic previously computed its own inline pack
        # lookup and didn't).
        return _finding(
            "distribution", bundle.jurisdiction, "AMBER",
            f"Reference/dependency licence term(s) {unknown} have no matching policy pack in this installation -- whether they carry a copyleft distribution trigger for act(s) {sorted(acts)} is unknown to this tool, not confirmed absent.",
            [f"output_distribution_model = {bundle.output_distribution_model}", f"unknown licence terms: {unknown}"], "low",
            alternative_explanation="Add a policy pack for this licence (policies/licences/) or consult qualified counsel.",
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


def _licence_terms_with_packs(licence_ids: list[str]) -> tuple[list[str], list[str]]:
    """Returns (known_terms, unknown_terms) across every term of every
    given licence expression, deduplicated. Shared helper for the
    patent/trademark/contractual heuristics below, all of which read a
    per-licence fact off the same policy packs."""
    known: set[str] = set()
    unknown: set[str] = set()
    for rid in licence_ids or []:
        for term in licence_policy.split_terms(rid or ""):
            if licence_policy.load_pack(term) is not None:
                known.add(term)
            else:
                unknown.add(term)
    return sorted(known), sorted(unknown)


def _patent_risk(bundle: CaseBundle) -> dict[str, Any]:
    if bundle.reference_licence_ids is None:
        return _finding(
            "patent_risk", bundle.jurisdiction, "UNKNOWN",
            "No licence discovery has been run against the reference material, so no reference/dependency licence's patent grant terms are known.",
            [], "insufficient_evidence",
        )
    known, unknown = _licence_terms_with_packs(bundle.reference_licence_ids)
    if not known and not unknown:
        return _finding(
            "patent_risk", bundle.jurisdiction, "UNKNOWN",
            "No reference/dependency licence was concluded, so no patent grant terms are known.",
            [], "insufficient_evidence",
        )
    no_patent_grant = [t for t in known if licence_policy.load_pack(t) and not licence_policy.load_pack(t).get("patent_grant")]
    if no_patent_grant:
        return _finding(
            "patent_risk", bundle.jurisdiction, "AMBER",
            f"Reference/dependency licence(s) {no_patent_grant} carry no express patent grant per their policy pack -- this tool has no evidence about the licensor's (or a third party's) patent position on the functionality being reimplemented.",
            [f"licences without patent_grant: {no_patent_grant}"], "low",
            alternative_explanation="Absence of an express patent grant in the reference's licence does not itself mean a patent risk exists; it only means this tool found no contractual patent grant to point to. This is not a substitute for a patent landscape/freedom-to-operate search, which this tool does not perform.",
        )
    if unknown:
        return _finding(
            "patent_risk", bundle.jurisdiction, "AMBER",
            f"Licence term(s) {unknown} have no matching policy pack in this installation -- their patent grant terms (if any) are unknown to this tool.",
            [f"unknown licence terms: {unknown}"], "low",
        )
    return _finding(
        "patent_risk", bundle.jurisdiction, "GREEN_WITH_CONDITIONS",
        f"Every concluded reference/dependency licence term ({known}) carries an express patent grant per its policy pack.",
        [f"licences with patent_grant: {known}"], "medium",
        alternative_explanation="An express patent grant from the reference's licensor does not address a THIRD PARTY's patent claims against the reimplemented functionality -- this tool performs no patent landscape search.",
    )


def _trademark_risk(bundle: CaseBundle) -> dict[str, Any]:
    if bundle.reference_licence_ids is None:
        return _finding(
            "trademark_risk", bundle.jurisdiction, "UNKNOWN",
            "No licence discovery has been run against the reference material.",
            [], "insufficient_evidence",
        )
    known, unknown = _licence_terms_with_packs(bundle.reference_licence_ids)
    if not known and not unknown:
        return _finding(
            "trademark_risk", bundle.jurisdiction, "UNKNOWN",
            "No reference/dependency licence was concluded.",
            [], "insufficient_evidence",
        )
    return _finding(
        "trademark_risk", bundle.jurisdiction, "AMBER",
        "None of this project's known licence policy packs grant any trademark rights (per their trademark_grant field) -- a copyright/source licence never authorises using the original product's name, logo, or branding for the reimplementation.",
        [f"concluded licence terms checked: {sorted(known + unknown)}"], "medium",
        alternative_explanation="This is a general fact about licence scope, not evidence either way about whether THIS project's naming/branding actually infringes a trademark -- that depends on what name/marks the reimplementation actually uses, which this tool does not evaluate.",
    )


def _linking(bundle: CaseBundle) -> dict[str, Any]:
    if bundle.output_distribution_model is None:
        return _finding(
            "linking", bundle.jurisdiction, "UNKNOWN",
            "Intended distribution model for the implementation has not been configured.",
            [], "insufficient_evidence",
            alternative_explanation="Configure .cleanroom.yml's implementation.distribution_model.",
        )
    if "library" not in bundle.output_distribution_model:
        return _finding(
            "linking", bundle.jurisdiction, "GREEN_WITH_CONDITIONS",
            "The implementation is not configured to be distributed as a library other software links against -- linking-specific copyleft extension (as distinct from ordinary distribution, see 'distribution') is not engaged.",
            [f"output_distribution_model = {bundle.output_distribution_model}"], "medium",
        )
    known, unknown = _licence_terms_with_packs(bundle.reference_licence_ids or [])
    strong_copyleft_refs: set[str] = set()
    for term in known:
        pack = licence_policy.load_pack(term)
        if pack and pack.get("copyleft") in _STRONG_COPYLEFT_LEVELS:
            strong_copyleft_refs.add(term)
    if strong_copyleft_refs:
        return _finding(
            "linking", bundle.jurisdiction, "AMBER",
            f"The implementation is distributed as a library (other software will link against it), and reference/dependency licence(s) {sorted(strong_copyleft_refs)} carry strong copyleft -- unlike a standalone binary, a library that is a derivative work can extend copyleft obligations to whatever combines/links with it (the GPL family's 'derivative work via linking' theory), separately from whether the library itself is merely distributed.",
            [f"output_distribution_model includes library", f"strong-copyleft reference licences: {sorted(strong_copyleft_refs)}"],
            "medium",
            alternative_explanation="Whether linking against this specific library actually creates a derivative work under the applicable licence (some licences, e.g. LGPL, have an explicit linking exception not modelled by any pack in this installation) is a question for qualified counsel, not resolved here.",
        )
    if unknown:
        # Same fix as `_distribution`: a term with no matching pack must
        # read as unknown, not as "checked, no strong copyleft found."
        return _finding(
            "linking", bundle.jurisdiction, "AMBER",
            f"Reference/dependency licence term(s) {unknown} have no matching policy pack in this installation -- whether they carry strong copyleft that would extend to a linking work is unknown to this tool, not confirmed absent.",
            [f"output_distribution_model includes library", f"unknown licence terms: {unknown}"], "low",
            alternative_explanation="Add a policy pack for this licence (policies/licences/) or consult qualified counsel.",
        )
    return _finding(
        "linking", bundle.jurisdiction, "GREEN_WITH_CONDITIONS",
        "The implementation is distributed as a library, but no reference/dependency licence with strong copyleft was detected.",
        [f"output_distribution_model = {bundle.output_distribution_model}"], "medium",
    )


def _confidentiality(bundle: CaseBundle) -> dict[str, Any]:
    if bundle.access_authority in (None, "unknown"):
        return _finding(
            "confidentiality", bundle.jurisdiction, "UNKNOWN",
            "Access authority for the reference material has not been established.",
            [], "insufficient_evidence",
        )
    if bundle.access_authority != "contractual":
        return _finding(
            "confidentiality", bundle.jurisdiction, "GREEN_WITH_CONDITIONS",
            f"Access authority is declared '{bundle.access_authority}', not contractual -- no declared contractual confidentiality obligation is in scope.",
            [f"intake.access_authority = {bundle.access_authority}"], "medium",
        )
    if bundle.sanitisation_blocked is None:
        return _finding(
            "confidentiality", bundle.jurisdiction, "AMBER",
            "Access is declared contractual (implying a possible confidentiality obligation), and the sanitisation scanner has not been run to confirm no confidential material crossed into the handoff bundle.",
            ["intake.access_authority = contractual"], "low",
            alternative_explanation="Run 'cleanroom sanitise' on every candidate handoff document; this tool cannot read the actual contract's confidentiality terms.",
        )
    if bundle.sanitisation_blocked:
        return _finding(
            "confidentiality", bundle.jurisdiction, "RED",
            "Access is declared contractual and the sanitisation scanner has, at some point, blocked a candidate handoff document -- verify no confidential material from the contractual access actually crossed into Zone H before proceeding.",
            ["intake.access_authority = contractual", "a 'cleanroom sanitise' run recorded result=denied"], "high",
        )
    return _finding(
        "confidentiality", bundle.jurisdiction, "AMBER",
        "Access is declared contractual, but sanitisation runs on record have not blocked any candidate handoff document.",
        ["intake.access_authority = contractual", "no recorded sanitisation denial"], "medium",
        alternative_explanation="This tool cannot read the actual contract's confidentiality terms, only whether its own sanitisation scanner has caught anything; a clean sanitisation history is not the same as confirmed compliance with the contract.",
    )


def _trade_secrets(bundle: CaseBundle) -> dict[str, Any]:
    if bundle.access_authority in (None, "unknown"):
        return _finding(
            "trade_secrets", bundle.jurisdiction, "UNKNOWN",
            "Access authority for the reference material has not been established.",
            [], "insufficient_evidence",
        )
    if bundle.access_authority == "public":
        return _finding(
            "trade_secrets", bundle.jurisdiction, "GREEN_WITH_CONDITIONS",
            "Reference material was declared publicly accessible -- material that is genuinely public is not ordinarily capable of trade secret protection, which requires actual secrecy.",
            ["intake.access_authority = public"], "medium",
            alternative_explanation="If any specific portion of the 'public' material was in fact obtained or retained under a separate confidentiality obligation, that portion could still be a trade secret -- this is a general default, not a case-specific ruling.",
        )
    material_or_suspicious = [
        f for f in (bundle.similarity_findings or []) if f.get("classification") in ("material", "suspicious")
    ]
    if material_or_suspicious:
        return _finding(
            "trade_secrets", bundle.jurisdiction, "RED" if any(f.get("classification") == "material" for f in material_or_suspicious) else "AMBER",
            f"Access authority is '{bundle.access_authority}' (non-public) and {len(material_or_suspicious)} similarity finding(s) are open -- non-public access combined with unresolved similarity is the fact pattern trade secret misappropriation claims are built on; qualified counsel review is warranted before proceeding.",
            [f["id"] for f in material_or_suspicious], "high",
        )
    return _finding(
        "trade_secrets", bundle.jurisdiction, "AMBER",
        f"Access authority is '{bundle.access_authority}' (non-public); no similarity findings are currently open, but this tool cannot independently confirm what confidentiality/trade-secret terms (if any) governed that access.",
        [f"intake.access_authority = {bundle.access_authority}"], "low",
    )


def _database_rights(bundle: CaseBundle) -> dict[str, Any]:
    jurisdiction_key = (bundle.jurisdiction or "").lower()
    if jurisdiction_key in _DATABASE_RIGHT_JURISDICTIONS:
        return _finding(
            "database_rights", bundle.jurisdiction, "AMBER",
            f"'{bundle.jurisdiction}' has a confirmed sui generis database right (EU Database Directive 96/9/EC Art. 7, or a national/retained-law implementation) that applies independently of copyright -- if the reference material includes a substantial database (by verification or investment of obtaining/verifying/presenting its contents), this is a separate question from ordinary copyright/similarity analysis.",
            [f"jurisdiction = {bundle.jurisdiction}"], "medium",
            alternative_explanation="This flags that the regime exists in this jurisdiction, not that the specific reference material qualifies as a protected database -- that is a fact question this tool does not evaluate.",
        )
    if jurisdiction_key in _NO_DATABASE_RIGHT_JURISDICTIONS:
        return _finding(
            "database_rights", bundle.jurisdiction, "GREEN_WITH_CONDITIONS",
            f"'{bundle.jurisdiction}' has no sui generis database right (confirmed: US -- Feist Publications v. Rural Telephone Service rejected 'sweat of the brow' protection; Japan -- no separate database right, only ordinary copyright in a creative selection/arrangement under Copyright Act Art. 12-2).",
            [f"jurisdiction = {bundle.jurisdiction}"], "medium",
        )
    return _finding(
        "database_rights", bundle.jurisdiction, "UNKNOWN",
        f"Whether '{bundle.jurisdiction}' has a sui generis database right is not recorded in this tool for this jurisdiction.",
        [], "insufficient_evidence",
    )


def _contractual_permissions(bundle: CaseBundle) -> dict[str, Any]:
    if bundle.access_authority in (None, "unknown"):
        return _finding(
            "contractual_permissions", bundle.jurisdiction, "UNKNOWN",
            "Access authority for the reference material has not been established.",
            [], "insufficient_evidence",
        )
    if bundle.access_authority == "contractual":
        return _finding(
            "contractual_permissions", bundle.jurisdiction, "AMBER",
            "Access is declared contractual; this tool cannot read the actual contract/NDA text to confirm the specific act performed (e.g. reverse engineering, benchmarking) is contractually permitted.",
            ["intake.access_authority = contractual"], "low",
            alternative_explanation="A human must read the actual agreement and confirm the specific act is within its terms.",
        )
    if not bundle.licence_findings:
        return _finding(
            "contractual_permissions", bundle.jurisdiction, "UNKNOWN",
            "No licence discovery has been run against the reference material.",
            [], "insufficient_evidence",
        )
    concluded = sorted({f["concluded"] for f in bundle.licence_findings if f.get("concluded")})
    if not concluded:
        return _finding(
            "contractual_permissions", bundle.jurisdiction, "AMBER",
            "No licence was concluded for the reference material, so no licence-text-based reverse-engineering permission (or restriction) is known.",
            [f"{len(bundle.licence_findings)} location(s) scanned, 0 concluded"], "low",
        )
    known, unknown = _licence_terms_with_packs(concluded)
    restricting = [t for t in known if licence_policy.load_pack(t) and licence_policy.load_pack(t).get("reverse_engineering_restriction")]
    if restricting:
        return _finding(
            "contractual_permissions", bundle.jurisdiction, "RED",
            f"Concluded reference licence(s) {restricting} are recorded as containing a reverse-engineering/study restriction in their policy pack.",
            [f"restricting licences: {restricting}"], "high",
        )
    if unknown:
        return _finding(
            "contractual_permissions", bundle.jurisdiction, "AMBER",
            f"Concluded licence term(s) {unknown} have no matching policy pack in this installation -- whether they impose a reverse-engineering restriction is unknown to this tool.",
            [f"unknown licence terms: {unknown}"], "low",
        )
    return _finding(
        "contractual_permissions", bundle.jurisdiction, "GREEN_WITH_CONDITIONS",
        f"Concluded reference licence(s) {known} are known open-source/source-available licences with no reverse-engineering restriction recorded in their policy pack.",
        [f"concluded licences checked: {known}"], "medium",
        alternative_explanation="This checks the licence TEXT only; a separate contract, NDA, or terms-of-service the material was accessed under (if any) is not evaluated here -- see 'lawful_access'.",
    )


# Issue with no heuristic in v0.1: protected_expression (idea/expression
# merger analysis is irreducibly a human/expert judgement call this tool
# has no deterministic proxy for -- unlike the other 17 issues, no
# combination of existing facts distinguishes protectable expression from
# unprotectable idea/function/method of operation). Honestly reported
# UNKNOWN rather than simulated with a fake heuristic. See ROADMAP.md.
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
    "patent_risk": lambda b: [_patent_risk(b)],
    "trademark_risk": lambda b: [_trademark_risk(b)],
    "linking": lambda b: [_linking(b)],
    "confidentiality": lambda b: [_confidentiality(b)],
    "trade_secrets": lambda b: [_trade_secrets(b)],
    "database_rights": lambda b: [_database_rights(b)],
    "contractual_permissions": lambda b: [_contractual_permissions(b)],
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
