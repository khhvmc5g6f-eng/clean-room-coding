# Benchmark fixtures (Part LXXVI)

Synthetic, wholly-owned-by-this-project fixtures for evaluating Clean Room
Coding's engines without relying on disputed or copyrighted third-party
code. See `tests/integration/test_benchmark_suite.py` for the assertions
that use them.

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

This is a precision/recall *scaffold*, not yet a full measured
precision/recall report (Part LXXVII) -- see ROADMAP.md.
