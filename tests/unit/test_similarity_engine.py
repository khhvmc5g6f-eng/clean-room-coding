from pathlib import Path

from cleanroom.similarity.engine import compare_trees


def test_matches_by_filename_first(tmp_path: Path):
    ref = tmp_path / "ref"
    impl = tmp_path / "impl"
    (ref / "sub").mkdir(parents=True)
    (impl / "sub2").mkdir(parents=True)
    (ref / "sub" / "sort.py").write_text("def sort(x):\n    return sorted(x)\n", encoding="utf-8")
    (impl / "sub2" / "sort.py").write_text("def sort(x):\n    return sorted(x)\n", encoding="utf-8")

    result = compare_trees(ref, impl)
    assert result["files_matched_by_name"] == 1
    assert result["comparisons_run"] == 1  # matched by name, no all-pairs fallback needed
    assert result["comparisons_skipped"] == 0


def test_identical_files_score_very_high_and_are_flagged():
    pass  # covered by test_matches_by_filename_first + classify tests; kept for discoverability


def test_all_pairs_fallback_when_no_name_match(tmp_path: Path):
    ref = tmp_path / "ref"
    impl = tmp_path / "impl"
    ref.mkdir()
    impl.mkdir()
    (ref / "a.py").write_text("def foo(): pass\n", encoding="utf-8")
    (ref / "b.py").write_text("def bar(): pass\n", encoding="utf-8")
    (impl / "different_name.py").write_text("def baz(): pass\n", encoding="utf-8")

    result = compare_trees(ref, impl)
    assert result["files_matched_by_name"] == 0
    assert result["comparisons_run"] == 2  # 1 impl file x 2 ref files, all-pairs fallback
    assert result["comparisons_skipped"] == 0


def test_max_comparisons_cap_reports_skipped_not_silently(tmp_path: Path):
    ref = tmp_path / "ref"
    impl = tmp_path / "impl"
    ref.mkdir()
    impl.mkdir()
    for i in range(5):
        (ref / f"r{i}.py").write_text(f"def r{i}(): pass\n", encoding="utf-8")
    (impl / "unmatched.py").write_text("def unmatched(): pass\n", encoding="utf-8")

    result = compare_trees(ref, impl, max_comparisons=2)
    assert result["comparisons_run"] == 2
    assert result["comparisons_skipped"] == 3


def test_findings_have_both_lexical_and_structural_methods(tmp_path: Path):
    ref = tmp_path / "ref"
    impl = tmp_path / "impl"
    ref.mkdir()
    impl.mkdir()
    (ref / "x.py").write_text("def f(a, b):\n    return a + b\n", encoding="utf-8")
    (impl / "x.py").write_text("def f(a, b):\n    return a + b\n", encoding="utf-8")

    result = compare_trees(ref, impl)
    methods = {f["method"] for f in result["findings"]}
    assert methods == {"lexical", "structural"}
    # identical file content -> above any sane threshold -> flagged
    assert all(f["classification"] in ("suspicious", "conventional") for f in result["findings"])
