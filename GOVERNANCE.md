# Governance

## Maintainers model

Clean Room Coding is currently in **v0.1, single-maintainer (BDFL)**
mode: one maintainer (the repository owner,
[@khhvmc5g6f-eng](https://github.com/khhvmc5g6f-eng)) makes final calls
on scope, design direction, and merges. There is no formal maintainers
team yet.

As the project matures toward a 1.0 release and gains regular
contributors, this is expected to move to a small **maintainers group**
with shared merge rights, at which point this document will be updated
with the group's membership and its own decision process (e.g. majority
vote for contested changes). Until then, treat every reference below to
"the maintainer" as the current BDFL, and every reference to "an
additional reviewer" as any other trusted contributor the maintainer
designates for that review.

## How decisions are made

- **Routine changes** (bug fixes, new tests, documentation, CLI
  ergonomics, non-legal-content code under `src/cleanroom/` outside the
  paths below) proceed by **lazy consensus**: open a PR, allow a
  reasonable review window, and merge if no maintainer objects.
- **Anything under `policies/`, `jurisdictions/`, or `schemas/`**
  requires **explicit maintainer sign-off** before merge — these are
  this project's legal-content and contract surface (licence policy
  packs, jurisdiction packs, and the JSON Schemas everything else is
  validated against). Lazy consensus does not apply here even for small
  edits.
- **New features that change the CLI's command surface, exit-code
  semantics, or the three-zone model** (`src/cleanroom/zones.py`,
  `src/cleanroom/cli.py` command definitions, `src/cleanroom/exit_codes.py`)
  should be discussed in an issue before a PR is opened, since CI/CD
  consumers depend on these being stable and documented.

## Heightened review: policy packs and jurisdiction packs

Any change to a **licence policy pack** (`policies/licences/*.yml`) or a
**jurisdiction pack** (`jurisdictions/*/framework.yml`) requires **at
least one reviewer who is not the author** — including changes proposed
or merged by the sole maintainer, who must recuse themselves as the
"second reviewer" on their own edits and find another trusted reviewer,
even an informal one, before merging.

This applies even though Clean Room Coding explicitly does not give
legal advice (see [docs/legal-disclaimer.md](docs/legal-disclaimer.md)):
these packs are read directly by users making real licensing and
jurisdiction decisions about their own projects, and an error in a pack
(a wrong obligation, a stale statute citation, a miscategorised
copyleft strength) can mislead a user even while the tool correctly
labels its output as a heuristic rather than a verdict. Precision here
protects users from a bad "fact" input to their own judgement, not from
this project overreaching into giving advice.

Until the maintainers group exists, "an additional reviewer" may be
satisfied by any contributor with demonstrated familiarity with the
specific licence family or jurisdiction in question — it does not need
to be a lawyer, but it must be a second set of eyes distinct from
whoever wrote the change.

## Code of Conduct enforcement

Handled per [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md), currently by the
sole maintainer until a maintainers group exists.

## Changing this document

Changes to `GOVERNANCE.md` itself follow the same rule as `policies/` and
`jurisdictions/`: they require sign-off from someone other than the
author of the change, since this document defines who gets to make that
call for everything else.
