from __future__ import annotations

from collections import deque
from typing import Callable, Optional

from model import Pos


def neighbors4(p: Pos) -> list[Pos]:
    x, y = p
    return [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]


def inside(p: Pos, w: int, h: int) -> bool:
    x, y = p
    return 0 <= x < w and 0 <= y < h


def bfs_path(
    start: Pos,
    goal: Pos,
    w: int,
    h: int,
    blocked: set[Pos],
    max_len: int,
) -> Optional[list[Pos]]:
    """Return list of steps (without start), <= max_len."""
    if start == goal:
        return []

    q = deque([start])
    prev: dict[Pos, Pos] = {}
    seen = {start}

    while q:
        cur = q.popleft()
        for nb in neighbors4(cur):
            if not inside(nb, w, h) or nb in seen or nb in blocked:
                continue
            seen.add(nb)
            prev[nb] = cur
            if nb == goal:
                path_rev = [goal]
                while path_rev[-1] != start:
                    path_rev.append(prev[path_rev[-1]])
                path = list(reversed(path_rev))
                steps = path[1:]
                return steps[:max_len]
            q.append(nb)

    return None


def bfs_find(
    start: Pos,
    w: int,
    h: int,
    blocked: set[Pos],
    predicate: Callable[[Pos], bool],
    max_expand: int = 5000,
) -> Optional[list[Pos]]:
    """Find nearest cell matching predicate, return steps (without start)."""
    if predicate(start):
        return []

    q = deque([start])
    prev: dict[Pos, Pos] = {}
    seen = {start}
    expanded = 0

    while q and expanded < max_expand:
        cur = q.popleft()
        expanded += 1
        for nb in neighbors4(cur):
            if not inside(nb, w, h) or nb in seen or nb in blocked:
                continue
            seen.add(nb)
            prev[nb] = cur
            if predicate(nb):
                path_rev = [nb]
                while path_rev[-1] != start:
                    path_rev.append(prev[path_rev[-1]])
                path = list(reversed(path_rev))
                return path[1:]
            q.append(nb)
    return None
