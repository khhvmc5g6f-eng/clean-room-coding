"""Part VIII: contamination classification, C0 (public/factual) to C5 (legally restricted)."""

from __future__ import annotations

from enum import Enum


class Contamination(str, Enum):
    C0 = "C0"  # Public factual material or independent standards.
    C1 = "C1"  # Public documentation carrying minimal expressive risk.
    C2 = "C2"  # Reference documentation containing potentially expressive material.
    C3 = "C3"  # Original source implementation.
    C4 = "C4"  # Highly sensitive implementation detail, private source or confidential material.
    C5 = "C5"  # Legally restricted material or material whose permissible use has not been established.

    @property
    def rank(self) -> int:
        return int(self.value[1])

    def handoff_eligible(self) -> bool:
        """Only C0, and sanitised derivatives explicitly re-classified as C0, may enter Zone H."""
        return self is Contamination.C0


DESCRIPTIONS = {
    Contamination.C0: "Public factual material or independent standards.",
    Contamination.C1: "Public documentation carrying minimal expressive risk.",
    Contamination.C2: "Reference documentation containing potentially expressive material.",
    Contamination.C3: "Original source implementation.",
    Contamination.C4: "Highly sensitive implementation detail, private source or confidential material.",
    Contamination.C5: "Legally restricted material or material whose permissible use has not been established.",
}
