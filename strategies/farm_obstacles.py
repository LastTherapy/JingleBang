from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from model import Pos, Bomber
from strategies.base import Strategy, DecisionContext, UnitPlan
from services.nav import bfs_path, neighbors4
from services.danger import danger_from_bomb


@dataclass
class FarmObstaclesStrategy:
    """Подходим к ближайшему разрушаемому препятствию, ставим бомбу, отбегаем."""
    id: str = "farm_obstacles"

    def decide_for_unit(self, unit: Bomber, ctx: DecisionContext) -> Optional[UnitPlan]:
        if unit.bombs_available <= 0:
            return None
        if not ctx.obstacles:
            return None

        blocked = ctx.walls | ctx.obstacles | set(ctx.bombs.keys())

        # 1) выбираем ближайшую клетку постановки рядом с препятствием
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
        if to_place is None or not to_place:
            return None

        # 2) моделируем взрыв будущей бомбы (range=1, пока нет данных о прокачке)
        future_blast = danger_from_bomb(
            place,
            bomb_range=1,
            walls=ctx.walls,
            obstacles=ctx.obstacles,
            bombs_as_stoppers=set(ctx.bombs.keys()) | {place},
            map_size=(ctx.width, ctx.height),
        )
        forbidden = ctx.danger | future_blast | blocked | {place}

        escape = self._pick_escape(place, ctx, forbidden)
        if escape is None:
            escape = self._any_free_neighbor(place, ctx, forbidden)
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
        # BFS-подобный подбор “первой безопасной” клетки в радиусе
        for radius in range(1, 10):
            x0, y0 = start
            for dx, dy in [(radius,0),(-radius,0),(0,radius),(0,-radius)]:
                p = (x0 + dx, y0 + dy)
                if 0 <= p[0] < ctx.width and 0 <= p[1] < ctx.height and p not in forbidden:
                    return p
            # ромб манхэттена
            for dx in range(-radius, radius + 1):
                dy = radius - abs(dx)
                for sdy in (dy, -dy):
                    p = (x0 + dx, y0 + sdy)
                    if 0 <= p[0] < ctx.width and 0 <= p[1] < ctx.height and p not in forbidden:
                        return p
        return None

    def _any_free_neighbor(self, p: Pos, ctx: DecisionContext, forbidden: set[Pos]) -> Optional[Pos]:
        for nb in neighbors4(p):
            if 0 <= nb[0] < ctx.width and 0 <= nb[1] < ctx.height and nb not in forbidden:
                return nb
        return None
