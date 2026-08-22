"""Deterministic helpers shared across the engine.

Part LXVI: use deterministic software before LLM guessing. Hashing, canonical
JSON and timestamps live here so every module produces byte-identical,
reproducible evidence.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

GENESIS_HASH = "0" * 64


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def new_id() -> str:
    return str(uuid.uuid4())


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def canonical_json(obj: Any) -> bytes:
    """Stable serialisation used everywhere a hash is computed over JSON."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def sha256_json(obj: Any) -> str:
    return sha256_bytes(canonical_json(obj))


def hash_tree(root: Path, *, ignore_dirnames: set[str] | None = None) -> dict[str, str]:
    """Return {relative_posix_path: sha256} for every file under root.

    Deterministic and order-independent (caller sorts). Used by the evidence
    ledger and handoff manifest so "what crossed the boundary" is provable,
    not asserted.
    """
    ignore_dirnames = ignore_dirnames or {".git", "__pycache__", ".venv"}
    result: dict[str, str] = {}
    if not root.exists():
        return result
    for path in sorted(root.rglob("*")):
        if path.is_dir():
            continue
        if any(part in ignore_dirnames for part in path.parts):
            continue
        rel = path.relative_to(root).as_posix()
        result[rel] = sha256_file(path)
    return result
