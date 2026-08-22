# Contributing to Clean Room Coding

Thank you for considering a contribution. This project is early (v0.1,
alpha) and its two most sensitive surfaces — licence policy packs and
jurisdiction packs — carry real legal-content risk even though the tool
itself is explicitly **not legal advice** (see
[docs/legal-disclaimer.md](docs/legal-disclaimer.md)). Please read the
"Sensitive content" section below before touching anything under
`policies/`, `jurisdictions/`, or `schemas/`.

## Development environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

This installs `cleanroom` in editable mode plus the `dev` extra
(`pytest`, `pytest-cov`). Verify the install:

```bash
cleanroom --version
cleanroom doctor
```

## Running tests

```bash
pytest
```

Run a single file or a keyword-filtered subset the normal `pytest` way
(`pytest tests/test_licence.py`, `pytest -k jurisdiction`). Please add or
update tests for any behavioural change — this project's own test suite
is part of how it demonstrates the practices it promotes (see
`tests/` in the repository layout).

## Code style

There is no formatter or linter wired into CI yet (see
[.github/workflows/ci.yml](.github/workflows/ci.yml) — it currently only
runs `pytest`). Until one is added, please follow these conventions by
hand:

- **No comments unless they explain a non-obvious *why*.** Comments that
  restate *what* the code does (or could be inferred from names) should
  be deleted, not added. Good comments in this codebase explain a
  deliberate trade-off or a legal/technical constraint — see the module
  docstrings in `src/cleanroom/zones.py` and
  `src/cleanroom/sanitisation/scanner.py` for the tone to match.
- **Keep functions small and single-purpose.** Prefer a few short,
  named helper functions over one long function with internal sections.
  If a function needs an internal comment to explain what block does
  what, that is usually a signal it should be split up instead.
- **Match the existing style** of the module you are editing (dataclasses
  for structured records, `pathlib.Path` over string paths, explicit
  `ExitCode` values from `src/cleanroom/exit_codes.py` rather than bare
  `sys.exit(int)` literals).
- **Never fabricate a conclusion.** If you are touching
  `src/cleanroom/legal/engine.py`, `src/cleanroom/licence/`, or the
  similarity engine, and the available evidence does not support a firm
  answer, the correct output is `UNKNOWN` / `insufficient_evidence`, not
  a best guess. This is a hard project invariant, not a style preference.

## Adding a new licence policy pack

Licence policy packs live at `policies/licences/<SPDX-ID>.yml` (e.g.
`policies/licences/MIT.yml`). Each pack documents facts about a licence
(family, copyleft strength, obligations, distribution triggers) — it is
not a verdict engine, and it must not state "you are allowed to do X"
as a conclusion. To add one:

1. Copy the structure of an existing pack (e.g.
   `policies/licences/Apache-2.0.yml`) as your starting point.
2. Use the exact SPDX licence identifier as the filename and the
   `spdx_id` field.
3. Fill in `family`, `osi_approved`, `fsf_libre`, `copyleft`,
   `key_obligations`, `distribution_triggers`,
   `network_use_triggers_obligations`, and any grant/retaliation/notice
   fields relevant to that licence, citing the licence text itself as
   your source rather than a secondary summary.
4. Validate the pack against
   `schemas/licence-finding.schema.json` and add/extend a test under
   `tests/` that exercises discovery and policy evaluation against a
   fixture using this licence.
5. See "Sensitive content" below — this change requires an additional
   reviewer.

## Adding a new jurisdiction pack

Jurisdiction packs live at `jurisdictions/<slug>/framework.yml` (e.g.
`jurisdictions/england-wales/framework.yml`,
`jurisdictions/usa-federal/framework.yml`). A pack documents facts and
primary authorities for a legal system (relevant statutes/case law areas,
structured questions the legal engine asks) — it does not resolve those
questions itself. To add one:

1. Create `jurisdictions/<slug>/framework.yml` following the shape of an
   existing pack.
2. Cite primary authorities (statutes, leading cases) directly, not
   secondary blog-style summaries, and keep every entry phrased as a
   fact or a structured question, never as a legal conclusion.
3. Validate against `schemas/jurisdiction-matrix.schema.json` and add a
   test that exercises `cleanroom jurisdiction` / the judicial-panel
   prompt generation (`cleanroom judge`) against the new pack.
4. See "Sensitive content" below — this change requires an additional
   reviewer.

## Sensitive content: heightened review

Any change under `policies/`, `jurisdictions/`, or `schemas/` is treated
as legal-content, not ordinary code, because these files are read
directly by users making real licensing and clean-room decisions — even
though the tool disclaims giving legal advice itself. Per
[GOVERNANCE.md](GOVERNANCE.md), such changes require sign-off from a
reviewer other than the author before merge, in addition to passing
CI. If you are the sole maintainer reviewing your own PR, say so
explicitly in the PR description and expect the merge to wait for a
second pair of eyes.

## Pull requests

- Keep PRs focused on one change; split unrelated fixes into separate PRs.
- Describe the "why", not just the "what", in the PR description.
- Link any related issue.
- Expect CI (`pytest` on Python 3.11 and 3.12) to pass before review.

## Reporting a security issue

Do not open a public issue for a security vulnerability. See
[SECURITY.md](SECURITY.md).
