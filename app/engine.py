from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.assignments import AssignmentStore
from app.registry import StrategyRegistry
from model import Bomber, GameState, MoveCommand, Pos
from strategies.base import DecisionContext, Strategy, UnitPlan


@dataclass
class EngineConfig:
    max_path: int = 30


class DecisionEngine:
    def __init__(self, registry: StrategyRegistry, assignments: AssignmentStore, cfg: EngineConfig) -> None:
        self.registry = registry
        self.assignments = assignments
        self.cfg = cfg
        self._instances: dict[tuple[str, str], Strategy] = {}  # (bomber_id, strategy_id) -> instance

    def decide(self, state: GameState) -> list[MoveCommand]:
        walls = set(state.arena.walls)
        obstacles = set(state.arena.obstacles)
        bomb_cells = {b.pos for b in state.arena.bombs}
        mob_cells = {m.pos for m in state.mobs if int(m.safe_time) <= 0}

        ctx = DecisionContext(
            state=state,
            width=state.map_size[0],
            height=state.map_size[1],
            walls=walls,
            obstacles=obstacles,
            bomb_cells=bomb_cells,
            mob_cells=mob_cells,
        )

        cmds: list[MoveCommand] = []
        for b in state.bombers:
            if not b.alive or not b.can_move:
                continue

            sid = self.assignments.get_for(b.id)
            if sid not in self.registry.factories:
                sid = self.assignments.get_default()

            plan = self._decide_one(b, sid, ctx)
            if plan is None:
                continue

            plan = self._validate_and_clip(b, plan, ctx)
            if plan is None:
                continue

            cmds.append(MoveCommand(bomber_id=b.id, path=plan.path, bombs=plan.bombs))
        return cmds

    def _decide_one(self, unit: Bomber, strategy_id: str, ctx: DecisionContext) -> Optional[UnitPlan]:
        key = (unit.id, strategy_id)
        strat = self._instances.get(key)
        if strat is None:
            strat = self.registry.create(strategy_id)
            self._instances[key] = strat
        return strat.decide_for_unit(unit, ctx)

    def _validate_and_clip(self, unit: Bomber, plan: UnitPlan, ctx: DecisionContext) -> Optional[UnitPlan]:
        path = (plan.path or [])[: self.cfg.max_path]
        bombs = plan.bombs or []

        # bombs must be inside path
        path_set = set(path)
        bombs = [p for p in bombs if p in path_set]

        # bombs <= available
        if len(bombs) > unit.bombs_available:
            bombs = bombs[: unit.bombs_available]

        # Validate 4-neighborhood and blocked cells
        blocked = ctx.walls | ctx.obstacles | ctx.bomb_cells
        safe_path: list[Pos] = []
        cur = unit.pos
        for step in path:
            if abs(step[0] - cur[0]) + abs(step[1] - cur[1]) != 1:
                break
            if step in blocked:
                break
            safe_path.append(step)
            cur = step

        if not safe_path:
            return None

        safe_set = set(safe_path)
        bombs = [p for p in bombs if p in safe_set]
        return UnitPlan(path=safe_path, bombs=bombs, debug=plan.debug)
