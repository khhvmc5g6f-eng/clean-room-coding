# Architecture

## Layout

```
schemas/        JSON Schemas -- the contracts. Everything else is validated against these.
policies/       licence policy packs (facts + structured questions, not verdicts)
jurisdictions/  jurisdiction packs (facts + primary authorities + structured questions)
prompts/        reserved for standalone role prompts shared across panels (currently
                generated inline by src/cleanroom/legal/panels.py; see ROADMAP.md)
src/cleanroom/  the Python engine + CLI
skills/         the Agent Skill (progressive disclosure: SKILL.md is short,
                references/ is loaded on demand)
docs/           this documentation, plus docs/adr/ for Architecture Decision Records
examples/       a full worked walkthrough
tests/          unit + integration tests, run against every change
integrations/   the GitHub Action
.github/        CI, issue templates, CODEOWNERS
```

## Why Python (ADR 0001)

See [adr/0001-python-core-language-agnostic-contracts.md](adr/0001-python-core-language-agnostic-contracts.md).
Short version: best available ecosystem for licence/SBOM/JSON-Schema
tooling and fast to build correctly; every contract (schemas, CLI I/O
shape, evidence event format) is plain JSON so a future TypeScript or Rust
implementation could be added without redesigning anything.

## Why three zones, not two (ADR 0002)

See [adr/0002-three-zone-model.md](adr/0002-three-zone-model.md).

## Deterministic-first

Anything that can be computed reliably by deterministic code is (hashing,
licence text fingerprinting, SPDX expression parsing, AST structural
comparison, SBOM generation, schema validation). LLM/agent judgement is
reserved for genuinely judgement-laden steps (is this an observable
requirement?, does this similarity look coincidental?, what does a
qualified reviewer make of this evidence?) -- and even there, the code
never lets an LLM's uncertainty be silently upgraded to a confident
answer; `UNKNOWN`/`insufficient_evidence`/`needs_review` are first-class,
common outcomes throughout the schemas.

## Evidence-first

`src/cleanroom/evidence.py`'s hash-chained ledger is written to by nearly
every CLI command. The chain lets `cleanroom verify` detect any
retroactive edit to a past event. This is deliberately a flat
JSON-Lines file, not a database, so it's diffable, greppable, and portable
inside an evidence bundle without extra tooling.

## Provider abstraction

`src/cleanroom/legal/panels.py` builds prompt *text* for the adversarial/
judicial roles; it never calls an LLM API itself. This keeps the core
library provider-agnostic (Claude is the primary orchestration target for
this project, per the design brief, but nothing is hard-wired to it) and
keeps the deterministic core honestly deterministic.

## What's a documented limitation, not a silent gap

See [ROADMAP.md](../ROADMAP.md) for the full list -- e.g. structural
similarity has real AST/tree-sitter support for Python, JavaScript,
TypeScript, Go, Rust, Java, Ruby, C and C++ (generic-fallback for other
languages), SBOM dependency discovery reads direct declared dependencies
only (no transitive resolution), and the legal issue engine implements 10
of 18 issues with a real heuristic (the rest are honestly `UNKNOWN`
pending either more heuristics or a human reviewer, never a fabricated
answer).
