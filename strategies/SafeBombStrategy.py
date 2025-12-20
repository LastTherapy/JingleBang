from __future__ import annotations

import hashlib
from collections import deque
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Set, Tuple

from model import Bomber, Pos, Mob
from strategies.base import Strategy, DecisionContext, UnitPlan
from services.danger import danger_from_bomb


def neighbors4(p: Pos) -> List[Pos]:
    x, y = p
    return [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]


def inside(p: Pos, w: int, h: int) -> bool:
    x, y = p
    return 0 <= x < w and 0 <= y < h


def manhattan(a: Pos, b: Pos) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


@dataclass
class SafeBombConfig:
    # НАШИ параметры
    my_bomb_range: int = 1
    my_bomb_timer: float = 8.0

    safe_margin: float = 0.2

    # поведение
    explore_horizon: int = 16
    ally_avoid: bool = True

    # мобы/призраки
    mob_avoid_dist: int = 1  # избегаем клеток с dist <= 1 до моба


class SafeBombStrategy(Strategy):
    def __init__(self, cfg: SafeBombConfig | None = None) -> None:
        self.cfg = cfg or SafeBombConfig()
        self._prev_pos: Optional[Pos] = None

        # НОВОЕ: “коммит” на отход после бомбы (убирает метание и самозапирание)
        self._escape_plan: deque[Pos] = deque()

    def decide_for_unit(self, unit: Bomber, ctx: DecisionContext) -> Optional[UnitPlan]:
        w, h = ctx.width, ctx.height

        walls = set(ctx.walls)
        obstacles = set(ctx.obstacles)
        bombs_cells = set(ctx.bombs.keys())
        blocked_static = walls | obstacles | bombs_cells

        allies = [b for b in ctx.state.bombers if b.alive and b.id != unit.id]
        ally_cells = {a.pos for a in allies}

        mobs = list(ctx.state.mobs or [])
        mob_kill_zone = self._mob_kill_zone(mobs, w, h, dist=self.cfg.mob_avoid_dist)

        # чем нельзя ходить в обычном режиме
        blocked_move = set(blocked_static) | mob_kill_zone
        if self.cfg.ally_avoid:
            blocked_move |= ally_cells

        # карта “когда клетка взорвётся” для УЖЕ существующих бомб (в т.ч. вражеских)
        min_explosion = self._min_explosion_map(ctx, walls, obstacles, (w, h))

        # A) если у нас есть план отхода — продолжаем
        if self._escape_plan:
            step = self._escape_plan[0]
            if self._is_step_valid(unit.pos, step, blocked_move, min_explosion, w, h):
                self._escape_plan.popleft()
                self._prev_pos = unit.pos
                return UnitPlan(path=[step], bombs=[], debug="follow escape plan")
            else:
                # план сломался — сбрасываем
                self._escape_plan.clear()

        # B) если рядом моб/призрак или мы попали в опасную клетку — уходим
        if unit.pos in mob_kill_zone or (not self._safe_to_stay(unit.pos, leave_time=1.0, min_explosion=min_explosion)):
            step = self._panic_step(unit, blocked_move, min_explosion, mobs, w, h)
            if step is not None:
                self._prev_pos = unit.pos
                return UnitPlan(path=[step], bombs=[], debug="panic evade")
            return None

        # C1) попытка: поставить бомбу так, чтобы ломать препятствия (максимум)
        if unit.bombs_available > 0:
            plan = self._try_bomb_obstacles(unit, ctx, blocked_static, ally_cells, mob_kill_zone, min_explosion)
            if plan is not None:
                self._prev_pos = unit.pos
                return plan

            # C2) попытка: бомба рядом с мобом (аккуратно)
            plan = self._try_bomb_mobs(unit, ctx, blocked_static, ally_cells, mob_kill_zone, min_explosion, mobs)
            if plan is not None:
                self._prev_pos = unit.pos
                return plan

        # D) идти к ближайшей “позиции постановки” рядом с препятствием (BFS, без хаоса)
        goals = self._bomb_positions_for_obstacles(obstacles, blocked_move, w, h)
        if goals:
            target = self._pick_goal_spread(goals, unit.id)
            path = self._bfs(unit.pos, {target}, blocked_move, w, h)
            if path:
                step = self._anti_pingpong(unit.pos, path[0], blocked_move, min_explosion, w, h)
                self._prev_pos = unit.pos
                return UnitPlan(path=[step], bombs=[], debug="go to obstacle bomb-pos")

        # E) разведка (с разнесением и анти-циклом)
        step = self._explore_step(unit, allies, blocked_move, min_explosion, w, h)
        if step is not None:
            self._prev_pos = unit.pos
            return UnitPlan(path=[step], bombs=[], debug="explore")

        return None

    # --------------------- bomb: obstacles ---------------------

    def _try_bomb_obstacles(
            self,
            unit: Bomber,
            ctx: DecisionContext,
            blocked_static: Set[Pos],
            ally_cells: Set[Pos],
            mob_kill_zone: Set[Pos],
            min_explosion_existing: Dict[Pos, float],
    ) -> Optional[UnitPlan]:
        w, h = ctx.width, ctx.height
        walls = set(ctx.walls)
        obstacles = set(ctx.obstacles)

        candidates: List[Tuple[int, Pos, List[Pos]]] = []
        for bomb_cell in neighbors4(unit.pos):
            if not inside(bomb_cell, w, h):
                continue
            if bomb_cell in blocked_static:
                continue
            if bomb_cell in mob_kill_zone:
                continue

            blast = danger_from_bomb(
                pos=bomb_cell,
                bomb_range=self.cfg.my_bomb_range,
                walls=walls,
                obstacles=obstacles,
                bombs_as_stoppers=set(ctx.bombs.keys()) | {bomb_cell},
                map_size=(w, h),
            )

            destroyed = len(blast & obstacles)
            if destroyed <= 0:
                continue

            # friendly-fire запрет по текущим позициям
            if blast & ally_cells:
                continue

            explode_at = 1.0 + self.cfg.my_bomb_timer
            min_explosion_new = dict(min_explosion_existing)
            for p in blast:
                min_explosion_new[p] = min(min_explosion_new.get(p, float("inf")), explode_at)

            # ВАЖНО: после постановки бомбы её клетка станет блоком.
            blocked_after = set(blocked_static) | {bomb_cell} | mob_kill_zone | ally_cells

            escape = self._time_bfs_first(
                start=bomb_cell,
                start_time=1,
                blocked=blocked_after,
                min_explosion=min_explosion_new,
                w=w, h=h,
                max_time=int(self.cfg.my_bomb_timer) + 6,
                goal_pred=lambda p, t: (p not in blast) and self._safe_to_stay(p, leave_time=explode_at + 0.5, min_explosion=min_explosion_new),
            )
            if not escape:
                continue

            candidates.append((destroyed, bomb_cell, escape))

        if not candidates:
            return None

        candidates.sort(key=lambda x: x[0], reverse=True)
        destroyed, bomb_cell, escape = candidates[0]

        # Коммитим отход: на следующих тиках будем шагать по escape
        self._escape_plan = deque(escape)

        # В этом тике: шаг в bomb_cell и сразу закладка
        return UnitPlan(path=[bomb_cell], bombs=[bomb_cell], debug=f"bomb obstacles={destroyed}")

    # --------------------- bomb: mobs/ghosts ---------------------

    def _try_bomb_mobs(
            self,
            unit: Bomber,
            ctx: DecisionContext,
            blocked_static: Set[Pos],
            ally_cells: Set[Pos],
            mob_kill_zone: Set[Pos],
            min_explosion_existing: Dict[Pos, float],
            mobs: List[Mob],
    ) -> Optional[UnitPlan]:
        if not mobs:
            return None

        w, h = ctx.width, ctx.height
        walls = set(ctx.walls)
        obstacles = set(ctx.obstacles)

        # выбираем “ближайшего опасного”
        mobs_sorted = sorted(mobs, key=lambda m: manhattan(unit.pos, m.pos))
        for mob in mobs_sorted[:3]:
            # Ставим бомбу так, чтобы blast накрыл mob.pos.
            # При range=1 это означает: бомба в соседней клетке от mob.pos.
            for bomb_cell in neighbors4(mob.pos):
                if not inside(bomb_cell, w, h):
                    continue
                if bomb_cell in blocked_static:
                    continue
                if bomb_cell in ally_cells:
                    continue

                # Мы должны прийти в bomb_cell из соседней клетки (unit.pos) одним шагом, т.е. bomb_cell соседняя к unit.pos
                if manhattan(unit.pos, bomb_cell) != 1:
                    continue

                blast = danger_from_bomb(
                    pos=bomb_cell,
                    bomb_range=self.cfg.my_bomb_range,
                    walls=walls,
                    obstacles=obstacles,
                    bombs_as_stoppers=set(ctx.bombs.keys()) | {bomb_cell},
                    map_size=(w, h),
                )
                if mob.pos not in blast:
                    continue

                if blast & ally_cells:
                    continue

                explode_at = 1.0 + self.cfg.my_bomb_timer
                min_explosion_new = dict(min_explosion_existing)
                for p in blast:
                    min_explosion_new[p] = min(min_explosion_new.get(p, float("inf")), explode_at)

                blocked_after = set(blocked_static) | {bomb_cell} | ally_cells
                # После постановки хотим быстро увеличить дистанцию до mob (не стоять рядом)
                escape = self._time_bfs_first(
                    start=bomb_cell,
                    start_time=1,
                    blocked=blocked_after,
                    min_explosion=min_explosion_new,
                    w=w, h=h,
                    max_time=int(self.cfg.my_bomb_timer) + 6,
                    goal_pred=lambda p, t: (p not in blast)
                                           and (manhattan(p, mob.pos) >= 2)
                                           and self._safe_to_stay(p, leave_time=explode_at + 0.5, min_explosion=min_explosion_new),
                )
                if not escape:
                    continue

                self._escape_plan = deque(escape)
                return UnitPlan(path=[bomb_cell], bombs=[bomb_cell], debug=f"bomb mob={mob.type}")

        return None

    # --------------------- goals & movement ---------------------

    def _bomb_positions_for_obstacles(self, obstacles: Set[Pos], blocked: Set[Pos], w: int, h: int) -> Set[Pos]:
        goals: Set[Pos] = set()
        for ob in obstacles:
            for nb in neighbors4(ob):
                if inside(nb, w, h) and nb not in blocked:
                    goals.add(nb)
        return goals

    def _pick_goal_spread(self, goals: Set[Pos], unit_id: str) -> Pos:
        # детерминированный выбор цели из множества ближайших: чтобы разные бомберы чаще брали разные
        g = sorted(goals)
        idx = int(hashlib.md5(unit_id.encode("utf-8")).hexdigest(), 16) % len(g)
        return g[idx]

    def _explore_step(
            self,
            unit: Bomber,
            allies: List[Bomber],
            blocked: Set[Pos],
            min_explosion: Dict[Pos, float],
            w: int,
            h: int,
    ) -> Optional[Pos]:
        ally_pos = [a.pos for a in allies]

        candidates: List[Pos] = []
        for nb in neighbors4(unit.pos):
            if not inside(nb, w, h):
                continue
            if nb in blocked:
                continue
            if not self._safe_to_stay(nb, leave_time=2.0, min_explosion=min_explosion):
                continue
            candidates.append(nb)

        if not candidates:
            return None

        def score(p: Pos) -> float:
            spread = min((manhattan(p, ap) for ap in ally_pos), default=5)
            back_pen = 1000 if (self._prev_pos is not None and p == self._prev_pos) else 0
            return spread * 10 - back_pen

        best = max(candidates, key=score)
        return self._anti_pingpong(unit.pos, best, blocked, min_explosion, w, h)

    # --------------------- safety / bombs map ---------------------

    def _min_explosion_map(self, ctx: DecisionContext, walls: Set[Pos], obstacles: Set[Pos], map_size: Tuple[int, int]) -> Dict[Pos, float]:
        out: Dict[Pos, float] = {}
        stoppers = set(ctx.bombs.keys())
        for p, (rng, timer) in ctx.bombs.items():
            blast = danger_from_bomb(
                pos=p,
                bomb_range=int(rng),
                walls=walls,
                obstacles=obstacles,
                bombs_as_stoppers=stoppers,
                map_size=map_size,
            )
            for cell in blast:
                out[cell] = min(out.get(cell, float("inf")), float(timer))
        return out

    def _safe_to_stay(self, pos: Pos, leave_time: float, min_explosion: Dict[Pos, float]) -> bool:
        t = min_explosion.get(pos)
        if t is None:
            return True
        return t > (leave_time + self.cfg.safe_margin)

    # --------------------- mobs ---------------------

    def _mob_kill_zone(self, mobs: List[Mob], w: int, h: int, dist: int) -> Set[Pos]:
        if dist <= 0 or not mobs:
            return set()
        zone: Set[Pos] = set()
        for m in mobs:
            zone.add(m.pos)
            if dist >= 1:
                for nb in neighbors4(m.pos):
                    if inside(nb, w, h):
                        zone.add(nb)
        return zone

    # --------------------- panic ---------------------

    def _panic_step(
            self,
            unit: Bomber,
            blocked: Set[Pos],
            min_explosion: Dict[Pos, float],
            mobs: List[Mob],
            w: int,
            h: int,
    ) -> Optional[Pos]:
        # выбираем соседнюю клетку с максимальной дистанцией до ближайшего моба и безопасную по бомбам
        mob_pos = [m.pos for m in mobs]
        best: Optional[Pos] = None
        best_sc = float("-inf")

        for nb in neighbors4(unit.pos):
            if not inside(nb, w, h):
                continue
            if nb in blocked:
                continue
            if not self._safe_to_stay(nb, leave_time=2.0, min_explosion=min_explosion):
                continue
            d = min((manhattan(nb, mp) for mp in mob_pos), default=10)
            back = 1000 if (self._prev_pos is not None and nb == self._prev_pos) else 0
            sc = d * 10 - back
            if sc > best_sc:
                best_sc = sc
                best = nb

        return best

    # --------------------- BFS time-aware ---------------------

    def _time_bfs_first(
            self,
            start: Pos,
            start_time: int,
            blocked: Set[Pos],
            min_explosion: Dict[Pos, float],
            w: int,
            h: int,
            max_time: int,
            goal_pred: Callable[[Pos, int], bool],
    ) -> Optional[List[Pos]]:
        q = deque([(start, start_time)])
        prev: Dict[Tuple[Pos, int], Tuple[Pos, int]] = {}
        seen = {(start, start_time)}

        def ok(p: Pos, t: int) -> bool:
            return self._safe_to_stay(p, leave_time=float(t + 1), min_explosion=min_explosion)

        while q:
            cur, t = q.popleft()
            if t > start_time + max_time:
                continue

            if t > start_time and goal_pred(cur, t):
                return self._reconstruct(prev, (cur, t), start, start_time)

            for nx in neighbors4(cur):
                nt = t + 1
                if nt > start_time + max_time:
                    continue
                if not inside(nx, w, h):
                    continue
                if nx in blocked:
                    continue
                if not ok(nx, nt):
                    continue
                key = (nx, nt)
                if key in seen:
                    continue
                seen.add(key)
                prev[key] = (cur, t)
                q.append((nx, nt))

        return None

    def _reconstruct(
            self,
            prev: Dict[Tuple[Pos, int], Tuple[Pos, int]],
            end: Tuple[Pos, int],
            start: Pos,
            start_time: int,
    ) -> List[Pos]:
        cur = end
        out: List[Pos] = []
        while cur != (start, start_time):
            out.append(cur[0])
            cur = prev[cur]
        out.reverse()
        return out

    def _bfs(self, start: Pos, goals: Set[Pos], blocked: Set[Pos], w: int, h: int) -> Optional[List[Pos]]:
        if not goals:
            return None
        q = deque([start])
        prev: Dict[Pos, Pos] = {}
        seen = {start}

        while q:
            cur = q.popleft()
            if cur in goals and cur != start:
                path_rev = [cur]
                while path_rev[-1] != start:
                    path_rev.append(prev[path_rev[-1]])
                path = list(reversed(path_rev))
                return path[1:]

            for nb in neighbors4(cur):
                if not inside(nb, w, h):
                    continue
                if nb in blocked:
                    continue
                if nb in seen:
                    continue
                seen.add(nb)
                prev[nb] = cur
                q.append(nb)
        return None

    # --------------------- misc ---------------------

    def _anti_pingpong(self, cur: Pos, step: Pos, blocked: Set[Pos], min_explosion: Dict[Pos, float], w: int, h: int) -> Pos:
        if self._prev_pos is None or step != self._prev_pos:
            return step
        # если пытаемся сделать шаг назад — берём лучший альтернативный
        alts: List[Pos] = []
        for nb in neighbors4(cur):
            if not inside(nb, w, h):
                continue
            if nb in blocked:
                continue
            if nb == self._prev_pos:
                continue
            if not self._safe_to_stay(nb, leave_time=2.0, min_explosion=min_explosion):
                continue
            alts.append(nb)
        if not alts:
            return step
        # просто берём первый (можно усложнить скоринг)
        return alts[0]

    def _is_step_valid(self, cur: Pos, step: Pos, blocked: Set[Pos], min_explosion: Dict[Pos, float], w: int, h: int) -> bool:
        return (
                inside(step, w, h)
                and step not in blocked
                and manhattan(cur, step) == 1
                and self._safe_to_stay(step, leave_time=2.0, min_explosion=min_explosion)
        )
