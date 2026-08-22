from cleanroom.licence.policy import evaluate, is_blocking, load_pack


def test_allowed_licence():
    result = evaluate("MIT", allowed=["MIT", "Apache-2.0"], denied=["GPL-3.0-only"])
    assert result["status"] == "allowed"
    assert result["obligations"]


def test_denied_licence():
    result = evaluate("GPL-3.0-only", allowed=["MIT"], denied=["GPL-3.0-only"])
    assert result["status"] == "denied"


def test_unresolved_licence_needs_review():
    result = evaluate("MPL-2.0", allowed=["MIT"], denied=["GPL-3.0-only"])
    assert result["status"] == "needs_review"


def test_unknown_licence_expression():
    result = evaluate(None, allowed=["MIT"], denied=[])
    assert result["status"] == "unknown"


def test_is_blocking_rules():
    assert is_blocking("denied", "warn") is True
    assert is_blocking("needs_review", "block") is True
    assert is_blocking("needs_review", "warn") is False
    assert is_blocking("allowed", "block") is False


def test_load_pack_returns_structured_facts_not_a_verdict():
    pack = load_pack("GPL-3.0-only")
    assert pack is not None
    assert pack["copyleft"] == "strong"
    assert "clean_room_relevance" in pack
    assert isinstance(pack["key_obligations"], list) and pack["key_obligations"]
