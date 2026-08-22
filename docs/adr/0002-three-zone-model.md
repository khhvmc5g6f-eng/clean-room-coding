# 0002. Three zones (Reference / Handoff / Implementation), not two

## Status

Accepted

## Decision

Model a clean-room project as three zones -- Reference (R), Handoff (H),
Implementation (I) -- rather than the traditional two-room clean-room
model (a "chinese wall" between one analysis team and one implementation
team).

## Rationale

The classic two-room model conflates two different things: (1) the
sanitised specification that's *allowed* to cross the wall, and (2) the
implementation team's own working state. Without a distinct middle zone,
projects tend to either (a) let implementation agents read the analysis
team's raw notes directly ("just don't look at the *code*", which this
project's design brief explicitly rejects as insufficient), or (b) have no
single, hashable, versioned artefact that represents "exactly what crossed
the wall" for later evidential purposes.

A distinct Handoff zone gives:

- A single point of enforcement: `handoff.manifest.build_manifest` refuses
  to include anything not classified contamination-level C0
  (`ContaminationFailure`), so "what's authorised for implementation" is a
  mechanical check, not a matter of people remembering to be careful.
- A hashable, immutable artefact (`HANDOFF_MANIFEST.json`) that proves
  exactly which specification version the implementation side received --
  this is the artefact an adversarial reviewer or a lawyer can actually
  inspect later.
- A place for the sanitisation differential (raw analysis vs. sanitised
  specification) to live without needing implementation agents to ever see
  the raw side.

## Consequences

Every project using this tool has three directories
(`zone-r`/`zone-h`/`zone-i` by default, configurable in `.cleanroom.yml`)
instead of two. `PathGuard` (`src/cleanroom/zones.py`) is scoped per-agent
against all three, not a single boolean "has access to the reference or
not" -- an analyst agent is `{R}`-scoped, an implementation agent is
`{H, I}`-scoped, and neither should ever be granted all three.
