# Example: clean-room reimplementation of a synthetic MIT-licensed library

`run.sh` runs the entire pipeline end-to-end against a small, synthetic
MIT-licensed "reference" library (written for this example, not a real
third-party project) that sorts a list of entries by name.

```bash
bash examples/walkthrough-mit-library/run.sh /tmp/crc-walkthrough
```

It walks through every phase: `init`, `intake`, `licence`, `jurisdiction`,
`analyse`/`specify`, `sanitise`/`handoff`, `build`/`architect`, `test`/
`provenance`/`audit`, `legal`/`judge`/`report`/`release`/`status`. At the
end, `/tmp/crc-walkthrough/CLEAN_ROOM_REPORT.md` and
`CLEAN_ROOM_CERTIFICATE.json` summarise the result -- expect a `GREEN_WITH_CONDITIONS`-ish
picture with `release` exiting `9` (`MANUAL_REVIEW_REQUIRED`), since this
tool never auto-approves a release.

This same sequence is asserted, command-by-command, in
[tests/integration/test_cli_end_to_end.py](../../tests/integration/test_cli_end_to_end.py),
so it is verified on every change to the CLI, not just documented.
