from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from model import GameState, MoveCommand, Pos, Bomber
from strategies.base import DecisionContext, UnitPlan, Strategy
from services.danger import build_danger, danger_from_bomb
from app.registry import StrategyRegistry
from app.assignments import AssignmentStore


@dataclass(frozen=True)
class EngineConfig:
    max_path: int = 30
    danger_timer: float = 2.5

    # НАШИ параметры (пока сервер не отдаёт “конфиг” отдельно)
    my_bomb_range: int = 1
    my_bomb_timer: float = 8.0


class DecisionEngine:
    def __init__(self, registry: StrategyRegistry, assignments: AssignmentStore, cfg: EngineConfig) -> None:
        self.registry = registry
        self.assignments = assignments
        self.cfg = cfg
        self._instances: dict[tuple[str, str], Strategy] = {}

    def decide(self, state: GameState) -> list[MoveCommand]:
        walls = set(state.arena.walls)
        obstacles = set(state.arena.obstacles)
        bombs = {b.pos: (b.range, b.timer) for b in state.arena.bombs}

        danger = build_danger(
            bombs=bombs,
            timer_threshold=self.cfg.danger_timer,
            walls=walls,
            obstacles=obstacles,
            map_size=state.map_size,
        )

        ctx = DecisionContext(
            state=state,
            width=state.map_size[0],
            height=state.map_size[1],
            walls=walls,
            obstacles=obstacles,
            bombs=bombs,
            danger=danger,
        )

        units = [u for u in state.bombers if u.alive and u.can_move]
        units.sort(key=lambda u: u.id)

        occupied_now = {u.pos for u in units}
        reserved_next: set[Pos] = set()

        # НОВОЕ: чтобы союзники не шагали в blast-zone бомбы,
        # которую мы ставим “прямо сейчас” (в этом же тике).
        reserved_blast: set[Pos] = set()

        cmds: list[MoveCommand] = []
        for unit in units:
            strategy_id = self.assignments.get_for(unit.id)
            plan = self._decide_one(unit, strategy_id, ctx)
            if plan is None:
                continue

            plan = self._validate_and_clip(unit, plan, ctx)
            if plan is None:
                continue

            must_step: Optional[Pos] = plan.bombs[0] if plan.bombs else None
            chosen_step: Optional[Pos] = None

            def can_take(step: Pos) -> bool:
                if step in reserved_next:
                    return False
                if step in occupied_now and step != unit.pos:
                    return False
                if step in reserved_blast:
                    return False
                return True

            if must_step is not None:
                if not can_take(must_step):
                    continue
                chosen_step = must_step
            else:
                for step in plan.path:
                    if can_take(step):
                        chosen_step = step
                        break

            if chosen_step is None:
                continue

            final_path = [chosen_step]
            final_bombs = [b for b in (plan.bombs or []) if b == chosen_step]

            reserved_next.add(chosen_step)
            occupied_now.add(chosen_step)

            # Если ставим бомбу — сразу резервируем её будущую blast-зону
            if final_bombs:
                blast = danger_from_bomb(
                    pos=chosen_step,
                    bomb_range=self.cfg.my_bomb_range,
                    walls=walls,
                    obstacles=obstacles,
                    bombs_as_stoppers=set(ctx.bombs.keys()) | {chosen_step},
                    map_size=state.map_size,
                )
                reserved_blast |= blast

            cmds.append(MoveCommand(bomber_id=unit.id, path=final_path, bombs=final_bombs))

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
        bombs = list(plan.bombs or [])

        path_set = set(path)
        bombs = [b for b in bombs if b in path_set]

        if len(bombs) > unit.bombs_available:
            bombs = bombs[: unit.bombs_available]

        blocked = ctx.walls | ctx.obstacles | set(ctx.bombs.keys())

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
        bombs = [b for b in bombs if b in safe_set]

        # ход 1 шаг/тик: бомба должна быть на первом шаге
        if bombs and bombs[0] != safe_path[0]:
            bombs = []

        return UnitPlan(path=safe_path, bombs=bombs, debug=plan.debug)
