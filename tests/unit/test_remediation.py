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


def test_spec_gap_debug_finding_creates_review_required_task():
    debug_findings = [{"test_id": "CR-BEH-000001", "classification": "spec_gap", "reasons": ["ambiguity marker 'may vary' found"]}]
    tasks = rem.reconcile([], [], [], debug_findings)
    assert len(tasks) == 1
    assert tasks[0]["severity"] == "review_required"
    assert tasks[0]["source_type"] == "debug_finding"
    assert tasks[0]["source_ref"] == "CR-BEH-000001"


def test_implementation_bug_debug_finding_creates_no_task():
    debug_findings = [{"test_id": "CR-BEH-000002", "classification": "implementation_bug", "reasons": ["x"]}]
    assert rem.reconcile([], [], [], debug_findings) == []


def test_spec_gap_debug_finding_auto_resolves_on_rescan():
    debug_findings = [{"test_id": "CR-BEH-000003", "classification": "spec_gap", "reasons": ["x"]}]
    first_pass = rem.reconcile([], [], [], debug_findings)
    assert first_pass[0]["status"] == "open"

    second_pass = rem.reconcile(first_pass, [], [], [])
    assert second_pass[0]["status"] == "resolved_by_rescan"


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


def test_regressed_finding_reopens_after_being_resolved_by_rescan():
    """Regression test: a RED finding that was fixed (resolved_by_rescan)
    and then reappears must block release again -- a prior version of
    reconcile() left it silently resolved forever, defeating the tool's
    core enforcement guarantee."""
    legal = [{"issue": "copying", "jurisdiction": "gb", "decision_state": "RED", "finding": "x"}]

    open_pass = rem.reconcile([], legal, [])
    assert open_pass[0]["status"] == "open"

    cleared_pass = rem.reconcile(open_pass, [], [])
    assert cleared_pass[0]["status"] == "resolved_by_rescan"

    regressed_pass = rem.reconcile(cleared_pass, legal, [])
    assert regressed_pass[0]["status"] == "open"
    assert "resolved_utc" not in regressed_pass[0]
    assert len(rem.open_blocking_tasks(regressed_pass)) == 1


def test_overridden_finding_does_not_reopen_on_regression():
    """A human's explicit --override must survive the underlying finding
    reappearing -- only resolved_by_rescan reopens, never
    resolved_by_override (Part LI: a deliberate human decision)."""
    legal = [{"issue": "copying", "jurisdiction": "gb", "decision_state": "RED", "finding": "x"}]
    tasks = rem.reconcile([], legal, [])
    task_id = tasks[0]["id"]
    overridden = rem.apply_override(tasks, task_id, by="Jane Lawyer", notes="Accepted")

    # Finding clears, then regresses -- override must still hold.
    cleared = rem.reconcile(overridden, [], [])
    assert cleared[0]["status"] == "resolved_by_override"
    regressed = rem.reconcile(cleared, legal, [])
    assert regressed[0]["status"] == "resolved_by_override"
    assert rem.open_blocking_tasks(regressed) == []


def test_task_ids_are_stable_across_reconcile_calls_not_recomputed_by_sort_position():
    """Regression test: IDs must be assigned once at creation and never
    recomputed from sort position on a later call -- otherwise an
    --override recorded against one ID could silently apply to a
    different finding after a subsequent reconcile()."""
    legal_a = [{"issue": "copying", "jurisdiction": "gb", "decision_state": "RED", "finding": "a"}]
    tasks = rem.reconcile([], legal_a, [])
    first_id = tasks[0]["id"]

    legal_both = legal_a + [{"issue": "distribution", "jurisdiction": "us", "decision_state": "RED", "finding": "b"}]
    tasks2 = rem.reconcile(tasks, legal_both, [])
    # The original task's id must be unchanged even though a new task was inserted.
    original_task = next(t for t in tasks2 if t["source_ref"] == "copying@gb")
    assert original_task["id"] == first_id
