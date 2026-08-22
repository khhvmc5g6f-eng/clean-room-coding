from cleanroom.legal.engine import CaseBundle, ISSUES, run
from cleanroom.legal.panels import (
    aggregate_jurisdiction_decision,
    aggregate_panel_decision,
    global_decision,
    panel_completeness_across_findings,
)


def test_all_18_issues_covered():
    bundle = CaseBundle()
    findings = run(bundle)
    covered = {f["issue"] for f in findings}
    assert covered == set(ISSUES)


def test_unknown_access_authority_is_unknown_not_green():
    bundle = CaseBundle(access_authority=None)
    findings = {f["issue"]: f for f in run(bundle)}
    assert findings["lawful_access"]["decision_state"] == "UNKNOWN"
    assert findings["lawful_access"]["confidence"] == "insufficient_evidence"


def test_isolation_test_failure_is_red():
    bundle = CaseBundle(isolation_test_passed=False)
    findings = {f["issue"]: f for f in run(bundle)}
    assert findings["permitted_acts"]["decision_state"] == "RED"


def test_agpl_saas_combination_is_red():
    bundle = CaseBundle(
        output_distribution_model=["saas"],
        reference_licence_ids=["AGPL-3.0-only"],
    )
    findings = {f["issue"]: f for f in run(bundle)}
    assert findings["saas_network_provision"]["decision_state"] == "RED"


def test_material_similarity_finding_is_red():
    bundle = CaseBundle(similarity_findings=[{"id": "s1", "classification": "material"}])
    findings = {f["issue"]: f for f in run(bundle)}
    assert findings["copying"]["decision_state"] == "RED"


def test_aggregate_never_returns_bare_green():
    findings = [{"decision_state": "GREEN_WITH_CONDITIONS"}] * 3
    assert aggregate_jurisdiction_decision(findings) == "GREEN_WITH_CONDITIONS"

    findings_all_green = [{"decision_state": "GREEN"}]
    assert aggregate_jurisdiction_decision(findings_all_green) != "GREEN"


def test_aggregate_unknown_folds_to_amber():
    findings = [{"decision_state": "UNKNOWN"}]
    assert aggregate_jurisdiction_decision(findings) == "AMBER"


def test_aggregate_worst_wins():
    findings = [{"decision_state": "GREEN_WITH_CONDITIONS"}, {"decision_state": "RED"}]
    assert aggregate_jurisdiction_decision(findings) == "RED"


def test_global_decision_required_market_red_blocks_even_if_others_green():
    decisions = {"gb": "RED", "us": "GREEN_WITH_CONDITIONS"}
    assert global_decision(decisions, required_markets=["gb"]) == "RED"


def test_global_decision_ignores_non_required_red():
    decisions = {"gb": "GREEN_WITH_CONDITIONS", "us": "RED"}
    assert global_decision(decisions, required_markets=["gb"]) == "GREEN_WITH_CONDITIONS"


def test_global_decision_missing_required_market_is_amber_not_green():
    assert global_decision({}, required_markets=["gb"]) == "AMBER"


def test_licence_obligations_unknown_without_discovery():
    bundle = CaseBundle(licence_findings=None)
    findings = {f["issue"]: f for f in run(bundle)}
    assert findings["licence_obligations"]["decision_state"] == "UNKNOWN"


def test_licence_obligations_flags_copyleft():
    bundle = CaseBundle(licence_findings=[{"concluded": "GPL-3.0-only"}])
    findings = {f["issue"]: f for f in run(bundle)}
    assert findings["licence_obligations"]["decision_state"] == "AMBER"


def test_licence_obligations_green_for_permissive_only():
    bundle = CaseBundle(licence_findings=[{"concluded": "MIT"}])
    findings = {f["issue"]: f for f in run(bundle)}
    assert findings["licence_obligations"]["decision_state"] == "GREEN_WITH_CONDITIONS"


def test_licence_obligations_amber_for_unmapped_licence():
    bundle = CaseBundle(licence_findings=[{"concluded": "Unlicense-Not-A-Real-Id"}])
    findings = {f["issue"]: f for f in run(bundle)}
    assert findings["licence_obligations"]["decision_state"] == "AMBER"
    assert findings["licence_obligations"]["confidence"] == "low"


def test_distribution_unknown_without_config():
    bundle = CaseBundle(output_distribution_model=None)
    findings = {f["issue"]: f for f in run(bundle)}
    assert findings["distribution"]["decision_state"] == "UNKNOWN"


def test_distribution_green_when_no_distribution_act_configured():
    bundle = CaseBundle(output_distribution_model=["saas"])
    findings = {f["issue"]: f for f in run(bundle)}
    assert findings["distribution"]["decision_state"] == "GREEN_WITH_CONDITIONS"


def test_distribution_flags_copyleft_trigger_overlap():
    bundle = CaseBundle(output_distribution_model=["binary"], reference_licence_ids=["GPL-3.0-only"])
    findings = {f["issue"]: f for f in run(bundle)}
    assert findings["distribution"]["decision_state"] == "AMBER"


def test_distribution_green_when_no_reference_copyleft():
    bundle = CaseBundle(output_distribution_model=["binary"], reference_licence_ids=["MIT"])
    findings = {f["issue"]: f for f in run(bundle)}
    assert findings["distribution"]["decision_state"] == "GREEN_WITH_CONDITIONS"


def test_distribution_amber_not_green_when_reference_licence_has_no_pack():
    """Regression: `_distribution` used to compute its own inline pack
    lookup and treated a term with NO matching policy pack exactly like a
    term confirmed non-copyleft -- both silently fell through to the same
    GREEN_WITH_CONDITIONS fallback. A real, SPDX-recognised copyleft
    licence with no pack (MPL-2.0, which `license-expression` already
    resolves at high confidence via `cleanroom licence`, but which has no
    policies/licences/MPL-2.0.yml) must report AMBER "unknown to this
    tool", exactly like `_patent_risk`/`_trademark_risk` already do via the
    same `_licence_terms_with_packs` helper -- never a false-clean GREEN."""
    bundle = CaseBundle(output_distribution_model=["binary"], reference_licence_ids=["MPL-2.0"])
    findings = {f["issue"]: f for f in run(bundle)}
    assert findings["distribution"]["decision_state"] == "AMBER"
    assert "no matching policy pack" in findings["distribution"]["finding"]


def test_linking_amber_not_green_when_reference_licence_has_no_pack():
    """Same regression as `_distribution`, for `_linking`."""
    bundle = CaseBundle(output_distribution_model=["library"], reference_licence_ids=["MPL-2.0"])
    findings = {f["issue"]: f for f in run(bundle)}
    assert findings["linking"]["decision_state"] == "AMBER"
    assert "no matching policy pack" in findings["linking"]["finding"]


def test_distribution_amber_with_specific_trigger_when_eupl_pack_exists():
    """EUPL-1.2 (added the same pass as the fix above) closes its own
    instance of the gap: with a real pack now present, a EUPL-1.2
    reference gets the MORE SPECIFIC copyleft-distribution-trigger AMBER
    finding, not just the generic 'unknown pack' one."""
    bundle = CaseBundle(output_distribution_model=["binary"], reference_licence_ids=["EUPL-1.2"])
    findings = {f["issue"]: f for f in run(bundle)}
    assert findings["distribution"]["decision_state"] == "AMBER"
    assert "copyleft distribution triggers" in findings["distribution"]["finding"]

    bundle2 = CaseBundle(output_distribution_model=["library"], reference_licence_ids=["EUPL-1.2"])
    findings2 = {f["issue"]: f for f in run(bundle2)}
    assert findings2["linking"]["decision_state"] == "AMBER"
    assert "strong copyleft" in findings2["linking"]["finding"]


def test_distribution_still_amber_but_names_the_compatible_licence_overlap():
    """EUPL-1.2's Article 5 compatibility clause is a real, licence-text-
    specified interoperability mechanism (a named list of OTHER licences
    a EUPL-derived work may be redistributed under instead). When the
    project's configured output licence overlaps that list, the finding
    must still be AMBER (this tool never auto-resolves it to GREEN -- the
    actual merge-into-a-larger-work circumstance is a human question) but
    the alternative_explanation must name the specific overlap rather than
    staying generic, so a reviewer isn't left to rediscover it by hand."""
    bundle = CaseBundle(
        output_distribution_model=["binary"], reference_licence_ids=["EUPL-1.2"], output_licence_id="MPL-2.0",
    )
    findings = {f["issue"]: f for f in run(bundle)}
    assert findings["distribution"]["decision_state"] == "AMBER"  # never auto-green
    assert "MPL-2.0" in findings["distribution"]["alternative_explanation"]
    assert "compatible licence" in findings["distribution"]["alternative_explanation"]


def test_distribution_no_compatible_licence_note_when_output_licence_is_unrelated():
    """The overlap note must not appear when the configured output
    licence isn't actually in the reference licence's own compatible
    list -- never a false claim of compatibility."""
    bundle = CaseBundle(
        output_distribution_model=["binary"], reference_licence_ids=["EUPL-1.2"], output_licence_id="MIT",
    )
    findings = {f["issue"]: f for f in run(bundle)}
    assert findings["distribution"]["decision_state"] == "AMBER"
    assert "compatible licence" not in findings["distribution"]["alternative_explanation"]


def test_linking_names_the_compatible_licence_overlap_too():
    bundle = CaseBundle(
        output_distribution_model=["library"], reference_licence_ids=["EUPL-1.2"], output_licence_id="GPL-3.0-only",
    )
    findings = {f["issue"]: f for f in run(bundle)}
    assert findings["linking"]["decision_state"] == "AMBER"
    assert "GPL-3.0-only" in findings["linking"]["alternative_explanation"]


def test_derivative_work_question_unknown_without_requirement_graph():
    bundle = CaseBundle(requirement_classifications=None)
    findings = {f["issue"]: f for f in run(bundle)}
    assert findings["derivative_work_question"]["decision_state"] == "UNKNOWN"


def test_derivative_work_question_red_on_material_similarity():
    bundle = CaseBundle(
        requirement_classifications={"observable_requirement": 3},
        similarity_findings=[{"id": "s1", "classification": "material"}],
    )
    findings = {f["issue"]: f for f in run(bundle)}
    assert findings["derivative_work_question"]["decision_state"] == "RED"


def test_derivative_work_question_amber_when_source_details_remain():
    bundle = CaseBundle(requirement_classifications={"source_implementation_detail": 2, "observable_requirement": 1})
    findings = {f["issue"]: f for f in run(bundle)}
    assert findings["derivative_work_question"]["decision_state"] == "AMBER"


def test_derivative_work_question_green_when_clean():
    bundle = CaseBundle(requirement_classifications={"observable_requirement": 5})
    findings = {f["issue"]: f for f in run(bundle)}
    assert findings["derivative_work_question"]["decision_state"] == "GREEN_WITH_CONDITIONS"


def test_interoperability_provisions_unknown_without_pack():
    bundle = CaseBundle(interoperability_permitted_acts=None)
    findings = {f["issue"]: f for f in run(bundle)}
    assert findings["interoperability_provisions"]["decision_state"] == "UNKNOWN"


def test_interoperability_provisions_amber_when_pack_documents_none():
    bundle = CaseBundle(interoperability_permitted_acts=[])
    findings = {f["issue"]: f for f in run(bundle)}
    assert findings["interoperability_provisions"]["decision_state"] == "AMBER"


def test_interoperability_provisions_green_when_pack_documents_acts():
    bundle = CaseBundle(interoperability_permitted_acts=[{"act": "decompilation for interoperability"}])
    findings = {f["issue"]: f for f in run(bundle)}
    assert findings["interoperability_provisions"]["decision_state"] == "GREEN_WITH_CONDITIONS"


def test_protected_expression_is_always_unknown():
    """The one issue with no heuristic in v0.1 -- idea/expression merger
    has no deterministic proxy this tool can compute."""
    bundle = CaseBundle(access_authority="public", licence_findings=[{"concluded": "MIT"}], reference_licence_ids=["MIT"])
    findings = {f["issue"]: f for f in run(bundle)}
    assert findings["protected_expression"]["decision_state"] == "UNKNOWN"
    assert findings["protected_expression"]["confidence"] == "insufficient_evidence"


def test_patent_risk_unknown_without_licence_discovery():
    bundle = CaseBundle(reference_licence_ids=None)
    findings = {f["issue"]: f for f in run(bundle)}
    assert findings["patent_risk"]["decision_state"] == "UNKNOWN"


def test_patent_risk_amber_for_licence_with_no_patent_grant():
    bundle = CaseBundle(reference_licence_ids=["MIT"])
    findings = {f["issue"]: f for f in run(bundle)}
    assert findings["patent_risk"]["decision_state"] == "AMBER"


def test_patent_risk_green_for_licence_with_patent_grant():
    bundle = CaseBundle(reference_licence_ids=["Apache-2.0"])
    findings = {f["issue"]: f for f in run(bundle)}
    assert findings["patent_risk"]["decision_state"] == "GREEN_WITH_CONDITIONS"


def test_trademark_risk_unknown_without_licence_discovery():
    bundle = CaseBundle(reference_licence_ids=None)
    findings = {f["issue"]: f for f in run(bundle)}
    assert findings["trademark_risk"]["decision_state"] == "UNKNOWN"


def test_trademark_risk_amber_when_licence_concluded():
    bundle = CaseBundle(reference_licence_ids=["MIT"])
    findings = {f["issue"]: f for f in run(bundle)}
    assert findings["trademark_risk"]["decision_state"] == "AMBER"


def test_linking_green_when_not_distributed_as_library():
    bundle = CaseBundle(output_distribution_model=["binary"])
    findings = {f["issue"]: f for f in run(bundle)}
    assert findings["linking"]["decision_state"] == "GREEN_WITH_CONDITIONS"


def test_linking_amber_for_library_against_strong_copyleft_reference():
    bundle = CaseBundle(output_distribution_model=["library"], reference_licence_ids=["GPL-3.0-only"])
    findings = {f["issue"]: f for f in run(bundle)}
    assert findings["linking"]["decision_state"] == "AMBER"


def test_linking_green_for_library_against_permissive_reference():
    bundle = CaseBundle(output_distribution_model=["library"], reference_licence_ids=["MIT"])
    findings = {f["issue"]: f for f in run(bundle)}
    assert findings["linking"]["decision_state"] == "GREEN_WITH_CONDITIONS"


def test_confidentiality_unknown_without_access_authority():
    bundle = CaseBundle(access_authority=None)
    findings = {f["issue"]: f for f in run(bundle)}
    assert findings["confidentiality"]["decision_state"] == "UNKNOWN"


def test_confidentiality_green_when_not_contractual():
    bundle = CaseBundle(access_authority="public")
    findings = {f["issue"]: f for f in run(bundle)}
    assert findings["confidentiality"]["decision_state"] == "GREEN_WITH_CONDITIONS"


def test_confidentiality_red_when_contractual_and_sanitisation_blocked():
    bundle = CaseBundle(access_authority="contractual", sanitisation_blocked=True)
    findings = {f["issue"]: f for f in run(bundle)}
    assert findings["confidentiality"]["decision_state"] == "RED"


def test_confidentiality_amber_when_contractual_and_sanitisation_clean():
    bundle = CaseBundle(access_authority="contractual", sanitisation_blocked=False)
    findings = {f["issue"]: f for f in run(bundle)}
    assert findings["confidentiality"]["decision_state"] == "AMBER"


def test_confidentiality_amber_when_contractual_and_sanitisation_not_run():
    bundle = CaseBundle(access_authority="contractual", sanitisation_blocked=None)
    findings = {f["issue"]: f for f in run(bundle)}
    assert findings["confidentiality"]["decision_state"] == "AMBER"
    assert findings["confidentiality"]["confidence"] == "low"


def test_trade_secrets_green_when_public():
    bundle = CaseBundle(access_authority="public")
    findings = {f["issue"]: f for f in run(bundle)}
    assert findings["trade_secrets"]["decision_state"] == "GREEN_WITH_CONDITIONS"


def test_trade_secrets_red_when_contractual_and_material_finding():
    bundle = CaseBundle(access_authority="contractual", similarity_findings=[{"id": "s1", "classification": "material"}])
    findings = {f["issue"]: f for f in run(bundle)}
    assert findings["trade_secrets"]["decision_state"] == "RED"


def test_trade_secrets_amber_when_contractual_and_suspicious_finding():
    bundle = CaseBundle(access_authority="contractual", similarity_findings=[{"id": "s1", "classification": "suspicious"}])
    findings = {f["issue"]: f for f in run(bundle)}
    assert findings["trade_secrets"]["decision_state"] == "AMBER"


def test_trade_secrets_amber_when_contractual_and_no_findings():
    bundle = CaseBundle(access_authority="contractual", similarity_findings=[])
    findings = {f["issue"]: f for f in run(bundle)}
    assert findings["trade_secrets"]["decision_state"] == "AMBER"


def test_database_rights_amber_for_eu_jurisdiction():
    # bundle.jurisdiction holds the raw market code cli.py's `legal`
    # command actually sets it to (.cleanroom.yml's required_markets
    # entries, e.g. "eu"/"gb"/"us"), NOT the jurisdiction *pack id* like
    # "england-wales"/"usa-federal" -- these are two different strings
    # (see jurisdiction/resolver.py's COUNTRY_TO_PACK). This regression
    # test uses the real market-code strings deliberately.
    bundle = CaseBundle(jurisdiction="eu")
    findings = {f["issue"]: f for f in run(bundle)}
    assert findings["database_rights"]["decision_state"] == "AMBER"


def test_database_rights_amber_for_gb_retained_law():
    bundle = CaseBundle(jurisdiction="gb")
    findings = {f["issue"]: f for f in run(bundle)}
    assert findings["database_rights"]["decision_state"] == "AMBER"


def test_database_rights_amber_for_france_and_germany():
    for market in ("fr", "de"):
        bundle = CaseBundle(jurisdiction=market)
        findings = {f["issue"]: f for f in run(bundle)}
        assert findings["database_rights"]["decision_state"] == "AMBER", market


def test_database_rights_green_for_us_no_sui_generis_right():
    bundle = CaseBundle(jurisdiction="us")
    findings = {f["issue"]: f for f in run(bundle)}
    assert findings["database_rights"]["decision_state"] == "GREEN_WITH_CONDITIONS"


def test_database_rights_green_for_jp_no_sui_generis_right():
    bundle = CaseBundle(jurisdiction="jp")
    findings = {f["issue"]: f for f in run(bundle)}
    assert findings["database_rights"]["decision_state"] == "GREEN_WITH_CONDITIONS"


def test_database_rights_unknown_for_unrecorded_jurisdiction():
    bundle = CaseBundle(jurisdiction="atlantis")
    findings = {f["issue"]: f for f in run(bundle)}
    assert findings["database_rights"]["decision_state"] == "UNKNOWN"


def test_database_rights_uses_the_market_code_cli_actually_sets_not_the_pack_id():
    """Regression test for the exact bug caught by manual end-to-end CLI
    verification: a jurisdiction PACK ID (e.g. 'england-wales',
    'usa-federal') is never what bundle.jurisdiction actually holds in a
    real cleanroom legal run -- it holds the raw configured market code.
    Passing a pack id here must NOT match either jurisdiction set."""
    for pack_id in ("england-wales", "usa-federal", "france", "germany", "japan"):
        bundle = CaseBundle(jurisdiction=pack_id)
        findings = {f["issue"]: f for f in run(bundle)}
        assert findings["database_rights"]["decision_state"] == "UNKNOWN", pack_id


def test_contractual_permissions_unknown_without_access_authority():
    bundle = CaseBundle(access_authority=None)
    findings = {f["issue"]: f for f in run(bundle)}
    assert findings["contractual_permissions"]["decision_state"] == "UNKNOWN"


def test_contractual_permissions_amber_when_access_is_contractual():
    bundle = CaseBundle(access_authority="contractual")
    findings = {f["issue"]: f for f in run(bundle)}
    assert findings["contractual_permissions"]["decision_state"] == "AMBER"


def test_contractual_permissions_green_for_known_oss_licence_no_restriction():
    bundle = CaseBundle(access_authority="public", licence_findings=[{"concluded": "MIT"}])
    findings = {f["issue"]: f for f in run(bundle)}
    assert findings["contractual_permissions"]["decision_state"] == "GREEN_WITH_CONDITIONS"


def test_contractual_permissions_amber_for_unmapped_licence():
    bundle = CaseBundle(access_authority="public", licence_findings=[{"concluded": "Some-Unmapped-Licence"}])
    findings = {f["issue"]: f for f in run(bundle)}
    assert findings["contractual_permissions"]["decision_state"] == "AMBER"


def test_aggregate_panel_decision_worst_wins():
    panel = [
        {"panel_member_id": "m1", "decision_state": "GREEN_WITH_CONDITIONS"},
        {"panel_member_id": "m2", "decision_state": "RED"},
    ]
    assert aggregate_panel_decision(panel) == "RED"


def test_aggregate_panel_decision_empty_is_amber_not_green():
    assert aggregate_panel_decision([]) == "AMBER"


def test_aggregate_panel_decision_never_returns_bare_green():
    panel = [{"panel_member_id": "m1", "decision_state": "GREEN"}]
    assert aggregate_panel_decision(panel) == "GREEN_WITH_CONDITIONS"


def test_aggregate_panel_decision_unknown_folds_to_amber():
    panel = [{"panel_member_id": "m1", "decision_state": "UNKNOWN"}]
    assert aggregate_panel_decision(panel) == "AMBER"


def test_panel_completeness_ignores_findings_with_no_panel_review_at_all():
    """Deliberately narrow: a finding nobody ever ran through judge/
    judge-adjudicate must not count against the gate -- this checks
    completeness of panel review WHERE USED, it does not make panel
    review itself mandatory."""
    findings = [{"issue": "copying", "jurisdiction": "gb", "panel_adjudications": []}]
    satisfied, reasons = panel_completeness_across_findings(findings, panel_size_required=2, diversity_required=True)
    assert satisfied is True
    assert reasons == []


def test_panel_completeness_flags_insufficient_panel_size():
    findings = [{
        "issue": "copying", "jurisdiction": "gb",
        "panel_adjudications": [{"panel_member_id": "m1", "decision_state": "GREEN_WITH_CONDITIONS", "model_provider": "anthropic"}],
    }]
    satisfied, reasons = panel_completeness_across_findings(findings, panel_size_required=2, diversity_required=False)
    assert satisfied is False
    assert any("copying" in r and "1 panel member" in r and "2 required" in r for r in reasons)


def test_panel_completeness_flags_insufficient_diversity_even_with_enough_members():
    """Panel size alone isn't diversity: 2 members from the SAME provider
    must still fail when diversity is required."""
    findings = [{
        "issue": "copying", "jurisdiction": "gb",
        "panel_adjudications": [
            {"panel_member_id": "m1", "decision_state": "GREEN_WITH_CONDITIONS", "model_provider": "anthropic"},
            {"panel_member_id": "m2", "decision_state": "GREEN_WITH_CONDITIONS", "model_provider": "anthropic"},
        ],
    }]
    satisfied, reasons = panel_completeness_across_findings(findings, panel_size_required=2, diversity_required=True)
    assert satisfied is False
    assert any("diversity" in r for r in reasons)


def test_panel_completeness_satisfied_with_enough_diverse_members():
    findings = [{
        "issue": "copying", "jurisdiction": "gb",
        "panel_adjudications": [
            {"panel_member_id": "m1", "decision_state": "GREEN_WITH_CONDITIONS", "model_provider": "anthropic"},
            {"panel_member_id": "m2", "decision_state": "GREEN_WITH_CONDITIONS", "model_provider": "openai"},
        ],
    }]
    satisfied, reasons = panel_completeness_across_findings(findings, panel_size_required=2, diversity_required=True)
    assert satisfied is True
    assert reasons == []
