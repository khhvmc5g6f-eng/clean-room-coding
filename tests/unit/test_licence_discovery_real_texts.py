"""Regression tests for the fingerprint-collision bug found in code review:
canonical BSD-3-Clause text is a superset-match of BSD-2-Clause's marker,
and canonical AGPL-3.0/LGPL text's own preamble satisfies GPL-3.0-only/
GPL-2.0-only's markers too. Both previously caused `conflicting_evidence`
on completely unambiguous, mainstream licence text. See
tests/fixtures/real-license-texts/README.md for fixture provenance.
"""

from pathlib import Path

import pytest

from cleanroom.licence.discovery import _fingerprint_text

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "real-license-texts"


@pytest.mark.parametrize(
    "filename,expected",
    [
        ("BSD-3-Clause.txt", "BSD-3-Clause"),
        ("AGPL-3.0.txt", "AGPL-3.0-only"),
        ("LGPL-3.0.txt", "LGPL-3.0-only"),
        ("LGPL-2.1.txt", "LGPL-2.1-only"),
    ],
)
def test_real_licence_text_resolves_unambiguously(filename: str, expected: str):
    text = (FIXTURES / filename).read_text(encoding="utf-8")
    matches = _fingerprint_text(text)
    assert matches == [expected], (
        f"{filename} should fingerprint to exactly [{expected!r}], got {matches!r} "
        "-- a regression of the fingerprint-collision bug"
    )
