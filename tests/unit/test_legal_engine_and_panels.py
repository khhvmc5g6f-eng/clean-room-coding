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
