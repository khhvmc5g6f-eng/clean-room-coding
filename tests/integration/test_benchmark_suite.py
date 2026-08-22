"""Part LXXVI: exercises the licence-discovery and similarity engines
against synthetic, wholly-owned-by-this-project fixtures, so the tool's
behaviour is evaluated without relying on disputed third-party code.
"""

from pathlib import Path

from cleanroom.licence.discovery import discover
from cleanroom.similarity.classify import classify
from cleanroom.similarity.lexical import lexical_similarity
from cleanroom.similarity.structural import structural_similarity

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "benchmark"


def test_permissive_app_detected_as_mit():
    findings = discover(FIXTURES / "permissive-app")
    concluded = {f.concluded for f in findings}
    assert "MIT" in concluded


def test_gpl_app_detected_as_gpl():
    findings = discover(FIXTURES / "gpl-app")
    concluded = {f.concluded for f in findings}
    assert "GPL-3.0-only" in concluded


def test_seeded_copying_is_caught(threshold: float = 0.15):
    original = (FIXTURES / "gpl-app" / "wobble_sort.py").read_text(encoding="utf-8")
    cloned = (FIXTURES / "contaminated-clone" / "sorter.py").read_text(encoding="utf-8")

    lex_score = lexical_similarity(original, cloned)
    struct_score, method = structural_similarity(original, cloned)

    assert lex_score > 0.35, "renamed-only clone should still score well above the similarity threshold lexically"
    assert struct_score > 0.9, "structure is untouched -- AST shape should be nearly identical"
    assert method == "python_ast"

    finding = classify(
        finding_id="benchmark-1", method="structural", reference_ref="gpl-app/wobble_sort.py",
        implementation_ref="contaminated-clone/sorter.py", score=struct_score, threshold=threshold,
    )
    assert finding.classification == "suspicious"
    assert finding.requires_finding is True


def test_independent_implementation_is_not_flagged(threshold: float = 0.15):
    original = (FIXTURES / "gpl-app" / "wobble_sort.py").read_text(encoding="utf-8")
    independent = (FIXTURES / "independent-clone" / "ordering.py").read_text(encoding="utf-8")

    struct_score, _ = structural_similarity(original, independent)
    finding = classify(
        finding_id="benchmark-2", method="structural", reference_ref="gpl-app/wobble_sort.py",
        implementation_ref="independent-clone/ordering.py", score=struct_score, threshold=threshold,
    )
    assert finding.classification == "coincidental", (
        f"independent implementation scored {struct_score:.3f}, should be below threshold {threshold}"
    )
    assert finding.requires_finding is False
