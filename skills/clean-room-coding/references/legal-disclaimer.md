# Legal disclaimer (read before surfacing any legal/jurisdiction finding)

Nothing produced by `cleanroom`, this skill, or any panel/prompt it
generates (`cleanroom legal`, `cleanroom judge`) is legal advice. Specifically:

- **Simulated roles are simulations.** "Applicant Counsel", "Challenger
  Counsel", "Simulated Senior High Court (Business and Property Courts, IP)
  Reviewer", "Simulated Federal District Court IP Reviewer" etc. are
  prompt-engineering labels for structured adversarial analysis. If a user
  asks whether these are real lawyers/judges, say clearly that they are not.
- **Decision states are triage, not verdicts.** `GREEN` / `GREEN_WITH_CONDITIONS`
  / `AMBER` / `RED` / `UNKNOWN` tell you where to focus human legal review,
  not whether something is lawful. The engine is deliberately built so
  automated aggregation can never produce an unconditional `GREEN` --
  only an explicit human lawyer sign-off (`human_override` on a
  legal-finding record) can.
- **`UNKNOWN` / `insufficient_evidence` is a correct, common answer.**
  Never let a user (or yourself) round it up to a comfortable-sounding
  conclusion just because a report "should" have a clean answer.
- **When a user needs an actual legal opinion** (a real release decision
  with real consequences, a demand letter, litigation), tell them plainly
  that this tool's output is a starting point for their own qualified
  counsel, not a replacement for one.
- **`CLEAN_ROOM_CERTIFICATE.json` is a process record, not a certification**
  by any accredited body (not OpenChain, not a bar association, not a
  court). Its `disclaimer` field states this; don't strip that field out
  of any summary you give a user.

If you are ever uncertain whether something you're about to say is
"reporting a tool finding" versus "giving legal advice", err toward the
former framing explicitly and add the caveat.
