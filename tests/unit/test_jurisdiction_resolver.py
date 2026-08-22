from cleanroom.jurisdiction.resolver import build_matrix, load_pack


def test_england_wales_and_us_packs_load():
    assert load_pack("england-wales") is not None
    assert load_pack("usa-federal") is not None


def test_no_default_jurisdiction_when_nothing_configured():
    matrix = build_matrix(project_id="demo", required_markets=[])
    for issue in matrix["issues"]:
        assert issue["jurisdictions"] == []  # never silently assumes a jurisdiction


def test_required_market_with_pack_is_primary_tier():
    matrix = build_matrix(project_id="demo", required_markets=["gb"])
    copyright_issue = next(i for i in matrix["issues"] if i["issue"] == "copyright")
    assert copyright_issue["jurisdictions"][0]["tier"] == "primary"
    assert "england-wales" in matrix["legal_panels_convened"]


def test_market_without_pack_is_unknown_tier_not_dropped():
    matrix = build_matrix(project_id="demo", required_markets=["cn"])
    copyright_issue = next(i for i in matrix["issues"] if i["issue"] == "copyright")
    assert copyright_issue["jurisdictions"][0]["tier"] == "unknown"


def test_all_six_packs_load():
    for pack_id in ("england-wales", "usa-federal", "france", "germany", "japan", "eu"):
        assert load_pack(pack_id) is not None, f"{pack_id} pack failed to load"


def test_new_jurisdiction_markets_resolve_to_primary_tier():
    matrix = build_matrix(project_id="demo", required_markets=["fr", "de", "jp", "eu"])
    copyright_issue = next(i for i in matrix["issues"] if i["issue"] == "copyright")
    tiers = {j["jurisdiction"]: j["tier"] for j in copyright_issue["jurisdictions"]}
    assert tiers == {"fr": "primary", "de": "primary", "jp": "primary", "eu": "primary"}
    assert {"france", "germany", "japan", "eu"} <= set(matrix["legal_panels_convened"])


def test_multiple_markets_trigger_conflicts_of_law_panel():
    matrix = build_matrix(project_id="demo", required_markets=["gb", "us"])
    assert matrix["conflicts_of_law_panel_required"] is True
