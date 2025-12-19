from __future__ import annotations

import random
import time
from collections import deque
from typing import Iterable, List, Optional, Set, Tuple

from model import Bomb, GameState, MoveCommand, Pos


class GridNavigator:
    def __init__(self, map_size: Tuple[int, int], walls: Iterable[Pos], obstacles: Iterable[Pos], bombs: Iterable[Bomb]) -> None:
        self.width, self.height = map_size
        self.walls: Set[Pos] = set(walls)
        self.obstacles: Set[Pos] = set(obstacles)
        self.bombs: List[Bomb] = list(bombs)

    def inside(self, pos: Pos) -> bool:
        x, y = pos
        return 0 <= x < self.width and 0 <= y < self.height

    def is_blocked(self, pos: Pos) -> bool:
        return pos in self.walls or pos in self.obstacles or self._is_bomb_at(pos)

    def _is_bomb_at(self, pos: Pos) -> bool:
        return any(bomb.pos == pos for bomb in self.bombs)

    def neighbors(self, pos: Pos) -> List[Pos]:
        x, y = pos
        candidates = [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]
        return [p for p in candidates if self.inside(p) and not self.is_blocked(p)]

    def shortest_path(
        self, start: Pos, goals: Set[Pos], forbidden: Set[Pos], max_steps: int = 30
    ) -> Optional[List[Pos]]:
        """
        BFS до ближайшей точки из goals. Возвращает путь (без стартовой клетки).
        """
        if not goals:
            return None
        if start in goals:
            return []

        queue = deque([(start, 0)])
        parents: dict[Pos, Optional[Pos]] = {start: None}

        while queue:
            current, dist = queue.popleft()
            for n in self.neighbors(current):
                if n in parents or n in forbidden:
                    continue
                parents[n] = current
                if n in goals:
                    return self._reconstruct_path(parents, n)[1:]  # без стартовой клетки
                if dist + 1 < max_steps:
                    queue.append((n, dist + 1))
        return None

    def _reconstruct_path(self, parents: dict[Pos, Optional[Pos]], end: Pos) -> List[Pos]:
        path: List[Pos] = [end]
        cur = end
        while parents[cur] is not None:
            cur = parents[cur]  # type: ignore[assignment]
            path.append(cur)
        path.reverse()
        return path

    def compute_danger_zone(self, timer_threshold: float = 2.5) -> Set[Pos]:
        """
        Приближенно оцениваем зоны поражения бомб, которые скоро рванут.
        """
        danger: Set[Pos] = set()
        for bomb in self.bombs:
            if bomb.timer > timer_threshold:
                continue
            danger.add(bomb.pos)
            danger |= self._blast_for_bomb(bomb)
        return danger

    def _blast_for_bomb(self, bomb: Bomb) -> Set[Pos]:
        cells: Set[Pos] = set()
        directions = [(1, 0), (-1, 0), (0, 1), (0, -1)]
        for dx, dy in directions:
            for step in range(1, bomb.range + 1):
                pos = (bomb.pos[0] + dx * step, bomb.pos[1] + dy * step)
                if not self.inside(pos):
                    break
                cells.add(pos)
                if pos in self.walls or pos in self.obstacles:
                    break
        return cells

    def reachable_adjacent_to_obstacles(self) -> Set[Pos]:
        positions: Set[Pos] = set()
        for ox, oy in self.obstacles:
            for pos in [(ox + 1, oy), (ox - 1, oy), (ox, oy + 1), (ox, oy - 1)]:
                if self.inside(pos) and not self.is_blocked(pos):
                    positions.add(pos)
        return positions


class GreedyBomberStrategy:
    def __init__(
        self,
        *,
        timer_threshold: float = 2.5,
        max_steps: int = 12,
        wander_steps: int = 6,
        cooldown: float = 0.6,
    ) -> None:
        self.timer_threshold = timer_threshold
        self.max_steps = max_steps
        self.wander_steps = wander_steps
        self.cooldown = cooldown
        self.random = random.Random()
        self.last_command_at: dict[str, float] = {}

    def decide(self, state: GameState) -> List[MoveCommand]:
        navigator = GridNavigator(
            map_size=state.map_size,
            walls=state.arena.walls,
            obstacles=state.arena.obstacles,
            bombs=state.arena.bombs,
        )
        danger = navigator.compute_danger_zone(timer_threshold=self.timer_threshold)

        commands: List[MoveCommand] = []
        now = time.monotonic()
        for bomber in state.bombers:
            if not bomber.alive or not bomber.can_move:
                continue
            last_ts = self.last_command_at.get(bomber.id, 0.0)
            if now - last_ts < self.cooldown:
                continue

            command = self._decide_for_bomber(bomber.pos, bomber.id, bomber.bombs_available, navigator, danger)
            if command and (command.path or command.bombs):
                commands.append(command)
                self.last_command_at[bomber.id] = now
        return commands

    def _decide_for_bomber(
        self,
        start: Pos,
        bomber_id: str,
        bombs_available: int,
        navigator: GridNavigator,
        danger: Set[Pos],
    ) -> Optional[MoveCommand]:
        # 1. Если стоим в опасной зоне — отходим.
        if start in danger:
            safe_cells = self._safe_cells(navigator, danger)
            path = navigator.shortest_path(start, safe_cells, forbidden=danger, max_steps=self.max_steps)
            if path is None:
                return None
            return MoveCommand(bomber_id=bomber_id, path=path[: self.max_steps], bombs=[])

        # 2. Ищем ближайший подход к разрушимому препятствию.
        adjacent = navigator.reachable_adjacent_to_obstacles()
        path = navigator.shortest_path(start, adjacent, forbidden=danger, max_steps=self.max_steps)
        if path is not None:
            truncated = path[: self.max_steps]
            bombs: List[Pos] = []
            if bombs_available > 0:
                drop_bomb = truncated[-1] if truncated else start
                bombs = [drop_bomb]
            return MoveCommand(bomber_id=bomber_id, path=truncated, bombs=bombs)

        # 3. Блуждаем в безопасной зоне, чтобы раскрывать карту.
        path = self._wander(start, navigator, danger)
        return MoveCommand(bomber_id=bomber_id, path=path, bombs=[]) if path else None

    def _safe_cells(self, navigator: GridNavigator, danger: Set[Pos]) -> Set[Pos]:
        safe = set()
        for x in range(navigator.width):
            for y in range(navigator.height):
                pos = (x, y)
                if navigator.is_blocked(pos) or pos in danger:
                    continue
                safe.add(pos)
        return safe

    def _wander(self, start: Pos, navigator: GridNavigator, danger: Set[Pos]) -> List[Pos]:
        current = start
        path: List[Pos] = []
        for _ in range(self.wander_steps):
            options = [p for p in navigator.neighbors(current) if p not in danger]
            if not options:
                break
            current = self.random.choice(options)
            path.append(current)
        return path
