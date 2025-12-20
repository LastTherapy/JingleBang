from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from model import Bomber, Pos, Mob
from strategies.base import DecisionContext, Strategy, UnitPlan
from services.nav import neighbors4, bfs_path, bfs_find
from services.danger import blast_cross, can_hit_target_in_cross


def manhattan(a: Pos, b: Pos) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


@dataclass
class EvadeAndBombMobsStrategy:
    """
    1) Если моб близко — уйти так, чтобы не пересечься с ним.
    2) Если есть возможность — поставить бомбу так, чтобы текущая позиция моба попадала в крест,
       и сразу уйти из зоны взрыва.
    Важно: мы не предсказываем движение моба (оно зависит от типа), поэтому бомбим “по месту”.
    """
    id: str = "evade_bomb_mobs"
    threat_dist: int = 2  # если моб в <=2 клетках — считаем угрозой

    def decide_for_unit(self, unit: Bomber, ctx: DecisionContext) -> Optional[UnitPlan]:
        awake_mobs = [m for m in ctx.state.mobs if int(m.safe_time) <= 0]
        if not awake_mobs:
            return None

        blocked = _blocked_cells(ctx)

        # 0) если прямо сейчас стоим на мобе — это уже беда, но попробуем сделать шаг
        if unit.pos in {m.pos for m in awake_mobs}:
            step = self._best_step_away(unit.pos, awake_mobs, ctx, blocked)
            return UnitPlan(path=[step] if step else [], bombs=[], debug="panic-on-mob") if step else None

        nearest = min(awake_mobs, key=lambda m: manhattan(unit.pos, m.pos))
        dist = manhattan(unit.pos, nearest.pos)

        # 1) попытка “быстрого убийства” — если можем поставить бомбу и безопасно отойти
        if unit.bombs_available > 0:
            plan = self._try_bomb_nearest(unit, nearest, ctx, blocked)
            if plan is not None:
                return plan

        # 2) если угроза — уходим
        if dist <= self.threat_dist:
            esc = self._escape_plan(unit, awake_mobs, ctx, blocked)
            if esc is not None:
                return esc

        return None

    def _try_bomb_nearest(self, unit: Bomber, mob: Mob, ctx: DecisionContext, blocked: set[Pos]) -> Optional[UnitPlan]:
        bomb_range = max(1, int(ctx.booster.bomb_range))
        bombs_now = set(ctx.bombs.keys())

        # кандидаты: клетка = текущая или клетки в радиусе 5 шагов, откуда можно “попасть” моба крестом
        candidate_cells: list[Pos] = [unit.pos] + [p for p in neighbors4(unit.pos)]
        # расширим candidates ещё на несколько клеток: ищем ближайшую “позицию выстрела” BFS-ом
        # (без фанатизма — 10 клеток глубины)
        def is_fire_pos(p: Pos) -> bool:
            if p in blocked:
                return False
            return can_hit_target_in_cross(p, mob.pos, bomb_range, ctx.walls, ctx.obstacles, bombs_now)

        fire_path = bfs_find(unit.pos, ctx.width, ctx.height, blocked, predicate=is_fire_pos, max_expand=1500)
        if fire_path is not None:
            fire_pos = unit.pos if len(fire_path) == 0 else fire_path[-1]
        else:
            # fallback: проверим локально
            fire_pos = None
            for p in candidate_cells:
                if p in blocked:
                    continue
                if can_hit_target_in_cross(p, mob.pos, bomb_range, ctx.walls, ctx.obstacles, bombs_now):
                    fire_pos = p
                    break
            if fire_pos is None:
                return None

        # путь до fire_pos
        to_fire = bfs_path(unit.pos, fire_pos, ctx.width, ctx.height, blocked, max_len=30)
        if to_fire is None:
            return None
        path_prefix = to_fire[:]

        # зона взрыва будущей бомбы
        future_blast = blast_cross(fire_pos, bomb_range, ctx.walls, ctx.obstacles, bombs_now | {fire_pos})
        forbidden = set(blocked) | set(ctx.danger) | future_blast | ctx.mob_positions

        # отойти: найдём ближайшую клетку, которая не в forbidden
        escape_path = bfs_find(fire_pos, ctx.width, ctx.height, blocked, predicate=lambda p: p not in forbidden, max_expand=3000)
        if escape_path is None:
            return None

        full_path = (path_prefix + escape_path)[:30]
        if fire_pos not in full_path:
            # если fire_pos == unit.pos и path_prefix пуст — ok
            if fire_pos != unit.pos:
                return None

        return UnitPlan(path=full_path, bombs=[fire_pos], debug=f"bomb_mob mob={mob.id} type={mob.type} at={mob.pos} place={fire_pos}")

    def _escape_plan(self, unit: Bomber, mobs: list[Mob], ctx: DecisionContext, blocked: set[Pos]) -> Optional[UnitPlan]:
        mob_positions = {m.pos for m in mobs}

        # ищем ближайшую клетку, где дистанция до всех мобов >= threat_dist+1
        def safe(p: Pos) -> bool:
            if p in mob_positions:
                return False
            # минимальная дистанция
            md = min(manhattan(p, m.pos) for m in mobs)
            return md >= (self.threat_dist + 1) and p not in ctx.danger

        path = bfs_find(unit.pos, ctx.width, ctx.height, blocked, predicate=safe, max_expand=4000)
        if path is None:
            # fallback: один шаг “в сторону”
            step = self._best_step_away(unit.pos, mobs, ctx, blocked)
            return UnitPlan(path=[step], bombs=[], debug="escape-1step") if step else None

        return UnitPlan(path=path[:30], bombs=[], debug="escape")

    def _best_step_away(self, pos: Pos, mobs: list[Mob], ctx: DecisionContext, blocked: set[Pos]) -> Optional[Pos]:
        best = None
        best_score = -10**9
        for nb in neighbors4(pos):
            if nb in blocked:
                continue
            if not (0 <= nb[0] < ctx.width and 0 <= nb[1] < ctx.height):
                continue
            if nb in ctx.danger:
                continue
            # score = как можно дальше от ближайшего моба
            md = min(manhattan(nb, m.pos) for m in mobs)
            score = md
            if nb in ctx.mob_positions:
                score -= 1000
            if score > best_score:
                best_score = score
                best = nb
        return best


def _blocked_cells(ctx: DecisionContext) -> set[Pos]:
    blocked = set()
    if not ctx.booster.can_pass_walls:
        blocked |= ctx.walls
    if not ctx.booster.can_pass_obstacles:
        blocked |= ctx.obstacles
    if not ctx.booster.can_pass_bombs:
        blocked |= set(ctx.bombs.keys())
    return blocked
