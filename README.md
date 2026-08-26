# Clean Room Coding

![Clean Room Coding](docs/assets/banner.png)

[![CI](https://github.com/khhvmc5g6f-eng/clean-room-coding/actions/workflows/ci.yml/badge.svg)](https://github.com/khhvmc5g6f-eng/clean-room-coding/actions/workflows/ci.yml)
[![Licence: BUSL-1.1](https://img.shields.io/badge/licence-BUSL--1.1-blue)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](pyproject.toml)
[![REUSE status](https://img.shields.io/badge/REUSE-compliant-brightgreen)](REUSE.toml)

A reproducible, auditable methodology and toolchain for independently
reimplementing software functionality while managing copyright, open-source
licensing, provenance, jurisdiction and evidential integrity.

**Clean Room Coding is not "change enough code and the licence disappears,"**
and it isn't a tool that reads licensed source and mechanically rewrites it
into a new language either — that would still be a derivative of what it
read, language-hop or not. It is: lawfully observe and specify permissible
functionality, isolate source analysis from implementation, independently
engineer the replacement (in whatever language you choose — never the
reference's own source, translated), verify behaviour, audit provenance
and similarity, resolve applicable jurisdictions, conduct adversarial
review, and preserve the evidence demonstrating how the result was created.

> **This project is not a law firm and does not provide legal advice.**
> Every "legal" or "judicial" output in this repository is an AI-generated
> heuristic for engineering triage, clearly labelled as a simulation, and
> is not a substitute for qualified professional legal advice. See
> [docs/legal-disclaimer.md](docs/legal-disclaimer.md).

## Status

v0.3.0 — early, narrow-but-real core, since reviewed and hardened by an
independent code review and security audit (see
[ROADMAP.md](ROADMAP.md#external-review-findings-2026-08-22) for exactly
what was found and fixed), then substantially extended: 13 licence
packs, fail-closed `--agent-id` PathGuard enforcement once an
implementation agent exists, real SBOM checksums and Cargo/composer
support, in-toto signing, judicial-panel provider diversity with a real
opt-in release gate, a Reference-side agent registration path, a
mechanically-enforced Clean-Room Gate between Sanitise and Handoff, a
real opt-in orchestration harness with distinct default models on each
side of the clean line, protocol/schema similarity coverage,
capability-regression coverage checking, structured facts-only
handoffs, and a guarded web-lookup contract for implementation agents
(see [CHANGELOG.md](CHANGELOG.md) for the full, dated history of every
pass, and "Version history" below for the release-by-release summary).
ROADMAP.md is the source of truth for what's fully implemented, what is
a documented limitation, and what is not yet built. Currently ships:

- A full three-zone (Reference / Handoff / Implementation) project model
  with an allow-list-capable `PathGuard` and an append-only, hash-chained
  evidence ledger that degrades gracefully rather than crashing on a
  corrupted/interrupted write.
- Deterministic licence discovery (LICENSE/NOTICE files, SPDX headers,
  package manifests, with symlink/non-regular-file safety) plus 13 policy
  packs: MIT, Apache-2.0, GPL-3.0-only, AGPL-3.0-only, BUSL-1.1 (this
  project's own licence), EUPL-1.2 (the EU's own strong-copyleft software
  licence), NASA-1.3 (a real, substantive copyleft-shaped US-agency
  licence -- not a public-domain notice), NIST-PD/NTIA-PD (genuine
  US public-domain notices), and four public sector data/information
  licences for reference material that includes government open data:
  OGL-UK-3.0 (UK), etalab-2.0 (France), and Germany's
  DL-DE-BY-2.0/DL-DE-ZERO-2.0 pair.
- A jurisdiction resolution engine with real, independently fact-checked
  packs for England & Wales, US federal, EU, France, Germany and Japan
  (facts + primary authorities + structured questions, not legal
  conclusions).
- A sanitisation scanner, requirement/behavioural specification graph,
  cryptographically hashed handoff manifest, and a similarity engine
  (lexical + Python AST / real tree-sitter structural via `ast-grep-py`
  for JS/TS/Go/Rust/Java/Ruby/C/C++, lexical-only for
  `.proto`/`.thrift`/`.avsc`/`.graphql`/`.gql`, + negative-control
  background comparison) now wired to a real `cleanroom similarity`
  command. `cleanroom diff-reference` re-checks a project's registered
  Zone R source against its original tree hash to catch silent drift
  after intake.
- SBOM generation (SPDX + CycloneDX), and a heuristic legal-issue engine
  with adversarial-counsel and judicial-review **prompt generation**
  (`cleanroom judge`) that any external LLM harness can answer by hand
  via `cleanroom judge-adjudicate` — or that this library's own real,
  opt-in orchestration harness can answer directly (see below).
- A **mechanically-enforced handover checkpoint** (`cleanroom gate`,
  Part XCIV): a recorded PASS/FAIL decision, backed by a real
  deterministic sufficiency/cleanliness signal, required before a
  specification version may cross into the Handoff zone — `cleanroom
  handoff` refuses outright without a matching PASS on record for that
  exact version. The human decision is always authoritative; overriding
  an `insufficient` signal to PASS requires an explicit acknowledgment
  and is recorded as such, never conflated with a genuinely clean pass.
- A **structured, facts-only handoff format** (`cleanroom handoff
  --format facts-json`, alongside the default free-form Markdown
  document): schema-validated field/enum name+number+type tuples for
  protocol/schema clean-room work, mechanically rejecting anything that
  reads like leaked prose or commentary from the reference.
- **Capability-regression coverage checking** (`cleanroom coverage`,
  Part XCVI): does a Zone I implementation still reference everything a
  project's pre-migration/legacy code actually used, banded by
  confidence rather than a binary pass/fail — a non-blocking advisory
  surfaced by `cleanroom gate` and `cleanroom report`.
- A **guarded web-lookup contract** for implementation-zone agents
  (`cleanroom check-url`/`cleanroom exclude-source`): blocks a URL that
  matches a project's own registered reference source (or its
  raw-content mirrors), allows unrelated ones, and records every check
  to the evidence ledger — an integration contract for an orchestrating
  harness to call, not a network sandbox this tool enforces on its own.
- A **remediation feedback loop** (`cleanroom remediate`): a RED legal
  finding or a suspicious/material similarity finding is automatically
  routed back to the implementation team as a blocked requirement, and
  `cleanroom release` refuses to proceed while one is open — closing the
  loop from "something looks wrong" to "it has to be fixed or explicitly
  signed off before this ships."
- Optional **AI-model suggestion** (`cleanroom ai-suggest`): asks
  explicitly whether to add AI/ML capability, then searches the real
  Hugging Face Hub, classifying candidates as embeddable/standalone vs.
  requiring a dedicated inference server, and checks each model's licence
  against your own policy.
- A **rich final report** — `cleanroom report --html --pdf` produces a
  colour-coded HTML page and a paginated PDF (alongside the always-written
  JSON/Markdown) covering what the project started with, what it did,
  functional coverage, remediation status, and the jurisdiction-by-
  jurisdiction decision.
- A 36-command CLI (`cleanroom ...`) with `--json` output, an actually-wired
  `--config` override, and documented exit codes for CI/CD.
- A real, opt-in **orchestration harness** (`cleanroom council` /
  `cleanroom implement`, `pip install cleanroom[orchestrate]`): the first
  actual implementation of "whatever LLM orchestration the caller uses"
  that `legal/panels.py`'s adversarial-review prompts have always
  deferred to. A Reference-side Council member (registered via
  `cleanroom recruit`) sends the same applicant/challenger/judicial-
  review prompts `cleanroom judge` writes to disk for a human to a real
  LLM backend and merges the result back exactly as `judge-adjudicate`
  would; a registered `cleanroom build` agent then hands off to
  `cleanroom implement`, which sends it Zone H's real sanitised
  documents (never Zone R) and writes whatever files the model returns
  into Zone I, with every path checked to stay inside it. **Each side of
  the clean line gets a real, deliberately different default model, not
  one generic choice reused everywhere:** the Council defaults to
  `claude-opus-5` (the adversarial, multi-jurisdiction legal reasoning it
  performs is the task most worth the strongest available reasoning
  budget), and the implementation team defaults to `claude-sonnet-5`
  (fast and cost-effective for writing code from an already-frozen,
  already-reviewed specification) — either is overridable per call with
  `--model-id`, and the evidence ledger always records whichever model
  actually did the work, never a blank field left over from an
  unspecified default. Real, cost-incurring LLM API calls -- never
  invoked implicitly. See ROADMAP.md for exactly what's verified (all
  the harness's own logic, via a `FakeBackend` test double, and the
  model-provenance recording via a mocked Anthropic client) versus what
  a live `ANTHROPIC_API_KEY` run of your own would be the first real
  end-to-end proof of.
- An Agent Skill at [skills/clean-room-coding/SKILL.md](skills/clean-room-coding/SKILL.md)
  for use from Claude Code.

## Version history

Pre-1.0 alpha — see [SECURITY.md](SECURITY.md) for which line currently
gets fixes. Each version below folds in every build-out pass since the
previous one; [CHANGELOG.md](CHANGELOG.md) has the full, dated write-up
of every individual pass (what changed, what was verified, what's still
unproven) rather than just the one-line summary here.

| Version | Date | Highlights |
| --- | --- | --- |
| **0.3.0** | 2026-08-23 | Mechanically-enforced **Clean-Room Gate** between Sanitise and Handoff; real opt-in **LLM orchestration harness** (`cleanroom council`/`cleanroom implement`) with distinct default models per side of the clean line; fail-closed `--agent-id` zone enforcement once an implementation agent exists; structured facts-only handoffs (`--format facts-json`); capability-regression **coverage** checking; guarded web-lookup contract for implementation agents; protocol/schema (`.proto`/`.thrift`/`.avsc`/`.graphql`) similarity coverage; a real GPL/AGPL licence-detection false positive fixed. |
| **0.2.0** | 2026-08-22 | The `v0.1.0` core, reviewed by an internal code review + security audit and then substantially extended in ~25 further passes on the same day: 13 licence policy packs, 6 jurisdiction packs, the similarity engine (Python AST + tree-sitter structural), SBOM generation (SPDX + CycloneDX) with real transitive-dependency checksums, the heuristic legal-issue engine (17/18 issues) with adversarial-counsel/judicial-review prompt generation and a provider-diversity release gate, the remediation feedback loop, optional AI-model suggestion, SLSA build provenance and in-toto signing, a measured similarity benchmark, and the Agent Skill. |
| **0.1.0** | 2026-08-22 | Initial **deep-but-narrow** first build: the three-zone (Reference/Handoff/Implementation) project model, `PathGuard` isolation, the append-only hash-chained evidence ledger, and the core CLI pipeline. Never cut as a standalone release — folded directly into 0.2.0's CHANGELOG entry the same day, so there is no separate `v0.1.0` tag or changelog section to link to. |

## How this compares

A competitive-landscape review (2026-08-22) found no existing tool that
combines process-separation (reference/handoff/implementation zones, an
evidence ledger, jurisdiction resolution) with licence/similarity/SBOM
tooling the way this project does — see
[ROADMAP.md](ROADMAP.md#competitive-landscape-researched-2026-08-22) for
the full write-up. Since then, `license-expression`, `ast-grep-py`
(tree-sitter) and `spdx-tools`/`cyclonedx-python-lib` have all been
integrated in place of earlier hand-rolled logic; ScanCode Toolkit
remains a possible future optional extra for deeper licence-text
detection.

## Quick start

Install the current development release from GitHub, then initialise and
check a project:

```bash
git clone https://github.com/khhvmc5g6f-eng/clean-room-coding.git
cd clean-room-coding
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cleanroom init --name "My Reimplementation Project" --target-language python
cleanroom doctor
```

Install the portable Agent Skill separately with:

```bash
gh skill install khhvmc5g6f-eng/clean-room-coding clean-room-coding
```

The Python package is not yet published to PyPI. The editable Git checkout
above is the supported installation route for this pre-1.0 release.

See [docs/quickstart.md](docs/quickstart.md) for a full worked walkthrough
and [docs/concepts.md](docs/concepts.md) for the three-zone model,
contamination levels and clean-room maturity levels (CR0-CR5).

## Repository layout

```
clean-room-coding/
├── src/cleanroom/       # the Python engine + CLI
├── schemas/             # JSON Schemas: the contracts everything else is validated against
├── policies/licences/   # licence policy packs (facts + structured questions, not verdicts)
├── jurisdictions/       # jurisdiction packs (facts + primary authorities + structured questions)
├── prompts/             # role prompts for analyst/sanitisation/legal/judicial panels
├── skills/clean-room-coding/  # the Agent Skill (progressive disclosure)
├── docs/                # concepts, architecture, ADRs, legal disclaimer
├── examples/            # a full worked walkthrough
├── tests/               # unit + integration tests, including the framework's own self-tests
├── integrations/github-action/  # reusable GitHub Action
└── .github/              # CI, issue templates, CODEOWNERS
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) and [GOVERNANCE.md](GOVERNANCE.md).
Security issues: see [SECURITY.md](SECURITY.md).

## Licence

[Business Source License 1.1](LICENSE) (BUSL-1.1) — source-available, not
OSI-approved. Free to use, modify, self-host and run commercially
in-house; you may not resell it, white-label it, or offer it to others as
a hosted/SaaS product in competition with the Licensor. Converts to
GPL-3.0-or-later on 2030-08-22. See [LICENSE](LICENSE) for the full terms
(including the Additional Use Grant) and [NOTICE](NOTICE) for a summary.
This project practises the provenance standards it promotes — see its own
[SBOM](evidence/) and [REUSE](REUSE.toml) configuration.
