# 0001. Python core, language-agnostic contracts

## Status

Accepted

## Decision

Build the v0.1 Clean Room Coding engine and CLI in Python (`src/cleanroom`),
and define every cross-cutting contract -- JSON Schemas, CLI `--json`
output shape, the evidence-event and handoff-manifest formats -- as plain
JSON with no Python-specific structures, so a future implementation in
another language (TypeScript, Rust) could interoperate with or replace the
Python core without redesigning any of the contracts.

## Rationale

Python has the strongest available ecosystem for the specific problems
this tool solves first: licence text handling, SPDX-adjacent tooling,
JSON Schema validation (`jsonschema`), YAML config, and straightforward
CLI construction (`click`). It is also fast to get right and well-tested
in the time available for a v0.1 "deep core, narrow breadth" build.

Committing every contract to plain JSON (not pickled objects, not
Python-only dataclasses serialized in a Python-specific way) means:

- Another language's implementation can read/write the same
  `.cleanroom.yml`, `HANDOFF_MANIFEST.json`, evidence ledger, and SBOM
  files.
- CI/CD and other tooling can consume `--json` CLI output without a Python
  dependency.
- The schemas in `/schemas` are the actual source of truth, not
  Python type hints.

## Alternatives considered

**TypeScript/Node** -- comparable CLI ergonomics and strong JSON tooling,
but a weaker licence/SBOM library ecosystem at the time of writing.
**Rust** -- best for a single-binary cross-platform CLI and hashing
performance, but a smaller ecosystem for licence/SBOM libraries and
significantly more code to write from scratch for a v0.1 timeline.

Both remain valid future targets given the language-agnostic contracts
this ADR commits to.
