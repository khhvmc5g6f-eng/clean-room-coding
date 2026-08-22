"""Part XXVIII: stalled, zombie and looping agent detection.

Deterministic rules over a simple observation log (one entry per heartbeat
tick): no LLM judgement needed to notice "the same action repeated N times
with no file modified". Feed real tool-call/heartbeat events from whatever
orchestration harness is running the agents.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class Tick:
    action_signature: str
    files_modified: int
    test_result: str | None = None  # "pass" | "fail" | None


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
