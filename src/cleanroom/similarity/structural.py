"""Part XXXIV structural similarity: AST/call-pattern/control-flow shape.

Real AST comparison for Python (stdlib `ast`) and, since the 2026-08-22
integration research confirmed `ast-grep-py` as the clear winner over
`py-tree-sitter` (one dependency, no per-language grammar packages to
version-track, JS/TS/Go/Rust/Java/Ruby/C/C++ all in its built-in language
table), for every language `ast-grep-py` supports. Only a language ast-grep
doesn't recognise -- or a parse failure -- falls back to the weaker
bracket/keyword heuristic, which callers should treat as lower-confidence
evidence (`structural_similarity`'s returned `method` says which path
produced a given score).
"""

from __future__ import annotations

import ast
import re

from cleanroom.similarity.lexical import jaccard, shingles

try:
    from ast_grep_py import SgRoot
except ImportError:  # pragma: no cover - ast-grep-py is a base dependency; guarded for robustness
    SgRoot = None  # type: ignore[assignment,misc]

# File-extension -> ast-grep-py language identifier. Anything not listed
# here (or whose parse fails) falls back to generic_structural_shape.
SUFFIX_TO_ASTGREP_LANG = {
    ".js": "javascript", ".jsx": "javascript", ".mjs": "javascript", ".cjs": "javascript",
    ".ts": "typescript", ".tsx": "tsx",
    ".go": "go", ".rs": "rust", ".java": "java", ".rb": "ruby",
    ".c": "c", ".h": "c", ".cpp": "cpp", ".cc": "cpp", ".hpp": "cpp", ".cxx": "cpp",
}

# The single source of truth for "which file extensions does the
# similarity engine consider source code" -- both engine.py and
# negative_control.py import this rather than maintaining their own copy
# (they previously duplicated an identical set, risking drift).
SOURCE_SUFFIXES = {".py"} | set(SUFFIX_TO_ASTGREP_LANG)

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


def treesitter_structural_shape(source: str, language: str) -> list[str] | None:
    """Return a sequence of tree-sitter node-kind names (via ast-grep-py)
    for `language`, ignoring identifiers/literal values, or None if the
    language isn't supported or the source doesn't parse. `language` is an
    ast-grep-py language identifier (e.g. "javascript", "go", "rust",
    "java"), not a file extension -- see SUFFIX_TO_ASTGREP_LANG."""
    if SgRoot is None:
        return None
    try:
        root = SgRoot(source, language)
    except BaseException:
        # An unrecognised language string surfaces from the underlying
        # Rust library as pyo3_runtime.PanicException, which subclasses
        # BaseException directly (not Exception) -- a plain `except
        # Exception` silently fails to catch it. A source that fails to
        # parse raises an ordinary Exception subclass instead. Either way
        # this is "not available", not a bug to propagate.
        return None
    shape: list[str] = []

    def walk(node) -> None:
        shape.append(node.kind())
        for child in node.children():
            walk(child)

    walk(root.root())
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


def structural_similarity(
    source_a: str, source_b: str, *, language: str | None = None, shingle_size: int = 8
) -> tuple[float, str]:
    """Returns (score, method) where method is 'python_ast', 'treesitter:<language>',
    or 'generic_fallback'. `language` is an ast-grep-py language identifier
    (see SUFFIX_TO_ASTGREP_LANG) derived by the caller from the file being
    compared -- omit it to only try the Python/generic paths."""
    shape_a = python_structural_shape(source_a)
    shape_b = python_structural_shape(source_b)
    if shape_a is not None and shape_b is not None:
        method = "python_ast"
    elif language is not None and (ts_a := treesitter_structural_shape(source_a, language)) is not None and (
        ts_b := treesitter_structural_shape(source_b, language)
    ) is not None:
        shape_a, shape_b = ts_a, ts_b
        method = f"treesitter:{language}"
    else:
        shape_a = generic_structural_shape(source_a)
        shape_b = generic_structural_shape(source_b)
        method = "generic_fallback"
    score = jaccard(shingles(shape_a, shingle_size), shingles(shape_b, shingle_size))
    return score, method
