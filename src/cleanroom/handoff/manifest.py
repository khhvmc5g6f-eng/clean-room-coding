"""Parts XXIV-XXV: the immutable, hashed, signable handoff bundle.

Produces HANDOFF_MANIFEST.json (machine-readable) and
CLEAN_ROOM_HANDOFF.md (human-readable) from the contents of Zone H. Every
file is hashed so the implementation side can prove exactly which
specification version it received, byte for byte.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from cleanroom.contamination import Contamination
from cleanroom.exit_codes import ContaminationFailure
from cleanroom.schema_registry import validate
from cleanroom.util import is_safe_regular_file, sha256_file, sha256_json, utc_now_iso

MANIFEST_FILENAME = "HANDOFF_MANIFEST.json"
HANDOFF_DOC_FILENAME = "CLEAN_ROOM_HANDOFF.md"
FACTS_DOC_FILENAME = "CLEAN_ROOM_HANDOFF_FACTS.json"


def build_manifest(
    *,
    project_id: str,
    specification_version: str,
    zone_h: Path,
    file_contamination: dict[str, str],
    sanitisation_report_hash: str,
    signer: str | None = None,
    facts_document: dict[str, str] | None = None,
) -> dict[str, Any]:
    """file_contamination maps zone_h-relative posix paths to a contamination
    level. Any file not classified C0 blocks the handoff (Part V: Zone H
    contains ONLY sanitised, authorised-for-implementation artefacts)."""
    files = []
    violations = []
    for path in sorted(zone_h.rglob("*")):
        if path.is_dir() and not path.is_symlink():
            continue
        if path.name in (MANIFEST_FILENAME, HANDOFF_DOC_FILENAME, FACTS_DOC_FILENAME, ".gitkeep"):
            continue
        rel = path.relative_to(zone_h).as_posix()
        safe, reason = is_safe_regular_file(path, zone_h)
        if not safe:
            violations.append(f"{rel}: unsafe path, refusing to include in handoff ({reason})")
            continue
        level = file_contamination.get(rel)
        if level is None:
            violations.append(f"{rel}: no contamination classification recorded")
            continue
        if not Contamination(level).handoff_eligible():
            violations.append(f"{rel}: classified {level}, not eligible for Zone H (must be C0)")
            continue
        files.append({"path": rel, "sha256": sha256_file(path), "contamination_level": level})

    if violations:
        raise ContaminationFailure(
            "Refusing to build handoff manifest -- Zone H contains non-C0 material:\n"
            + "\n".join(f"  - {v}" for v in violations)
        )

    manifest = {
        "schema_version": "1.0.0",
        "project_id": project_id,
        "specification_version": specification_version,
        "created_utc": utc_now_iso(),
        "files": files,
        "sanitisation_report_hash": sanitisation_report_hash,
    }
    git_commit = _current_git_commit()
    if git_commit:
        manifest["git_commit"] = git_commit
    if signer:
        manifest["signer"] = signer
    if facts_document:
        manifest["facts_document"] = facts_document

    manifest["manifest_hash"] = sha256_json(manifest)

    errors = validate(manifest, "handoff-manifest.schema.json")
    if errors:
        raise ValueError(f"Built an invalid handoff manifest: {errors}")
    return manifest


def sign_manifest(manifest: dict[str, Any], *, gpg_key_id: str | None = None) -> dict[str, Any]:
    """Best-effort detached signature over manifest_hash using the system `gpg`,
    if available and a key id is supplied. Never fabricates a signature."""
    if not gpg_key_id or not shutil.which("gpg"):
        return manifest
    try:
        result = subprocess.run(
            ["gpg", "--batch", "--pinentry-mode", "error", "--local-user", gpg_key_id, "--detach-sign", "--armor", "--output", "-"],
            input=manifest["manifest_hash"].encode("utf-8"),
            capture_output=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        return manifest
    if result.returncode == 0:
        manifest["signature"] = {
            "algorithm": "gpg-detached-armor-over-manifest_hash",
            "value": result.stdout.decode("utf-8"),
            "signer_identity": gpg_key_id,
        }
    return manifest


def write_manifest(manifest: dict[str, Any], zone_h: Path) -> Path:
    path = zone_h / MANIFEST_FILENAME
    with open(path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
    return path


def write_handoff_doc(manifest: dict[str, Any], zone_h: Path) -> Path:
    lines = [
        "# Clean Room Handoff",
        "",
        f"- Project: `{manifest['project_id']}`",
        f"- Specification version: `{manifest['specification_version']}`",
        f"- Created (UTC): {manifest['created_utc']}",
        f"- Manifest hash: `{manifest['manifest_hash']}`",
    ]
    if manifest.get("git_commit"):
        lines.append(f"- Git commit: `{manifest['git_commit']}`")
    lines += [
        "",
        "This bundle contains only C0 (public factual / independent-standard)",
        "material authorised for implementation. Implementation agents",
        "consuming it must not be given any other access to Zone R.",
        "",
        "## Files",
        "",
        "| Path | SHA-256 | Contamination |",
        "|---|---|---|",
    ]
    for f in manifest["files"]:
        lines.append(f"| `{f['path']}` | `{f['sha256'][:16]}…` | {f['contamination_level']} |")
    lines.append("")
    path = zone_h / HANDOFF_DOC_FILENAME
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def validate_facts_document(data: Any) -> list[str]:
    """Validate a candidate facts-only handoff document against
    handoff-facts.schema.json (see schemas/handoff-facts.schema.json --
    that file, like every schema in schemas/, requires human
    legal/governance review per CONTRIBUTING.md/GOVERNANCE.md beyond a
    passing test run).

    JSON Schema alone (string patterns/maxLength) already rejects most
    prose leakage -- multi-line strings, long free-text fields, and
    additional/unexpected keys. It cannot, however, express "this string
    value looks like copied commentary rather than a short identifier"
    for the one place the schema has to allow an arbitrary string --
    `fact.value` (a bare scalar, which legitimately can be a string enum
    value or similar). This function adds that one extra mechanical
    check on top of schema validation: a string `value` that is
    unreasonably long or contains whitespace-heavy prose-shaped content
    is rejected the same way a schema violation would be, with the same
    'reject rather than silently accept' bias the sanitisation scanner
    already uses -- a false positive here costs a review, a false
    negative costs a leak."""
    if not isinstance(data, dict):
        return ["<root>: facts document must be a JSON object"]
    errors = validate(data, "handoff-facts.schema.json")
    if errors:
        return errors
    prose_errors: list[str] = []
    for i, fact in enumerate(data.get("facts", [])):
        if not isinstance(fact, dict):
            continue  # schema validation above already covers this
        value = fact.get("value")
        if isinstance(value, str):
            if len(value) > 64:
                prose_errors.append(
                    f"facts/{i}/value: string value is {len(value)} chars, longer than the 64-char limit for a "
                    "bare fact value -- this looks like copied commentary/prose rather than a short identifier "
                    "or enum literal; move any explanatory text to a free-form Markdown handoff instead"
                )
            elif value.count(" ") >= 4:
                prose_errors.append(
                    f"facts/{i}/value: {value!r} contains {value.count(' ')} spaces -- bare fact values are "
                    "short identifiers/literals, not sentences; this looks like leaked prose"
                )
    return prose_errors


def write_facts_doc(facts_data: dict[str, Any], zone_h: Path) -> Path:
    """Write an already-validated facts document into Zone H as
    CLEAN_ROOM_HANDOFF_FACTS.json. Callers must call
    `validate_facts_document` first and refuse to call this on a document
    that failed validation -- this function does not re-validate, so it
    must never be reachable with unvalidated input from `cli.py`."""
    path = zone_h / FACTS_DOC_FILENAME
    with open(path, "w", encoding="utf-8") as f:
        json.dump(facts_data, f, indent=2, sort_keys=True)
    return path


def verify_manifest(manifest: dict[str, Any], zone_h: Path) -> list[str]:
    """Re-hash Zone H and compare against the manifest. Empty list = intact."""
    problems = []
    expected = dict(manifest)
    signature = expected.pop("signature", None)
    stored_hash = expected.pop("manifest_hash")
    recomputed = sha256_json(expected)
    if recomputed != stored_hash:
        problems.append(f"manifest_hash mismatch: stored {stored_hash}, recomputed {recomputed}")
    for entry in manifest["files"]:
        path = zone_h / entry["path"]
        if not path.is_file():
            problems.append(f"{entry['path']}: file missing from Zone H")
            continue
        actual = sha256_file(path)
        if actual != entry["sha256"]:
            problems.append(f"{entry['path']}: hash mismatch (manifest {entry['sha256']}, actual {actual})")
    return problems


def _current_git_commit() -> str | None:
    try:
        result = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            return result.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return None
