from unittest.mock import MagicMock, patch

from cleanroom.provenance.intoto import (
    LINK_PREDICATE_TYPE,
    STATEMENT_TYPE,
    event_to_link_statement,
    export_ledger_to_link_statements,
    sign_statement,
)


def _base_event(**overrides) -> dict:
    event = {
        "event_id": "11111111-1111-1111-1111-111111111111",
        "sequence": 0,
        "timestamp_utc": "2026-08-22T00:00:00.000Z",
        "actor": {"type": "tool", "id": "cleanroom-sbom"},
        "action": "cleanroom provenance",
        "zone": "I",
        "inputs": [],
        "outputs": [],
        "result": "success",
        "previous_hash": "0" * 64,
        "event_hash": "a" * 64,
    }
    event.update(overrides)
    return event


def test_statement_shape_matches_in_toto_spec():
    statement = event_to_link_statement(_base_event())
    assert statement["_type"] == STATEMENT_TYPE == "https://in-toto.io/Statement/v1"
    assert statement["predicateType"] == LINK_PREDICATE_TYPE == "https://in-toto.io/attestation/link/v0.3"
    assert statement["predicate"]["name"] == "cleanroom provenance"
    # Every claim here traces back to the ledger's own hash chain, not a
    # signature -- must never be silently presented as a signed attestation.
    assert statement["unsigned"] is True
    assert "not" in statement["unsigned_note"].lower()


def test_event_with_no_file_outputs_falls_back_to_event_hash_subject():
    """An event with no recorded file output (most commands today) must
    still be exportable -- its own tamper-evident hash stands in as the
    subject, rather than the event being silently unexportable."""
    statement = event_to_link_statement(_base_event())
    assert statement["subject"] == [{"name": "cleanroom provenance", "digest": {"sha256": "a" * 64}}]


def test_event_with_real_output_hash_uses_it_as_subject():
    event = _base_event(outputs=[{"path": "zone-h/HANDOFF_MANIFEST.json", "sha256": "b" * 64}])
    statement = event_to_link_statement(event)
    assert statement["subject"] == [{"name": "zone-h/HANDOFF_MANIFEST.json", "digest": {"sha256": "b" * 64}}]


def test_output_without_sha256_is_not_fabricated_a_digest():
    """Regression test: an output recorded with only a path (no hash
    actually computed) must not produce a spec-violating subject entry
    with no digest, nor a fabricated one -- it's dropped, falling back to
    the event-hash subject instead."""
    event = _base_event(outputs=[{"path": "some/file.txt"}])  # no sha256
    statement = event_to_link_statement(event)
    assert statement["subject"] == [{"name": "cleanroom provenance", "digest": {"sha256": "a" * 64}}]


def test_input_without_sha256_is_dropped_from_materials_not_fabricated():
    event = _base_event(inputs=[{"path": "reference/lib.py"}])  # no sha256
    statement = event_to_link_statement(event)
    assert statement["predicate"]["materials"] == []


def test_input_with_sha256_becomes_a_material():
    event = _base_event(inputs=[{"path": "reference/lib.py", "sha256": "c" * 64}])
    statement = event_to_link_statement(event)
    assert statement["predicate"]["materials"] == [{"name": "reference/lib.py", "digest": {"sha256": "c" * 64}}]


def test_environment_carries_the_ledger_hash_chain_fields():
    statement = event_to_link_statement(_base_event())
    env = statement["predicate"]["environment"]
    assert env["event_id"] == "11111111-1111-1111-1111-111111111111"
    assert env["previous_hash"] == "0" * 64
    assert env["event_hash"] == "a" * 64
    assert env["actor"] == {"type": "tool", "id": "cleanroom-sbom"}


def test_byproducts_carries_result_and_optional_fields():
    event = _base_event(result="failure", detail="something failed", git_commit="deadbeef")
    statement = event_to_link_statement(event)
    assert statement["predicate"]["byproducts"] == {
        "result": "failure", "detail": "something failed", "git_commit": "deadbeef",
    }


def test_export_ledger_preserves_order():
    events = [_base_event(sequence=i, event_id=f"1111111{i}-1111-1111-1111-111111111111", event_hash=f"{i}" * 64) for i in range(3)]
    statements = export_ledger_to_link_statements(events)
    assert [s["predicate"]["environment"]["sequence"] for s in statements] == [0, 1, 2]


def test_sign_statement_without_key_id_is_a_no_op():
    statement = event_to_link_statement(_base_event())
    result = sign_statement(statement, gpg_key_id=None)
    assert result["unsigned"] is True
    assert "signature" not in result


def test_sign_statement_never_fabricates_when_gpg_unavailable():
    """Regression test: even with a key id given, if gpg isn't on PATH,
    the statement must stay honestly unsigned -- never a fabricated
    signature (same discipline as handoff/manifest.py::sign_manifest)."""
    statement = event_to_link_statement(_base_event())
    with patch("shutil.which", return_value=None):
        result = sign_statement(statement, gpg_key_id="ABCDEF1234567890")
    assert result["unsigned"] is True
    assert "signature" not in result


def test_sign_statement_produces_a_real_signature_when_gpg_succeeds():
    statement = event_to_link_statement(_base_event())
    fake_result = MagicMock(returncode=0, stdout=b"-----BEGIN PGP SIGNATURE-----\nfake\n-----END PGP SIGNATURE-----\n")
    with patch("shutil.which", return_value="/usr/bin/gpg"), patch("subprocess.run", return_value=fake_result):
        result = sign_statement(statement, gpg_key_id="ABCDEF1234567890")
    assert result["unsigned"] is False
    assert result["signature"]["signer_identity"] == "ABCDEF1234567890"
    assert result["signature"]["algorithm"] == "gpg-detached-armor-over-statement-sha256"
    assert "signed_content_sha256" in result["signature"]
    assert "cryptographically signed" in result["unsigned_note"]


def test_sign_statement_falls_back_silently_when_gpg_returns_nonzero():
    statement = event_to_link_statement(_base_event())
    fake_result = MagicMock(returncode=2, stdout=b"")
    with patch("shutil.which", return_value="/usr/bin/gpg"), patch("subprocess.run", return_value=fake_result):
        result = sign_statement(statement, gpg_key_id="wrong-key")
    assert result["unsigned"] is True
    assert "signature" not in result


def test_export_ledger_signs_every_statement_when_key_id_given():
    events = [_base_event(sequence=i, event_id=f"1111111{i}-1111-1111-1111-111111111111", event_hash=f"{i}" * 64) for i in range(2)]
    fake_result = MagicMock(returncode=0, stdout=b"-----BEGIN PGP SIGNATURE-----\nfake\n-----END PGP SIGNATURE-----\n")
    with patch("shutil.which", return_value="/usr/bin/gpg"), patch("subprocess.run", return_value=fake_result):
        statements = export_ledger_to_link_statements(events, gpg_key_id="ABCDEF1234567890")
    assert all(not s["unsigned"] for s in statements)
