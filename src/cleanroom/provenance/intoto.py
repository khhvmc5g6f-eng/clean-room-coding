"""Part XLII (extension): export the evidence ledger to in-toto Link
attestations (https://in-toto.io/attestation/link/v0.3, wrapped in the
in-toto Attestation Framework's Statement envelope,
https://in-toto.io/Statement/v1).

*** THESE ARE STRUCTURAL EXPORTS, NOT SIGNED IN-TOTO ATTESTATIONS. ***

A genuine in-toto attestation's security value comes entirely from a
DSSE-enveloped cryptographic signature over the Statement, verifiable
against a specific signer's known public key. This project's evidence
ledger authenticates its OWN integrity by hash-chaining every event
(Part XLII, `evidence.py`'s `verify_chain`), not by having each individual
actor (human/agent/tool/CI) sign their own step with a private key -- there
is no such key here to sign with. This module maps each ledger event to
the correct in-toto Link predicate *shape*, for interoperability with
tooling that consumes that shape, and to make the ledger's existing
hash-chain evidence (`event_hash`/`previous_hash`) visible in a format
in-toto-aware tooling understands -- but importing one of these files into
a real in-toto/SLSA verification workflow and treating it as equivalent to
a signed attestation would be a false assurance. Every exported file
records this plainly in an `unsigned` field; callers must not strip it.
"""

from __future__ import annotations

from typing import Any

STATEMENT_TYPE = "https://in-toto.io/Statement/v1"
LINK_PREDICATE_TYPE = "https://in-toto.io/attestation/link/v0.3"


def _resource_descriptor(entry: dict[str, Any]) -> dict[str, Any]:
    """An in-toto ResourceDescriptor: `name` is required, `digest` only
    when a real hash was recorded (Part LXVIII: never fabricate one)."""
    descriptor: dict[str, Any] = {"name": entry.get("path") or "(unnamed)"}
    if entry.get("sha256"):
        descriptor["digest"] = {"sha256": entry["sha256"]}
    return descriptor


def event_to_link_statement(event: dict[str, Any]) -> dict[str, Any]:
    """Maps one evidence-ledger event to an in-toto Statement wrapping a
    Link predicate. See the module docstring: this is a structural
    export, not a cryptographically signed attestation."""
    # The Statement spec requires every subject entry to have `digest`
    # set -- an output recorded with a path but no sha256 doesn't qualify
    # (never fabricate the missing hash).
    outputs = [o for o in (event.get("outputs") or []) if o.get("path") and o.get("sha256")]
    subject = [_resource_descriptor(o) for o in outputs]
    if not subject:
        # No digest-bearing file output was recorded for this event (e.g.
        # an audit/status/legal run touches no new artefact) -- the
        # event's own tamper-evident hash stands in as the subject, so
        # every ledger event is exportable, not just file-producing ones.
        subject = [{"name": event["action"], "digest": {"sha256": event["event_hash"]}}]

    # The Link predicate spec requires every materials entry to have both
    # `name` and `digest` set -- an input recorded with a path but no
    # sha256 is dropped here rather than emitted with a missing/fabricated
    # digest (Part LXVIII: never invent a hash that wasn't actually
    # computed).
    materials = [_resource_descriptor(i) for i in (event.get("inputs") or []) if i.get("path") and i.get("sha256")]

    environment: dict[str, Any] = {
        "event_id": event["event_id"],
        "sequence": event["sequence"],
        "timestamp_utc": event["timestamp_utc"],
        "actor": event["actor"],
        "previous_hash": event["previous_hash"],
        "event_hash": event["event_hash"],
    }
    if event.get("zone"):
        environment["zone"] = event["zone"]

    byproducts: dict[str, Any] = {"result": event.get("result", "unknown")}
    if event.get("detail"):
        byproducts["detail"] = event["detail"]
    if event.get("git_commit"):
        byproducts["git_commit"] = event["git_commit"]

    return {
        "_type": STATEMENT_TYPE,
        "subject": subject,
        "predicateType": LINK_PREDICATE_TYPE,
        "predicate": {
            "name": event["action"],
            "command": [event["action"]],
            "materials": materials,
            "byproducts": byproducts,
            "environment": environment,
        },
        "unsigned": True,
        "unsigned_note": (
            "This is a structural mapping of an evidence-ledger event to the in-toto Link "
            "predicate shape, NOT a cryptographically signed in-toto attestation. Its "
            "integrity guarantee comes from the evidence ledger's hash chain "
            "(environment.previous_hash/event_hash, verified by 'cleanroom verify'), not from "
            "a DSSE signature. Do not present this as equivalent to a signed attestation."
        ),
    }


def export_ledger_to_link_statements(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Maps every event in an evidence ledger (as returned by
    `EvidenceLedger.read_all()`) to its in-toto Link Statement, in the
    ledger's own order."""
    return [event_to_link_statement(event) for event in events]
