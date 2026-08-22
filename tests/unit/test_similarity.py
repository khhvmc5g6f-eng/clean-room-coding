from cleanroom.similarity.classify import classify
from cleanroom.similarity.lexical import jaccard, lexical_similarity
from cleanroom.similarity.structural import structural_similarity


def test_identical_text_lexical_similarity_is_one():
    text = "def foo(a, b):\n    return a + b\n"
    assert lexical_similarity(text, text) == 1.0


def test_unrelated_text_lexical_similarity_is_low():
    a = "def foo(a, b):\n    return a + b\n"
    b = "class Widget:\n    def render(self):\n        pass\n"
    assert lexical_similarity(a, b) < 0.3


def test_jaccard_basic():
    assert jaccard({1, 2, 3}, {2, 3, 4}) == 2 / 4
    assert jaccard(set(), set()) == 0.0


def test_python_structural_similarity_detects_identical_shape_different_names():
    a = "def foo(x, y):\n    if x:\n        return y\n    return None\n"
    b = "def bar(p, q):\n    if p:\n        return q\n    return None\n"
    score, method = structural_similarity(a, b)
    assert method == "python_ast"
    assert score > 0.8  # same shape despite different identifiers


def test_classify_below_threshold_is_coincidental():
    finding = classify(
        finding_id="f1", method="lexical", reference_ref="ref.py", implementation_ref="impl.py",
        score=0.05, threshold=0.15,
    )
    assert finding.classification == "coincidental"
    assert not finding.requires_finding


def test_classify_above_threshold_no_background_is_suspicious():
    finding = classify(
        finding_id="f2", method="lexical", reference_ref="ref.py", implementation_ref="impl.py",
        score=0.5, threshold=0.15,
    )
    assert finding.classification == "suspicious"
    assert finding.requires_finding


def test_classify_above_threshold_but_within_background_is_conventional():
    finding = classify(
        finding_id="f3", method="structural", reference_ref="ref.py", implementation_ref="impl.py",
        score=0.5, threshold=0.15, background_score=0.45, background_margin=0.10,
    )
    assert finding.classification == "conventional"
    assert not finding.requires_finding


def test_classify_never_auto_assigns_material_or_required():
    from cleanroom.similarity.classify import AUTOMATIC_CLASSIFICATIONS

    assert "material" not in AUTOMATIC_CLASSIFICATIONS
    assert "required" not in AUTOMATIC_CLASSIFICATIONS
    assert "constrained" not in AUTOMATIC_CLASSIFICATIONS
