from pathlib import Path

from cleanroom.similarity.negative_control import background_scores


def test_background_scores_empty_without_negative_controls():
    assert background_scores("def f(): pass\n", []) == {}


def test_background_scores_computes_lexical_and_structural(tmp_path: Path):
    control_root = tmp_path / "control"
    control_root.mkdir()
    (control_root / "other.py").write_text("def g(): pass\n", encoding="utf-8")

    result = background_scores("def f(): pass\n", [control_root])
    assert "lexical" in result
    assert "structural" in result


def test_background_scores_uses_the_given_language_for_structural_comparison(tmp_path: Path, monkeypatch):
    """Regression test: background_scores() previously never passed a
    `language` hint through to structural_similarity(), so a background
    score for a non-Python implementation was always computed via the
    weaker generic_fallback method -- even when the actual foreground
    reference-vs-implementation comparison used real tree-sitter. A
    background computed by a different, weaker method than the
    foreground it's meant to be compared against isn't a valid
    background. Confirmed by capturing the method structural_similarity
    was actually called with."""
    control_root = tmp_path / "control"
    control_root.mkdir()
    (control_root / "other.js").write_text("function bar(y) { return y + 2; }", encoding="utf-8")

    seen_languages = []
    import cleanroom.similarity.negative_control as nc_module

    real_structural_similarity = nc_module.structural_similarity

    def spy(source_a, source_b, *, language=None, shingle_size=8):
        seen_languages.append(language)
        return real_structural_similarity(source_a, source_b, language=language, shingle_size=shingle_size)

    monkeypatch.setattr(nc_module, "structural_similarity", spy)

    background_scores("function foo(x) { return x + 1; }", [control_root], language="javascript")
    assert seen_languages == ["javascript"]


def test_background_scores_defaults_to_no_language_hint_when_omitted(tmp_path: Path, monkeypatch):
    """Backward compatibility: omitting `language` (the default) must
    still work exactly as before -- structural_similarity() falls back to
    python_ast/generic_fallback on its own."""
    control_root = tmp_path / "control"
    control_root.mkdir()
    (control_root / "other.py").write_text("def g(): pass\n", encoding="utf-8")

    seen_languages = []
    import cleanroom.similarity.negative_control as nc_module

    real_structural_similarity = nc_module.structural_similarity

    def spy(source_a, source_b, *, language=None, shingle_size=8):
        seen_languages.append(language)
        return real_structural_similarity(source_a, source_b, language=language, shingle_size=shingle_size)

    monkeypatch.setattr(nc_module, "structural_similarity", spy)
    background_scores("def f(): pass\n", [control_root])
    assert seen_languages == [None]
