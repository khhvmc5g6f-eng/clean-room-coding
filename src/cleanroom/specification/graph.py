"""Part XIX: the requirement graph.

Requirement -> Feature -> Screen/API -> Acceptance Test -> Implementation ->
Verification -> Evidence, stored as flat, schema-validated JSON nodes so
completeness can be computed mechanically rather than asserted.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cleanroom.contamination import Contamination
from cleanroom.schema_registry import validate

GRAPH_FILENAME = "requirements.json"


class RequirementGraph:
    def __init__(self, nodes: list[dict[str, Any]] | None = None):
        self.nodes: dict[str, dict[str, Any]] = {n["id"]: n for n in (nodes or [])}

    @classmethod
    def load(cls, path: Path) -> "RequirementGraph":
        if not path.is_file():
            return cls([])
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls(data.get("nodes", []))

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"nodes": list(self.nodes.values())}, f, indent=2, sort_keys=True)

    def add(self, node: dict[str, Any]) -> None:
        errors = validate(node, "requirement.schema.json")
        if errors:
            raise ValueError(f"Invalid requirement node {node.get('id')}: {errors}")
        self.nodes[node["id"]] = node

    def handoff_eligible_nodes(self) -> list[dict[str, Any]]:
        """Part XVI: only observable_requirement nodes at C0 may cross to Zone H."""
        eligible = []
        for node in self.nodes.values():
            if node["classification"] != "observable_requirement":
                continue
            level = node.get("contamination_level")
            if level is None or Contamination(level).handoff_eligible():
                eligible.append(node)
        return eligible

    def source_implementation_details(self) -> list[dict[str, Any]]:
        """Nodes explicitly excluded from handoff per Part XVI."""
        return [n for n in self.nodes.values() if n["classification"] == "source_implementation_detail"]

    def traceability_report(self) -> dict[str, Any]:
        """Part XXXIII: completion/coverage percentages -- never inflated to 100%
        just because everything written so far passes."""
        total = len(self.nodes)
        if total == 0:
            return {
                "total": 0, "verified": 0, "implemented": 0, "blocked": 0,
                "excluded": 0, "verified_percent": 0.0, "completion_percent": 0.0,
            }
        by_status: dict[str, int] = {}
        for node in self.nodes.values():
            by_status[node["status"]] = by_status.get(node["status"], 0) + 1
        verified = by_status.get("verified", 0)
        implemented = by_status.get("implemented", 0)
        blocked = by_status.get("blocked", 0)
        excluded = by_status.get("excluded", 0)
        eligible_for_completion = total - excluded
        return {
            "total": total,
            "by_status": by_status,
            "verified": verified,
            "implemented": implemented,
            "blocked": blocked,
            "excluded": excluded,
            "verified_percent": round(100 * verified / total, 1),
            "completion_percent": round(100 * verified / eligible_for_completion, 1) if eligible_for_completion else 0.0,
        }

    def blockers(self) -> list[dict[str, Any]]:
        return [
            {"id": n["id"], "statement": n["statement"], **n.get("blocker", {})}
            for n in self.nodes.values()
            if n["status"] == "blocked"
        ]
