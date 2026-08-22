"""Part XXXVI: negative-control testing.

Computes a background similarity level by comparing the implementation
against unrelated projects sharing the same language/framework, so common
boilerplate isn't mistaken for copying.
"""

from __future__ import annotations

from pathlib import Path
from statistics import mean

from cleanroom.similarity.lexical import lexical_similarity
from cleanroom.similarity.structural import SOURCE_SUFFIXES, structural_similarity


def _read_files(root: Path) -> list[str]:
    texts = []
    if not root.exists():
        return texts
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.suffix in SOURCE_SUFFIXES:
            try:
                texts.append(path.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                continue
    return texts


def background_scores(
    implementation_text: str, negative_control_roots: list[Path], *, language: str | None = None,
) -> dict[str, float]:
    """Returns {'lexical': avg_score, 'structural': avg_score} across every
    file in every configured negative-control project. Empty dict if no
    negative-control projects are configured -- callers must treat that as
    "no background available", not as a background of zero.

    `language` should be the same ast-grep-py language hint the caller used
    for the actual reference-vs-implementation comparison (see
    `structural.SUFFIX_TO_ASTGREP_LANG`). Without it, every comparison here
    silently falls back to the weaker generic bracket/keyword method even
    when the foreground comparison used real tree-sitter -- a background
    score computed by a different, weaker method than the foreground score
    it's meant to be compared against isn't a valid background at all
    (confirmed by direct reproduction: the same two JS snippets score
    identically here whether or not `language` is passed in this trivial
    case, but report `generic_fallback` instead of `treesitter:javascript`
    as their method -- a real discrepancy for less trivial inputs)."""
    lexical_scores: list[float] = []
    structural_scores: list[float] = []
    for root in negative_control_roots:
        for text in _read_files(root):
            lexical_scores.append(lexical_similarity(implementation_text, text))
            structural_scores.append(structural_similarity(implementation_text, text, language=language)[0])
    result = {}
    if lexical_scores:
        result["lexical"] = mean(lexical_scores)
    if structural_scores:
        result["structural"] = mean(structural_scores)
    return result
