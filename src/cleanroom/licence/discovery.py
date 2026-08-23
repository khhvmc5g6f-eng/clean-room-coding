"""Part X: deterministic licence discovery.

Scans LICENSE/COPYING/NOTICE files, SPDX-License-Identifier headers and
common package manifests. Every conclusion distinguishes declared vs
detected vs concluded, and unmatched or conflicting evidence is surfaced as
low/unknown confidence rather than silently resolved.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from cleanroom.licence.spdx import KNOWN_IDENTIFIERS
from cleanroom.util import is_safe_regular_file

LICENCE_FILENAME_RE = re.compile(
    r"^(LICEN[CS]E|COPYING|NOTICE|COPYRIGHT)(\..*)?$", re.IGNORECASE
)

# REUSE-IgnoreStart -- this is the *pattern* used to detect an SPDX header
# in scanned third-party files, not a licence declaration for this file.
SPDX_HEADER_RE = re.compile(r"SPDX-License-Identifier:\s*([^\n\r]+)")
# REUSE-IgnoreEnd

# Distinctive fingerprints for the licences this v0.1 build understands deeply.
# Each entry is (spdx_id, required_markers, excluded_markers, title_excluded_markers).
#
# `excluded_markers` (checked against the FULL body) exists because some real
# license texts are proper supersets of another's marker set -- e.g. canonical
# BSD-3-Clause text contains BSD-2-Clause's entire marker phrase as a strict
# substring, and the "Neither the name of" clause that distinguishes them only
# ever appears deep in the body, never in the title -- so it must be checked
# against the full text.
#
# `title_excluded_markers` (checked ONLY against the first TITLE_WINDOW chars)
# exists for the opposite situation: canonical GPL-3.0 text's own Section 13
# discusses compatibility with "the GNU Affero General Public License", and
# canonical AGPL-3.0 text reciprocally discusses "the ordinary GNU General
# Public License" -- both are legitimate body mentions, not a self-declaration
# of which license the file actually is. Checking those markers against the
# full body (as with BSD) would make GPL-3.0-only and AGPL-3.0-only wrongly
# exclude each other's genuine files; only the title/preamble reliably
# self-declares which one a given file is.
#
# Verified empirically against the real gnu.org AGPL-3.0/GPL-2.0/LGPL texts,
# a real canonical GPL-3.0 LICENSE file, and a canonical BSD-3-Clause file
# (see tests/unit/test_licence_discovery.py and
# tests/unit/test_licence_discovery_real_texts.py's real-license-text
# regression tests).
TEXT_FINGERPRINTS: list[tuple[str, list[str], list[str], list[str]]] = [
    ("AGPL-3.0-only", ["GNU AFFERO GENERAL PUBLIC LICENSE", "Version 3"], [], ["GNU GENERAL PUBLIC LICENSE"]),
    ("GPL-3.0-only", ["GNU GENERAL PUBLIC LICENSE", "Version 3"], [], ["GNU AFFERO GENERAL PUBLIC LICENSE"]),
    ("GPL-2.0-only", ["GNU GENERAL PUBLIC LICENSE", "Version 2"], ["GNU AFFERO GENERAL PUBLIC LICENSE", "GNU LESSER GENERAL PUBLIC LICENSE"], []),
    ("LGPL-3.0-only", ["GNU LESSER GENERAL PUBLIC LICENSE", "Version 3"], [], []),
    ("LGPL-2.1-only", ["GNU LESSER GENERAL PUBLIC LICENSE", "Version 2.1"], [], []),
    ("MPL-2.0", ["Mozilla Public License Version 2.0"], [], []),
    ("Apache-2.0", ["Apache License", "Version 2.0"], [], []),
    ("MIT", ["Permission is hereby granted, free of charge"], [], []),
    ("BSD-3-Clause", ["Redistributions of source code must retain", "Neither the name"], [], []),
    ("BSD-2-Clause", ["Redistributions of source code must retain"], ["Neither the name of"], []),
    ("ISC", ["Permission to use, copy, modify, and/or distribute this software"], [], []),
    ("Unlicense", ["This is free and unencumbered software released into the public domain"], [], []),
    ("BUSL-1.1", ["Business Source License 1.1"], [], []),
]

MANIFEST_FILENAMES = {"package.json", "pyproject.toml", "Cargo.toml", "composer.json"}

IGNORE_DIRNAMES = {".git", "__pycache__", ".venv", "node_modules", "dist", "build"}


@dataclass
class LicenceFinding:
    path: str
    declared: str | None = None
    detected: list[str] = field(default_factory=list)
    concluded: str | None = None
    conflicting_evidence: bool = False
    confidence: str = "unknown"
    evidence: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


TITLE_WINDOW = 200


def _fingerprint_text(text: str) -> list[str]:
    matches = []
    lowered = text.lower()
    title = lowered[:TITLE_WINDOW]
    for spdx_id, markers, excluded, title_excluded in TEXT_FINGERPRINTS:
        if not all(marker.lower() in lowered for marker in markers):
            continue
        if any(marker.lower() in lowered for marker in excluded):
            continue
        if any(marker.lower() in title for marker in title_excluded):
            continue
        matches.append(spdx_id)
    return matches


def _read_text(path: Path, limit: int = 200_000) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:limit]
    except OSError:
        return ""


def _scan_licence_files(root: Path) -> list[LicenceFinding]:
    findings = []
    for path in sorted(root.rglob("*")):
        if path.is_dir() or any(part in IGNORE_DIRNAMES for part in path.parts):
            continue
        if not LICENCE_FILENAME_RE.match(path.name):
            continue
        if not is_safe_regular_file(path, root)[0]:
            continue
        text = _read_text(path)
        detected = _fingerprint_text(text)
        rel = path.relative_to(root).as_posix()
        finding = LicenceFinding(
            path=rel,
            detected=detected,
            evidence=[{"source": path.name, "excerpt": text[:400].strip()}],
        )
        if len(detected) == 1:
            finding.concluded = detected[0]
            finding.confidence = "high"
        elif len(detected) > 1:
            finding.conflicting_evidence = True
            finding.confidence = "low"
        else:
            finding.confidence = "unknown"
        findings.append(finding)
    return findings


def _scan_spdx_headers(root: Path, source_extensions: set[str]) -> list[LicenceFinding]:
    findings = []
    for path in sorted(root.rglob("*")):
        if path.is_dir() or any(part in IGNORE_DIRNAMES for part in path.parts):
            continue
        if path.suffix not in source_extensions:
            continue
        if not is_safe_regular_file(path, root)[0]:
            continue
        head = _read_text(path, limit=2000)
        match = SPDX_HEADER_RE.search(head)
        if not match:
            continue
        expr = match.group(1).strip()
        rel = path.relative_to(root).as_posix()
        first_id = expr.split()[0] if expr else ""
        findings.append(
            LicenceFinding(
                path=rel,
                declared=expr,
                concluded=expr if first_id in KNOWN_IDENTIFIERS else None,
                confidence="high" if first_id in KNOWN_IDENTIFIERS else "medium",
                evidence=[{"source": "SPDX-License-Identifier header", "excerpt": expr}],
            )
        )
    return findings


def _scan_manifests(root: Path) -> list[LicenceFinding]:
    findings = []
    for path in sorted(root.rglob("*")):
        if path.is_dir() or path.name not in MANIFEST_FILENAMES:
            continue
        if any(part in IGNORE_DIRNAMES for part in path.parts):
            continue
        if not is_safe_regular_file(path, root)[0]:
            continue
        rel = path.relative_to(root).as_posix()
        declared = None
        try:
            if path.name == "package.json":
                data = json.loads(_read_text(path))
                declared = data.get("license")
            elif path.name == "composer.json":
                data = json.loads(_read_text(path))
                lic = data.get("license")
                declared = ", ".join(lic) if isinstance(lic, list) else lic
            elif path.name == "pyproject.toml":
                declared = _extract_toml_licence(_read_text(path))
            elif path.name == "Cargo.toml":
                declared = _extract_toml_licence(_read_text(path))
        except (json.JSONDecodeError, OSError):
            declared = None
        if declared:
            first_id = str(declared).split()[0]
            findings.append(
                LicenceFinding(
                    path=rel,
                    declared=str(declared),
                    concluded=str(declared) if first_id in KNOWN_IDENTIFIERS else None,
                    confidence="high" if first_id in KNOWN_IDENTIFIERS else "medium",
                    evidence=[{"source": path.name, "excerpt": str(declared)}],
                )
            )
    return findings


def _extract_toml_licence(text: str) -> str | None:
    match = re.search(r'^\s*license\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if match:
        return match.group(1)
    match = re.search(r'^\s*license\s*=\s*\{\s*text\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if match:
        return match.group(1)
    return None


def discover(
    root: Path,
    *,
    source_extensions: set[str] | None = None,
) -> list[LicenceFinding]:
    source_extensions = source_extensions or {
        ".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs", ".java", ".c", ".h", ".cpp", ".rb",
    }
    findings: list[LicenceFinding] = []
    findings.extend(_scan_licence_files(root))
    findings.extend(_scan_spdx_headers(root, source_extensions))
    findings.extend(_scan_manifests(root))
    return findings
