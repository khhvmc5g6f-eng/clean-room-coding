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
judicial roles; it never calls an LLM API itself, and every prompt it
builds is fully answerable by a human, a Claude Code subagent, or any
other harness reading the same text. This keeps the deterministic core
(licence discovery, hashing, SBOM generation, schema validation, the
legal-issue heuristic engine) honestly deterministic, independent of
whether anyone ever answers a single judicial-review prompt.

`src/cleanroom/orchestration/{backends,harness}.py` is a real, opt-in
exception, not a contradiction of the above: it is a genuine, pluggable
`AgentBackend` interface (`orchestration/backends.py`) with one shipped
implementation (`AnthropicBackend`, an optional `cleanroom[orchestrate]`
dependency) that `cleanroom council`/`cleanroom implement` use to
actually answer `panels.py`'s prompts and actually write implementation
code. Adding another provider means implementing `AgentBackend`'s one
`complete()` method; nothing in `harness.py`'s own orchestration logic
(prompt construction, response parsing, merging results back through the
deterministic machinery) is Anthropic-specific. This is never invoked
implicitly -- `recruit`/`build`/`judge`/`judge-adjudicate`/`remediate`
all remain exactly as provider-agnostic (i.e. they never call an LLM)
as before this existed.

## What's a documented limitation, not a silent gap

See [ROADMAP.md](../ROADMAP.md) for the full list -- e.g. structural
similarity has real AST/tree-sitter support for Python, JavaScript,
TypeScript, Go, Rust, Java, Ruby, C and C++ (generic-fallback for other
languages), SBOM transitive dependency resolution is opt-in
(`cleanroom provenance --resolve-transitive`) rather than automatic, and
the legal issue engine implements 17 of 18 issues with a real heuristic
-- only `protected_expression` is honestly `UNKNOWN`, since idea/
expression merger judgment has no deterministic proxy this tool can
compute, never a fabricated answer.
