"""Part XLII: an append-only, hash-chained evidence ledger.

Each event's event_hash commits to the previous event's hash, so any
retroactive edit to an earlier event is detectable by re-walking the chain
(`verify_chain`). This is deliberately a plain JSON-Lines file rather than a
database: it must be diffable, greppable and portable inside an evidence
bundle without extra tooling.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cleanroom.schema_registry import validate
from cleanroom.util import GENESIS_HASH, canonical_json, new_id, sha256_bytes, utc_now_iso

LEDGER_FILENAME = "ledger.jsonl"


@dataclass
class Actor:
    type: str  # human | agent | tool | ci
    id: str
    role: str | None = None
    model_provider: str | None = None
    model_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d = {"type": self.type, "id": self.id}
        if self.role:
            d["role"] = self.role
        if self.model_provider:
            d["model_provider"] = self.model_provider
        if self.model_id:
            d["model_id"] = self.model_id
        return d


class EvidenceLedger:
    def __init__(self, evidence_dir: Path):
        self.evidence_dir = evidence_dir
        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        self.ledger_path = evidence_dir / LEDGER_FILENAME

    def _last_hash(self) -> tuple[str, int]:
        if not self.ledger_path.exists():
            return GENESIS_HASH, -1
        last_line = None
        sequence = -1
        with open(self.ledger_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    last_line = line
                    sequence += 1
        if last_line is None:
            return GENESIS_HASH, -1
        return json.loads(last_line)["event_hash"], sequence

    def append(
        self,
        *,
        actor: Actor,
        action: str,
        zone: str = "none",
        inputs: list[dict[str, str]] | None = None,
        outputs: list[dict[str, str]] | None = None,
        tool: str | None = None,
        git_commit: str | None = None,
        result: str = "success",
        detail: str | None = None,
    ) -> dict[str, Any]:
        previous_hash, previous_seq = self._last_hash()
        event: dict[str, Any] = {
            "event_id": new_id(),
            "sequence": previous_seq + 1,
            "timestamp_utc": utc_now_iso(),
            "actor": actor.to_dict(),
            "action": action,
            "zone": zone,
            "inputs": inputs or [],
            "outputs": outputs or [],
            "result": result,
            "previous_hash": previous_hash,
        }
        if tool:
            event["tool"] = tool
        if git_commit:
            event["git_commit"] = git_commit
        if detail:
            event["detail"] = detail
        event["event_hash"] = sha256_bytes(canonical_json(event))

        errors = validate(event, "evidence-event.schema.json")
        if errors:
            raise ValueError(f"Refusing to append invalid evidence event: {errors}")

        with open(self.ledger_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, sort_keys=True) + "\n")
        return event

    def read_all(self) -> list[dict[str, Any]]:
        if not self.ledger_path.exists():
            return []
        events = []
        with open(self.ledger_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    events.append(json.loads(line))
        return events

    def verify_chain(self) -> list[str]:
        """Re-walk the hash chain. Returns a list of problems; empty = intact."""
        problems: list[str] = []
        expected_previous = GENESIS_HASH
        for i, event in enumerate(self.read_all()):
            stored_hash = event.get("event_hash")
            recomputed = dict(event)
            recomputed.pop("event_hash", None)
            recomputed_hash = sha256_bytes(canonical_json(recomputed))
            if event.get("previous_hash") != expected_previous:
                problems.append(
                    f"event #{i} ({event.get('event_id')}): previous_hash mismatch, "
                    f"expected {expected_previous}, got {event.get('previous_hash')}"
                )
            if stored_hash != recomputed_hash:
                problems.append(
                    f"event #{i} ({event.get('event_id')}): event_hash does not match "
                    f"recomputed hash -- record may have been tampered with"
                )
            expected_previous = stored_hash
        return problems
