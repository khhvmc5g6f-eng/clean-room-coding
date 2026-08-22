# Clean-room maturity levels

A project self-declares a target level in `.cleanroom.yml`'s
`clean_room_level`; the level names what controls are *supposed* to be in
place, not a score the tool computes for you in v0.1 (automatic level
verification/gating is on the roadmap -- see ROADMAP.md).

- **CR0** -- No clean-room separation. (Not a real target; exists so the
  scale has a zero point.)
- **CR1** -- Documented independent implementation. A basic paper trail
  exists (who built what, when) but no technical separation.
- **CR2** -- Separate implementation agents and a sanitised specification.
  This is the default for `cleanroom init`. Zone R/H/I exist; handoff is
  built from sanitised, C0-classified material; implementation agents are
  registered separately from analysts.
- **CR3** -- Technically enforced isolation plus provenance. `PathGuard`
  denial is verified (`cleanroom audit`'s isolation test passes), and
  SBOM/provenance generation is wired in (`cleanroom provenance`).
- **CR4** -- Independent similarity review, evidence ledger, and
  jurisdiction review are all active: `cleanroom compare`/the similarity
  engine has been run against the implementation, the evidence ledger's
  hash chain is intact (`cleanroom verify`), and `cleanroom jurisdiction`
  + `cleanroom legal` have been run for every required market.
- **CR5** -- Maximum assurance: everything in CR4, plus adversarial legal
  review (`cleanroom judge`'s prompts actually answered and reviewed by
  qualified counsel), a cryptographically signed handoff manifest
  (`cleanroom handoff --signer <gpg-key-id>`), reproducible build
  provenance, and an evidence bundle a genuinely external reviewer
  (adversarial or a lawyer) could pick up and reconstruct the process
  from without trusting any single participant's say-so.

**Automatic computation:** `cleanroom status` now reports a
`computed_maturity` field (`src/cleanroom/maturity.py`) alongside the
declared `clean_room_level`, independently derived from real, checkable
project state (ledger events, zone directories, a handoff manifest, a
Zone-R-blind implementation agent, the PathGuard self-test, generated
SBOM, similarity findings, jurisdiction pack coverage, legal findings,
manifest signature) -- never silently reconciled with the declaration in
either direction, so a mismatch (`matches_declared: false`) stays visible.
CR5's "adversarial legal review... reviewed by qualified counsel"
criterion is always reported unmet: whether a human lawyer actually
endorsed `cleanroom judge`'s prompts isn't a fact any of this tool's files
can establish, so the computed level can never automatically reach CR5 --
that remains a human judgment call, not an automated gate.
