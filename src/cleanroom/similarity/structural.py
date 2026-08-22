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

from cleanroom.similarity.lexical import jaccard, shingles

_STRUCTURAL_KEYWORDS = {
    "if", "else", "elif", "for", "while", "try", "except", "finally",
    "return", "def", "class", "function", "switch", "case", "do",
}


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
        for word in _STRUCTURAL_KEYWORDS:
            if stripped.startswith(word) or f" {word} " in f" {stripped} ":
                shape.append(f"kw:{word}")
        depth += stripped.count("{") + stripped.count("(") - stripped.count("}") - stripped.count(")")
        shape.append(f"depth:{max(depth, 0)}")
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
