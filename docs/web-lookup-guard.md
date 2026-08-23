# Web-lookup guard for implementation-zone agents (Part XCV)

## The gap this closes

Before this existed, a Zone H+I implementation agent had no sanctioned way
to search the web while building — it worked purely from the Zone H
handoff and its own general knowledge. That is safe but overly narrow: a
public-domain CRC algorithm reference, an official protocol spec, or a
permissively-licensed helper library are genuine engineering resources
that have nothing to do with the Zone R material a clean-room project
exists to avoid copying, and forbidding them outright just pushes real
questions onto an agent's unaided memory instead.

This module gives an orchestrating harness a real, deterministic check —
`cleanroom.webguard.check_url_against_exclusions` (and the equivalent
`cleanroom check-url` CLI command) — to run before it lets an
implementation agent's web-fetch/web-search tool call actually hit a URL.

## What this is, precisely

**A decision function plus an integration contract. Not a network
sandbox, not an enforced proxy, not something that can itself stop a
fetch happening in another process.**

`cleanroom-coding` is a CLI/library; it has no hook into whatever tool or
runtime actually performs a web-fetch inside an orchestrating harness or
agent framework (Claude Code, another SDK, a custom agent loop). It
cannot intercept, delay, or block that fetch. What it *can* do, and does,
is answer the question "does this URL match the Zone R material (or an
obvious mirror/fork of it) this project exists to avoid copying?" with a
real, evidenced answer — and log every question asked, whatever the
answer, to the project's tamper-evident evidence ledger.

Claiming this module enforces anything beyond that would be exactly the
overclaim AGENTS.md item c warns against for legal/licence findings — the
same honesty standard applies here to what a technical control can
actually do. If you need an actually-enforced sandbox (a proxy that
physically blocks the request), that is a separate, larger piece of
infrastructure this feature is not scoped to build.

## What gets excluded, and how

For a project whose Zone R was recruited via `git clone` (the pattern
every real project observed so far uses — see `zone_r`'s own `.git`
`origin` remote, the same source of truth `cleanroom diff-reference`
uses), `cleanroom.webguard.registered_exclusions()` automatically derives:

- `OWNER/REPO` — matches any URL whose path contains `OWNER` then `REPO`
  as two *consecutive* path segments, case-insensitive, on **any** host.
  This is what catches most mirrors without needing to know their domain
  in advance (e.g. `some-mirror.example/mirror/OWNER/REPO`).
- `HOST/OWNER/REPO` — the origin's own host explicitly named, for a clear
  audit trail even though the host-agnostic entry above already covers it.
- For a GitHub-hosted origin specifically, `raw.githubusercontent.com/
  OWNER/REPO` is also recorded explicitly, since that is the single most
  common way a GitHub repo's raw file content gets fetched by a different
  URL shape than the repo page itself.

Normalisation handles `https://github.com/OWNER/REPO`, `.git` suffixes,
a `www.` prefix, `git@github.com:OWNER/REPO.git` (SCP-like), and
`ssh://git@github.com/OWNER/REPO.git`.

If Zone R was **not** recruited via `git clone` (no `.git`, or no
resolvable `origin` remote), there is no automatic derivation — per the
never-fabricate-a-conclusion rule (AGENTS.md item c), `webguard` refuses
to guess a pattern rather than inventing one. Cover that project with
manual `cleanroom exclude-source` entries instead.

### Manual additions: `cleanroom exclude-source`

A human who identifies a mirror/fork the automatic heuristic can't name on
its own (a rehost under a completely unrelated `owner/repo`, a vendored
tarball site, a translated/renamed fork) can add it directly:

```bash
cleanroom exclude-source "gitclone.example/vendor/meshtastic-proto-mirror" \
  --note "known unofficial mirror, found 2026-08-23"
```

Manual patterns are matched as a plain case-insensitive **substring** of
the checked URL — simple and predictable, but that also means an
overly-broad pattern (a bare hostname shared by many unrelated projects)
can over-block. Prefer a specific host+path fragment.

## Known limitations of the heuristic

- **Path-shape based, not content-based.** It matches on `OWNER/REPO`
  appearing in a URL's path. A mirror that reshuffles the path entirely
  (serves the identical code under a different, unrelated name, with no
  `owner/repo`-shaped path anywhere) will not be caught automatically —
  it needs a manual `exclude-source` entry once a human identifies it.
- **No content fetching or hashing.** This never downloads anything to
  check whether it's *actually* the same code; it only reasons about the
  URL string. A URL that happens to reuse the same `OWNER/REPO` path
  segments for an unrelated purpose (unlikely in practice, but possible)
  would be blocked too — a conservative false positive, which is the
  correct bias per AGENTS.md item b's "over-flag on purpose" precedent for
  the prompt-injection scanner.
- **One reference source per check.** `registered_exclusions()` only
  covers Zone R's own registered origin. A project with several distinct
  reference sources recruited into the same Zone R needs a manual
  `exclude-source` entry for each one beyond the first that isn't the
  checkout's own `origin` remote.
- **No wildcard/regex syntax.** Both automatic and manual patterns are
  simple string/segment matches, not full pattern languages — deliberately,
  so a human reviewing the exclusion list (`evidence/exclusions.json`) can
  read exactly what it does without needing to evaluate a regex.

## The integration contract for an orchestrating harness

If you are building or configuring the harness that actually drives an
implementation-zone agent's web-fetch/web-search tool (Claude Code's own
`WebFetch`/`WebSearch`, another agent framework's equivalent, or a custom
tool wrapper), wire it in like this:

1. **Before** dispatching the agent's fetch/search call, run:

   ```bash
   cleanroom --project <project_dir> check-url "<the target URL>"
   ```

   or, from Python, in-process:

   ```python
   from cleanroom.project import Project
   from cleanroom.webguard import check_url_against_exclusions

   project = Project.discover(project_dir)
   result = check_url_against_exclusions(url, project)
   ```

2. **On `blocked: true`:**
   - Refuse the fetch — do not let the underlying tool call proceed with
     that URL.
   - Treat it as a policy violation, not a soft warning: the CLI exits
     `3` (`ExitCode.POLICY_FAILURE`, see `src/cleanroom/exit_codes.py`) on
     a blocked result specifically so a script can gate on it directly
     (`cleanroom check-url "$URL" || refuse_fetch`).
   - Surface it to the human overseeing the project — `result["reason"]`
     is a ready-to-show string naming the matched pattern and its source.
     Do not silently drop the attempt; a pattern of blocked lookups for
     the same URL shape may mean the agent is trying to route around the
     guard (deliberately or not) and is worth a human's attention.

3. **On `blocked: false`:** proceed with the fetch. The check has already
   been appended to the evidence ledger (see below) either way, so no
   further bookkeeping is needed on the allowed path.

4. **Every call is logged**, blocked or allowed, to
   `<project>/evidence/ledger.jsonl` — the same hash-chained evidence
   ledger `cleanroom verify` walks and every other `cleanroom` command
   writes to (`cleanroom.evidence.EvidenceLedger`, see `evidence.py`).
   Each entry records the actor (`tool: cleanroom-webguard`), the URL, and
   whether it matched an exclusion. This is what gives a later human
   reviewer — not just the harness in the moment — a real record of what
   an implementation agent looked up during a project, not merely the
   harness's own say-so that it "respected the policy."

### What the harness must NOT rely on

Do not assume that omitting the `check-url` call, or calling it after the
fetch already happened, is caught by anything else in this codebase. The
check is opt-in from the harness's side by design (this project has no
way to force it) — the guarantee here is "if you call it honestly, you
get a real, evidenced answer and a real audit trail," not "fetches are
physically prevented." That stronger guarantee is future work, not
something this feature (or its tests) claim to deliver today.
