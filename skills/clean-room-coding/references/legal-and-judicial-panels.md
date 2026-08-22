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

Whatever you produce, it feeds back into `legal-finding.schema.json`
records (via `human_override` if a real lawyer reviews it) -- it does not
by itself change `CLEAN_ROOM_CERTIFICATE.json`'s `global_decision`, which
`cleanroom report` computes deterministically from whatever finding records
exist (`src/cleanroom/legal/panels.py::aggregate_jurisdiction_decision` /
`global_decision` -- worst-finding-wins, and a required market with `RED`
blocks release outright regardless of other markets).

Read `legal-disclaimer.md` before writing any of this if you haven't
already.
