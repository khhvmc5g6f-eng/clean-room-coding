"""Part XXVIII: stalled, zombie and looping agent detection.

Deterministic rules over a simple observation log (one entry per heartbeat
tick): no LLM judgement needed to notice "the same action repeated N times
with no file modified". Feed real tool-call/heartbeat events from whatever
orchestration harness is running the agents.

`append_tick`/`load_ticks` are a minimal, real persistence layer for that
observation log -- a JSON-Lines file per agent under
`evidence/ticks/<agent_id>.jsonl` -- so `cleanroom heartbeat` (cli.py) can
actually call `diagnose()` on a real tick history instead of this module
being reachable only in isolation. This is deliberately minimal: it does
not spawn, schedule, or supervise agents itself (Part LXV: provider-
agnostic) -- whatever harness is actually running multiple agents (a
script, CI, another framework) calls `cleanroom heartbeat` once per
meaningful action/tick.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

TICK_LOG_DIRNAME = "ticks"


@dataclass
class Tick:
    action_signature: str
    files_modified: int
    test_result: str | None = None  # "pass" | "fail" | None


def _tick_log_path(evidence_dir: Path, agent_id: str) -> Path:
    return evidence_dir / TICK_LOG_DIRNAME / f"{agent_id}.jsonl"


def append_tick(evidence_dir: Path, agent_id: str, tick: Tick) -> None:
    path = _tick_log_path(evidence_dir, agent_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(asdict(tick), sort_keys=True) + "\n")


def load_ticks(evidence_dir: Path, agent_id: str) -> list[Tick]:
    path = _tick_log_path(evidence_dir, agent_id)
    if not path.is_file():
        return []
    ticks: list[Tick] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        ticks.append(Tick(**json.loads(line)))
    return ticks


def diagnose(ticks: list[Tick], *, repeat_threshold: int = 3) -> str:
    """Returns one of ACTIVE, STALLED, LOOPING given the tail of an agent's
    tick history. Callers combine this with explicit statuses (BLOCKED,
    WAITING, FAILED, COMPLETE, TERMINATED) that come from outside the
    observation log (e.g. an explicit dependency wait)."""
    if not ticks:
        return "ACTIVE"

    tail = ticks[-repeat_threshold:]
    if len(tail) == repeat_threshold and len({t.action_signature for t in tail}) == 1:
        return "LOOPING"

    if len(tail) == repeat_threshold and all(t.files_modified == 0 for t in tail):
        return "STALLED"

    failing = [t for t in tail if t.test_result == "fail"]
    if len(failing) == repeat_threshold and all(t.files_modified == 0 for t in failing):
        return "STALLED"

    return "ACTIVE"


def recommend_action(status: str) -> str:
    return {
        "LOOPING": "Terminate and reassign the requirement to a freshly instantiated agent; preserve any files it did produce.",
        "STALLED": "Inspect the last tick's context, diagnose the blocker, and either unblock or replace the agent.",
        "ACTIVE": "No action needed.",
    }.get(status, "Inspect manually.")
