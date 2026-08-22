from pathlib import Path

from cleanroom.zones import AgentZoneScope, PathGuard, ZoneAccessDenied, create_zones, run_isolation_test


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
    ok, detail = run_isolation_test(zone_r, zone_h, zone_i)
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
