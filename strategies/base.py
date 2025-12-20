from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol

from model import GameState, Bomber, Pos


@dataclass(frozen=True)
class UnitPlan:
    path: list[Pos]
    bombs: list[Pos]
    debug: str = ""


@dataclass(frozen=True)
class DecisionContext:
    state: GameState
    width: int
    height: int
    walls: set[Pos]
    obstacles: set[Pos]
    bombs: dict[Pos, tuple[int, float]]  # pos -> (range, timer)
    danger: set[Pos]


class Strategy(Protocol):
    id: str

    def decide_for_unit(self, unit: Bomber, ctx: DecisionContext) -> Optional[UnitPlan]:
        ...
