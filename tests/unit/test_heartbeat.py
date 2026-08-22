from pathlib import Path

from cleanroom.orchestration.heartbeat import (
    Tick,
    append_tick,
    diagnose,
    efficiency_summary,
    load_ticks,
    recommend_action,
    tick_intervals_seconds,
)


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


def test_old_tick_log_lines_without_a_timestamp_key_still_load(tmp_path: Path):
    """Real backward compatibility: a persisted .jsonl line written before
    `timestamp` existed has no such key at all -- Tick(**json.loads(line))
    must still construct fine, with timestamp defaulting to None (honestly
    "not recorded"), not a KeyError or a fabricated "now" value."""
    evidence_dir = tmp_path / "evidence"
    log_path = evidence_dir / "ticks" / "agent-1.jsonl"
    log_path.parent.mkdir(parents=True)
    log_path.write_text('{"action_signature": "edit:a.py", "files_modified": 1, "test_result": null}\n', encoding="utf-8")

    ticks = load_ticks(evidence_dir, "agent-1")
    assert ticks == [Tick(action_signature="edit:a.py", files_modified=1, test_result=None, timestamp=None)]


def test_tick_intervals_seconds_computes_real_elapsed_time_between_stamped_ticks():
    ticks = [
        Tick(action_signature="a", files_modified=1, timestamp="2026-08-22T10:00:00.000Z"),
        Tick(action_signature="b", files_modified=1, timestamp="2026-08-22T10:00:05.000Z"),
        Tick(action_signature="c", files_modified=1, timestamp="2026-08-22T10:00:15.000Z"),
    ]
    assert tick_intervals_seconds(ticks) == [5.0, 10.0]


def test_tick_intervals_seconds_skips_unstamped_ticks_rather_than_treating_as_zero_gap():
    ticks = [
        Tick(action_signature="a", files_modified=1, timestamp="2026-08-22T10:00:00.000Z"),
        Tick(action_signature="b", files_modified=1, timestamp=None),  # e.g. predates timestamp tracking
        Tick(action_signature="c", files_modified=1, timestamp="2026-08-22T10:00:10.000Z"),
    ]
    # Only the one real interval between the two stamped ticks -- never a
    # fabricated zero-second gap for the unstamped one in between.
    assert tick_intervals_seconds(ticks) == [10.0]


def test_efficiency_summary_reports_none_not_zero_with_fewer_than_two_stamped_ticks():
    summary = efficiency_summary([Tick(action_signature="a", files_modified=1, timestamp="2026-08-22T10:00:00.000Z")])
    assert summary["average_tick_interval_seconds"] is None
    assert summary["elapsed_seconds"] is None
    assert summary["stamped_ticks"] == 1
    assert summary["unstamped_ticks"] == 0


def test_efficiency_summary_counts_unstamped_ticks_honestly():
    ticks = [
        Tick(action_signature="a", files_modified=1, timestamp=None),
        Tick(action_signature="b", files_modified=1, timestamp="2026-08-22T10:00:00.000Z"),
        Tick(action_signature="c", files_modified=1, timestamp="2026-08-22T10:00:04.000Z"),
    ]
    summary = efficiency_summary(ticks)
    assert summary["total_ticks"] == 3
    assert summary["stamped_ticks"] == 2
    assert summary["unstamped_ticks"] == 1
    assert summary["average_tick_interval_seconds"] == 4.0
