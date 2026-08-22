"""Parts XX-XXI, LXXIII-LXXIV: the sanitisation panel's deterministic scanners.

These are heuristics that flag candidate handoff material for human/panel
review before it is allowed to cross Zone R -> Zone H. They deliberately
over-flag (false positives cost a review; false negatives cost a leak).
Nothing here auto-approves a document -- `scan()` always returns findings,
never a bare "clean" verdict.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

SECRET_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("aws_access_key_id", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("generic_api_key_assignment", re.compile(r"(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*['\"][A-Za-z0-9_\-/+=]{12,}['\"]")),
    ("private_key_block", re.compile(r"-----BEGIN (RSA |EC |OPENSSH |)PRIVATE KEY-----")),
    ("bearer_token", re.compile(r"(?i)bearer\s+[A-Za-z0-9_\-.]{20,}")),
    ("github_token", re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}")),
]

CODE_SYNTAX_MARKERS = re.compile(
    r"(\bdef\s+\w+\s*\(|\bfunction\s+\w+\s*\(|\bclass\s+\w+\s*[:({]|"
    r"^\s*(import|from|require|#include)\s|;\s*$|=>\s*\{|\{\s*$)",
    re.MULTILINE,
)

PROMPT_INJECTION_MARKERS = re.compile(
    r"(?i)(ignore (all|the) (previous|above) instructions|"
    r"you are now|disregard (your|all) (system|prior) (prompt|instructions)|"
    r"act as (if|though) you (are|have) no restrictions|"
    r"reveal your (system prompt|instructions))"
)

# camelCase, PascalCase, or snake_case -- catching only camelCase/PascalCase
# missed the majority of realistic leaks from Python/Rust/Ruby reference
# material, which overwhelmingly uses snake_case.
IDENTIFIER_RE = re.compile(
    r"\b([a-z]+(?:[A-Z][a-z0-9]*)+|[A-Z][a-zA-Z0-9]*[a-z]|[a-z][a-z0-9]*(?:_[a-z0-9]+)+)\b"
)


@dataclass
class SanitisationFinding:
    category: str
    severity: str  # info | warning | blocking
    excerpt: str
    detail: str
    location: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d = {"category": self.category, "severity": self.severity, "excerpt": self.excerpt, "detail": self.detail}
        if self.location:
            d["location"] = self.location
        return d


def scan_secrets(text: str) -> list[SanitisationFinding]:
    findings = []
    for name, pattern in SECRET_PATTERNS:
        for match in pattern.finditer(text):
            findings.append(
                SanitisationFinding(
                    category="secret",
                    severity="blocking",
                    excerpt=_redact(match.group(0)),
                    detail=f"Matched secret pattern '{name}'. Secrets must never cross into Zone H (Part LXXIII).",
                )
            )
    return findings


def scan_code_like(text: str) -> list[SanitisationFinding]:
    findings = []
    for match in CODE_SYNTAX_MARKERS.finditer(text):
        findings.append(
            SanitisationFinding(
                category="source_snippet_suspected",
                severity="warning",
                excerpt=match.group(0).strip(),
                detail="Text resembles source code syntax rather than a functional/behavioural description.",
            )
        )
    return findings


def scan_prompt_injection(text: str) -> list[SanitisationFinding]:
    """Part LXXIV: reference material is untrusted input to any LLM analyst."""
    findings = []
    for match in PROMPT_INJECTION_MARKERS.finditer(text):
        findings.append(
            SanitisationFinding(
                category="suspected_prompt_injection",
                severity="blocking",
                excerpt=match.group(0),
                detail="Reference content contains an instruction-like phrase. It must never override Clean Room Coding policy or system instructions; record and disregard it.",
            )
        )
    return findings


def scan_identifier_overlap(text: str, reference_identifiers: set[str], *, min_len: int = 6) -> list[SanitisationFinding]:
    """Flags distinctive identifiers copied verbatim from the reference (Part XX)."""
    findings = []
    for match in IDENTIFIER_RE.finditer(text):
        ident = match.group(0)
        if len(ident) >= min_len and ident in reference_identifiers:
            findings.append(
                SanitisationFinding(
                    category="distinctive_identifier_overlap",
                    severity="warning",
                    excerpt=ident,
                    detail="Identifier matches a distinctive name observed in the reference implementation.",
                )
            )
    return findings


def scan_verbatim_overlap(text: str, reference_texts: list[str], *, min_run: int = 40) -> list[SanitisationFinding]:
    """Flags any substring of >= min_run characters shared verbatim with
    reference documentation/source. Checks EVERY offset (a stride-sampled
    version previously missed runs whose length was close to min_run --
    verified empirically: a run of exactly min_run chars had roughly a
    1-in-(min_run/2) chance of landing on a sampled offset). Builds each
    reference text's n-grams into a set once, so this is O(len(ref) +
    len(text)*min_run) rather than O(len(text)/step * len(ref))."""
    findings = []
    seen_chunks: set[str] = set()
    for ref in reference_texts:
        if len(ref) < min_run:
            continue
        ref_ngrams = {ref[i : i + min_run] for i in range(len(ref) - min_run + 1)}
        for i in range(len(text) - min_run + 1):
            chunk = text[i : i + min_run]
            if chunk in ref_ngrams and chunk not in seen_chunks:
                seen_chunks.add(chunk)
                findings.append(
                    SanitisationFinding(
                        category="verbatim_text_overlap",
                        severity="blocking",
                        excerpt=chunk,
                        detail=f"A {min_run}+ character run is verbatim-identical to reference material.",
                    )
                )
    return findings


def scan(
    text: str,
    *,
    reference_identifiers: set[str] | None = None,
    reference_texts: list[str] | None = None,
) -> list[SanitisationFinding]:
    findings: list[SanitisationFinding] = []
    findings.extend(scan_secrets(text))
    findings.extend(scan_code_like(text))
    findings.extend(scan_prompt_injection(text))
    if reference_identifiers:
        findings.extend(scan_identifier_overlap(text, reference_identifiers))
    if reference_texts:
        findings.extend(scan_verbatim_overlap(text, reference_texts))
    return findings


def is_handoff_blocked(findings: list[SanitisationFinding]) -> bool:
    return any(f.severity == "blocking" for f in findings)


def _redact(value: str) -> str:
    if len(value) <= 8:
        return "*" * len(value)
    return value[:4] + "…" + value[-4:]
