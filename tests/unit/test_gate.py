import json
from pathlib import Path

import pytest

from cleanroom import gate
from cleanroom.specification.graph import RequirementGraph


def _graph_with_one_eligible_node() -> RequirementGraph:
    graph = RequirementGraph()
    graph.add({
        "id": "CR-REQ-000001", "kind": "requirement", "statement": "sorts ascending",
        "classification": "observable_requirement", "contamination_level": "C0", "status": "proposed",
    })
    return graph


def test_signal_insufficient_on_empty_graph(tmp_path: Path):
    signal = gate.compute_signal(RequirementGraph(), tmp_path / "sanitisation-reports")
    assert signal["automated_signal"] == "insufficient"
    assert signal["sufficiency"]["handoff_eligible_nodes"] == 0
    assert signal["blocking_sanitisation_reports"] == []


def test_signal_insufficient_when_only_source_implementation_details_present(tmp_path: Path):
    graph = RequirementGraph()
    graph.add({
        "id": "CR-REQ-000001", "kind": "requirement", "statement": "uses internal FooSorter class",
        "classification": "source_implementation_detail", "contamination_level": "C3", "status": "proposed",
    })
    signal = gate.compute_signal(graph, tmp_path / "sanitisation-reports")
    assert signal["automated_signal"] == "insufficient"
    assert signal["sufficiency"]["handoff_eligible_nodes"] == 0
    assert signal["sufficiency"]["source_implementation_details_excluded"] == 1


def test_signal_sufficient_with_eligible_node_and_no_blocking_reports(tmp_path: Path):
    signal = gate.compute_signal(_graph_with_one_eligible_node(), tmp_path / "sanitisation-reports")
    assert signal["automated_signal"] == "sufficient"
    assert signal["sufficiency"]["handoff_eligible_nodes"] == 1
    assert signal["blocking_sanitisation_reports"] == []


def test_signal_insufficient_when_a_sanitisation_report_is_blocked(tmp_path: Path):
    reports_dir = tmp_path / "sanitisation-reports"
    reports_dir.mkdir()
    (reports_dir / "spec.md.json").write_text(
        json.dumps({"source_document": "zone-h/spec.md", "raw_analysis_ref": "x", "findings": [], "entries": [], "blocked": True}),
        encoding="utf-8",
    )
    signal = gate.compute_signal(_graph_with_one_eligible_node(), reports_dir)
    assert signal["automated_signal"] == "insufficient"
    assert signal["blocking_sanitisation_reports"] == ["spec.md.json"]


def test_signal_sufficient_when_only_non_blocking_reports_present(tmp_path: Path):
    reports_dir = tmp_path / "sanitisation-reports"
    reports_dir.mkdir()
    (reports_dir / "spec.md.json").write_text(
        json.dumps({"source_document": "zone-h/spec.md", "raw_analysis_ref": "x", "findings": [], "entries": [], "blocked": False}),
        encoding="utf-8",
    )
    signal = gate.compute_signal(_graph_with_one_eligible_node(), reports_dir)
    assert signal["automated_signal"] == "sufficient"


def test_build_decision_records_no_override_on_clean_pass():
    signal = {"automated_signal": "sufficient", "sufficiency": {"handoff_eligible_nodes": 1, "total_requirement_nodes": 1, "source_implementation_details_excluded": 0}, "blocking_sanitisation_reports": []}
    record = gate.build_decision(
        project_id="demo", specification_version="v1", decision="pass",
        reviewer="Jane Reviewer", notes="looks complete", signal=signal, sequence=1,
    )
    assert record["id"] == "CR-GATE-000001"
    assert record["decision"] == "pass"
    assert record["overrode_automated_signal"] is False


def test_build_decision_flags_override_when_pass_despite_insufficient_signal():
    signal = {"automated_signal": "insufficient", "sufficiency": {"handoff_eligible_nodes": 0, "total_requirement_nodes": 0, "source_implementation_details_excluded": 0}, "blocking_sanitisation_reports": []}
    record = gate.build_decision(
        project_id="demo", specification_version="v1", decision="pass",
        reviewer="Jane Reviewer", notes="tiny feature, one line is genuinely enough", signal=signal, sequence=1,
    )
    assert record["overrode_automated_signal"] is True


def test_build_decision_never_flags_override_on_fail():
    signal = {"automated_signal": "insufficient", "sufficiency": {"handoff_eligible_nodes": 0, "total_requirement_nodes": 0, "source_implementation_details_excluded": 0}, "blocking_sanitisation_reports": []}
    record = gate.build_decision(
        project_id="demo", specification_version="v1", decision="fail",
        reviewer="Jane Reviewer", notes="not enough coverage yet", signal=signal, sequence=1,
    )
    assert record["overrode_automated_signal"] is False


def test_build_decision_rejects_invalid_decision_value():
    signal = {"automated_signal": "sufficient", "sufficiency": {"handoff_eligible_nodes": 1, "total_requirement_nodes": 1, "source_implementation_details_excluded": 0}, "blocking_sanitisation_reports": []}
    with pytest.raises(ValueError):
        gate.build_decision(
            project_id="demo", specification_version="v1", decision="maybe",
            reviewer="Jane Reviewer", notes="x", signal=signal, sequence=1,
        )


def test_load_decisions_missing_file_returns_empty_list(tmp_path: Path):
    assert gate.load_decisions(tmp_path / "GATE_DECISIONS.json") == []


def test_save_and_load_decisions_round_trip(tmp_path: Path):
    signal = {"automated_signal": "sufficient", "sufficiency": {"handoff_eligible_nodes": 1, "total_requirement_nodes": 1, "source_implementation_details_excluded": 0}, "blocking_sanitisation_reports": []}
    record = gate.build_decision(
        project_id="demo", specification_version="v1", decision="pass",
        reviewer="Jane Reviewer", notes="x", signal=signal, sequence=1,
    )
    path = tmp_path / "GATE_DECISIONS.json"
    gate.save_decisions(path, [record])
    assert gate.load_decisions(path) == [record]


def test_latest_decision_picks_most_recent_for_matching_version_only():
    signal = {"automated_signal": "sufficient", "sufficiency": {"handoff_eligible_nodes": 1, "total_requirement_nodes": 1, "source_implementation_details_excluded": 0}, "blocking_sanitisation_reports": []}
    v1_fail = gate.build_decision(project_id="demo", specification_version="v1", decision="fail", reviewer="A", notes="x", signal=signal, sequence=1)
    v2_pass = gate.build_decision(project_id="demo", specification_version="v2", decision="pass", reviewer="A", notes="x", signal=signal, sequence=2)
    v1_pass = gate.build_decision(project_id="demo", specification_version="v1", decision="pass", reviewer="A", notes="fixed the gap", signal=signal, sequence=3)
    decisions = [v1_fail, v2_pass, v1_pass]
    assert gate.latest_decision(decisions, "v1") == v1_pass
    assert gate.latest_decision(decisions, "v2") == v2_pass
    assert gate.latest_decision(decisions, "v3-does-not-exist") is None
