"""Part XLII (extension): export the evidence ledger to in-toto Link
attestations (https://in-toto.io/attestation/link/v0.3, wrapped in the
in-toto Attestation Framework's Statement envelope,
https://in-toto.io/Statement/v1).

*** BY DEFAULT THESE ARE STRUCTURAL EXPORTS, NOT SIGNED IN-TOTO
ATTESTATIONS -- unless a signer is configured (see `sign_statement`
below). ***

A genuine in-toto attestation's security value comes entirely from a
cryptographic signature over the Statement, verifiable against a
specific signer's known public key. This project's evidence ledger
authenticates its OWN integrity by hash-chaining every event (Part XLII,
`evidence.py`'s `verify_chain`), not by having each individual actor
(human/agent/tool/CI) sign their own step with a private key -- there is
no PER-ACTOR key here (that would need a much bigger multi-party key-
management system). What DOES exist, using the exact same mechanism
`handoff/manifest.py::sign_manifest` already uses for the handoff
manifest: an optional, project-level GPG signer
(`cleanroom verify --export-in-toto-links --signer <gpg-key-id>`) that
produces a real, standard, verifiable detached signature over each
exported Statement -- a genuine cryptographic attestation, just not a
full in-toto-native DSSE/Sigstore envelope with per-step signer
attribution. Without `--signer` (or if `gpg` isn't available, or the key
id is wrong), every exported file honestly stays `unsigned: true` --
`sign_statement` never fabricates a signature, exactly like
`sign_manifest` doesn't. Callers must not strip the `unsigned`/
`unsigned_note`/`signature` fields, whichever way they come out.
"""

from __future__ import annotations

import shutil
import subprocess
from typing import Any

from cleanroom.util import sha256_json

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


def sign_statement(statement: dict[str, Any], *, gpg_key_id: str | None = None) -> dict[str, Any]:
    """Best-effort detached GPG signature over the statement's own
    content, using the identical mechanism and discipline as
    `handoff/manifest.py::sign_manifest`: never fabricates a signature.
    If `gpg_key_id` is omitted or `gpg` isn't on PATH, `statement` is
    returned unchanged (still `unsigned: true`). Only when a real
    signature is actually produced does `unsigned` become `false` -- a
    genuine, standard, verifiable PGP signature (the same mechanism
    `git commit -S` and package-repository signing use), not a full
    in-toto-native DSSE/Sigstore envelope, but real cryptographic
    attestation nonetheless, tied to whatever key the caller configures."""
    if not gpg_key_id or not shutil.which("gpg"):
        return statement
    payload = sha256_json({k: v for k, v in statement.items() if k not in ("unsigned", "unsigned_note", "signature")})
    try:
        result = subprocess.run(
            ["gpg", "--batch", "--pinentry-mode", "error", "--local-user", gpg_key_id, "--detach-sign", "--armor", "--output", "-"],
            input=payload.encode("utf-8"),
            capture_output=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        return statement
    if result.returncode == 0:
        statement["signature"] = {
            "algorithm": "gpg-detached-armor-over-statement-sha256",
            "value": result.stdout.decode("utf-8"),
            "signer_identity": gpg_key_id,
            "signed_content_sha256": payload,
        }
        statement["unsigned"] = False
        statement["unsigned_note"] = (
            f"This statement IS cryptographically signed: a real detached GPG signature (key "
            f"'{gpg_key_id}') over the sha256 of this statement's own content ('signed_content_sha256'), "
            f"using the same mechanism 'cleanroom handoff --signer' already uses for the handoff "
            f"manifest. This is a genuine, verifiable signature -- not a full in-toto-native "
            f"DSSE/Sigstore envelope with per-step signer attribution."
        )
    return statement


def export_ledger_to_link_statements(
    events: list[dict[str, Any]], *, gpg_key_id: str | None = None,
) -> list[dict[str, Any]]:
    """Maps every event in an evidence ledger (as returned by
    `EvidenceLedger.read_all()`) to its in-toto Link Statement, in the
    ledger's own order. Pass `gpg_key_id` to have each one really signed
    (see `sign_statement`) rather than left honestly `unsigned`."""
    return [sign_statement(event_to_link_statement(event), gpg_key_id=gpg_key_id) for event in events]
