"""Part XXI: the sanitisation differential.

Keeps RAW_ANALYSIS (Zone R-derived, never leaves Zone R/its evidence store)
and SANITISED_SPECIFICATION (candidate for Zone H) as distinct artefacts,
plus a machine-readable record of what was removed/transformed, why, and
who approved it. RAW_ANALYSIS is never written into the handoff bundle.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from cleanroom.sanitisation.scanner import SanitisationFinding


@dataclass
class DifferentialEntry:
    raw_excerpt: str
    sanitised_excerpt: str | None  # None means removed entirely
    action: str  # "removed" | "transformed" | "retained"
    reason: str
    approved_by: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SanitisationReport:
    source_document: str
    raw_analysis_ref: str
    findings: list[SanitisationFinding] = field(default_factory=list)
    entries: list[DifferentialEntry] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_document": self.source_document,
            "raw_analysis_ref": self.raw_analysis_ref,
            "findings": [f.to_dict() for f in self.findings],
            "entries": [e.to_dict() for e in self.entries],
            "blocked": any(f.severity == "blocking" for f in self.findings),
        }

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, sort_keys=True)
