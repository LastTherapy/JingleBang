from __future__ import annotations

from dataclasses import dataclass
from collections import deque
from typing import Callable, Dict, Iterable, Optional, Tuple, List

from model import Bomber, Pos
from strategies.base import Strategy, DecisionContext, UnitPlan

from services.danger import danger_from_bomb


def neighbors4(p: Pos) -> List[Pos]:
    x, y = p
    return [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]


def inside(p: Pos, w: int, h: int) -> bool:
    x, y = p
    return 0 <= x < w and 0 <= y < h


@dataclass
class SafeBombConfig:
    bomb_timer: float = 3.0      # таймер "нашей" бомбы (сек)
    bomb_range: int = 3          # радиус "нашей" бомбы
    safe_margin: float = 0.15    # запас по времени (сек) чтобы не ходить "впритык"
    max_plan_len: int = 30       # лимит API


class SafeBombStrategy(Strategy):
    """
    Стратегия "безопасная бомба":
    - не ставит бомбу, если она накроет союзника (по текущим позициям)
    - ставит бомбу только если есть гарантированный уход по таймеру
    - не входит в зону взрыва бомб, если не успевает покинуть её до взрыва
    """

    def __init__(self, cfg: SafeBombConfig | None = None) -> None:
        self.cfg = cfg or SafeBombConfig()

    # -------------------- публичный метод стратегии --------------------

    def decide_for_unit(self, unit: Bomber, ctx: DecisionContext) -> Optional[UnitPlan]:
        w, h = ctx.width, ctx.height
        blocked = set(ctx.walls) | set(ctx.obstacles) | set(ctx.bombs.keys())

        # precompute: для каждой клетки -> минимальное (самое раннее) время взрыва среди бомб, которые её накрывают
        min_explosion = self._min_explosion_map(
            bombs=list(ctx.bombs.items()),  # (pos -> (range, timer))
            walls=set(ctx.walls),
            obstacles=set(ctx.obstacles),
            map_size=(w, h),
        )

        # 1) Если текущая позиция не переживает ближайшую секунду — срочно эвакуируемся
        if not self._safe_to_stay(unit.pos, leave_time=1.0, min_explosion=min_explosion):
            esc = self._escape_plan(
                start=unit.pos,
                start_time=0,
                blocked=blocked,
                min_explosion=min_explosion,
                w=w,
                h=h,
                goal_pred=lambda p, t: self._is_stably_safe(p, t, min_explosion),
                max_time=10,  # сек-горизонт поиска эвакуации
            )
            if esc:
                return UnitPlan(path=esc, bombs=[], debug="escape: start unsafe")
            return None

        # 2) Пытаемся поставить безопасную бомбу (если есть)
        if unit.bombs_available > 0:
            plan = self._try_bomb_then_escape(unit, ctx, blocked, min_explosion)
            if plan:
                return plan

        # 3) Если рядом опасно (в danger по конфигу движка) — отходим в "стабильно безопасную" клетку
        if unit.pos in ctx.danger:
            esc = self._escape_plan(
                start=unit.pos,
                start_time=0,
                blocked=blocked,
                min_explosion=min_explosion,
                w=w,
                h=h,
                goal_pred=lambda p, t: self._is_stably_safe(p, t, min_explosion),
                max_time=10,
            )
            if esc:
                return UnitPlan(path=esc, bombs=[], debug="escape: ctx.danger")

        # 4) Иначе — ничего не делаем (пусть другие стратегии/назначения рулят)
        return None

    # -------------------- логика бомбы --------------------

    def _try_bomb_then_escape(
            self,
            unit: Bomber,
            ctx: DecisionContext,
            blocked: set[Pos],
            min_explosion_existing: Dict[Pos, float],
    ) -> Optional[UnitPlan]:
        w, h = ctx.width, ctx.height
        allies = [b for b in ctx.state.bombers if b.alive and b.id != unit.id]

        # Куда можно сделать первый шаг (в твоём engine бомба должна быть в path, поэтому кладём бомбу на первую клетку path)
        candidates = []
        for nb in neighbors4(unit.pos):
            if not inside(nb, w, h):
                continue
            if nb in blocked:
                continue
            # клетка nb должна быть "проходима по времени" (после шага туда мы должны прожить хотя бы следующую секунду)
            # после 1 шага мы оказываемся там на t=1 и проживаем до t=2
            if not self._safe_to_stay(nb, leave_time=2.0, min_explosion=min_explosion_existing):
                continue
            candidates.append(nb)

        # Немного приоритета: сначала те, что реально "имеют смысл бомбить"
        candidates.sort(key=lambda p: 0 if self._has_bomb_value(p, ctx) else 1)

        for bomb_cell in candidates:
            if not self._has_bomb_value(bomb_cell, ctx):
                continue

            # зона взрыва нашей потенциальной бомбы
            blast = danger_from_bomb(
                pos=bomb_cell,
                bomb_range=self.cfg.bomb_range,
                walls=set(ctx.walls),
                obstacles=set(ctx.obstacles),
                bombs_as_stoppers=set(ctx.bombs.keys()) | {bomb_cell},
                map_size=(w, h),
            )

            # не вредим союзникам: если хоть один союзник СЕЙЧАС в blast — не ставим
            if any(a.pos in blast for a in allies):
                continue

            # добавляем "нашу" бомбу как будущий взрыв в абсолютном времени:
            # мы придём на bomb_cell на t=1 и поставим бомбу => взрыв в t=1 + bomb_timer
            new_explosion_time = 1.0 + self.cfg.bomb_timer
            min_explosion = dict(min_explosion_existing)
            for p in blast:
                min_explosion[p] = min(min_explosion.get(p, float("inf")), new_explosion_time)

            # После постановки бомбы клетка bomb_cell станет занятой бомбой: назад на неё заходить нельзя
            blocked_after = set(blocked) | {bomb_cell}

            # Нам нужен путь-эвакуация от bomb_cell (мы на ней в t=1) до клетки вне blast,
            # причём по таймеру мы должны успеть выйти
            escape = self._escape_plan(
                start=bomb_cell,
                start_time=1,
                blocked=blocked_after,
                min_explosion=min_explosion,
                w=w,
                h=h,
                goal_pred=lambda p, t: (p not in blast) and self._is_stably_safe(p, t, min_explosion),
                max_time=int(self.cfg.bomb_timer) + 3,  # небольшой запас по времени
            )

            if not escape:
                continue

            # итоговый план: 1) шаг на bomb_cell, 2) ставим бомбу там, 3) уходим по escape
            path = [bomb_cell] + escape  # escape уже без стартовой клетки bomb_cell
            path = path[: self.cfg.max_plan_len]
            return UnitPlan(path=path, bombs=[bomb_cell], debug="bomb+escape safe")

        return None

    def _has_bomb_value(self, bomb_cell: Pos, ctx: DecisionContext) -> bool:
        """Есть ли смысл ставить бомбу: она заденет моба/врага/препятствие."""
        w, h = ctx.width, ctx.height
        blast = danger_from_bomb(
            pos=bomb_cell,
            bomb_range=self.cfg.bomb_range,
            walls=set(ctx.walls),
            obstacles=set(ctx.obstacles),
            bombs_as_stoppers=set(ctx.bombs.keys()) | {bomb_cell},
            map_size=(w, h),
        )

        targets = set(ctx.state.arena.obstacles)
        targets |= {m.pos for m in ctx.state.mobs}
        targets |= {e.pos for e in ctx.state.enemies}

        return any(t in blast for t in targets)

    # -------------------- время/опасность --------------------

    def _safe_to_stay(self, pos: Pos, leave_time: float, min_explosion: Dict[Pos, float]) -> bool:
        """
        pos безопасна, если ближайший взрыв, который накрывает pos, происходит строго позже leave_time.
        leave_time = момент, когда мы гарантированно покидаем клетку.
        """
        t = min_explosion.get(pos)
        if t is None:
            return True
        return t > (leave_time + self.cfg.safe_margin)

    def _is_stably_safe(self, pos: Pos, current_time: int, min_explosion: Dict[Pos, float]) -> bool:
        """
        "Стабильно безопасно" — ближайший взрыв по этой клетке не скоро.
        current_time = целое время (сек) после current_time шагов.
        """
        t = min_explosion.get(pos, float("inf"))
        return t > (float(current_time) + 2.0)  # 2 секунды запаса

    def _min_explosion_map(
            self,
            bombs: List[Tuple[Pos, Tuple[int, float]]],  # [(pos, (range, timer))]
            walls: set[Pos],
            obstacles: set[Pos],
            map_size: Tuple[int, int],
    ) -> Dict[Pos, float]:
        out: Dict[Pos, float] = {}
        stoppers = {p for p, _ in bombs}
        for p, (rng, timer) in bombs:
            blast = danger_from_bomb(
                pos=p,
                bomb_range=rng,
                walls=walls,
                obstacles=obstacles,
                bombs_as_stoppers=stoppers,
                map_size=map_size,
            )
            for cell in blast:
                out[cell] = min(out.get(cell, float("inf")), float(timer))
        return out

    # -------------------- time-aware BFS --------------------

    def _escape_plan(
            self,
            start: Pos,
            start_time: int,
            blocked: set[Pos],
            min_explosion: Dict[Pos, float],
            w: int,
            h: int,
            goal_pred: Callable[[Pos, int], bool],
            max_time: int,
    ) -> Optional[List[Pos]]:
        """
        BFS по (pos, t) с учётом таймеров бомб.
        Состояние (pos, t) означает: мы на pos в момент t.
        Требование выживания: мы должны пережить интервал до t+1 -> safe_to_stay(pos, leave_time=t+1).
        """
        # если уже в хорошем месте — можно вообще не двигаться
        if goal_pred(start, start_time) and self._safe_to_stay(start, leave_time=float(start_time + 1), min_explosion=min_explosion):
            return []

        q = deque([(start, start_time)])
        prev: Dict[Tuple[Pos, int], Tuple[Pos, int]] = {}
        seen = {(start, start_time)}

        while q:
            pos, t = q.popleft()
            if t >= start_time + max_time:
                continue

            # должны выжить до следующей секунды
            if not self._safe_to_stay(pos, leave_time=float(t + 1), min_explosion=min_explosion):
                continue

            for nb in neighbors4(pos):
                nt = t + 1
                if not inside(nb, w, h):
                    continue
                if nb in blocked:
                    continue

                state = (nb, nt)
                if state in seen:
                    continue

                # оказавшись в nb в момент nt, мы должны прожить до nt+1
                if not self._safe_to_stay(nb, leave_time=float(nt + 1), min_explosion=min_explosion):
                    continue

                seen.add(state)
                prev[state] = (pos, t)

                if goal_pred(nb, nt):
                    # восстановление пути: список клеток, в которые мы последовательно заходим
                    path_rev = [state]
                    while path_rev[-1] != (start, start_time):
                        path_rev.append(prev[path_rev[-1]])
                    path_rev.reverse()

                    # path_rev содержит состояния, берем позиции кроме стартовой
                    steps = [p for (p, _t) in path_rev][1:]
                    return steps[: self.cfg.max_plan_len]

                q.append(state)

        return None
