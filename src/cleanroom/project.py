"""Ties config, zones and the evidence ledger together into one project handle."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from cleanroom.config import DEFAULT_CONFIG_FILENAME, ProjectConfig, find_config, load_config
from cleanroom.evidence import EvidenceLedger


@dataclass
class Project:
    config: ProjectConfig
    root: Path
    evidence: EvidenceLedger

    @classmethod
    def discover(cls, start: Path, *, explicit_config_path: Path | None = None) -> "Project":
        config_path = find_config(start, explicit_path=explicit_config_path)
        config = load_config(config_path)
        root = config_path.parent
        evidence = EvidenceLedger(root / "evidence")
        return cls(config=config, root=root, evidence=evidence)

    @property
    def zone_r(self) -> Path:
        return self.config.zone_path("R")

    @property
    def zone_h(self) -> Path:
        return self.config.zone_path("H")

    @property
    def zone_i(self) -> Path:
        return self.config.zone_path("I")

    @property
    def config_path(self) -> Path:
        return self.root / DEFAULT_CONFIG_FILENAME
