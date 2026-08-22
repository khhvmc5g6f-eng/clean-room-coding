from pathlib import Path

from cleanroom.benchmark import default_fixtures_dir, render_markdown, run_benchmark

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "benchmark"


def test_default_fixtures_dir_resolves_from_a_git_checkout():
    resolved = default_fixtures_dir()
    assert resolved is not None
    assert resolved.resolve() == FIXTURES.resolve()


def test_run_benchmark_covers_all_manifest_cases():
    report = run_benchmark(FIXTURES)
    assert report["case_count"] == 8
    assert len(report["cases"]) == 8


def test_run_benchmark_confusion_matrix_sums_to_case_count():
    report = run_benchmark(FIXTURES)
    matrix = report["confusion_matrix"]
    assert sum(matrix.values()) == report["case_count"]


def test_run_benchmark_recall_is_perfect_no_copy_goes_undetected():
    """Every positive (should-be-flagged) case in this hand-built corpus
    is in fact flagged -- recall is the more safety-critical of the two
    metrics for a clean-room compliance tool (a missed copy is worse than
    a false alarm a human reviewer then clears)."""
    report = run_benchmark(FIXTURES)
    assert report["recall"] == 1.0
    assert report["confusion_matrix"]["false_negative"] == 0


def test_run_benchmark_documents_the_known_false_positive():
    """Regression test for a real, measured finding, not a bug to hide:
    js-independent-clone scores just above the default 0.15 structural
    threshold (~0.18) even though it's a genuinely independent
    reimplementation -- an honest limitation of the current default
    threshold for JS's tree-sitter node-kind vocabulary. This must stay
    visible in the report, not be silently 'fixed' by loosening the
    fixture until it passes."""
    report = run_benchmark(FIXTURES)
    js_case = next(c for c in report["cases"] if c["case_id"] == "js-independent-clone")
    assert js_case["outcome"] == "false_positive"
    assert report["confusion_matrix"]["false_positive"] == 1
    assert report["precision"] < 1.0


def test_run_benchmark_caveat_present_and_not_overclaiming():
    report = run_benchmark(FIXTURES)
    assert "small" in report["caveat"].lower()
    assert "not a statistically representative" in report["caveat"]


def test_higher_threshold_would_have_avoided_the_false_positive():
    """Confirms the false positive is genuinely threshold-sensitive (not
    some other bug) -- raising the structural threshold clears it, at the
    cost of recall margin elsewhere shrinking too. Informational, not
    asserting a specific new default should be adopted."""
    report = run_benchmark(FIXTURES, threshold=0.2)
    js_case = next(c for c in report["cases"] if c["case_id"] == "js-independent-clone")
    assert js_case["outcome"] == "true_negative"


def test_render_markdown_includes_every_case_id():
    report = run_benchmark(FIXTURES)
    markdown = render_markdown(report)
    for case in report["cases"]:
        assert case["case_id"] in markdown
    assert "Precision" in markdown
