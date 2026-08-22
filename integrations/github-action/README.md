# Clean Room Coding GitHub Action

A composite GitHub Action that runs `cleanroom doctor`, `cleanroom
licence`, `cleanroom audit`, and `cleanroom report` (all with `--json`)
against a project, so a clean-room project's CI can surface Clean Room
Coding's checks as a PR status check.

This action does **not** check out your repository — do that yourself
first, as usual.

## Usage

```yaml
name: Clean room checks

on:
  pull_request:
  push:
    branches: [main]

jobs:
  cleanroom:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: khhvmc5g6f-eng/clean-room-coding/integrations/github-action@main
        with:
          project-path: .
          policy: standard
```

### Inputs

| Input             | Default   | Description |
| ------------------ | --------- | ----------- |
| `project-path`      | `.`       | Path to the Clean Room Coding project (the directory containing `.cleanroom.yml`), relative to your checked-out repository. |
| `policy`            | `standard`| Placeholder for a future strict/standard/permissive release-policy tier. Not yet enforced — v0.1 only has one release-policy shape (see `.cleanroom.yml`'s `release_policy` section). Safe to pass now so workflows don't need updating once tiers exist. |
| `cleanroom-ref`     | `main`    | Git ref of `khhvmc5g6f-eng/clean-room-coding` to install `cleanroom` from. `cleanroom` is not yet published to PyPI, so this action installs it via `pip install git+https://github.com/khhvmc5g6f-eng/clean-room-coding.git@<ref>`. Pin this to a tag or commit for a reproducible CI run. |
| `python-version`    | `3.11`    | Python version used to run `cleanroom`. |

## What a PASS, a MANUAL_REVIEW_REQUIRED, and a real failure mean

Clean Room Coding never auto-approves a release — see
[`src/cleanroom/exit_codes.py`](../../src/cleanroom/exit_codes.py) and
[`cleanroom release`](../../src/cleanroom/cli.py) in the main
repository. In a PR check context, this action's outcome should be read
as:

- **The action step succeeds (green check)** — every command it ran
  (`doctor`, `licence`, `audit`, `report`) exited `0` (PASS) or `9`
  (`MANUAL_REVIEW_REQUIRED`). A `9` is logged as a GitHub Actions
  warning annotation, not an error, and does **not** fail the step. This
  is expected steady-state for this tool: a human must still sign off
  on release regardless of how clean the automated checks are — see
  `cleanroom release`'s own behaviour, which exits
  `MANUAL_REVIEW_REQUIRED` even after every automated gate passes,
  whenever `approval_gates.human_signoff_required_for_release` is true
  (the default).
- **The action step fails (red X) with an `::error::` annotation naming
  a subcommand and a non-zero, non-9 exit code** — a real problem:
  a configuration error, a denied/unresolved licence
  (`LICENCE_FAILURE`), a contamination/isolation-test failure
  (`CONTAMINATION_FAILURE`), a broken evidence ledger, or similar. Treat
  this the same as any other failing CI check: it should block merge
  until resolved, not be waved through.
- **`MANUAL_REVIEW_REQUIRED` should not be treated as "green light to
  merge and release."** It means the automated gates this action can
  check did not find a blocking problem, but this project's own release
  policy still requires a human to review the certificate
  (`CLEAN_ROOM_CERTIFICATE.json`) and jurisdiction findings before the
  reimplementation is actually released. Use the job logs (or a
  follow-up `cleanroom report`/`cleanroom release` run) for that
  sign-off, not this Action's exit status alone.

Every command is also run with `--json`; see the step logs (inside the
`::group::cleanroom <subcommand> --json` sections) for the full
machine-readable output if you want to parse specific fields in a later
job step.
