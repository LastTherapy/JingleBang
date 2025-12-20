from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from model import GameState, MoveCommand, Pos, Bomber, BoosterState
from strategies.base import DecisionContext, UnitPlan, Strategy
from services.danger import build_danger
from app.registry import StrategyRegistry
from app.assignments import AssignmentStore


@dataclass
class EngineConfig:
    max_path: int = 30
    danger_timer: float = 2.5


class DecisionEngine:
    def __init__(self, registry: StrategyRegistry, assignments: AssignmentStore, cfg: EngineConfig) -> None:
        self.registry = registry
        self.assignments = assignments
        self.cfg = cfg
        self._instances: dict[tuple[str, str], Strategy] = {}

    def decide(self, state: GameState, booster: BoosterState) -> list[MoveCommand]:
        walls = set(state.arena.walls)
        obstacles = set(state.arena.obstacles)
        bombs = {b.pos: (b.range, b.timer) for b in state.arena.bombs}

        danger = build_danger(
            bombs=bombs,
            timer_threshold=self.cfg.danger_timer,
            walls=walls,
            obstacles=obstacles,
        )

        mob_positions = {m.pos for m in state.mobs if int(m.safe_time) <= 0}
        enemy_positions = {e.pos for e in state.enemies if int(e.safe_time) <= 0}

        ctx = DecisionContext(
            state=state,
            booster=booster,
            width=state.map_size[0],
            height=state.map_size[1],
            walls=walls,
            obstacles=obstacles,
            bombs=bombs,
            danger=danger,
            mob_positions=mob_positions,
            enemy_positions=enemy_positions,
        )

        cmds: list[MoveCommand] = []
        for unit in state.bombers:
            if not unit.alive:
                continue
            if not unit.can_move:
                continue

            strategy_id = self.assignments.get_for(unit.id)
            plan = self._decide_one(unit, strategy_id, ctx)
            if plan is None:
                continue

            plan = self._validate_and_clip(unit, plan, ctx)
            if plan is None:
                continue

            cmds.append(MoveCommand(bomber_id=unit.id, path=plan.path, bombs=plan.bombs))

        return cmds

    def _decide_one(self, unit: Bomber, strategy_id: str, ctx: DecisionContext) -> Optional[UnitPlan]:
        key = (unit.id, strategy_id)
        strat = self._instances.get(key)
        if strat is None:
            strat = self.registry.create(strategy_id)
            self._instances[key] = strat
        return strat.decide_for_unit(unit, ctx)

    def _validate_and_clip(self, unit: Bomber, plan: UnitPlan, ctx: DecisionContext) -> Optional[UnitPlan]:
        path = plan.path[: self.cfg.max_path]
        bombs = plan.bombs or []

        # bombs должны быть в path
        path_set = set(path)
        bombs = [b for b in bombs if b in path_set]

        # не больше доступных бомб
        if len(bombs) > unit.bombs_available:
            bombs = bombs[: unit.bombs_available]

        # blocked учитывает boosters passability
        blocked = set()
        if not ctx.booster.can_pass_walls:
            blocked |= ctx.walls
        if not ctx.booster.can_pass_obstacles:
            blocked |= ctx.obstacles
        if not ctx.booster.can_pass_bombs:
            blocked |= set(ctx.bombs.keys())

        safe_path: list[Pos] = []
        cur = unit.pos
        for step in path:
            # только 4-way
            if abs(step[0] - cur[0]) + abs(step[1] - cur[1]) != 1:
                break
            if step in blocked:
                break
            safe_path.append(step)
            cur = step

        if not safe_path:
            return None

        safe_set = set(safe_path)
        bombs = [b for b in bombs if b in safe_set]

        return UnitPlan(path=safe_path, bombs=bombs, debug=plan.debug)
