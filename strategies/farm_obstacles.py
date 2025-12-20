from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from model import Bomber, Pos
from services.nav import bfs_path, bfs_find, neighbors4, inside
from strategies.base import DecisionContext, Strategy, UnitPlan


@dataclass
class FarmObstaclesStrategy:
    """Approach nearest obstacle, plant bomb adjacent, then move away."""
    id: str = "farm_obstacles"

    def decide_for_unit(self, unit: Bomber, ctx: DecisionContext) -> Optional[UnitPlan]:
        if unit.bombs_available <= 0:
            return None
        if not ctx.obstacles:
            return None

        blocked = ctx.walls | ctx.obstacles | ctx.bomb_cells | ctx.mob_cells

        # pick a "place cell" adjacent to an obstacle
        best_path = None
        best_place = None
        for obs in ctx.obstacles:
            for place in neighbors4(obs):
                if not inside(place, ctx.width, ctx.height):
                    continue
                if place in blocked:
                    continue
                path = bfs_path(unit.pos, place, ctx.width, ctx.height, blocked, max_len=30)
                if path is None:
                    continue
                if best_path is None or len(path) < len(best_path):
                    best_path = path
                    best_place = place

        if best_path is None or best_place is None or len(best_path) == 0:
            return None

        # escape: find nearest cell that is not adjacent to place and not in blocked
        def safe(p: Pos) -> bool:
            if p in blocked:
                return False
            # avoid immediate adjacency (roughly "step away")
            return abs(p[0] - best_place[0]) + abs(p[1] - best_place[1]) >= 2

        esc_path = bfs_find(best_place, ctx.width, ctx.height, blocked, predicate=safe, max_expand=4000)
        if esc_path is None:
            return UnitPlan(path=best_path[:30], bombs=[best_place], debug="farm(no-esc)")

        full = (best_path + esc_path)[:30]
        if best_place not in full:
            return None

        return UnitPlan(path=full, bombs=[best_place], debug="farm")
