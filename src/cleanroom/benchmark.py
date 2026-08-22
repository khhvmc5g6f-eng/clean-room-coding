"""Parts LXXVI-LXXVII: a measured precision/recall report for the
similarity engine, run against `tests/fixtures/benchmark/`'s small,
hand-built, wholly-owned-by-this-project ground-truth corpus.

This is deliberately NOT a large-scale or academic benchmark -- it is 8
synthetic (reference, implementation) pairs with a human-assigned
ground_truth label (see `manifest.yml`), used to compute real precision/
recall/F1 numbers instead of leaving Part LXXVII as an unmeasured claim.
A small corpus means these numbers describe how the engine behaves on
these specific cases, not a statistically representative sample of all
possible clean-room reimplementations -- report them as that, not as
general accuracy claims.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from cleanroom.similarity.classify import classify
from cleanroom.similarity.lexical import lexical_similarity
from cleanroom.similarity.structural import structural_similarity

MANIFEST_FILENAME = "manifest.yml"
_POSITIVE_CLASSIFICATIONS = {"suspicious", "material"}

_PACKAGE_DIR = Path(__file__).resolve().parent


def default_fixtures_dir() -> Path | None:
    """The benchmark fixtures live under `tests/fixtures/benchmark/` in
    the source repository, not inside the installed package (like
    `jurisdiction/resolver.py`'s pack directory, `pyproject.toml` only
    ships `src/cleanroom`) -- so this only resolves when running from a
    git checkout, not a bare `pip install cleanroom`. Returns None rather
    than raising when not found, so callers can report that plainly."""
    for parent in _PACKAGE_DIR.parents:
        candidate = parent / "tests" / "fixtures" / "benchmark"
        if (candidate / MANIFEST_FILENAME).is_file():
            return candidate
    return None


@dataclass
class CaseResult:
    case_id: str
    language: str
    ground_truth: str  # "positive" | "negative"
    predicted: str  # "positive" | "negative"
    lexical_score: float
    structural_score: float
    structural_method: str
    description: str

    @property
    def outcome(self) -> str:
        if self.ground_truth == "positive" and self.predicted == "positive":
            return "true_positive"
        if self.ground_truth == "negative" and self.predicted == "negative":
            return "true_negative"
        if self.ground_truth == "negative" and self.predicted == "positive":
            return "false_positive"
        return "false_negative"

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id, "language": self.language, "ground_truth": self.ground_truth,
            "predicted": self.predicted, "outcome": self.outcome,
            "lexical_score": round(self.lexical_score, 4), "structural_score": round(self.structural_score, 4),
            "structural_method": self.structural_method, "description": self.description,
        }


def load_manifest(fixtures_dir: Path) -> list[dict[str, Any]]:
    manifest_path = fixtures_dir / MANIFEST_FILENAME
    with open(manifest_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data["cases"]


def run_case(fixtures_dir: Path, case: dict[str, Any], *, threshold: float = 0.15) -> CaseResult:
    ref_text = (fixtures_dir / case["reference"]).read_text(encoding="utf-8")
    impl_text = (fixtures_dir / case["implementation"]).read_text(encoding="utf-8")
    language = None if case["language"] == "python" else case["language"]

    lex_score = lexical_similarity(ref_text, impl_text)
    struct_score, struct_method = structural_similarity(ref_text, impl_text, language=language)

    finding = classify(
        finding_id=case["id"], method="structural", reference_ref=case["reference"],
        implementation_ref=case["implementation"], score=struct_score, threshold=threshold,
    )
    predicted = "positive" if finding.classification in _POSITIVE_CLASSIFICATIONS else "negative"

    return CaseResult(
        case_id=case["id"], language=case["language"], ground_truth=case["ground_truth"], predicted=predicted,
        lexical_score=lex_score, structural_score=struct_score, structural_method=struct_method,
        description=case["description"],
    )


def run_benchmark(fixtures_dir: Path, *, threshold: float = 0.15) -> dict[str, Any]:
    cases = load_manifest(fixtures_dir)
    results = [run_case(fixtures_dir, case, threshold=threshold) for case in cases]

    tp = sum(1 for r in results if r.outcome == "true_positive")
    tn = sum(1 for r in results if r.outcome == "true_negative")
    fp = sum(1 for r in results if r.outcome == "false_positive")
    fn = sum(1 for r in results if r.outcome == "false_negative")

    precision = tp / (tp + fp) if (tp + fp) else None
    recall = tp / (tp + fn) if (tp + fn) else None
    f1 = (2 * precision * recall / (precision + recall)) if precision and recall and (precision + recall) else None
    accuracy = (tp + tn) / len(results) if results else None

    return {
        "threshold": threshold,
        "case_count": len(results),
        "confusion_matrix": {"true_positive": tp, "true_negative": tn, "false_positive": fp, "false_negative": fn},
        "precision": round(precision, 4) if precision is not None else None,
        "recall": round(recall, 4) if recall is not None else None,
        "f1": round(f1, 4) if f1 is not None else None,
        "accuracy": round(accuracy, 4) if accuracy is not None else None,
        "cases": [r.to_dict() for r in results],
        "caveat": (
            "Small, hand-built, synthetic corpus (8 cases) -- these numbers describe behaviour on these "
            "specific cases, not a statistically representative measurement of general clean-room-reimplementation "
            "accuracy. See tests/fixtures/benchmark/README.md."
        ),
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Similarity engine benchmark report",
        "",
        f"**Cases:** {report['case_count']} -- "
        f"**Precision:** {report['precision']} -- **Recall:** {report['recall']} -- "
        f"**F1:** {report['f1']} -- **Accuracy:** {report['accuracy']}",
        "",
        f"> {report['caveat']}",
        "",
        "| Case | Language | Ground truth | Predicted | Outcome | Lexical | Structural (method) |",
        "|---|---|---|---|---|---|---|",
    ]
    for c in report["cases"]:
        lines.append(
            f"| {c['case_id']} | {c['language']} | {c['ground_truth']} | {c['predicted']} | {c['outcome']} | "
            f"{c['lexical_score']} | {c['structural_score']} ({c['structural_method']}) |"
        )
    return "\n".join(lines) + "\n"
