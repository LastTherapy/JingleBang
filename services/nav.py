from __future__ import annotations

from collections import deque
from typing import Optional

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
    max_len: int = 30,
) -> Optional[list[Pos]]:
    if start == goal:
        return []

    q = deque([start])
    prev: dict[Pos, Pos] = {}
    seen = {start}

    while q:
        cur = q.popleft()
        for nb in neighbors4(cur):
            if not inside(nb, w, h):
                continue
            if nb in seen:
                continue
            if nb in blocked:
                continue

            seen.add(nb)
            prev[nb] = cur

            if nb == goal:
                path_rev = [goal]
                while path_rev[-1] != start:
                    path_rev.append(prev[path_rev[-1]])
                path = list(reversed(path_rev))
                steps = path[1:]  # без стартовой клетки
                return steps[:max_len]

            q.append(nb)

    return None


def bfs_nearest(
    start: Pos,
    goals: set[Pos],
    w: int,
    h: int,
    blocked: set[Pos],
    max_len: int = 30,
) -> Optional[list[Pos]]:
    """Путь к ближайшей из целей."""
    if not goals:
        return None

    q = deque([start])
    prev: dict[Pos, Pos] = {}
    seen = {start}

    while q:
        cur = q.popleft()
        if cur in goals and cur != start:
            # восстановим путь до cur
            path_rev = [cur]
            while path_rev[-1] != start:
                path_rev.append(prev[path_rev[-1]])
            path = list(reversed(path_rev))
            return path[1:][:max_len]

        for nb in neighbors4(cur):
            if not inside(nb, w, h):
                continue
            if nb in seen:
                continue
            if nb in blocked:
                continue
            seen.add(nb)
            prev[nb] = cur
            q.append(nb)

    return None
