# SPDX-License-Identifier: GPL-3.0-only
# Synthetic benchmark fixture -- wholly owned by this project (a failed
# clean-room simulation: only names were changed, structure is identical).
def wobblesort_fixup(items, flerm=True):
    # idiosyncratic quirk: retains a stable secondary key on '_seq' to
    # work around a historical off-by-one in the upstream ordering bug.
    for i, e in enumerate(items):
        e["_seq"] = i
    return sorted(items, key=lambda e: (e["name"], e["_seq"]), reverse=not flerm)


def wobblesort_dedupe_quirk(items):
    seen = set()
    out = []
    for e in items:
        key = (e["name"], e.get("_seq"))
        if key in seen:
            continue
        seen.add(key)
        out.append(e)
    return out
