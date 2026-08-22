# The three-zone model

- **Zone R (Reference)** -- original source, docs, screenshots, binaries,
  tests, manuals, reference assets. Only analyst agents may enter.
- **Zone H (Handoff)** -- exclusively sanitised artefacts authorised for
  implementation: behavioural specs, public standards, API contracts,
  interoperability requirements, acceptance criteria. Nothing here should
  ever be classified above contamination level `C0` (see
  `src/cleanroom/contamination.py`) -- `cleanroom handoff --all-c0` will
  refuse to build a manifest otherwise (`ContaminationFailure`).
- **Zone I (Implementation)** -- new source, architecture, tests, docs,
  design assets, build environment. Implementation agents must have **no
  read path** to Zone R.

## Technical isolation

`src/cleanroom/zones.py`'s `PathGuard` is the actual enforcement
mechanism: every agent instance gets an `AgentZoneScope` (permitted zones +
explicit prohibited paths), and `PathGuard.check()`/`is_allowed()` denies
any resolved path outside that scope -- including through symlinks or `..`
traversal, since it resolves the path first.

**Honesty about scope:** this only protects reads performed through
`cleanroom`'s own APIs (the CLI, this skill's scripts, or any orchestration
built on `src/cleanroom` as a library). It cannot stop an external editor
or agent harness that ignores it entirely -- that requires OS-level
containers, separate worktrees, separate credentials, or separate
processes, which a real deployment should layer on top. If you are
orchestrating implementation subagents yourself (e.g. via the Task/Agent
tool), the practical equivalent is: **never point an implementation
subagent's file-read tool at a Zone R path, and never paste Zone R content
into an implementation subagent's context.**

Run `cleanroom audit` (which calls `run_isolation_test`) to get a concrete
pass/fail: it instantiates an implementation-scoped guard and asserts a
Zone R read is `DENIED`.

## Contamination levels (C0-C5)

C0 public/factual, C1 public docs (minimal expressive risk), C2 reference
docs (potentially expressive), C3 original source, C4 highly sensitive/
confidential, C5 legally restricted or unresolved-permission material.
Only C0 -- including sanitised derivatives explicitly re-classified down to
C0 -- may cross into Zone H. See `schemas/contamination-level.schema.json`.
