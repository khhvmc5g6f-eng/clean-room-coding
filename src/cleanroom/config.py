"""Loads and validates .cleanroom.yml (Part IV)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from cleanroom.exit_codes import ConfigurationError
from cleanroom.schema_registry import validate

DEFAULT_CONFIG_FILENAME = ".cleanroom.yml"


@dataclass
class ProjectConfig:
    path: Path
    data: dict[str, Any]

    @property
    def project_id(self) -> str:
        return self.data["project"]["id"]

    @property
    def clean_room_level(self) -> str:
        return self.data["clean_room_level"]

    def zone_path(self, zone: str) -> Path:
        key = {"R": "reference_path", "H": "handoff_path", "I": "implementation_path"}[zone]
        return self.path.parent / self.data["zones"][key]

    def required_markets(self) -> list[str]:
        return self.data.get("jurisdiction", {}).get("required_markets", [])


def load_config(path: Path) -> ProjectConfig:
    if not path.is_file():
        raise ConfigurationError(f"No config found at {path}. Run 'cleanroom init' first.")
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    errors = validate(data, "config.schema.json")
    if errors:
        joined = "\n".join(f"  - {e}" for e in errors)
        raise ConfigurationError(
            f"{path} failed schema validation ({len(errors)} error(s)):\n{joined}"
        )
    return ProjectConfig(path=path, data=data)


def find_config(start: Path, *, explicit_path: Path | None = None) -> Path:
    """Search upward from `start` for .cleanroom.yml, like git does for .git.

    If `explicit_path` is given (the CLI's --config flag), it overrides
    discovery entirely -- it must exist, or this raises immediately rather
    than silently falling back to upward search.
    """
    if explicit_path is not None:
        if not explicit_path.is_file():
            raise ConfigurationError(f"--config was given as {explicit_path}, but that file does not exist.")
        return explicit_path
    current = start.resolve()
    for candidate in [current, *current.parents]:
        candidate_file = candidate / DEFAULT_CONFIG_FILENAME
        if candidate_file.is_file():
            return candidate_file
    raise ConfigurationError(
        f"No {DEFAULT_CONFIG_FILENAME} found in {start} or any parent directory. "
        "Run 'cleanroom init' to create a new project."
    )


def default_config(project_name: str, project_id: str, *, target_language: str = "same-as-reference") -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "project": {"name": project_name, "id": project_id},
        "zones": {
            "reference_path": "zone-r",
            "handoff_path": "zone-h",
            "implementation_path": "zone-i",
            "strict_isolation": True,
        },
        "clean_room_level": "CR2",
        "implementation": {"target_language": target_language},
        "jurisdiction": {"required_markets": ["gb"], "informational_markets": ["us"]},
        "dependency_policy": {
            "allowed_licences": ["MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "ISC"],
            "denied_licences": [],
            "unknown_licence_action": "block",
        },
        "similarity": {"lexical_threshold": 0.15, "structural_threshold": 0.15},
        "providers": {"orchestration": "claude-code", "panel_diversity_required": False, "panel_size": 1},
        "evidence": {"retention_days": 0, "redact_secrets": True},
        "approval_gates": {"human_signoff_required_for_release": True, "human_signoff_required_for_handoff": False},
        "release_policy": {
            "require_technical_gate": True,
            "require_provenance_gate": True,
            "require_contamination_gate": True,
            "block_on_red_required_jurisdiction": True,
            "require_panel_diversity_gate": False,
        },
    }
