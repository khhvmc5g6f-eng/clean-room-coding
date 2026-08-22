# Roadmap

Clean Room Coding v0.1.0 is a **deep-but-narrow** first build: everything
listed under "Built and tested" is real, working code with passing tests
-- nothing is scaffolded-but-fake. Everything under "Documented
limitation" is a genuine gap, called out here (and usually inline in the
relevant module's docstring) rather than silently claimed as complete.

## Built and tested (v0.1.0)

- Three-zone project model (`cleanroom init`), technically-enforced
  `PathGuard` isolation, and an isolation self-test (`cleanroom audit`).
- Append-only, hash-chained evidence ledger (`cleanroom` writes to it from
  nearly every command; `cleanroom verify` detects tampering).
- Deterministic licence discovery (LICENSE/NOTICE/COPYING files, SPDX
  headers, `package.json`/`pyproject.toml`/`Cargo.toml`/`composer.json`
  manifests) and policy evaluation, with 4 licence packs: MIT, Apache-2.0,
  GPL-3.0-only, AGPL-3.0-only.
- A minimal SPDX expression parser (`AND`/`OR`/`WITH`, `LicenseRef-*`,
  a curated known-identifier list -- not the full SPDX licence list).
- Jurisdiction resolution engine with 2 real packs: England & Wales and
  US federal (real statutes and leading case law, structured review
  questions, never defaulting to a single assumed jurisdiction).
- Sanitisation scanner (secrets, code-like text, prompt-injection
  phrasing, distinctive-identifier overlap, verbatim-text overlap) and the
  raw/sanitised differential record.
- Requirement graph + GIVEN/WHEN/THEN behavioural specs, with mechanical
  observable-requirement/source-implementation-detail partitioning and
  traceability reporting that never inflates completion percentages.
- Cryptographically hashed `HANDOFF_MANIFEST.json` (+ optional GPG
  detached signature) and integrity verification.
- Similarity engine: lexical (token-shingle Jaccard), structural (real
  Python AST comparison; generic bracket/keyword fallback for other
  languages), and negative-control background scoring -- with automatic
  classification restricted to `coincidental`/`conventional`/`suspicious`
  only (`required`/`constrained`/`material` require human/panel review by
  design).
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
- Release policy engine with a mandatory human sign-off gate by default
  (exit code 9), and a `RED` in any required jurisdiction blocking release
  outright regardless of other jurisdictions.
- 22-command CLI with `--json`/`--quiet`/`--verbose`/`--project`/`--config`
  and documented exit codes; a Click-based `CliRunner` integration test
  drives the full pipeline end-to-end.
- The Agent Skill (`skills/clean-room-coding/SKILL.md` +
  progressive-disclosure `references/`).

## Documented limitations (not silently overclaimed)

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
  weight accordingly).
- **SBOM/dependency discovery**: direct declared dependencies only, from
  `requirements.txt`/`pyproject.toml`/`package.json`. No transitive
  resolution, no registry lookups for licence/hash of resolved versions.
- **`cleanroom compare`** (functional equivalence engine) compares two
  already-captured output files under configurable tolerance; it does not
  itself run the reference and implementation programs side-by-side.
- **No dedicated `SIMILARITY_FAILURE` (exit 7) CLI gate yet** -- the
  similarity engine's Python API is complete and tested, but no CLI
  subcommand runs it end-to-end against two codebases and exits 7 on a
  material finding. Next natural addition.
- **No automatic clean-room-level (CR0-CR5) computation** -- see
  docs/clean-room-levels.md. The level in `.cleanroom.yml` is a
  declaration the project's owners back up manually today.
- **Provider diversity / multi-model panels** (`panel_diversity_required`,
  `panel_size` in `.cleanroom.yml`) are recorded in config but not yet
  wired to an actual multi-provider LLM adapter layer -- Claude via
  whatever harness runs `cleanroom judge`'s prompts is the only path today.
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

## Likely next additions

1. A `cleanroom similarity <ref-dir> <impl-dir>` command wiring the
   existing similarity engine to exit code 7.
2. More legal-issue heuristics (particularly `distribution`,
   `licence_obligations`, `derivative_work_question`, since those close
   the loop with the licence-discovery/policy layer that already exists).
3. A third jurisdiction pack (EU, as the design brief's next most-requested).
4. Transitive dependency resolution for SBOM generation.
5. Automatic clean-room-level computation from project state.
