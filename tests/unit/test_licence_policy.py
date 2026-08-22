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


def test_ogl_uk_3_0_pack_is_a_real_non_copyleft_data_licence_not_a_software_one():
    """OGL-UK-3.0 (the UK Open Government Licence) is a public sector
    information/data licence, not a conventional OSS software licence --
    the pack must reflect that honestly (no share-alike obligation, no
    patent grant claimed, and its own real exclusions recorded) rather than
    being forced into the same shape as MIT/Apache/GPL."""
    pack = load_pack("OGL-UK-3.0")
    assert pack is not None
    assert pack["family"] == "public_sector_data"
    assert pack["copyleft"] == "none"
    assert pack["patent_grant"] is False
    assert pack["trademark_grant"] is False
    assert "key_exclusions" in pack and any("personal data" in e.lower() for e in pack["key_exclusions"])

    result = evaluate("OGL-UK-3.0", allowed=["OGL-UK-3.0"], denied=[])
    assert result["status"] == "allowed"
    assert any("attribution statement" in o for o in result["obligations"])
