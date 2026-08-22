# Clean Room Coding

![Clean Room Coding](docs/assets/banner.png)

A reproducible, auditable methodology and toolchain for independently
reimplementing software functionality while managing copyright, open-source
licensing, provenance, jurisdiction and evidential integrity.

**Clean Room Coding is not "change enough code and the licence disappears."**
It is: lawfully observe and specify permissible functionality, isolate
source analysis from implementation, independently engineer the
replacement, verify behaviour, audit provenance and similarity, resolve
applicable jurisdictions, conduct adversarial review, and preserve the
evidence demonstrating how the result was created.

> **This project is not a law firm and does not provide legal advice.**
> Every "legal" or "judicial" output in this repository is an AI-generated
> heuristic for engineering triage, clearly labelled as a simulation, and
> is not a substitute for qualified professional legal advice. See
> [docs/legal-disclaimer.md](docs/legal-disclaimer.md).

## Status

v0.1.0 — early, narrow-but-real core. See [ROADMAP.md](ROADMAP.md) for what
is fully implemented, what is a documented limitation, and what is not yet
built. Currently ships:

- A full three-zone (Reference / Handoff / Implementation) project model
  with a technically-enforced path guard and an append-only, hash-chained
  evidence ledger.
- Deterministic licence discovery (LICENSE/NOTICE files, SPDX headers,
  package manifests) plus policy packs for MIT, Apache-2.0, GPL-3.0-only
  and AGPL-3.0-only.
- A jurisdiction resolution engine with real packs for England & Wales and
  US federal law (facts + primary authorities + structured questions, not
  legal conclusions).
- A sanitisation scanner, requirement/behavioural specification graph,
  cryptographically hashed handoff manifest, similarity engine (lexical +
  Python AST structural + negative-control background comparison), SBOM
  generation (SPDX + CycloneDX), and a heuristic legal-issue engine with
  adversarial-counsel and judicial-review **prompt generation** (the
  reasoning itself is performed by whatever LLM harness you run it through
  — this library never calls one on its own).
- A 22-command CLI (`cleanroom ...`) with `--json` output and documented
  exit codes for CI/CD.
- An Agent Skill at [skills/clean-room-coding/SKILL.md](skills/clean-room-coding/SKILL.md)
  for use from Claude Code.

## Quick start

```bash
pip install -e ".[dev]"
cleanroom init --name "My Reimplementation Project"
cleanroom doctor
```

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

Apache-2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE). This project
practises the provenance standards it promotes — see its own
[SBOM](evidence/) and [REUSE](REUSE.toml) configuration.
