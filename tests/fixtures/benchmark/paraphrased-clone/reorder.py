# SPDX-License-Identifier: GPL-3.0-only
# Synthetic benchmark fixture -- wholly owned by this project (a partially-
# disguised clone of gpl-app/wobble_sort.py: variable names and control-flow
# layout were lightly reworked, but the underlying algorithm/structure --
# stamp a stable secondary key, then sort by (name, key), then de-dupe with
# a seen-set -- was not independently re-derived).
def stabilize_ordering(record_list, ascending=True):
    idx = 0
    for record in record_list:
        record["_seq"] = idx
        idx += 1
    reverse_flag = not ascending
    return sorted(record_list, key=lambda r: (r["name"], r["_seq"]), reverse=reverse_flag)


def drop_duplicates(record_list):
    already_seen = set()
    kept = []
    for record in record_list:
        marker = (record["name"], record.get("_seq"))
        if marker in already_seen:
            continue
        already_seen.add(marker)
        kept.append(record)
    return kept
