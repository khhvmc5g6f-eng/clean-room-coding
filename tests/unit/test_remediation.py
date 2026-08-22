from cleanroom.legal import remediation as rem


def test_red_legal_finding_creates_blocking_task():
    findings = [{"issue": "copying", "jurisdiction": "gb", "decision_state": "RED", "finding": "material similarity"}]
    tasks = rem.reconcile([], findings, [])
    assert len(tasks) == 1
    assert tasks[0]["severity"] == "blocking"
    assert tasks[0]["status"] == "open"
    assert tasks[0]["source_type"] == "legal_finding"


def test_amber_legal_finding_creates_review_required_task():
    findings = [{"issue": "lawful_access", "jurisdiction": "gb", "decision_state": "AMBER", "finding": "unclear"}]
    tasks = rem.reconcile([], findings, [])
    assert tasks[0]["severity"] == "review_required"


def test_green_with_conditions_creates_no_task():
    findings = [{"issue": "lawful_access", "jurisdiction": "gb", "decision_state": "GREEN_WITH_CONDITIONS", "finding": "fine"}]
    assert rem.reconcile([], findings, []) == []


def test_material_similarity_creates_blocking_task():
    findings = [{"id": "SIM-1", "classification": "material", "reference_ref": "a.py", "implementation_ref": "b.py", "explanation": "x"}]
    tasks = rem.reconcile([], [], findings)
    assert tasks[0]["severity"] == "blocking"
    assert tasks[0]["source_type"] == "similarity_finding"


def test_suspicious_similarity_creates_review_required_task():
    findings = [{"id": "SIM-1", "classification": "suspicious", "reference_ref": "a.py", "implementation_ref": "b.py", "explanation": "x"}]
    tasks = rem.reconcile([], [], findings)
    assert tasks[0]["severity"] == "review_required"


def test_fixed_finding_auto_resolves_on_rescan():
    legal = [{"issue": "copying", "jurisdiction": "gb", "decision_state": "RED", "finding": "x"}]
    first_pass = rem.reconcile([], legal, [])
    assert first_pass[0]["status"] == "open"

    # Re-run with the finding no longer present (team fixed it).
    second_pass = rem.reconcile(first_pass, [], [])
    assert second_pass[0]["status"] == "resolved_by_rescan"
    assert "resolved_utc" in second_pass[0]


def test_still_broken_finding_stays_open_across_reconcile():
    legal = [{"issue": "copying", "jurisdiction": "gb", "decision_state": "RED", "finding": "x"}]
    first_pass = rem.reconcile([], legal, [])
    second_pass = rem.reconcile(first_pass, legal, [])
    assert second_pass[0]["status"] == "open"


def test_open_blocking_tasks_filters_correctly():
    tasks = [
        {"status": "open", "severity": "blocking"},
        {"status": "open", "severity": "review_required"},
        {"status": "resolved_by_rescan", "severity": "blocking"},
    ]
    blocking = rem.open_blocking_tasks(tasks)
    assert len(blocking) == 1


def test_apply_override_marks_resolved_without_rescan():
    legal = [{"issue": "copying", "jurisdiction": "gb", "decision_state": "RED", "finding": "x"}]
    tasks = rem.reconcile([], legal, [])
    task_id = tasks[0]["id"]
    overridden = rem.apply_override(tasks, task_id, by="Jane Lawyer", notes="Accepted residual risk")
    assert overridden[0]["status"] == "resolved_by_override"
    assert overridden[0]["override"]["by"] == "Jane Lawyer"


def test_apply_override_unknown_id_raises():
    import pytest
    with pytest.raises(ValueError):
        rem.apply_override([], "CR-REM-000099", by="x", notes="y")


def test_apply_override_already_resolved_raises():
    import pytest
    tasks = [{"id": "CR-REM-000001", "status": "resolved_by_rescan", "severity": "blocking"}]
    with pytest.raises(ValueError):
        rem.apply_override(tasks, "CR-REM-000001", by="x", notes="y")
