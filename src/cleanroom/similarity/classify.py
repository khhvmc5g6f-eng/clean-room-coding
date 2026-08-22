"""Part XXXV: similarity explanation and classification.

The automated classifier only ever assigns {coincidental, conventional,
suspicious} -- never REQUIRED, CONSTRAINED or MATERIAL. Those three
specifically require knowledge this engine doesn't have (whether a pattern
is protocol-mandated, whether alternatives were genuinely scarce, or a
legal judgement that similarity is inconsistent with independent creation)
and must be assigned by a human/panel review via `apply_review`. This is a
deliberate refusal to let deterministic tooling manufacture a legal
conclusion (Part LXVI-LXVIII).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

AUTOMATIC_CLASSIFICATIONS = ("coincidental", "conventional", "suspicious")
REVIEW_ONLY_CLASSIFICATIONS = ("required", "constrained", "material")
ALL_CLASSIFICATIONS = AUTOMATIC_CLASSIFICATIONS + REVIEW_ONLY_CLASSIFICATIONS


@dataclass
class SimilarityFinding:
    id: str
    method: str
    reference_ref: str
    implementation_ref: str
    score: float
    classification: str
    background_score: float | None = None
    explanation: str = ""
    requires_finding: bool = False
    reviewer: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if d["background_score"] is None:
            del d["background_score"]
        if d["reviewer"] is None:
            del d["reviewer"]
        return d


def classify(
    *,
    finding_id: str,
    method: str,
    reference_ref: str,
    implementation_ref: str,
    score: float,
    threshold: float,
    background_score: float | None = None,
    background_margin: float = 0.10,
) -> SimilarityFinding:
    if score < threshold:
        return SimilarityFinding(
            id=finding_id, method=method, reference_ref=reference_ref,
            implementation_ref=implementation_ref, score=score,
            background_score=background_score, classification="coincidental",
            explanation=f"Score {score:.3f} is below the configured threshold ({threshold:.3f}).",
            requires_finding=False,
        )

    if background_score is not None and (score - background_score) <= background_margin:
        return SimilarityFinding(
            id=finding_id, method=method, reference_ref=reference_ref,
            implementation_ref=implementation_ref, score=score,
            background_score=background_score, classification="conventional",
            explanation=(
                f"Score {score:.3f} is within {background_margin:.2f} of the negative-control "
                f"background level ({background_score:.3f}) -- consistent with common framework/"
                "language expression rather than copying (Part XXXVI)."
            ),
            requires_finding=False,
        )

    return SimilarityFinding(
        id=finding_id, method=method, reference_ref=reference_ref,
        implementation_ref=implementation_ref, score=score,
        background_score=background_score, classification="suspicious",
        explanation=(
            f"Score {score:.3f} exceeds the threshold ({threshold:.3f}) and "
            + (
                f"exceeds the negative-control background ({background_score:.3f}) by more than {background_margin:.2f}."
                if background_score is not None
                else "no negative-control background score is available to rule out common boilerplate."
            )
        ),
        requires_finding=True,
    )


def apply_review(
    finding: SimilarityFinding,
    *,
    classification: str,
    explanation: str,
    reviewer: str,
) -> SimilarityFinding:
    if classification not in ALL_CLASSIFICATIONS:
        raise ValueError(f"Unknown classification '{classification}'")
    finding.classification = classification
    finding.explanation = explanation
    finding.reviewer = reviewer
    finding.requires_finding = classification in ("suspicious", "material")
    return finding
