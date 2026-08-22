import pytest

from cleanroom.specification.graph import RequirementGraph


def test_handoff_eligible_only_observable_c0():
    graph = RequirementGraph()
    graph.add({
        "id": "CR-REQ-000001", "kind": "requirement", "statement": "sorts ascending",
        "classification": "observable_requirement", "contamination_level": "C0", "status": "proposed",
    })
    graph.add({
        "id": "CR-REQ-000002", "kind": "requirement", "statement": "uses internal FooSorter class",
        "classification": "source_implementation_detail", "contamination_level": "C3", "status": "proposed",
    })
    eligible = graph.handoff_eligible_nodes()
    assert [n["id"] for n in eligible] == ["CR-REQ-000001"]
    details = graph.source_implementation_details()
    assert [n["id"] for n in details] == ["CR-REQ-000002"]


def test_traceability_report_never_claims_100_percent_falsely():
    graph = RequirementGraph()
    graph.add({
        "id": "CR-REQ-000001", "kind": "requirement", "statement": "x",
        "classification": "observable_requirement", "contamination_level": "C0", "status": "verified",
    })
    graph.add({
        "id": "CR-REQ-000002", "kind": "requirement", "statement": "y",
        "classification": "observable_requirement", "contamination_level": "C0", "status": "proposed",
    })
    report = graph.traceability_report()
    assert report["total"] == 2
    assert report["verified"] == 1
    assert report["completion_percent"] == 50.0


def test_invalid_node_rejected():
    graph = RequirementGraph()
    with pytest.raises(ValueError):
        graph.add({"id": "not-a-valid-id", "kind": "requirement", "statement": "x", "classification": "observable_requirement", "status": "proposed"})


def test_blockers_reported():
    graph = RequirementGraph()
    graph.add({
        "id": "CR-REQ-000001", "kind": "requirement", "statement": "x",
        "classification": "observable_requirement", "status": "blocked",
        "blocker": {"reason": "waiting on legal review", "responsible_component": "legal-engine"},
    })
    blockers = graph.blockers()
    assert blockers[0]["reason"] == "waiting on legal review"
