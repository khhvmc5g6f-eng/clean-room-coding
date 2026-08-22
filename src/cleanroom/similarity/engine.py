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
from cleanroom.similarity.structural import structural_similarity

SOURCE_SUFFIXES = {".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs", ".java", ".rb", ".c", ".cpp", ".h"}
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
    ref_by_name = {f.name: f for f in ref_files}

    pairs: list[tuple[Path, Path]] = []
    matched_by_name = 0
    unmatched_impl: list[Path] = []
    for impl_file in impl_files:
        ref_match = ref_by_name.get(impl_file.name)
        if ref_match is not None:
            pairs.append((ref_match, impl_file))
            matched_by_name += 1
        else:
            unmatched_impl.append(impl_file)

    skipped = 0
    if unmatched_impl and ref_files:
        remaining_budget = max(max_comparisons - len(pairs), 0)
        all_pairs = [(r, i) for i in unmatched_impl for r in ref_files]
        if len(all_pairs) > remaining_budget:
            skipped = len(all_pairs) - remaining_budget
            all_pairs = all_pairs[:remaining_budget]
        pairs.extend(all_pairs)

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

    findings = []
    for i, (ref_file, impl_file) in enumerate(plan.pairs):
        ref_text = ref_file.read_text(encoding="utf-8", errors="replace")
        impl_text = impl_file.read_text(encoding="utf-8", errors="replace")
        ref_rel = str(ref_file.relative_to(reference_root))
        impl_rel = str(impl_file.relative_to(implementation_root))

        background = background_scores(impl_text, negative_control_roots) if negative_control_roots else {}

        lex_score = lexical_similarity(ref_text, impl_text)
        findings.append(
            classify(
                finding_id=f"SIM-LEX-{i:05d}", method="lexical", reference_ref=ref_rel,
                implementation_ref=impl_rel, score=lex_score, threshold=lexical_threshold,
                background_score=background.get("lexical"),
            ).to_dict()
        )

        struct_score, struct_method = structural_similarity(ref_text, impl_text)
        finding = classify(
            finding_id=f"SIM-STRUCT-{i:05d}", method="structural", reference_ref=ref_rel,
            implementation_ref=impl_rel, score=struct_score, threshold=structural_threshold,
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
