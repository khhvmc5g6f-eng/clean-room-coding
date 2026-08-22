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
- A minimal SPDX expression parser (`AND`/`OR`/`WITH`, `LicenseRef-*`,
  a curated known-identifier list -- not the full SPDX licence list).
- Jurisdiction resolution engine with 2 real packs: England & Wales and
  US federal (real statutes and leading case law, structured review
  questions, never defaulting to a single assumed jurisdiction).
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
  Python AST comparison; generic bracket/keyword fallback for other
  languages), and negative-control background scoring -- with automatic
  classification restricted to `coincidental`/`conventional`/`suspicious`
  only (`required`/`constrained`/`material` require human/panel review by
  design). Now wired to a real CLI command, `cleanroom similarity
  <ref-dir> <impl-dir>`, which exits `SIMILARITY_FAILURE` (7) on an
  unresolved suspicious/material finding.
- SBOM generation (SPDX 2.3 + CycloneDX 1.5 JSON) from direct declared
  dependencies.
- A heuristic legal-issue engine covering 5 of Part XLIV's 18 issues with
  real deterministic logic (`lawful_access`, `copyright_subsistence`,
  `permitted_acts`, `copying`/`substantiality`, `saas_network_provision`);
  the remaining 13 are honestly `UNKNOWN` pending more heuristics or human
  review -- never fabricated.
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
  GPL-2.0-or-later on 2030-08-22.

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

## Competitive landscape (researched 2026-08-22)

A research pass across GitHub and Hugging Face found no existing tool
that combines process-separation (reference/handoff/implementation zones,
an evidence ledger, jurisdiction resolution) with license/similarity/SBOM
tooling the way this project does -- the closest analogue is a narrower
two-zone Claude Code skill (`clean-room-skill` on npm) with no license
scanning, similarity engine, SBOM, or evidence ledger. Concrete, real
opportunities to strengthen this project by depending on established
libraries rather than hand-rolled logic, in priority order:

1. **`license-expression`** (aboutcode-org) -- a mature, complete SPDX
   expression parser/normaliser. Could replace `licence/spdx.py`'s
   deliberately minimal ~30-identifier parser.
2. **ScanCode Toolkit** (aboutcode-org) -- an industry-standard licence-
   text-matching engine (tens of thousands of rules, confidence scoring)
   that could replace or augment `licence/discovery.py`'s hand-rolled
   text fingerprints, which this pass's bug (see above) shows are fragile
   against real-world text.
3. **`spdx-tools`** / **`cyclonedx-python`** -- official libraries for
   emitting spec-valid SPDX/CycloneDX documents, in place of the
   hand-rolled serialisation in `provenance/sbom.py`.
4. **tree-sitter** (via `ast-grep-py` or `py-tree-sitter` directly) -- real
   multi-language parsing to replace the generic bracket/keyword
   structural-similarity fallback for JS/Go/Rust/Java. Dolos (a modern
   MOSS/JPlag-style tool) uses exactly this architecture and is a good
   blueprint.
5. **SLSA build provenance / in-toto attestations** -- not yet
   implemented (the original banner draft overstated this; corrected).
   Genuinely buildable next: GitHub's native
   `actions/attest-build-provenance` action produces real SLSA provenance
   (itself an in-toto-format attestation) for anything built in the
   existing CI workflow -- a natural, small addition. Separately, the
   evidence ledger's hash-chained events are conceptually close to
   in-toto's "link" metadata; an export from the ledger to real in-toto
   link files is a natural fit for this project's own architecture.

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
- **Legal-issue engine**: 13 of 18 issues (contractual_permissions,
  protected_expression, interoperability_provisions, licence_obligations,
  derivative_work_question, linking, distribution, patent_risk,
  trademark_risk, database_rights, confidentiality, trade_secrets) have no
  dedicated heuristic yet -- always `UNKNOWN`.
- **Jurisdiction packs**: only England & Wales and US federal exist. EU,
  Germany, France, Japan (mentioned in the original design brief) are not
  built. Adding one is a real research task (see CONTRIBUTING.md), not a
  template fill-in.
- **Structural similarity**: real AST comparison only for Python. Other
  languages use a much weaker bracket/keyword-shape fallback
  (`structural_similarity` reports which method was used so callers can
  weight accordingly) -- see "Competitive landscape" for a concrete
  tree-sitter-based upgrade path.
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
2. Depend on `license-expression` and/or ScanCode Toolkit instead of the
   hand-rolled SPDX parser and licence-text fingerprints.
3. More legal-issue heuristics (particularly `distribution`,
   `licence_obligations`, `derivative_work_question`, since those close
   the loop with the licence-discovery/policy layer that already exists).
4. A third jurisdiction pack (EU, as the design brief's next most-requested).
5. Transitive dependency resolution for SBOM generation.
6. Automatic clean-room-level computation from project state.
7. SLSA build provenance via `actions/attest-build-provenance` in the
   release workflow.
8. tree-sitter-based structural similarity for JS/Go/Rust/Java.
