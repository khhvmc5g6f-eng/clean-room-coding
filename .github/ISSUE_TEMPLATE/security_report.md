---
name: Security vulnerability
about: Do not use this template — report privately instead
title: "[Do not file publicly — see SECURITY.md]"
labels: security
---

**Please do not report security vulnerabilities through a public GitHub
issue.**

See [SECURITY.md](../../SECURITY.md) for how to report a vulnerability
privately, via either:

- [GitHub private security advisories](https://github.com/khhvmc5g6f-eng/clean-room-coding/security/advisories/new), or
- `security@cleanroom.dev`

This is especially important for anything involving:

- A bypass of the Zone R/H/I path guard (`src/cleanroom/zones.py`)
- A way to make the licence, legal, or similarity engines produce a
  false/fabricated conclusion instead of `UNKNOWN`/`insufficient_evidence`
- Exposure of sensitive evidence-ledger contents
- Any other confidentiality, integrity, or availability issue

If you have arrived here without a security concern, please use one of
the other issue templates instead.
