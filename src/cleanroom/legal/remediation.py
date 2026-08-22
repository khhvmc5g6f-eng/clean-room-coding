"""Closes the loop the design brief asks for explicitly: if a legal or
similarity finding flags a real concern, does it get sent back to the
implementation team to recode before release -- or does it just sit in a
report nobody acts on?

`reconcile()` is idempotent and re-derives the *should-exist* set of
remediation tasks from whatever legal/similarity findings currently exist
each time it runs:

- A finding that newly triggers (RED legal finding, or a `suspicious`/
  `material` similarity finding) gets a new open task AND a `blocked`
  node in the requirement graph (kind=remediation), so it shows up in
  `cleanroom specify report`'s traceability and `cleanroom report`'s
  outstanding_issues without any separate bookkeeping.
- A previously-open task whose underlying finding no longer triggers
  (because the team actually fixed it and re-ran `legal`/`similarity`)
  is automatically marked `resolved_by_rescan` and its graph node
  unblocked.
- A task can also be closed by an explicit human `override` (Part LI --
  a lawyer/reviewer deliberately accepting residual risk) without the
  underlying finding clearing. This is recorded distinctly
  (`resolved_by_override`) so it's never confused with an actual fix.

`cleanroom release` refuses to proceed while any `open` blocking task
remains (see cli.py) -- this is the actual enforcement point.
"""

from __future__ import annotations

from typing import Any

from cleanroom.util import new_id, utc_now_iso

AMBER_LIKE = {"AMBER", "UNKNOWN"}


def _legal_task_source(finding: dict[str, Any]) -> tuple[str, str, str] | None:
    """Returns (source_ref, severity, description) or None if this finding
    doesn't warrant a remediation task."""
    state = finding.get("decision_state")
    ref = f"{finding['issue']}@{finding['jurisdiction']}"
    if state == "RED":
        return ref, "blocking", f"Legal issue engine reported RED for '{finding['issue']}' in {finding['jurisdiction']}: {finding.get('finding', '')}"
    if state in AMBER_LIKE:
        return ref, "review_required", f"Legal issue engine reported {state} for '{finding['issue']}' in {finding['jurisdiction']}: {finding.get('finding', '')}"
    return None


def _similarity_task_source(finding: dict[str, Any]) -> tuple[str, str, str] | None:
    classification = finding.get("classification")
    if classification == "material":
        return finding["id"], "blocking", f"Similarity finding {finding['id']} ({finding['reference_ref']} vs {finding['implementation_ref']}) classified MATERIAL: {finding.get('explanation', '')}"
    if classification == "suspicious":
        return finding["id"], "review_required", f"Similarity finding {finding['id']} ({finding['reference_ref']} vs {finding['implementation_ref']}) classified SUSPICIOUS: {finding.get('explanation', '')}"
    return None


def derive_expected_tasks(
    legal_findings: list[dict[str, Any]],
    similarity_findings: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Returns {source_key: {source_type, source_ref, severity, description}}
    for every finding that currently warrants a remediation task."""
    expected: dict[str, dict[str, Any]] = {}
    for finding in legal_findings:
        result = _legal_task_source(finding)
        if result:
            ref, severity, description = result
            expected[f"legal_finding:{ref}"] = {
                "source_type": "legal_finding", "source_ref": ref,
                "severity": severity, "description": description,
            }
    for finding in similarity_findings:
        result = _similarity_task_source(finding)
        if result:
            ref, severity, description = result
            expected[f"similarity_finding:{ref}"] = {
                "source_type": "similarity_finding", "source_ref": ref,
                "severity": severity, "description": description,
            }
    return expected


def reconcile(
    existing_tasks: list[dict[str, Any]],
    legal_findings: list[dict[str, Any]],
    similarity_findings: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Pure function: given the current task list and current findings,
    return the reconciled task list (new tasks added, stale ones marked
    resolved_by_rescan, overridden/open ones left untouched)."""
    expected = derive_expected_tasks(legal_findings, similarity_findings)
    by_key = {f"{t['source_type']}:{t['source_ref']}": t for t in existing_tasks}

    reconciled: list[dict[str, Any]] = []
    now = utc_now_iso()

    for key, task in by_key.items():
        if key in expected:
            if task["status"] == "resolved_by_rescan":
                # The underlying finding cleared once (hence resolved_by_rescan)
                # and has now reappeared -- a regression. Re-open it; do NOT
                # touch resolved_by_override, which is a deliberate human
                # decision that must survive a finding reappearing (see
                # apply_override's docstring/design).
                task = dict(task)
                task["status"] = "open"
                task["description"] = expected[key]["description"]
                task.pop("resolved_utc", None)
            reconciled.append(task)
            continue
        if task["status"] == "open":
            task = dict(task)
            task["status"] = "resolved_by_rescan"
            task["resolved_utc"] = now
        reconciled.append(task)

    # New tasks get the next number after the highest ID already in use.
    # IDs are assigned ONCE, here, and never recomputed on a later
    # reconcile() call -- `apply_override` matches on `id`, so an ID must
    # stay valid across runs regardless of insertion order or how many
    # tasks clear/reopen in between (previously this renumbered every
    # task from scratch on every call, which could -- under same-tick
    # timestamp collisions -- silently shift which finding an id pointed
    # at between one `remediate` run and the next).
    existing_numbers = [int(t["id"].rsplit("-", 1)[1]) for t in reconciled if t.get("id")]
    next_number = max(existing_numbers, default=0) + 1

    for key, meta in expected.items():
        if key in by_key:
            continue
        reconciled.append(
            {
                "id": f"CR-REM-{next_number:06d}",
                "source_type": meta["source_type"],
                "source_ref": meta["source_ref"],
                "severity": meta["severity"],
                "description": meta["description"],
                "assigned_to": "implementation-team",
                "status": "open",
                "created_utc": now,
            }
        )
        next_number += 1

    reconciled.sort(key=lambda t: (t["created_utc"], t["id"]))
    return reconciled


def open_blocking_tasks(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [t for t in tasks if t["status"] == "open" and t["severity"] == "blocking"]


def apply_override(tasks: list[dict[str, Any]], task_id: str, *, by: str, notes: str) -> list[dict[str, Any]]:
    found = False
    for task in tasks:
        if task["id"] == task_id:
            if task["status"] != "open":
                raise ValueError(f"{task_id} is not open (status={task['status']}); nothing to override.")
            task["status"] = "resolved_by_override"
            task["resolved_utc"] = utc_now_iso()
            task["override"] = {"by": by, "notes": notes}
            found = True
    if not found:
        raise ValueError(f"No task with id {task_id}")
    return tasks
