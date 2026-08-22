# SPDX-License-Identifier: MIT
# Synthetic benchmark fixture -- wholly owned by this project. A second,
# independently-written list-backed stack with a deliberately different
# shape (deque instead of list, different method names/order, an extra
# size() method) -- ground truth NEGATIVE: similar in *concept* to
# reference_stack.py purely because a stack is a stack, not because either
# was derived from the other.
from collections import deque


class LastInFirstOut:
    def __init__(self):
        self.buffer = deque()

    def size(self):
        return len(self.buffer)

    def add(self, item):
        self.buffer.append(item)

    def take(self):
        return self.buffer.pop()

    def top(self):
        return self.buffer[-1]
