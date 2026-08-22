# Benchmark fixtures (Parts LXXVI-LXXVII)

Synthetic, wholly-owned-by-this-project fixtures for evaluating Clean Room
Coding's engines without relying on disputed or copyrighted third-party
code. `tests/integration/test_benchmark_suite.py` exercises the original
two-case scaffold directly; `manifest.yml` + `src/cleanroom/benchmark.py`
(`cleanroom benchmark`) run the full 8-case ground-truth corpus and
compute real precision/recall/F1 -- a measured report, not just a
scaffold, per Part LXXVII.

- `permissive-app/` -- a small MIT-licensed synthetic library.
- `gpl-app/` -- a small GPL-3.0-only-licensed synthetic library with a
  distinctive, idiosyncratic structure (unusual variable names, a specific
  bug-compatible quirk) precisely so a similarity engine has something
  non-generic to detect.
- `contaminated-clone/` -- a byte-for-byte copy of `gpl-app`'s source with
  only cosmetic renaming, simulating a failed clean-room process. The
  similarity engine should score this as high lexical/structural
  similarity and classify it `suspicious`.
- `independent-clone/` -- a from-scratch implementation of the same
  observable behaviour as `gpl-app`, written with different structure and
  naming, simulating a successful clean-room process. The similarity
  engine should score this low and classify it `coincidental`.
- `paraphrased-clone/` -- a partially-disguised clone of `gpl-app` (names
  and layout reworked, algorithm/structure not independently re-derived).
- `common-idiom/` -- two independently-written, structurally different
  implementations of the same trivial concept (a stack), testing that
  ordinary shared idiom doesn't get misclassified as copying.
- `js-app/` / `js-contaminated-clone/` / `js-independent-clone/` and
  `go-app/` / `go-contaminated-clone/` / `go-independent-clone/` -- the
  same contaminated/independent pattern in JavaScript and Go, exercising
  the real tree-sitter structural path (`ast-grep-py`), not just Python's
  stdlib `ast`.

## Measured result (run `cleanroom benchmark` to reproduce)

Across these 8 hand-built cases: **precision 0.80, recall 1.00, F1 0.89,
accuracy 0.875** at the default 0.15 structural threshold. Every real
copy in this corpus was caught (no false negatives) -- there is one real,
documented false positive: `js-independent-clone` scores ~0.18, just
above the default threshold, despite being a genuinely independent
reimplementation. This is an honest, currently-unresolved limitation of
the default structural threshold for JavaScript's tree-sitter node-kind
vocabulary (a functional-array-methods rewrite shingles closer to a
loop-based original than the equivalent Python/Go rewrites do in this
corpus) -- not something to paper over by loosening this fixture. See
`ROADMAP.md` for follow-up.

**Honesty note:** 8 hand-built synthetic cases describe how the engine
behaves on these specific cases, not a statistically representative
measurement of general clean-room-reimplementation accuracy. Treat this
as a real but small signal, not a general accuracy claim.
