# SPDX-License-Identifier: MIT
# Synthetic benchmark fixture -- wholly owned by this project. A plain,
# idiomatic list-backed stack -- the kind of code many engineers would
# independently converge on, used to test that ordinary shared idiom
# doesn't get misclassified as copying.
class Stack:
    def __init__(self):
        self._items = []

    def push(self, value):
        self._items.append(value)

    def pop(self):
        return self._items.pop()

    def peek(self):
        return self._items[-1]

    def is_empty(self):
        return len(self._items) == 0
