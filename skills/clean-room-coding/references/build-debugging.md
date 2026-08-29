# Build-side debugging suite (Part XCVII)

`cleanroom debug` (`src/cleanroom/debugging.py`) gives Team B a
structured way to triage a failing behavioural test (`cleanroom test`)
before looping Team A in, without ever needing -- or being tempted -- to
look at Zone R to find out what's actually supposed to happen.

## Why this needs its own step

Team B holds Zone H (the sanitised spec) and Zone I (its own new code)
only (`references/three-zone-model.md`). A failing test can mean one of
two very different things, and the fix for each is different:

- **The spec is clear and Zone I just doesn't meet it yet.** An ordinary
  bug, fixable entirely inside Zone I -- Team B doesn't need anyone
  else.
- **The spec itself doesn't say clearly enough what correct behaviour
  is.** No amount of reading Zone I code fixes that, and "just check the
  reference to find out" is exactly the contamination this whole project
  exists to prevent (AGENTS.md rule a).

Every failing test used to get the same treatment: bounce it to Team A
as a discrepancy report (phase 12 of `SKILL.md`'s validation loop). That
still happens for a genuine ambiguity -- `cleanroom debug` just decides,
deterministically, which failures actually need that round trip and
which ones Team B can and should fix itself right now.

## What it does

For every `behavioral_tests.json` entry with `result: "fail"`:

1. **Missing requirement -> `insufficient_evidence`.** The test
   references a `requirement_ids` entry that doesn't exist in
   `requirements.json`, or has none at all. There is nothing to compare
   the failure against; this is a data problem in the spec itself; fix
   the linkage, not the code.
2. **Ambiguity marker in the linked requirement/test text ->
   `spec_gap`.** A deterministic, intentionally over-flagging word list
   (`AMBIGUITY_MARKERS` -- "TBD", "implementation-defined", "may vary",
   "at least one of", etc., same over-flag-on-purpose bias as the
   prompt-injection scanner in `sanitisation/scanner.py`) matched
   somewhere in the requirement statement(s) or the test's own
   given/when/then.
3. **Otherwise -> `implementation_bug`.** The requirement text is
   present and nothing flagged as ambiguous -- default assumption is
   Zone I's own code doesn't yet meet a spec that IS clear.

This is a small set of lexical checks, not a model call and not a claim
of understanding. It will sometimes flag a genuinely precise requirement
that happens to contain "typically," or miss a genuinely vague one with
no marker word -- that is exactly why a `spec_gap` finding still goes
through the ordinary human/Team-A remediation loop below rather than
being treated as a final verdict, and why an `implementation_bug`
finding gets a worksheet to work through rather than a "diagnosed for
you" claim (AGENTS.md rule c: never fabricate a conclusion the
deterministic evidence doesn't support).

## spec_gap: routed through the existing remediation ledger, not a new one

A `spec_gap` finding becomes a `debug_finding`-sourced task in
`REMEDIATION_TASKS.json` and a `blocked` `kind: "remediation"` node in
`requirements.json` -- the exact same mechanism `cleanroom remediate`
already uses for RED legal findings and suspicious/material similarity
findings (`legal/remediation.py`). That means it automatically shows up
in:

- `cleanroom build`'s pre-flight open-concerns panel,
- `cleanroom report`'s `remediation_summary`,
- the requirement graph's `blockers()` (surfaced in `cleanroom report`'s
  `outstanding_issues`).

Severity is always `review_required`, never `blocking` -- this is Team
B's own heuristic guess about its own test failure, not a confirmed
legal/similarity violation, so it must not unilaterally block `cleanroom
release` the way a RED legal finding does. Resolving it is the same as
resolving any other remediation task: fix the underlying cause (reword
the ambiguous requirement via `cleanroom specify add-requirement`,
route it through Sanitise and a fresh Clean-Room Gate decision like any
specification amendment -- phase 12/9 of `SKILL.md`) and re-run
`cleanroom debug`; the task clears itself (`resolved_by_rescan`), or
apply an explicit `cleanroom remediate --override` if the ambiguity is a
deliberately accepted risk rather than something to reword.

## implementation_bug: a worksheet, not an automated fix

Each `implementation_bug` finding gets a structured, Zone-I-scoped
checklist (`ctx.emit`'s `worksheets`, keyed by test id) -- nothing in it
reads or edits Zone I source itself:

- **`zone_reminder`** -- if answering any prompt below would require
  looking at the reference material, that's a sign this is actually a
  `spec_gap`, not an `implementation_bug`; stop and re-triage rather than
  peeking at Zone R.
- **`backward_trace`** -- start at the observed wrong output, walk
  backward one call/data-flow hop at a time until you find the exact hop
  where correct input became incorrect output; don't stop at the first
  place the bug becomes visible (the symptom), and falsify your
  root-cause hypothesis before fixing anything.
- **`defense_in_depth`** -- is the value validated only where it's first
  produced, or at every layer that depends on the same assumption? A
  check that reports wrongness sooner is not a substitute for fixing the
  layer that was actually wrong.
- **`temporal_concurrency`** -- present only when the failure's own text
  matched a concurrency marker (`CONCURRENCY_MARKERS` -- "async",
  "retry", "idempotent", "race", etc.): build a chronological model of
  the events involved, check whether state updates are really atomic,
  check idempotency for anything retryable, check safe resumption for
  anything interruptible.

## Idempotent, like `cleanroom remediate`

Re-running `cleanroom debug` re-derives `DEBUG_FINDINGS.json` and
re-syncs `REMEDIATION_TASKS.json`/the requirement graph from whatever is
currently in `behavioral_tests.json`/`requirements.json` -- a
previously-open `debug_finding` task whose test no longer fails (or
whose linked requirement was reworded to remove the ambiguity) is
automatically marked `resolved_by_rescan`, exactly like a fixed legal or
similarity finding.
