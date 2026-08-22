# SPDX-License-Identifier: MIT
# Synthetic benchmark fixture -- wholly owned by this project.
class PriorityQueue:
    def __init__(self):
        self._items = []

    def push(self, item, priority):
        self._items.append((priority, item))
        self._items.sort(key=lambda pair: pair[0])

    def pop(self):
        return self._items.pop(0)[1]
