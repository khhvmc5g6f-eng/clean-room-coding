"""Directory-level similarity orchestration -- wires lexical/structural/
classify/negative_control into a single `compare_trees()` call the CLI can
run (`cleanroom similarity`). Fills the ROADMAP.md gap: the per-pair engine
existed with no command driving it across two whole codebases.

Matching strategy (documented, not silently capped): files are matched by
identical relative path/basename first (the common case when refactoring
in place), then, only if nothing matched by name, by an all-pairs sweep
bounded by `max_comparisons` -- if the bound is hit, the excess pairs are
reported as `skipped`, never silently dropped.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cleanroom.similarity.classify import classify
from cleanroom.similarity.lexical import lexical_similarity
from cleanroom.similarity.negative_control import background_scores
from cleanroom.similarity.structural import SOURCE_SUFFIXES, SUFFIX_TO_ASTGREP_LANG, structural_similarity
IGNORE_DIRNAMES = {".git", "__pycache__", ".venv", "node_modules", "dist", "build"}


def _source_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return [
        p for p in sorted(root.rglob("*"))
        if p.is_file() and p.suffix in SOURCE_SUFFIXES and not any(part in IGNORE_DIRNAMES for part in p.parts)
    ]


@dataclass
class ComparisonPlan:
    pairs: list[tuple[Path, Path]]
    matched_by_name: int
    skipped: int


def _plan_pairs(reference_root: Path, implementation_root: Path, *, max_comparisons: int) -> ComparisonPlan:
    ref_files = _source_files(reference_root)
    impl_files = _source_files(implementation_root)

    # A basename can legitimately appear more than once in the reference
    # tree (e.g. "utils.py" in two different reference directories) -- a
    # single-file dict here previously kept only the last one sorted,
    # silently losing a comparison against the other(s) without ever
    # counting it in `skipped`. Match against every same-named candidate.
    ref_by_name: dict[str, list[Path]] = {}
    for f in ref_files:
        ref_by_name.setdefault(f.name, []).append(f)

    pairs: list[tuple[Path, Path]] = []
    matched_by_name = 0
    unmatched_impl: list[Path] = []
    for impl_file in impl_files:
        ref_matches = ref_by_name.get(impl_file.name)
        if ref_matches:
            for ref_match in ref_matches:
                pairs.append((ref_match, impl_file))
                matched_by_name += 1
        else:
            unmatched_impl.append(impl_file)

    skipped = 0
    if unmatched_impl and ref_files:
        remaining_budget = max(max_comparisons - len(pairs), 0)
        # Round-robin across unmatched impl files rather than a flat slice
        # ordered by impl file: a flat slice can give early-sorted impl
        # files full ref coverage while later-sorted ones get none at all,
        # even though a copied file could be any of them. Round-robin
        # spreads the budget so truncation isn't file-order-biased.
        per_impl_pairs = [[(r, i) for r in ref_files] for i in unmatched_impl]
        budgeted: list[tuple[Path, Path]] = []
        round_index = 0
        while len(budgeted) < remaining_budget and any(per_impl_pairs):
            for bucket in per_impl_pairs:
                if round_index < len(bucket) and len(budgeted) < remaining_budget:
                    budgeted.append(bucket[round_index])
            round_index += 1
            if round_index >= max((len(b) for b in per_impl_pairs), default=0):
                break
        total_available = sum(len(b) for b in per_impl_pairs)
        skipped = total_available - len(budgeted)
        pairs.extend(budgeted)

    return ComparisonPlan(pairs=pairs, matched_by_name=matched_by_name, skipped=skipped)


def compare_trees(
    reference_root: Path,
    implementation_root: Path,
    *,
    lexical_threshold: float = 0.15,
    structural_threshold: float = 0.15,
    negative_control_roots: list[Path] | None = None,
    max_comparisons: int = 2000,
) -> dict[str, Any]:
    negative_control_roots = negative_control_roots or []
    plan = _plan_pairs(reference_root, implementation_root, max_comparisons=max_comparisons)

    # Cache per impl-file text and background score: an impl file compared
    # against multiple reference files (the all-pairs fallback) previously
    # re-read every negative-control file and recomputed its background
    # score once per pair, rather than once per impl file.
    impl_text_cache: dict[Path, str] = {}
    background_cache: dict[Path, dict[str, float]] = {}

    findings = []
    for i, (ref_file, impl_file) in enumerate(plan.pairs):
        ref_text = ref_file.read_text(encoding="utf-8", errors="replace")
        language = SUFFIX_TO_ASTGREP_LANG.get(impl_file.suffix)
        if impl_file not in impl_text_cache:
            impl_text_cache[impl_file] = impl_file.read_text(encoding="utf-8", errors="replace")
            background_cache[impl_file] = (
                background_scores(impl_text_cache[impl_file], negative_control_roots, language=language)
                if negative_control_roots
                else {}
            )
        impl_text = impl_text_cache[impl_file]
        background = background_cache[impl_file]
        ref_rel = str(ref_file.relative_to(reference_root))
        impl_rel = str(impl_file.relative_to(implementation_root))

        lex_score = lexical_similarity(ref_text, impl_text)
        findings.append(
            classify(
                finding_id=f"SIM-LEX-{i:05d}", method="lexical", reference_ref=ref_rel,
                implementation_ref=impl_rel, score=lex_score, threshold=lexical_threshold,
                background_score=background.get("lexical"),
            ).to_dict()
        )

        struct_score, struct_method = structural_similarity(ref_text, impl_text, language=language)
        # A generic bracket/keyword fallback is real but weaker evidence
        # than an actual AST/tree-sitter comparison (see structural.py's
        # docstring) -- down-weight it by requiring a higher score before
        # it's flagged, rather than silently giving it the same confidence
        # as a real parse.
        effective_threshold = structural_threshold * 1.5 if struct_method == "generic_fallback" else structural_threshold
        finding = classify(
            finding_id=f"SIM-STRUCT-{i:05d}", method="structural", reference_ref=ref_rel,
            implementation_ref=impl_rel, score=struct_score, threshold=effective_threshold,
            background_score=background.get("structural"),
        )
        finding_dict = finding.to_dict()
        finding_dict["structural_method"] = struct_method
        findings.append(finding_dict)

    return {
        "reference_root": str(reference_root),
        "implementation_root": str(implementation_root),
        "files_matched_by_name": plan.matched_by_name,
        "comparisons_run": len(plan.pairs),
        "comparisons_skipped": plan.skipped,
        "findings": findings,
    }
