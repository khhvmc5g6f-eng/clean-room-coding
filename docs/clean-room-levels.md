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

**v0.1 honesty note:** the CLI does not yet compute "you are at CR3, not
CR4" automatically from project state -- that's a natural next step (see
ROADMAP.md) but for now the level in `.cleanroom.yml` is a declaration the
project's owners are responsible for backing up with the actual gates
described above, most of which `cleanroom audit`/`cleanroom report` do let
you verify individually.
