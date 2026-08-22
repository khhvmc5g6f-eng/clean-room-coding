"""Parts VII, XXVI: the agent registry.

Records what any agent instance -- analyst, sanitiser, implementer,
orchestrator -- is allowed to see and do, so the evidence ledger can prove
who/what produced any given artefact and under what scope. This registry
does not spawn or run agents itself (Part LXV: provider-agnostic); it is
the record-keeping layer any orchestration harness (Claude Code subagents,
another framework) should write to.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from cleanroom.util import new_id, utc_now_iso

REGISTRY_FILENAME = "agents.json"


@dataclass
class AgentRecord:
    agent_id: str
    role: str
    created_utc: str
    permitted_zones: list[str]
    prohibited_paths: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    model_provider: str | None = None
    model_id: str | None = None
    supplied_documents: list[str] = field(default_factory=list)
    status: str = "ACTIVE"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


VALID_STATUSES = {
    "ACTIVE", "BLOCKED", "WAITING", "STALLED", "LOOPING",
    "FAILED", "COMPLETE", "TERMINATED",
}


class AgentRegistry:
    def __init__(self, evidence_dir: Path):
        self.path = evidence_dir / REGISTRY_FILENAME
        self._agents: dict[str, AgentRecord] = {}
        if self.path.is_file():
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for a in data.get("agents", []):
                self._agents[a["agent_id"]] = AgentRecord(**a)

    def register(
        self,
        *,
        role: str,
        permitted_zones: list[str],
        prohibited_paths: list[str] | None = None,
        tools: list[str] | None = None,
        model_provider: str | None = None,
        model_id: str | None = None,
        supplied_documents: list[str] | None = None,
    ) -> AgentRecord:
        record = AgentRecord(
            agent_id=new_id(),
            role=role,
            created_utc=utc_now_iso(),
            permitted_zones=permitted_zones,
            prohibited_paths=prohibited_paths or [],
            tools=tools or [],
            model_provider=model_provider,
            model_id=model_id,
            supplied_documents=supplied_documents or [],
        )
        self._agents[record.agent_id] = record
        self._save()
        return record

    def set_status(self, agent_id: str, status: str) -> None:
        if status not in VALID_STATUSES:
            raise ValueError(f"Invalid status '{status}'; must be one of {sorted(VALID_STATUSES)}")
        self._agents[agent_id].status = status
        self._save()

    def all(self) -> list[AgentRecord]:
        return list(self._agents.values())

    def orphaned(self) -> list[AgentRecord]:
        """Part XXVIII: no orphaned work is permitted -- agents left FAILED/
        STALLED/LOOPING/TERMINATED without a replacement having taken over."""
        return [a for a in self._agents.values() if a.status in ("STALLED", "LOOPING", "FAILED")]

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump({"agents": [a.to_dict() for a in self._agents.values()]}, f, indent=2, sort_keys=True)
