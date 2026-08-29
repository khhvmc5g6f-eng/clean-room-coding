from cleanroom import debugging as dbg


REQ_CLEAR = {
    "id": "CR-REQ-000001", "kind": "requirement",
    "statement": "The export function returns exactly the rows matching the filter, in ascending id order.",
    "classification": "observable_requirement", "status": "handed_off",
}

REQ_AMBIGUOUS = {
    "id": "CR-REQ-000002", "kind": "requirement",
    "statement": "The retry behaviour is implementation-defined and may vary by backend.",
    "classification": "observable_requirement", "status": "handed_off",
}

REQ_CONCURRENT = {
    "id": "CR-REQ-000003", "kind": "requirement",
    "statement": "Concurrent submissions of the same order id must be idempotent.",
    "classification": "observable_requirement", "status": "handed_off",
}


def _test(id_, requirement_ids, given="G", when="W", then="T"):
    return {"id": id_, "given": given, "when": when, "then": then, "requirement_ids": requirement_ids, "result": "fail"}


def test_missing_requirement_is_insufficient_evidence():
    t = _test("CR-BEH-000001", ["CR-REQ-999999"])
    finding = dbg.classify_failure(t, [REQ_CLEAR])
    assert finding["classification"] == "insufficient_evidence"
    assert "CR-REQ-999999" in finding["missing_requirement_ids"]


def test_no_requirement_ids_is_insufficient_evidence():
    t = {"id": "CR-BEH-000001", "given": "G", "when": "W", "then": "T", "requirement_ids": [], "result": "fail"}
    finding = dbg.classify_failure(t, [REQ_CLEAR])
    assert finding["classification"] == "insufficient_evidence"


def test_ambiguous_requirement_is_spec_gap():
    t = _test("CR-BEH-000002", ["CR-REQ-000002"])
    finding = dbg.classify_failure(t, [REQ_AMBIGUOUS])
    assert finding["classification"] == "spec_gap"
    assert any("may vary" in r or "implementation-defined" in r for r in finding["reasons"])


def test_clear_requirement_is_implementation_bug():
    t = _test("CR-BEH-000003", ["CR-REQ-000001"])
    finding = dbg.classify_failure(t, [REQ_CLEAR])
    assert finding["classification"] == "implementation_bug"
    assert finding["concurrency_relevant"] is False


def test_concurrency_language_flagged_on_implementation_bug():
    t = _test("CR-BEH-000004", ["CR-REQ-000003"])
    finding = dbg.classify_failure(t, [REQ_CONCURRENT])
    assert finding["classification"] == "implementation_bug"
    assert finding["concurrency_relevant"] is True
    assert "idempotent" in finding["concurrency_markers"] or "concurrent" in finding["concurrency_markers"] or "concurrently" in finding["concurrency_markers"]


def test_worksheet_includes_temporal_section_only_when_concurrency_relevant():
    plain_finding = dbg.classify_failure(_test("CR-BEH-000005", ["CR-REQ-000001"]), [REQ_CLEAR])
    plain_worksheet = dbg.build_worksheet(plain_finding, _test("CR-BEH-000005", ["CR-REQ-000001"]))
    assert "temporal_concurrency" not in plain_worksheet

    concurrent_finding = dbg.classify_failure(_test("CR-BEH-000006", ["CR-REQ-000003"]), [REQ_CONCURRENT])
    concurrent_worksheet = dbg.build_worksheet(concurrent_finding, _test("CR-BEH-000006", ["CR-REQ-000003"]))
    assert "temporal_concurrency" in concurrent_worksheet
    assert len(concurrent_worksheet["temporal_concurrency"]) > 0


def test_worksheet_always_carries_zone_reminder():
    finding = dbg.classify_failure(_test("CR-BEH-000007", ["CR-REQ-000001"]), [REQ_CLEAR])
    worksheet = dbg.build_worksheet(finding, _test("CR-BEH-000007", ["CR-REQ-000001"]))
    assert "Zone R" in worksheet["zone_reminder"]


def test_triage_suite_skips_passing_and_not_tested():
    tests = [
        {"id": "CR-BEH-000008", "given": "G", "when": "W", "then": "T", "requirement_ids": ["CR-REQ-000001"], "result": "pass"},
        {"id": "CR-BEH-000009", "given": "G", "when": "W", "then": "T", "requirement_ids": ["CR-REQ-000001"], "result": "not_tested"},
        _test("CR-BEH-000010", ["CR-REQ-000001"]),
    ]
    result = dbg.triage_suite(tests, [REQ_CLEAR])
    assert len(result["findings"]) == 1
    assert result["findings"][0]["test_id"] == "CR-BEH-000010"
    assert "CR-BEH-000010" in result["worksheets"]


def test_triage_suite_only_builds_worksheets_for_implementation_bug():
    tests = [_test("CR-BEH-000011", ["CR-REQ-000002"])]  # ambiguous -> spec_gap
    result = dbg.triage_suite(tests, [REQ_AMBIGUOUS])
    assert result["findings"][0]["classification"] == "spec_gap"
    assert result["worksheets"] == {}
