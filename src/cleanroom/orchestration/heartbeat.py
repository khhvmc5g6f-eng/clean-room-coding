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

`Tick.timestamp` (and `tick_intervals_seconds()` below) close a real gap:
`diagnose()` can spot STALLED/LOOPING from repetition alone, but with no
time dimension in the log at all, nothing could ever measure how FAST an
agent is actually working -- only that it repeated itself. The CLI caller
supplies `timestamp` explicitly at the moment it calls `cleanroom
heartbeat` (via `utc_now_iso()`, the same helper the evidence ledger uses)
rather than this module defaulting it -- a tick loaded from a log written
before this field existed genuinely has no recorded timestamp, and
`timestamp=None` says so honestly instead of fabricating "now" for a tick
that happened at some real, unknown, earlier time.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

TICK_LOG_DIRNAME = "ticks"


@dataclass
class Tick:
    action_signature: str
    files_modified: int
    test_result: str | None = None  # "pass" | "fail" | None
    timestamp: str | None = None  # ISO-8601 UTC, e.g. utc_now_iso() -- None for ticks recorded before this field existed


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


def _parse_timestamp(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def tick_intervals_seconds(ticks: list[Tick]) -> list[float]:
    """Real elapsed seconds between each consecutive PAIR of ticks that
    both carry a timestamp -- the actual velocity signal `diagnose()`'s
    repetition-only heuristic cannot provide on its own. Ticks with no
    timestamp (e.g. persisted before this field existed, or a malformed
    value) are skipped entirely rather than treated as a zero-second gap,
    which would silently fabricate a "very fast" reading."""
    stamped = [t for t in ticks if t.timestamp]
    parsed = [(_parse_timestamp(t.timestamp), t) for t in stamped]
    parsed = [(dt, t) for dt, t in parsed if dt is not None]
    intervals: list[float] = []
    for (dt1, _), (dt2, _) in zip(parsed, parsed[1:]):
        intervals.append((dt2 - dt1).total_seconds())
    return intervals


def efficiency_summary(ticks: list[Tick]) -> dict[str, Any]:
    """A real, honest efficiency signal to sit alongside `diagnose()`'s
    stall/loop status -- not a fabricated score. Reports what's actually
    computable from the tick log and says plainly when it isn't:
    `average_tick_interval_seconds`/`elapsed_seconds` are None (not 0)
    when fewer than two timestamped ticks exist, and `unstamped_ticks`
    names how many ticks in this history predate timestamp tracking so a
    reader knows the interval average excludes them rather than assuming
    full coverage."""
    intervals = tick_intervals_seconds(ticks)
    stamped_count = len([t for t in ticks if t.timestamp and _parse_timestamp(t.timestamp)])
    return {
        "total_ticks": len(ticks),
        "stamped_ticks": stamped_count,
        "unstamped_ticks": len(ticks) - stamped_count,
        "average_tick_interval_seconds": (sum(intervals) / len(intervals)) if intervals else None,
        "elapsed_seconds": sum(intervals) if intervals else None,
    }


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
