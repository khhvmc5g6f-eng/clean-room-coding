# Answering the adversarial-counsel / judicial-review prompts

`cleanroom judge` (`src/cleanroom/legal/panels.py`) writes three prompt
files per convened jurisdiction pack into `evidence/judicial-review/`:
`<pack>-applicant-prompt.md`, `<pack>-challenger-prompt.md`,
`<pack>-judicial-prompt.md`. These are meant to be answered by an LLM (you,
via a fresh subagent, or another harness) -- `cleanroom` itself never calls
one. If you are the one answering them:

- **Applicant Counsel**: construct the strongest plausible argument for
  independence/compliance from the supplied evidence only. Explicitly
  surface unfavourable evidence too -- omitting it is not "strongest
  plausible", it's misleading.
- **Challenger Counsel**: argue as if instructed by the original rights
  holder. Identify the strongest reasonable allegations the evidence
  supports, and what additional evidence a real rights holder would go
  looking for (Part L's "evidential stress test").
- **Judicial Review**: use the jurisdiction pack's `simulated_judicial_role_title`
  (never a generic or wrong-jurisdiction title). Your job is to find
  weaknesses in BOTH briefs, not to approve release -- do not be
  sycophantic toward a clean outcome. Produce, per issue: applicable
  law, facts established vs. uncertain, an assessment of similarities and
  their explanation, outstanding rights questions, and a `decision_state`
  (`GREEN` | `GREEN_WITH_CONDITIONS` | `AMBER` | `RED` | `UNKNOWN`) with
  reasoning -- and say plainly wherever a real answer needs qualified human
  counsel rather than this simulation.

Whatever you produce, feed it back with `cleanroom judge-adjudicate
<pack-id> <answer-file> --panel-member <id>` -- `answer-file` is a JSON
list of `{issue, decision_state, for_release_argument,
against_release_argument, adjudication}` objects, one per issue you
adjudicated. This merges into the matching `legal-finding.schema.json`
record(s) (matched by issue + which of that pack's real markets the
finding is under, e.g. `gb`/`uk` for `england-wales` -- not the pack id
itself, a different string). If `.cleanroom.yml`'s `providers.panel_size`
is greater than 1 (provider diversity), call this once per independent
panel member with a distinct `--panel-member` id (and `--model-provider`/
`--model-id` if known) -- the finding's recorded `decision_state` always
reflects the worst-wins aggregate across every panel member so far
(`src/cleanroom/legal/panels.py::aggregate_panel_decision`), so one
dissenting RED/AMBER member is never smoothed over by others' more
favourable view. The command's own output reports whether `panel_size`/
`panel_diversity_required` are actually satisfied yet.

This does NOT by itself change `CLEAN_ROOM_CERTIFICATE.json`'s
`global_decision`, which `cleanroom report` computes deterministically
from the legal-issue engine's finding records
(`src/cleanroom/legal/panels.py::aggregate_jurisdiction_decision` /
`global_decision` -- worst-finding-wins, and a required market with `RED`
blocks release outright regardless of other markets) -- a judicial
panel's adjudication is recorded as additional evidentiary context on the
finding, not silently made into a second release gate. A real lawyer's
review still goes through the same finding's `human_override` field, as
before.

Read `legal-disclaimer.md` before writing any of this if you haven't
already.
