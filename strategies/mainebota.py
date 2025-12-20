import time
import json
import collections
from typing import Any, Dict, List, Tuple, Set, Optional

import requests

BASE_URL = "https://games-test.datsteam.dev"
TOKEN = "345c75ba-26c0-4f3e-acd4-09e63982ca52"

HEADERS = {
    "accept": "application/json",
    "Content-Type": "application/json",
    "X-Auth-Token": TOKEN,
}

ARENA_URL = f"{BASE_URL}/api/arena"
MOVE_URL = f"{BASE_URL}/api/move"

Pos = Tuple[int, int]


def get_arena() -> Dict[str, Any]:
    r = requests.get(ARENA_URL, headers=HEADERS, timeout=10)
    if not r.ok:
        raise RuntimeError(f"GET /api/arena -> HTTP {r.status_code}\n{r.text}")
    return r.json()


def post_move(payload: Dict[str, Any]) -> Dict[str, Any]:
    r = requests.post(MOVE_URL, headers=HEADERS, json=payload, timeout=10)
    if not r.ok:
        raise RuntimeError(f"POST /api/move -> HTTP {r.status_code}\n{r.text}")
    return r.json()


def in_bounds(p: Pos, w: int, h: int) -> bool:
    return 0 <= p[0] < w and 0 <= p[1] < h


def neighbors4(p: Pos) -> List[Pos]:
    x, y = p
    return [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]


def manhattan(a: Pos, b: Pos) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def bombs_to_blocked(bombs) -> Set[Pos]:
    blocked: Set[Pos] = set()
    for b in bombs or []:
        if isinstance(b, dict) and isinstance(b.get("pos"), list) and len(b["pos"]) == 2:
            blocked.add((b["pos"][0], b["pos"][1]))
        elif isinstance(b, list) and len(b) == 2:
            blocked.add((b[0], b[1]))
    return blocked


def bfs_path(start: Pos, goal: Pos, blocked: Set[Pos], w: int, h: int, max_len: int = 30) -> Optional[List[Pos]]:
    """Путь без диагоналей. Возвращает список клеток (НЕ включая start)."""
    if goal in blocked or not in_bounds(goal, w, h):
        return None
    if start == goal:
        return []

    q = collections.deque([start])
    prev: Dict[Pos, Optional[Pos]] = {start: None}

    while q:
        cur = q.popleft()
        if cur == goal:
            break
        for nxt in neighbors4(cur):
            if not in_bounds(nxt, w, h):
                continue
            if nxt in blocked:
                continue
            if nxt in prev:
                continue
            prev[nxt] = cur
            q.append(nxt)

    if goal not in prev:
        return None

    path: List[Pos] = []
    cur: Pos = goal
    while cur != start:
        path.append(cur)
        cur = prev[cur]  # type: ignore
    path.reverse()

    return path[:max_len]


def build_scout_path(start: Pos, primary: List[Pos], blocked: Set[Pos], w: int, h: int, steps: int = 5) -> List[Pos]:
    """Разведка на steps шагов: без мгновенного отката и без циклов."""
    fallback = [(0, 1), (0, -1), (1, 0), (-1, 0)]
    order = primary + [d for d in fallback if d not in primary] + [d for d in fallback if d in primary]

    cur = start
    prev: Optional[Pos] = None
    visited: Set[Pos] = {cur}
    path: List[Pos] = []

    for _ in range(steps):
        chosen: Optional[Pos] = None
        for dx, dy in order:
            nxt = (cur[0] + dx, cur[1] + dy)
            if not in_bounds(nxt, w, h):
                continue
            if nxt in blocked:
                continue
            if nxt == prev:
                continue
            if nxt in visited:
                continue
            chosen = nxt
            break

        if chosen is None:
            break

        prev = cur
        cur = chosen
        visited.add(cur)
        path.append(cur)

    return path


def choose_stand_cell(obstacle: Pos, start: Pos, blocked: Set[Pos], w: int, h: int) -> Optional[Pos]:
    """Выбираем свободную клетку рядом с obstacle, куда реально можно подойти."""
    candidates = [p for p in neighbors4(obstacle) if in_bounds(p, w, h) and p not in blocked]
    if not candidates:
        return None
    # ближе к бомберу — лучше
    candidates.sort(key=lambda p: manhattan(start, p))
    return candidates[0]


def slice_return_path(same_path: List[Pos], cur: Pos, home: Pos) -> List[Pos]:
    """
    Вернуться "тем же путём": same_path — список клеток подхода (start->...->stand),
    а мы хотим идти обратно. Если текущая позиция лежит на этом пути — идём назад по нему.
    """
    if not same_path:
        return []

    # полный маршрут подхода с home в начале:
    full = [home] + same_path
    try:
        idx = full.index(cur)
    except ValueError:
        return []  # не на маршруте — вызывающий сделает BFS домой

    # идти назад: full[idx-1], full[idx-2], ... home
    back = list(reversed(full[:idx]))
    return back


# Состояние на время работы скрипта (в памяти)
# mode:
#   scout   - разбегаться/разведка
#   approach- идём к obstacle и ставим бомбу
#   return  - возвращаемся тем же путём
#   wait    - ждём пока bombs_available снова станет >0
State = Dict[str, Any]
state: Dict[str, State] = {}


def main(loop_seconds: float = 1.2, scout_steps: int = 5):
    # 6 направлений для разведки
    scout_intents = [
        [(1, 0)],                 # вправо
        [(-1, 0)],                # влево
        [(0, 1)],                 # +Y
        [(0, -1)],                # -Y
        [(1, 0), (0, 1)],         # вправо + вниз
        [(-1, 0), (0, -1)],       # влево + вверх
    ]

    while True:
        arena = get_arena()
        w, h = arena["map_size"]

        arena_obj = arena.get("arena") or {}
        walls = {(p[0], p[1]) for p in (arena_obj.get("walls") or [])}
        obstacles_all = [(p[0], p[1]) for p in (arena_obj.get("obstacles") or [])]
        bombs_blocked = bombs_to_blocked(arena_obj.get("bombs") or [])

        bombers = arena.get("bombers") or []
        bomber_positions = {(b["pos"][0], b["pos"][1]) for b in bombers if isinstance(b, dict) and b.get("pos")}

        base_blocked = set(walls) | set(bombs_blocked) | set(obstacles_all)

        # Чтобы бомберы не выбирали один и тот же obstacle в текущем тике
        used_obstacles: Set[Pos] = set()

        cmds = []

        for i, b in enumerate(bombers[:6]):
            if not b.get("alive", True):
                continue

            bid = b["id"]
            cur = (b["pos"][0], b["pos"][1])
            can_move = bool(b.get("can_move", False))
            bombs_available = int(b.get("bombs_available") or 0)

            st = state.setdefault(bid, {"mode": "scout"})
            mode = st["mode"]

            # блоки для данного бомбера: базовые + позиции других бомберов
            blocked = set(base_blocked) | (bomber_positions - {cur})

            # если не может двигаться — команду не шлём
            if not can_move:
                continue

            path: List[Pos] = []
            bombs_points: List[Pos] = []

            # ----- 1) возврат тем же путём -----
            if mode == "return":
                home: Pos = st["home"]
                approach_path: List[Pos] = st.get("approach_path", [])

                back_same = slice_return_path(approach_path, cur, home)

                # режем до 30 шагов
                back_same = back_same[:30]

                # если не на маршруте — BFS домой
                if not back_same and cur != home:
                    p = bfs_path(cur, home, blocked, w, h, max_len=30)
                    if p:
                        back_same = p

                path = back_same

                # если уже дома — дальше решаем по бомбам
                if cur == home or not path:
                    if bombs_available > 0:
                        st["mode"] = "scout"
                    else:
                        st["mode"] = "wait"

            # ----- 2) ожидание восстановления бомбы -----
            if st["mode"] == "wait":
                if bombs_available > 0:
                    st["mode"] = "scout"
                else:
                    # стоим, не двигаемся
                    path = []
                    bombs_points = []

            # ----- 3) подход + бомба -----
            if st["mode"] in ("scout", "approach") and bombs_available > 0:
                # если obstacles видны — попробуем выбрать СВОЙ ближайший (не занятый другим бомбером в этом тике)
                if obstacles_all:
                    # отсортируем по расстоянию от текущего бомбера
                    obs_sorted = sorted(obstacles_all, key=lambda ob: manhattan(cur, ob))

                    chosen_ob = None
                    for ob in obs_sorted:
                        if ob not in used_obstacles:
                            chosen_ob = ob
                            used_obstacles.add(ob)
                            break

                    if chosen_ob is not None:
                        stand = choose_stand_cell(chosen_ob, cur, blocked, w, h)

                        if stand is not None:
                            # подход максимум 30, а возврат делаем на следующих тиках
                            approach = bfs_path(cur, stand, blocked, w, h, max_len=30)
                            if approach is not None and len(approach) > 0:
                                path = approach
                                bombs_points = [stand]  # ставим бомбу когда достигнем stand

                                # сохраним маршрут подхода, чтобы возвращаться тем же путём
                                st["mode"] = "return"
                                st["home"] = cur
                                st["approach_path"] = approach
                                st["stand"] = stand
                            else:
                                # подход не построился — разведка
                                st["mode"] = "scout"

            # ----- 4) разведка -----
            if st["mode"] == "scout" and not path:
                path = build_scout_path(cur, scout_intents[i % len(scout_intents)], blocked, w, h, steps=scout_steps)

            # если бомбы нет (bombs_available==0) и мы не в return — просто ждём, как ты хотела
            if bombs_available == 0 and st["mode"] not in ("return",):
                st["mode"] = "wait"
                path = []
                bombs_points = []

            cmds.append({
                "id": bid,
                "path": [[x, y] for (x, y) in path],
                "bombs": [[x, y] for (x, y) in bombs_points],
            })

            print(f"[{bid[:6]}] mode={st['mode']} can_move={can_move} bombs={bombs_available} pos={cur} "
                  f"obstacles_seen={len(obstacles_all)} path_len={len(path)} bombs_cmd={len(bombs_points)}")

        if cmds:
            payload = {"bombers": cmds}
            print("\nSENDING MOVE PAYLOAD:")
            print(json.dumps(payload, ensure_ascii=False, indent=2))

            resp = post_move(payload)
            print("\nMOVE RESPONSE:")
            print(json.dumps(resp, ensure_ascii=False, indent=2))

        time.sleep(loop_seconds)


if __name__ == "__main__":
    main()
