from pathlib import Path

from cleanroom.orchestration.heartbeat import Tick, append_tick, diagnose, load_ticks, recommend_action


def test_diagnose_active_with_no_ticks():
    assert diagnose([]) == "ACTIVE"


def test_diagnose_looping_on_repeated_identical_action():
    ticks = [Tick(action_signature="edit:foo.py", files_modified=1) for _ in range(3)]
    assert diagnose(ticks) == "LOOPING"


def test_diagnose_stalled_on_no_files_modified():
    ticks = [Tick(action_signature=f"read:file{i}.py", files_modified=0) for i in range(3)]
    assert diagnose(ticks) == "STALLED"


def test_diagnose_active_when_making_real_progress():
    ticks = [Tick(action_signature=f"edit:file{i}.py", files_modified=1) for i in range(3)]
    assert diagnose(ticks) == "ACTIVE"


def test_diagnose_stalled_on_repeated_test_failures_with_no_fix_attempted():
    # Distinct action signatures so this exercises the failing-tests
    # STALLED path specifically, not the identical-signature LOOPING path.
    ticks = [Tick(action_signature=f"run-tests-attempt-{i}", files_modified=0, test_result="fail") for i in range(3)]
    assert diagnose(ticks) == "STALLED"


def test_recommend_action_maps_each_status():
    assert "Terminate" in recommend_action("LOOPING")
    assert "Inspect" in recommend_action("STALLED")
    assert recommend_action("ACTIVE") == "No action needed."


def test_append_and_load_ticks_round_trip(tmp_path: Path):
    evidence_dir = tmp_path / "evidence"
    append_tick(evidence_dir, "agent-1", Tick(action_signature="edit:a.py", files_modified=1))
    append_tick(evidence_dir, "agent-1", Tick(action_signature="run-tests", files_modified=0, test_result="pass"))
    ticks = load_ticks(evidence_dir, "agent-1")
    assert ticks == [
        Tick(action_signature="edit:a.py", files_modified=1, test_result=None),
        Tick(action_signature="run-tests", files_modified=0, test_result="pass"),
    ]


def test_load_ticks_for_unknown_agent_is_empty_not_an_error(tmp_path: Path):
    assert load_ticks(tmp_path / "evidence", "never-registered") == []


def test_ticks_are_isolated_per_agent(tmp_path: Path):
    evidence_dir = tmp_path / "evidence"
    append_tick(evidence_dir, "agent-a", Tick(action_signature="x", files_modified=1))
    append_tick(evidence_dir, "agent-b", Tick(action_signature="y", files_modified=1))
    assert len(load_ticks(evidence_dir, "agent-a")) == 1
    assert len(load_ticks(evidence_dir, "agent-b")) == 1
