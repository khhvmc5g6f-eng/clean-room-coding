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


def is_safe_regular_file(path: Path, root: Path) -> tuple[bool, str]:
    """Guards against two real risks when walking an untrusted tree (a
    'reference repo a user pointed the tool at', or Zone H just before a
    handoff manifest is built): a symlink that resolves outside `root`
    (which would smuggle content from elsewhere -- e.g. Zone R -- into a
    Zone H hash/manifest), and a non-regular file (FIFO/socket/device)
    that would hang a blocking read forever. Returns (is_safe, reason);
    callers should skip and record `reason` rather than silently including
    or crashing on an unsafe path."""
    if path.is_symlink():
        try:
            resolved = path.resolve(strict=True)
        except OSError:
            return False, "broken symlink"
        try:
            resolved.relative_to(root.resolve())
        except ValueError:
            return False, f"symlink resolves outside the scanned root ({resolved})"
    if not path.is_file():
        return False, "not a regular file (symlink/FIFO/socket/device or similar)"
    return True, ""


def hash_tree(root: Path, *, ignore_dirnames: set[str] | None = None) -> tuple[dict[str, str], list[str]]:
    """Return ({relative_posix_path: sha256}, [skipped-path-reasons]) for
    every file under root. Deterministic and order-independent (caller
    sorts). Used by the evidence ledger and handoff manifest so "what
    crossed the boundary" is provable, not asserted -- unsafe paths
    (symlinks escaping root, FIFOs/devices) are skipped and reported, never
    silently included or allowed to hang the scan.
    """
    ignore_dirnames = ignore_dirnames or {".git", "__pycache__", ".venv"}
    result: dict[str, str] = {}
    skipped: list[str] = []
    if not root.exists():
        return result, skipped
    for path in sorted(root.rglob("*")):
        if path.is_dir() and not path.is_symlink():
            continue
        if any(part in ignore_dirnames for part in path.parts):
            continue
        rel = path.relative_to(root).as_posix()
        safe, reason = is_safe_regular_file(path, root)
        if not safe:
            skipped.append(f"{rel}: {reason}")
            continue
        result[rel] = sha256_file(path)
    return result, skipped
