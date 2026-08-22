from cleanroom.licence.spdx import parse


def test_simple_known_identifier():
    p = parse("MIT")
    assert p.well_formed
    assert p.all_known
    assert not p.issues


def test_compound_and_expression():
    p = parse("Apache-2.0 AND MIT")
    assert p.well_formed
    assert p.all_known
    assert p.operators == ["AND"]


def test_with_exception():
    p = parse("GPL-3.0-only WITH Classpath-exception-2.0")
    assert p.well_formed
    assert p.all_known


def test_unbalanced_parens_flagged():
    p = parse("(MIT AND Apache-2.0")
    assert not p.well_formed
    assert p.issues


def test_license_ref_flagged_for_manual_review():
    p = parse("LicenseRef-Custom-Foo")
    assert not p.all_known
    assert any("manual legal review" in issue for issue in p.issues)


def test_unknown_identifier_not_silently_accepted():
    p = parse("TotallyMadeUpLicence-9.9")
    assert not p.all_known
    assert p.issues
