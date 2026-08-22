---
name: Licence detection error
about: cleanroom licence concluded the wrong licence, or should have said UNKNOWN
title: "[Licence detection] "
labels: licence-detection
---

**File / path scanned**

**Expected licence** (SPDX identifier, or "should be UNKNOWN" if
evidence was genuinely ambiguous)

**Detected licence** (the `concluded` value from `cleanroom licence
--json`)

**Evidence present at that path** (LICENSE/NOTICE file contents, SPDX
header, package manifest field — whichever applies; paste the relevant
snippet, not the whole file)

```
```

**Project config used** (`.cleanroom.yml` `dependency_policy` section —
`allowed_licences` / `denied_licences` / `unknown_licence_action`)

```yaml
```

**Full `cleanroom licence --json` output for this finding**

```json
```

**Additional context** (e.g. is this a case the discovery heuristics
can't reasonably handle, or a genuine bug?)
