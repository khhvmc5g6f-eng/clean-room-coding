# SPDX-License-Identifier: MIT
# Synthetic benchmark fixture -- wholly owned by this project (a successful
# clean-room simulation: implements the same OBSERVABLE behaviour as
# gpl-app/wobble_sort.py -- stable ordering by name, then de-duplication --
# from an independently-written behavioural spec, with different structure).
from operator import itemgetter


def order_by_name(records, descending=False):
    indexed = list(enumerate(records))
    indexed.sort(key=lambda pair: (pair[1]["name"], pair[0]), reverse=descending)
    return [record for _, record in indexed]


def unique_by_name(records):
    result = {}
    for record in records:
        result.setdefault(record["name"], record)
    return list(result.values())
