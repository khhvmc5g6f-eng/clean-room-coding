# Roadmap

Clean Room Coding v0.1.0 is a **deep-but-narrow** first build: everything
listed under "Built and tested" is real, working code with passing tests
-- nothing is scaffolded-but-fake. Everything under "Documented
limitation" is a genuine gap, called out here (and usually inline in the
relevant module's docstring) rather than silently claimed as complete.

This roadmap was reviewed and extended after an internal code review,
security audit, and a competitive-landscape research pass (2026-08-22) --
see "External review findings" and "Competitive landscape" below.

## Built and tested (v0.1.0)

- Three-zone project model (`cleanroom init`, with an explicit
  `--target-language` prompt so the implementation language is always a
  stated choice, never assumed to match the reference), technically
  allow-listed `PathGuard` isolation, and a `PathGuard` mechanism self-test
  plus a project-specific `check_agent_zone_consistency` cross-check
  (`cleanroom audit`) -- see "External review findings" below for the
  honest limits of what this currently proves.
- Append-only, hash-chained evidence ledger (`cleanroom` writes to it from
  nearly every command; `cleanroom verify` detects tampering, and degrades
  gracefully rather than crashing on a truncated/interrupted write).
- Deterministic licence discovery (LICENSE/NOTICE/COPYING files, SPDX
  headers, `package.json`/`pyproject.toml`/`Cargo.toml`/`composer.json`
  manifests, with symlink/non-regular-file safety) and policy evaluation,
  with 5 licence packs: MIT, Apache-2.0, GPL-3.0-only, AGPL-3.0-only,
  BUSL-1.1 (this project's own licence).
- SPDX expression parsing backed by the real `license-expression` library
  (`AND`/`OR`/`WITH`, the full real SPDX licence list via
  `get_spdx_licensing()`, `LicenseRef-*` always flagged for manual review)
  -- replaced the earlier hand-rolled, curated-subset parser.
- Jurisdiction resolution engine with 6 real, independently fact-checked
  packs: England & Wales, US federal, EU, France, Germany, Japan (real
  statutes and leading case law, structured review questions, never
  defaulting to a single assumed jurisdiction).
- Sanitisation scanner (secrets, code-like text, prompt-injection
  phrasing, distinctive-identifier overlap covering camelCase/PascalCase/
  snake_case, verbatim-text overlap checked at every offset via an n-gram
  set rather than a stride-sampled search) and the raw/sanitised
  differential record.
- Requirement graph + GIVEN/WHEN/THEN behavioural specs, with mechanical
  observable-requirement/source-implementation-detail partitioning and
  traceability reporting that never inflates completion percentages.
- Cryptographically hashed `HANDOFF_MANIFEST.json` (+ optional GPG
  detached signature, now with a timeout so a pinentry prompt can't hang
  the CLI) and integrity verification, with symlink-escape detection so
  Zone R content can't be smuggled into the "sanitised" bundle via a link.
- Similarity engine: lexical (token-shingle Jaccard), structural (real
  Python AST comparison, and real tree-sitter comparison via `ast-grep-py`
  for JavaScript/TypeScript/Go/Rust/Java/Ruby/C/C++; a generic bracket/
  keyword fallback -- down-weighted via a higher classification threshold
  -- only for languages neither path supports), and negative-control
  background scoring -- with automatic
  classification restricted to `coincidental`/`conventional`/`suspicious`
  only (`required`/`constrained`/`material` require human/panel review by
  design). Now wired to a real CLI command, `cleanroom similarity
  <ref-dir> <impl-dir>`, which exits `SIMILARITY_FAILURE` (7) on an
  unresolved suspicious/material finding.
- SBOM generation (SPDX 2.3 + CycloneDX 1.5 JSON) from direct declared
  dependencies, serialized via the real `spdx-tools`/`cyclonedx-python-lib`
  libraries' own model/converter instead of hand-typed JSON -- confirmed
  schema-conformant with each library's own validator
  (`validate_full_spdx_document`, `make_schemabased_validator`), including
  a fix-up for a real spdx-tools 0.8.5 quirk (see "Fixed" below).
- A heuristic legal-issue engine covering 10 of Part XLIV's 18 issues with
  real deterministic logic (`lawful_access`, `copyright_subsistence`,
  `permitted_acts`, `copying`/`substantiality`, `saas_network_provision`,
  `licence_obligations`, `distribution`, `derivative_work_question`,
  `interoperability_provisions`); the remaining 8 (`patent_risk`,
  `trademark_risk`, `database_rights`, `confidentiality`, `trade_secrets`,
  `linking`, `contractual_permissions`, `protected_expression`) are
  honestly `UNKNOWN` pending more heuristics or human review -- never
  fabricated. `cleanroom legal` now actually feeds the engine real
  similarity findings and requirement-graph classifications (see "Fixed"
  below -- this was previously a silent gap: the CLI built every
  `CaseBundle` without them, so `copying`/`substantiality` and
  `derivative_work_question` reported `UNKNOWN` even after `cleanroom
  similarity`/`cleanroom specify` had produced real facts).
- Adversarial-counsel + judicial-review **prompt generation**
  (`cleanroom judge`) for whatever LLM harness answers them, plus
  deterministic decision-state aggregation that can never produce an
  unconditional `GREEN` automatically.
- **Remediation feedback loop** (`cleanroom remediate`): every RED legal
  finding and every suspicious/material similarity finding is
  automatically turned into a tracked task, routed back to the
  implementation team as a `blocked` node in the requirement graph.
  Re-running after an actual fix clears it automatically
  (`resolved_by_rescan`); a human can instead explicitly accept residual
  risk (`--override --by --notes`, recorded as `resolved_by_override` so
  it's never confused with an actual fix). `cleanroom release` refuses to
  proceed while any blocking task is open -- this is the concrete,
  testable answer to "does a flagged legal concern get sent back to be
  recoded before release."
- Optional AI-model suggestion (`cleanroom ai-suggest`): asks explicitly
  whether AI/ML capability should be added, and if so searches the real
  Hugging Face Hub, classifying each candidate as `embeddable` (ships an
  ONNX/GGUF/TFLite/CoreML artefact, no server needed), `server_required`,
  or honestly `unknown` when there isn't enough evidence -- and
  cross-checks each model's Hub licence tag against the project's own
  `dependency_policy` using the same engine `cleanroom licence` uses.
- Release policy engine with a mandatory human sign-off gate by default
  (exit code 9), a `RED` in any required jurisdiction blocking release
  outright regardless of other jurisdictions, and now an open blocking
  remediation task blocking release unconditionally too.
- Rich final report: `cleanroom report` always writes
  `CLEAN_ROOM_CERTIFICATE.json` + `CLEAN_ROOM_REPORT.md`, and `--html`/
  `--pdf` add a colour-coded HTML page and a paginated PDF (via fpdf2, no
  fragile system-library dependency) covering what the project started
  with, what it did (derived from the evidence ledger), functional
  coverage, remediation status, jurisdictions, and outstanding issues.
- 25-command CLI (`init`, `doctor`, `intake`, `inspect`, `licence`,
  `jurisdiction`, `analyse`, `specify`, `sanitise`, `handoff`, `architect`,
  `ai-suggest`, `build`, `test`, `compare`, `similarity`, `provenance`,
  `audit`, `legal`, `judge`, `remediate`, `verify`, `report`, `release`,
  `status`) with `--json`/`--quiet`/`--verbose`/`--project`/`--config`
  (now actually wired to an explicit config path, not silently ignored)
  and documented exit codes; Click-based `CliRunner` integration tests
  drive the full pipeline end-to-end.
- The Agent Skill (`skills/clean-room-coding/SKILL.md` +
  progressive-disclosure `references/`).
- Licensed under **BUSL-1.1** (Business Source License 1.1): free for
  essentially all use including internal commercial use, restricted from
  being resold/white-labelled as a competing product, converting to
  GPL-3.0-or-later on 2030-08-22.

## External review findings (2026-08-22) -- fixed this pass

An internal code review and security audit (two independent passes) found
and this pass fixed:

- **Critical (security):** `run_isolation_test` (now `run_pathguard_self_test`)
  proved the `PathGuard` mechanism works in isolation, but nothing in
  `cli.py` actually routed real file reads through it -- so it was not
  evidence that any specific project's real agents were ever gated by it.
  Fixed honestly rather than oversold: the self-test's docstring and every
  consumer now say plainly what it does and doesn't prove, and a new,
  real, project-specific check (`check_agent_zone_consistency`) cross-
  references the `AgentRegistry` against the evidence ledger for genuine
  zone violations. Full live enforcement (every CLI read gated per
  invoking agent) remains a documented gap -- see below.
- **Critical (correctness):** `licence/discovery.py`'s text fingerprinting
  matched multiple licences simultaneously on real, unmodified BSD-3-Clause
  and AGPL-3.0/LGPL license text (their own text contains another
  licence's marker phrase as a substring), which reported unambiguous,
  mainstream licences as "conflicting" and could block a release under the
  default policy. Fixed with explicit per-fingerprint exclusion markers;
  regression-tested against the real gnu.org AGPL-3.0/LGPL-3.0/LGPL-2.1
  texts and a canonical BSD-3-Clause file.
- **High (security):** a symlink inside Zone H or a scanned reference tree
  that resolved outside the scanned root was previously followed and
  hashed/read without question -- meaning Zone R content could be
  smuggled into a "sanitised" handoff manifest via a symlink, and a FIFO
  named `LICENSE` would hang licence discovery forever. Fixed with a
  shared `is_safe_regular_file` check used by `hash_tree`, the handoff
  manifest builder, and licence discovery.
- **High (security):** `PathGuard`'s `permitted_paths` field was declared
  but never consulted, so it silently allowed any path outside the three
  named zones -- looked like an allow-list but wasn't one. Fixed: when
  `permitted_paths` is populated, `PathGuard` now behaves as a true
  allow-list.
- **Medium:** the evidence ledger raised an unhandled `JSONDecodeError` on
  a truncated/corrupt line (a realistic outcome of a process being killed
  mid-write) instead of degrading gracefully. Fixed: corrupt lines are now
  skipped and reported as a `verify_chain()` finding rather than crashing.
- Several correctness/robustness fixes: `--config` is now actually wired
  through to config discovery (previously parsed and silently ignored);
  `cleanroom licence`/`cleanroom handoff` now log evidence events on their
  failure paths, not only on success; `cleanroom audit` now checks Zone H
  licences against the project's real policy instead of a hardcoded
  MIT/Apache-2.0 allowlist, and actually fails the exit code on a blocking
  finding; the sanitisation scanner's identifier-overlap check now catches
  snake_case identifiers (it previously only matched camelCase/PascalCase,
  missing the majority of realistic Python/Rust/Ruby leaks); the
  verbatim-overlap scanner now checks every offset via an n-gram set
  (previously stride-sampled, which could miss a run whose length was
  close to the threshold); the evidence ledger no longer re-reads the
  whole file on every append (was O(n^2) over a ledger's lifetime); the
  gpg signing subprocess now has a timeout and runs non-interactively.

## Second review pass (2026-08-22) -- code added after the first pass, fixed

A follow-up review specifically covering code written after the first pass
above (the similarity engine's CLI wiring, the remediation loop, AI-model
suggestion, and the PDF/HTML report renderers), plus a full legal-citation
fact-check and a Skill-accuracy audit, found and this pass fixed:

- **Critical (correctness): a regressed finding stayed silently resolved
  forever.** `legal/remediation.py`'s `reconcile()` only ever transitioned
  an `open` task to `resolved_by_rescan`; if a finding that had already
  cleared (and was marked `resolved_by_rescan`) reappeared later (a fix
  reverted, a regression reintroduced), the task was left
  `resolved_by_rescan` and never reopened -- `cleanroom release` would
  silently stop blocking on a live RED finding. Confirmed by direct
  reproduction before fixing. Fixed: a `resolved_by_rescan` task whose
  finding reappears is now reopened; a `resolved_by_override` task
  (a deliberate human decision) correctly never auto-reopens.
- **Critical (correctness): `cleanroom report --pdf` crashed on ordinary
  human-entered text.** fpdf2's core fonts only support Latin-1; a
  project name or finding description containing an em dash, curly
  quotes, or an ellipsis (routine in both human-entered `.cleanroom.yml`
  metadata and LLM-authored legal/similarity finding text) raised
  `FPDFUnicodeEncodingException` and crashed the report outright.
  Confirmed by direct reproduction. Fixed by downgrading common Unicode
  punctuation to ASCII equivalents and falling back to safe replacement
  for anything else, applied centrally to every `cell`/`multi_cell` call.
- Remediation task IDs were recomputed by sort position on every
  `reconcile()` call rather than assigned once; under same-tick timestamp
  collisions (rapid re-runs, a frozen clock in tests) a human's recorded
  `--override <id>` could silently apply to a different finding after a
  later run. Fixed: IDs are now assigned once at creation and never
  reassigned.
- `similarity/engine.py` matched at most one same-named reference file per
  basename (a dict keyed by filename, last-sorted-wins), silently losing
  a comparison against any other reference file sharing that basename
  (e.g. two different reference directories both containing `utils.py`) --
  contradicting the module's own "never silently dropped" documentation.
  Fixed: an impl file now matches every same-named reference file.
- `similarity/engine.py`'s all-pairs fallback truncated with a flat slice
  ordered by impl-file sort position, so hitting `--max-comparisons` could
  give an early-sorted impl file full reference coverage while a
  later-sorted one -- which could just as plausibly be the copied one --
  got none. Fixed with round-robin distribution across unmatched impl
  files.
- `similarity/structural.py`'s generic (non-Python) fallback matched
  keywords by substring/prefix, misreading `"iffy"`, `"definitely(...)"`,
  `"classList.add(...)"` as `if`/`def`/`class` control-flow structure, and
  clamped only the *emitted* depth value while letting the internal
  counter go negative on a stray unmatched bracket (plausible inside a
  string/comment, since this fallback does no comment/string stripping),
  permanently offsetting every subsequent line's signature. Fixed with a
  word-boundary regex and by clamping the counter itself; also extended
  the keyword list to cover Go/Rust/Ruby (`func`, `fn`/`match`/`loop`,
  `elsif`/`unless`/`until`), which the module is explicitly routed to
  handle but previously had no vocabulary for.
- `ai/suggest.py`'s Hub-licence-to-SPDX table was missing several common,
  *legitimate* SPDX identifiers (`CC-BY-NC-4.0`, `WTFPL`, `OFL-1.1`,
  `LGPL-2.1-only`), which the fix adds -- while deliberately continuing to
  leave model-specific "Responsible AI License" tags (`openrail`,
  `llama2`/`llama3`, `bigscience-openrail-m`, etc.) unmapped, since they
  carry real use-restrictions with no honest SPDX equivalent.
- **`sanitisation/differential.py` (the RAW_ANALYSIS/SANITISED_SPECIFICATION
  differential record, Part XXI) was fully implemented but never called
  from anywhere** -- `cleanroom sanitise` built its own ad-hoc dict instead
  of using it, meaning the differential record ADR-0002 documents as part
  of the three-zone model didn't actually exist in the live pipeline.
  Fixed: `cleanroom sanitise` now builds and persists a real
  `SanitisationReport`/`DifferentialEntry` record (each blocking finding
  becomes an explicit "removed" entry with its reason).
- Two legal citation errors, found by an independent fact-check against
  primary sources (legislation.gov.uk, copyright.gov, CourtListener,
  BAILII, MariaDB's own BUSL FAQ) that verified ~30 claims total: IBCOS
  Computers Ltd v Barclays Highland Finance Ltd was missing "Mercantile"
  from the party name; Oracle America, Inc. v. Google LLC, 593 U.S. ___
  (2021) had the wrong party order and an unfinalised reporter citation
  (the Supreme Court case is Google LLC v. Oracle America, Inc., 593 U.S.
  1 (2021) -- Google was petitioner). Both fixed. Every other citation and
  every licence-pack mechanic checked out accurate.
- The Skill's own documentation had drifted from the code it describes:
  `references/exit-codes.md` wrongly said `SIMILARITY_FAILURE` (7) was
  "not yet wired" (it has been, since `cleanroom similarity` was added,
  and this directly contradicted SKILL.md's own phase 11); `cleanroom
  verify` and `cleanroom status` were never mentioned anywhere in the
  skill despite being real, shipped commands; the licence-pack count was
  stale at four in two places (BUSL-1.1 makes it five). All fixed.

**Confirmed as genuinely orphaned, left as a documented decision rather
than force-fixed:** `orchestration/heartbeat.py` (Part XXVIII stall/loop
detection) has no caller anywhere in the codebase and 0% test coverage --
unlike `differential.py`, it has no natural single-shot CLI hook (it's
designed to consume a live tick-by-tick observation stream from an
orchestration harness running multiple agents over time, which this
stateless CLI doesn't have a producer for yet). It's well-written and
documented, but not wired to anything real. Wiring it in properly needs an
actual multi-agent orchestration harness to feed it ticks -- tracked as a
roadmap item, not silently removed or silently claimed as functional.

**Deferred (real, lower-priority findings from the same review, not yet
acted on):** `similarity/negative_control.py`'s `background_scores`
recomputes every negative-control file's score for every (reference,
implementation) pair rather than caching per implementation file (real
but pure performance, not correctness); `structural_method` (`python_ast`
vs `generic_fallback`) is recorded on each finding but not yet consulted
by `classify()` to down-weight the weaker fallback's findings relative to
real AST comparisons; the PDF jurisdiction table renders row-by-row with
manual `cell()` calls, so a page break could in principle land mid-row
without a repeated header (fpdf2's built-in table API would fix this more
robustly than a manual patch); `ai/suggest.py`'s Hub search call has no
explicit timeout.

## Competitive landscape (researched 2026-08-22)

A research pass across GitHub and Hugging Face found no existing tool
that combines process-separation (reference/handoff/implementation zones,
an evidence ledger, jurisdiction resolution) with license/similarity/SBOM
tooling the way this project does -- the closest analogue is a narrower
two-zone Claude Code skill (`clean-room-skill` on npm) with no license
scanning, similarity engine, SBOM, or evidence ledger. Concrete, real
opportunities to strengthen this project by depending on established
libraries rather than hand-rolled logic, in priority order:

A follow-up pass (2026-08-22) turned each of the four candidates below into
a concrete, verified integration plan (real current PyPI versions/licences,
actual API signatures fetched from source, and an effort estimate) rather
than a bare "worth considering":

1. **`license-expression`** (PyPI `license-expression`, v30.4.4, Apache-2.0)
   -- would replace `licence/spdx.py`. `Licensing(symbols=[...]).validate(expr)`
   returns an `ExpressionInfo(errors, invalid_symbols, normalized_expression)`
   that maps closely onto this project's known/unknown split, and unknown
   identifiers fall through permissively (no exception) unless
   `validate=True` is requested -- matching this project's "never silently
   turn uncertainty into certainty" design. The one real gap: `parse()`
   returns a nested boolean-algebra tree, not the flat, appearance-ordered
   `operators` list `spdx.py` currently exposes -- needs a small tree-walk
   adapter or keeping the existing regex tokenizer just for that field.
   **Effort: ~1-2 days** (a genuine compatibility shim, not a drop-in).
2. **ScanCode Toolkit** (PyPI `scancode-toolkit`, v32.5.0, and a lighter
   `scancode-toolkit-mini` twin; both `Apache-2.0 AND CC-BY-4.0 AND
   LicenseRef-scancode-other-permissive AND LicenseRef-scancode-other-copyleft`
   for bundled third-party reference license *text*, not the code itself)
   -- would replace/augment `licence/discovery.py`'s hand-rolled text
   fingerprints, whose exact failure mode (see the second review pass
   above -- BSD-3/BSD-2 and AGPL/GPL-3.0 substring collisions) is
   structurally what ScanCode's real rule-based/n-gram matcher with
   `min_score`/`match_coverage` thresholds is built to avoid. Its
   `scancode.api.get_licenses(path)` returns SPDX expressions natively
   plus a numeric `score`/`match_coverage`/`rule_relevance` per match (no
   confidence enum -- needs a bucketing scheme), and it operates on a file
   path only (no in-memory string API). Confirmed heavy: ~40 transitive
   dependencies (lxml, pdfminer.six, pefile, etc.) even in the "mini"
   variant -- this is real, not just reputation. **Recommendation: make it
   an optional `[licensecheck]` extra, not a base dependency; effort ~1-2
   days for a thin adapter + tests.**
3. **`spdx-tools`** (PyPI `spdx-tools`, v0.8.5, Apache-2.0) and
   **`cyclonedx-python-lib`** (PyPI `cyclonedx-python-lib`, v11.12.0,
   Apache-2.0 -- note this is the *library*, distinct from the
   `cyclonedx-bom` CLI package, which does real transitive dependency
   resolution and would be scope creep beyond this project's documented
   direct-deps-only v0.1 design) -- both would replace the hand-rolled
   dict serialisation in `provenance/sbom.py` with typed models
   (`Document`/`Package`/`Relationship`; `Bom`/`Component`) plus a real
   schema validator (`validate_full_spdx_document`;
   `JsonStrictValidator(SchemaVersion.V1_5)`) gained for free.
   `discover_dependencies()` stays untouched; only `to_spdx`/`to_cyclonedx`/
   `save` change. **Effort: ~1.5-2 days combined**, low risk -- the main
   surprise risk is the libraries' stricter validation surfacing latent
   bugs (e.g. a malformed purl) the current permissive code accepts
   silently.
4. **`ast-grep-py`** (PyPI `ast-grep-py`, v0.45.1, MIT) -- confirmed the
   clear winner over `py-tree-sitter` for the generic structural-similarity
   fallback: JavaScript, Go, Rust and Java are all in ast-grep's built-in
   language table (a single compiled wheel, no per-language grammar
   packages to install/version separately, unlike `py-tree-sitter` where
   `tree-sitter-java`'s grammar package is confirmed stalled at Dec 2024
   versus the others' 2025/2026 releases -- a real per-language
   maintenance-drift risk `ast-grep-py` avoids). `SgRoot(source,
   lang).root().kind()` / `.children()` maps directly onto the existing
   `type(node).__name__` walk pattern used for Python. **Effort: ~half a
   day to a day total for all four languages** once one
   `<lang>_structural_shape()` wrapper exists, since ast-grep normalizes
   the API across languages -- the remaining per-language cost is
   validating that each grammar's node-kind vocabulary shingles sensibly,
   not writing new code per language.
5. **SLSA build provenance / in-toto attestations** -- not yet
   implemented (an earlier banner draft overstated this; corrected).
   Genuinely buildable next: GitHub's native
   `actions/attest-build-provenance` action produces real SLSA provenance
   (itself an in-toto-format attestation) for anything built in the
   existing CI workflow -- a natural, small addition. Separately, the
   evidence ledger's hash-chained events are conceptually close to
   in-toto's "link" metadata; an export from the ledger to real in-toto
   link files is a natural fit for this project's own architecture.

None of these four libraries are integrated yet -- each is a real
dependency/architecture decision for the project's maintainer(s) to make
deliberately, not something to silently swap in.

None of these are integrated yet -- doing so is a deliberate future
decision, not a silent gap, since each is a real dependency/architecture
change that should be evaluated on its own.

## Documented limitations (not silently overclaimed)

- **`PathGuard` is not yet wired into every real file read the CLI
  performs.** See "External review findings" above -- `cli.py`'s commands
  read project files directly rather than through a per-invocation
  `PathGuard.check()`, because the current stateless-CLI design doesn't
  track "which registered agent is running this command." Building on
  `cleanroom` as a library (e.g. an orchestration harness that spawns
  implementation subagents) can and should gate their file access through
  `PathGuard` directly; the CLI itself doesn't yet do this automatically.
- **Legal-issue engine**: 8 of 18 issues (`contractual_permissions`,
  `protected_expression`, `linking`, `patent_risk`, `trademark_risk`,
  `database_rights`, `confidentiality`, `trade_secrets`) have no dedicated
  heuristic yet -- always `UNKNOWN`. Each would need facts this tool
  cannot compute deterministically (actual contract/NDA text analysis,
  patent/trademark/database-right registry lookups, or idea/expression-
  merger judgment), not just a missing feature.
- **Jurisdiction packs**: England & Wales, US federal, EU, France, Germany
  and Japan now exist (6 of the 6 originally mentioned in the design
  brief). Adding a further jurisdiction is still a real research task (see
  CONTRIBUTING.md), not a template fill-in -- each existing pack's
  citations were independently verified against primary sources
  (official statute translations, EUR-Lex/BGH/Cour de cassation/
  Bundesgerichtshof/court self-published texts), and two case law
  citations in the France and Japan packs are explicitly flagged as
  unverified/pre-dating the modern IP court structure rather than forced
  into a false fit.
- **Structural similarity**: real AST comparison for Python, and real
  tree-sitter comparison (via `ast-grep-py`) for JavaScript/TypeScript/Go/
  Rust/Java/Ruby/C/C++. Any other language still uses a much weaker
  bracket/keyword-shape fallback (`structural_similarity` reports which
  method was used, and `compare_trees` down-weights fallback-based
  findings with a higher classification threshold).
- **SBOM/dependency discovery**: direct declared dependencies only, from
  `requirements.txt`/`pyproject.toml`/`package.json`. No transitive
  resolution, no registry lookups for licence/hash of resolved versions.
- **`cleanroom compare`** (functional equivalence engine) compares two
  already-captured output files under configurable tolerance; it does not
  itself run the reference and implementation programs side-by-side.
- **`cleanroom similarity`'s all-pairs fallback is bounded**
  (`--max-comparisons`, default 2000) when files can't be matched by name;
  comparisons beyond the cap are reported as `comparisons_skipped`, never
  silently dropped, but a very large, entirely-renamed codebase won't get
  full pairwise coverage without raising the cap.
- **No automatic clean-room-level (CR0-CR5) computation** -- see
  docs/clean-room-levels.md. The level in `.cleanroom.yml` is a
  declaration the project's owners back up manually today.
- **Provider diversity / multi-model panels** (`panel_diversity_required`,
  `panel_size` in `.cleanroom.yml`) are recorded in config but not yet
  wired to an actual multi-provider LLM adapter layer -- Claude via
  whatever harness runs `cleanroom judge`'s prompts is the only path today.
- **No SLSA/in-toto attestations yet** -- see "Competitive landscape";
  genuinely buildable, not yet built.
- **No web dashboard, no plugin architecture, no GitLab/Bitbucket
  adapters** -- the CLI/library API is the whole surface for v0.1;
  `docs/architecture.md` notes these as intentionally out of scope for a
  narrow-but-real first release, not abandoned.
- **Benchmark suite / precision-recall measurement** (Parts LXXVI-LXXVII)
  is limited to `tests/fixtures/benchmark/` -- a small hand-built set, not
  yet a measured precision/recall report.
- **Only Python + Node manifests** are parsed by licence discovery and SBOM
  generation; `Cargo.toml`/`composer.json` are read for licence discovery
  only, not yet for SBOM dependency listing.
- **`cleanroom ai-suggest`'s deployment-shape classification is a
  heuristic** based on Hub `library_name`/file extensions/`pipeline_tag`,
  not a guarantee -- it reports `unknown` rather than guessing whenever
  the evidence is insufficient, but "embeddable" doesn't verify the model
  will actually run acceptably on any given target hardware.

## Likely next additions

1. Wire `PathGuard.check()` into a real per-agent file-access path for
   whatever orchestration harness this library is embedded in (the
   remaining piece of the isolation-enforcement gap above).
2. ~~Depend on `license-expression`~~ -- **done**: `spdx.py` is now backed
   by the real `license-expression` library. ScanCode Toolkit remains an
   option for a future optional `[licensecheck]` extra (not a base
   dependency, given its ~40 transitive deps) if deeper licence-text
   detection is needed beyond the current fingerprint scanner.
3. ~~`ast-grep-py`-based structural similarity for JS/Go/Rust/Java~~ --
   **done**, and extended to also cover TypeScript/TSX/Ruby/C/C++.
4. ~~More legal-issue heuristics (particularly `distribution`,
   `licence_obligations`, `derivative_work_question`)~~ -- **done**, along
   with `interoperability_provisions`. The remaining 8 issues each need
   facts this tool cannot compute deterministically (see "Documented
   limitations").
5. ~~`spdx-tools`/`cyclonedx-python-lib` to replace the hand-rolled SBOM
   serialization in `provenance/sbom.py`~~ -- **done**, confirmed schema-
   valid against each library's own validator.
6. SLSA build provenance via `actions/attest-build-provenance` in a
   release workflow (confirmed buildable; not yet built).
7. Automatic clean-room-level (CR0-CR5) computation from project state
   (not yet started).
8. Transitive dependency resolution for SBOM generation (still not
   started -- separate from the serialization work just done).
9. Decide `orchestration/heartbeat.py`'s fate: build a real multi-agent
   orchestration harness that can feed it observation ticks, or remove it
   -- it is currently well-written but genuinely unused (see "documented
   decision" note above).
