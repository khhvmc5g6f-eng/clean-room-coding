"""Part XCVI: capability-regression coverage checking (`cleanroom coverage`).

Motivating case (see AGENTS.md item c for the "never fabricate a
conclusion" rule this module follows throughout): a real clean-room
migration deliberately scoped its reimplementation down to "only what the
app's existing screens/BLE code actually use" -- a reasonable, common
clean-room strategy. That scoping-down silently dropped a working
enum-name -> numeric-id conversion for two config fields, which then wrote
garbage to real hardware. Nothing in this tool caught it; it took a
manual, ad-hoc audit agent reading application code by hand. This module
turns that specific class of check -- "did the clean-room implementation
keep referencing everything the pre-migration code actually referenced,
the same way it referenced it" -- into a first-class, repeatable command,
rather than leaving it to chance.

`coverage` is deliberately distinct from `similarity` (suspicious COPYING
between reference and implementation source text) and `compare`
(functional equivalence between two full program outputs): it instead
diffs a REQUIREMENT SURFACE -- the set of named fields/enum-values the
pre-migration ("legacy") usage code actually touched -- against what the
Zone I implementation still touches, by name.

What this DOES check (a real, bounded, useful signal):
  - Every named field the legacy usage code referenced (`identifier:
    value` shapes -- object/dict/map literals) is still referenced under
    the same name somewhere in the Zone I implementation scanned.
  - Whether an enum-like literal value (e.g. "EU_868", "LONG_FAST" --
    upper-snake-case constant shape) that the legacy code always passed
    through a lookup/function call before use is, in Zone I, assigned or
    consumed RAW for every occurrence found -- the exact shape of the
    motivating bug (a silently-dropped enum-name -> numeric-id
    conversion).

What this does NOT check (stated here once, plainly, rather than
oversold in the CLI output -- see also `check_coverage()`'s returned
"limitations" list, always populated in every report so a reader never
has to trust a docstring they didn't open):
  - No AST or semantic analysis of any language. This is a regex/
    brace-counting heuristic over `identifier: value`-shaped text. A
    field genuinely renamed during the rescope is indistinguishable from
    one silently dropped.
  - It cannot see a conversion performed in a helper/shared module that
    doesn't happen to sit textually next to the field it converts.
  - It cannot verify a conversion it DOES find is the *correct* one --
    only that a conversion-shaped expression exists or doesn't.
  - It only recognises `identifier: value` usage shapes (object/dict/map
    literals, which is how the real motivating bug's fields were set).
    Method calls, protobuf field descriptors, and getter/setter
    accessors are out of scope for this first version.

Because of all of the above, findings are never emitted as a plain PASS/
FAIL. Every finding carries a `confidence` of `CONFIRMED` (the presence/
absence fact itself, not "this is definitely a real regression"),
`PLAUSIBLE` (the convention-divergence check -- a real, human-reviewable
signal, never auto-failed), matching AGENTS.md item c: absence of
evidence is its own answer, not license to guess.
"""

from __future__ import annotations

import bisect
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cleanroom.schema_registry import validate

IGNORE_DIRNAMES = {".git", "__pycache__", ".venv", "node_modules", "dist", "build"}

# Deliberately broad: "identifier: value" is common to JS/TS object
# literals, JSON, Dart/Kotlin/Swift map literals, Python dict literals,
# and more -- the whole point of a first version is an honestly narrow
# extraction shape applied across many languages, rather than a precise
# per-language parser for just one.
SCAN_SUFFIXES = {
    ".js", ".jsx", ".ts", ".tsx", ".json", ".dart", ".kt", ".kts", ".java",
    ".swift", ".py", ".go", ".rs", ".rb", ".c", ".cc", ".cpp", ".h", ".hpp",
    ".proto", ".yaml", ".yml",
}

_ENUM_LIKE = re.compile(r"^[A-Z][A-Z0-9_]*$")
_KEY_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\s*:\s*")
_WRAP_HINT = re.compile(r"[\(\[]")
_STRING_RE = re.compile(r"""(['"])((?:\\.|(?!\1).)*)\1""")

CONFIDENCE_CONFIRMED = "CONFIRMED"
CONFIDENCE_PLAUSIBLE = "PLAUSIBLE"
CONFIDENCE_INSUFFICIENT = "insufficient_evidence"

STATUS_PRESENT = "present"
STATUS_MISSING = "missing"
STATUS_DIVERGENT = "divergent"


@dataclass
class UsageFact:
    """One `identifier: value` occurrence extracted from source text --
    never claimed to be more than that (not a resolved symbol, not a type)."""

    name: str
    value_expr: str
    literal: str | None
    wrapped: bool
    enum_like: bool
    block: str | None
    file: str
    line: int
    snippet: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name, "value_expr": self.value_expr, "literal": self.literal,
            "wrapped": self.wrapped, "enum_like": self.enum_like, "block": self.block,
            "file": self.file, "line": self.line, "snippet": self.snippet,
        }


def _iter_files(root: Path) -> list[Path]:
    if root.is_file():
        return [root]
    if not root.exists():
        return []
    return [
        p for p in sorted(root.rglob("*"))
        if p.is_file() and p.suffix in SCAN_SUFFIXES and not any(part in IGNORE_DIRNAMES for part in p.parts)
    ]


_HASH_COMMENT_SUFFIXES = {".py", ".rb", ".yaml", ".yml"}
_SLASH_COMMENT_SUFFIXES = {
    ".js", ".jsx", ".ts", ".tsx", ".dart", ".kt", ".kts", ".java", ".swift",
    ".go", ".rs", ".c", ".cc", ".cpp", ".h", ".hpp", ".proto",
}


def _mask_comments(text: str, suffix: str) -> str:
    """Blank out comment content (replaced with spaces, newlines kept) so
    it can't be mistaken for `identifier: value` usage facts -- e.g. a
    docstring/comment that happens to contain a colon. Deliberately naive:
    it does not know about `//`/`#`/`/* */` appearing inside a string
    literal (a URL like "http://example.com" loses its trailing text on
    the same masked line), so it can occasionally under-extract inside a
    string. Accepted as an honest limitation of a first-pass heuristic,
    not a parser -- see LIMITATIONS. Length and newline positions are
    preserved so line numbers computed against the ORIGINAL text remain
    correct after masking."""
    def blank_span(m: re.Match) -> str:
        return "".join(ch if ch == "\n" else " " for ch in m.group(0))

    if suffix in _SLASH_COMMENT_SUFFIXES:
        text = re.sub(r"/\*.*?\*/", blank_span, text, flags=re.DOTALL)
        text = re.sub(r"//[^\n]*", blank_span, text)
    elif suffix in _HASH_COMMENT_SUFFIXES:
        text = re.sub(r"#[^\n]*", blank_span, text)
    return text


def _extract_from_text(text: str, file_label: str, suffix: str = "") -> list[UsageFact]:
    """Brace-counting regex scan for `identifier: value` usage facts,
    tracking the innermost enclosing block's own key (e.g. the "lora" in
    `lora: { region: ... }`) so callers can group sibling fields. This is
    NOT a parser: it does not understand string escaping edge cases,
    comments containing braces, or template-literal interpolation beyond
    what the string/bracket regexes below happen to tolerate. Documented
    as a heuristic, not silently assumed to be exact (AGENTS.md item c)."""
    facts: list[UsageFact] = []
    stack: list[str | None] = []
    lines = text.splitlines()
    line_starts = [0]
    for ln in lines:
        line_starts.append(line_starts[-1] + len(ln) + 1)

    def line_of(pos: int) -> int:
        return bisect.bisect_right(line_starts, pos)

    masked = _mask_comments(text, suffix)
    text = masked  # scan the masked copy; `lines` above (for snippets) stays the original text
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch in "{[":
            stack.append(None)
            i += 1
            continue
        if ch in "}]":
            if stack:
                stack.pop()
            i += 1
            continue
        m = _KEY_RE.match(text, i)
        if m:
            key = m.group(1)
            j = m.end()
            k = j
            while k < n and text[k] in " \t":
                k += 1
            if k < n and text[k] == "{":
                # This key opens a nested block -- label the block we're
                # about to push with the key that introduced it, so a
                # sibling field inside can be grouped by its parent.
                stack.append(key)
                i = k + 1
                continue
            start = k
            depth = 0
            p = k
            while p < n:
                c = text[p]
                if c in "([":
                    depth += 1
                elif c in ")]":
                    if depth == 0:
                        break
                    depth -= 1
                elif c in ",}" and depth == 0:
                    break
                elif c == "\n" and depth == 0:
                    break
                p += 1
            value_expr = text[start:p].strip().rstrip(",")
            if value_expr:
                str_m = _STRING_RE.search(value_expr)
                literal = str_m.group(2) if str_m else (value_expr if _ENUM_LIKE.match(value_expr) else None)
                wrapped = bool(_WRAP_HINT.search(value_expr))
                enum_like = bool(literal and _ENUM_LIKE.match(literal))
                ln = line_of(start)
                snippet = lines[ln - 1].strip() if 0 < ln <= len(lines) else value_expr
                facts.append(UsageFact(
                    name=key, value_expr=value_expr, literal=literal, wrapped=wrapped,
                    enum_like=enum_like, block=stack[-1] if stack else None,
                    file=file_label, line=ln, snippet=snippet,
                ))
            i = p
            continue
        i += 1
    return facts


def extract_usage_facts(root: Path) -> list[UsageFact]:
    """Every `identifier: value` usage fact found under `root` (a single
    file or a directory), restricted to `SCAN_SUFFIXES`. An empty result
    for a real, non-empty tree means "nothing in this extractor's narrow
    shape was found here" -- see `check_coverage()`'s `overall_status`,
    never silently treated as "nothing to report, therefore clean"."""
    facts: list[UsageFact] = []
    for f in _iter_files(root):
        text = f.read_text(encoding="utf-8", errors="replace")
        label = str(f.relative_to(root)) if root.is_dir() else f.name
        facts.extend(_extract_from_text(text, label, suffix=f.suffix))
    return facts


@dataclass
class CoverageFinding:
    id: str
    name: str
    status: str
    confidence: str
    legacy_locations: list[dict[str, Any]]
    zone_i_locations: list[dict[str, Any]]
    explanation: str
    requires_review: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "name": self.name, "status": self.status, "confidence": self.confidence,
            "legacy_locations": self.legacy_locations, "zone_i_locations": self.zone_i_locations,
            "explanation": self.explanation, "requires_review": self.requires_review,
        }


def _loc(f: UsageFact) -> dict[str, Any]:
    return {"file": f.file, "line": f.line, "snippet": f.snippet, "value_expr": f.value_expr}


LIMITATIONS = [
    "No AST or semantic analysis of any language -- this is a regex/brace-counting heuristic over "
    "'identifier: value' shaped text. A field genuinely renamed in good faith during the rescope looks "
    "identical to one silently dropped.",
    "Cannot see a conversion performed in a helper/shared module that isn't textually adjacent to the "
    "field it converts.",
    "Only recognises 'identifier: value' usage shapes (object/dict/map literals) -- method calls, "
    "protobuf field descriptors, and getter/setter accessors are out of scope for this first version.",
    "Does not verify that a conversion it DOES find is the *correct* one -- only that a conversion-shaped "
    "expression exists or doesn't.",
    "A 'missing' finding means the exact name wasn't found anywhere in the scanned Zone I implementation "
    "under SCAN_SUFFIXES -- not a proof the capability is gone (it could be handled by generated code, a "
    "dependency, or a file extension this scan doesn't recognise).",
    "Comments are blanked out with a naive language-agnostic-per-suffix regex (not real tokenisation) before "
    "extraction, to avoid mistaking comment text for usage facts -- it doesn't know about '//', '#', or '/* */' "
    "appearing inside a string literal, so a string containing one of those sequences can be truncated on that "
    "line.",
]


def check_coverage(legacy_root: Path, zone_i_root: Path) -> dict[str, Any]:
    """Cross-check every named usage fact found in `legacy_root` against
    `zone_i_root`. Never returns a bare pass/fail -- see module docstring
    and `LIMITATIONS`, always included in the result so a caller can't
    accidentally present this as a semantic guarantee it isn't."""
    legacy_facts = extract_usage_facts(legacy_root)
    zone_i_facts = extract_usage_facts(zone_i_root)

    by_name_legacy: dict[str, list[UsageFact]] = {}
    for f in legacy_facts:
        by_name_legacy.setdefault(f.name, []).append(f)
    by_name_zone_i: dict[str, list[UsageFact]] = {}
    for f in zone_i_facts:
        by_name_zone_i.setdefault(f.name, []).append(f)

    findings: list[CoverageFinding] = []
    seq = 0
    for name in sorted(by_name_legacy):
        seq += 1
        legacy_occurrences = by_name_legacy[name]
        zone_i_occurrences = by_name_zone_i.get(name, [])

        if not zone_i_occurrences:
            findings.append(CoverageFinding(
                id=f"COV-{seq:05d}", name=name, status=STATUS_MISSING, confidence=CONFIDENCE_CONFIRMED,
                legacy_locations=[_loc(f) for f in legacy_occurrences], zone_i_locations=[],
                explanation=(
                    f"'{name}' is referenced {len(legacy_occurrences)} time(s) in the legacy usage code but "
                    "never appears (under this exact name) anywhere in the Zone I implementation scanned -- "
                    "a candidate dropped capability. CONFIRMED here means the name-based absence is real and "
                    "deterministic, not that this is definitely a bug: see LIMITATIONS (a rename would look "
                    "identical)."
                ),
                requires_review=True,
            ))
            continue

        # Convention-consistency check: does legacy always route this field's
        # value through a lookup/function call (a map subscript, a call
        # expression) before use, while every Zone I occurrence of the same
        # field name assigns/consumes it raw? Deliberately NOT restricted to
        # `enum_like` literal values -- the real motivating bug's config
        # value is a variable reference resolved through a lookup table
        # (`REGION_MAP[cfg.region]`), not a bare enum-string literal, so
        # gating on literal shape alone would miss exactly the case this
        # exists to catch. Broadening it this way trades some false
        # positives (a field wrapped in legacy for an unrelated reason, e.g.
        # a null-check helper) for not missing the real pattern -- acceptable
        # because this is a PLAUSIBLE, human-reviewed flag, never an
        # auto-fail (AGENTS.md item c).
        legacy_wrapped = [f for f in legacy_occurrences if f.wrapped]
        zone_i_any_wrapped = any(f.wrapped for f in zone_i_occurrences)
        zone_i_raw = [f for f in zone_i_occurrences if not f.wrapped]

        if legacy_wrapped and not zone_i_any_wrapped and zone_i_raw:
            findings.append(CoverageFinding(
                id=f"COV-{seq:05d}", name=name, status=STATUS_DIVERGENT, confidence=CONFIDENCE_PLAUSIBLE,
                legacy_locations=[_loc(f) for f in legacy_wrapped],
                zone_i_locations=[_loc(f) for f in zone_i_raw],
                explanation=(
                    f"Legacy usage always passes '{name}' through a lookup/function call before use "
                    f"(e.g. {legacy_wrapped[0].value_expr!r}), but every Zone I occurrence of '{name}' assigns/"
                    f"consumes it raw (e.g. {zone_i_raw[0].value_expr!r}), with no equivalent conversion found "
                    "anywhere this field is referenced in the scanned implementation. This is the exact shape of "
                    "the motivating real-world bug (an enum-name -> numeric-id lookup silently dropped during "
                    "rescoping). PLAUSIBLE, not CONFIRMED, and never auto-failed: a grep-based scan cannot rule "
                    "out the conversion happening in a shared helper this scan didn't associate with the field, "
                    "or the raw value already being in the form Zone I actually needs -- requires human review."
                ),
                requires_review=True,
            ))
            continue

        findings.append(CoverageFinding(
            id=f"COV-{seq:05d}", name=name, status=STATUS_PRESENT, confidence=CONFIDENCE_CONFIRMED,
            legacy_locations=[_loc(f) for f in legacy_occurrences],
            zone_i_locations=[_loc(f) for f in zone_i_occurrences],
            explanation=f"'{name}' is referenced by name in both the legacy usage code and the Zone I implementation.",
            requires_review=False,
        ))

    finding_dicts = [f.to_dict() for f in findings]
    for finding_dict in finding_dicts:
        errors = validate(finding_dict, "coverage-finding.schema.json")
        if errors:
            raise ValueError(f"Built an invalid coverage finding {finding_dict.get('id')}: {errors}")

    overall_status = "insufficient_evidence" if not legacy_facts else "checked"
    return {
        "legacy_root": str(legacy_root),
        "implementation_root": str(zone_i_root),
        "method": (
            "Grep/regex-based static usage-fact extraction over 'identifier: value' shapes -- not an AST or "
            "semantic analysis. Reports whether every named field the legacy code referenced is still "
            "referenced (under the same name) in the Zone I implementation, and flags value-conversion "
            "conventions the legacy code applied to an enum-like field that Zone I appears not to."
        ),
        "overall_status": overall_status,
        "usage_facts_extracted": {"legacy": len(legacy_facts), "implementation": len(zone_i_facts)},
        "distinct_fields_referenced_in_legacy": len(by_name_legacy),
        "findings": finding_dicts,
        "limitations": LIMITATIONS,
    }
