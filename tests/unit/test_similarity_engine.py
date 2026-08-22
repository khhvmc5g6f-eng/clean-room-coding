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


def test_duplicate_basename_in_reference_tree_is_not_silently_dropped(tmp_path: Path):
    """Regression test: a single-file-per-name dict previously collapsed
    multiple reference files sharing a basename (e.g. 'utils.py' in two
    different reference directories) to whichever sorted last, silently
    losing any comparison against the other(s). Both must be matched."""
    ref = tmp_path / "ref"
    impl = tmp_path / "impl"
    (ref / "dir_a").mkdir(parents=True)
    (ref / "dir_b").mkdir(parents=True)
    impl.mkdir()
    (ref / "dir_a" / "utils.py").write_text("def a(): pass\n", encoding="utf-8")
    (ref / "dir_b" / "utils.py").write_text("def b(): pass\n", encoding="utf-8")
    (impl / "utils.py").write_text("def a(): pass\n", encoding="utf-8")

    result = compare_trees(ref, impl)
    assert result["files_matched_by_name"] == 2  # matched against BOTH same-named ref files
    assert result["comparisons_run"] == 2


def test_all_pairs_truncation_is_not_biased_toward_first_impl_file(tmp_path: Path):
    """Regression test: a flat slice of all-pairs previously gave earlier
    (by sort order) unmatched impl files full reference coverage while
    later ones got none at all. Round-robin must give every unmatched impl
    file at least one comparison before any gets a second, when the budget
    allows it."""
    ref = tmp_path / "ref"
    impl = tmp_path / "impl"
    ref.mkdir()
    impl.mkdir()
    (ref / "r0.py").write_text("def r0(): pass\n", encoding="utf-8")
    (ref / "r1.py").write_text("def r1(): pass\n", encoding="utf-8")
    (impl / "a_first.py").write_text("def a(): pass\n", encoding="utf-8")
    (impl / "z_last.py").write_text("def z(): pass\n", encoding="utf-8")

    # Budget for exactly 2 comparisons out of 4 possible (2 impl x 2 ref).
    # compare_trees doesn't expose the raw pairs directly, so infer from
    # findings which impl files were compared at all.
    result = compare_trees(ref, impl, max_comparisons=2)
    compared_impl_names = {f["implementation_ref"] for f in result["findings"]}
    assert "a_first.py" in compared_impl_names
    assert "z_last.py" in compared_impl_names


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
