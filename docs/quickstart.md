# Quick start

```bash
git clone https://github.com/khhvmc5g6f-eng/clean-room-coding
cd clean-room-coding
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cleanroom doctor
```

This project is not yet published to PyPI. Run it from the editable Git
checkout shown above. To use its Agent Skill independently of the Python CLI:

```bash
gh skill install khhvmc5g6f-eng/clean-room-coding clean-room-coding
```

`doctor` should report `ok` for `schemas`, `licence_policy_packs`,
`jurisdiction_packs` and `git`.

## Walk through a project

```bash
mkdir -p /tmp/my-reimplementation && cd /tmp/my-reimplementation
cleanroom init --name "My Reimplementation" --id my-reimpl --target-language python
```

This writes `.cleanroom.yml` and creates `zone-r/` (Reference),
`zone-h/` (Handoff) and `zone-i/` (Implementation).

**1. Record intake authority** before touching any reference material:

```bash
cleanroom intake --source "upstream-lib v2.3, github.com/example/upstream-lib" \
  --access-authority public
```

**2. Put the reference material in `zone-r/`**, take a quick deterministic
look at it, then discover its licences:

```bash
cleanroom inspect zone-r
cleanroom licence zone-r
```

**3. Resolve jurisdiction** (edit `.cleanroom.yml`'s `jurisdiction.required_markets`
first if the defaults -- `gb` required, `us` informational -- don't match):

```bash
cleanroom jurisdiction
```

**4. Analyse** (writes per-role analyst task files under `evidence/analysis-tasks/`;
an LLM session -- e.g. this project's Agent Skill run from Claude Code --
does the actual reading of `zone-r` and records findings as requirement
nodes):

```bash
cleanroom analyse
cleanroom specify add-requirement --id CR-REQ-000001 --kind requirement \
  --statement "Entries can be sorted ascending or descending by name" \
  --classification observable_requirement
cleanroom specify add-behavioral --given "a list of entries" \
  --when "ascending order by name is requested" \
  --then "entries are returned alphabetically ascending" \
  --requirement CR-REQ-000001
```

**5. Write the handoff specification into `zone-h/`**, sanitise it, pass it
through the Clean-Room Gate, then build the manifest:

```bash
echo "GIVEN a list of entries / WHEN sorted ascending / THEN alphabetical order" \
  > zone-h/sort-behaviour.md
cleanroom sanitise zone-h/sort-behaviour.md
cleanroom gate --specification-version v1 --decision pass \
  --reviewer "Your Name" --notes "Sufficient for independent implementation."
cleanroom handoff --specification-version v1 --all-c0
```

`handoff` refuses (exit 3) without a matching PASS already recorded for
`v1` -- see [docs/concepts.md](concepts.md#the-clean-room-gate).

**6. Implement** in `zone-i/` (a fresh agent/contributor, Zone H access
only), registering the agent and recording architecture decisions:

```bash
cleanroom build --role "Backend Team"
cleanroom architect --title "Sort implementation" \
  --decision "Use a stable sort keyed on the entries' name field" \
  --rationale "Matches the handed-off behavioural spec; no dependency on the reference's internal data structures"
```

**7. Test, provenance, audit:**

```bash
cleanroom test
cleanroom provenance
cleanroom audit
```

**8. Legal triage and report:**

```bash
cleanroom legal --access-authority public
cleanroom judge   # writes prompts to evidence/judicial-review/ -- answer them via an LLM session
cleanroom report --version 0.1.0
cleanroom release  # exit 9 (MANUAL_REVIEW_REQUIRED) is expected, not a failure
cleanroom status
```

See [examples/](../examples/) for a complete, runnable version of this
walkthrough, and [docs/legal-disclaimer.md](legal-disclaimer.md) before
treating any of step 8's output as more than engineering triage.
