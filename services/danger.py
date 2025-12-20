from __future__ import annotations

from model import Pos


def blast_cross(
    pos: Pos,
    bomb_range: int,
    walls: set[Pos],
    obstacles: set[Pos],
    bombs: set[Pos],
) -> set[Pos]:
    """
    Взрыв крестом. Луч останавливается об стену/препятствие/бомбу.
    """
    x, y = pos
    out = {pos}
    for dx, dy in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
        for i in range(1, bomb_range + 1):
            p = (x + dx * i, y + dy * i)
            out.add(p)
            if p in walls or p in obstacles or p in bombs:
                break
    return out


def build_danger(
    bombs: dict[Pos, tuple[int, float]],  # pos -> (range, timer_sec)
    timer_threshold: float,
    walls: set[Pos],
    obstacles: set[Pos],
) -> set[Pos]:
    danger: set[Pos] = set()
    stoppers = set(bombs.keys())
    for p, (r, t) in bombs.items():
        if t <= timer_threshold:
            danger |= blast_cross(p, r, walls, obstacles, stoppers)
    return danger


def can_hit_target_in_cross(
    bomb_pos: Pos,
    target_pos: Pos,
    bomb_range: int,
    walls: set[Pos],
    obstacles: set[Pos],
    bombs: set[Pos],
) -> bool:
    """
    Можно ли поразить target_pos взрывом бомбы в bomb_pos.
    """
    bx, by = bomb_pos
    tx, ty = target_pos
    if bx == tx:
        dist = abs(ty - by)
        if dist == 0 or dist > bomb_range:
            return False
        step = 1 if ty > by else -1
        y = by
        for _ in range(dist):
            y += step
            p = (bx, y)
            if p == target_pos:
                return True
            if p in walls or p in obstacles or p in bombs:
                return False
        return False
    if by == ty:
        dist = abs(tx - bx)
        if dist == 0 or dist > bomb_range:
            return False
        step = 1 if tx > bx else -1
        x = bx
        for _ in range(dist):
            x += step
            p = (x, by)
            if p == target_pos:
                return True
            if p in walls or p in obstacles or p in bombs:
                return False
        return False
    return False
