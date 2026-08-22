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

### Added (fifth pass — real SBOM library integration)

- `provenance/sbom.py`'s `to_spdx()`/`to_cyclonedx()` now build real
  `spdx_tools`/`cyclonedx-python-lib` model objects and serialize through
  each library's own converter/outputter, replacing hand-typed JSON that
  only resembled the format. Both are confirmed genuinely schema-valid
  with each library's own validator
  (`validate_full_spdx_document`/`make_schemabased_validator`), including
  for a real dependency with an MIT licence concluded/declared via the
  existing `license-expression`-backed `licence/spdx.py` parser (an
  unrecognised licence string now honestly falls back to
  `NOASSERTION`/is omitted rather than being forced into an invalid
  document). `discover_dependencies()` and the `Dependency` dataclass are
  unchanged — only the serialization half these libraries replace.
- CycloneDX output uses the modern CycloneDX 1.5 `metadata.tools` pattern
  (a `Component` inside a `ToolRepository`) rather than the deprecated
  flat `Tool` list, confirmed by direct testing that the legacy form
  raises `SchemaDeprecationWarning1Dot5` under `SchemaVersion.V1_5` and
  the new form doesn't.

### Fixed (fifth pass)

- **spdx-tools 0.8.5 serializes `externalRefs[].referenceCategory` as the
  raw Python enum name (`PACKAGE_MANAGER`, underscore) instead of the
  hyphenated value the real SPDX 2.3 JSON schema requires
  (`PACKAGE-MANAGER`)** — confirmed by fetching and inspecting
  `spdx/spdx-spec`'s own `spdx-schema-2-3.json` directly rather than
  assuming, since this is a claim about a third-party library's
  correctness. Fixed with a narrow, documented post-processing step in
  `to_spdx()` rather than silently shipping non-conformant output;
  covered by `test_spdx_output_is_schema_valid`.

### Added (sixth pass — SLSA build provenance)

- `.github/workflows/release.yml`: a new workflow, separate from `ci.yml`,
  that fires only on `release: published` (not every push/tag), builds
  the sdist/wheel with `python -m build`, generates a real SLSA v1.0
  build-provenance attestation (in-toto format, Sigstore-signed) via
  GitHub's native `actions/attest-build-provenance@v4`, and uploads both
  the artifacts and the attestation to the release so a consumer can run
  `gh attestation verify` against what they downloaded. Confirmed the
  package actually builds cleanly with `python -m build` in this repo
  before writing the workflow, rather than assuming it would.

### Added (seventh pass — automatic clean-room-level computation)

- `src/cleanroom/maturity.py`: `cleanroom status` now reports a
  `computed_maturity` field, independently derived from real project
  state, alongside the declared `clean_room_level` in `.cleanroom.yml`
  (the two are never silently reconciled -- a mismatch surfaces as
  `matches_declared: false`, not auto-corrected in either direction).
  Levels are cumulative and evaluated deterministically from files/state
  this tool already produces: ledger events and zone directories (CR1); a
  handoff manifest plus a Zone-R-blind implementation agent registered via
  `cleanroom build` (CR2); the PathGuard self-test passing and a generated
  SBOM (CR3); similarity findings, an intact evidence-ledger hash chain,
  full jurisdiction-pack coverage for required markets, and legal findings
  (CR4); a cryptographically signed handoff manifest (part of CR5).
  CR5's other criterion -- adversarial legal review actually reviewed by
  qualified counsel -- is always reported unmet with an explanatory note,
  since no project file can establish that a human lawyer did this; the
  computed level therefore can never automatically reach CR5, by design.
  Verified end-to-end (not just unit-level) by manually driving a real
  project through `init` -> `build`/`handoff` -> `provenance` ->
  `similarity`/`legal` and printing the computed level at each stage
  before trusting the corresponding regression test
  (`test_computed_maturity_level_advances_with_real_project_state`).

### Added (eighth pass — opt-in transitive dependency resolution)

- New `src/cleanroom/provenance/transitive.py`: `resolve_transitive()`
  walks a project's real dependency graph via read-only registry metadata
  calls (PyPI's JSON API for pip/pyproject dependencies, the npm registry
  API for package.json dependencies) -- it never installs a package or
  runs any of its code, so it's safe to run against dependency names
  taken from an untrusted reference project's manifest. Breadth-first,
  deduplicated by (ecosystem, name) so a diamond dependency is only
  queried once, depth-capped (default 5) against pathological graphs, and
  every failed lookup is recorded as `unresolved` with a reason rather
  than silently dropped.
- Wired into a new opt-in `cleanroom provenance --resolve-transitive`
  flag (default off, so the command's existing offline behaviour is
  unchanged unless asked) that writes
  `evidence/sbom/transitive-dependencies.json` alongside the existing
  SPDX/CycloneDX documents. Deliberately kept as a separate artefact
  rather than merged into the SBOM documents themselves this pass, to
  avoid changing their existing direct-deps-only scope/behaviour for
  anyone not opting in.
- Tests mock the registry HTTP layer (`_pypi_lookup`/`_npm_lookup`/
  `_http_get_json`) throughout, including a CLI-level regression test
  (`test_provenance_resolve_transitive_is_opt_in_and_writes_evidence`) --
  no test in this suite makes a real network call.

### Fixed (ninth pass — two long-deferred small findings, plus a real bug found while fixing one of them)

- **`ai/suggest.py`'s Hugging Face Hub search had no timeout** -- neither
  `HfApi.__init__` nor `list_models` exposes one. `search_models()` now
  bounds the call explicitly. First attempt used a
  `concurrent.futures.ThreadPoolExecutor` with `shutdown(wait=False)` on
  timeout; confirmed by direct testing (a simulated 5-second hang) that
  this still blocked process exit for the full hang duration, because
  CPython's `concurrent.futures.thread` registers an atexit hook that
  joins every executor-owned thread at interpreter shutdown regardless of
  `wait=False`. Switched to a plain daemon `threading.Thread` + a result
  queue instead, which isn't subject to that join; confirmed the fix by
  timing the test (0.9s total vs. 5.6s with the executor-based attempt).
- **The PDF jurisdiction table rendered row-by-row with manual `cell()`
  calls**, so a page break could in principle split a row across pages
  with no repeated header. Rewritten using fpdf2's own `table()` API
  (`first_row_as_headings`/`repeat_headings`, both on by default), which
  repeats the header row automatically on every page.
- **Found while fixing the table, by visually reading a rendered sample
  report rather than trusting the test suite alone: `_chip()` (the
  coloured "Global decision" badge) set the document's fill colour via
  `set_fill_color()` but, unlike its own text-colour reset, never reset
  it afterwards.** fpdf2's `table()` API fills any cell without its own
  explicit style using whatever fill colour is currently active on the
  document -- so every cell in the jurisdiction table inherited the
  chip's colour, not just the intentionally-coloured Decision cell.
  Reproduced with an isolated minimal script before and after the fix,
  and covered by a new regression test
  (`test_chip_resets_fill_colour_so_it_does_not_leak_into_later_content`).

### Added (tenth pass — evidence ledger to in-toto Link export)

- New `src/cleanroom/provenance/intoto.py`: maps every evidence-ledger
  event to an in-toto Attestation Framework Statement wrapping a Link
  predicate (`https://in-toto.io/attestation/link/v0.3`), verified field-
  by-field against the real spec fetched from `in-toto/attestation`
  directly (including the requirement that every `subject`/`materials`
  entry have a real `digest` -- an input/output recorded with a path but
  no sha256 is dropped rather than given a fabricated digest, and an
  event with no file output at all falls back to using its own
  tamper-evident `event_hash` as the subject, so every ledger event is
  exportable, not just file-producing ones).
- **These are explicitly, loudly NOT signed in-toto attestations** --
  every exported file carries `unsigned: true` and an `unsigned_note`
  explaining why: a genuine in-toto attestation's assurance comes from a
  DSSE-signed statement verifiable against a known signer's key, and this
  project's evidence ledger authenticates itself by hash-chaining events
  (Part XLII), not by having each actor (human/agent/tool/CI) hold a
  private signing key. Documented plainly rather than overclaimed.
- Wired into a new opt-in `cleanroom verify --export-in-toto-links` flag
  (default off), writing one `<sequence>-<action>.link.json` file per
  ledger event to `evidence/in-toto-links/`.

### Added (eleventh pass — a minimal heartbeat harness, per explicit user direction)

- `orchestration/heartbeat.py` was genuinely orphaned since v0.1 (0%
  coverage, no caller anywhere) because its `diagnose()` needs a live
  tick-by-tick observation stream this stateless CLI had no producer for.
  Asked the user directly whether to leave it, remove it, or sketch a
  minimal harness; they chose the last option. Added `append_tick()`/
  `load_ticks()` (a small, real JSON-Lines persistence layer per agent,
  `evidence/ticks/<agent_id>.jsonl`) and a new `cleanroom heartbeat
  <agent-id> --action-signature ... --files-modified N [--test-result
  pass|fail]` command that appends one tick, re-runs `diagnose()` over
  that agent's real history, and -- only when the diagnosis actually
  finds a problem (`STALLED`/`LOOPING`), never silently overwriting an
  explicit `BLOCKED`/`WAITING`/terminal status set for unrelated reasons
  -- calls `AgentRegistry.set_status()`, which itself had no caller
  anywhere before this either.
- This does not make `cleanroom` a multi-agent orchestrator: it still
  never spawns, schedules, or supervises agents itself (Part LXV,
  provider-agnostic) -- whatever is actually running multiple agents over
  time (a script, CI, another framework) calls `cleanroom heartbeat` once
  per meaningful tick.
- Verified end-to-end via the real installed CLI binary, not just the
  test suite: registered an agent, fed it three identical-signature
  ticks, and confirmed both the `LOOPING` diagnosis and that
  `cleanroom status`'s `orphaned_agents` picked it up afterward, before
  writing the corresponding regression tests.
- CLI command count: 25 -> 26.

### Added (twelfth pass — measured precision/recall benchmark, and a real ScanCode Toolkit finding)

- New `src/cleanroom/benchmark.py` + `cleanroom benchmark` (no
  `.cleanroom.yml` project needed, like `cleanroom doctor`): runs the
  similarity engine against a new, expanded 8-case ground-truth corpus
  (`tests/fixtures/benchmark/manifest.yml`) and computes real precision/
  recall/F1/accuracy -- Part LXXVII was previously an unmeasured claim.
  Added 6 new fixture pairs (a partially-disguised Python paraphrase, a
  same-concept-different-structure Python pair to test against false
  positives from ordinary shared idiom, and matched contaminated/
  independent pairs in JavaScript and Go to exercise the real tree-sitter
  structural path, not just Python's `ast`) alongside the original 2.
- **Measured result: precision 0.80, recall 1.00, F1 0.89, accuracy
  0.875** at the default 0.15 threshold -- with one real, deliberately
  undisguised false positive (`js-independent-clone`, ~0.18 structural
  score despite being a genuinely independent reimplementation). Kept in
  the corpus and documented plainly as a real limitation of the default
  structural threshold for JavaScript's tree-sitter node-kind vocabulary,
  rather than loosened until the number looked clean -- a benchmark that
  can't produce a false positive isn't measuring anything.
- Investigated whether ScanCode Toolkit could be added as the previously-
  recommended optional `[licensecheck]` extra and found a real, concrete
  blocker beyond the already-known "~40 transitive deps" concern:
  `scancode.api` requires a native `libmagic` library, and the only PyPI
  plugin that provides one (`typecode-libmagic`) has no working binary
  for arm64 macOS + Python 3.14 -- confirmed by installing both in a
  clean scratch venv and hitting `NoMagicLibError` on the very first
  import, with no system libmagic available to fall back to either. Left
  unbuilt rather than writing adapter code that couldn't be verified to
  actually run.
- CLI command count: 26 -> 27.

### Added (thirteenth pass — merge transitive dependencies into the SBOM documents themselves)

- `provenance/sbom.py`'s `to_spdx()`/`to_cyclonedx()` now accept an
  optional `transitive` parameter (a `TransitiveResolution`, unused/`None`
  by default -- fully backward compatible). When given, every non-direct
  resolved dependency is added as its own package/component, nested under
  its *real* parent in the dependency graph (not flattened under the
  root) -- a depth-3 chain like `demo -> click -> colorama -> six` gets
  three separate `DEPENDS_ON`/`dependsOn` edges reflecting exactly that,
  not three edges from the root. An entry whose parent can't be matched
  (e.g. resolved against a different `deps` list) is still included as a
  package, just without that one edge, rather than dropped.
- `cleanroom provenance --resolve-transitive` now wires this in: the
  generated `sbom.spdx.json`/`sbom.cyclonedx.json` include the resolved
  transitive graph, in addition to the existing separate
  `evidence/sbom/transitive-dependencies.json` artefact. Verified against
  the real, live PyPI registry (not just mocked tests): `click`'s actual
  current dependency tree (`colorama`, `importlib-metadata` -> `zipp`)
  resolved and merged correctly, and the merged CycloneDX document passed
  its own real schema validator.
- **Found and fixed a real, separate bug while doing that live-network
  verification**: `transitive.py`'s HTTP calls used whatever default SSL
  context `ssl.create_default_context()` found, which on at least one
  real Python installation had no usable local trust store at all
  (`CERTIFICATE_VERIFY_FAILED: unable to get local issuer certificate`) --
  every lookup silently failed as an opaque "network error" with no
  indication it was actually a local cert-store problem. Fixed by
  preferring `certifi`'s CA bundle when `certifi` is importable (already
  a transitive dependency via `huggingface_hub`'s `httpx`, but not
  required -- falls through to urllib's own default context otherwise).

### Fixed (fourteenth pass — investigated the benchmark's JS false positive, found a real bug behind it)

- Investigated `js-independent-clone`'s false positive (see the previous
  pass) properly rather than tuning the fixture until it passed. Measured
  the raw structural-similarity noise floor for genuinely-unrelated small
  JS snippets (tree-sitter) against equivalent unrelated Python snippets
  (`ast`): JS's mean was ~0.05 (one pair as high as 0.32) versus exactly
  0.0 across all 15 Python pairs tested -- real, but a longer,
  structurally-distinct unrelated JS pair scored 0.02, so it's not simply
  "JS always needs a higher threshold." Tracing the specific false
  positive down to its actual overlapping AST shingles showed it shares
  near-identical boolean-condition phrasing with the reference -- exactly
  the "conventional shared idiom" case the negative-control background-
  score mechanism exists to handle.
- **That investigation surfaced a real, separate, previously-untested
  bug**: `similarity/negative_control.py`'s `background_scores()` never
  passed a `language` hint through to `structural_similarity()`, so
  background scoring for any non-Python implementation always silently
  used the weak `generic_fallback` method -- even when the actual
  foreground reference-vs-implementation comparison used real
  tree-sitter. A background score computed by a different, weaker method
  than the foreground it's meant to be compared against isn't a valid
  background at all. Fixed by adding an optional `language` parameter and
  threading it through from `similarity/engine.py`'s `compare_trees()`
  (which already derives the right language hint per file, just wasn't
  passing it to background scoring). Confirmed the fix actually resolves
  the original false positive: with a plausible negative-control JS
  corpus configured, the same 0.181 score now classifies `conventional`
  instead of `suspicious`.
- New `tests/unit/test_negative_control.py` (no prior test file existed
  for this module at all) plus a new engine-level regression test
  confirming `compare_trees()` passes the derived language through to
  `background_scores()`.

### Added (fifteenth pass — legal-issue engine coverage 10/18 -> 17/18)

- Seven new real heuristics in `legal/engine.py`: `patent_risk` and
  `trademark_risk` (grounded in each reference/dependency licence's
  policy pack `patent_grant`/`trademark_grant` fields -- not a patent/
  trademark registry search, which this tool doesn't perform),
  `linking` (whether the output is distributed as a library other
  software links against, cross-referenced with reference licences'
  copyleft strength -- distinct from `distribution`'s "did you hand out
  copies" question), `confidentiality` and `trade_secrets` (grounded in
  `access_authority` plus sanitisation-blocked history / open similarity
  findings -- not the actual contract text), `database_rights` (a
  per-jurisdiction fact table for the real sui generis database right,
  EU Database Directive 96/9/EC and its national/retained-law
  implementations -- verified England & Wales still has its own
  post-Brexit database right under assimilated law before writing this
  in, rather than assumed), and `contractual_permissions` (grounded in a
  new `reverse_engineering_restriction` field added to all 5 existing
  licence policy packs -- verified none of MIT/Apache-2.0/GPL-3.0-only/
  AGPL-3.0-only/BUSL-1.1's actual licence text imposes one). Only
  `protected_expression` remains `UNKNOWN`: idea/expression merger
  judgment has no deterministic proxy this tool can compute, unlike the
  other 17 issues.
- `cleanroom legal` now also derives `sanitisation_blocked` from the
  evidence ledger (any `cleanroom sanitise` run recorded `result=denied`)
  and feeds it into the `CaseBundle` -- previously declared as a field
  but never populated anywhere, so `confidentiality` could never
  distinguish a clean sanitisation history from one that actually caught
  something.
- 33 new regression tests across `test_legal_engine_and_panels.py` and a
  new CLI-level integration test proving the `sanitisation_blocked`
  wiring end-to-end (writing a real secret-shaped string, confirming
  `cleanroom sanitise` blocks it, then confirming `confidentiality`
  correctly reports `RED`).

### Fixed (fifteenth pass)

- **Caught by real end-to-end manual CLI verification, not just the test
  suite: `database_rights`' jurisdiction fact table used jurisdiction
  *pack ids* (`"england-wales"`, `"usa-federal"`, `"france"`, `"germany"`,
  `"japan"`) as its lookup keys, but `cli.py`'s `legal` command actually
  sets `CaseBundle.jurisdiction` to the raw configured *market code*
  (`"gb"`, `"us"`, `"fr"`, `"de"`, `"jp"` -- two different string spaces,
  see `jurisdiction/resolver.py`'s `COUNTRY_TO_PACK`).** Every real
  `cleanroom legal` run would have silently reported `database_rights` as
  `UNKNOWN` for every actual jurisdiction, defeating the heuristic
  entirely -- caught only because a real installed-CLI smoke test was run
  before considering the feature done, not because any unit test (which
  all used made-up bundles) exercised the mismatch. Fixed the constants
  to use the real market-code strings, and added a regression test that
  asserts pack-id strings specifically do NOT match (to prevent this
  exact confusion recurring silently).

### Added (sixteenth pass — close the judicial-review feedback loop; wire provider diversity)

- Discovered a deeper gap while investigating "provider diversity /
  multi-model panels are recorded in config but not wired to anything":
  `cleanroom judge` only ever WROTE prompt files -- there was no command
  anywhere that read a completed judicial-review answer back into the
  system, for any panel size, even though `legal-finding.schema.json`
  already had `for_release_argument`/`against_release_argument`/
  `adjudication`/`reviewer` fields clearly meant for exactly this.
- New `cleanroom judge-adjudicate <pack-id> <answer-file>
  --panel-member <id> [--model-provider ...] [--model-id ...]`: ingests
  one panel member's answer (a JSON list of per-issue adjudications) and
  merges it into the matching finding(s), matched by issue plus which of
  that pack's real configured markets the finding is under (not the pack
  id itself -- a different string space, see `COUNTRY_TO_PACK`).
  Re-submitting under the same `--panel-member` id replaces that member's
  prior answer rather than duplicating it.
- Extended `legal-finding.schema.json` with a `panel_adjudications` array
  (one entry per independent panel member) and added
  `legal/panels.py::aggregate_panel_decision()` -- the same worst-wins,
  never-round-up philosophy as the existing `aggregate_jurisdiction_decision`,
  applied across panel members instead of across findings. A finding's
  top-level `decision_state`/`reviewer`/argument fields always reflect
  that aggregate, so a single dissenting RED/AMBER panel member is never
  smoothed over by other members' more favourable view, and callers that
  only read the top-level fields keep working correctly regardless of
  `panel_size`.
- The command reports whether `.cleanroom.yml`'s `providers.panel_size`/
  `panel_diversity_required` are actually satisfied yet (distinct
  providers recorded so far) -- informational only. This does NOT change
  `cleanroom report`/`release`'s `global_decision`, which remains purely
  finding-based (the deterministic legal-issue engine's output); the
  judicial panel's adjudication is recorded as additional evidentiary
  context on the finding, not silently made into a second release gate.
- Verified the entire flow by hand against a real project before writing
  tests: ran `init` -> `jurisdiction` -> `legal` -> `judge` ->
  `judge-adjudicate` with two disagreeing simulated panel members,
  confirmed worst-wins held, confirmed resubmission replaced rather than
  duplicated, and confirmed a market mapped to a different pack was left
  untouched. That verification caught a real bug before it ever reached a
  test file: `utc_now_iso` was used but never imported in `cli.py`,
  which would have made every real invocation crash outright.
- 11 new regression tests across `test_cli_end_to_end.py` and
  `test_legal_engine_and_panels.py`.

### Added (seventeenth pass — real, opt-in per-invocation PathGuard enforcement)

- New global `--agent-id <id>` CLI option and `Ctx.enforce_zone_access()`:
  when given, `inspect`/`licence`/`similarity` now call a real
  `PathGuard.check()` against that agent's actual `AgentRegistry` scope
  before reading the path they were given, denying access exactly like
  `run_pathguard_self_test`'s synthetic probe does -- but for a real
  registered agent on a real invocation, not just a unit-level sanity
  check. Without `--agent-id`, every command's behaviour is unchanged
  from before this existed.
- Verified end-to-end against a real project before writing tests, both
  directions: a `cleanroom build`-registered (Zone H+I only) agent is
  genuinely denied `cleanroom licence zone-r` (exit code 4, a real
  `ContaminationFailure`, not a silent pass), and a separately-registered
  Zone-R-scoped agent (registered directly via `AgentRegistry`, since no
  CLI command creates an R-scoped agent today) passes straight through
  with no denial.
- **This does not fully close the gap `zones.py`'s own docstring has
  documented since the second review pass** -- only these three commands
  are wired, and only when `--agent-id` is passed. Every other command,
  and any invocation that omits the flag, still reads files directly with
  no gate. Documented plainly as a narrower, real, opt-in step rather than
  claiming the gap is fully closed.
- 3 new CLI-level regression tests covering the deny path, the allow
  path, and an unregistered `--agent-id` being rejected outright.

### Added (eighteenth pass — real, optional signing for in-toto exports)

- `provenance/intoto.py`'s exported Link Statements can now be really
  signed: new `sign_statement()` and `--signer <gpg-key-id>` on
  `cleanroom verify --export-in-toto-links`, using the exact same
  mechanism and never-fabricate discipline as
  `handoff/manifest.py::sign_manifest` (a detached, ASCII-armored GPG
  signature over the statement's own content). Without `--signer`, or if
  `gpg`/the key id isn't usable, every export honestly stays
  `unsigned: true` -- confirmed both ways: a mocked successful `gpg` call
  producing a real `signature` block and flipping `unsigned` to `false`,
  and this environment's genuine lack of a `gpg` binary producing an
  honest, non-crashing fallback (no `gpg` is actually installed here,
  which is exactly the scenario this discipline exists for).
- This is still a single project-level signer, not per-actor
  (human/agent/tool/CI each signing their own step) -- that would need a
  materially bigger multi-party key-management system. Documented
  plainly as a real but narrower signing capability, not a full in-toto-
  native DSSE/Sigstore envelope with per-step signer attribution.
- 5 new unit tests plus 2 new CLI-level regression tests (one with a
  mocked successful signature, one exercising the real no-`gpg`
  fallback in this environment).

### Added (nineteenth pass — real checksums in transitive dependency resolution and SBOM output)

- `provenance/transitive.py`'s resolved dependencies now carry a real
  registry-published digest: PyPI's per-file `sha256` (preferring the
  wheel, falling back to the sdist when no wheel exists), or npm's SRI
  `integrity` field decoded to hex, falling back to the legacy `shasum`
  (sha1) when `integrity` is absent. Never fabricated or re-hashed
  locally -- only relays whatever digest the registry itself already
  published for the resolved version, in whatever algorithm that
  ecosystem actually used.
- That digest is now wired all the way through into the real SBOM
  documents, not just the standalone `evidence/sbom/transitive-
  dependencies.json` artefact: SPDX packages get a real `checksums`
  entry (`spdx_tools.spdx.model.checksum.Checksum`), CycloneDX
  components get a real `hashes` entry, for both transitive and (where a
  `sha256` is already known) direct dependencies.
- Verified against the live PyPI registry: a real end-to-end
  `cleanroom provenance --resolve-transitive` run against a project
  depending on `click==8.1.7` produced `colorama`'s SBOM-embedded sha256
  checksum matching PyPI's own published wheel digest byte-for-byte.
- 5 new unit tests for digest extraction (`_pypi_lookup`/`_npm_lookup`/
  `_npm_integrity_to_digest`), 4 new SBOM-level unit tests asserting real
  checksums appear on SPDX packages and CycloneDX components (both
  transitive and direct), and an extended CLI integration test asserting
  a resolved transitive dependency's digest reaches the actual SPDX/
  CycloneDX documents written to disk.
- Direct dependencies parsed straight from a manifest
  (`requirements.txt`/`pyproject.toml`/`package.json`) still have no
  digest unless one was already set on the `Dependency` object by some
  other mechanism (e.g. an existing lockfile) -- `discover_dependencies()`
  itself doesn't fetch or hash anything.

### Added (twentieth pass — extend --agent-id PathGuard enforcement to `sanitise`)

- `cleanroom sanitise` now also calls `Ctx.enforce_zone_access` before
  reading its target document, joining `inspect`/`licence`/`similarity`
  from the eighteenth-preceding pass. This one matters most of the four:
  `sanitise` reads a candidate document straight out of Zone H, which is
  the actual R-to-H boundary-crossing gate `PathGuard` exists to police,
  not just an incidental file read.
- `compare` and `similarity --negative-control` were deliberately left
  unguarded and are now documented as such rather than silently skipped:
  `compare` doesn't load a `Project` at all today, so adding enforcement
  would be a real behaviour change (forcing every invocation inside a
  clean-room project directory), not the purely-additive pattern used
  elsewhere; negative-control paths are explicitly meant to sit outside
  the three zones, so PathGuard-checking them would be semantically
  wrong.
- 1 new CLI-level regression test covering both the deny path (an R-only
  agent denied `sanitise` of a Zone H document) and the allow path (an
  H-scoped agent let through).

### Added (twenty-first pass — Cargo.toml/composer.json dependency listing for SBOM generation)

- `sbom.discover_dependencies()` now also parses `Cargo.toml`
  ([dependencies]/[dev-dependencies]/[build-dependencies], both bare
  version-requirement strings and inline tables with their own `version`
  key) and `composer.json` (`require`/`require-dev`, correctly excluding
  platform pseudo-packages: `php`, `hhvm`, `ext-*`, `lib-*`) -- both were
  already read for licence discovery but not for SBOM dependency listing.
  A real TOML parser (stdlib `tomllib` on 3.11+, the `tomli` backport on
  3.10, now a base dependency for that platform) is used for Cargo.toml,
  not a regex -- its dependency tables have shapes a
  `pyproject.toml`-style list regex can't represent. A path/git-only Cargo
  dependency (no registry version) is skipped rather than listed with a
  fabricated version.
- `provenance/transitive.py`'s `--resolve-transitive` still only walks
  PyPI/npm -- a Cargo/Composer direct dependency given to
  `resolve_transitive()` is now explicitly recorded `unresolved` with the
  reason "transitive resolution not yet implemented for the
  cargo/composer ecosystem", rather than being silently misrouted through
  the PyPI lookup (the previous binary npm-or-not-npm ecosystem check
  would have done exactly that, mislabelling a real capability gap as an
  ordinary "package not found").
- Verified end-to-end against a real project: `cleanroom provenance` on a
  Cargo.toml + composer.json project correctly listed all 3 real
  dependencies (`serde`, `tokio`, `guzzlehttp/guzzle`) with real purls and
  versions in both the SPDX and CycloneDX documents, and correctly
  excluded the `php` platform entry.
- 5 new unit tests (Cargo bare-string/inline-table versions, path-only
  skip, Composer platform-package exclusion, `discover_dependencies`
  end-to-end) plus 1 new `transitive.py` test proving the unsupported-
  ecosystem path never reaches the PyPI lookup.

### Added (twenty-second pass — OGL-UK-3.0 licence pack)

- `policies/licences/OGL-UK-3.0.yml` for the UK Open Government Licence
  v3.0, verified against its primary source (The National Archives' own
  licence text) and cross-checked against SPDX's own list entry. A
  genuinely different kind of pack from the other five: a public sector
  information/data licence (`family: public_sector_data`), not a
  conventional OSS software licence -- no share-alike obligation, no
  patent grant, and its own real `key_exclusions` (personal data,
  unlawfully-accessed information, government logos/crests, third-party
  IP the Information Provider wasn't authorised to license) recorded
  rather than glossed over. Cross-referenced against the existing
  `database_rights` heuristic, since OGLv3.0 explicitly licenses
  "copyright OR database right material."
- `license-expression`'s own SPDX symbol table already recognised
  OGL-UK-1.0/2.0/3.0 (and OGL-Canada-2.0) before this pack existed, so
  `cleanroom licence` already concluded OGL-UK-3.0 at high confidence --
  this pack adds the structured obligations/exclusions/prompts the other
  five packs get, it doesn't change discovery confidence (confirmed by
  direct testing: removing the pack and re-running discovery on the same
  fixture still concludes the licence at `high` confidence, since that's
  driven entirely by the SPDX symbol table, not pack existence).
- 3 new unit tests (manifest discovery at high confidence, the pack's
  own structured facts, `evaluate()`'s obligations surfacing).

### Fixed (same pass — `_distribution`/`_linking` silently treated an unpacked licence as non-copyleft)

- Building the OGL pack out required mapping how licence packs,
  `legal/engine.py`'s heuristics, and jurisdiction packs interconnect --
  that map surfaced a real, independent bug: `_distribution()` and
  `_linking()` computed their own inline `load_pack()` lookup and only
  added a term to their "found copyleft" set when a matching pack existed
  AND was copyleft -- a term with NO matching pack (a real, SPDX-
  recognised licence `cleanroom licence` concludes at high confidence,
  just with no `policies/licences/<id>.yml` yet) silently fell through to
  exactly the same `GREEN_WITH_CONDITIONS` result as a term confirmed
  non-copyleft. Every other heuristic reading `load_pack()` results
  (`_licence_obligations`, `_patent_risk`, `_trademark_risk`,
  `_contractual_permissions`) already drew this distinction correctly via
  the shared `_licence_terms_with_packs()` helper; `_distribution`/
  `_linking` predated that helper and were never migrated to it.
- Fixed by switching both to `_licence_terms_with_packs()` and returning
  AMBER ("have no matching policy pack in this installation -- ... is
  unknown to this tool, not confirmed absent") for an unpacked term,
  matching the other four heuristics. This benefits every currently-
  unpacked-but-SPDX-recognised copyleft licence a project might
  reference (LGPL variants, MPL-2.0, EPL-2.0, EUPL, CDDL, OSL-3.0, etc.),
  not just OGL or EUPL specifically.
- Verified by direct reproduction: a real end-to-end `cleanroom legal`
  run against an EUPL-1.2-licensed reference (a real SPDX-recognised
  copyleft licence with no pack) with a configured `binary`/`library`
  distribution model now reports AMBER for both `distribution` and
  `linking`, where it previously reported a false `GREEN_WITH_CONDITIONS`.
- 2 new regression tests confirming this exact case.

### Added (twenty-third pass — three more country licence packs, plus EUPL-1.2)

- `policies/licences/etalab-2.0.yml` for France's Licence Ouverte / Open
  Licence v2.0 (Etalab), verified against its primary source
  (data.gouv.fr's own licence page). Same `family: public_sector_data`
  shape as OGL-UK-3.0, non-copyleft, explicitly stated by its own text to
  be compatible with the UK OGL, CC-BY, and ODC-BY.
- `policies/licences/DL-DE-BY-2.0.yml` and `DL-DE-ZERO-2.0.yml` for
  Germany's attribution/no-attribution public-data licence pair
  (Datenlizenz Deutschland), verified against govdata.de. The Zero
  variant's `key_obligations` honestly records that it imposes none at
  all -- the licence's genuinely notable feature, not an oversight.
- `policies/licences/EUPL-1.2.yml` for the European Union Public Licence
  v1.2 -- unlike the three data-licence packs above, a real copyleft
  SOFTWARE licence. Verified by fetching the actual licence text (via
  OSI's own mirror) and full-text-searching it directly rather than
  summarising an excerpt: confirmed no occurrence of "network"/"SaaS"
  anywhere (so `network_use_triggers_obligations: false`, unlike
  AGPL-3.0), a general breach-termination clause in Article 12 (not a
  patent-specific retaliation clause, so `patent_retaliation_clause:
  false`), and an express patent grant. OSI approval confirmed directly
  on opensource.org ("Approved: July 13, 2017"); both `osi_approved` and
  `fsf_libre` cross-checked against SPDX's own `license-list-data`
  (`isOsiApproved: true`, `isFsfLibre: true`).
- All four new packs' `osi_approved`/`fsf_libre` fields were checked
  against SPDX's own `license-list-data` JSON rather than assumed --
  confirming `false`/`false` for the three data licences (genuinely not
  applicable/not found, not a gap) and `true`/`true` for EUPL-1.2.
- EUPL-1.2 directly demonstrates the `_distribution`/`_linking` fix from
  the same day's earlier pass: with this pack now present, a EUPL-1.2
  reference gets the specific copyleft-distribution-trigger AMBER finding
  rather than the generic "no matching policy pack" one (the two earlier
  regression tests for that fix were switched to MPL-2.0, a real
  SPDX-recognised copyleft licence still genuinely unpacked, so they keep
  testing the no-pack case they were written for).
- 5 new/updated unit tests (per-pack structured facts for all four, plus
  the EUPL-1.2-now-has-a-pack distinction) and a real end-to-end
  `cleanroom licence` run confirming EUPL-1.2 concludes at high confidence
  with its real, verified obligations surfaced.
- Not pursued, honestly: Japan has no SPDX-recognised government
  open-data licence to build a pack around; US federal government works
  are public domain by statute (17 U.S.C. Sec. 105), not by a licence, so
  there's no single "US government licence pack" analogous to the other
  four -- SPDX only has narrower agency-specific identifiers (`NIST-PD`,
  `NASA-1.3`, `NTIA-PD`) for this.

### Added (twenty-fourth pass — EUPL's compatibility clause, and the US-agency licences)

- `CaseBundle.output_licence_id`, wired from `.cleanroom.yml`'s
  `implementation.output_licence` (a field the config schema already
  declared but which nothing previously consumed -- a partially-wired
  gap closed, not a from-scratch feature).
- `EUPL-1.2.yml` gained a structured `compatible_licences` field (Article
  5's own published list, expanded from its "GPL v2 and v3" style wording
  into 21 real SPDX ids, each checked against `license-expression`'s
  known-symbols table before being written) and a new
  `_compatible_licence_overlap()` helper that `_distribution`/`_linking`
  call whenever a copyleft trigger fires. This never auto-resolves a
  finding to GREEN -- confirming the work genuinely qualifies as an
  Article-5 merge into a larger work remains a human question this tool
  does not make on its own -- but the AMBER finding's
  `alternative_explanation` now names the specific overlap (e.g. an
  output licence of `MPL-2.0` against a `EUPL-1.2` reference) instead of
  staying generic.
- 6 new/updated tests: unit tests for the overlap/no-overlap cases on
  both `_distribution` and `_linking`, a pack-level test confirming every
  `compatible_licences` entry is a real SPDX id, and a real end-to-end
  CLI integration test proving `.cleanroom.yml`'s configured
  `output_licence` actually reaches the finding.
- Re-verified (exhaustively this time -- all 2,447 `license-expression`
  known identifiers searched, plus several government-portal fetch
  attempts) that Japan genuinely has no SPDX-recognised government/
  public-sector licence to build a pack around.
- Added `NASA-1.3.yml`, `NIST-PD.yml`, and `NTIA-PD.yml` after all --
  these were previously skipped only for not fitting the "one general
  pack per country" pattern, not because they were unverifiable. Turned
  out to be more substantial and varied than first assumed:
  - `NASA-1.3` (verified by fetching and searching the actual licence
    text) is genuinely NOT a public-domain instrument despite covering
    US government software -- a real, OSI-approved, copyleft-shaped
    licence (`family: copyleft`, `copyleft: strong`) with redistribution/
    source-disclosure obligations and a distinctive indemnification
    clause with no equivalent in this project's other copyleft packs. It
    exists precisely because NASA software is often contractor-authored,
    so real copyright can subsist in it, unlike a pure civil-servant
    work.
  - `NIST-PD`/`NTIA-PD` (verified against SPDX's own license-list-data,
    full licence text) ARE genuine 17 U.S.C. Sec. 105 public-domain
    notices (new `family: public_domain`), but not identical: NTIA-PD's
    text additionally grants rights for non-US jurisdictions where NTIA
    might hold copyright, and asks for a non-binding attribution
    courtesy, neither of which NIST-PD's text contains -- kept as two
    separate packs since the difference is real, not cosmetic.
- 6 new/updated tests, including a real end-to-end `cleanroom licence`
  run for NASA-1.3 and a comparison test proving NASA-1.3 triggers the
  same AMBER copyleft-distribution finding as any other strong-copyleft
  licence while NIST-PD genuinely resolves to a confirmed GREEN (not
  just an unpacked-unknown one).

### Added (twenty-fifth pass — a deep-dive on the two agent teams and the judicial panel, four real enhancements)

- **`cleanroom recruit`**: a new command registering a real Reference-
  side (Zone R only) agent -- the counterpart to `cleanroom build`'s
  Zone H+I agents. Before this, `build` was the ONLY CLI path into
  `AgentRegistry`, hardcoded to `permitted_zones=["H","I"]`; a Zone-R
  agent could only be registered by calling `AgentRegistry` directly in
  Python. `recruit` sets `prohibited_paths=[zone-h, zone-i]` (the same
  belt-and-suspenders pattern `build` uses for zone-r), verified
  end-to-end with `--agent-id`: a real allow into Zone R and a real deny
  into Zone H via PathGuard.
- **`--tool NAME` (repeatable) on both `build` and `recruit`**:
  `AgentRecord.tools` was a dataclass field with zero writers and zero
  readers anywhere in the codebase before this. Now genuinely populated
  and surfaced through `cleanroom status`'s existing agent listing.
- **Real tick timestamps and an efficiency summary for `cleanroom
  heartbeat`**: `Tick` gained a `timestamp` field, stamped by the CLI at
  the actual moment of each call (`utc_now_iso()`), not a fabricated
  default -- a tick loaded from a log written before this field existed
  has `timestamp=None`, honestly. New `tick_intervals_seconds()`/
  `efficiency_summary()` in `orchestration/heartbeat.py` compute real
  elapsed-time-between-ticks, surfaced in `heartbeat`'s own JSON output
  as `average_tick_interval_seconds`/`elapsed_seconds` -- `None` (never
  `0`) when fewer than two stamped ticks exist, so a stall doesn't read
  as "instant." `diagnose()`'s STALLED/LOOPING detection could already
  spot repetition; this adds the actual velocity signal it never had.
- **`release_policy.require_panel_diversity_gate`** (opt-in, default
  `false`): `judge-adjudicate` already computed whether the configured
  `panel_size`/`panel_diversity_required` were satisfied per call, but
  nothing previously read that back at release time -- a project could
  configure real panel requirements and have them silently ignored. New
  `panel_completeness_across_findings()` (`legal/panels.py`) checks every
  finding that has ANY panel_adjudication recorded across the whole
  project; `release_allowed()` gained `panel_diversity_gate`/
  `require_panel_diversity_gate`/`panel_diversity_reasons` params,
  matching the existing three gates' shape exactly. Deliberately narrow:
  a finding with no panel_adjudications at all is not judged -- this
  closes a half-finished-panel-review gap, it does not make judicial
  review itself mandatory. Verified end-to-end: a same-provider
  single-member adjudication genuinely blocks release with the gate on,
  and passes once a second, different-provider member adjudicates.
- Fixed two more stale doc references caught while auditing this
  subsystem: SKILL.md's `--agent-id` paragraph still said only
  `inspect`/`licence`/`similarity` (missing `sanitise`, added in an
  earlier pass) and still described the pre-`recruit` "or directly via
  `AgentRegistry`" workaround as the only path for a non-`build` role.
- 17 new/updated tests across `test_heartbeat.py`,
  `test_legal_engine_and_panels.py`, `test_release_policy.py`, and
  `test_cli_end_to_end.py`, plus real end-to-end CLI verification for
  every one of the four changes.

[Unreleased]: https://github.com/khhvmc5g6f-eng/clean-room-coding/compare/HEAD
