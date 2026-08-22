"""Part XXXIV lexical similarity: token/identifier/string overlap.

Simple, deterministic, explainable Jaccard similarity over token shingles.
Deliberately not fuzzy-matching or embedding-based -- every score here can
be reproduced by hand from the two input files, which matters when a
finding is later reviewed by a lawyer or an adversarial reviewer (Part LI).
"""

from __future__ import annotations

import re

_TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*|[0-9]+(?:\.[0-9]+)?")


def tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text)


def shingles(tokens: list[str], n: int = 5) -> set[tuple[str, ...]]:
    if len(tokens) < n:
        return {tuple(tokens)} if tokens else set()
    return {tuple(tokens[i : i + n]) for i in range(len(tokens) - n + 1)}


def jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 0.0
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


def lexical_similarity(text_a: str, text_b: str, *, shingle_size: int = 5) -> float:
    a = shingles(tokenize(text_a), shingle_size)
    b = shingles(tokenize(text_b), shingle_size)
    return jaccard(a, b)


def identifier_overlap(text_a: str, text_b: str) -> float:
    ident_re = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]{2,}\b")
    a = set(ident_re.findall(text_a))
    b = set(ident_re.findall(text_b))
    return jaccard(a, b)
