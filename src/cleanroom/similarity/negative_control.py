"""Part XXXVI: negative-control testing.

Computes a background similarity level by comparing the implementation
against unrelated projects sharing the same language/framework, so common
boilerplate isn't mistaken for copying.
"""

from __future__ import annotations

from pathlib import Path
from statistics import mean

from cleanroom.similarity.lexical import lexical_similarity
from cleanroom.similarity.structural import structural_similarity

SOURCE_SUFFIXES = {".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs", ".java", ".rb", ".c", ".cpp", ".h"}


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


def background_scores(implementation_text: str, negative_control_roots: list[Path]) -> dict[str, float]:
    """Returns {'lexical': avg_score, 'structural': avg_score} across every
    file in every configured negative-control project. Empty dict if no
    negative-control projects are configured -- callers must treat that as
    "no background available", not as a background of zero."""
    lexical_scores: list[float] = []
    structural_scores: list[float] = []
    for root in negative_control_roots:
        for text in _read_files(root):
            lexical_scores.append(lexical_similarity(implementation_text, text))
            structural_scores.append(structural_similarity(implementation_text, text)[0])
    result = {}
    if lexical_scores:
        result["lexical"] = mean(lexical_scores)
    if structural_scores:
        result["structural"] = mean(structural_scores)
    return result
