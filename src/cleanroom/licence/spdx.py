"""SPDX licence expression support (Part X), backed by `license-expression`
(aboutcode-org, Apache-2.0) instead of a hand-rolled ~30-identifier parser.

A prior hand-rolled version deliberately covered only a curated subset and
said so plainly. Swapping in `license_expression.get_spdx_licensing()`
gives real coverage of the full SPDX License List instead -- confirmed via
integration research (2026-08-22) as a low-risk dependency (Apache-2.0,
well-maintained, used by ScanCode Toolkit itself). The one real gap the
library doesn't cover natively: a flat, appearance-ordered `operators`
list (its `parse()` returns a nested boolean-algebra tree, not a flat
sequence). This module keeps a small, read-only regex tokenizer
(unchanged in spirit from the original implementation) purely to extract
that flat list and to pre-check paren balance -- semantic validation
(which identifiers are real) is delegated entirely to the library.

Uncertainty is still a first-class outcome, not an edge case: `parse()`
returns which identifiers are known vs unknown rather than silently
accepting or rejecting the whole expression (Part X: "Never silently turn
uncertainty into certainty.").
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from license_expression import ExpressionError, ExpressionParseError, get_spdx_licensing

_LICENSING = get_spdx_licensing()

# Kept for backward compatibility with callers that check identifiers
# against a known set directly (e.g. licence/discovery.py's manifest/
# SPDX-header scanners) without needing a full expression parse. Backed by
# the same real SPDX License List the parser uses, not a curated subset.
KNOWN_IDENTIFIERS = frozenset(_LICENSING.known_symbols.keys())

KNOWN_EXCEPTIONS = frozenset(
    key for key, symbol in _LICENSING.known_symbols.items() if getattr(symbol, "is_exception", False)
)

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
    if not expr:
        return ParsedExpression(expr, [], [], well_formed=False, all_known=False, issues=["empty expression"])

    tokens = _tokenize(expr)
    operators = [t for t in tokens if t in ("AND", "OR", "WITH")]
    identifier_tokens = [t for t in tokens if t not in ("(", ")", "AND", "OR", "WITH")]

    depth = 0
    for tok in tokens:
        if tok == "(":
            depth += 1
        elif tok == ")":
            depth -= 1
            if depth < 0:
                break
    well_formed = depth == 0

    if not well_formed:
        # Deliberately don't attempt term validation on malformed input --
        # we can't reliably tell which identifiers are "real" in an
        # expression whose structure isn't even valid.
        return ParsedExpression(expr, [], operators, well_formed=False, all_known=False, issues=["unbalanced parentheses"])

    issues: list[str] = []
    invalid_symbols: set[str] = set()
    try:
        info = _LICENSING.validate(expr, strict=True)
        invalid_symbols = set(info.invalid_symbols or [])
        issues.extend(info.errors or [])
    except (ExpressionError, ExpressionParseError) as e:
        # A structurally-balanced expression can still be invalid (e.g. a
        # bare operator with nothing to its left/right). Report it as an
        # issue rather than raising -- callers expect a ParsedExpression,
        # never an exception, for any syntactically paren-balanced input.
        well_formed = False
        issues.append(f"invalid expression: {e}")

    terms: list[SpdxTerm] = []
    for tok in identifier_tokens:
        if tok.startswith("LicenseRef-"):
            issues.append(f"'{tok}' is a custom LicenseRef -- requires manual legal review")
            terms.append(SpdxTerm(identifier=tok, known=False))
            continue
        known = tok not in invalid_symbols
        if not known:
            issues.append(f"'{tok}' is not in the SPDX license list -- unverified")
        terms.append(SpdxTerm(identifier=tok, known=known))

    all_known = bool(terms) and all(t.known for t in terms)
    return ParsedExpression(raw=expr, terms=terms, operators=operators, well_formed=well_formed, all_known=all_known, issues=issues)


def is_compound(expr: str) -> bool:
    return bool(re.search(r"\b(AND|OR|WITH)\b", expr))
