# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project intends to adhere to [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
once it reaches 1.0.

## [Unreleased]

Initial v0.1.0 build. This is early, alpha software — see
[README.md](README.md) status section and
[docs/legal-disclaimer.md](docs/legal-disclaimer.md).

### Added

- Three-zone project model (Reference / Handoff / Implementation) with a
  technically-enforced path guard (`src/cleanroom/zones.py`) and an
  append-only, hash-chained evidence ledger.
- Deterministic licence discovery (LICENSE/NOTICE files, SPDX headers,
  package manifests) plus four licence policy packs: MIT, Apache-2.0,
  GPL-3.0-only, AGPL-3.0-only (`policies/licences/`).
- A jurisdiction resolution engine with real packs for England & Wales
  and US federal law (`jurisdictions/`) — facts, primary authorities, and
  structured questions, not legal conclusions.
- A sanitisation scanner for candidate handoff material (secrets, code
  syntax markers, verbatim-overlap risk, prompt-injection markers).
- A requirement / behavioural specification graph (`cleanroom specify
  add-requirement`, `add-behavioral`, `report`) with observable-vs-source
  classification and traceability reporting.
- A cryptographically hashed, signable handoff manifest
  (`cleanroom handoff`).
- A similarity engine: lexical comparison, Python AST structural
  comparison, and negative-control background comparison.
- SBOM generation in both SPDX and CycloneDX formats
  (`cleanroom provenance`).
- A heuristic legal-issue engine (`src/cleanroom/legal/engine.py`)
  covering 18 distinct legal questions, always emitting `UNKNOWN` /
  `insufficient_evidence` rather than a fabricated conclusion when facts
  are insufficient.
- Adversarial-counsel and judicial-review **prompt generation**
  (`cleanroom judge`) for every convened jurisdiction panel — the
  reasoning itself is performed by whatever LLM harness runs the
  generated prompts; this library never calls one on its own.
- A 22-command CLI (`cleanroom init`, `doctor`, `intake`, `licence`,
  `jurisdiction`, `analyse`, `specify` (`add-requirement`, `report`,
  `add-behavioral`), `sanitise`, `handoff`, `architect`, `build`, `test`,
  `compare`, `provenance`, `audit`, `legal`, `judge`, `verify`, `report`,
  `release`, `status`) with `--json` output and documented exit codes
  (`src/cleanroom/exit_codes.py`) for CI/CD consumption.
- Project documentation: `CONTRIBUTING.md`, `SECURITY.md`,
  `GOVERNANCE.md`, `CODE_OF_CONDUCT.md`, `AGENTS.md`.
- CI workflow running `pytest` on Python 3.11 and 3.12
  (`.github/workflows/ci.yml`), GitHub issue templates, and a
  `CODEOWNERS` file protecting the legal-content and contract surface.
- A reusable composite GitHub Action
  (`integrations/github-action/action.yml`) wrapping
  `cleanroom doctor`/`licence`/`audit`/`report` for use in a caller's CI.

[Unreleased]: https://github.com/khhvmc5g6f-eng/clean-room-coding/compare/HEAD
