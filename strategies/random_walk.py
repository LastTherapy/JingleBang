from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Optional

from model import Bomber, Pos
from services.nav import neighbors4, inside
from strategies.base import DecisionContext, Strategy, UnitPlan


@dataclass
class RandomWalkStrategy:
    id: str = "random_walk"

    def decide_for_unit(self, unit: Bomber, ctx: DecisionContext) -> Optional[UnitPlan]:
        blocked = ctx.walls | ctx.obstacles | ctx.bomb_cells
        options = [p for p in neighbors4(unit.pos) if inside(p, ctx.width, ctx.height) and p not in blocked]
        if not options:
            return None
        return UnitPlan(path=[random.choice(options)], bombs=[], debug="rnd")
