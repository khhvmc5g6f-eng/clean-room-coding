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


def test_etalab_2_0_pack_is_a_real_non_copyleft_data_licence():
    """France's direct analogue of OGL-UK-3.0 (the Licence Ouverte /
    Etalab Open License), same non-software data-licence shape."""
    pack = load_pack("etalab-2.0")
    assert pack is not None
    assert pack["family"] == "public_sector_data"
    assert pack["copyleft"] == "none"
    assert pack["osi_approved"] is False


def test_dl_de_by_2_0_and_dl_de_zero_2_0_are_the_attribution_and_no_attribution_pair():
    """Germany's two-variant scheme: DL-DE-BY-2.0 requires attribution,
    DL-DE-ZERO-2.0 (its companion) requires none at all -- the packs must
    reflect that real difference, not treat them identically."""
    by_pack = load_pack("DL-DE-BY-2.0")
    zero_pack = load_pack("DL-DE-ZERO-2.0")
    assert by_pack is not None and zero_pack is not None
    assert by_pack["family"] == zero_pack["family"] == "public_sector_data"
    assert by_pack["copyleft"] == zero_pack["copyleft"] == "none"
    assert any("dl-de/by-2-0" in o for o in by_pack["key_obligations"])
    assert len(zero_pack["key_obligations"]) == 1
    assert "none are imposed" in zero_pack["key_obligations"][0].lower()


def test_eupl_1_2_pack_is_a_real_osi_and_fsf_approved_strong_copyleft_licence():
    """Unlike the four data-licence packs added alongside it, EUPL-1.2 is
    a genuine copyleft SOFTWARE licence -- both OSI-approved and
    FSF-libre (verified directly against opensource.org and SPDX's own
    license-list-data), with an express patent grant but no patent
    retaliation clause and no trademark grant."""
    pack = load_pack("EUPL-1.2")
    assert pack is not None
    assert pack["family"] == "copyleft"
    assert pack["copyleft"] == "strong"
    assert pack["osi_approved"] is True
    assert pack["fsf_libre"] is True
    assert pack["patent_grant"] is True
    assert pack["patent_retaliation_clause"] is False
    assert pack["trademark_grant"] is False
    assert pack["network_use_triggers_obligations"] is False

    result = evaluate("EUPL-1.2", allowed=["EUPL-1.2"], denied=[])
    assert result["status"] == "allowed"
    assert any("Source Code" in o for o in result["obligations"])


def test_eupl_1_2_compatible_licences_are_all_real_spdx_identifiers():
    """Every entry in EUPL-1.2's `compatible_licences` (Article 5's own
    published list, expanded into concrete SPDX ids) must be a real
    identifier `license-expression` actually recognises -- never an
    invented one, even though the source text itself doesn't use SPDX
    id syntax."""
    from cleanroom.licence.spdx import KNOWN_IDENTIFIERS

    pack = load_pack("EUPL-1.2")
    compatible = pack["compatible_licences"]
    assert len(compatible) >= 15
    for spdx_id in compatible:
        assert spdx_id in KNOWN_IDENTIFIERS, f"{spdx_id} is not a real SPDX identifier"


def test_nasa_1_3_pack_is_a_real_copyleft_licence_not_a_public_domain_notice():
    """NASA-1.3 is NOT a public-domain instrument despite covering US
    government software -- it's a real, substantive, OSI-approved
    copyleft-shaped licence (used precisely because NASA software is
    often contractor-authored, so real copyright can subsist in it)."""
    pack = load_pack("NASA-1.3")
    assert pack is not None
    assert pack["family"] == "copyleft"
    assert pack["copyleft"] == "strong"
    assert pack["osi_approved"] is True
    assert pack["fsf_libre"] is False
    assert pack["patent_grant"] is True
    assert any("indemnif" in o.lower() for o in pack["key_obligations"])


def test_nist_pd_and_ntia_pd_are_real_public_domain_notices_not_licences():
    """Both are 17 U.S.C. Sec. 105 public-domain notices, not licences
    granting conditional rights -- distinct family from both the
    copyleft packs (NASA-1.3, GPL, EUPL) and the public-sector-data
    packs (OGL-UK-3.0, etalab-2.0, DL-DE-*), which ARE affirmative grants
    over rights the grantor holds."""
    nist = load_pack("NIST-PD")
    ntia = load_pack("NTIA-PD")
    assert nist is not None and ntia is not None
    assert nist["family"] == ntia["family"] == "public_domain"
    assert nist["copyleft"] == ntia["copyleft"] == "none"
    # NTIA-PD's real, distinguishing feature: an express non-US rights
    # grant NIST-PD's text does not contain.
    assert any("non-us" in o.lower() or "outside the united states" in o.lower() or "countries other than" in o.lower() for o in ntia["key_obligations"])


def test_nasa_1_3_reference_triggers_real_copyleft_distribution_finding():
    """End-to-end through the legal engine: NASA-1.3 must produce the
    SAME kind of AMBER copyleft-distribution finding as any other strong-
    copyleft licence -- not be treated as a no-obligation public-domain
    case just because it's associated with a US Government agency."""
    from cleanroom.legal.engine import CaseBundle, run

    bundle = CaseBundle(output_distribution_model=["binary"], reference_licence_ids=["NASA-1.3"])
    findings = {f["issue"]: f for f in run(bundle)}
    assert findings["distribution"]["decision_state"] == "AMBER"
    assert "copyleft distribution triggers" in findings["distribution"]["finding"]


def test_nist_pd_reference_is_genuinely_green_not_just_unpacked_unknown():
    """Contrast case: NIST-PD really is non-copyleft, so with the pack
    now present, a NIST-PD reference resolves to a confirmed GREEN, not
    an 'unknown pack' AMBER."""
    from cleanroom.legal.engine import CaseBundle, run

    bundle = CaseBundle(output_distribution_model=["binary"], reference_licence_ids=["NIST-PD"])
    findings = {f["issue"]: f for f in run(bundle)}
    assert findings["distribution"]["decision_state"] == "GREEN_WITH_CONDITIONS"
