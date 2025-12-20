from __future__ import annotations

from model import Pos


def _inside(p: Pos, w: int, h: int) -> bool:
    x, y = p
    return 0 <= x < w and 0 <= y < h


def danger_from_bomb(
    pos: Pos,
    bomb_range: int,
    walls: set[Pos],
    obstacles: set[Pos],
    bombs_as_stoppers: set[Pos],
    map_size: tuple[int, int],
) -> set[Pos]:
    w, h = map_size
    x, y = pos
    out = set()
    if _inside(pos, w, h):
        out.add(pos)

    for dx, dy in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
        for i in range(1, bomb_range + 1):
            p = (x + dx * i, y + dy * i)
            if not _inside(p, w, h):
                break
            out.add(p)
            if p in walls or p in obstacles or p in bombs_as_stoppers:
                break
    return out


def build_danger(
    bombs: dict[Pos, tuple[int, float]],  # pos -> (range, timer)
    timer_threshold: float,
    walls: set[Pos],
    obstacles: set[Pos],
    map_size: tuple[int, int],
) -> set[Pos]:
    stoppers = set(bombs.keys())
    danger: set[Pos] = set()
    for p, (r, t) in bombs.items():
        if t <= timer_threshold:
            danger |= danger_from_bomb(p, r, walls, obstacles, stoppers, map_size=map_size)
    return danger
