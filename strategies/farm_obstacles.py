from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from model import Pos, Bomber
from strategies.base import Strategy, DecisionContext, UnitPlan
from services.nav import bfs_path, neighbors4
from services.danger import blast_cross


@dataclass
class FarmObstaclesStrategy:
    """
    Подойти к ближайшему разрушаемому препятствию, поставить бомбу, убежать.
    """
    id: str = "farm_obstacles"

    def decide_for_unit(self, unit: Bomber, ctx: DecisionContext) -> Optional[UnitPlan]:
        if unit.bombs_available <= 0:
            return None
        if not ctx.obstacles:
            return None

        blocked = _blocked_cells(ctx)

        # 1) клетка постановки рядом с препятствием
        best: tuple[int, Pos, Pos] | None = None  # (dist, place_cell, obstacle_cell)
        for obs in ctx.obstacles:
            for place in neighbors4(obs):
                if place == unit.pos:
                    continue
                if place in blocked:
                    continue
                path = bfs_path(unit.pos, place, ctx.width, ctx.height, blocked, max_len=30)
                if path is None:
                    continue
                d = len(path)
                if best is None or d < best[0]:
                    best = (d, place, obs)

        if best is None:
            return None

        _, place, obs = best
        to_place = bfs_path(unit.pos, place, ctx.width, ctx.height, blocked, max_len=30)
        if not to_place:
            return None

        bomb_range = max(1, int(ctx.booster.bomb_range))

        # 2) зона будущего взрыва
        future_blast = blast_cross(place, bomb_range, ctx.walls, ctx.obstacles, set(ctx.bombs.keys()) | {place})
        forbidden = set(blocked) | set(ctx.danger) | future_blast | ctx.mob_positions

        # 3) найти безопасную клетку для отхода
        escape = self._pick_escape(place, ctx, forbidden)
        if escape is None:
            return None

        from_place = bfs_path(place, escape, ctx.width, ctx.height, blocked, max_len=30)
        if from_place is None:
            return None

        full_path = (to_place + from_place)[:30]
        if place not in full_path:
            return None

        return UnitPlan(path=full_path, bombs=[place], debug=f"farm obs={obs} place={place} escape={escape}")

    def _pick_escape(self, start: Pos, ctx: DecisionContext, forbidden: set[Pos]) -> Optional[Pos]:
        # простой поиск по “кольцам” манхэттена
        for radius in range(1, 10):
            x0, y0 = start
            candidates: list[Pos] = []
            for dx in range(-radius, radius + 1):
                dy = radius - abs(dx)
                for sgn in (-1, 1):
                    p = (x0 + dx, y0 + sgn * dy)
                    if 0 <= p[0] < ctx.width and 0 <= p[1] < ctx.height and p not in forbidden:
                        candidates.append(p)
                if dy == 0:
                    continue
            if candidates:
                return candidates[0]
        return None


def _blocked_cells(ctx: DecisionContext) -> set[Pos]:
    blocked = set()
    if not ctx.booster.can_pass_walls:
        blocked |= ctx.walls
    if not ctx.booster.can_pass_obstacles:
        blocked |= ctx.obstacles
    if not ctx.booster.can_pass_bombs:
        blocked |= set(ctx.bombs.keys())
    return blocked
