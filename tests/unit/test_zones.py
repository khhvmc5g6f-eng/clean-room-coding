from pathlib import Path

from cleanroom.zones import (
    AgentZoneScope,
    PathGuard,
    ZoneAccessDenied,
    check_agent_zone_consistency,
    create_zones,
    run_pathguard_self_test,
)


def _make_zones(tmp_path: Path):
    zone_r, zone_h, zone_i = tmp_path / "zone-r", tmp_path / "zone-h", tmp_path / "zone-i"
    create_zones(tmp_path, zone_r, zone_h, zone_i)
    return zone_r, zone_h, zone_i


def test_implementation_agent_denied_zone_r(tmp_path: Path):
    zone_r, zone_h, zone_i = _make_zones(tmp_path)
    scope = AgentZoneScope(agent_id="a1", role="implementation", permitted_zones=frozenset({"H", "I"}))
    guard = PathGuard(scope, zone_r, zone_h, zone_i)
    assert not guard.is_allowed(zone_r / "secret.py")
    assert guard.is_allowed(zone_h / "spec.md")
    assert guard.is_allowed(zone_i / "main.py")


def test_analyst_agent_allowed_zone_r(tmp_path: Path):
    zone_r, zone_h, zone_i = _make_zones(tmp_path)
    scope = AgentZoneScope(agent_id="a2", role="analyst", permitted_zones=frozenset({"R"}))
    guard = PathGuard(scope, zone_r, zone_h, zone_i)
    assert guard.is_allowed(zone_r / "reference.py")
    assert not guard.is_allowed(zone_i / "implementation.py")


def test_isolation_self_test_passes(tmp_path: Path):
    zone_r, zone_h, zone_i = _make_zones(tmp_path)
    ok, detail = run_pathguard_self_test(zone_r, zone_h, zone_i)
    assert ok is True
    assert "DENIED" in detail


def test_prohibited_path_wins_even_if_zone_permitted(tmp_path: Path):
    zone_r, zone_h, zone_i = _make_zones(tmp_path)
    secret = zone_i / "leaked-secret.py"
    scope = AgentZoneScope(
        agent_id="a3", role="implementation", permitted_zones=frozenset({"I"}),
        prohibited_paths=(secret,),
    )
    guard = PathGuard(scope, zone_r, zone_h, zone_i)
    assert not guard.is_allowed(secret)
    assert guard.is_allowed(zone_i / "other.py")


def test_without_permitted_paths_a_path_outside_all_zones_is_allowed(tmp_path: Path):
    # Documented, deliberate behaviour when no explicit allow-list is set:
    # PathGuard only polices the three named zones (an agent commonly also
    # needs the project root/evidence dir, which live outside R/H/I).
    zone_r, zone_h, zone_i = _make_zones(tmp_path)
    scope = AgentZoneScope(agent_id="a4", role="implementation", permitted_zones=frozenset({"H", "I"}))
    guard = PathGuard(scope, zone_r, zone_h, zone_i)
    outside = tmp_path.parent / "unrelated-file.txt"
    assert guard.is_allowed(outside)


def test_with_permitted_paths_it_becomes_a_true_allow_list(tmp_path: Path):
    zone_r, zone_h, zone_i = _make_zones(tmp_path)
    allowed_extra = tmp_path / "evidence"
    allowed_extra.mkdir()
    scope = AgentZoneScope(
        agent_id="a5", role="implementation", permitted_zones=frozenset({"H", "I"}),
        permitted_paths=(allowed_extra,),
    )
    guard = PathGuard(scope, zone_r, zone_h, zone_i)
    assert guard.is_allowed(zone_i / "main.py")
    assert guard.is_allowed(allowed_extra / "ledger.jsonl")
    outside = tmp_path.parent / "unrelated-file.txt"
    assert not guard.is_allowed(outside)
    assert not guard.is_allowed(zone_r / "secret.py")


def test_check_agent_zone_consistency_flags_a_real_violation():
    agents = [{"agent_id": "impl-1", "role": "implementation", "permitted_zones": ["H", "I"]}]
    events = [
        {"event_id": "e1", "actor": {"id": "impl-1", "role": "implementation"}, "action": "read file", "zone": "R"},
        {"event_id": "e2", "actor": {"id": "impl-1", "role": "implementation"}, "action": "wrote file", "zone": "I"},
    ]
    problems = check_agent_zone_consistency(agents, events)
    assert len(problems) == 1
    assert "impl-1" in problems[0]


def test_check_agent_zone_consistency_clean_when_no_violation():
    agents = [
        {"agent_id": "impl-1", "role": "implementation", "permitted_zones": ["H", "I"]},
        {"agent_id": "analyst-1", "role": "analyst", "permitted_zones": ["R"]},
    ]
    events = [
        {"event_id": "e1", "actor": {"id": "analyst-1"}, "action": "read reference", "zone": "R"},
        {"event_id": "e2", "actor": {"id": "impl-1"}, "action": "wrote file", "zone": "I"},
    ]
    assert check_agent_zone_consistency(agents, events) == []
