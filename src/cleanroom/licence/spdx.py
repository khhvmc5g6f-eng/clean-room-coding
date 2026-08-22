"""Minimal SPDX licence expression support (Part X).

Deliberately not a full SPDX license-list implementation. It supports:
  - a curated set of common identifiers (extend via KNOWN_IDENTIFIERS)
  - compound expressions: AND / OR / WITH, with parentheses
  - LicenseRef-* custom identifiers, which are always well-formed but
    unknown -- callers must treat them as requiring manual review

Uncertainty is a first-class outcome, not an edge case: `parse()` returns
which identifiers are known vs unknown rather than silently accepting or
rejecting the whole expression (Part X: "Never silently turn uncertainty
into certainty.").
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# A curated subset covering the licence packs shipped in v0.1 plus common
# dependency licences. This is NOT the full SPDX license list.
KNOWN_IDENTIFIERS = {
    "MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "ISC", "0BSD",
    "GPL-2.0-only", "GPL-2.0-or-later", "GPL-3.0-only", "GPL-3.0-or-later",
    "LGPL-2.1-only", "LGPL-2.1-or-later", "LGPL-3.0-only", "LGPL-3.0-or-later",
    "AGPL-3.0-only", "AGPL-3.0-or-later",
    "MPL-2.0", "EPL-1.0", "EPL-2.0", "EUPL-1.2",
    "Unlicense", "CC0-1.0", "CC-BY-4.0", "CC-BY-SA-4.0",
    "Python-2.0", "Zlib", "BSL-1.0", "Artistic-2.0", "BUSL-1.1",
}

KNOWN_EXCEPTIONS = {"Classpath-exception-2.0", "GCC-exception-3.1", "OpenSSL-exception"}

_TOKEN_RE = re.compile(r"\(|\)|AND|OR|WITH|[A-Za-z0-9.\-+]+")


@dataclass
class SpdxTerm:
    identifier: str
    known: bool
    or_later: bool = False


@dataclass
class ParsedExpression:
    raw: str
    terms: list[SpdxTerm]
    operators: list[str]  # "AND" | "OR" | "WITH", in order of appearance
    well_formed: bool
    all_known: bool
    issues: list[str]


def _tokenize(expr: str) -> list[str]:
    return _TOKEN_RE.findall(expr)


def parse(expr: str) -> ParsedExpression:
    expr = expr.strip()
    issues: list[str] = []
    tokens = _tokenize(expr)
    if not tokens:
        return ParsedExpression(expr, [], [], well_formed=False, all_known=False, issues=["empty expression"])

    depth = 0
    for tok in tokens:
        if tok == "(":
            depth += 1
        elif tok == ")":
            depth -= 1
            if depth < 0:
                issues.append("unbalanced parentheses")
    if depth != 0:
        issues.append("unbalanced parentheses")

    terms: list[SpdxTerm] = []
    operators: list[str] = []
    for tok in tokens:
        if tok in ("(", ")"):
            continue
        if tok in ("AND", "OR", "WITH"):
            operators.append(tok)
            continue
        if tok.startswith("LicenseRef-"):
            terms.append(SpdxTerm(identifier=tok, known=False))
            issues.append(f"'{tok}' is a custom LicenseRef -- requires manual legal review")
            continue
        if tok in KNOWN_EXCEPTIONS:
            terms.append(SpdxTerm(identifier=tok, known=True))
            continue
        if tok in KNOWN_IDENTIFIERS:
            terms.append(SpdxTerm(identifier=tok, known=True))
            continue
        terms.append(SpdxTerm(identifier=tok, known=False))
        issues.append(f"'{tok}' is not in the curated known-identifier list -- unverified")

    well_formed = depth == 0
    all_known = all(t.known for t in terms) and bool(terms)
    return ParsedExpression(
        raw=expr, terms=terms, operators=operators,
        well_formed=well_formed, all_known=all_known, issues=issues,
    )


def is_compound(expr: str) -> bool:
    return bool(re.search(r"\b(AND|OR|WITH)\b", expr))
