# Security Policy

## Supported versions

Clean Room Coding is pre-1.0 alpha software. Only the current `0.2.x`
line is supported with security fixes; there is no long-term-support
branch yet.

| Version | Supported |
| ------- | --------- |
| 0.2.x   | Yes       |
| < 0.2.0 | No        |

This table will be revised once a 1.0 release exists.

## Reporting a vulnerability

Please **do not** open a public GitHub issue for a suspected security
vulnerability.

Instead, report it privately using either of these channels:

1. **GitHub private security advisories** (preferred): open one at
   <https://github.com/khhvmc5g6f-eng/clean-room-coding/security/advisories/new>.
2. **Email**: `security@cleanroom.dev` (placeholder address — replace
   with a monitored inbox before relying on it).

Please include:

- The affected version/commit.
- A description of the vulnerability and its impact (e.g. path-guard
  bypass in `src/cleanroom/zones.py`, a way to make the licence/legal
  engines emit a false conclusion instead of `UNKNOWN`, secret exposure
  in the evidence ledger, arbitrary file read/write, etc.).
- Steps to reproduce, or a minimal proof of concept.

We aim to acknowledge reports within 5 business days. As a pre-1.0,
single-maintainer project there is no formal SLA for a fix yet; severity
and available maintainer time both affect turnaround.

## Sensitive data in the evidence ledger

Clean Room Coding's evidence ledger (`evidence/`, plus per-project ledgers
under a project's own working directory) is designed to capture a full,
append-only, hash-chained record of what was read, written, sanitised and
decided — by design, that can include source excerpts, licence text,
sanitisation findings, and legal/judicial-panel output tied to a real
project under analysis.

**This is sensitive by construction, not by accident.** Before you ever
commit an evidence ledger (or any generated artefact derived from a real
project you ran the tool against — `JURISDICTION_MATRIX.json`,
`CLEAN_ROOM_CERTIFICATE.json`, sanitisation reports, handoff manifests,
etc.) to a public repository:

- Confirm the ledger does not contain confidential source material,
  credentials, or anything the reference material's licence/contract
  forbids redistributing.
- When in doubt, keep it out of version control (see `.gitignore` for
  the patterns this repository already excludes) and get explicit
  confirmation from whoever owns the analysed project that it is safe
  to publish before committing it anywhere public.

This repository's own `evidence/` directory only ever contains the
project's *own* self-audit trail (its SBOM, its own dogfooded runs) — it
is not a place to store a third party's confidential material.

## Dependency updates

This project intends to run Dependabot (or an equivalent Renovate
configuration) against `pyproject.toml` and GitHub Actions workflow
pins, with:

- Security-relevant updates reviewed and merged as soon as practical
  after CI passes.
- Routine (non-security) dependency bumps reviewed in a monthly batch
  rather than ad hoc, to keep review overhead predictable for a
  single-maintainer project.

If you notice an outdated or vulnerable dependency and no automated PR
has been opened for it yet, please report it via the same channels as
above (or a normal issue, if it is not itself sensitive).
