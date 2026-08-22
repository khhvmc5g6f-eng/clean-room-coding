"""Part XXXIV structural similarity: AST/call-pattern/control-flow shape.

v0.1 scope (documented limitation, not silently overclaimed): true AST
comparison is implemented for Python via the stdlib `ast` module. For any
other language, `structural_similarity` falls back to a bracket/keyword
structural skeleton, which is weaker evidence and should be treated
accordingly by the similarity classifier. Extending real-AST support to
other languages (e.g. via tree-sitter) is on the roadmap -- see ROADMAP.md.
"""

from __future__ import annotations

import ast
import re

from cleanroom.similarity.lexical import jaccard, shingles

# Covers the control-flow vocabularies of Python/JS/Java (if/else/for/while/
# try/except/switch/case), Go (func), Rust (fn/match/loop), and Ruby
# (elsif/unless/until) -- the languages engine.py routes to this fallback.
_STRUCTURAL_KEYWORDS = {
    "if", "else", "elif", "elsif", "for", "while", "try", "except", "finally",
    "return", "def", "class", "function", "func", "fn", "switch", "case",
    "do", "match", "loop", "unless", "until",
}
# Matched with word boundaries (re.finditer, not startswith/substring) so
# an identifier that merely starts with a keyword -- "iffy", "definitely",
# "classList", "document.write" -- is never misread as control-flow
# structure. A previous substring-based version did exactly that.
_KEYWORD_RE = re.compile(r"\b(" + "|".join(re.escape(k) for k in _STRUCTURAL_KEYWORDS) + r")\b")


def python_structural_shape(source: str) -> list[str] | None:
    """Return a sequence of AST node type names, ignoring identifiers and
    literal values, or None if `source` isn't parseable Python."""
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return None
    shape: list[str] = []
    for node in ast.walk(tree):
        shape.append(type(node).__name__)
    return shape


def generic_structural_shape(source: str) -> list[str]:
    """Language-agnostic fallback: control-flow keywords and bracket depth
    transitions, in order. Weaker signal than a real AST -- callers should
    down-weight matches produced by this path."""
    shape: list[str] = []
    depth = 0
    for line in source.splitlines():
        stripped = line.strip()
        for match in _KEYWORD_RE.finditer(stripped):
            shape.append(f"kw:{match.group(1)}")
        # Clamp depth itself (not just what's emitted): a single stray
        # unmatched closing bracket -- plausible inside a string literal or
        # comment, since this fallback does no string/comment stripping --
        # could otherwise drive depth permanently negative, after which
        # every remaining line in the file collapses to the same emitted
        # "depth:0" regardless of its real nesting, making two structurally
        # very different files after that point indistinguishable.
        depth = max(depth + stripped.count("{") + stripped.count("(") - stripped.count("}") - stripped.count(")"), 0)
        shape.append(f"depth:{depth}")
    return shape


def structural_similarity(source_a: str, source_b: str, *, shingle_size: int = 8) -> tuple[float, str]:
    """Returns (score, method) where method is 'python_ast' or 'generic_fallback'."""
    shape_a = python_structural_shape(source_a)
    shape_b = python_structural_shape(source_b)
    if shape_a is not None and shape_b is not None:
        method = "python_ast"
    else:
        shape_a = generic_structural_shape(source_a)
        shape_b = generic_structural_shape(source_b)
        method = "generic_fallback"
    score = jaccard(shingles(shape_a, shingle_size), shingles(shape_b, shingle_size))
    return score, method
