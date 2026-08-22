"""Loads policy packs (policies/licences/*.yml) and evaluates dependency policy.

Part XI: "Do not encode legal conclusions as immutable universal rules."
Packs are data (facts, obligations, structured questions), not verdicts.
This module's job is to compute allowed/denied/needs_review against the
project's own configured allow/deny lists -- a deterministic, auditable
decision -- and separately surface the pack's non-binding notes.
"""

from __future__ import annotations

import functools
from pathlib import Path
from typing import Any

import yaml

_PACKAGE_DIR = Path(__file__).resolve().parent


def _candidate_policy_dirs() -> list[Path]:
    candidates = [_PACKAGE_DIR / "packs"]
    for parent in _PACKAGE_DIR.parents:
        candidate = parent / "policies" / "licences"
        if candidate.is_dir():
            candidates.append(candidate)
    return candidates


@functools.lru_cache(maxsize=1)
def policy_dir() -> Path:
    for candidate in _candidate_policy_dirs():
        if candidate.is_dir() and any(candidate.glob("*.yml")):
            return candidate
    raise FileNotFoundError("Could not locate policies/licences/ pack directory.")


@functools.lru_cache(maxsize=None)
def load_pack(spdx_id: str) -> dict[str, Any] | None:
    path = policy_dir() / f"{spdx_id}.yml"
    if not path.is_file():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def available_packs() -> list[str]:
    return sorted(p.stem for p in policy_dir().glob("*.yml"))


def split_terms(spdx_expression: str) -> list[str]:
    """Split a compound SPDX expression into simple identifier terms,
    stripping the AND/OR/WITH operators and parens. Not a real boolean-
    algebra parse (see licence/spdx.py for that) -- good enough for
    looking up each term's individual policy pack, which is all callers
    of this need it for."""
    return [
        t.strip()
        for t in spdx_expression.replace("(", " ").replace(")", " ").split()
        if t not in ("AND", "OR", "WITH")
    ]


def evaluate(
    spdx_expression: str | None,
    *,
    allowed: list[str],
    denied: list[str],
) -> dict[str, Any]:
    """Decide allowed/denied/unknown/needs_review for one licence expression
    against a project's configured allow/deny lists. Deterministic: same
    inputs, same output, always. Whether "needs_review"/"unknown" should
    block a release is a separate policy decision -- see `is_blocking`.
    """
    if spdx_expression is None:
        return {
            "status": "unknown",
            "obligations": [],
            "notes": "No licence could be concluded from available evidence.",
        }

    # Simple identifiers only for allow/deny matching in v0.1; compound
    # expressions are evaluated term-by-term.
    terms = split_terms(spdx_expression)
    if any(t in denied for t in terms):
        status = "denied"
        notes = f"One or more terms in '{spdx_expression}' are explicitly denied by project policy."
    elif terms and all(t in allowed for t in terms):
        status = "allowed"
        notes = f"All terms in '{spdx_expression}' are explicitly allowed by project policy."
    else:
        status = "needs_review"
        notes = f"'{spdx_expression}' is not fully covered by the project's allow/deny lists."

    obligations: list[str] = []
    for term in terms:
        pack = load_pack(term)
        if pack:
            obligations.extend(pack.get("key_obligations", []))

    return {"status": status, "obligations": obligations, "notes": notes}


def is_blocking(status: str, unknown_action: str) -> bool:
    """Given a policy_result.status and the project's unknown_licence_action
    config (block|warn|allow), decide whether this finding should fail CI.
    """
    if status == "denied":
        return True
    if status in ("unknown", "needs_review"):
        return unknown_action == "block"
    return False
