# Exit codes

From `src/cleanroom/exit_codes.py`:

| Code | Name | Meaning |
|---|---|---|
| 0 | PASS | Success. |
| 1 | GENERAL_FAILURE | Unclassified error. |
| 2 | CONFIGURATION_ERROR | Missing/invalid `.cleanroom.yml`. |
| 3 | POLICY_FAILURE | Release policy gate failed (not a RED jurisdiction specifically -- see 8). |
| 4 | CONTAMINATION_FAILURE | Non-C0 material in Zone H, or the isolation self-test failed. |
| 5 | LICENCE_FAILURE | A licence finding is `denied` or unresolved-and-blocking. |
| 6 | TEST_FAILURE | Behavioural/pytest/`compare` failure. |
| 7 | SIMILARITY_FAILURE | Reserved for similarity-gate failures (not yet wired to a dedicated CLI check in v0.1 -- see ROADMAP.md). |
| 8 | LEGAL_RED | Global legal decision is RED in a required jurisdiction. |
| 9 | MANUAL_REVIEW_REQUIRED | Release is otherwise allowed but human sign-off is still configured as required -- **this is an expected stop, not a failure.** |

When scripting against `cleanroom` (CI, or your own orchestration), always
special-case 9: it means "everything this tool can check has passed; a
human still needs to say yes." Treating it as a failure will make every
project permanently unreleasable; treating it as a silent pass defeats the
entire point of the human sign-off gate.
