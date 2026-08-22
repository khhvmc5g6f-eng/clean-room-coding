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
  GPL-3.0-or-later on 2030-08-22 for each released version. See
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

### Fixed (second review pass, code added after the first)

- **A regressed legal/similarity finding stayed silently `resolved_by_rescan`
  forever** — `legal/remediation.py`'s `reconcile()` never reopened a task
  whose underlying finding had cleared once and then reappeared, so
  `cleanroom release` would silently stop blocking on a live RED finding
  after a fix was reverted. Confirmed by direct reproduction; fixed by
  reopening `resolved_by_rescan` tasks (never `resolved_by_override`,
  which is a deliberate human decision) when their finding recurs.
- **`cleanroom report --pdf` crashed on ordinary human-entered text** — an
  em dash, curly quotes, or an ellipsis in a project name or a
  legal/similarity finding description (routine in both `.cleanroom.yml`
  metadata and LLM-authored finding text) raised
  `FPDFUnicodeEncodingException`, since fpdf2's core fonts only support
  Latin-1. Confirmed by direct reproduction; fixed centrally for every
  `cell`/`multi_cell` call.
- Remediation task IDs were recomputed by sort position on every
  `reconcile()` call rather than assigned once, which could — under
  same-tick timestamp collisions — silently shift which finding a
  previously-recorded `--override <id>` pointed at. IDs are now assigned
  once at creation and never reassigned.
- `similarity/engine.py` matched at most one same-named reference file per
  basename, silently losing comparisons against any other reference file
  sharing that name; now matches every same-named candidate. Its all-pairs
  fallback also truncated with an impl-file-order-biased flat slice
  instead of round-robin, which could give one impl file full reference
  coverage while another got none at all under the same `--max-comparisons`
  budget.
- `similarity/structural.py`'s non-Python fallback matched keywords by
  substring (misreading `"iffy"`, `"classList.add(...)"` as control-flow
  structure) and only clamped its *emitted* depth, not the internal
  counter, so one stray unmatched bracket could permanently offset every
  later line's signature. Fixed with word-boundary matching and clamping
  the counter itself; also added missing Go/Rust/Ruby keywords.
- `ai/suggest.py`'s Hub-licence-to-SPDX table was missing several
  legitimate SPDX identifiers (`CC-BY-NC-4.0`, `WTFPL`, `OFL-1.1`,
  `LGPL-2.1-only`) — added, while deliberately leaving model-specific
  "Responsible AI License" tags unmapped since they have no honest SPDX
  equivalent.
- `sanitisation/differential.py` (the RAW_ANALYSIS/SANITISED_SPECIFICATION
  record ADR-0002 documents) was fully implemented but never called from
  anywhere — `cleanroom sanitise` now actually builds and persists a real
  `SanitisationReport`/`DifferentialEntry` record.
- Two legal citation errors found by an independent fact-check of ~30
  claims against primary sources: a missing "Mercantile" in the IBCOS
  case name, and the wrong party order/an unfinalised reporter citation
  for the Oracle/Google Supreme Court case (correct: *Google LLC v. Oracle
  America, Inc.*, 593 U.S. 1 (2021)).
- The Skill's documentation had drifted from the code: `references/
  exit-codes.md` wrongly said exit code 7 was unwired (it has been, since
  `cleanroom similarity` shipped); `cleanroom verify`/`cleanroom status`
  were never mentioned in the skill; the licence-pack count was stale.

### Added (third pass — library integrations and jurisdiction coverage)

- `src/cleanroom/licence/spdx.py` is now backed by the real
  `license-expression` library (`get_spdx_licensing()`), replacing the
  hand-rolled curated-subset parser with the full real SPDX licence list;
  the public API surface is unchanged and all existing tests pass
  unmodified.
- Real tree-sitter structural similarity via `ast-grep-py`
  (`similarity/structural.py`'s `treesitter_structural_shape`) for
  JavaScript, TypeScript, TSX, Go, Rust, Java, Ruby, C and C++ — previously
  only Python had a real AST comparison; every other language used the
  weaker bracket/keyword fallback. `similarity/engine.py` now derives a
  language hint per compared file and down-weights genuine
  `generic_fallback` findings with a 1.5x higher classification
  threshold, since that path is real but weaker evidence.
- Four new independently fact-checked jurisdiction packs: `eu`, `france`,
  `germany`, `japan` (`jurisdictions/<id>/framework.yml`), bringing the
  total to 6. Each cites real primary sources (official statute
  translations, EUR-Lex, Cour de cassation, Bundesgerichtshof, Japan's
  Ministry of Justice translation service) verified during this pass, not
  reused from training-data recall; two case-law entries (France, Japan)
  are explicitly flagged in-file as unverified/pre-dating the modern IP
  court structure rather than presented as settled authority.

### Fixed (third pass)

- **`treesitter_structural_shape` silently escaped its own error
  handling.** `ast-grep-py`'s underlying Rust library raises
  `pyo3_runtime.PanicException` for an unrecognised language string, and
  that exception class subclasses `BaseException` directly rather than
  `Exception` — so the function's `except Exception` clause never caught
  it, and an unsupported/misspelled language crashed the whole comparison
  instead of falling back. Confirmed by direct reproduction (inspecting
  the exception's `__mro__`); fixed by catching `BaseException` in that
  narrowly-scoped single-call `try` block.
- **The four new jurisdiction packs were orphan files.**
  `jurisdiction/resolver.py`'s `COUNTRY_TO_PACK` only mapped `gb`/`uk`/`us`
  to their packs — `eu`/`fr`/`de`/`jp` had no entry, so `build_matrix`
  would report every EU/France/Germany/Japan market as `unknown` tier
  regardless of the new packs existing on disk. Fixed by extending
  `COUNTRY_TO_PACK`; a regression test (`test_new_jurisdiction_markets_
  resolve_to_primary_tier`) now asserts all four resolve to `primary`.

### Added (fourth pass — more legal-issue heuristics)

- Four new real heuristics in the legal issue engine
  (`src/cleanroom/legal/engine.py`), bringing coverage from 5 to 10 of
  Part XLIV's 18 issues: `licence_obligations` (flags concluded licences
  with copyleft obligations via each licence's policy pack), `distribution`
  (flags configured distribution acts that overlap a reference/dependency
  licence's copyleft distribution triggers), `derivative_work_question`
  (grounded in the requirement graph's observable/source classification
  plus any open MATERIAL similarity finding), and
  `interoperability_provisions` (surfaces the jurisdiction pack's
  documented interoperability-permitted-acts, if any). Each still ends in
  `UNKNOWN` when its underlying facts are missing rather than guessing.
- `licence/policy.py` gained a small public `split_terms()` helper
  (extracted from `evaluate()`) so the new heuristics and the existing
  policy evaluator share one compound-SPDX-expression splitter instead of
  duplicating the logic.

### Fixed (fourth pass)

- **`cleanroom legal` never populated `similarity_findings`,
  `requirement_classifications`, or `interoperability_permitted_acts` on
  the `CaseBundle` it builds.** The `copying`/`substantiality` heuristic
  has existed since v0.1 but was unreachable in practice: the CLI command
  never read `evidence/similarity-findings.json`, so it always reported
  `UNKNOWN` even after `cleanroom similarity` had produced real findings.
  Fixed by loading that file (and the requirement graph, and the
  resolved jurisdiction pack) in the `legal` command; confirmed with a new
  CLI-level regression test
  (`test_legal_picks_up_similarity_and_requirement_graph_facts`) that
  writes a suspicious similarity finding and an unresolved
  `source_implementation_detail` requirement node before running
  `cleanroom legal`, and asserts both are reflected as `AMBER` rather than
  `UNKNOWN`.

[Unreleased]: https://github.com/khhvmc5g6f-eng/clean-room-coding/compare/HEAD
