from cleanroom.legal.engine import CaseBundle, ISSUES, run
from cleanroom.legal.panels import aggregate_jurisdiction_decision, global_decision


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
