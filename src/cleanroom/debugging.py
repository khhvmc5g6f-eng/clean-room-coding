"""Part XCVII: a build-side debugging suite for the implementation team
(Team B).

Team B only ever holds Zone H (sanitised spec + behavioural tests) and
Zone I (its own new code) -- never Zone R (see AGENTS.md rule a). When a
behavioural test fails, that constraint means a failure can mean one of
two very different things, and confusing them is expensive:

- The spec is clear and Zone I's code just doesn't meet it yet -- an
  ordinary implementation bug, fixable entirely within Zone I. Team B
  should debug it there and does not need anyone else.
- The spec itself doesn't say, clearly enough, what the correct
  behaviour is. No amount of staring at Zone I fixes that -- and the one
  thing Team B must never do is "just check the reference" to find out
  (that is exactly the contamination this project exists to prevent).
  The only legitimate move is to escalate for an unambiguous answer,
  which is what `legal/remediation.py`'s existing ledger + blocked
  requirement-graph node already do for legal/similarity findings --
  this module treats a `spec_gap` finding as a third source of the same
  kind of task, not a new parallel mechanism (see `_debug_task_source`
  in `legal/remediation.py`).

The classifier below is deliberately a small set of deterministic
lexical checks, not a model call and not a promise that it "understands"
the failure -- per AGENTS.md rule c, when the evidence doesn't clearly
support `spec_gap`, it defaults to treating the failure as an ordinary
implementation bug rather than inventing a diagnosis. It will
occasionally be wrong in both directions (a genuinely ambiguous
requirement with no marker word, or a marker word that happens to appear
in an otherwise-precise requirement) -- that is why `spec_gap` findings
still go through the existing human/Team-A remediation loop rather than
being treated as a final answer, and why `implementation_bug` findings
get a worksheet to work through rather than a "fixed for you" claim.
"""

from __future__ import annotations

from typing import Any

# Deterministic lexical markers for "this text does not actually commit to
# one unambiguous behaviour." Intentionally biased toward over-flagging --
# a false spec_gap costs a remediation task that gets resolved_by_rescan
# on the next 'cleanroom debug' once reworded; a false implementation_bug
# sends Team B chasing a bug that was never theirs to fix. Keep that bias
# if extending this list (same rationale as the prompt-injection scanner
# in sanitisation/scanner.py: prefer a false positive to a false negative).
AMBIGUITY_MARKERS = (
    "tbd", "t.b.d", "unclear", "unspecified", "not specified", "not yet defined",
    "may vary", "at least one of", "roughly", "approximately", "similar to",
    "and/or", "unless otherwise", "as appropriate", "if applicable",
    "in some cases", "typically", "in most cases", "up to the implementation",
    "implementation-defined", "left to the implementer",
)

# Deterministic lexical markers that a failure may be timing/ordering
# sensitive rather than a plain logic bug -- when present, the worksheet
# adds a temporal/concurrency section instead of silently omitting it.
CONCURRENCY_MARKERS = (
    "async", "asynchronous", "concurrent", "concurrently", "race",
    "retry", "retries", "parallel", "thread", "simultaneously",
    "idempotent", "idempotency", "timeout", "queue", "at-least-once",
    "at most once", "eventually consistent", "debounce", "throttle",
    "interrupt", "resume", "reconnect",
)

CLASSIFICATIONS = ("implementation_bug", "spec_gap", "insufficient_evidence")


def _requirement_statements(requirement_ids: list[str], requirement_nodes: list[dict[str, Any]]) -> list[str]:
    by_id = {n["id"]: n for n in requirement_nodes}
    return [by_id[rid]["statement"] for rid in requirement_ids if rid in by_id]


def classify_failure(test: dict[str, Any], requirement_nodes: list[dict[str, Any]]) -> dict[str, Any]:
    """Triage a single failing behavioural test (`result == "fail"` in
    `behavioral_tests.json`) against the requirement graph. Pure function,
    no I/O -- see `triage_suite` for the command-level driver.

    Returns a finding dict with a `classification` in `CLASSIFICATIONS`
    and a `reasons` list explaining exactly which deterministic check
    produced it, so a human reviewing DEBUG_FINDINGS.json never has to
    take the classification on faith.
    """
    requirement_ids = list(test.get("requirement_ids", []))
    by_id = {n["id"]: n for n in requirement_nodes}
    missing = [rid for rid in requirement_ids if rid not in by_id]

    if not requirement_ids or missing:
        reasons = [f"requirement {rid} referenced by {test['id']} was not found in requirements.json" for rid in missing]
        if not requirement_ids:
            reasons.append(f"{test['id']} has no requirement_ids linked at all")
        return {
            "test_id": test["id"],
            "classification": "insufficient_evidence",
            "reasons": reasons,
            "requirement_ids": requirement_ids,
            "missing_requirement_ids": missing,
        }

    statements = _requirement_statements(requirement_ids, requirement_nodes)
    combined_text = " ".join([test.get("given", ""), test.get("when", ""), test.get("then", ""), *statements]).lower()

    ambiguity_hits = sorted({m for m in AMBIGUITY_MARKERS if m in combined_text})
    if ambiguity_hits:
        return {
            "test_id": test["id"],
            "classification": "spec_gap",
            "reasons": [f"ambiguity marker '{m}' found in the linked requirement/behavioural text" for m in ambiguity_hits],
            "requirement_ids": requirement_ids,
            "ambiguity_markers": ambiguity_hits,
        }

    concurrency_hits = sorted({m for m in CONCURRENCY_MARKERS if m in combined_text})
    return {
        "test_id": test["id"],
        "classification": "implementation_bug",
        "reasons": [
            "requirement text is present and no deterministic ambiguity marker was found "
            "-- default assumption is Zone I's own code does not yet meet a spec that IS clear"
        ],
        "requirement_ids": requirement_ids,
        "concurrency_relevant": bool(concurrency_hits),
        "concurrency_markers": concurrency_hits,
    }


ZONE_REMINDER = (
    "This worksheet is scoped to Zone H (the sanitised spec/behavioural test) and "
    "Zone I (your own implementation) only. If answering any prompt below would "
    "require looking at the original reference material, STOP: that means this is "
    "actually a spec_gap, not an implementation_bug -- re-run 'cleanroom debug' after "
    "checking whether the requirement text should be reworded, or escalate for "
    "reference-side clarification through the normal remediation loop. Never read "
    "Zone R to resolve a debugging question (AGENTS.md rule a)."
)

BACKWARD_TRACE_PROMPTS = (
    "Start at the observed wrong output (what THEN says vs what Zone I actually "
    "produced), not at a guessed cause. Name the exact file:line that produced the "
    "wrong value.",
    "Walk backward one call/data-flow hop at a time from that line: what did it "
    "receive as input, and where did that input come from? Repeat until you reach "
    "either a hop where the value was already wrong (root cause is upstream) or a "
    "hop where the value was still correct (root cause is at the hop after it).",
    "Do not stop at the first place the bug becomes visible -- that is the symptom, "
    "not the cause. Keep tracing until you can state, in one sentence, the single "
    "hop where correct input became incorrect output.",
    "Once you have a root-cause hypothesis, falsify it before fixing anything: what "
    "observation would be true if you're wrong? Check that, specifically, before "
    "editing code.",
)

DEFENSE_IN_DEPTH_PROMPTS = (
    "Is this value validated only where it's first produced, or does every layer "
    "that depends on it also check the assumption it's relying on?",
    "If you add a fix at the layer where the bug was caught, would the same bad "
    "value have caused a different failure two layers further downstream if this "
    "test hadn't caught it first?",
    "Is the fix a change to the logic that was wrong, or a check that reports "
    "wrongness sooner without changing the underlying behaviour? Both may be "
    "needed -- do not treat an earlier check as a substitute for a real fix.",
)

TEMPORAL_CONCURRENCY_PROMPTS = (
    "Build a chronological model of the events this test exercises. Mark any edge "
    "that assumes serial execution but could, under load or retry, happen out of "
    "order or concurrently.",
    "For every state update involved: is it actually atomic, or does it only look "
    "atomic because the non-atomic window is usually short?",
    "For every operation this test repeats or could retry: is it idempotent? What "
    "happens if it runs twice?",
    "If this scenario is interrupted partway through, can it resume safely, or does "
    "it need to detect and clean up a half-done state?",
)


def build_worksheet(finding: dict[str, Any], test: dict[str, Any]) -> dict[str, Any]:
    """`implementation_bug` findings only. A structured, Zone-I-scoped
    debugging checklist to work through -- not an automated fix, and
    nothing here reads or edits Zone I source itself. Combines backward
    root-cause tracing and defense-in-depth layering with a
    temporal/concurrency section that only appears when the failure's own
    text actually suggests it's timing/ordering sensitive."""
    worksheet: dict[str, Any] = {
        "test_id": test["id"],
        "given": test.get("given"),
        "when": test.get("when"),
        "then": test.get("then"),
        "zone_reminder": ZONE_REMINDER,
        "backward_trace": list(BACKWARD_TRACE_PROMPTS),
        "defense_in_depth": list(DEFENSE_IN_DEPTH_PROMPTS),
    }
    if finding.get("concurrency_relevant"):
        worksheet["temporal_concurrency"] = list(TEMPORAL_CONCURRENCY_PROMPTS)
        worksheet["concurrency_markers_detected"] = finding.get("concurrency_markers", [])
    return worksheet


def triage_suite(tests: list[dict[str, Any]], requirement_nodes: list[dict[str, Any]]) -> dict[str, Any]:
    """Runs `classify_failure` over every currently-failing behavioural
    test (`result == "fail"`) and builds a worksheet for each
    `implementation_bug` finding. Pure function: callers are responsible
    for persisting `findings` (DEBUG_FINDINGS.json) and for feeding
    `spec_gap` findings into `legal/remediation.py::reconcile` (see
    `cleanroom debug` in cli.py) -- this module does not touch the
    remediation ledger or the requirement graph directly, to keep the
    triage logic testable without a whole project on disk."""
    findings: list[dict[str, Any]] = []
    worksheets: dict[str, dict[str, Any]] = {}
    for test in tests:
        if test.get("result") != "fail":
            continue
        finding = classify_failure(test, requirement_nodes)
        findings.append(finding)
        if finding["classification"] == "implementation_bug":
            worksheets[test["id"]] = build_worksheet(finding, test)
    return {"findings": findings, "worksheets": worksheets}
