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
- A heuristic legal-issue engine covering 17 of Part XLIV's 18 issues with
  real deterministic logic (`lawful_access`, `copyright_subsistence`,
  `permitted_acts`, `copying`/`substantiality`, `saas_network_provision`,
  `licence_obligations`, `distribution`, `derivative_work_question`,
  `interoperability_provisions`, `patent_risk`, `trademark_risk`,
  `linking`, `confidentiality`, `trade_secrets`, `database_rights`,
  `contractual_permissions`). Only `protected_expression` remains
  honestly `UNKNOWN` -- idea/expression merger analysis has no
  deterministic proxy this tool can compute, unlike the other 17, so it's
  reported UNKNOWN rather than simulated. `cleanroom legal` now actually
  feeds the engine real similarity findings, requirement-graph
  classifications, and sanitisation-blocked history (see "Fixed" below --
  these were previously silent gaps: the CLI built every `CaseBundle`
  without them, so several heuristics reported `UNKNOWN` even after the
  facts they needed had already been produced elsewhere).
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
- 28-command CLI (`init`, `doctor`, `intake`, `inspect`, `licence`,
  `jurisdiction`, `analyse`, `specify`, `sanitise`, `handoff`, `architect`,
  `ai-suggest`, `build`, `heartbeat`, `test`, `compare`, `similarity`,
  `provenance`, `audit`, `legal`, `judge`, `judge-adjudicate`, `remediate`,
  `verify`, `report`, `release`, `status`, `benchmark`) with
  `--json`/`--quiet`/`--verbose`/`--project`/`--config` (now actually
  wired to an explicit config path, not silently ignored) and documented
  exit codes; Click-based
  `CliRunner` integration tests drive the full pipeline end-to-end.
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

**Update (2026-08-22): a minimal harness now exists.**
`orchestration/heartbeat.py` was genuinely orphaned (no caller anywhere,
0% coverage) because it needs a live tick-by-tick observation stream this
stateless CLI had no producer for. Rather than either force-fixing it
into something it isn't or deleting well-written logic, a small, real,
single-shot harness closes the loop: `cleanroom heartbeat <agent-id>
--action-signature ... --files-modified N [--test-result pass|fail]`
appends one tick to a per-agent JSON-Lines log
(`evidence/ticks/<agent_id>.jsonl`, via new `heartbeat.py` functions
`append_tick`/`load_ticks`), re-runs `diagnose()` over that agent's real
tick history, and -- only when the diagnosis actually finds a problem
(`STALLED`/`LOOPING`), never to silently overwrite an explicit `BLOCKED`/
`WAITING`/terminal status set for unrelated reasons -- calls
`AgentRegistry.set_status()`, which itself had no caller anywhere before
this. Whatever is actually orchestrating multiple agents over time (a
script, CI, another framework) calls this once per meaningful tick;
`cleanroom` itself still doesn't spawn or schedule agents (Part LXV:
provider-agnostic). Verified end-to-end via the real installed CLI
binary, not just the test suite: registering an agent, feeding it three
identical-signature ticks, and confirming both the `LOOPING` diagnosis
and that `cleanroom status`'s `orphaned_agents` picks it up afterward.

**Deferred (real, lower-priority findings from the same review):**
~~`similarity/negative_control.py`'s `background_scores` recomputes every
negative-control file's score for every (reference, implementation) pair
rather than caching per implementation file~~ and ~~`structural_method`
not being consulted by `classify()` to down-weight the weaker fallback's
findings~~ -- both **done** during the `ast-grep-py` integration pass
(`similarity/engine.py`'s `impl_text_cache`/`background_cache` and
`effective_threshold`). ~~The PDF jurisdiction table renders row-by-row
with manual `cell()` calls, so a page break could in principle land
mid-row without a repeated header~~ and ~~`ai/suggest.py`'s Hub search
call has no explicit timeout~~ -- both **done**: the jurisdiction table
now uses fpdf2's own `table()` API (repeats headers across pages
automatically), and `search_models()` now bounds the Hub call with an
explicit timeout via a daemon thread (a `ThreadPoolExecutor` was tried
first, but confirmed by direct testing to still block process exit for
the full hang duration -- CPython's `concurrent.futures.thread` joins
every executor-owned thread at interpreter shutdown regardless of
`shutdown(wait=False)`). Fixing the table also surfaced a real,
previously-undetected rendering bug (see "Fixed" in CHANGELOG.md): `_chip()`
never reset the fill colour it set for the coloured "Global decision"
chip, which fpdf2's table cells silently inherited for every column, not
just the intentionally-coloured one -- found by visually reading a
rendered sample report, not just running the test suite.

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
   **Update (2026-08-22): attempted this and hit a real, concrete
   blocker, not just the transitive-dep-count concern above.**
   `scancode.api` transitively imports `typecode`, which requires a
   native `libmagic` shared library; the bundled `typecode-libmagic`
   plugin (the only PyPI package that provides one) has no working
   binary for arm64 macOS + Python 3.14 -- confirmed by installing both
   packages in a clean scratch venv and hitting `NoMagicLibError` on the
   very first `import scancode.api`, with no libmagic dylib anywhere on
   the system to point it at instead. Making this work would require
   installing system-level native software (e.g. `brew install libmagic`)
   on every machine that runs `cleanroom`, which is a materially bigger
   ask than "one more optional Python extra" and wasn't something to do
   unilaterally just to chase this one integration. Left unbuilt rather
   than writing adapter code that couldn't be verified to actually run.
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
5. **SLSA build provenance / in-toto attestations** -- **done** for build
   provenance: `.github/workflows/release.yml` builds the sdist/wheel on
   `release: published` and attests them with GitHub's native
   `actions/attest-build-provenance` (real SLSA v1.0 provenance, in-toto
   format, Sigstore-signed), then uploads both to the release so a
   consumer can `gh attestation verify` what they downloaded. Verified the
   package actually builds cleanly with `python -m build` before writing
   the workflow, rather than assuming it would. The evidence ledger's
   hash-chained events are now also exportable to the in-toto Attestation
   Framework's Link predicate shape (`cleanroom verify
   --export-in-toto-links` -> `provenance/intoto.py`), verified against
   the real spec fetched from `in-toto/attestation` directly rather than
   assumed -- **but these exports are explicitly NOT cryptographically
   signed attestations** (every file says so in an `unsigned`/
   `unsigned_note` field): the ledger authenticates itself by hash-chaining,
   not by each actor holding a signing key, so there is nothing to sign
   with. Presented honestly as a structural interoperability export, not
   overclaimed as equivalent to a real signed in-toto attestation.

None of these four libraries are integrated yet -- each is a real
dependency/architecture decision for the project's maintainer(s) to make
deliberately, not something to silently swap in.

None of these are integrated yet -- doing so is a deliberate future
decision, not a silent gap, since each is a real dependency/architecture
change that should be evaluated on its own.

## Documented limitations (not silently overclaimed)

- **`PathGuard` is now wired into real per-invocation reads for a subset
  of commands, opt-in.** `inspect`/`licence`/`similarity` now call
  `Ctx.enforce_zone_access()` before reading their target path, which
  looks up a real `AgentRegistry` record for whatever agent id is passed
  via the new global `--agent-id <id>` option and runs a real
  `PathGuard.check()` against that agent's actual registered scope --
  verified end-to-end (both the deny path, a Zone-H+I-only `cleanroom
  build` agent denied `zone-r`, and the allow path, an `R`-scoped agent
  let through) against a real project, not just `run_pathguard_self_test`'s
  synthetic probe. Without `--agent-id`, every command's behaviour is
  unchanged from before this existed. **Still a real, narrower gap, not
  fully solved:** only those three commands are wired, and only when
  `--agent-id` is actually passed -- every other command, and any
  invocation that omits the flag, still reads files directly with no
  gate. Extending coverage to every zone-touching command, and to a real
  multi-agent orchestration harness built on top of this library that
  calls `enforce_zone_access` for every subagent file read, remains
  future work.
- **Legal-issue engine**: only `protected_expression` has no dedicated
  heuristic -- always `UNKNOWN`. Idea/expression merger judgment has no
  deterministic proxy this tool can compute, unlike the other 17 issues.
  `patent_risk`/`trademark_risk` (via each licence policy pack's
  `patent_grant`/`trademark_grant` fields, not a registry/freedom-to-
  operate search), `database_rights` (via a per-jurisdiction fact table,
  not a database-content classifier), `confidentiality`/`trade_secrets`
  (via `access_authority` + sanitisation history/similarity findings,
  not the actual contract text), `linking` (via `output_distribution_model`
  + reference licence copyleft strength), and `contractual_permissions`
  (via each policy pack's `reverse_engineering_restriction` field for the
  5 currently-known licences, not the actual contract if access is
  `contractual`) are all real but narrower-than-a-full-analysis triage
  signals -- each documents exactly what it does and doesn't establish in
  its own `alternative_explanation` field.
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
- **SBOM/dependency discovery**: `cleanroom provenance --resolve-transitive`
  now merges the resolved transitive graph directly into the SPDX/
  CycloneDX documents too (each dependency nested under its real parent,
  not flattened under the root), in addition to writing the standalone
  `evidence/sbom/transitive-dependencies.json` artefact -- verified
  against the live PyPI registry (`click` -> `colorama`/
  `importlib-metadata` -> `zipp`, a real 3-level chain) and against
  CycloneDX's own schema validator. Without the flag, `cleanroom
  provenance`'s behaviour is exactly as before (direct declared
  dependencies only, from `requirements.txt`/`pyproject.toml`/
  `package.json`). No hash of resolved versions is captured yet.
- **`cleanroom compare`** (functional equivalence engine) compares two
  already-captured output files under configurable tolerance; it does not
  itself run the reference and implementation programs side-by-side.
- **`cleanroom similarity`'s all-pairs fallback is bounded**
  (`--max-comparisons`, default 2000) when files can't be matched by name;
  comparisons beyond the cap are reported as `comparisons_skipped`, never
  silently dropped, but a very large, entirely-renamed codebase won't get
  full pairwise coverage without raising the cap.
- **Automatic clean-room-level (CR0-CR5) computation** now exists
  (`src/cleanroom/maturity.py`, surfaced via `cleanroom status`'s
  `computed_maturity` field) -- see docs/clean-room-levels.md. It is
  independent of, and never silently reconciled with, the declared
  `clean_room_level` in `.cleanroom.yml`; CR5 can never be automatically
  reached since its qualified-counsel-review criterion has no fact this
  tool can check.
- **Provider diversity / multi-model panels** (`panel_diversity_required`,
  `panel_size` in `.cleanroom.yml`) are now wired to something real: a new
  `cleanroom judge-adjudicate <pack-id> <answer-file> --panel-member <id>`
  command ingests one independent panel member's completed judicial-
  review answer and merges it into the matching legal-finding record(s),
  closing a loop that didn't exist before at any panel size --
  `legal-finding.schema.json` already had `for_release_argument`/
  `against_release_argument`/`adjudication`/`reviewer` fields clearly
  meant for this, but no command read an answer back in. Call it once per
  independent panel member; a new `aggregate_panel_decision()` (worst-
  wins, same philosophy as `aggregate_jurisdiction_decision`) means one
  dissenting member's RED/AMBER is never smoothed over by others' more
  favourable view, and the command reports whether `panel_size`/
  `panel_diversity_required` are actually satisfied yet (distinct
  providers recorded so far). This does NOT change what
  `cleanroom report`/`release` treat as the release-gating
  `global_decision` -- that remains purely finding-based (deterministic
  engine output), not the judicial panel's adjudication, which is
  recorded as additional evidentiary context rather than silently made a
  new gate.
- **SLSA build provenance is now generated on release** (see
  "Competitive landscape" above) via `.github/workflows/release.yml`, and
  the evidence ledger can now export to the in-toto Link predicate shape
  (`cleanroom verify --export-in-toto-links`) -- but those exports are
  unsigned structural mappings, not real signed in-toto attestations (see
  "Competitive landscape" for why: no per-actor signing key exists to
  produce one).
- **No web dashboard, no plugin architecture, no GitLab/Bitbucket
  adapters** -- the CLI/library API is the whole surface for v0.1;
  `docs/architecture.md` notes these as intentionally out of scope for a
  narrow-but-real first release, not abandoned.
- **Benchmark suite / precision-recall measurement** (Parts LXXVI-LXXVII)
  now has a real measured report: `cleanroom benchmark` runs the
  similarity engine against 8 hand-built ground-truth cases (Python,
  JavaScript, Go) and computes precision/recall/F1 for real
  (`src/cleanroom/benchmark.py`, `tests/fixtures/benchmark/manifest.yml`).
  Current measured result: precision 0.80, recall 1.00, F1 0.89 at the
  default threshold -- with one real, undisguised false positive
  (`js-independent-clone`, an honest limitation of the default
  structural threshold for JS's tree-sitter node-kind vocabulary, not
  papered over). Still a small, hand-built, synthetic corpus, not a
  large-scale or statistically representative benchmark -- treat the
  numbers as a real signal on these specific cases, not a general
  accuracy claim.
- **Only Python + Node manifests** are parsed by licence discovery and SBOM
  generation; `Cargo.toml`/`composer.json` are read for licence discovery
  only, not yet for SBOM dependency listing.
- **`cleanroom ai-suggest`'s deployment-shape classification is a
  heuristic** based on Hub `library_name`/file extensions/`pipeline_tag`,
  not a guarantee -- it reports `unknown` rather than guessing whenever
  the evidence is insufficient, but "embeddable" doesn't verify the model
  will actually run acceptably on any given target hardware.

## Likely next additions

1. ~~Wire `PathGuard.check()` into a real per-agent file-access path~~ --
   **partially done**: `inspect`/`licence`/`similarity` now do this via
   opt-in `--agent-id`. Remaining: every other zone-touching command, and
   making it the default (or otherwise mandatory) rather than opt-in, for
   whatever orchestration harness this library is embedded in.
2. ~~Depend on `license-expression`~~ -- **done**: `spdx.py` is now backed
   by the real `license-expression` library. ScanCode Toolkit remains an
   option for a future optional `[licensecheck]` extra (not a base
   dependency, given its ~40 transitive deps) if deeper licence-text
   detection is needed beyond the current fingerprint scanner.
3. ~~`ast-grep-py`-based structural similarity for JS/Go/Rust/Java~~ --
   **done**, and extended to also cover TypeScript/TSX/Ruby/C/C++.
4. ~~More legal-issue heuristics~~ -- **done**, all the way to 17 of 18
   (`distribution`, `licence_obligations`, `derivative_work_question`,
   `interoperability_provisions`, `patent_risk`, `trademark_risk`,
   `linking`, `confidentiality`, `trade_secrets`, `database_rights`,
   `contractual_permissions`). Only `protected_expression` remains
   `UNKNOWN` -- it has no deterministic proxy this tool can compute (see
   "Documented limitations").
5. ~~`spdx-tools`/`cyclonedx-python-lib` to replace the hand-rolled SBOM
   serialization in `provenance/sbom.py`~~ -- **done**, confirmed schema-
   valid against each library's own validator.
6. ~~SLSA build provenance via `actions/attest-build-provenance` in a
   release workflow~~ -- **done** (`.github/workflows/release.yml`, fires
   on `release: published`).
7. ~~Automatic clean-room-level (CR0-CR5) computation from project
   state~~ -- **done** (`src/cleanroom/maturity.py`, `cleanroom status`).
8. ~~Transitive dependency resolution for SBOM generation~~ -- **done**,
   now including the merge into the SPDX/CycloneDX documents themselves
   (see "SBOM/dependency discovery" above), not just the separate
   artefact.
9. ~~Decide `orchestration/heartbeat.py`'s fate~~ -- **done**: a minimal,
   real single-shot harness (`cleanroom heartbeat`) now wires it in
   without building a full multi-agent orchestrator (see "Update
   (2026-08-22)" note above for what this does and doesn't do).
10. ~~Benchmark suite / measured precision-recall report~~ -- **done**
    (`cleanroom benchmark`, 8 ground-truth cases across Python/JS/Go); see
    "Benchmark suite" above for the measured 0.80 precision / 1.00 recall
    result and its one real documented false positive.
11. ~~Investigate the false positive `cleanroom benchmark` found~~ --
    **done**, and it wasn't quite what it first looked like. Measured the
    raw noise floor for genuinely-unrelated small JS snippets via
    tree-sitter (mean ~0.05, one pair at 0.32) against the equivalent
    Python `ast` noise floor (0.0 for all 15 pairs tested) -- JS's
    tree-sitter node-kind vocabulary is real measurably noisier for
    short/similarly-shaped code, but a longer, genuinely
    structurally-distinct unrelated JS pair scored 0.02, comparable to
    Python. So it's not a blanket "JS needs a higher default threshold"
    finding. Tracing the specific `js-independent-clone` false positive
    down to its actual overlapping shingles surfaced something more
    useful: it shares near-identical boolean-condition phrasing with the
    reference (`active && priority >= threshold`) -- exactly the
    "conventional shared idiom, not copying" case `classify()`'s
    negative-control background-score mechanism exists to handle. That
    led to a real, separate, previously-untested bug (see "Fixed" below):
    `negative_control.py`'s `background_scores()` never passed a
    `language` hint to `structural_similarity()`, so background scoring
    for any non-Python file always silently used the weak
    `generic_fallback` method, never real tree-sitter, even when the
    foreground comparison did. Fixed, and confirmed the fix actually
    resolves this exact case: with a plausible negative-control JS corpus
    configured, the same 0.181 score now classifies `conventional`, not
    `suspicious`. The benchmark corpus itself doesn't wire in negative
    controls (its manifest has no such concept yet) so its measured
    0.80 precision stands as an honest "structural comparison alone, no
    negative controls" number -- a real user running `cleanroom
    similarity --negative-control ...` gets the benefit of this fix.
12. Attempted **ScanCode Toolkit** as an optional `[licensecheck]` extra
    and hit a real, concrete blocker (a native `libmagic` dependency with
    no working plugin for arm64 macOS + Python 3.14) -- see "Competitive
    landscape" above. Revisit only if a way to make this reliably
    installable across platforms materialises, or if the maintainer is
    willing to require a system-level `libmagic` install.
