from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from model import Bomber
from strategies.base import DecisionContext, Strategy, UnitPlan


@dataclass
class IdleStrategy:
    id: str = "idle"

    def decide_for_unit(self, unit: Bomber, ctx: DecisionContext) -> Optional[UnitPlan]:
        return None
