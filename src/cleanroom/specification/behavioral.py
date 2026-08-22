"""Part XVIII: GIVEN/WHEN/THEN behavioural specifications."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cleanroom.schema_registry import validate

BEHAVIORAL_FILENAME = "behavioral_tests.json"


class BehavioralSuite:
    def __init__(self, tests: list[dict[str, Any]] | None = None):
        self.tests: dict[str, dict[str, Any]] = {t["id"]: t for t in (tests or [])}

    @classmethod
    def load(cls, path: Path) -> "BehavioralSuite":
        if not path.is_file():
            return cls([])
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls(data.get("tests", []))

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"tests": list(self.tests.values())}, f, indent=2, sort_keys=True)

    def add(self, test: dict[str, Any]) -> None:
        errors = validate(test, "behavioral-test.schema.json")
        if errors:
            raise ValueError(f"Invalid behavioural test {test.get('id')}: {errors}")
        self.tests[test["id"]] = test

    def next_id(self) -> str:
        existing = [int(t.split("-")[-1]) for t in self.tests]
        n = (max(existing) + 1) if existing else 1
        return f"CR-BEH-{n:06d}"

    def summary(self) -> dict[str, int]:
        summary: dict[str, int] = {"pass": 0, "fail": 0, "not_tested": 0, "blocked": 0, "unknown": 0}
        for test in self.tests.values():
            result = test.get("result", "not_tested")
            summary[result] = summary.get(result, 0) + 1
        return summary
