# Licence discovery

`cleanroom licence <path>` (`src/cleanroom/licence/discovery.py`) scans
three kinds of evidence, and keeps them distinct rather than collapsing
them into one answer:

- **declared** -- an explicit `SPDX-License-Identifier` header or a
  package manifest field (`package.json` `license`, `pyproject.toml`
  `[project.license]`, `Cargo.toml` `license`, `composer.json` `license`).
- **detected** -- text-fingerprint matches against LICENSE/COPYING/NOTICE/
  COPYRIGHT files (a curated set of distinctive phrases per licence, e.g.
  "GNU AFFERO GENERAL PUBLIC LICENSE" + "Version 3" for AGPL-3.0-only).
- **concluded** -- the engine's best-effort single answer, which is `null`
  whenever the evidence is absent, ambiguous, or conflicting (e.g. a
  LICENSE file whose text matches two different fingerprints) -- this is
  reported as `conflicting_evidence: true` and `confidence: "low"`, never
  silently resolved to one licence.

A `null` concluded licence, or `confidence: "unknown"`, is a normal and
common result -- most real repositories have messy or partial licence
metadata. Report it as-is; do not "fill in" a guess.

## Policy evaluation

`.cleanroom.yml`'s `dependency_policy.allowed_licences` /
`denied_licences` / `unknown_licence_action` decide whether a concluded
licence is `allowed`, `denied`, or `needs_review` (see
`src/cleanroom/licence/policy.py::evaluate` / `is_blocking`). Denied always
blocks; `needs_review`/`unknown` only blocks if `unknown_licence_action:
block` (the default).

## Licence policy packs

`/policies/licences/*.yml` (MIT, Apache-2.0, GPL-3.0-only, AGPL-3.0-only, BUSL-1.1,
and OGL-UK-3.0 -- the UK Open Government Licence, a public sector data/
information licence rather than a software one -- in v0.1) are FACTS + structured
review questions, never verdicts -- `key_obligations`, `distribution_triggers`,
`network_use_triggers_obligations`, `clean_room_relevance`,
`structured_issue_prompts`, `uncertainty_notes`.
Read the specific pack for the licence in play before advising a user on
what a licence "requires" -- don't rely on general knowledge, since the
pack captures this project's considered, versioned position (and any
correction to it goes through heightened review per GOVERNANCE.md).
