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
- A 25-command CLI (`cleanroom init`, `doctor`, `intake`, `inspect`,
  `licence`, `jurisdiction`, `analyse`, `specify` (`add-requirement`,
  `report`, `add-behavioral`), `sanitise`, `handoff`, `architect`,
  `ai-suggest`, `build`, `test`, `compare`, `similarity`, `provenance`,
  `audit`, `legal`, `judge`, `remediate`, `verify`, `report`, `release`,
  `status`) with `--json` output and documented exit codes
  (`src/cleanroom/exit_codes.py`) for CI/CD consumption.
- Project documentation: `CONTRIBUTING.md`, `SECURITY.md`,
  `GOVERNANCE.md`, `CODE_OF_CONDUCT.md`, `AGENTS.md`.
- CI workflow running `pytest` and `reuse lint` on Python 3.11 and 3.12
  (`.github/workflows/ci.yml`), GitHub issue templates, and a
  `CODEOWNERS` file protecting the legal-content and contract surface.
- A reusable composite GitHub Action
  (`integrations/github-action/action.yml`) wrapping
  `cleanroom doctor`/`licence`/`audit`/`report`/`remediate` for use in a
  caller's CI.
- `cleanroom similarity <ref-dir> <impl-dir>`: wires the similarity engine
  to a real CLI command with `--negative-control` and `--max-comparisons`,
  exiting `SIMILARITY_FAILURE` (7) on an unresolved suspicious/material
  finding.
- `cleanroom remediate`: an automatic, idempotent feedback loop — a RED
  legal finding or a suspicious/material similarity finding becomes a
  tracked, blocked requirement-graph node assigned to the implementation
  team; re-running after a real fix clears it automatically; a human can
  instead `--override --by --notes` to explicitly accept residual risk
  (recorded distinctly from an actual fix). `cleanroom release` now
  refuses to proceed while a blocking task is open.
- `cleanroom ai-suggest`: asks explicitly whether to add AI/ML capability,
  then searches the real Hugging Face Hub, classifying candidates as
  embeddable/standalone vs. server-required (or honestly `unknown`), and
  checks each model's Hub licence tag against the project's own
  `dependency_policy`.
- `cleanroom report --html` / `--pdf`: colour-coded HTML and paginated PDF
  renderings of the final report (`src/cleanroom/report_pdf.py`, via
  fpdf2), alongside the always-written JSON certificate and Markdown
  report. The report now also includes "what it started with" (from
  `.cleanroom.yml`) and "what it did" (derived from the evidence ledger).
- `cleanroom init --target-language`: the reimplementation's target
  language/format is now an explicit, recorded choice (interactive prompt
  by default) rather than assumed to match the reference — a mechanical
  translation of the reference's own source would defeat clean-room
  independence, so this project deliberately never offers that; the
  language is instead a genuine free choice for the implementation team.
- A fifth licence policy pack, `BUSL-1.1`, describing this project's own
  licence (see "Changed" below).

### Changed

- **Relicensed from Apache-2.0 to Business Source License 1.1
  (BUSL-1.1).** Apache-2.0 explicitly permitted resale/rebranding as a
  competing product, which conflicted with the goal of preventing exactly
  that; BUSL-1.1 permits free use including internal commercial use, but
  not offering the software to third parties as a competing hosted/SaaS
  product or reselling/white-labelling it, and automatically converts to
  GPL-2.0-or-later on 2030-08-22 for each released version. See
  `LICENSE`/`NOTICE`/`REUSE.toml`.
- `cleanroom audit` now checks Zone H licences against the project's own
  configured `dependency_policy` (previously a hardcoded MIT/Apache-2.0
  allowlist) and actually fails its exit code on a blocking finding; it
  also now reports `PathGuard` self-test results and a new, project-
  specific `agent_zone_consistency` check (see "Security" below) rather
  than only the isolation self-test.
- `--config` is now actually wired through to project discovery
  (previously parsed by the CLI but silently ignored).

### Fixed

Found by an internal code review and security audit (2026-08-22) — see
[ROADMAP.md](ROADMAP.md#external-review-findings-2026-08-22) for full
detail:

- Licence-text fingerprinting matched multiple licences simultaneously on
  real, unmodified BSD-3-Clause and AGPL-3.0/LGPL licence text, reporting
  unambiguous mainstream licences as "conflicting evidence." Fixed with
  explicit per-fingerprint exclusion markers and regression-tested against
  the real gnu.org licence texts.
- `cleanroom licence` logged a "success" evidence event even when its
  findings were policy-blocking; `cleanroom handoff` logged no evidence
  event at all when it refused a handoff for non-C0 content. Both now log
  accurately on every path.
- The sanitisation scanner's identifier-overlap check only matched
  camelCase/PascalCase identifiers, missing the majority of realistic
  snake_case leaks from Python/Rust/Ruby reference material.
- The verbatim-overlap scanner used a stride-sampled substring search that
  could miss a copied run whose length was close to the detection
  threshold; it now checks every offset via an n-gram set, which is also
  faster on realistic inputs.
- The evidence ledger re-read the entire ledger file on every single
  append (O(n²) over a ledger's lifetime); it now caches the chain tip in
  memory.
- `cleanroom compare --float-epsilon 0` raised an unhandled
  `ZeroDivisionError`; now a clear `ClickException`.
- The GPG signing subprocess had no timeout and could hang indefinitely on
  an interactive pinentry prompt; it now runs non-interactively with a
  30-second timeout.

### Security

- **Isolation-proof honesty fix:** the isolation self-test (renamed
  `run_pathguard_self_test`) only ever proved the `PathGuard` mechanism
  denies correctly in isolation — nothing in the CLI actually routed real
  file reads through it, so a passing self-test was not evidence that any
  specific project's agents were ever gated by it. Docstrings and every
  consumer now say this plainly, and a new, real, project-specific check
  (`check_agent_zone_consistency`) cross-references the agent registry
  against the evidence ledger for genuine zone violations. Full live
  per-invocation enforcement remains a documented roadmap item.
- A symlink inside Zone H (or a scanned reference tree) that resolved
  outside the scanned root was previously followed and hashed/read
  without question — meaning Zone R content could be smuggled into a
  "sanitised" handoff manifest via a symlink, and a FIFO named `LICENSE`
  would hang licence discovery forever. Fixed with a shared
  `is_safe_regular_file` check used by the hash-tree walker, the handoff
  manifest builder, and licence discovery.
- `PathGuard`'s `permitted_paths` field was declared but never consulted,
  so it silently allowed any path outside the three named zones — it now
  behaves as a true allow-list when populated.
- The evidence ledger raised an unhandled `JSONDecodeError` on a
  truncated/corrupt line (a realistic outcome of an interrupted write);
  it now degrades gracefully and reports the corruption as a
  `verify_chain()` finding instead of crashing.

[Unreleased]: https://github.com/khhvmc5g6f-eng/clean-room-coding/compare/HEAD
