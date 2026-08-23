# The Clean-Room Gate

`cleanroom gate` (Part XCIV) is a recorded, evidence-backed PASS/FAIL
decision on whether a specification version is sufficient for independent
implementation and free of restricted material. It sits between Sanitise
and Handoff. See `three-zone-model.md` for what Team A / Team B mean.

## Why this exists as its own command, not just a review step

Before this command existed, nothing stopped `cleanroom handoff` from
running the moment sanitisation passed, even if the requirement graph was
still empty or barely started -- "sanitised" only means "no blocking
secret/verbatim-text finding in this one document," not "this is enough
information for someone else to build the thing." The gate makes that
second, distinct judgement a real, mechanically-enforced step:
`cleanroom handoff --specification-version vN` now refuses outright
(`PolicyFailure`, exit 3) unless a `pass` decision has already been
recorded for that exact `vN`.

## What the automated signal is, and isn't

`cleanroom gate` computes a real, deterministic `automated_signal` before
asking for a decision:

- **`sufficient`** -- at least one `observable_requirement` node is
  actually handoff-eligible (`RequirementGraph.handoff_eligible_nodes()`,
  the same check `cleanroom specify report` surfaces) **and** no
  sanitisation report on file for a candidate Zone H document is blocked.
- **`insufficient`** -- either condition fails.

This is deliberately a low, mechanical bar, not a claim that the
specification is *good*. A graph with one thin requirement node reads
`sufficient` just as readily as a thorough one; judging actual coverage
quality is still the reviewer's job, informed by `cleanroom specify
report`'s fuller traceability numbers (verified/implemented/blocked
percentages) and by reading the candidate Zone H documents directly. The
signal exists to catch the "nothing has been specified yet" and
"a sanitisation finding was never resolved" cases mechanically, not to
replace review.

## The human decision is authoritative

`--decision pass|fail` is a human call (`--reviewer` and `--notes` are
both required), not a rubber stamp of `automated_signal`:

- Recording `--decision fail` is legitimate even when the signal reads
  `sufficient` -- e.g. a reviewer who read the actual documents and found
  a real gap the mechanical check can't see. This blocks handoff and
  returns the finding to Team A, and it is itself recorded (`decision:
  "fail"` in `GATE_DECISIONS.json`) rather than silently discarded.
- Recording `--decision pass` while `automated_signal` reads
  `insufficient` is also legitimate -- a reviewer may correctly judge that
  a genuinely small feature needs only the one requirement node that
  exists. But the tool never lets this through silently: it requires
  explicit acknowledgment (`--acknowledge-automated-signal`, or an
  interactive confirmation outside `--json` mode) and always records
  `overrode_automated_signal: true` on the decision, so a real override
  is never indistinguishable from a genuinely clean pass when someone
  reads `GATE_DECISIONS.json` later.

## Where the decision lives

Every decision -- pass and fail alike -- is appended to
`GATE_DECISIONS.json` at the project root (never overwritten; a
specification version that failed and was later fixed keeps its FAIL on
record, with the later PASS appended after it) and to the evidence
ledger (`cleanroom gate` as the action, the reviewer as a `human` actor).
`cleanroom handoff` reads the **latest** decision for the specification
version it's building.

## The validation loop reuses this same gate

A specification amendment coming out of the validation loop (Team A's
behavioural-discrepancy findings on Team B's build, fed back via
`cleanroom specify add-requirement`/`add-behavioral`) is handed to Team B
as a **new** specification version, sanitised and gated exactly like the
first one -- never patched into Zone H directly. See SKILL.md's
"Mandatory stage: Team A / Team B implementation handover" for how this
fits into the full phase sequence.
