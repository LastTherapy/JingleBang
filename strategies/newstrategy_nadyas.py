import time
import json
import collections
from typing import Any, Dict, List, Tuple, Set, Optional

import requests

# =======================
# CONFIG
# =======================
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

# !!! ВАЖНО: если у вас "крестом на 1 клетку" — это 1
BLAST_RADIUS = 1

MAX_PATH = 30
LOOP_SECONDS = 1.2

OPENING_SECONDS = 60
OPENING_SCATTER_SECONDS = 6

DEBUG = True


# =======================
# HTTP
# =======================
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


# =======================
# GRID HELPERS
# =======================
def in_bounds(p: Pos, w: int, h: int) -> bool:
    return 0 <= p[0] < w and 0 <= p[1] < h


def neighbors4(p: Pos) -> List[Pos]:
    x, y = p
    return [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]


def manhattan(a: Pos, b: Pos) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def bombs_to_positions(bombs) -> List[Pos]:
    out: List[Pos] = []
    for b in bombs or []:
        if isinstance(b, dict) and isinstance(b.get("pos"), list) and len(b["pos"]) == 2:
            out.append((b["pos"][0], b["pos"][1]))
        elif isinstance(b, list) and len(b) == 2:
            out.append((b[0], b[1]))
    return out


def bfs_path(start: Pos, goal: Pos, blocked: Set[Pos], w: int, h: int, max_len: int = MAX_PATH) -> Optional[List[Pos]]:
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


# =======================
# DANGER (BLAST CROSS)
# =======================
def compute_blast_cells(bomb_pos: Pos, walls: Set[Pos], obstacles: Set[Pos], w: int, h: int, radius: int) -> Set[Pos]:
    bx, by = bomb_pos
    danger: Set[Pos] = {bomb_pos}

    for dx, dy in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
        for step in range(1, radius + 1):
            p = (bx + dx * step, by + dy * step)
            if not in_bounds(p, w, h):
                break
            if p in walls:
                break
            danger.add(p)
            if p in obstacles:
                break

    return danger


def compute_danger_map(bomb_positions: List[Pos], walls: Set[Pos], obstacles: Set[Pos], w: int, h: int, radius: int) -> Set[Pos]:
    danger: Set[Pos] = set()
    for bp in bomb_positions:
        danger |= compute_blast_cells(bp, walls, obstacles, w, h, radius)
    return danger


def find_nearest_safe(start: Pos, blocked: Set[Pos], danger: Set[Pos], w: int, h: int, max_len: int = MAX_PATH) -> Optional[List[Pos]]:
    if start not in danger:
        return []

    q = collections.deque([start])
    prev: Dict[Pos, Optional[Pos]] = {start: None}

    while q:
        cur = q.popleft()
        for nxt in neighbors4(cur):
            if not in_bounds(nxt, w, h):
                continue
            if nxt in blocked:
                continue
            if nxt in prev:
                continue

            prev[nxt] = cur
            if nxt not in danger:
                path: List[Pos] = []
                c = nxt
                while c != start:
                    path.append(c)
                    c = prev[c]  # type: ignore
                path.reverse()
                return path[:max_len]

            q.append(nxt)

    return None


# =======================
# SCATTER / SCOUT
# =======================
def build_scout_path(start: Pos, primary: List[Pos], blocked: Set[Pos], w: int, h: int, steps: int = 2) -> List[Pos]:
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


# =======================
# BOMB PLAN: place only if safe escape exists
# =======================
def choose_stand_cell(obstacle: Pos, start: Pos, blocked: Set[Pos], w: int, h: int) -> Optional[Pos]:
    candidates = [p for p in neighbors4(obstacle) if in_bounds(p, w, h) and p not in blocked]
    if not candidates:
        return None
    candidates.sort(key=lambda p: manhattan(start, p))
    return candidates[0]


def plan_bomb_and_escape_safely(
    start: Pos,
    chosen_obstacle: Pos,
    blocked: Set[Pos],
    walls: Set[Pos],
    obstacles_set: Set[Pos],
    existing_bombs: List[Pos],
    w: int,
    h: int,
) -> Optional[Tuple[List[Pos], Pos, str]]:
    """
    Возвращает (full_path, bomb_pos=stand, reason_on_fail_or_ok).
    """
    stand = choose_stand_cell(chosen_obstacle, start, blocked, w, h)
    if stand is None:
        return None

    approach = bfs_path(start, stand, blocked, w, h, max_len=MAX_PATH)
    if approach is None or len(approach) == 0:
        return None

    danger = compute_danger_map(existing_bombs + [stand], walls, obstacles_set, w, h, BLAST_RADIUS)

    back_same = list(reversed(approach[:-1]))
    escape: List[Pos] = []
    if back_same:
        escape.extend(back_same)
    else:
        step_opts = [n for n in neighbors4(stand) if in_bounds(n, w, h) and n not in blocked]
        if not step_opts:
            return None
        escape.append(step_opts[0])

    end_pos = escape[-1]

    if end_pos in danger:
        blocked_after_bomb = set(blocked) | {stand}
        extra = find_nearest_safe(end_pos, blocked_after_bomb, danger, w, h, max_len=MAX_PATH)
        if extra is None:
            return None
        escape.extend(extra)

    full = (approach + escape)[:MAX_PATH]

    if stand not in full:
        return None
    if full[-1] in danger:
        return None

    return full, stand, "OK"


# =======================
# OPENING CONTROL
# =======================
global_ctrl = {
    "round_id": None,
    "round_start_ts": 0.0,
    "opening_done": set(),
    "initiator_idx": 0,
}


def is_opening(now: float) -> bool:
    return now - global_ctrl["round_start_ts"] < OPENING_SECONDS


def is_scatter_only(now: float) -> bool:
    return now - global_ctrl["round_start_ts"] < OPENING_SCATTER_SECONDS


# =======================
# MAIN LOOP
# =======================
def main() -> None:
    scout_intents = [
        [(1, 0)],
        [(-1, 0)],
        [(0, 1)],
        [(0, -1)],
        [(1, 0), (0, 1)],
        [(-1, 0), (0, -1)],
    ]

    while True:
        now = time.time()
        arena = get_arena()

        round_id = arena.get("round")
        if global_ctrl["round_id"] != round_id:
            global_ctrl["round_id"] = round_id
            global_ctrl["round_start_ts"] = now
            global_ctrl["opening_done"] = set()
            global_ctrl["initiator_idx"] = 0
            print(f"\n=== NEW ROUND: {round_id} | opening={OPENING_SECONDS}s scatter_only={OPENING_SCATTER_SECONDS}s ===\n")

        w, h = arena["map_size"]
        arena_obj = arena.get("arena") or {}

        walls = {(p[0], p[1]) for p in (arena_obj.get("walls") or [])}
        obstacles_list = [(p[0], p[1]) for p in (arena_obj.get("obstacles") or [])]
        obstacles_set = set(obstacles_list)
        existing_bombs = bombs_to_positions(arena_obj.get("bombs") or [])

        base_blocked = set(walls) | set(obstacles_set) | set(existing_bombs)
        base_danger = compute_danger_map(existing_bombs, walls, obstacles_set, w, h, BLAST_RADIUS)

        bombers_all = arena.get("bombers") or []
        bombers = [b for b in bombers_all if b.get("alive", True)][:6]
        bomber_by_id = {b["id"]: b for b in bombers}
        bomber_ids = [b["id"] for b in bombers]
        bomber_positions = {(b["pos"][0], b["pos"][1]) for b in bombers if b.get("pos")}

        opening = is_opening(now)
        scatter_only = opening and is_scatter_only(now)

        if DEBUG:
            print(f"[STATE] opening={opening} scatter_only={scatter_only} obstacles_seen={len(obstacles_list)} bombs_seen={len(existing_bombs)}")

        # ===== scatter-only window =====
        if scatter_only:
            cmds = []
            for i, bid in enumerate(bomber_ids):
                b = bomber_by_id[bid]
                if not b.get("can_move", False):
                    continue
                pos = (b["pos"][0], b["pos"][1])
                blocked = set(base_blocked) | (bomber_positions - {pos})

                if pos in base_danger:
                    esc = find_nearest_safe(pos, blocked, base_danger, w, h, max_len=MAX_PATH)
                    path = esc if esc is not None else []
                else:
                    path = build_scout_path(pos, scout_intents[i % len(scout_intents)], blocked, w, h, steps=2)

                cmds.append({"id": bid, "path": [[x, y] for (x, y) in path], "bombs": []})

            payload = {"bombers": cmds}
            if DEBUG:
                print("\n[OPENING scatter-only] SENDING MOVE PAYLOAD:")
                print(json.dumps(payload, ensure_ascii=False, indent=2))
            resp = post_move(payload)
            if DEBUG:
                print("\nMOVE RESPONSE:")
                print(json.dumps(resp, ensure_ascii=False, indent=2))
            time.sleep(LOOP_SECONDS)
            continue

        # ===== opening initiator =====
        if opening and len(global_ctrl["opening_done"]) < min(6, len(bomber_ids)):
            initiator_id = None
            if bomber_ids:
                for _ in range(len(bomber_ids)):
                    idx = global_ctrl["initiator_idx"] % len(bomber_ids)
                    cand = bomber_ids[idx]
                    global_ctrl["initiator_idx"] = (idx + 1) % len(bomber_ids)
                    if cand not in global_ctrl["opening_done"]:
                        initiator_id = cand
                        break

            planned_initiator: Optional[Tuple[str, List[Pos], Pos]] = None

            if initiator_id is not None:
                ib = bomber_by_id.get(initiator_id)
                if ib and ib.get("can_move", False) and int(ib.get("bombs_available") or 0) > 0 and obstacles_list:
                    start = (ib["pos"][0], ib["pos"][1])
                    blocked = set(base_blocked) | (bomber_positions - {start})

                    chosen_ob = min(obstacles_list, key=lambda ob: manhattan(start, ob))
                    plan = plan_bomb_and_escape_safely(
                        start=start,
                        chosen_obstacle=chosen_ob,
                        blocked=blocked,
                        walls=walls,
                        obstacles_set=obstacles_set,
                        existing_bombs=existing_bombs,
                        w=w,
                        h=h,
                    )

                    if plan is not None:
                        path, bomb_pos, _ = plan
                        danger_with_new = compute_danger_map(existing_bombs + [bomb_pos], walls, obstacles_set, w, h, BLAST_RADIUS)

                        all_ok = True
                        bad_id = None
                        for oid in bomber_ids:
                            if oid == initiator_id:
                                continue
                            ob = bomber_by_id.get(oid)
                            if not ob:
                                continue
                            opos = (ob["pos"][0], ob["pos"][1])

                            if (not ob.get("can_move", False)) and (opos in danger_with_new):
                                all_ok = False
                                bad_id = oid
                                break

                            if opos in danger_with_new and ob.get("can_move", False):
                                other_blocked = set(base_blocked) | (bomber_positions - {opos}) | {bomb_pos}
                                esc = find_nearest_safe(opos, other_blocked, danger_with_new, w, h, max_len=MAX_PATH)
                                if esc is None:
                                    all_ok = False
                                    bad_id = oid
                                    break

                        if all_ok:
                            planned_initiator = (initiator_id, path, bomb_pos)
                        else:
                            if DEBUG:
                                print(f"[OPENING] initiator {initiator_id[:6]} bomb@{bomb_pos} REJECTED (no escape for {bad_id[:6] if bad_id else '?'})")
                    else:
                        if DEBUG:
                            print(f"[OPENING] initiator {initiator_id[:6]}: plan=None (no safe plan)")

            if DEBUG:
                print(f"[OPENING] initiator={initiator_id[:6] if initiator_id else None} planned={planned_initiator[0][:6] if planned_initiator else None} done={len(global_ctrl['opening_done'])}")

            cmds = []
            if planned_initiator:
                _, _, bomb_pos = planned_initiator
                danger_now = compute_danger_map(existing_bombs + [bomb_pos], walls, obstacles_set, w, h, BLAST_RADIUS)
            else:
                danger_now = base_danger

            for i, bid in enumerate(bomber_ids):
                b = bomber_by_id[bid]
                if not b.get("can_move", False):
                    continue

                pos = (b["pos"][0], b["pos"][1])
                blocked = set(base_blocked) | (bomber_positions - {pos})
                if planned_initiator:
                    blocked |= {planned_initiator[2]}

                if planned_initiator and bid == planned_initiator[0]:
                    _, path, bomb_pos = planned_initiator
                    cmds.append({"id": bid, "path": [[x, y] for (x, y) in path], "bombs": [[bomb_pos[0], bomb_pos[1]]]})
                    global_ctrl["opening_done"].add(bid)
                    continue

                if pos in danger_now:
                    esc = find_nearest_safe(pos, blocked, danger_now, w, h, max_len=MAX_PATH)
                    path = esc if esc is not None else []
                    cmds.append({"id": bid, "path": [[x, y] for (x, y) in path], "bombs": []})
                else:
                    # если инициатор не смог — раздвигаемся, а не стоим
                    if planned_initiator is None:
                        path = build_scout_path(pos, scout_intents[i % len(scout_intents)], blocked, w, h, steps=2)
                        cmds.append({"id": bid, "path": [[x, y] for (x, y) in path], "bombs": []})
                    else:
                        cmds.append({"id": bid, "path": [], "bombs": []})

            payload = {"bombers": cmds}
            if DEBUG:
                print("\n[OPENING] SENDING MOVE PAYLOAD:")
                print(json.dumps(payload, ensure_ascii=False, indent=2))
            resp = post_move(payload)
            if DEBUG:
                print("\nMOVE RESPONSE:")
                print(json.dumps(resp, ensure_ascii=False, indent=2))

            time.sleep(LOOP_SECONDS)
            continue

        # ===== AUTONOMOUS =====
        used_obstacles: Set[Pos] = set()
        cmds = []

        for i, bid in enumerate(bomber_ids):
            b = bomber_by_id[bid]
            if not b.get("can_move", False):
                continue

            pos = (b["pos"][0], b["pos"][1])
            bombs_avail = int(b.get("bombs_available") or 0)
            blocked = set(base_blocked) | (bomber_positions - {pos})

            # если уже в danger от существующих бомб — сначала эвакуация
            if pos in base_danger:
                esc = find_nearest_safe(pos, blocked, base_danger, w, h, max_len=MAX_PATH)
                path = esc if esc is not None else []
                cmds.append({"id": bid, "path": [[x, y] for (x, y) in path], "bombs": []})
                continue

            if bombs_avail <= 0:
                cmds.append({"id": bid, "path": [], "bombs": []})
                continue

            cmd = None
            if obstacles_list:
                obs_sorted = sorted(obstacles_list, key=lambda ob: manhattan(pos, ob))
                chosen_ob = None
                for ob in obs_sorted:
                    if ob not in used_obstacles:
                        chosen_ob = ob
                        used_obstacles.add(ob)
                        break

                if chosen_ob is not None:
                    plan = plan_bomb_and_escape_safely(
                        start=pos,
                        chosen_obstacle=chosen_ob,
                        blocked=blocked,
                        walls=walls,
                        obstacles_set=obstacles_set,
                        existing_bombs=existing_bombs,
                        w=w,
                        h=h,
                    )
                    if plan is not None:
                        path, bomb_pos, _ = plan
                        cmd = {"id": bid, "path": [[x, y] for (x, y) in path], "bombs": [[bomb_pos[0], bomb_pos[1]]]}

            if cmd:
                cmds.append(cmd)
            else:
                # если не можем бомбить — не дёргаемся, а делаем 3 шага раздвижки
                path = build_scout_path(pos, scout_intents[i % len(scout_intents)], blocked, w, h, steps=3)
                cmds.append({"id": bid, "path": [[x, y] for (x, y) in path], "bombs": []})

        payload = {"bombers": cmds}
        if DEBUG:
            print("\n[AUTO] SENDING MOVE PAYLOAD:")
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        resp = post_move(payload)
        if DEBUG:
            print("\nMOVE RESPONSE:")
            print(json.dumps(resp, ensure_ascii=False, indent=2))

        time.sleep(LOOP_SECONDS)


if __name__ == "__main__":
    main()
