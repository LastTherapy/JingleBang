from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from strategies.base import Strategy

StrategyFactory = Callable[[], Strategy]


@dataclass
class StrategyRegistry:
    factories: dict[str, StrategyFactory]

    def list_ids(self) -> list[str]:
        return sorted(self.factories.keys())

    def create(self, strategy_id: str) -> Strategy:
        return self.factories[strategy_id]()
