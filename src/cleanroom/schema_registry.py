"""Locates and validates against the JSON Schemas in /schemas.

Schemas are authored once at the repository root so they are visible and
diffable independent of the Python package (Part IV: "Do not permit
silently malformed configuration"). This module finds them whether cleanroom
is run from a checkout (development, CI) or from an installed package that
carries a bundled copy as package data.
"""

from __future__ import annotations

import functools
import json
from pathlib import Path
from typing import Any

import jsonschema

_PACKAGE_DIR = Path(__file__).resolve().parent


def _candidate_schema_dirs() -> list[Path]:
    candidates = [_PACKAGE_DIR / "schemas"]
    # Walk upward from this file looking for a repo-root /schemas directory.
    for parent in _PACKAGE_DIR.parents:
        candidate = parent / "schemas"
        if candidate.is_dir():
            candidates.append(candidate)
    return candidates


@functools.lru_cache(maxsize=1)
def schema_dir() -> Path:
    for candidate in _candidate_schema_dirs():
        if candidate.is_dir() and any(candidate.glob("*.schema.json")):
            return candidate
    raise FileNotFoundError(
        "Could not locate the Clean Room Coding schemas/ directory. "
        "Run cleanroom from within a checkout of the project, or install "
        "the package with its bundled schema data."
    )


@functools.lru_cache(maxsize=None)
def load_schema(name: str) -> dict[str, Any]:
    """Load a schema by filename, e.g. 'config.schema.json'."""
    path = schema_dir() / name
    if not path.is_file():
        raise FileNotFoundError(f"Unknown schema: {name} (looked in {schema_dir()})")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _resolver_for(name: str) -> jsonschema.validators.RefResolver:
    base = load_schema(name)
    store = {}
    for path in schema_dir().glob("*.schema.json"):
        with open(path, "r", encoding="utf-8") as f:
            doc = json.load(f)
        store[doc.get("$id", path.name)] = doc
        store[path.name] = doc
    return jsonschema.validators.RefResolver.from_schema(base, store=store)


def validate(instance: Any, schema_name: str) -> list[str]:
    """Validate instance against schema_name; return a list of error strings (empty = valid)."""
    schema = load_schema(schema_name)
    resolver = _resolver_for(schema_name)
    validator_cls = jsonschema.validators.validator_for(schema)
    validator = validator_cls(schema, resolver=resolver)
    errors = sorted(validator.iter_errors(instance), key=lambda e: list(e.path))
    return [f"{'/'.join(str(p) for p in e.path) or '<root>'}: {e.message}" for e in errors]
