from cleanroom.similarity.classify import classify
from cleanroom.similarity.lexical import jaccard, lexical_similarity
from cleanroom.similarity.structural import generic_structural_shape, structural_similarity, treesitter_structural_shape


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


def test_generic_structural_shape_does_not_misread_identifiers_as_keywords():
    """Regression test: a substring/startswith-based keyword scan
    previously matched 'iffy', 'definitely(...)', 'classList.add(...)' as
    if/def/class control-flow structure. Must require word boundaries."""
    shape = generic_structural_shape("iffy = definitely(classList.add(x))\n")
    assert not any(s in ("kw:if", "kw:def", "kw:class") for s in shape)


def test_generic_structural_shape_matches_real_keywords_with_boundaries():
    shape = generic_structural_shape("if x:\n    return y\n")
    assert "kw:if" in shape
    assert "kw:return" in shape


def test_generic_structural_shape_depth_is_clamped_not_just_emitted():
    """Regression test: a stray unmatched closing bracket (plausible inside
    a string/comment, since this fallback does no string/comment stripping)
    previously drove the internal depth counter negative WITHOUT clamping
    the counter itself (only its emitted value was clamped) -- so once
    real nesting pushed the counter back above zero, every subsequent
    line's emitted depth was permanently offset by the size of that one
    stray excursion, rather than reflecting true nesting. A correctly
    clamped counter recovers exactly, with no lasting offset."""
    # A stray '}' with no matching '{' first, then two levels of real
    # brace nesting -- the clamped depth sequence must be 0, 1, 2, 2.
    source = "}\nif (x) {\n  if (y) {\n    return z;\n"
    shape = generic_structural_shape(source)
    depths = [s for s in shape if s.startswith("depth:")]
    assert depths == ["depth:0", "depth:1", "depth:2", "depth:2"]


def test_generic_structural_shape_covers_go_rust_ruby_keywords():
    assert "kw:func" in generic_structural_shape("func main() {\n")
    assert "kw:fn" in generic_structural_shape("fn main() {\n")
    assert "kw:match" in generic_structural_shape("match x {\n")
    assert "kw:loop" in generic_structural_shape("loop {\n")
    assert "kw:elsif" in generic_structural_shape("elsif x\n")
    assert "kw:unless" in generic_structural_shape("unless x\n")


def test_treesitter_javascript_real_ast_detects_identical_shape_different_names():
    a = "function foo(x, y) { if (x) { return y; } }"
    b = "function bar(p, q) { if (p) { return q; } }"
    shape_a = treesitter_structural_shape(a, "javascript")
    shape_b = treesitter_structural_shape(b, "javascript")
    assert shape_a is not None and shape_b is not None
    assert shape_a == shape_b  # identical AST shape despite different identifiers


def test_treesitter_go_rust_java_all_produce_real_shapes():
    assert treesitter_structural_shape("func main() {}\n", "go") is not None
    assert treesitter_structural_shape("fn main() {}\n", "rust") is not None
    assert treesitter_structural_shape("class Foo { void bar() {} }\n", "java") is not None


def test_treesitter_unsupported_language_returns_none_not_raises():
    assert treesitter_structural_shape("whatever", "not-a-real-language") is None


def test_treesitter_unparseable_source_returns_none_not_raises():
    # ast-grep-py is generally tolerant/error-recovering, but this must
    # never raise regardless -- a parse failure is "not available", not a
    # crash.
    result = treesitter_structural_shape("\x00\x01 not real code {{{", "javascript")
    assert result is None or isinstance(result, list)


def test_structural_similarity_uses_treesitter_for_javascript_files():
    a = "function foo(x, y) { if (x) { return y; } }"
    b = "function bar(p, q) { if (p) { return q; } }"
    score, method = structural_similarity(a, b, language="javascript")
    assert method == "treesitter:javascript"
    assert score == 1.0  # identical shape


def test_structural_similarity_falls_back_to_generic_for_unsupported_language():
    score, method = structural_similarity("if x then y end", "if p then q end", language="cobol-does-not-exist")
    assert method == "generic_fallback"
