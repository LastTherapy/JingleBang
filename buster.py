from dataclasses import dataclass
from typing import Literal, Optional


Mode = Literal["clear", "safe", "greedy"]


@dataclass(frozen=True)
class LevelUpConfig:
    mode: Mode = "clear"
    reserve_points: int = 2  # держим запас на passability/bomber_count
    min_delay_ms: int = 3000 # ниже этого "фитиль" не опускаем по умолчанию


@dataclass(frozen=True)
class BoosterPick:
    index: int          # индекс в payload["available"]
    booster_type: str   # type из available
    reason: str


def _find_available_idx(payload: dict, booster_type: str) -> Optional[int]:
    for i, b in enumerate(payload.get("available", [])):
        if b.get("type") == booster_type:
            return i
    return None


def choose_booster(payload: dict, cfg: LevelUpConfig) -> Optional[BoosterPick]:
    st = payload.get("state", {})
    points = int(st.get("points", 0))

    # Если поинтов нет — ничего не покупаем
    if points <= 0:
        return None

    def can_buy(t: str) -> bool:
        idx = _find_available_idx(payload, t)
        if idx is None:
            return False
        cost = int(payload["available"][idx].get("cost", 1))
        return points >= cost

    def pick(t: str, reason: str) -> Optional[BoosterPick]:
        idx = _find_available_idx(payload, t)
        if idx is None:
            return None
        return BoosterPick(index=idx, booster_type=t, reason=reason)

    bombs = int(st.get("bombs", 1))
    delay = int(st.get("bomb_delay", 8000))
    rng = int(st.get("bomb_range", 1))
    speed = int(st.get("speed", 2))
    view = int(st.get("view", st.get("view_range", 5)))
    armor = int(st.get("armor", 0))

    # passability уровни (можем смотреть как “уже есть/нет”)
    can_pass_bombs = bool(st.get("can_pass_bombs", False))
    can_pass_obstacles = bool(st.get("can_pass_obstacles", False))
    can_pass_walls = bool(st.get("can_pass_walls", False))
    pass_level = int(can_pass_bombs) + int(can_pass_obstacles) + int(can_pass_walls)

    # Не тратим последние reserve_points (оставляем “ручку”)
    def spending_allowed(cost: int) -> bool:
        return (points - cost) >= cfg.reserve_points

    # --- РЕЖИМЫ ---
    if cfg.mode == "clear":
        # 1) фитиль вниз, но не ниже min_delay_ms
        if delay > cfg.min_delay_ms and can_buy("bomb_delay"):
            idx = _find_available_idx(payload, "bomb_delay")
            cost = int(payload["available"][idx]["cost"])
            if spending_allowed(cost):
                return pick("bomb_delay", f"clear: ускоряем цикл взрывов (delay {delay}->{max(delay-2000, cfg.min_delay_ms)})")

        # 2) карманы до 3
        if bombs < 3 and can_buy("bomb_count"):
            idx = _find_available_idx(payload, "bomb_count")
            cost = int(payload["available"][idx]["cost"])
            if spending_allowed(cost):
                return pick("bomb_count", f"clear: больше бомб одновременно (bombs {bombs}->{bombs+1})")

        # 3) радиус до 3
        if rng < 3 and can_buy("bomb_range"):
            idx = _find_available_idx(payload, "bomb_range")
            cost = int(payload["available"][idx]["cost"])
            if spending_allowed(cost):
                return pick("bomb_range", f"clear: больше задеваем препятствий (range {rng}->{rng+1})")

        # 4) дальше — скорость/зрение, но тоже с учётом резерва
        if speed < 5 and can_buy("speed"):
            idx = _find_available_idx(payload, "speed")
            cost = int(payload["available"][idx]["cost"])
            if spending_allowed(cost):
                return pick("speed", f"clear: ускоряем перемещения (speed {speed}->{speed+1})")

        if view < 11 and can_buy("vision"):
            idx = _find_available_idx(payload, "vision")
            cost = int(payload["available"][idx]["cost"])
            if spending_allowed(cost):
                return pick("vision", f"clear: меньше сюрпризов (view {view}->{view+3})")

    elif cfg.mode == "safe":
        # приоритет — vision, затем armor, затем passability
        if view < 14 and can_buy("vision"):
            idx = _find_available_idx(payload, "vision")
            cost = int(payload["available"][idx]["cost"])
            if spending_allowed(cost):
                return pick("vision", f"safe: видим угрозы раньше (view {view}->{view+3})")

        if armor < 2 and can_buy("armor"):
            idx = _find_available_idx(payload, "armor")
            cost = int(payload["available"][idx]["cost"])
            if spending_allowed(cost):
                return pick("armor", f"safe: переживаем взрывы лучше (armor {armor}->{armor+1})")

        # passability дорого (2), поэтому держим резерв иначе
        if pass_level < 1 and can_buy("passability"):
            idx = _find_available_idx(payload, "passability")
            cost = int(payload["available"][idx]["cost"])
            if spending_allowed(cost):
                return pick("passability", "safe: берём проходимость (минимум уровень 1)")

    elif cfg.mode == "greedy":
        # очки: range+count+speed
        if rng < 4 and can_buy("bomb_range"):
            idx = _find_available_idx(payload, "bomb_range")
            cost = int(payload["available"][idx]["cost"])
            if spending_allowed(cost):
                return pick("bomb_range", f"greedy: эффективнее фарм (range {rng}->{rng+1})")

        if bombs < 4 and can_buy("bomb_count"):
            idx = _find_available_idx(payload, "bomb_count")
            cost = int(payload["available"][idx]["cost"])
            if spending_allowed(cost):
                return pick("bomb_count", f"greedy: больше параллельных взрывов (bombs {bombs}->{bombs+1})")

        if speed < 5 and can_buy("speed"):
            idx = _find_available_idx(payload, "speed")
            cost = int(payload["available"][idx]["cost"])
            if spending_allowed(cost):
                return pick("speed", f"greedy: быстрее добегаем до целей (speed {speed}->{speed+1})")

    # Если мы сюда дошли — либо не можем тратить (из-за резерва),
    # либо всё упёрлось. Тогда можно потратить “остаток” на мелочь без резерва:
    # (например, если points >= reserve_points + 1)
    if points > cfg.reserve_points:
        # мягкий fallback: vision -> speed -> range -> armor
        for t in ("vision", "speed", "bomb_range", "armor"):
            idx = _find_available_idx(payload, t)
            if idx is None:
                continue
            cost = int(payload["available"][idx].get("cost", 1))
            if points >= cost:
                return BoosterPick(index=idx, booster_type=t, reason=f"fallback: тратим поинт на {t}")

    return None
