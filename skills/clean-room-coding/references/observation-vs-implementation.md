# Observable requirement vs. source implementation detail

Every finding an analyst produces while reading Zone R must be tagged one
of two ways (`schemas/requirement.schema.json`'s `classification` field):

- **`observable_requirement`** -- behaviour a user or external caller can
  observe from outside the program. Example: "When the user selects
  ascending order, entries are returned alphabetically." Eligible for
  handoff (subject to contamination level `C0` and sanitisation).
- **`source_implementation_detail`** -- internal structure, algorithm
  choice, variable/class naming, file layout. Example: "Class `FooSorter`
  calls `barSort()` with this internal data structure." **Excluded from
  handoff.** `RequirementGraph.source_implementation_details()` and
  `handoff_eligible_nodes()` enforce this split mechanically.

This is the single most important judgement call an analyst agent makes.
Getting it wrong in the direction of "observable" is how a clean-room
process fails silently -- it's the difference between "the API returns
entries sorted by the `name` field" (fine to hand off) and "the API's
sort is implemented with a comparator that mirrors the reference's exact
internal method name and code structure" (not fine).

When genuinely unsure which category a finding belongs in, default to
`source_implementation_detail` (excluded) and flag it for human review
rather than guessing it's safe to hand off.
