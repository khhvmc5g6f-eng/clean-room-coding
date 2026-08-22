# Concepts

## The central principle

Clean-room reimplementation is not "change enough code and the licence
disappears." It is: lawfully observe and specify permissible functionality,
isolate source analysis from implementation, independently engineer the
replacement, verify behaviour, audit provenance and similarity, resolve
applicable jurisdictions, conduct adversarial review, and preserve the
evidence demonstrating how the result was created.

## The three zones

See [skills/clean-room-coding/references/three-zone-model.md](../skills/clean-room-coding/references/three-zone-model.md)
for the full detail. Short version: **Reference** (original material,
analyst-only access), **Handoff** (sanitised, C0-only, immutable and
hashed), **Implementation** (fresh agents/contributors, no path back to
Reference).

## Contamination levels

C0 (public/factual) through C5 (legally restricted/unresolved). See
[schemas/contamination-level.schema.json](../schemas/contamination-level.schema.json).
Only C0 material may cross into the Handoff zone.

## Clean-room maturity levels (CR0-CR5)

See [clean-room-levels.md](clean-room-levels.md).

## Observable requirement vs. source implementation detail

The load-bearing distinction for what's allowed to cross from Reference
into Handoff. See
[skills/clean-room-coding/references/observation-vs-implementation.md](../skills/clean-room-coding/references/observation-vs-implementation.md).

## Declared / detected / concluded licence

Licence discovery never collapses uncertainty into a single confident
answer. See
[skills/clean-room-coding/references/licence-discovery.md](../skills/clean-room-coding/references/licence-discovery.md).

## Jurisdiction tiers

primary / secondary / potential / unknown, per legal issue, never defaulted
to a single assumed country. See
[skills/clean-room-coding/references/jurisdiction.md](../skills/clean-room-coding/references/jurisdiction.md).

## Decision states

`GREEN` / `GREEN_WITH_CONDITIONS` / `AMBER` / `RED` (jurisdiction/global
level) and additionally `UNKNOWN` (per-finding level, folded into `AMBER`
on aggregation). Worst-finding-wins; a `RED` in a required market blocks
release regardless of other markets (no averaging). See
[docs/legal-disclaimer.md](legal-disclaimer.md).

## Evidence ledger

An append-only, hash-chained JSON-Lines log
(`src/cleanroom/evidence.py`) -- every event's hash commits to the
previous event's hash, so retroactive tampering is detectable by
`cleanroom verify` / `EvidenceLedger.verify_chain()`.
