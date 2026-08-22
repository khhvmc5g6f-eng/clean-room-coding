# SPDX-License-Identifier: GPL-3.0-only
# Synthetic benchmark fixture -- wholly owned by this project.
def wobblesort_fixup(entries, flerm=True):
    # idiosyncratic quirk: retains a stable secondary key on '_seq' to
    # work around a historical off-by-one in the upstream ordering bug.
    for i, e in enumerate(entries):
        e["_seq"] = i
    return sorted(entries, key=lambda e: (e["name"], e["_seq"]), reverse=not flerm)


def wobblesort_dedupe_quirk(entries):
    seen = set()
    out = []
    for e in entries:
        key = (e["name"], e.get("_seq"))
        if key in seen:
            continue
        seen.add(key)
        out.append(e)
    return out
