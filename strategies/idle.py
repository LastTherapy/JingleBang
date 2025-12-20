from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from strategies.base import Strategy, DecisionContext, UnitPlan
from model import Bomber


@dataclass
class IdleStrategy:
    id: str = "idle"

    def decide_for_unit(self, unit: Bomber, ctx: DecisionContext) -> Optional[UnitPlan]:
        return None
