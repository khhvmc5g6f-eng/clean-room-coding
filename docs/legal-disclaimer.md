# Legal disclaimer

**Clean Room Coding is a software engineering tool. It is not a law firm,
does not employ lawyers acting in that capacity for you, and does not
provide legal advice.**

## What "legal" and "judicial" features actually are

- `cleanroom legal` runs a deterministic, heuristic **legal issue engine**
  (`src/cleanroom/legal/engine.py`) that only ever concludes GREEN,
  GREEN_WITH_CONDITIONS, AMBER, RED or UNKNOWN from facts the rest of the
  tool has already computed (licence discovery results, the isolation
  self-test, similarity findings). Where no such fact exists, the result
  is `UNKNOWN` with `confidence: "insufficient_evidence"` -- by design,
  never coerced into a reassuring-looking `GREEN`.
- `cleanroom judge` generates **prompt templates** for three simulated
  roles -- Applicant Counsel, Challenger Counsel, and a jurisdiction-
  appropriate Judicial Reviewer (e.g. "Simulated Senior High Court
  (Business and Property Courts, IP) Reviewer" for England & Wales,
  "Simulated Federal District Court IP Reviewer" for the US). These are
  clearly-labelled simulations for engineering triage. `cleanroom` never
  calls an LLM itself to answer them -- whatever produces the answers
  (you, a Claude Code session, another harness) must preserve that
  labelling and must say, if asked, that these are not real legal
  professionals.
- Jurisdiction packs (`/jurisdictions/*/framework.yml`) record real,
  citable primary and secondary authorities (statutes, leading cases) as
  **facts about what the law says**, plus structured questions for review.
  They are not, and cannot be, a substitute for jurisdiction-specific,
  up-to-date, qualified legal advice about your specific facts.
- `CLEAN_ROOM_CERTIFICATE.json` is a **process record**: what was checked,
  what passed, what's outstanding. It is not a certification issued by any
  accredited body (not OpenChain, not a court, not a bar association), and
  its schema requires the disclaimer text to be present verbatim.

## What you should actually do with the output

Treat every AMBER/RED/UNKNOWN finding as a prioritised list of things to
take to qualified counsel in the relevant jurisdiction(s) before making a
real release decision. Treat GREEN_WITH_CONDITIONS as "the automated
checks this tool can run currently show no red flag, conditioned on the
listed obligations" -- not as "cleared." The release policy engine
(`src/cleanroom/report.py::release_allowed`) is deliberately built so a
human sign-off is required by default (`approval_gates.human_signoff_required_for_release`)
even when every automated gate passes -- exit code 9
(`MANUAL_REVIEW_REQUIRED`) reflects this and should never be silently
treated as a pass by CI.

## Currency

Legal authority changes. A `legal_review_as_of` date is recorded on legal
findings; re-run `cleanroom legal`/`cleanroom judge` (and re-check the
underlying jurisdiction pack) whenever licences, legislation, target
markets, or distribution model change materially.
